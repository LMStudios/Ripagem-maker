"""Mapa de tempo com inserções: preserva a fonte e abre espaço para falas maiores."""
import math,re,subprocess
from pathlib import Path
from . import trocas as T,ml_core as M
# Entradas por chamada do FFmpeg; o resto da linha (caminhos do FFmpeg e do script) cabe na folga até 32 mil.
_ARGS_LIMIT=24000

def margin_ms():
    from . import armazenamento
    return armazenamento.read().get('margem_fala_ms',200)

def mute_start(a,previous,fps):
    margin=margin_ms()
    left=max(previous,a-round(margin/1000*fps))
    # Não deixa uma sílaba isolada entre duas substituições próximas.
    if margin and 0<left-previous<=round(.12*fps):left=previous
    return left

def edits(out,rows,info):
    if not rows:return []
    fps=info['fps'];expand=T.load(out).get('modo_duracao','fixo')=='expandir';offset=0;result=[]
    if expand:T.prefetch([Path(out)/row['audio']['fit'] for row in rows],M.FFPROBE)
    for row in rows:
        a=round(row['inicio_ms']/1000*fps);b=round(row['fim_ms']/1000*fps)
        length=max(b-a,math.ceil(T.probe(Path(out)/row['audio']['fit'])['duration']*fps-1e-3)) if expand else b-a
        extra=length-(b-a);result.append({'a':a,'b':b,'start':a+offset,'end':a+offset+length,'extra':extra,'row':row});offset+=extra
    return result

def shift(frame,changes):return frame+sum(e['extra'] for e in changes if e['b']<=frame)

def hold(job,out,path,frame,length,info):
    directory=Path(out)/'trocas/expansoes';directory.mkdir(parents=True,exist_ok=True)
    stat=Path(path).stat();key=T.digest([T.path_text(path),stat.st_size,stat.st_mtime_ns,frame,length,info['fps']]);target=directory/(key+'.mp4')
    if target.exists():return target
    fps=info['fps'];tmp=directory/(key+'.tmp.mp4')
    still=directory/(key+'.frame.png')
    try:
        M.run_proc(job,[M.FFMPEG,'-y','-v','error','-ss',f'{max(0,frame)/fps:.9f}','-i',str(path),'-an','-frames:v','1','-update','1',str(still)])
        M.run_proc(job,[M.FFMPEG,'-y','-v','error','-loop','1','-framerate',str(fps),'-i',str(still),'-an','-frames:v',str(length),'-r',str(fps),'-fps_mode','cfr','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(tmp)])
        if abs(T.probe(tmp,False)['duration']-length/fps)>max(.003,.2/fps):raise ValueError('Não foi possível estender a imagem para a fala inteira.')
        tmp.replace(target)
    finally:
        if tmp.exists():tmp.unlink()
        if still.exists():still.unlink()
    return target

def parts(job,out,rows,visuals,info):
    changes=edits(out,rows,info);source=T.source(out);frames=round(info['duration']*info['fps']);video=[];overlays=[];cursor=0;offset=0
    for e in changes:
        if e['extra']:
            if e['b']>cursor:video.append({'path':source,'start':cursor+offset,'end':e['b']+offset,'in':cursor})
            if info['video']:video.append({'path':hold(job,out,source,e['b']-1,e['extra'],info),'start':e['b']+offset,'end':e['b']+offset+e['extra'],'in':0})
            cursor=e['b'];offset+=e['extra']
    if cursor<frames:video.append({'path':source,'start':cursor+offset,'end':frames+offset,'in':cursor})
    for v in visuals:
        a=v['start_frame'];b=v['end_frame'];path=Path(out)/v['file'];cursor=a
        if v.get('timeline_fechada'):
            from . import fechamento as FC
            for lo,hi,source_in in FC.expand(a,b,FC.windows(changes,info['fps'])):
                overlays.append({'path':path,'start':lo,'end':hi,'in':source_in,'source_original':True,'timeline_fechada':True})
            continue
        if v.get('timeline_final'):
            overlays.append({'path':path,'start':a,'end':b,'in':0,'source_original':True});continue
        for e in changes:
            if not e['extra'] or not a<e['b']<=b:continue
            stop=e['b'];start=shift(cursor,changes)
            if cursor<stop:overlays.append({'path':path,'start':start,'end':start+stop-cursor,'in':cursor-a})
            start=shift(stop,changes)-e['extra'];overlays.append({'path':hold(job,out,path,stop-a-1,e['extra'],info),'start':start,'end':start+e['extra'],'in':0})
            cursor=stop
        if cursor<b:
            start=shift(cursor,changes);overlays.append({'path':path,'start':start,'end':start+b-cursor,'in':cursor-a})
    return {'changes':changes,'video':video,'visuals':overlays,'frames':frames+offset,'extra_frames':offset}

def audio_mix(job,out,rows,info,target):
    changes=edits(out,rows,info);pieces=[];cursor=0;removed=0;frames=round(info['duration']*info['fps']);fps=info['fps']
    for i,e in enumerate(changes,1):
        left=mute_start(e['a'],cursor,fps)
        if cursor<left:pieces.append(('old',cursor,left))
        removed+=e['a']-left
        pieces.append(('new',i,e['end']-e['start']));cursor=e['b']
    if cursor<frames:pieces.append(('old',cursor,frames))
    import tempfile
    # O áudio original é extraído uma vez sem compressão e cada pedaço lê só o seu trecho, com corte exato.
    # Antes, cada pedaço recebia o áudio inteiro e descartava o resto: 15× mais lento e com falas até 8 ms fora do lugar.
    with tempfile.TemporaryDirectory(prefix='mix-',dir=Path(out)/'trocas') as temp:
        wav=Path(temp)/'original.wav'
        job.step='Preparando o áudio original para a montagem'
        M.run_proc(job,[M.FFMPEG,'-y','-v','error','-i',str(T.source(out)),'-map','0:a:0','-vn','-c:a','pcm_s16le',str(wav)])
        job.step='Montando o áudio final da montagem'
        # Filtros em arquivo e entradas em lotes: a linha de comando do Windows aceita só ~32 mil caracteres.
        def mix(inputs,chains,dest,codec):
            labels=''.join(f'[a{i}]' for i in range(len(chains)))
            script=Path(temp)/'filtros.txt';script.write_text(';'.join(chains+[labels+f'concat=n={len(chains)}:v=0:a=1[aout]']),encoding='utf-8')
            M.run_proc(job,[M.FFMPEG,'-y','-v','error',*inputs,'-/filter_complex',str(script),'-map','[aout]',*codec,str(dest)])
        parts=[];inputs=[];chains=[];n=0
        for kind,a,b in pieces:
            if kind=='silence':args=[];chain=f'anullsrc=r=48000:cl=stereo,atrim=duration={b/fps:.9f}'
            elif kind=='old':args=['-ss',f'{a/fps:.9f}','-t',f'{(b-a)/fps:.9f}','-i',str(wav)];chain=f'[{n}:a]atrim=duration={(b-a)/fps:.9f}'
            else:args=['-i',str(Path(out)/rows[a-1]['audio']['fit'])];chain=f'[{n}:a]apad,atrim=duration={b/fps:.9f}'
            if args and len(subprocess.list2cmdline(inputs+args))>_ARGS_LIMIT:
                parts.append(Path(temp)/f'lote{len(parts)}.wav');mix(inputs,chains,parts[-1],M.aac_args('x.wav'))
                inputs=[];chains=[];n=0;chain=re.sub(r'^\[\d+:a\]','[0:a]',chain)
            inputs+=args;n+=bool(args)
            chains.append(chain+f',aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[a{len(chains)}]')
        if parts:
            parts.append(Path(temp)/f'lote{len(parts)}.wav');mix(inputs,chains,parts[-1],M.aac_args('x.wav'))
            inputs=[x for p in parts for x in ('-i',str(p))];chains=[f'[{i}:a]asetpts=PTS-STARTPTS[a{i}]' for i in range(len(parts))]
        mix(inputs,chains,target,M.aac_args(target))
    from .editorial import add_music
    return add_music(job,out,target,(frames+sum(e['extra'] for e in changes)-removed)/fps)

def preview(job,out,plan,rows,visuals,info):
    out=Path(out);fps=info['fps'];frames=round(info['duration']*fps);expected=T.preview_signature(out);dest=out/'trocas'/('previa_'+__import__('uuid').uuid4().hex[:8]);dest.mkdir(parents=True);clips=[];added=0
    for n,row in enumerate(rows,1):
        if job.cancel:raise M.Cancelled()
        global_changes=edits(out,rows,info);before=sum(c['extra'] for c in global_changes if c['b']<=round(row['inicio_ms']/1000*fps));local_visuals=[dict(v,start_frame=v['start_frame']-before,end_frame=v['end_frame']-before) if v.get('timeline_final') else v for v in visuals]
        layout=parts(job,out,[row],local_visuals,info);e=layout['changes'][0];added+=e['extra'];a=max(0,e['a']-round(2*fps));b=min(frames,e['b']+round(2*fps));duration=(b-a+e['extra'])/fps
        cmd=[M.FFMPEG,'-y','-v','error','-ss',str(a/fps),'-t',str((b-a)/fps),'-i',str(T.source(out)),'-i',str(out/row['audio']['fit'])];filters=[];audio=[]
        previous=max((c['b'] for c in global_changes if c['b']<=e['a']),default=0)
        left=max(a,mute_start(e['a'],previous,fps));removed=e['a']-left
        if left>a:
            filters.append(f'[0:a]atrim=end={(left-a)/fps:.9f},aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[ab]');audio.append('[ab]')
        filters.append(f'[1:a]apad,atrim=duration={(e["end"]-e["start"])/fps:.9f},aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[an]');audio.append('[an]')
        if b>e['b']:
            filters.append(f'[0:a]atrim=start={(e["b"]-a)/fps:.9f}:end={(b-a)/fps:.9f},aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[aa]');audio.append('[aa]')
        filters.append(''.join(audio)+f'concat=n={len(audio)}:v=0:a=1[aout]');next_input=2
        if info['video']:
            vp=[]
            for part in layout['video']:
                start=max(a,part['start']);end=min(b+e['extra'],part['end'])
                if start>=end:continue
                source_in=part['in']+start-part['start'];label='vp'+str(len(vp));vp.append('['+label+']')
                if part['path']==T.source(out):chain=f'[0:v]trim=start={(source_in-a)/fps:.9f}:end={(source_in-a+end-start)/fps:.9f}'
                else:
                    cmd+=['-ss',str(source_in/fps),'-t',str((end-start)/fps),'-i',str(part['path'])];chain=f'[{next_input}:v]trim=end_frame={end-start}';next_input+=1
                filters.append(chain+f',fps={fps:.8f},setpts=N/({fps:.8f}*TB)[{label}]')
            filters.append(''.join(vp)+f'concat=n={len(vp)}:v=1:a=0[vbase]');base='vbase'
            for i,part in enumerate(layout['visuals']):
                start=max(a,part['start']);end=min(b+e['extra'],part['end'])
                if start>=end:continue
                source_in=part['in']+start-part['start'];cmd+=['-ss',str(source_in/fps),'-t',str((end-start)/fps),'-i',str(part['path'])]
                label=f'ov{i}';filters.append(f'[{next_input}:v]fps={fps:.8f},scale={info["width"]}:{info["height"]}:force_original_aspect_ratio=increase,crop={info["width"]}:{info["height"]},setsar=1,setpts=PTS-STARTPTS+{(start-a)/fps:.9f}/TB[{label}]');next_input+=1
                new=f'vov{i}';filters.append(f"[{base}][{label}]overlay=eof_action=pass:enable='between(t,{(start-a)/fps:.9f},{(end-a)/fps:.9f})'[{new}]");base=new
            filters.append(f'[{base}]scale=trunc(iw*min(1\\,720/ih)/2)*2:trunc(ih*min(1\\,720/ih)/2)*2,setsar=1[vout]')
        from . import fechamento as FC
        video_label=FC.video_filter(filters,'vout',[(left-a,e['a']-a)] if removed else [],b-a+e['extra'],fps) if info['video'] else None
        duration-=removed/fps;added-=removed
        target=dest/(f'{n:03d}.mp4' if info['video'] else f'{n:03d}.m4a');cmd+=['-filter_complex',';'.join(filters),'-map','[aout]']
        if info['video']:cmd+=['-map','['+video_label+']','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-r',str(fps)]
        cmd+=['-c:a','aac','-t',str(duration),str(target)];job.step=f'Prévia com espaço ampliado · {n} de {len(rows)}';job.pct=(n-1)/len(rows);M.run_proc(job,cmd)
        from .editorial import add_music
        global_changes=edits(out,rows,info);target=add_music(job,out,target,duration,shift(a,global_changes)/fps);clips.append(target)
    listing=dest/'lista.txt';listing.write_text(''.join("file '"+p.name+"'\n" for p in clips));target=dest/('PREVIA_TROCAS.mp4' if info['video'] else 'PREVIA_TROCAS.m4a')
    M.run_proc(job,[M.FFMPEG,'-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(target)])
    result={'assinatura':expected,'arquivo':str(target.relative_to(out)),'trechos':len(rows),'pendentes':len([r for r in plan['itens'] if r['aprovado']])-len(rows),'video':info['video'],'visuais':bool(visuals),'acrescimo_s':added/fps,'observacao':'Falas na velocidade natural. A timeline abre espaço e mantém a última imagem no intervalo extra; o restante segue sincronizado.'}
    with T.LOCK:
        if T.preview_signature(out)!=expected:raise ValueError('A montagem mudou. Gere uma nova prévia.')
        current=T.load(out);current['previa']=result;T.write(T.plan_path(out),current)
    job.pct=1;job.step='Prévia pronta com espaço para as falas completas';return result

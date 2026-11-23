"""Plano de trocas aprovado, áudios por speaker, encaixe e montagem não destrutiva."""
import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET
from . import ml_core as M
from .media_cache import metadata,prefetch

LOCK=threading.RLock()

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]

def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
    finally:
        if tmp.exists():tmp.unlink()

def source_identity(path):
    """Identifica o vídeo por tamanho e data: o caminho muda ao mover a pasta e os acentos podem vir em formas Unicode diferentes."""
    stat=Path(path).stat()
    return [stat.st_size,stat.st_mtime_ns]

def path_text(path):
    """Caminho absoluto numa só forma Unicode (EDIÇÃO composta), para comparações estáveis."""
    import unicodedata
    return unicodedata.normalize('NFC',str(Path(path).resolve()))

def legacy_path_texts(path):
    """Formas com que versões anteriores gravaram o caminho (aceitas para não invalidar trabalhos existentes)."""
    import unicodedata
    text=str(Path(path).resolve())
    return list(dict.fromkeys([text,unicodedata.normalize('NFC',text),unicodedata.normalize('NFD',text)]))

def source(out):
    path=next(iter(Path(out).glob('_fonte.*')),None)
    if not path:raise ValueError('Áudio/vídeo de origem ausente. Reenvie a fonte para este trabalho.')
    return path

def probe(path,require_audio=True):
    d=metadata(path,M.FFPROBE);audio=next((s for s in d['streams'] if s['codec_type']=='audio'),None)
    video=next((s for s in d['streams'] if s['codec_type']=='video' and not s.get('disposition',{}).get('attached_pic')),None)
    if not audio and require_audio:raise ValueError('A mídia não tem áudio.')
    has_audio=bool(audio);audio=audio or {}
    fps=30.
    if video:
        a,b=video.get('avg_frame_rate','30/1').split('/');fps=float(a)/float(b) if float(b) else 30.
        if not math.isfinite(fps) or fps<=0:fps=30.
    width,height=(video['width'],video['height']) if video else (1920,1080)
    rotation=next((int(s.get('rotation',0)) for s in (video or {}).get('side_data_list',[]) if 'rotation' in s),0)
    if abs(rotation)%180==90:width,height=height,width
    return {'duration':float(d['format']['duration']),'fps':fps,'width':width,'height':height,'video':bool(video),'has_audio':has_audio,'sample_rate':int(audio.get('sample_rate',48000)),'channels':int(audio.get('channels',1))}

def plan_path(out):return Path(out)/'trocas'/'plano.json'

def form_ready(row,text):
    return (not row.get('forma_pendente') or row.get('forma_ia_aplicada')
            or text.strip()!=row.get('base_novo',row['original']).strip())

def load(out):
    path=plan_path(out)
    if not path.exists():raise ValueError('Monte a lista de trocas primeiro.')
    plan=json.loads(path.read_text())
    if plan.get('forma',{}).get('ativo'):
        for row in plan['itens']:
            if row.get('forma_confirmada') and not form_ready(row,row['novo']):
                row['forma_confirmada']=False
    return plan

def build(out,product,include_prices=False,form_config=None,only_prices=False):
    with LOCK:
        from . import otimizacao as OT
        only_prices=bool(only_prices or OT.active(out))
        if only_prices:include_prices=True
        candidates=[]
        for file in Path(out).glob('frases_*.json'):
            data=json.loads(file.read_text())
            if data.get('produto','').casefold()==product.strip().casefold():candidates.append((file.stat().st_mtime,data))
        if not candidates:raise ValueError('Busque as frases do produto antes de montar a lista.')
        meta=max(candidates,key=lambda x:x[0])[1]
        price_file=Path(out)/'precos_TROCA.json'
        prices=json.loads(price_file.read_text()).get('frases',[]) if include_prices and price_file.exists() else []
        if only_prices:
            # Exclusive scope: never merge product substitutions or usage-form adaptations.
            phrases=[dict(p,origem='preco_kit') for p in prices if p.get('novo') and p['novo']!=p['text']]
        else:
            phrases=[dict(p,origem='produto') for p in meta['frases']]
            for p in prices:
                same=next((r for r in phrases if r['start']==p['start'] and r['end']==p['end'] and r['text']==p['text']),None)
                if same:
                    changed=p.get('novo') or p['text']
                    if meta.get('produto_novo'):changed=re.sub(re.escape(product),lambda _:meta['produto_novo'],changed,flags=re.I)
                    same.update(novo=changed,origem='produto_e_preco')
                else:phrases.append(dict(p,origem='preco_kit'))
        raw=json.loads((Path(out)/'transcricao_bruta.json').read_text())
        from . import editorial as E
        from .mencoes import transcript_words
        raw['words']=transcript_words(raw)
        speakers=sorted({str(w['speaker']) for w in raw['words'] if w.get('speaker') is not None})
        previous=load(out) if plan_path(out).exists() else {}
        from . import formas
        form=formas.normalize(previous.get('forma',{}) if form_config is None else form_config)
        recovered=previous.get('recuperadas_visuais',[])
        if not only_prices:
            for saved in recovered:
                p=dict(saved)
                if p.get('substitui_id'):phrases=[r for r in phrases if digest([r['start'],r['end'],r['text'],r['origem']])!=p['substitui_id']]
                if any(r['start']<=p['start'] and r['end']>=p['end'] for r in phrases):continue
                old_name=p.get('produto_novo')
                if old_name and old_name!=meta.get('produto_novo'):p['novo']=p['novo'].replace(old_name,meta.get('produto_novo') or product)
                phrases.append(p)
        if not only_prices:phrases= formas.augment(phrases,raw,form,[product]+[a.strip() for a in str(meta.get('produto_aliases') or '').split(',')],meta.get('produto_novo') or '')
        old={r['id']:r for r in previous.get('itens',[]) if previous.get('somente_valores',False)==only_prices}
        info=probe(source(out));rows=[]
        for p in sorted(phrases,key=lambda r:r['start']):
            key=digest([p['start'],p['end'],p['text'],p['origem']]);prior=old.get(key,{})
            speaker,pending_speaker,speaker_notice=E.speaker_info(p,raw)
            row={'id':key,'inicio_ms':p['start'],'fim_ms':p['end'],'original':p['text'],'novo':p.get('novo') or p['text'],'speaker':speaker,'speaker_pendente':pending_speaker,'speaker_aviso':speaker_notice,'origem':p['origem'],'aprovado':False}
            if prior.get('base_novo')==(p.get('novo') or p['text']):row.update({k:prior[k] for k in ('novo','speaker','aprovado','audio','speaker_confirmado','historico_audio','forma_confirmada','mencao_descartada') if k in prior})
            if p.get('mencoes_revisar'):
                row['mencoes_revisar']=p['mencoes_revisar']
                if p.get('novo_sem_sugestoes') and p.get('novo')==p.get('novo_com_sugestoes'):
                    row['novo_sem_sugestoes']=p['novo_sem_sugestoes']
            if row.get('speaker_confirmado'):row['speaker_pendente']=False;row['speaker_aviso']=''
            if prior.get('audio') and prior.get('base_novo')!=(p.get('novo') or p['text']):row['historico_audio']=prior.get('historico_audio',[])+[copy.deepcopy(prior['audio'])]
            row['base_novo']=p.get('novo') or p['text'];row['duracao_s']=(p['end']-p['start'])/1000
            row['original_audio']=prior.get('original_audio') or p.get('file')
            if p.get('forma_detectada'):
                row.update(forma_detectada=True,forma_avisos=p.get('forma_avisos',[]),forma_pendente=p.get('forma_pendente',False))
                if previous.get('forma')!=form:row['forma_confirmada']=False
                elif prior.get('forma_ia_aplicada') and prior.get('base_novo')==row['base_novo']:
                    row.update(forma_ia_aplicada=True,forma_pendente=True,forma_avisos=prior.get('forma_avisos',[]))
            if 'ofertas_incluidas' in p:row['ofertas_incluidas']=p['ofertas_incluidas']
            rows.append(row)
        plan={'somente_valores':only_prices,'produto':product,'produto_aliases':meta.get('produto_aliases',''),'produto_novo':product if only_prices else meta.get('produto_novo') or '', 'incluir_precos':include_prices,'speakers':sorted(set(speakers)|{r['speaker'] for r in rows}),'itens':rows,'fps':info['fps'],'duracao_s':info['duration'],'revisao':None,'samples':previous.get('samples',{}),'modo_duracao':previous.get('modo_duracao','fixo' if previous else 'expandir'),'forma':form,'editorial':previous.get('editorial',{}),'trilha':previous.get('trilha',{}),'voz_teste':previous.get('voz_teste'),'recuperadas_visuais':recovered}
        from . import identidade_entrega as ID
        plan['nomenclatura']=previous.get('nomenclatura',ID.read(out))
        for key in ('preferencias_voz','pitch_transcricao'): 
            if key in previous:plan[key]=previous[key]
        if previous.get('itens')==rows:plan['revisao']=previous.get('revisao');plan['previa']=previous.get('previa');plan['entrega']=previous.get('entrega')
        if previous and previous.get('somente_valores',False)!=only_prices:
            write(Path(out)/'trocas'/('plano_antes_escopo_'+digest(previous)+'.json'),previous)
        write(plan_path(out),plan)
        from . import visuais as VIS, deteccao_visual as DV
        if VIS.path(out).exists():VIS.current_state(out)
        if previous.get('produto')!=product and DV.path(out).exists():
            visual=DV.load(out)
            if visual.get('nome')==previous.get('produto'):
                visual['nome']=product
                visual['aliases']=', '.join(a for a in [plan.get('produto_aliases',''),plan.get('editorial',{}).get('aliases','')] if a)
                DV.write(out,visual)
        return plan

def save(out,updates):
    with LOCK:
        plan=load(out);before=digest([[r['id'],r['novo'],r['speaker'],r['aprovado']] for r in plan['itens']]);byid={r['id']:r for r in plan['itens']}
        for change in updates:
            if change.get('id') not in byid:raise ValueError('Trecho desconhecido; atualize a lista.')
            row=byid[change['id']]
            if 'forma_texto_esperado' in change and (change['forma_texto_esperado']!=row['novo'] or not (row.get('forma_detectada') or row.get('forma_pendente'))):raise ValueError('Uma adaptação mudou durante a aprovação. Confira a lista atual e tente novamente.')
            new=str(change.get('novo',row['novo'])).strip();speaker=str(change.get('speaker',row['speaker']))
            accepted=bool(change.get('aprovado',row['aprovado']))
            mixed=row.get('novo_sem_sugestoes')
            if 'mencao_descartada' in change and row.get('mencoes_revisar'):
                dismissed=change['mencao_descartada'] is True
                row['mencao_descartada']=dismissed
                if mixed:
                    old_text, replacement=(row['base_novo'],mixed) if dismissed else (mixed,row['base_novo'])
                    if new not in (old_text,replacement):
                        raise ValueError('O texto foi editado. Ajuste apenas a grafia sugerida no campo Frase nova e aprove a frase.')
                    new=replacement
                    accepted=dismissed
            if accepted and row.get('mencao_descartada') and not mixed:
                row['mencao_descartada']=False
            if not new or len(new)>8000:raise ValueError('Cada frase nova precisa ter entre 1 e 8000 caracteres.')
            if speaker not in plan['speakers']:raise ValueError('Speaker não identificado nesta transcrição.')
            if new!=row['novo']:row['forma_confirmada']=False
            if change.get('forma_confirmada') is True:
                if not form_ready(row,new):
                    raise ValueError('Ainda há modo de uso original na fala. Adapte o texto antes de aprovar.')
                row['forma_confirmada']=True
            if (new,speaker)!=(row['novo'],row['speaker']) and row.get('audio'):row.setdefault('historico_audio',[]).append(copy.deepcopy(row.pop('audio')))
            if speaker!=row['speaker'] and speaker!='A_CONFIRMAR':row.update(speaker_pendente=False,speaker_confirmado=True,speaker_aviso='')
            row.update(novo=new,speaker=speaker,aprovado=accepted)
        if digest([[r['id'],r['novo'],r['speaker'],r['aprovado']] for r in plan['itens']])!=before:plan['revisao']=None;plan.pop('previa',None)
        write(plan_path(out),plan);return plan

def approved(plan,with_audio=False):
    rows=[r for r in plan['itens'] if r['aprovado']]
    if not rows:raise ValueError('Aprove pelo menos uma frase.')
    if any(r.get('forma_pendente') and not r.get('forma_confirmada') for r in rows):raise ValueError('Há adaptações de modo de uso pendentes. Informe a instrução real ou reescreva e confirme as frases na etapa Falas.')
    if any(r['speaker']=='A_CONFIRMAR' or r.get('speaker_pendente') for r in rows):raise ValueError('Há speaker a confirmar. Ouça o original e confirme a pessoa na etapa Falas.')
    for a,b in zip(rows,rows[1:]):
        if a['fim_ms']>b['inicio_ms']:raise ValueError('Há frases aprovadas sobrepostas. Una os textos ou desmarque uma delas.')
    if with_audio:
        for row in rows:
            audio=row.get('audio',{})
            if not audio.get('aprovado') or not audio.get('fit'):raise ValueError('Ouça e aprove todos os áudios selecionados antes de montar.')
            if audio.get('texto_hash')!=digest([row['novo'],row['speaker']]):raise ValueError('Há áudio desatualizado. Gere novamente a frase alterada.')
    return rows

def sample_job(job,out):
    plan=load(out);raw=json.loads((Path(out)/'transcricao_bruta.json').read_text());src=source(out);samples={}
    utterances=raw.get('utterances') or []
    for speaker in plan['speakers']:
        if speaker=='A_CONFIRMAR':continue
        existing=plan.get('samples',{}).get(speaker,{})
        if existing.get('arquivo') and (Path(out)/existing['arquivo']).is_file():samples[speaker]=existing;continue
        intervals=[];total=0
        for u in sorted(utterances,key=lambda u:u['end']-u['start'],reverse=True):
            if str(u.get('speaker') or 'A_CONFIRMAR')!=speaker:continue
            if any(str(v.get('speaker') or 'A_CONFIRMAR')!=speaker and v['start']<u['end'] and v['end']>u['start'] for v in utterances):continue
            length=min((u['end']-u['start'])/1000,60-total)
            if length<.5:continue
            intervals.append((u['start']/1000,length));total+=length
            if total>=60:break
        if not intervals:
            for row in plan['itens']:
                if row['speaker']==speaker and row.get('speaker_confirmado') and not row.get('speaker_pendente'):
                    length=min(row['duracao_s'],60-total)
                    if length>=.5:intervals.append((row['inicio_ms']/1000,length));total+=length
                    if total>=60:break
        if not intervals:continue
        folder=Path(out)/'trocas'/'amostras';folder.mkdir(parents=True,exist_ok=True)
        target=folder/(digest(speaker)+'.mp3');cmd=[M.FFMPEG,'-y','-v','error']
        for start,length in intervals:cmd+=['-ss',str(start),'-t',str(length),'-i',str(src)]
        filters=[]
        for i in range(len(intervals)):filters.append(f'[{i}:a:0]asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=mono[a{i}]')
        filters.append(''.join(f'[a{i}]' for i in range(len(intervals)))+f'concat=n={len(intervals)}:v=0:a=1[a]')
        cmd+=['-filter_complex',';'.join(filters),'-map','[a]','-c:a','libmp3lame','-b:a','128k',str(target)]
        job.step='Preparando amostra do speaker '+speaker;M.run_proc(job,cmd)
        samples[speaker]={'arquivo':str(target.relative_to(out)),'duracao_s':probe(target)['duration']}
    with LOCK:
        plan=load(out);plan['samples']=samples;write(plan_path(out),plan)
    job.step='Amostras prontas para ouvir';return {'samples':samples}

def replace_sample_job(job, out, speaker, uploaded, name):
    """Confere e converte outra amostra antes de trocar a referência do speaker."""
    import math
    out, uploaded = Path(out), Path(uploaded)
    target = out / 'trocas/amostras' / (uuid.uuid4().hex + '.mp3')
    committed = False
    try:
        with LOCK:
            plan = load(out)
            if speaker not in plan['speakers'] or speaker == 'A_CONFIRMAR':
                raise ValueError('Confirme o speaker antes de substituir a amostra.')
            before = plan.get('samples', {}).get(speaker)
        duration = probe(uploaded)['duration']
        if not math.isfinite(duration) or not 0 < duration <= 120:
            raise ValueError('Escolha uma gravação com voz de até 2 minutos.')
        target.parent.mkdir(parents=True, exist_ok=True)
        job.step = 'Preparando a nova amostra do speaker ' + speaker
        M.run_proc(job, [M.FFMPEG, '-y', '-v', 'error', '-i', str(uploaded), '-map', '0:a:0',
                         '-vn', '-ac', '1', '-ar', '44100', '-c:a', 'libmp3lame', '-b:a', '128k', str(target)])
        sample = {'arquivo': str(target.relative_to(out)), 'duracao_s': probe(target)['duration'],
                  'nome': name, 'origem': 'importada'}
        if job.cancel: raise M.Cancelled()
        with LOCK:
            plan = load(out)
            if speaker not in plan['speakers'] or plan.get('samples', {}).get(speaker) != before:
                raise ValueError('A amostra deste speaker mudou durante a importação. Confira e tente novamente.')
            plan.setdefault('samples', {})[speaker] = sample
            preferences = plan.get('preferencias_voz')
            if preferences:
                preferences.update(autoriza_envio=False, autoriza_clonagem=False)
                preferences.get('voices', {}).pop(speaker, None)
            write(plan_path(out), plan)
            committed = True
        job.step = 'Amostra substituída — ouça e confirme a autorização'
        return {'speaker': speaker, 'amostra': sample}
    finally:
        if not committed: target.unlink(missing_ok=True)
        uploaded.unlink(missing_ok=True)


def audio_path(out,row,kind,suffix):
    """Nome legível na ordem da lista; versões novas nunca sobrescrevem mídia exportada."""
    plan=load(out)
    number=next((i for i,r in enumerate(plan['itens'],1) if r['id']==row['id']),1)
    safe=lambda text:re.sub(r'[^A-Za-z0-9_-]+','_',str(text)).strip('_')[:48] or 'Produto'
    stem=f"{number:03d}_Speaker_{safe(row['speaker'])}_{safe(plan['produto_novo'])}_{kind}"
    directory=Path(out)/'trocas'/('gerados' if kind=='GERADO' else 'encaixados');directory.mkdir(parents=True,exist_ok=True)
    target=directory/(stem+suffix);version=2
    while target.exists():
        target=directory/(stem+f'_V{version:02d}'+suffix);version+=1
    return target

def name_existing_audio(out):
    """Cria cópias legíveis e mantém os caminhos antigos válidos para XMLs existentes."""
    with LOCK:
        plan=load(out);changed=0
        for row in plan['itens']:
            audio=row.get('audio',{})
            for field,kind in (('raw','GERADO'),('fit','PRONTO')):
                if not audio.get(field):continue
                original=Path(out)/audio[field]
                if not original.is_file() or re.match(r'^\d{3,}_Speaker_',original.name):continue
                target=audio_path(out,row,kind,original.suffix);shutil.copy2(original,target)
                audio[field]=str(target.relative_to(out));changed+=1
        if changed:
            plan['revisao']=None;write(plan_path(out),plan)
        return changed


def fit(job,out,row,raw,autofit=True,allow_short=False):
    info=probe(raw);original=(row['fim_ms']-row['inicio_ms'])/1000;fps=load(out)['fps']
    start=round(row['inicio_ms']/1000*fps);end=round(row['fim_ms']/1000*fps);target=max(1,end-start)/fps
    expand=load(out).get('modo_duracao','fixo')=='expandir'
    if expand:
        frames=max(end-start,math.ceil(info['duration']*fps-1e-3));target=frames/fps
        dst=audio_path(out,row,'PRONTO','.wav');M.run_proc(job,[M.FFMPEG,'-y','-v','error','-i',str(raw),'-vn','-af',f'aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={target:.9f},asetpts=PTS-STARTPTS','-c:a','pcm_s16le',str(dst)])
        return {'raw':str(Path(raw).relative_to(out)),'duracao_s':round(info['duration'],3),'alvo_s':round((end-start)/fps,3),'diferenca_ms':round((target-(end-start)/fps)*1000),'texto_hash':digest([row['novo'],row['speaker']]),'aprovado':False,'fit':str(dst.relative_to(out)),'status':'espaco_ampliado' if frames>end-start else 'silencio_adicionado' if info['duration']<target-.1 else 'encaixa','timeline_frames':frames,'modo_duracao':'expandir'}
    ratio=info['duration']/target
    result={'raw':str(Path(raw).relative_to(out)),'duracao_s':round(info['duration'],3),'alvo_s':round(target,3),'diferenca_ms':round((info['duration']-target)*1000),'texto_hash':digest([row['novo'],row['speaker']]),'aprovado':False,'fit':None}
    # allow_short: áudio encurtado de propósito (silêncio das bordas removido) é completado com silêncio, não descartado.
    if ratio>1.1 or (ratio<.75 and not allow_short) or (ratio>1.005 and not autofit):
        result['status']='regenerar_longo' if ratio>1 else 'regenerar_curto';return result
    dst=audio_path(out,row,'PRONTO','.wav')
    af='aresample=48000,aformat=channel_layouts=stereo'
    if ratio>1.005:af+=f',atempo={ratio:.8f}';result['status']='velocidade_ajustada'
    elif target-info['duration']>.1:result['status']='silencio_adicionado'
    else:result['status']='encaixa'
    af+=f',apad,atrim=duration={target:.8f},asetpts=PTS-STARTPTS'
    M.run_proc(job,[M.FFMPEG,'-y','-v','error','-i',str(raw),'-vn','-af',af,'-c:a','pcm_s16le',str(dst)])
    result['fit']=str(dst.relative_to(out));return result

def record_audio(out,rowid,audio):
    with LOCK:
        plan=load(out);row=next((r for r in plan['itens'] if r['id']==rowid),None)
        if not row or audio['texto_hash']!=digest([row['novo'],row['speaker']]):raise ValueError('O texto/speaker mudou durante a geração; o áudio foi salvo mas precisa ser gerado novamente.')
        if row.get('audio') and row['audio'].get('fit')!=audio.get('fit'):row.setdefault('historico_audio',[]).append(copy.deepcopy(row['audio']))
        row['audio']=audio;plan['revisao']=None;plan.pop('previa',None);write(plan_path(out),plan)

def approve_audio(out,rowid,expected_hash):
    with LOCK:
        plan=load(out);row=next((r for r in plan['itens'] if r['id']==rowid),None)
        if not row:raise ValueError('Trecho não encontrado.')
        audio=row.get('audio',{})
        if not audio.get('fit') or audio.get('texto_hash')!=digest([row['novo'],row['speaker']]) or audio.get('texto_hash')!=expected_hash:raise ValueError('Áudio ausente, fora da duração ou desatualizado.')
        audio['aprovado']=True;plan['revisao']=None;write(plan_path(out),plan);return plan


_AUDIO_PENDING_REASONS = {
    'sem_fala': 'Menção fora da lista de falas.',
    'fora_da_selecao': 'Fala fora da seleção.',
    'texto_antigo': 'O texto ainda contém o nome do produto antigo.',
    'sem_audio': 'Áudio ainda não preparado.',
    'audio_desatualizado': 'Áudio desatualizado.',
    'audio_nao_aprovado': 'Áudio ainda não aprovado.',
    'audio_pendente_revisao': 'Outro ponto desta fala está pendente de revisão.',
}


def _review_audio(out, plan, fps):
    from . import conferencia_mencoes as CM
    if any(j.kind == 'vozes' and j.status in ('na_fila', 'executando')
           and Path(j.params.get('out', '')).resolve() == Path(out).resolve()
           for j in list(M.JOBS.values())):
        raise ValueError('Aguarde a geração dos áudios terminar antes de gerar o XML de revisão.')
    coverage = CM.public(CM.scan(out, plan))
    review = plan.get('revisao') or {}
    if not coverage.get('ignorado') and review.get('resquicios') and review.get('assinatura') == preview_signature(out):
        raise ValueError('Revise os marcadores da conferência do áudio final antes de gerar o XML de revisão.')

    selected = approved(plan) if any(r.get('aprovado') for r in plan['itens']) else []
    pending = coverage['pendencias']
    flagged = {p['id_fala'] for p in pending}
    omitted = set()
    rows = []
    for row in selected:
        audio = row.get('audio', {})
        status = None
        if not audio.get('fit') or not (Path(out) / audio['fit']).is_file():
            status = 'sem_audio'
        elif (audio.get('texto_hash') != digest([row['novo'], row['speaker']])
              or audio.get('modo_duracao', 'fixo') != plan.get('modo_duracao', 'fixo')):
            status = 'audio_desatualizado'
        elif not audio.get('aprovado'):
            status = 'audio_nao_aprovado'
        if row['id'] in flagged or status:
            omitted.add(row['id'])
            if row['id'] not in flagged:
                pending.append({'id': row['id'], 'id_fala': row['id'], 'status': status,
                                'inicio_ms': row['inicio_ms'], 'fim_ms': row['fim_ms'],
                                'texto': row['original']})
        else:
            rows.append(row)

    # Uma frase omitida mantém o áudio de origem mesmo nas outras menções que continha.
    for item in coverage['itens']:
        if item['status'] == 'coberta' and item['id_fala'] in omitted:
            item['status'] = 'audio_pendente_revisao'
            pending.append(item.copy())
    if not pending:
        raise ValueError('As pendências de áudio foram resolvidas. Gere a entrega normalmente.')

    # Protege a frase inteira quando a janela não invade outro áudio aprovado.
    ready = [(round(r['inicio_ms'] * fps / 1000), round(r['fim_ms'] * fps / 1000)) for r in rows]
    by_id = {r['id']: r for r in plan['itens']}
    for item in pending:
        row = by_id.get(item['id_fala'])
        a = row['inicio_ms'] if row else item.get('frase_inicio_ms', item['inicio_ms'])
        b = row['fim_ms'] if row else item.get('frase_fim_ms', item['fim_ms'])
        if any(round(a * fps / 1000) < stop and round(b * fps / 1000) > start for start, stop in ready):
            a, b = item['inicio_ms'], item['fim_ms']
        if any(round(a * fps / 1000) < stop and max(round(a * fps / 1000) + 1, round(b * fps / 1000)) > start
               for start, stop in ready):
            raise ValueError('Uma pendência de áudio se sobrepõe a uma fala aprovada. Ajuste os intervalos antes de gerar o XML de revisão.')
        item.update(revisao_inicio_ms=a, revisao_fim_ms=b,
                    motivo=_AUDIO_PENDING_REASONS[item['status']])
    pending.sort(key=lambda item: (item['inicio_ms'], item['fim_ms']))
    return rows, selected, coverage


def export_xml(out,visual_only=False,job=None,*,revisao_pendencias=False):
    from . import visuais as VIS
    from . import conferencia_mencoes as CM
    if revisao_pendencias and visual_only:
        raise ValueError('O XML de revisão precisa incluir o áudio do projeto.')
    plan=load(out) if plan_path(out).exists() or not visual_only else {'produto':'','produto_novo':'VSL'}
    if not revisao_pendencias:
        rows=[] if visual_only else approved(plan,True)
        coverage={} if visual_only else CM.require(out,plan,job=job)
    if revisao_pendencias:
        visual_state = VIS.load(out)
        if not (visual_state.get('sem_takes') or visual_state.get('incluir')):
            raise ValueError('Prepare os takes ou escolha manter as imagens atuais antes do XML de revisão.')
    visuals=VIS.valid_prepared(out,not visual_only) if VIS.path(out).exists() or visual_only else []
    src=source(out);info=probe(src);fps=info['fps'];frames=round(info['duration']*fps)
    if revisao_pendencias:
        rows, selected, coverage = _review_audio(out, plan, fps)
    from . import montagem as MT
    layout=MT.parts(job or M.Job('montagem','Preparar montagem',None),out,rows,visuals,info);source_frames=frames;frames=layout['frames']
    prefetch([p['path'] for p in layout['video']+layout['visuals']]+[Path(out)/r['audio']['fit'] for r in rows],M.FFPROBE)
    if visuals and not info['video']:raise ValueError('A montagem visual exige o vídeo original.')
    from . import broll as BR
    brolls=BR.approved(out) if info['video'] else []
    root=ET.Element('xmeml',version='4');cache={str(src):info}
    def metadata(path):
        key=str(path)
        if key not in cache:cache[key]=probe(path,False)
        return cache[key]
    seq=ET.SubElement(root,'sequence',id='dr-trocas-'+uuid.uuid4().hex[:8])
    def val(p,k,v):ET.SubElement(p,k).text=str(v)
    def rate(p,value=None):
        f=fps if value is None else value;n=round(f)
        r=ET.SubElement(p,'rate');val(r,'timebase',n);val(r,'ntsc','TRUE' if abs(f-n)>.01 else 'FALSE')
    def file(parent,path,fileid,video=False,*,video_only=False):
        f=ET.SubElement(parent,'file',id=fileid);val(f,'name',path.name);val(f,'pathurl',path.resolve().as_uri());meta=metadata(path);rate(f,meta['fps'] if video else fps)
        val(f,'duration',round(meta['duration']*(meta['fps'] if video else fps)));media=ET.SubElement(f,'media')
        if video:
            sc=ET.SubElement(ET.SubElement(media,'video'),'samplecharacteristics');rate(sc,meta['fps']);val(sc,'width',meta['width']);val(sc,'height',meta['height']);val(sc,'pixelaspectratio','square')
        if not video_only and meta.get('has_audio',True):
            am=ET.SubElement(media,'audio');val(am,'channelcount',meta['channels']);sc=ET.SubElement(am,'samplecharacteristics');val(sc,'depth',16);val(sc,'samplerate',meta['sample_rate'])
    def clip(track,path,start,end,ins,kind,cid,enabled=True,*,video_only=False):
        c=ET.SubElement(track,'clipitem',id=cid);meta=metadata(path);sourcefps=meta['fps'] if kind=='video' else fps;sourcein=round(ins*sourcefps/fps);sourceout=round((ins+end-start)*sourcefps/fps)
        for k,v in [('name',path.name),('enabled','TRUE' if enabled else 'FALSE'),('duration',round(meta['duration']*sourcefps)),('start',start),('end',end),('in',sourcein),('out',sourceout)]:val(c,k,v)
        rate(c,sourcefps);file_id='file-'+digest(str(path))+('-video-only' if video_only else '')
        file(c,path,file_id,kind=='video',video_only=video_only);st=ET.SubElement(c,'sourcetrack');val(st,'mediatype',kind);val(st,'trackindex',1)
        if kind=='video' and (meta['width'],meta['height'])!=(info['width'],info['height']):
            effect=ET.SubElement(ET.SubElement(c,'filter'),'effect')
            for k,v in [('name','Basic Motion'),('effectid','basic'),('effectcategory','motion'),('effecttype','motion'),('mediatype','video')]:val(effect,k,v)
            parameter=ET.SubElement(effect,'parameter');val(parameter,'parameterid','scale');val(parameter,'name','Scale');val(parameter,'valuemin',0);val(parameter,'valuemax',10000);val(parameter,'value',100*max(info['width']/meta['width'],info['height']/meta['height']))
        return c
    val(seq,'name',('DR Visuais · ' if visual_only else 'DR Trocas aprovadas · ')+plan['produto_novo']);val(seq,'duration',frames);rate(seq)
    media=ET.SubElement(seq,'media')
    if info['video']:
        video=ET.SubElement(media,'video');sc=ET.SubElement(ET.SubElement(video,'format'),'samplecharacteristics');rate(sc)
        for k,v in [('width',info['width']),('height',info['height']),('pixelaspectratio','square'),('fielddominance','none')]:val(sc,k,v)
        v1=ET.SubElement(video,'track')
        for i,piece in enumerate(layout['video']):clip(v1,piece['path'],piece['start'],piece['end'],piece['in'],'video','original-video-'+str(i))
        if visuals or brolls:
            track=ET.SubElement(video,'track')
            for i,segment in enumerate(v for v in layout['visuals'] if not v.get('timeline_fechada')):clip(track,segment['path'],segment['start'],segment['end'],segment['in'],'video','visual-'+str(i),video_only=True)
        if brolls:
            # V3: b-roll escolhido pelo editor, ancorado no início da frase do original, sem áudio.
            v3=ET.SubElement(video,'track')
            for i,b in enumerate(brolls):
                a=MT.shift(round(b['inicio_ms']/1000*fps),layout['changes']);e=MT.shift(round(b['fim_ms']/1000*fps),layout['changes'])
                e=min(e,a+max(1,math.floor(metadata(b['path'])['duration']*fps)));clip(v3,b['path'],a,max(a+1,e),0,'video','broll-'+str(i),video_only=True)
    audio=ET.SubElement(media,'audio');original=ET.SubElement(audio,'track');cuts=ET.SubElement(audio,'track');replacement=ET.SubElement(audio,'track')
    review_intervals = {}
    if revisao_pendencias:
        for item in coverage['pendencias']:
            a = min(source_frames - 1, max(0, round(item['revisao_inicio_ms'] * fps / 1000)))
            b = min(source_frames, max(a + 1, round(item['revisao_fim_ms'] * fps / 1000)))
            review_intervals.setdefault((a, b), []).append(item)

    windows=[];previous=0
    for r in rows:
        a=round(r['inicio_ms']/1000*fps);b=round(r['fim_ms']/1000*fps)
        left=MT.mute_start(a,previous,fps)
        left=max([left, *(stop for _,stop in review_intervals if left < stop <= a)])
        windows.append((left,b,r));previous=b
    bounds=sorted({0,source_frames,*[v for a,b,r in windows for v in (a,b)],*[v for pair in review_intervals for v in pair]})
    for i,(a,b) in enumerate(zip(bounds,bounds[1:])):
        disabled=any(x<=a and b<=y for x,y,r in windows)
        start=MT.shift(a,layout['changes']);original_clip=clip(cuts if disabled else original,src,start,start+b-a,a,'audio','original-audio-'+str(i),not disabled)
        if not disabled and any(x<=a and b<=y for x,y in review_intervals):
            original_clip.find('name').text='PENDÊNCIA DE ÁUDIO · '+src.name
    for i,e in enumerate(layout['changes']):
        a,b,row=e['start'],e['end'],e['row']
        clip(replacement,Path(out)/row['audio']['fit'],a,b,0,'audio','novo-'+str(i))
        marker=ET.SubElement(seq,'marker');val(marker,'name','TROCA '+str(i+1)+' · Speaker '+row['speaker']);val(marker,'comment',row['original']+' → '+row['novo']);val(marker,'in',a);val(marker,'out',b)
    if VIS.path(out).exists():
        visual_state=VIS.load(out)
        for i,row in enumerate(visual_state.get('coverage_markers',[])+visual_state.get('manual_markers',[])):
            marker=ET.SubElement(seq,'marker');val(marker,'name','AJUSTAR TAKE MANUALMENTE · autorizado' if row.get('manual') else 'ADAPTAR MODO DE USO · sem potes');val(marker,'comment',row['text']+' · '+row['motivo']);val(marker,'in',MT.shift(round(row['start']/1000*fps),layout['changes']));val(marker,'out',MT.shift(round(row['end']/1000*fps),layout['changes']))
    from . import deteccao_visual as DV
    old_product=DV.approved_markers(out)
    visual_pending=[]
    if VIS.path(out).exists():
        visual_state=VIS.load(out)
        visual_pending=[m for m in visual_state.get('pendencias_visuais',[]) if m.get('token')==VIS.gap_token(visual_state,m['id'],m['start'],m['end'])]
    for row in visual_pending:
        # Fresta que o editor escolheu resolver no Premiere: takes e falas aprovadas ficam como estão.
        a,b=MT.shift(round(row['start']/1000*fps),layout['changes']),MT.shift(round(row['end']/1000*fps),layout['changes'])
        marker=ET.SubElement(seq,'marker');val(marker,'name','PENDÊNCIA VISUAL · produto antigo');val(marker,'comment',f'Produto antigo visível sem take em V2 ({row["start"]/1000:.2f}–{row["end"]/1000:.2f} s do original). Cubra este trecho no Premiere.');val(marker,'in',a);val(marker,'out',max(a+1,b))
    for row in old_product:
        # Só marcação nesta etapa: a imagem e o áudio originais continuam intactos.
        marker=ET.SubElement(seq,'marker');val(marker,'name','PRODUTO ANTIGO NA IMAGEM'+(' · só marcar (antes da 1ª menção)' if row.get('antes_da_mencao') else ''));val(marker,'comment',row['motivo']);val(marker,'in',MT.shift(round(row['inicio_ms']/1000*fps),layout['changes']));val(marker,'out',MT.shift(round(row['fim_ms']/1000*fps),layout['changes']))
    music=plan.get('trilha',{})
    if music.get('modo')=='separada':
        music_path=Path(out)/music['arquivo'];length=max(1,math.floor(metadata(music_path)['duration']*fps));track=ET.SubElement(audio,'track');position=0;index=0
        while position<frames:
            stop=min(frames,position+length);c=clip(track,music_path,position,stop,0,'audio','trilha-'+str(index))
            filt=ET.SubElement(c,'filter');effect=ET.SubElement(filt,'effect')
            for k,v in [('name','Audio Levels'),('effectid','audiolevels'),('effectcategory','audio'),('effecttype','audio'),('mediatype','audio')]:val(effect,k,v)
            param=ET.SubElement(effect,'parameter')
            for k,v in [('parameterid','level'),('name','Level'),('valuemin',0),('valuemax',4),('value',10**(music.get('ganho_db',-18)/20))]:val(param,k,v)
            position=stop;index+=1
            if not music.get('repetir'):break
    from . import fechamento as FC
    closures=FC.windows(layout['changes'],fps)
    if revisao_pendencias:
        changes = layout['changes']
        closures = [(left, e['start']) for (a, _, _),e in zip(windows, changes)
                    if (left := MT.shift(a, changes)) < e['start']]
        if any(v.get('timeline_final') or v.get('timeline_fechada') for v in visuals):
            prepared_changes = MT.edits(out, [r for r in selected if r.get('audio', {}).get('fit')], info)
            planned_expansions = [(e['b'], e['extra']) for e in prepared_changes if e['extra']]
            review_expansions = [(e['b'], e['extra']) for e in changes if e['extra']]
            if review_expansions != planned_expansions or closures != FC.windows(prepared_changes, fps):
                raise ValueError('A pendência de áudio altera a duração da montagem dos takes. Revise a fala ou escolha manter as imagens atuais antes de gerar o XML de revisão.')
        from .identidade_entrega import clock
        for (a, b), items in review_intervals.items():
            start, end = MT.shift(a, changes), MT.shift(b, changes)
            mapped_start, mapped_end = FC.position(start, closures), FC.position(end, closures)
            for item in items:
                item.update(inicio_timeline_frame=mapped_start, fim_timeline_frame=mapped_end,
                            timecode_timeline=clock(mapped_start / fps))
            marker = ET.SubElement(seq, 'marker')
            val(marker, 'name', 'PENDÊNCIA DE ÁUDIO · tratar no Premiere')
            reasons = ' '.join(dict.fromkeys(item['motivo'] for item in items))
            phrases = ' '.join(dict.fromkeys(item['texto'] for item in items))
            val(marker, 'comment', f'{reasons} Áudio original preservado. {phrases}')
            val(marker, 'in', start)
            val(marker, 'out', end)
    FC.xml(seq,closures,fps);closed_frames=sum(b-a for a,b in closures)
    if info['video'] and any(v.get('timeline_fechada') for v in visuals):
        track=seq.findall('media/video/track')[1]
        for i,v in enumerate(visuals):
            if v.get('timeline_fechada'):clip(track,Path(out)/v['file'],v['start_frame'],v['end_frame'],0,'video','visual-completo-'+str(i),video_only=True)
    from .nomes_arquivos import write_xml
    if not visual_only:
        checked=coverage if not revisao_pendencias else {'itens':[r for r in coverage['itens'] if r['status']=='coberta']}
        coverage['verificacao_xml']=CM.verify_xml(seq,checked,fps)
    label=' para '.join(filter(None,[plan.get('produto',''),plan.get('produto_novo','')])) or Path(out).name
    from . import identidade_entrega as ID
    identity=ID.identity(plan,out)
    review_info = {}
    if revisao_pendencias:
        identity['nome_sequencia'] = 'REVISÃO DE ÁUDIO - ' + identity['nome_sequencia']
        review_info = {'revisao_pendencias': True, 'completa': False, 'pendencias': coverage['pendencias'],
                       'total_pendencias': len(coverage['pendencias'])}
    dst=write_xml(root,Path(out)/'trocas',label,'Takes visuais' if visual_only else 'Troca de potes',sequence_name=identity['nome_sequencia'])
    manifest=dst.with_suffix('.json');write(manifest,{'nomenclatura':identity,'produto':plan['produto'],'produto_novo':plan['produto_novo'],'itens':rows,'visuais_v2':visuals,'broll_v3':[{k:b.get(k) for k in ('frase','arquivo','inicio_ms','fim_ms','texto','status','candidato')} for b in brolls],'ajustes_manuais_autorizados':VIS.load(out).get('manual_markers',[]) if VIS.path(out).exists() else [],'produto_antigo_na_imagem':[{k:r.get(k) for k in ('inicio_ms','fim_ms','motivo','antes_da_mencao','motivos','origem')} for r in old_product],'pendencias_visuais':[{'inicio_ms':m['start'],'fim_ms':m['end'],'premiere_inicio_s':m.get('premiere_inicio_s'),'premiere_fim_s':m.get('premiere_fim_s'),'aparicoes':m.get('aparicoes',[]),'marcador':'PENDÊNCIA VISUAL · produto antigo'} for m in visual_pending],'modo_duracao':plan.get('modo_duracao','fixo'),'margem_fala_ms':MT.margin_ms(),'trilha':music,'expansao_frames':layout['extra_frames'],'margens_removidas_frames':closed_frames,'deslocamentos':[{'inicio_original':e['a'],'fim_original':e['b'],'inicio_final':FC.position(e['start'],closures),'fim_final':FC.position(e['end'],closures),'acrescimo_frames':e['extra']} for e in layout['changes']],'referencia':'VSL preservada; quando a fala é maior, o restante é deslocado e a última imagem é mantida durante o espaço extra. A1 mantém o restante original; A2 contém os trechos originais substituídos, desativados; A3 contém as novas falas correspondentes.','arquivo':str(dst.relative_to(out))})
    if not visual_only:
        data=json.loads(manifest.read_text());data.update(conferencia_mencoes=coverage,**review_info);write(manifest,data)
    if not dst.is_file() or not dst.stat().st_size:raise ValueError('Não foi possível confirmar o XML no disco.')
    ET.parse(dst)
    return delivery_info(out,{'nome_sequencia':identity['nome_sequencia'],'nomenclatura_assinatura':ID.signature(plan,out),'xml':str(dst.relative_to(out)),'json':str(manifest.relative_to(out)),'trechos':len(rows),'visuais':len(visuals),'broll':len(brolls),'acrescimo_s':(layout['extra_frames']-closed_frames)/fps,'duracao_s':(frames-closed_frames)/fps,**review_info})

def rename_delivery(out):
    """Reemite só XML/relatório quando a mídia da entrega atual continua igual."""
    from . import identidade_entrega as ID
    from .nomes_arquivos import write_xml
    with LOCK:
        plan=load(out);old=plan.get('entrega') or {};signature=preview_signature(out)
        if old.get('assinatura')!=signature:raise ValueError('A montagem mudou. Gere uma nova entrega antes de atualizar apenas o nome.')
        info=delivery_info(out,old)
        if not info.get('xml_existe'):raise ValueError('XML da entrega atual não encontrado. Gere a entrega novamente.')
        tree=ET.parse(info['xml_absoluto']);identity=ID.identity(plan,out)
        dst=write_xml(tree.getroot(),Path(out)/'trocas','','',sequence_name=identity['nome_sequencia'])
        report=Path(out)/old.get('json','');data=json.loads(report.read_text()) if report.is_file() else {}
        data.update(nomenclatura=identity,arquivo=str(dst.relative_to(out)));write(dst.with_suffix('.json'),data)
        result={**old,'xml':str(dst.relative_to(out)),'json':str(dst.with_suffix('.json').relative_to(out)),'nome_sequencia':identity['nome_sequencia'],'nomenclatura_assinatura':ID.signature(plan,out)}
        if old.get('completa') and old.get('legenda'):
            from . import finalizacao as F
            details=data.get('entrega_final') or {}
            sha=details.get('legenda_sha256')
            if not sha:raise ValueError('Gere novamente a entrega completa para atualizar os arquivos.')
            details['legenda_ao_lado_do_xml']=dst.with_suffix('.srt').relative_to(out).as_posix()
            data['entrega_final']=details;write(dst.with_suffix('.json'),data)
            result.update(F.package(out,result,{'arquivo':old['legenda'],'sha256':sha}))
        plan['entrega']=result;write(plan_path(out),plan);return delivery_info(out,result)


def mix(job,out):
    plan=load(out);rows=approved(plan,True);src=source(out);info=probe(src)
    dst=Path(out)/'trocas'/('montagem_audio_'+uuid.uuid4().hex[:8]+'.m4a')
    from . import montagem as MT
    if plan.get('modo_duracao')=='expandir' or MT.margin_ms() or plan.get('trilha',{}).get('modo')=='separada':
        return MT.audio_mix(job,out,rows,info,dst)
    cmd=[M.FFMPEG,'-y','-v','error','-i',str(src)]
    for row in rows:cmd+=['-i',str(Path(out)/row['audio']['fit'])]
    mute='+'.join(f"between(t,{r['inicio_ms']/1000:.6f},{r['fim_ms']/1000:.6f})" for r in rows)
    fc=[f"[0:a:0]aresample=48000,aformat=channel_layouts=stereo,volume=0:enable='{mute}'[base]"]
    for i,row in enumerate(rows,1):fc.append(f"[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo,adelay={row['inicio_ms']}:all=1[a{i}]")
    fc.append('[base]'+''.join(f'[a{i}]' for i in range(1,len(rows)+1))+f'amix=inputs={len(rows)+1}:duration=first:normalize=0:dropout_transition=0[out]')
    cmd+=['-filter_complex',';'.join(fc),'-map','[out]','-t',str(info['duration']),*M.aac_args(dst),str(dst)]
    job.step='Preparando áudio integral com as trocas aprovadas';M.run_proc(job,cmd);return dst

def review_job(job,out,aliases=''):
    from . import validacao as V
    plan=load(out);approved(plan,True);signature=preview_signature(out)
    from . import conferencia_mencoes as CM
    import platform
    known=CM.scan(out,plan)['aliases']
    dst=mix(job,out);tr=V.transcribe(job,dst,{'motor':'mlx' if platform.system()=='Darwin' and platform.machine()=='arm64' else 'fw','idioma':'auto'})
    report=V.analyze(tr['words'],','.join(known)+','+aliases);report['audio']=str(dst.relative_to(out));report['cobertura']='Áudio integral da montagem gerada, incluindo a trilha separada configurada. Não analisa imagens nem legendas e não é o vídeo posteriormente exportado pelo Premiere.'
    path=Path(out)/'trocas'/('revisao_'+uuid.uuid4().hex[:8]+'.json');write(path,report|{'transcricao':tr})
    with LOCK:
        current=load(out)
        if preview_signature(out)!=signature:raise ValueError('As trocas mudaram durante a revisão. Gere uma nova conferência.')
        current['revisao']={'assinatura':signature,'arquivo':str(path.relative_to(out)),'audio':str(dst.relative_to(out)),'resquicios':report['resquicios'],'status':'revisar' if report['resquicios'] else 'nenhuma_mencao_encontrada','observacao':report['observacao']+' '+report['cobertura'],'cobertura':report['cobertura'],'pitch':report.get('pitch'),'candidatos_pitch':report.get('candidatos_pitch',[])};write(plan_path(out),current)
    job.step='Conferência final concluída';return current['revisao']

def preview_signature(out):
    from . import visuais as VIS
    plan=load(out);src=source(out);s=VIS.load(out)
    from . import montagem as MT
    core=[{k:r.get(k) for k in ('id','inicio_ms','fim_ms','novo','speaker','aprovado')}|{'audio':{k:r.get('audio',{}).get(k) for k in ('fit','texto_hash','aprovado','modo_duracao')}} for r in plan['itens']]
    from .armazenamento import visual_margin_ms
    raw=Path(out)/'transcricao_bruta.json';decisions=Path(out)/'trocas/mencoes_descartadas.json'
    audit=['cobertura-mencoes-1',plan.get('produto'),plan.get('produto_aliases'),plan.get('editorial',{}).get('aliases'),*[source_identity(p) if p.exists() else None for p in (raw,decisions)]]
    return digest(['fechar-margens-1',audit,MT.margin_ms(),visual_margin_ms() if s.get('incluir') else None,plan.get('modo_duracao','fixo'),core,plan.get('trilha',{}),path_text(src),src.stat().st_size,src.stat().st_mtime_ns,s.get('incluir'),s.get('prepared',{}).get('signature') if s.get('incluir') and s.get('prepared') else None])

def export_reviewed(out,expected,*,persist=True):
    with LOCK:
        plan=load(out);current=preview_signature(out)
        if not expected or expected!=current or (plan.get('previa') or {}).get('assinatura')!=current:raise ValueError('A montagem mudou após a prévia. Confira uma nova prévia antes de preparar a entrega.')
        result = export_xml(out)
        if persist:
            plan['entrega'] = result | {'assinatura': current}
            write(plan_path(out), plan)
        return result

def delivery_info(out,result):
    from .sistema import localizar_entrega
    if not result:return {}
    info=localizar_entrega(out,result['xml'])
    return dict(result,xml_existe=info['existe'],xml_absoluto=info['arquivo'],xml_nome=info['nome'],pasta_absoluta=info['pasta'])

def flow_state(out):
    from . import identidade_entrega as ID
    plan=load(out);current=preview_signature(out);preview=plan.get('previa') or {};delivery=delivery_info(out,plan.get('entrega') or {})
    identity = ID.signature(plan,out)
    review = delivery_info(out,plan.get('entrega_revisao') or {})
    return {'previa':preview,'previa_atual':preview.get('assinatura')==current,'entrega':delivery,'entrega_atual':delivery.get('assinatura')==current and delivery.get('xml_existe',False) and delivery.get('nomenclatura_assinatura')==identity,
            'entrega_revisao':review,'entrega_revisao_atual':review.get('assinatura')==current and review.get('xml_existe',False) and review.get('nomenclatura_assinatura')==identity}

def preview_job(job,out):
    """Prévia local dos trechos prontos, com contexto; não aprova nem cobra voz."""
    from . import visuais as VIS
    out=Path(out);plan=load(out);rows=approved(plan)
    ready=[r for r in rows if r.get('audio',{}).get('fit') and r['audio'].get('texto_hash')==digest([r['novo'],r['speaker']])]
    if not ready:raise ValueError('Gere ou importe pelo menos um áudio que caiba antes da prévia.')
    src=source(out);info=probe(src);expected=preview_signature(out);visual_state=VIS.load(out)
    visuals=VIS.valid_prepared(out) if visual_state.get('incluir') else []
    from . import montagem as MT
    if plan.get('modo_duracao')=='expandir' or MT.margin_ms() or plan.get('trilha',{}).get('modo')=='separada':
        return MT.preview(job,out,plan,ready,visuals,info)
    dest=out/'trocas'/('previa_'+uuid.uuid4().hex[:8]);dest.mkdir(parents=True)
    clips=[]
    for n,row in enumerate(ready,1):
        if job.cancel:raise M.Cancelled()
        start=max(0,row['inicio_ms']/1000-2);end=min(info['duration'],row['fim_ms']/1000+2);duration=end-start
        a=row['inicio_ms']/1000-start;b=row['fim_ms']/1000-start
        cmd=[M.FFMPEG,'-y','-v','error','-ss',str(start),'-t',str(duration),'-i',str(src),'-i',str(out/row['audio']['fit'])]
        fc=[f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume=0:enable='between(t,{a:.6f},{b:.6f})'[base]",f"[1:a]aresample=48000,aformat=channel_layouts=stereo,adelay={round(a*1000)}:all=1[new]",'[base][new]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[aout]']
        video='0:v:0'
        if info['video']:
            active=[v for v in visuals if v['end_frame']/info['fps']>start and v['start_frame']/info['fps']<end]
            for i,v in enumerate(active,2):
                va=v['start_frame']/info['fps'];vb=v['end_frame']/info['fps'];offset=max(0,start-va)
                cmd+=['-ss',str(offset),'-i',str(out/v['file'])]
                fc.append(f'[{i}:v]setpts=PTS-STARTPTS+{max(0,va-start):.6f}/TB[ov{i}]')
                base='[0:v]' if i==2 else f'[v{i-1}]'
                fc.append(f"{base}[ov{i}]overlay=eof_action=pass:enable='between(t,{max(0,va-start):.6f},{vb-start:.6f})'[v{i}]")
            base=f'[v{len(active)+1}]' if active else '[0:v]'
            fc.append(base+'scale=trunc(iw*min(1\\,720/ih)/2)*2:trunc(ih*min(1\\,720/ih)/2)*2,setsar=1[vout]');video='[vout]'
        path=dest/f'{n:03d}.mp4' if info['video'] else dest/f'{n:03d}.m4a'
        cmd+=['-filter_complex',';'.join(fc),'-map','[aout]']
        if info['video']:cmd+=['-map',video,'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-r',str(info['fps'])]
        cmd+=['-c:a','aac','-t',str(duration),str(path)]
        job.step=f'Preparando prévia {n} de {len(ready)}';job.pct=(n-1)/len(ready);M.run_proc(job,cmd);clips.append(path)
    listing=dest/'lista.txt';listing.write_text(''.join("file '"+p.name+"'\n" for p in clips))
    target=dest/('PREVIA_TROCAS.mp4' if info['video'] else 'PREVIA_TROCAS.m4a')
    M.run_proc(job,[M.FFMPEG,'-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(target)])
    result={'assinatura':expected,'arquivo':str(target.relative_to(out)),'trechos':len(ready),'pendentes':len(rows)-len(ready),'video':info['video'],'visuais':bool(visuals),'observacao':'Prévia dos áudios prontos com 2 segundos de contexto. Não aprova falas; os trechos sem áudio pronto não aparecem.'}
    with LOCK:
        latest=load(out)
        if digest(latest['itens'])!=digest(plan['itens']) or preview_signature(out)!=expected:raise ValueError('A montagem mudou durante a prévia. Gere novamente.')
        latest['previa']=result;write(plan_path(out),latest)
    job.pct=1;job.step='Prévia pronta — confira as trocas';return result

def duration_job(job,out,mode):
    if mode not in {'fixo','expandir'}:raise ValueError('Escolha manter a duração ou abrir espaço na timeline.')
    with LOCK:
        plan=load(out);saved_rows=copy.deepcopy(plan['itens']);old_mode=plan.get('modo_duracao','fixo')
        def needs(row):
            audio=row.get('audio',{})
            return bool(audio.get('raw')) and (old_mode!=mode or audio.get('modo_duracao','fixo')!=mode or not audio.get('fit') or not (Path(out)/audio['fit']).is_file() or audio.get('texto_hash')!=digest([row['novo'],row['speaker']]))
        rows=[r for r in saved_rows if needs(r)];reused=sum(bool(r.get('audio',{}).get('fit')) and not needs(r) for r in saved_rows)
        if not rows and old_mode==mode:
            job.step='Os áudios já estavam preparados — aprovações mantidas';job.pct=1
            return {'resultados':[],'modo_duracao':mode,'local':True,'reutilizados':reused}
        plan['modo_duracao']=mode;plan['revisao']=None
        pending={r['id'] for r in rows}
        for row in plan['itens']:
            if row['id'] in pending:row['audio'].update(fit_anterior=row['audio'].get('fit'),fit=None,aprovado=False,status='preparando_duracao')
        plan.pop('previa',None);plan.pop('entrega',None);write(plan_path(out),plan)
    results=[]
    for i,row in enumerate(rows):
        if job.cancel:raise M.Cancelled()
        job.step=f'Preparando duração localmente · {i+1} de {len(rows)}';job.pct=i/max(1,len(rows))
        old=row['audio'];fresh=fit(job,out,row,Path(out)/old.get('fonte_preparo',old['raw']),True)
        fresh.update({k:old[k] for k in ('assinatura','provider','model','voice_id','raw','fonte_preparo','recorte_inicio_ms','recorte_fim_ms','duracao_bruta_s','texto_enviado','contexto_usado') if k in old})
        if old.get('aprovado') and old.get('fit') and fresh.get('fit'):
            prior=Path(out)/old['fit'];new=Path(out)/fresh['fit']
            def checksum(p):
                h=hashlib.sha256()
                with p.open('rb') as f:
                    while chunk:=f.read(1024**2):h.update(chunk)
                return h.digest()
            if prior.exists() and prior.stat().st_size==new.stat().st_size and checksum(prior)==checksum(new):fresh['aprovado']=True
        record_audio(out,row['id'],fresh);results.append({'id':row['id'],'status':fresh['status']})
    job.step='Áudios preparados sem novos créditos — ouça e aprove';job.pct=1;return {'resultados':results,'modo_duracao':mode,'local':True,'reutilizados':reused}

def fast_delivery_job(job,out,autorizado=False,preparar_apenas=False,*,persist=True,revisao_pendencias=False):
    """Autorização explícita em lote, sem visualização e sem chamar serviços de voz."""
    if autorizado is not True:raise ValueError('Autorize explicitamente a entrega sem conferir a prévia.')
    if revisao_pendencias is True:
        if preparar_apenas:
            raise ValueError('Gere o XML de revisão diretamente para marcar as pendências.')
        if job.cancel:raise M.Cancelled()
        job.step = 'Gerando XML de revisão com pendências de áudio marcadas'
        expected = preview_signature(out)
        result = export_xml(out,job=job,revisao_pendencias=True)
        xml = Path(out) / result['xml']
        manifest = Path(out) / result['json']
        result.update(sem_previa=True,assinatura=expected)
        try:
            with LOCK:
                if job.cancel:raise M.Cancelled()
                if preview_signature(out) != expected:
                    raise ValueError('A montagem mudou durante a revisão. Gere o XML novamente.')
                if persist:
                    plan = load(out)
                    plan['entrega_revisao'] = result
                    write(plan_path(out),plan)
        except BaseException:
            xml.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)
            raise
        job.pct = 1
        job.step = 'XML de revisão pronto · trate as pendências sinalizadas'
        return result
    from . import visuais as VIS
    from .workflow import require_takes
    require_takes(out)
    from . import conferencia_mencoes as CM
    CM.require(out,job=job)
    plan=load(out);rows=approved(plan,True);mode=plan.get('modo_duracao','fixo')
    if any(not r.get('audio',{}).get('raw') or not (Path(out)/r['audio']['raw']).is_file() for r in rows):raise ValueError('Há falas selecionadas sem áudio gerado. Gere ou importe os áudios antes da entrega rápida.')
    if any(not r['audio'].get('fit') or r['audio'].get('modo_duracao','fixo')!=mode for r in rows):
        duration_job(job,out,mode);plan=load(out);rows=approved(plan)
    if any(not r['audio'].get('fit') for r in rows):raise ValueError('Há áudios sem preparo. Use Abrir espaço para falas maiores ou importe outros áudios.')
    state=VIS.load(out)
    if not state.get('sem_takes'):
        job.step='Preparando takes para a entrega rápida';needs=True
        if state.get('incluir') and state.get('cobrir_falas'):
            try:needs=not bool(VIS.valid_prepared(out))
            except ValueError:pass
        if needs:VIS.automatic(job,out,state.get('root',''),state.get('max_clip_s',6))
    if job.cancel:raise M.Cancelled()
    job.step='Autorizando áudios selecionados em lote'
    with LOCK:
        plan=load(out);selected=approved(plan)
        for r in selected:
            audio=r.get('audio',{})
            if not audio.get('fit') or not (Path(out)/audio['fit']).is_file() or audio.get('texto_hash')!=digest([r['novo'],r['speaker']]):raise ValueError('Há uma fala alterada ou mídia ausente. Atualize os áudios antes da entrega.')
        changed_approval=any(not r['audio'].get('aprovado') for r in selected)
        for r in selected:r['audio']['aprovado']=True
        if changed_approval:plan['revisao']=None
        write(plan_path(out),plan)
    if preparar_apenas:
        job.pct=1;job.step='Montagem preparada · confira a legenda'
        return {'preparada':True}
    job.step='Gerando XML com todos os trechos autorizados';expected=preview_signature(out);result=export_xml(out,job=job)
    if job.cancel:raise M.Cancelled()
    result['sem_previa']=True
    manifest=Path(out)/result['json'];data=json.loads(manifest.read_text());data['conferencia']='Dispensada explicitamente pelo usuário na entrega rápida';write(manifest,data)
    with LOCK:
        plan=load(out)
        if preview_signature(out)!=expected:raise ValueError('A montagem mudou durante a entrega. Prepare novamente.')
        if persist:
            plan['entrega'] = result | {'assinatura': expected, 'autorizacao': 'Lote autorizado sem assistir à prévia'}
            write(plan_path(out), plan)
    job.pct=1;job.step='Entrega rápida pronta — XML com falas e takes autorizados';return result

"""Auditoria local da fala: resquícios de produto, pitch e marcadores de revisão."""
import copy
import json
import math
import re
import tempfile
import unicodedata
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET
from . import ml_core as M
from .progresso import phase


def norm(value):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+',text))


def terms(value):
    values = re.split(r'[,;\n]+',value) if isinstance(value,str) else value or []
    return list(dict.fromkeys(norm(v) for v in values if norm(v)))


SIX = r'\b(?:6|six|seis)\s+(?:bottles?|jars?|potes?|frascos?|botellas?|botes?|flacons?|month(?:s)?\s+(?:supply|package))\b'
KIT = r'\b(1|2|3|4|5|6|one|two|three|four|five|six|um|uma|dois|duas|tres|quatro|cinco|seis|uno|dos)\s+(?:bottles?|jars?|potes?|frascos?|botellas?|botes?|months?\s+(?:supply|package))\b'
PRICE = re.compile(r'(?<!\w)(?:\$\s*|r\$\s*)?\d{1,4}(?:[.,]\d{2})?(?!\w)|\b(?:twenty[ -]+nine|forty[ -]+nine|vinte e nove|quarenta e nove|veintinueve|cuarenta y nueve)\b', re.I)
CURRENCY = r'\b(?:dollars?|dolares?|reais|euros?|bucks?|por pote|per bottle|each bottle|por frasco|cada pote|cada frasco)\b|\$'


def analyze(words, aliases):
    """Timestamps são segundos desde o primeiro quadro do arquivo analisado."""
    clean=[]
    for w in words:
        s,e=float(w['s']),float(w['e'])
        if not math.isfinite(s+e) or s<0 or e<s: raise ValueError('Transcrição com timestamps inválidos.')
        clean.append({'w':str(w['w']),'s':s,'e':e,'speaker':w.get('speaker')})
    clean.sort(key=lambda w:w['s'])
    sentences=M.build_sentences(clean,M.load_rules()) if clean else []
    def phrase(wi):
        found=next((s for s in sentences if s['w0']<=wi<=s['w1']),None)
        return {'inicio':found['s'],'fim':found['e'],'texto':found['texto']} if found else {'inicio':clean[wi]['s'],'fim':clean[wi]['e'],'texto':clean[wi]['w']}
    from .mencoes import compact, timed_spans
    hits=[]
    aliases=terms(aliases)
    exact_aliases={compact(name):name for name in aliases}
    for i,size,score in timed_spans(clean,aliases):
        last=i+size-1
        candidate=' '.join(norm(w['w']) for w in clean[i:i+size])
        exact=score==1
        hits.append(phrase(i)|{'tipo':'produto_antigo' if exact else 'produto_possivel',
                               'termo':exact_aliases.get(compact(candidate),candidate) if exact else candidate,
                               'status':'encontrado' if exact else 'revisar',
                               'mencao_inicio':clean[i]['s'],'mencao_fim':clean[last]['e']})
    # Texto com mapa de caracteres -> palavra para marcar o início do VALOR.
    spans=[]; text=''
    for wi,w in enumerate(clean):
        if text: text+=' '
        start=len(text); text+=w['w'].lower()
        spans.append((start,len(text),wi))
    def word_at(char): return next((wi for a,b,wi in spans if a<=char<b),None)
    kits=[]
    normalized=''; ns=[]
    for wi,w in enumerate(clean):
        if normalized: normalized+=' '
        a=len(normalized);normalized+=norm(w['w']);ns.append((a,len(normalized),wi))
    for m in re.finditer(KIT,normalized):
        wi=next((wi for a,b,wi in ns if a<=m.start()<b),None)
        if wi is not None: kits.append((wi,m[1] in ('6','six','seis'),m[0]))
    candidates=[]
    for m in PRICE.finditer(text):
        wi=word_at(m.start())
        if wi is None: continue
        raw=norm(m[0]);known=raw in ('29','49','twenty nine','forty nine','vinte e nove','quarenta e nove','veintinueve','cuarenta y nueve')
        near=[k for k in kits if abs(k[0]-wi)<=35 and abs(clean[k[0]]['s']-clean[wi]['s'])<=15]
        nearest=min(near,key=lambda k:abs(k[0]-wi),default=None)
        context=' '.join(w['w'] for w in clean[max(0,wi-5):wi+7])
        currency=bool(re.search(CURRENCY,context,re.I))
        # Não confunde quantidade do kit, idade, prazo ou valor isolado com pitch.
        following=' '.join(norm(w['w']) for w in clean[wi:wi+3])
        quantity=bool(re.match(KIT,following)) or bool(re.search(r'\b(?:years?|anos?|dias?|days?|meses|months?)\b',following))
        if quantity or not (known or currency): continue
        contextual=bool(nearest and nearest[1] and currency)
        if not contextual and not known: continue
        candidates.append(phrase(wi)|{'tipo':'pitch' if contextual else 'pitch_possivel','status':'contexto_6_potes' if contextual else 'revisar','valor':m[0],'tempo':clean[wi]['s'],'contexto': ' '.join(w['w'] for w in clean[max(0,wi-18):wi+18]),'kit':nearest[2] if nearest else None})
    candidates.sort(key=lambda x:x['tempo'])
    contextual=[c for c in candidates if c['status']=='contexto_6_potes']
    pitch=contextual[0] if contextual else None
    # Um preço anterior sem contexto impede afirmar que o escolhido é o PRIMEIRO.
    earlier=[c for c in candidates if pitch and c['tempo']<pitch['tempo'] and c['status']=='revisar' and c.get('kit') is None]
    if earlier: pitch=None
    hits.sort(key=lambda h:h['mencao_inicio'])
    return {'resquicios':hits,'termos_pesquisados':aliases,'validacao_produto':'nao_configurada' if not aliases else ('revisar' if hits else 'nenhuma_mencao_encontrada'),
            'pitch':pitch,'candidatos_pitch':candidates,'status_pitch':'detectado_por_contexto' if pitch else ('revisar' if candidates else 'nao_encontrado'),
            'observacao':'Análise da transcrição por regras; erros de reconhecimento de fala podem ocultar ou sugerir menções. Confira o áudio nos marcadores.'}


def transcribe(job,path,options):
    phase(job,"extracao","Extração do áudio para validação")
    with tempfile.TemporaryDirectory(prefix='dr-auditoria-') as temp:
        wav=Path(temp)/'audio.wav'; out=Path(temp)/'transcricao.json'
        job.step='Extraindo áudio para validação';job.pct=.02
        M.run_proc(job,[M.FFMPEG,'-y','-v','error','-i',str(path),'-vn','-ac','1','-ar','16000',str(wav)])
        phase(job,'validacao','Transcrição para validação',False)
        def progress(line):
            if line.startswith('PROGRESS '): job.pct=.05+.85*float(line.split()[1])
            elif line.startswith('STEP '): job.step='Validação: '+line[5:]
        try:
            duration=M.probe(path)['duracao']
        except RuntimeError:
            result=M.subprocess.check_output([M.FFPROBE,'-v','error','-show_entries','format=duration','-of','json',str(path)])
            duration=float(json.loads(result)['format']['duration'])
        cuts=','.join(str(n) for n in range(240,int(duration)-30,240))
        M.run_proc(job,[M.PY,str(M.BASE/'asr_worker.py'),str(wav),str(out),'--engine',options.get('motor','mlx'),'--lang',options.get('idioma','auto'),'--cuts',cuts],progress)
        data=json.loads(out.read_text())
        if not data.get('words'): raise ValueError('Não foi reconhecida fala. A validação não pôde ser concluída.')
        return data


def markers(report):
    result=[]
    for i,h in enumerate(report['resquicios'],1):
        result.append({'inicio':h['inicio'],'fim':h['fim'],'nome':f"TROCAR {i:03d} · {h['termo']}" if h['tipo']=='produto_antigo' else f"REVISAR {i:03d} · {h['termo']}",'comentario':h['texto']+' | '+h['status']})
    for c in report['candidatos_pitch']:
        selected=report['pitch'] and c['tempo']==report['pitch']['tempo']
        result.append({'inicio':c['tempo'],'fim':max(c['tempo']+.1,c['fim']),'nome':('PITCH · ' if selected else 'REVISAR PITCH · ')+c['valor'],'comentario':c['contexto']+' | '+c['status']})
    return sorted(result,key=lambda r:r['inicio'])


def jsx(items,source,tag):
    data=json.dumps(items,ensure_ascii=True)
    return '''// DR Studio: somente marcadores, sem cortes ou substituições.
// Executar em host ExtendScript/CEP do Premiere com a sequência correta aberta.
(function () {
 var seq=app.project.activeSequence;
 if (!seq) { alert("Abra a sequencia do video analisado."); return; }
 var offset=prompt("Video: __SOURCE__\\nSequencia ativa: "+seq.name+"\\nPosicao do inicio do arquivo na sequencia, em segundos (0 se comeca no inicio):", "0");
 if(offset===null) return;
 offset=Number(offset.replace(",","."));
 if(!isFinite(offset)||offset<0) { alert("Posicao invalida."); return; }
 var rows=__DATA__,count=0;
 for(var i=0;i<rows.length;i++) {
   var row=rows[i],key="[DR:__TAG__:"+i+":"+offset+"]",exists=false;
   var prev=seq.markers.getFirstMarker();
   while(prev) { if(String(prev.comments).indexOf(key)>=0) { exists=true;break; } prev=seq.markers.getNextMarker(prev); }
   if(exists) continue;
   var marker=seq.markers.createMarker(offset+row.inicio);
   marker.name=row.nome;marker.comments=key+" "+row.comentario;
   marker.end=offset+row.fim;count++;
 }
 alert(count+" marcadores criados. Nenhum corte foi feito.");
})();
'''.replace('__DATA__',data).replace('__SOURCE__',json.dumps(source,ensure_ascii=True)[1:-1]).replace('__TAG__',tag)


def export(report,path,info,tag):
    rows=markers(report)
    base='validacao_'+tag
    report=report|{'arquivo_fonte':str(path),'duracao_s':info['duracao'],'fps':info['fps'],'origem_tempos':'segundos desde o início do arquivo; sem timecode de origem','marcadores':rows}
    (M.OUT_DIR/(base+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (M.OUT_DIR/(base+'.jsx')).write_text(jsx(rows,Path(path).name,tag))
    # FCP7 XML: sequência nova com o vídeo completo e marcadores, sem alterar projeto existente.
    root=ET.Element('xmeml',version='4');seq=ET.SubElement(root,'sequence',id='dr-'+tag)
    fps=float(info['fps'] or 30);nom=round(fps);ntsc=abs(fps-nom)>.01
    def value(parent,key,text): ET.SubElement(parent,key).text=str(text)
    def rate(parent):
        r=ET.SubElement(parent,'rate');value(r,'timebase',nom);value(r,'ntsc','TRUE' if ntsc else 'FALSE')
    frames=round(info['duracao']*fps)
    value(seq,'name','DR Validação · '+Path(path).stem);value(seq,'duration',frames);rate(seq)
    for row in rows:
        m=ET.SubElement(seq,'marker');value(m,'name',row['nome']);value(m,'comment',row['comentario']);value(m,'in',round(row['inicio']*fps));value(m,'out',min(frames,max(round(row['fim']*fps),round(row['inicio']*fps)+1)))
    media=ET.SubElement(seq,'media')
    video_media=ET.SubElement(media,'video')
    fmt=ET.SubElement(ET.SubElement(video_media,'format'),'samplecharacteristics')
    rate(fmt);value(fmt,'width',info['largura']);value(fmt,'height',info['altura']);value(fmt,'pixelaspectratio','square');value(fmt,'fielddominance','none')
    audio_media=ET.SubElement(media,'audio') if info['tem_audio'] else None
    for kind in ['video']+(['audio'] if info['tem_audio'] else []):
        track=ET.SubElement(video_media if kind=='video' else audio_media,'track');clip=ET.SubElement(track,'clipitem',id='clip-'+kind)
        for k,v in [('name',Path(path).name),('duration',frames),('start',0),('end',frames),('in',0),('out',frames)]: value(clip,k,v)
        rate(clip)
        f=ET.SubElement(clip,'file',id='file-'+tag)
        if kind=='video':
            value(f,'name',Path(path).name);value(f,'pathurl',Path(path).resolve().as_uri());rate(f);value(f,'duration',frames)
            fm=ET.SubElement(f,'media'); vc=ET.SubElement(ET.SubElement(fm,'video'),'samplecharacteristics');rate(vc)
            value(vc,'width',info['largura']);value(vc,'height',info['altura']);value(vc,'pixelaspectratio','square')
            ac=ET.SubElement(ET.SubElement(fm,'audio'),'samplecharacteristics');value(ac,'samplerate',info.get('sample_rate') or 48000);value(ac,'depth',16)
        st=ET.SubElement(clip,'sourcetrack');value(st,'mediatype',kind);value(st,'trackindex',1)
    ET.indent(root)
    from .nomes_arquivos import write_xml
    label=Path(path).parent.name if Path(path).stem=='_fonte' else Path(path).stem
    marked=write_xml(root,M.OUT_DIR,label,'Conferencia - Marcadores')
    cutroot=copy.deepcopy(root)
    cutseq=cutroot.find('sequence')
    cutseq.find('name').text='DR Cortes · '+Path(path).stem
    cutseq.set('id','dr-cortes-'+tag)
    # Quantiza ao quadro e preserva a cobertura integral da mídia nas duas trilhas.
    ranges=[]
    for hit in report['resquicios']:
        if hit['status'] != 'encontrado': continue
        a=max(0,min(frames,math.floor(hit['inicio']*fps)))
        b=max(0,min(frames,math.ceil(hit['fim']*fps)))
        if b>a: ranges.append((a,b))
    ranges.sort()
    merged=[]
    for a,b in ranges:
        if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else: merged.append((a,b))
    bounds=sorted({0,frames,*[n for pair in merged for n in pair]})
    for track in cutseq.findall('./media/video/track')+cutseq.findall('./media/audio/track'):
        original=track.find('clipitem')
        track.remove(original)
        kind=original.findtext('sourcetrack/mediatype')
        for i,(a,b) in enumerate(zip(bounds,bounds[1:])):
            clip=copy.deepcopy(original);clip.set('id',f'dr-{tag}-{kind}-{i}')
            for key,value_ in [('start',a),('end',b),('in',a),('out',b)]: clip.find(key).text=str(value_)
            if any(lo<=a and b<=hi for lo,hi in merged): clip.find('name').text='TROCAR · '+Path(path).name
            # A mídia é definida uma vez e referenciada pelos demais segmentos.
            if kind!='video' or i>0:
                file=clip.find('file')
                for child in list(file): file.remove(child)
            # Vincula cada par áudio/vídeo, para seleção e movimentação conjunta.
            if info['tem_audio']:
                for linked_kind in ('video','audio'):
                    link=ET.SubElement(clip,'link')
                    value(link,'linkclipref',f'dr-{tag}-{linked_kind}-{i}')
                    value(link,'mediatype',linked_kind);value(link,'trackindex',1);value(link,'clipindex',i+1)
            track.append(clip)
    ET.indent(cutroot)
    cutfile=write_xml(cutroot,M.OUT_DIR,label,'Conferencia - Cortes')
    report['cortes_automaticos']={'trechos':len(merged),'segmentos':len(bounds)-1,'intervalos_frames':merged,'fps':fps,'conteudo_removido':False,'regra':'Frases com menções exatas; grafias parecidas e candidatos de pitch recebem somente marcadores.'}
    exports={ext:base+'.'+ext for ext in ('json','jsx')}|{'xml':marked.name,'cortes':cutfile.name}
    report['exports']=exports
    (M.OUT_DIR/(base+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def audit_path(job,path,options):
    tr=transcribe(job,path,options)
    phase(job,'analise','Análise da transcrição')
    job.step='Procurando produto antigo e preço dos 6 potes';job.pct=.92
    report=analyze(tr['words'],options.get('termos',''))
    report.update({'transcricao':tr,'motor':tr['engine']})
    return export(report,path,M.probe(path),uuid.uuid4().hex[:10])


def run(job,options):
    if options.get('video'):
        meta=M.read_meta(options['video'])
        if not meta: raise ValueError('Vídeo não encontrado na biblioteca.')
        path=M.vdir(options['video'])/meta['arquivo']
    elif options.get('arquivo'):
        path=(M.OUT_DIR/options['arquivo']).resolve()
        if path.parent!=M.OUT_DIR.resolve() or not path.is_file(): raise ValueError('Arquivo de saída não encontrado.')
    else:
        from .demandas import download
        vid=download(job,options['url']);meta=M.read_meta(vid);path=M.vdir(vid)/meta['arquivo']
    report=audit_path(job,path,options)
    job.step='Validação concluída — confira os resultados'
    return {'validacao':public(report)}


def submit(options):
    if not any(options.get(k) for k in ('video','arquivo','url')): raise ValueError('Escolha um vídeo ou informe o link.')
    if options.get('url'):
        from .demandas import check_url
        check_url(options['url'])
    return M.submit('validacao','Validar produto e localizar pitch',run,'asr',options=options)


def public(report):
    # A transcrição integral fica no JSON; não trafega a cada atualização da fila.
    return {k:v for k,v in report.items() if k!='transcricao'}

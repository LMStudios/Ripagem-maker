"""Conferência editorial, pronúncia, ajustes locais e trilha. Nenhuma geração paga automática."""
import copy,math,re
from pathlib import Path
from . import trocas as T,ml_core as M
UNKNOWN='A_CONFIRMAR'

def tokens(text):return re.findall(r"[\w]+",str(text).casefold())
def speaker_info(phrase,raw):
    words=[w for w in raw.get('words',[]) if w.get('start',0)<phrase['end'] and w.get('end',0)>phrase['start']]
    labels={str(w['speaker']).strip() for w in words if w.get('speaker') is not None and str(w.get('speaker')).strip()}
    declared=str(phrase.get('speaker') or '').strip()
    if not words and declared:return declared,False,''
    missing=not labels or any(w.get('speaker') is None or not str(w.get('speaker')).strip() for w in words)
    conflict=len(labels)>1 or bool(labels and declared and declared not in labels)
    if missing or conflict:return UNKNOWN,True,'Speaker ausente ou conflitante; ouça o trecho e confirme.'
    return next(iter(labels)),False,''

def pronunciation(plan,text):
    value=plan.get('editorial',{}).get('pronuncia','').strip();name=plan.get('produto_novo','').strip()
    if not value or not name:return str(text)
    return re.sub(r'(?<!\w)'+re.escape(name)+r'(?!\w)',lambda _:value,str(text),flags=re.I)

def settings(out,body):
    value=str(body.get('pronuncia','')).strip()
    if len(value)>180 or '\n' in value:raise ValueError('Use uma orientação de pronúncia de até 180 caracteres, em uma linha.')
    aliases=str(body.get('aliases','')).strip()
    if len(aliases)>1500:raise ValueError('Use até 1500 caracteres nas grafias antigas.')
    with T.LOCK:
        plan=T.load(out);before=copy.deepcopy(plan);changed=[]
        plan.setdefault('editorial',{}).update(pronuncia=value,aliases=aliases)
        for row in plan['itens']:
            if pronunciation(before,row['novo'])!=pronunciation(plan,row['novo']):
                if row.get('audio'):row.setdefault('historico_audio',[]).append(copy.deepcopy(row.pop('audio')))
                changed.append(row['id'])
        if changed:plan.pop('previa',None)
        if changed or before.get('editorial',{}).get('aliases','')!=aliases:plan['revisao']=None
        T.write(T.plan_path(out),plan)
    return {'plano':plan,'falas_afetadas':changed}

def assign(out,body):
    name=str(body.get('speaker','')).strip()
    if not re.fullmatch(r'[\w -]{1,40}',name) or name==UNKNOWN:raise ValueError('Informe um speaker existente ou um novo nome, como DEPO_01.')
    ids=body.get('ids',[])
    if not isinstance(ids,list) or not ids:raise ValueError('Escolha uma ou mais frases.')
    with T.LOCK:
        plan=T.load(out);byid={r['id']:r for r in plan['itens']}
        if any(rid not in byid for rid in ids):raise ValueError('Há uma frase desconhecida.')
        for rid in ids:
            row=byid[rid]
            if row['speaker']!=name and row.get('audio'):row.setdefault('historico_audio',[]).append(copy.deepcopy(row.pop('audio')))
            row.update(speaker=name,speaker_pendente=False,speaker_confirmado=True,speaker_aviso='');row.pop('speaker_sugerido',None)
        plan['speakers']=sorted(set(plan['speakers'])|{name});plan['revisao']=None;plan.pop('previa',None);T.write(T.plan_path(out),plan)
    return plan

def get_row(out,rid):
    plan=T.load(out);row=next((r for r in plan['itens'] if r['id']==rid),None)
    if not row:raise ValueError('Frase não encontrada.')
    return plan,row

def original_job(job,out,rid):
    plan,row=get_row(out,rid);target=T.audio_path(out,row,'ORIGINAL','.mp3')
    M.run_proc(job,[M.FFMPEG,'-y','-v','error','-ss',str(row['inicio_ms']/1000),'-i',str(T.source(out)),'-t',str(row['duracao_s']),'-vn','-c:a','libmp3lame',str(target)])
    with T.LOCK:
        current,latest=get_row(out,rid);latest['original_audio']=str(target.relative_to(out));T.write(T.plan_path(out),current)
    return {'arquivo':str(target.relative_to(out))}

def repetitions(words,expected):
    seq=[]
    for w in words:
        for word in tokens(w.get('w',w.get('text',''))):seq.append((word,float(w.get('s',w.get('start',0))),float(w.get('e',w.get('end',0)))))
    result=[];wanted=tokens(expected)
    for width in range(1,min(5,len(seq)//2+1)):
        a=[w[0] for w in seq[-2*width:-width]];b=[w[0] for w in seq[-width:]]
        if a==b and a:
            expected_repeats=any(wanted[i:i+width]==a and wanted[i+width:i+2*width]==a for i in range(max(0,len(wanted)-2*width+1)))
            if not expected_repeats:result.append({'tipo':'possivel_repeticao_final','inicio_audio_ms':round(seq[-width][1]*1000),'fim_audio_ms':round(seq[-1][2]*1000),'texto':' '.join(b),'status':'revisar','observacao':'Sugestão da transcrição local; ouça antes de cortar. Não comprova repetição no áudio.'})
    return result

def analyze_job(job,out,rid,motor='fw',idioma='auto'):
    from . import validacao as V
    plan,row=get_row(out,rid);audio=row.get('audio',{});relative=audio.get('fit')
    if not relative:raise ValueError('Gere ou importe o áudio antes de analisar.')
    file=Path(out)/relative;stamp=[file.stat().st_size,file.stat().st_mtime_ns];transcript=V.transcribe(job,file,{'motor':motor,'idioma':idioma})
    report={'arquivo':relative,'stamp':stamp,'alertas':repetitions(transcript['words'],audio.get('texto_enviado') or pronunciation(plan,row['novo'])),'texto_reconhecido':' '.join(w.get('w',w.get('text','')) for w in transcript['words']),'observacao':'Análise local de possível repetição. Duração maior que a original não é considerada erro.'}
    with T.LOCK:
        current,latest=get_row(out,rid)
        if latest.get('audio',{}).get('fit')!=relative:raise ValueError('O áudio mudou durante a análise. Analise novamente.')
        latest['audio']['analise']=report;T.write(T.plan_path(out),current)
    return report

def trim_job(job,out,rid,start_ms=0,end_ms=None):
    plan,row=get_row(out,rid);old=copy.deepcopy(row.get('audio',{}))
    if not old.get('raw'):raise ValueError('Áudio gerado ou importado não encontrado.')
    source=Path(out)/old['raw'];duration=T.probe(source)['duration'];start=float(start_ms)/1000;end=duration if end_ms is None else float(end_ms)/1000
    if not all(math.isfinite(x) for x in (start,end)) or not 0<=start<end<=duration+.002 or end-start<.1:raise ValueError('Informe um intervalo válido no áudio gerado, com pelo menos 100 ms.')
    target=T.audio_path(out,row,'RECORTADO','.wav')
    M.run_proc(job,[M.FFMPEG,'-y','-v','error','-i',str(source),'-vn','-af',f'atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS','-c:a','pcm_s16le',str(target)])
    fresh=T.fit(job,out,row,target,True);fresh.update({k:old[k] for k in ('assinatura','provider','model','voice_id','texto_enviado','contexto_usado') if k in old})
    fresh.update(raw=old['raw'],duracao_bruta_s=duration,fonte_preparo=str(target.relative_to(out)),recorte_inicio_ms=round(start*1000),recorte_fim_ms=round(end*1000))
    T.record_audio(out,rid,fresh)
    with T.LOCK:
        current,latest=get_row(out,rid);latest.setdefault('historico_audio',[]).append(old);T.write(T.plan_path(out),current)
    return {'id':rid,'audio':fresh,'observacao':'Recorte local salvo em novo arquivo. Gerado bruto e outras frases preservados. Ouça e aprove novamente.'}

def visual_references(raw,existing):
    from . import visuais as V
    result=[];explicit=re.compile(r'\b(bottles?|jars?|potes?|frascos?|capsules?|cápsulas?|patch(?:es)?|adesivos?|droppers?|gotas?|powder|pó|gummies)\b',re.I)
    generic=re.compile(r'\b(this (?:product|formula|treatment)|este produto|essa fórmula|esse tratamento|seu pedido|your order)\b',re.I)
    for sentence in V.sentences(raw.get('words',[])):
        text=' '.join(w['text'] for w in sentence)
        if not explicit.search(text) and not generic.search(text):continue
        a=max(0,min(w['start'] for w in sentence)-150);b=max(w['end'] for w in sentence)+250
        if any(r['start']<b and r['end']>a for r in existing+result):continue
        result.append({'id':T.digest(['visual_referencia',a,b,text]),'start':a,'end':b,'kit':None,'selected':False,'text':text,'motivo':'Referência à apresentação do produto' if explicit.search(text) else 'Referência contextual ao produto/pedido','confianca':'revisar','somente_visual':True})
    return result

def distribution(state):
    counts={};seconds={};last=None;repeated=[]
    for segment in state.get('segments',[]):
        aid=segment['asset'];counts[aid]=counts.get(aid,0)+1;seconds[aid]=seconds.get(aid,0)+(segment['end_frame']-segment['start_frame'])/state.get('fps',30)
        if aid==last:repeated.append(segment['mention'])
        last=aid
    used=[{'nome':a['name'],'uso':a.get('uso','produto' if a.get('kit') else 'apoio'),'vezes':counts.get(a['id'],0),'segundos':round(seconds.get(a['id'],0),2)} for a in state.get('assets',[]) if counts.get(a['id'])]
    return {'materiais':used,'repeticoes_consecutivas':repeated,'pendencias':state.get('issues',[]),'fallbacks':state.get('fallbacks',[])}

def soundtrack(out,body):
    mode=body.get('modo','nao_definida');gain=float(body.get('ganho_db',-18))
    if mode not in {'original','separada','sem','nao_definida'} or not math.isfinite(gain) or not -60<=gain<=0:raise ValueError('Escolha o modo da trilha e um volume entre -60 e 0 dB.')
    with T.LOCK:
        plan=T.load(out);music=plan.get('trilha',{})
        if mode=='separada' and not music.get('arquivo'):raise ValueError('Importe uma trilha antes de escolher trilha separada.')
        plan['trilha']=dict(music,modo=mode,ganho_db=gain,repetir=bool(body.get('repetir',False)));plan['revisao']=None;plan.pop('previa',None);T.write(T.plan_path(out),plan)
    return plan['trilha']

def add_music(job,out,source,duration,start_seconds=0):
    music=T.load(out).get('trilha',{})
    if music.get('modo')!='separada':return Path(source)
    file=Path(out)/music['arquivo'];length=T.probe(file)['duration'];loop=music.get('repetir',False)
    if not loop and start_seconds>=length:return Path(source)
    offset=start_seconds%length if loop else start_seconds;source=Path(source);target=source.with_name(source.stem+'_TRILHA'+source.suffix)
    cmd=[M.FFMPEG,'-y','-v','error','-i',str(source)]
    if loop:cmd+=['-stream_loop','-1']
    cmd+=['-ss',str(offset),'-i',str(file),'-filter_complex',f"[1:a]volume={music.get('ganho_db',-18)}dB,apad,atrim=duration={duration:.9f}[music];[0:a][music]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[a]",'-map','0:v?','-map','[a]','-c:v','copy',*M.aac_args(target),'-t',str(duration),str(target)]
    M.run_proc(job,cmd);return target

def preflight(out):
    from . import visuais as V
    from . import conferencia_mencoes as CM
    plan=T.load(out);selected=[r for r in plan['itens'] if r['aprovado']];state=V.load(out);music=plan.get('trilha',{});alerts=[]
    pending=[r['id'] for r in selected if r['speaker']==UNKNOWN or r.get('speaker_pendente')];missing=[r['id'] for r in selected if not r.get('audio',{}).get('fit') or not (Path(out)/r['audio']['fit']).is_file()];unapproved=[r['id'] for r in selected if not r.get('audio',{}).get('aprovado')]
    duplicates=[{'id':r['id'],'alertas':r['audio']['analise']['alertas']} for r in selected if r.get('audio',{}).get('analise',{}).get('alertas') and r['audio']['analise'].get('arquivo')==r['audio'].get('fit')]
    forms=[r for r in selected if r.get('forma_pendente') and not r.get('forma_confirmada')]
    if forms:alerts.append({'tipo':'forma','bloqueia':True,'texto':str(len(forms))+' frases com modo de uso ou mecanismo antigo ainda precisam de adaptação.','etapa':3})
    if pending:alerts.append({'tipo':'speaker','bloqueia':True,'texto':str(len(pending))+' speaker(s) precisam de confirmação.','etapa':3})
    if missing:alerts.append({'tipo':'audio','bloqueia':True,'texto':str(len(missing))+' falas sem áudio preparado.','etapa':3})
    if unapproved:alerts.append({'tipo':'aprovacao','bloqueia':False,'texto':str(len(unapproved))+' áudios ainda não aprovados.','etapa':3})
    if duplicates:alerts.append({'tipo':'repeticao','bloqueia':False,'texto':str(len(duplicates))+' áudios têm possível repetição final; ouça antes de entregar.','etapa':3})
    coverage=CM.scan(out,plan);omitted=[r for r in coverage['pendencias'] if r['status'] in ('sem_fala','fora_da_selecao','texto_antigo')]
    if omitted:alerts.append({'tipo':'mencoes','bloqueia':True,'texto':str(len(omitted))+' menção(ões) do produto antigo ainda sem substituição, inclusive falas fora da seleção. Confira a Conferência completa das menções em Falas.','etapa':3})
    if state.get('issues'):alerts.append({'tipo':'takes','bloqueia':True,'texto':str(len(state['issues']))+' intervalos visuais pendentes.','etapa':4})
    if music.get('modo','nao_definida')=='nao_definida':alerts.append({'tipo':'trilha','bloqueia':False,'texto':'Trilha ainda não definida. Escolha manter o original, adicionar trilha ou seguir sem trilha separada.','etapa':6})
    review={}  # A validação textual ocorre com o SRT enviado na etapa final.
    if music.get('modo')=='separada':
        file=Path(out)/music.get('arquivo','')
        if not file.is_file():alerts.append({'tipo':'trilha','bloqueia':True,'texto':'Arquivo da trilha não encontrado.','etapa':6})
        elif not music.get('repetir') and T.probe(file)['duration']<plan['duracao_s']:alerts.append({'tipo':'trilha_curta','bloqueia':False,'texto':'A trilha é menor que a VSL e terminará antes do vídeo; ative repetição se desejar.','etapa':6})
    return {'produto_antigo':plan['produto'],'produto_novo':plan['produto_novo'],'pronuncia':plan.get('editorial',{}).get('pronuncia',''),'aliases':plan.get('editorial',{}).get('aliases',''),'selecionadas':len(selected),'geradas':len(selected)-len(missing),'aprovadas':len(selected)-len(unapproved),'speakers_pendentes':pending,'trilha':music,'visuais':distribution(state),'alertas':alerts,'revisao':review,'entrega':T.delivery_info(out,plan.get('entrega') or {}),'entrega_atual':T.flow_state(out)['entrega_atual'],'limite':'Análise de transcrição e plano de montagem. Não faz leitura visual de imagens/legendas do vídeo. Tempos e alertas devem ser conferidos no Premiere.'}

def analyze_batch(job,out,motor='mlx'):
    plan=T.load(out);rows=[r for r in plan['itens'] if r.get('aprovado') and r.get('audio',{}).get('fit')];results=[]
    if not rows:raise ValueError('Gere ou importe áudios antes de conferir os finais.')
    for index,row in enumerate(rows):
        if job.cancel:raise M.Cancelled()
        file=Path(out)/row['audio']['fit'];saved=row['audio'].get('analise',{});stamp=[file.stat().st_size,file.stat().st_mtime_ns]
        job.step=f'Conferindo final da fala {index+1} de {len(rows)}';job.progress={'tipo':'revisao_audio','fase':'Conferência local dos finais','processadas':index,'total':len(rows),'indeterminado':True}
        if saved.get('arquivo')==row['audio']['fit'] and saved.get('stamp')==stamp:report=saved
        else:report=analyze_job(job,out,row['id'],motor)
        results.append({'id':row['id'],'alertas':len(report.get('alertas',[]))});job.pct=(index+1)/len(rows)
    job.step='Finais conferidos — ouça os alertas antes de aprovar';return {'resultados':results,'local':True,'observacao':'Transcrição local pode falhar. Nenhum áudio foi cortado ou aprovado automaticamente.'}

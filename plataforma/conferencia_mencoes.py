"""Cobertura das menções na transcrição inteira, independente do OCR e da seleção."""
import json,re
from collections import Counter,defaultdict
from pathlib import Path
from . import trocas as T
from .mencoes import names,compact,transcript_words,timed_spans,is_common_speech_word,spans


def lexical(word):
    return re.sub(r"['’]s(?=[^\w]*$)",'',str(word),flags=re.I)


def aliases(plan,words=None):
    from . import falas_visuais as FV
    explicit=names(plan.get('produto'),str(plan.get('produto_aliases',''))+','+str(plan.get('editorial',{}).get('aliases','')))
    explicit=[n for n in explicit if not is_common_speech_word(n)]
    if not explicit:return []
    found={compact(n):n for n in explicit};counts=Counter();contexts=defaultdict(set)
    def suggestions(group):
        for i,size,_ in FV.hits(group,plan):
            value=' '.join(lexical(w['text']) for w in group[i:i+size]).strip('.,!?;:"()[] ')
            if compact(value) and not is_common_speech_word(value):yield i,size,value
    # Uma variante já revisada no projeto é evidência reutilizável, sem alterar a transcrição.
    for row in plan.get('itens',[]):
        if row.get('mencao_descartada') or not (row.get('origem')=='conferencia_visual' or row.get('aprovado') or row.get('speaker_confirmado')):continue
        group=[{'text':w,'start':i*100,'end':i*100+90,'speaker':'A'} for i,w in enumerate(row['original'].split())]
        for _,_,value in suggestions(group):found.setdefault(compact(value),value)
    # Novas grafias precisam se repetir com contexto de produto; não basta semelhança.
    for group in FV.sentences(words or []):
        for i,size,value in suggestions(group):
            key=compact(value);counts[key]+=1
            context=' '.join(w['text'] for w in group[max(0,i-5):i+size+5]).lower()
            if re.search(r'\b(?:formula|treatment|supplement|bottles?|capsules?|buy|order|recommend|try|produto|frasco|tratamento)\b',context):contexts[key].add(group[0]['start'])
            if counts[key]>=3 and len(contexts[key])>=2:found.setdefault(key,value)
    return list(found.values())


def identity(out,plan,raw):
    return T.digest([T.source_identity(T.source(out)),plan.get('produto'),raw])


def decisions(out,key):
    f=Path(out)/'trocas/mencoes_descartadas.json'
    if not f.exists():return {}
    data=json.loads(f.read_text());return data.get('itens',{}) if data.get('base')==key else {}


def scan(out,plan=None):
    from . import falas_visuais as FV
    out=Path(out);plan=T.load(out) if plan is None else plan
    if plan.get('somente_valores') or not plan.get('produto_novo') or compact(plan.get('produto'))==compact(plan.get('produto_novo')):return {'itens':[],'pendencias':[],'aliases':[],'ignorado':True}
    file=out/'transcricao_bruta.json'
    if not file.exists():return {'itens':[],'pendencias':[],'aliases':[],'indisponivel':True}
    raw=json.loads(file.read_text());words=transcript_words(raw);known=aliases(plan,words);key=identity(out,plan,raw);ignored=decisions(out,key)
    groups=FV.sentences(words);lookup={id(w):group for group in groups for w in group}
    lexical_words=[dict(w,text=lexical(w['text'])) for w in words];rows=[]
    for i,size,score in timed_spans(lexical_words,known,field='text',time='start',end='end',max_pause=850):
        a,b=int(words[i]['start']),int(words[i+size-1]['end']);group=lookup[id(words[i])];label=' '.join(w['text'] for w in words[i:i+size]);rid=T.digest([a,b,label])
        containing=[r for r in plan['itens'] if r['inicio_ms']<=a and r['fim_ms']>=b];selected=[r for r in containing if r.get('aprovado')]
        row=next(iter(selected or containing),None);status='sem_fala'
        if rid in ignored or row and row.get('mencao_descartada'):status='descartada'
        elif row:
            audio=row.get('audio',{})
            if spans([lexical(t) for t in row['novo'].split()],known,approximate=False):status='texto_antigo'
            elif not row.get('aprovado'):status='fora_da_selecao'
            elif not audio.get('fit') or not (out/audio['fit']).is_file():status='sem_audio'
            elif audio.get('texto_hash')!=T.digest([row['novo'],row['speaker']]) or audio.get('modo_duracao','fixo')!=plan.get('modo_duracao','fixo'):status='audio_desatualizado'
            elif not audio.get('aprovado'):status='audio_nao_aprovado'
            else:status='coberta'
        rows.append({'id':rid,'inicio_ms':a,'fim_ms':b,'termo':label,'frase_inicio_ms':group[0]['start'],'frase_fim_ms':group[-1]['end'],'texto':' '.join(w['text'] for w in group),'status':status,'id_fala':row['id'] if row else None,'palavras':group})
    return {'base':key,'itens':rows,'pendencias':[r for r in rows if r['status'] not in ('coberta','descartada')],'aliases':known,'transcricao_parcial':bool(raw.get('recorte_transcricao')),'limite':'Conferência da transcrição disponível e dos arquivos de substituição. Não comprova a pronúncia dos áudios gerados nem analisa trechos não transcritos.'}


def dismiss(out,start,end,reason):
    with T.LOCK:
        report=scan(out);items=decisions(out,report['base'])
        for row in report['itens']:
            if start<=row['inicio_ms'] and row['fim_ms']<=end:items[row['id']]={'motivo':reason,'termo':row['termo']}
        T.write(Path(out)/'trocas/mencoes_descartadas.json',{'base':report['base'],'itens':items})


def public(report):
    return {k:([{a:b for a,b in row.items() if a!='palavras'} for row in v] if k in ('itens','pendencias') else v) for k,v in report.items()}


def require(out,plan=None,*,job=None):
    plan=T.load(out) if plan is None else plan
    report=scan(out,plan)
    if report['pendencias']:
        first=report['pendencias'][0];t=first['inicio_ms']//1000
        if job is not None:
            job.error_action = {'tipo': 'revisar_mencao', 'trecho': {
                key: first[key] for key in ('inicio_ms', 'fim_ms', 'status', 'id_fala')
            }}
        raise ValueError(f"Há {len(report['pendencias'])} menção(ões) do produto antigo sem substituição concluída na transcrição. Primeira em {t//60:02}:{t%60:02} do vídeo original. Volte a Falas → Conferência completa das menções; confira também as falas fora da seleção. Nenhum XML novo foi gerado.")
    review=plan.get('revisao') or {}
    if not report.get('ignorado') and review.get('resquicios') and review.get('assinatura')==T.preview_signature(out):
        raise ValueError('A conferência do áudio final encontrou possíveis resquícios do produto antigo. Revise os marcadores antes de gerar outro XML.')
    return public(report)


def verify_xml(sequence,report,fps):
    """Inspeciona A1 após cortes/deslocamentos; tempos in/out continuam na fonte."""
    track=sequence.find('media/audio/track')
    clips=[] if track is None else [c for c in track.findall('clipitem') if c.findtext('enabled','TRUE')=='TRUE']
    left=[];checked=0
    for row in report.get('itens',[]):
        if row['status']=='descartada':continue
        checked+=1;a=round(row['inicio_ms']/1000*fps);b=max(a+1,round(row['fim_ms']/1000*fps))
        if any(min(int(c.findtext('out')),b)>max(int(c.findtext('in')),a) for c in clips):left.append(row)
    if left:raise ValueError(f"A conferência do XML encontrou {len(left)} menção(ões) ainda no áudio original ativo. A entrega foi interrompida antes de salvar o XML.")
    return {'mencoes_verificadas':checked,'mencoes_no_audio_original_ativo':0,'regra':'Conferência dos quadros de origem em A1 depois de aplicar os deslocamentos; não verifica a pronúncia da nova voz.'}

"""Segunda conferência: evidência visual gera candidatos; somente revisão altera Falas."""
import copy,json,re,tempfile,uuid,platform
from pathlib import Path
from difflib import SequenceMatcher
from . import trocas as T,deteccao_visual as D,formas as F,ml_core as M
from .mencoes import names,transcript_words,timed_spans,compact,is_common_speech_word

def path(out):return Path(out)/'trocas/conferencia_visual_falas.json'
def read(out):return json.loads(path(out).read_text()) if path(out).exists() else {}
def terms(plan):return names(plan['produto'],str(plan.get('produto_aliases',''))+','+str(plan.get('editorial',{}).get('aliases','')))
def hits(words,plan):
    result=timed_spans(words,terms(plan),field='text',time='start',end='end',max_pause=850)
    # Aqui já existe evidência visual do produto: aceita grafias próximas como
    # sugestões para revisão, sem afrouxar a busca principal nem aprovar nada.
    targets=[compact(n) for n in terms(plan) if len(compact(n))>=5]
    occupied={i for start,size,_ in result for i in range(start,start+size)}
    for i,w in enumerate(words):
        if i in occupied:continue
        for size in (2,1):
            chunk=words[i:i+size]
            if len(chunk)!=size or any(j in occupied for j in range(i,i+size)):continue
            if size>1 and any(is_common_speech_word(w['text']) for w in chunk):continue
            if size>1 and (chunk[0].get('speaker')!=chunk[1].get('speaker') or chunk[1]['start']-chunk[0]['end']>850 or re.search(r'[.!?]["\')\]]*$',chunk[0]['text'])):continue
            value=compact(' '.join(x['text'] for x in chunk))
            if len(value)<5 or is_common_speech_word(value):continue
            score=max((SequenceMatcher(None,value,t).ratio() for t in targets if value[:3]==t[:3] and abs(len(value)-len(t))<=2),default=0)
            if score>=.70:
                result.append((i,size,score));occupied.update(range(i,i+size));break
    return sorted(result)

def basis(out):
 p=T.load(out)
 return T.digest([p['produto'],p['produto_novo'],p.get('produto_aliases'),p.get('forma'),p.get('editorial'),p.get('somente_valores'),T.source_identity(T.source(out)),(Path(out)/'transcricao_bruta.json').read_text(),[(r['id'],r['inicio_ms'],r['fim_ms'],r['novo'],r['speaker']) for r in p['itens']],D.load(out).get('intervalos'),(Path(out)/'precos_TROCA.json').read_text() if (Path(out)/'precos_TROCA.json').exists() else ''])
def sentences(words):
 rows=[];group=[]
 for w in words:
  if group and (w.get('speaker')!=group[-1].get('speaker') or w['start']-group[-1]['end']>1500 or w['end']-group[0]['start']>60000):rows.append(group);group=[]
  group.append(w)
  if re.search(r'[.!?]["\')\]]*$',w['text']) and w['text'].lower() not in ('dr.','mr.','mrs.','etc.'):rows.append(group);group=[]
 if group:rows.append(group)
 return rows

def proposed(out,plan,text):
 # Reaproveita frases de preços já adaptadas no projeto; não calcula novas ofertas.
 price=Path(out)/'precos_TROCA.json'
 if plan.get('incluir_precos') and price.exists():
  for row in json.loads(price.read_text()).get('frases',[]):
   if row.get('text') and row.get('novo'):text=text.replace(row['text'],row['novo'])
 words=[{'text':w,'start':i*100,'end':i*100+90,'speaker':'A'} for i,w in enumerate(text.split())]
 for i,size,_ in reversed(hits(words,plan)):
  words[i:i+size]=[dict(words[i],text=(re.match(r'^[^\w]*',words[i]['text'])[0]+plan['produto_novo']+(re.search(r"['’]s(?=[^\w]*$)",words[i+size-1]['text'],re.I)[0] if re.search(r"['’]s(?=[^\w]*$)",words[i+size-1]['text'],re.I) else '')+re.search(r'[^\w]*$',words[i+size-1]['text'])[0]))]
 value=' '.join(w['text'] for w in words)
 if plan.get('forma',{}).get('ativo'):return F.adapt(value,plan['forma'])
 return value,[]

def candidate(out,plan,words,visual,proof='transcricao'):
 a,b=int(words[0]['start']),int(words[-1]['end']);text=' '.join(w['text'] for w in words)
 overlapping=[r for r in plan['itens'] if r['inicio_ms']<b and r['fim_ms']>a]
 if any(r['inicio_ms']<=a+100 and r['fim_ms']>=b-100 for r in overlapping):return None
 # Uma expansão envolve a frase inteira já existente e jamais outras falas.
 if len(overlapping)==1:
  old=overlapping[0];a=min(a,old['inicio_ms']);b=max(b,old['fim_ms'])
  allwords=transcript_words(json.loads((Path(out)/'transcricao_bruta.json').read_text()))
  if proof!='audio_local':words=[w for w in allwords if w['start']<b and w['end']>a];text=' '.join(w['text'] for w in words)
 labels={str(w['speaker']) for w in words if w.get('speaker') is not None}
 speaker=next(iter(labels)) if len(labels)==1 and all(w.get('speaker') is not None for w in words) else 'A_CONFIRMAR'
 value,notes=proposed(out,plan,text);matched=bool(hits(words,plan))
 return {'id':T.digest([a,b,text]),'inicio_ms':a,'fim_ms':b,'original':text,'novo':value,'speaker':speaker,'visual_id':visual['id'],'origem_evidencia':proof,
         'situacao':'mencao_provavel' if matched else 'conferir_audio','motivo':'Menção na transcrição ou no áudio, encontrada a partir da conferência visual.' if matched else 'O nome aparece na imagem, mas a transcrição não confirma a fala. Ouça ou reanalise este trecho.',
         'substitui_id':overlapping[0]['id'] if len(overlapping)==1 else None,'conflito':len(overlapping)>1 or b-a>60000,'avisos':notes+(['Confira os valores e kits com a oferta configurada antes de aprovar o texto.'] if plan.get('incluir_precos') else []),'forma_pendente':F.pending(notes),'status':'pendente'}

def view(out):
 with T.LOCK:
  plan=T.load(out)
  if plan.get('somente_valores'):return {'itens':[],'somente_valores':True,'base':basis(out)}
  visual=D.load(out)
  stale=bool(visual.get('analise') and D.outdated(out,visual))
  current=basis(out);saved=read(out);prior={r['id']:r for r in saved.get('itens',[])} if saved.get('base')==current else {}
  groups=sentences(transcript_words(json.loads((Path(out)/'transcricao_bruta.json').read_text())));rows={}
  from . import conferencia_mencoes as CM
  coverage=CM.scan(out,plan);effective=dict(plan,produto_aliases=','.join(coverage['aliases']))
  absent={(m['frase_inicio_ms'],m['frase_fim_ms']) for m in coverage['pendencias'] if m['status']=='sem_fala'}
  for group in groups:
   if (group[0]['start'],group[-1]['end']) not in absent:continue
   row=candidate(out,effective,group,{'id':'transcricao_integral'},'transcricao_integral')
   if row:row['motivo']='Menção na transcrição completa, inclusive fora dos trechos encontrados na imagem.';rows[row['id']]=row
  for mention in coverage['pendencias']:
   if mention['status'] not in ('fora_da_selecao','texto_antigo'):continue
   old=next((r for r in plan['itens'] if r['id']==mention['id_fala']),None)
   if not old:continue
   value,notes=proposed(out,effective,old['novo'] if mention['status']=='texto_antigo' else old['original'])
   rid=T.digest([old['id'],'reativar'])
   rows[rid]={'id':rid,'inicio_ms':old['inicio_ms'],'fim_ms':old['fim_ms'],'original':old['original'],'novo':value,'speaker':old['speaker'],'visual_id':'transcricao_integral','origem_evidencia':'transcricao_integral','situacao':'mencao_provavel','motivo':'Esta fala já está na lista, mas ficou fora da seleção da entrega.' if mention['status']=='fora_da_selecao' else 'O texto selecionado ainda contém o produto antigo.','substitui_id':old['id'],'existing_id':old['id'],'conflito':False,'avisos':notes,'forma_pendente':F.pending(notes),'status':'pendente'}
  for item in ([] if stale else visual.get('intervalos',[])):
   if item.get('status')=='descartado':continue
   close=[g for g in groups if g[0]['start']<item['fim_ms']+2000 and g[-1]['end']>item['inicio_ms']-2000]
   matches=[g for g in close if hits(g,plan)]
   # Sem menção textual: só um candidato incerto mais próximo; nunca inventa fala pelo OCR.
   if not matches and not (item.get('legenda_ms') or item.get('fala_sem_troca')):continue
   chosen=matches or sorted(close,key=lambda g:abs((g[0]['start']+g[-1]['end'])/2-(item['inicio_ms']+item['fim_ms'])/2))[:1]
   for g in chosen:
    row=candidate(out,plan,g,item)
    if row:rows[row['id']]=row
  for rid,row in prior.items():
   if row.get('origem_evidencia')=='audio_local':rows[rid]=row
   elif rid in rows:rows[rid].update({k:row[k] for k in ('status',) if k in row})
  cache=saved.get('audio_cache',[])
  visual_ids={r['id'] for r in visual.get('intervalos',[]) if r.get('status')!='descartado'}
  for entry in cache:
   if entry.get('fonte')!=T.source_identity(T.source(out)) or entry.get('visual_id') not in visual_ids:continue
   for group in sentences(entry['words']):
    if not hits(group,plan):continue
    row=candidate(out,plan,group,{'id':entry['visual_id']},'audio_local')
    if row:
     if row['id'] in prior:row['status']=prior[row['id']].get('status','pendente')
     rows={k:r for k,r in rows.items() if k==row['id'] or min(r['fim_ms'],row['fim_ms'])-max(r['inicio_ms'],row['inicio_ms'])<=.5*min(r['fim_ms']-r['inicio_ms'],row['fim_ms']-row['inicio_ms'])}
     rows[row['id']]=row
  result={'base':current,'itens':sorted(rows.values(),key=lambda r:(r['inicio_ms'],r['fim_ms'],r['id'])),'fonte':'_fonte'+T.source(out).suffix,'audio_cache':cache}
  result['cobertura_mencoes']=CM.public(coverage)
  if stale:result['aviso']='A busca visual precisa ser atualizada. A conferência da transcrição continua disponível.'
  task=next((j for j in list(M.JOBS.values()) if j.kind=='conferencia_fala_visual' and j.status in ('na_fila','executando') and str(Path(j.params.get('out','')).resolve())==str(Path(out).resolve())),None)
  if task:result['tarefa']=task.id
  T.write(path(out),result);return result

def validated_row(plan,row,body,approved=False):
  if row['conflito']:raise ValueError('Há outras falas sobrepostas ou intervalo muito longo. Ajuste as falas existentes antes de incluir.')
  speaker=str(body.get('speaker',row['speaker']))
  if speaker not in plan['speakers'] or speaker=='A_CONFIRMAR':raise ValueError('Confirme o speaker do trecho.')
  text=str(body.get('original',row['original'])).strip();new=str(body.get('novo',row['novo'])).strip()
  if not text or not new or max(len(text),len(new))>8000:raise ValueError('Confira o texto original e a adaptação; limite de 8000 caracteres.')
  a,b=body.get('inicio_ms',row['inicio_ms']),body.get('fim_ms',row['fim_ms'])
  if type(a) is not int or type(b) is not int or not 0<=a<b<=round(plan['duracao_s']*1000) or b-a>60000:raise ValueError('Confira início e fim: até 60 segundos dentro do vídeo.')
  if any(r['id']!=row['substitui_id'] and r['inicio_ms']<b and r['fim_ms']>a for r in plan['itens']):raise ValueError('Já há outra fala neste intervalo. Atualize a conferência.')
  old=next((r for r in plan['itens'] if r['id']==row['substitui_id']),{})
  original_audio=old.get('original_audio') if old.get('inicio_ms')==a and old.get('fim_ms')==b else None
  fresh={'id':T.digest([a,b,text,'conferencia_visual']),'inicio_ms':a,'fim_ms':b,'original':text,'novo':new,'base_novo':new,'speaker':speaker,'speaker_confirmado':True,'speaker_pendente':False,'origem':'conferencia_visual','aprovado':approved,'duracao_s':(b-a)/1000,'original_audio':original_audio}
  if plan.get('forma',{}).get('ativo') and F.match(text,plan['forma']):
   confirmed=bool(old.get('forma_confirmada') and (text,new,speaker,a,b)==(old['original'],old['novo'],old['speaker'],old['inicio_ms'],old['fim_ms']))
   fresh.update(forma_detectada=True,forma_pendente=not confirmed,forma_confirmada=confirmed,forma_avisos=row['avisos'],aprovado=approved and confirmed)
  if old.get('audio') or old.get('historico_audio'):fresh['historico_audio']=old.get('historico_audio',[])+([old['audio']] if old.get('audio') else [])
  return fresh

def insert_row(plan,row,fresh):
  old=next((r for r in plan['itens'] if r['id']==row.get('existing_id')),None)
  if old and (fresh['inicio_ms'],fresh['fim_ms'],fresh['original'])==(old['inicio_ms'],old['fim_ms'],old['original']):
   if (fresh['novo'],fresh['speaker'])!=(old['novo'],old['speaker']):
    if old.get('audio'):old.setdefault('historico_audio',[]).append(copy.deepcopy(old.pop('audio')))
    old['forma_confirmada']=False
   old.update(novo=fresh['novo'],speaker=fresh['speaker'],aprovado=fresh['aprovado'])
   fresh['id']=old['id']
   return
  plan['itens']=[r for r in plan['itens'] if r['id']!=row['substitui_id']]+[fresh];plan['itens'].sort(key=lambda r:r['inicio_ms'])
  plan.setdefault('recuperadas_visuais',[]).append({'start':fresh['inicio_ms'],'end':fresh['fim_ms'],'text':fresh['original'],'novo':fresh['novo'],'speaker':fresh['speaker'],'origem':'conferencia_visual','substitui_id':row['substitui_id'],'produto_novo':plan['produto_novo']})

def review(out,body):
 from . import automatico as A,visuais as V
 if A.active(out):raise ValueError('Pause o modo automático antes de revisar as falas.')
 with T.LOCK:
  state=view(out)
  if body.get('base')!=state['base']:raise ValueError('O projeto mudou. Atualize as sugestões antes de aplicar.')
  row=next((r for r in state['itens'] if r['id']==body.get('id')),None)
  if not row:raise ValueError('Sugestão não encontrada ou já contemplada em Falas.')
  if body.get('acao') in ('descartar','somente_visual'):
   if row.get('origem_evidencia')=='transcricao_integral':
    from . import conferencia_mencoes as CM
    CM.dismiss(out,row['inicio_ms'],row['fim_ms'],body['acao'])
   row['status']=body['acao'];T.write(path(out),state);return {'estado':state}
  if body.get('acao')!='adicionar':raise ValueError('Escolha adicionar, descartar ou somente visual.')
  if body.get('confirmou_audio') is not True:raise ValueError('Ouça o trecho e confirme que esta fala precisa de adaptação.')
  plan=T.load(out);fresh=validated_row(plan,row,body,approved=bool(row.get('existing_id')))
  backup=Path(out)/'trocas/backups'/('antes_fala_visual_'+uuid.uuid4().hex+'.json');T.write(backup,plan)
  insert_row(plan,row,fresh)
  plan['revisao']=None;plan.pop('previa',None);plan.pop('entrega',None);T.write(T.plan_path(out),plan)
  state['base']=basis(out);T.write(path(out),state)
  if V.path(out).exists():V.current_state(out)
  return {'plano':plan,'estado':view(out),'id_fala':fresh['id']}

def authorize_all(out,body):
 """Uma autorização explícita, uma gravação do plano e nenhum serviço de voz."""
 from . import automatico as A,visuais as V
 if body.get('autoriza_lote') is not True:raise ValueError('Autorize a inclusão e aprovação dos textos em lote.')
 if A.active(out):raise ValueError('Pause o modo automático antes de autorizar as falas.')
 with T.LOCK:
  state=view(out)
  if body.get('base')!=state['base']:raise ValueError('O projeto mudou. Atualize as sugestões antes de autorizar.')
  plan=T.load(out);before=copy.deepcopy(plan);added=[];pending=[]
  for row in sorted(state['itens'],key=lambda r:(r['inicio_ms'],r['fim_ms'])):
   if row.get('status')!='pendente':continue
   reason=''
   if row.get('situacao')!='mencao_provavel':reason='O áudio ainda não confirmou uma menção ao produto.'
   elif row.get('forma_pendente'):reason='O modo de uso precisa de revisão.'
   if not reason:
    try:
     fresh=validated_row(plan,row,{},approved=True)
     if fresh.get('forma_pendente'):reason='O modo de uso precisa de revisão.'
     elif fresh['novo']==fresh['original']:reason='O texto ainda não tem uma adaptação.'
    except ValueError as e:reason=str(e)
   if reason:pending.append({'id':row['id'],'inicio_ms':row['inicio_ms'],'motivo':reason});continue
   insert_row(plan,row,fresh);added.append(fresh['id'])
  if added:
   T.write(Path(out)/'trocas/backups'/('antes_autorizar_falas_'+uuid.uuid4().hex+'.json'),before)
   plan['revisao']=None;plan.pop('previa',None);plan.pop('entrega',None)
   T.write(T.plan_path(out),plan)
   state['base']=basis(out);T.write(path(out),state)
   if V.path(out).exists():V.current_state(out)
  return {'plano':plan,'estado':view(out),'autorizadas':len(added),'ids_falas':added,'pendencias':pending}

def recheck(job,out,candidate_id,expected):
 from . import validacao as L
 out=Path(out);state=view(out)
 if state['base']!=expected:raise ValueError('O projeto mudou. Atualize a conferência.')
 row=next((r for r in state['itens'] if r['id']==candidate_id),None)
 if not row:raise ValueError('Sugestão não encontrada.')
 a=max(0,row['inicio_ms']/1000-2);b=min(T.load(out)['duracao_s'],row['fim_ms']/1000+2)
 if b-a>65:raise ValueError('Selecione um trecho de até 60 segundos para conferir.')
 with tempfile.TemporaryDirectory(prefix='rm-fala-visual-') as tmp:
  wav=Path(tmp)/'trecho.wav';M.run_proc(job,[M.FFMPEG,'-v','error','-y','-ss',str(a),'-i',str(T.source(out)),'-t',str(b-a),'-vn','-ac','1','-ar','16000',str(wav)])
  data=L.transcribe(job,wav,{'motor':'mlx' if platform.system()=='Darwin' and platform.machine()=='arm64' else 'fw','idioma':'auto'})
 words=[{'text':w['w'],'start':round((a+w['s'])*1000),'end':round((a+w['e'])*1000)} for w in data['words']]
 raw=transcript_words(json.loads((out/'transcricao_bruta.json').read_text()))
 for w in words:
  labels={x.get('speaker') for x in raw if x['start']<w['end'] and x['end']>w['start']}
  if len(labels)==1 and None not in labels:w['speaker']=next(iter(labels))
 with T.LOCK:
  if basis(out)!=expected:raise ValueError('O projeto mudou durante a análise. Nenhuma fala foi alterada.')
  plan=T.load(out);matched=[g for g in sentences(words) if hits(g,plan)]
  state=view(out);prior=next(r for r in state['itens'] if r['id']==candidate_id);prior['status']='audio_conferido'
  for g in matched:
   new=candidate(out,plan,g,{'id':row['visual_id']},'audio_local')
   if new:state['itens']=[r for r in state['itens'] if r['id']!=new['id']]+[new]
  if not matched:prior['status']='pendente';prior['motivo']='A segunda transcrição não confirmou o nome. Confira o áudio antes de classificar como somente visual.'
  cache=state.setdefault('audio_cache',[])
  cache[:]=[c for c in cache if c.get('id')!=candidate_id]
  cache.append({'id':candidate_id,'fonte':T.source_identity(T.source(out)),'visual_id':row['visual_id'],'words':words})
  T.write(path(out),state)
 job.step='Áudio conferido localmente; revise as sugestões';return {'encontradas':len(matched)}

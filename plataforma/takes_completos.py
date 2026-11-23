"""Referencia mídias originais, com duração inteira ou encaixe na timeline."""
import math,random,uuid
from pathlib import Path
from . import trocas as T,montagem as MT,fechamento as FC

def schedule(out,state,seed=None,job=None,preserve=False):
    from . import visuais as V
    from .workflow import require_takes
    require_takes(out)
    info=T.probe(T.source(out));fps=info['fps'];plan=T.load(out);selected=[r for r in plan['itens'] if r.get('aprovado') and r.get('audio',{}).get('fit')];changes=MT.edits(out,selected,info)
    closures=FC.windows(changes,fps) if state.get('modo_takes')=='inteiro' else []
    rows=V.covered_mentions(out,state);intervals=[];total=round(info['duration']*fps)+sum(c['extra'] for c in changes)
    total=FC.position(total,closures)
    for row in rows:
        a=MT.shift(round(row['start']/1000*fps),changes);b=MT.shift(round(row['end']/1000*fps),changes)
        a,b=FC.position(a,closures),FC.position(b,closures)
        if b>a:intervals.append((a,b,row))
    first=0 if plan.get('somente_valores') else V.first_product_mention(out)
    first_frame=MT.shift(round(first/1000*fps),changes) if first is not None else 0
    first_frame=FC.position(first_frame,closures)
    if state.get('modo_takes')=='inteiro' and state.get('ajustar_janela'):
        groups=[]
        for start,end,row in intervals:
            if groups and start-groups[-1][1]<=round(.5*fps):
                a,b,prior=groups[-1]
                kits={k for k in (prior.get('kit'),row.get('kit')) if k is not None}
                if len(kits)<=1:
                    sources=prior.get('intervalos_originais',[prior['id']])+[row['id']]
                    combined=dict(prior,id='grupo_'+T.digest(sources),kit=next(iter(kits),None),
                                  intervalos_originais=sources,start=min(prior['start'],row['start']),end=max(prior['end'],row['end']),text=prior.get('text','')+' · '+row.get('text',''))
                    groups[-1]=(a,max(b,end),combined)
                    continue
            groups.append((start,end,row))
        intervals=groups
    review=[]
    if not intervals and not state.get('coverage_markers'):raise ValueError('Selecione uma menção ou fala para cobrir.')
    old_segments=state.get('segments',[]) if preserve else [];pending={i['mention'] for i in state.get('issues',[])};kept={}
    for segment in old_segments:
        if segment['mention'] not in pending:kept.setdefault(segment['mention'],[]).append(segment)
    rng=random.Random(seed if seed is not None else uuid.uuid4().hex);rank={a['id']:rng.random() for a in state['assets']};usage={};screen={};last=None;segments=[];issues=[]
    for index,(start,end,row) in enumerate(intervals):
        if V.manual_authorized(state,row):continue
        bound=intervals[index+1][0] if index+1<len(intervals) else total
        if start<0 or end>bound or start>=end:raise ValueError('As janelas visuais estão sobrepostas ou fora da montagem.')
        existing=kept.get(row['id'])
        if existing:
            if existing[0]['start_frame']!=start or existing[-1]['end_frame']<end:raise ValueError('Os intervalos mudaram. Prepare os takes novamente antes de preencher as pendências.')
            segments.extend(existing)
            for segment in existing:
                aid=segment['asset'];usage[aid]=usage.get(aid,0)+1;screen[aid]=screen.get(aid,0)+segment['end_frame']-segment['start_frame']
            last=existing[-1]['asset'];continue
        next_fixed=kept.get(intervals[index+1][2]['id'],[]) if index+1<len(intervals) else []
        next_asset=next_fixed[0]['asset'] if next_fixed else None
        authorized=V.random_authorized(state,row)
        chosen_kit=row.get('kit');fallback=False
        choices=[a for a in state['assets'] if a['kind']=='video' and a.get('kit')==row.get('kit')]
        old_product=row.get('produto_antigo')
        # Produto antigo na imagem: nunca presume quantidade pelo kit padrão.
        random_product=authorized or row.get('kit') is None and (old_product or not state.get('kit_sem_quantidade'))
        if authorized:
            choices=[a for a in state['assets'] if a['kind']=='video' and a.get('uso')=='produto']
        elif row.get('kit') is None:
            if state.get('kit_sem_quantidade') and not old_product:
                chosen_kit=state['kit_sem_quantidade'];choices=[a for a in state['assets'] if a['kind']=='video' and a.get('kit')==chosen_kit];fallback=True
            else:
                choices=[a for a in state['assets'] if a['kind']=='video' and a.get('uso')=='produto']
                if not choices:
                    issues.append({'mention':row['id'],'code':'generico','inicio_ms':row['start'],'fim_ms':row['end'],'error':'Falta vídeo classificado como Produto. O sorteio aceita takes de produto de qualquer kit; apoio e depoimentos não entram automaticamente.'});continue
        if not choices:
            issues.append({'mention':row['id'],'code':'kit','kit':chosen_kit,'inicio_ms':row['start'],'fim_ms':row['end'],'error':f'Não há vídeo disponível para o kit {chosen_kit}. Associe os materiais ao kit correto.'});continue
        original_start,original_end=start,end
        if state.get('modo_takes')=='inteiro' and state.get('ajustar_janela'):
            shortest=min(max(1,round(a['duration']*fps)) for a in choices)
            length=math.ceil((end-start)/shortest)*shortest
            previous_end=segments[-1]['end_frame'] if segments else first_frame
            proposed=max(first_frame,previous_end,end-length)
            if proposed<=start and proposed+length<=bound:
                start,end=proposed,proposed+length
            review.append({'mention':row['id'],'kit':chosen_kit,'inicio_original_frame':original_start,
                           'fim_original_frame':original_end,'inicio_frame':start,'fim_frame':end,
                           'janelas':len(row.get('intervalos_originais',[row['id']]))})
        lengths={a['id']:max(1,round(a['duration']*fps)) for a in choices};assets={a['id']:a for a in choices};failed=set();local={};steps=0
        def solve(remaining,previous,depth=0):
            nonlocal steps
            steps+=1
            if job and job.cancel:raise V.M.Cancelled()
            if remaining==0:return []
            if steps>6000 or depth>150:return None
            key=(remaining,previous)
            if key in failed:return None
            used=(end-start)-remaining
            eligible=[aid for aid in assets if aid!=previous and (lengths[aid]<=remaining or state.get('ajustar_janela') and start+used+lengths[aid]<=bound)]
            eligible.sort(key=lambda aid:(usage.get(aid,0)+local.get(aid,0),screen.get(aid,0)+local.get(aid,0)*lengths[aid],rank[aid]))
            for aid in eligible:
                length=lengths[aid]
                if length>=remaining:
                    if aid==next_asset:continue
                    return [aid]
                local[aid]=local.get(aid,0)+1;tail=solve(remaining-length,aid,depth+1);local[aid]-=1
                if tail is not None:return [aid]+tail
            failed.add(key);return None
        if state.get('modo_takes')=='encaixar':
            picks=[];remaining=end-start;previous=last;temp_usage=dict(usage)
            while remaining>0:
                if job and job.cancel:raise V.M.Cancelled()
                eligible=[aid for aid in assets if aid!=previous and not (lengths[aid]>=remaining and aid==next_asset)]
                if not eligible:picks=None;break
                eligible.sort(key=lambda aid:(temp_usage.get(aid,0),screen.get(aid,0),rank[aid]));pick=eligible[0];picks.append(pick);temp_usage[pick]=temp_usage.get(pick,0)+1;remaining-=min(remaining,lengths[pick]);previous=pick
        else:picks=solve(end-start,last)
        if picks is None:
            issues.append({'mention':row['id'],'code':'variedade' if state.get('modo_takes')=='encaixar' else 'duracao','inicio_ms':row['start'],'fim_ms':row['end'],'error':'Não há combinação de vídeos completos para esta janela sem repetir em sequência. Escolha vídeos compatíveis, ajuste os tempos ou ative “Permitir estender a janela visual”. Nenhum vídeo foi cortado ou congelado.'});continue
        cursor=start
        for aid in picks:
            asset=assets[aid];length=min(lengths[aid],end-cursor) if state.get('modo_takes')=='encaixar' else lengths[aid];segments.append({'mention':row['id'],'asset':aid,'kit':asset.get('kit') if random_product else chosen_kit,'sorteio_produto':random_product,'aleatorio_autorizado':authorized,'kit_detectado':row.get('kit'),'kit_padrao_aplicado':fallback,'start_frame':cursor,'end_frame':cursor+length,'timeline_final':True,'timeline_fechada':state.get('modo_takes')=='inteiro','take_completo':length==lengths[aid]});usage[aid]=usage.get(aid,0)+1;screen[aid]=screen.get(aid,0)+length;cursor+=length;last=aid
    state.update(segments=segments,issues=issues,revisao_intervalos=review,fallbacks=[{'mention':r['id'],'kit_detectado':r.get('kit'),'motivo':'Potes aleatórios autorizados pelo usuário; conferir quantidade visual.'} for r in rows if V.random_authorized(state,r)],prepared=None,fps=fps,timeline_final=True,timeline_fechada=state.get('modo_takes')=='inteiro',coverage_mentions=[r for r in rows if r.get('fala')]);V.write(out,state);return state

def prepare(job,out,state):
    from . import visuais as V
    from .workflow import require_takes
    require_takes(out)
    expected=V.signature(state);assets={a['id']:a for a in state['assets']};result=[]
    for index,segment in enumerate(state['segments'],1):
        if job.cancel:raise V.M.Cancelled()
        asset=assets[segment['asset']];file=Path(asset['path']);stamp=[file.stat().st_size,file.stat().st_mtime_ns]
        if asset['kind']!='video' or stamp!=asset['stamp']:raise ValueError('Um vídeo mudou ou não está disponível. Leia a pasta novamente.')
        result.append(dict(segment,file=str(file.resolve()),source_original=True,stamp=stamp))
        job.step=f'Referenciando vídeo original {index} de {len(state["segments"])}';job.pct=index/len(state['segments'])
    require_takes(out)
    with T.LOCK:
        current=V.load(out)
        if V.signature(current)!=expected:raise ValueError('O plano mudou. Prepare os takes novamente.')
        current.pop('cobertura_desatualizada',None);current['prepared']={'signature':expected,'segments':result,'previews':{},'timeline_final':True};V.write(out,current)
    return {'segmentos':len(result),'reutilizados':len(result),'midias_originais':True,'originais_completos':all(r.get('take_completo') for r in result)}

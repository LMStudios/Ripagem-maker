"""Sobreposições por quantidade: biblioteca local, sorteio sem repetição e V2 no Premiere."""
import copy
import hashlib
import json
import math
import os
import random
import re
import subprocess
import uuid
from bisect import bisect_right, insort
from pathlib import Path
from . import ml_core as M,trocas as T
from .media_cache import metadata

VIDEO={'.mp4','.mov','.m4v','.webm','.mkv'}
IMAGE={'.png','.jpg','.jpeg','.webp'}
NUMBERS={'a':1,'an':1,'one':1,'um':1,'uma':1,'un':1,'una':1,'two':2,'dois':2,'duas':2,'dos':2,'three':3,'tres':3,'três':3,'four':4,'quatro':4,'cuatro':4,'five':5,'cinco':5,'six':6,'seis':6,'seven':7,'sete':7,'siete':7,'eight':8,'oito':8,'ocho':8,'nine':9,'nove':9,'nueve':9,'ten':10,'dez':10,'diez':10,'twelve':12,'doze':12,'doce':12}
NOUN=re.compile(r'^(bottles?|jars?|potes?|frascos?|garrafas?|botes?|boxes|box|caixas?|cajas?|kits?|packs?|packages?|pouches|pouch|patches|patch|adesivos?|units?|unidades?)$')
ADJ={'free','extra','more','bonus','additional','full','gratis','grátis','gratuito','gratuitos','grátis','adicional','adicionais'}

def path(out):return Path(out)/'trocas/visuais/plano.json'
def load(out):
    state=json.loads(path(out).read_text()) if path(out).exists() else {'root':'','assets':[],'mentions':[],'segments':[],'max_clip_s':6,'incluir':False,'prepared':None,'warnings':[],'sem_takes':False,'mapa_meses':{},'modo_takes':'inteiro','ajustar_janela':False}
    from .armazenamento import visual_margin_ms
    state['margem_visual_atual_ms']=visual_margin_ms()
    return state
def write(out,state):T.write(path(out),state)
def quantity(text):
    if str(text).isdigit():return int(text) if 1<=int(text)<=99 else None
    return NUMBERS.get(str(text).lower())
def probe(file):
    d=metadata(file,M.FFPROBE);v=next((s for s in d['streams'] if s['codec_type']=='video'),None)
    if not v:raise ValueError('Sem imagem/vídeo: '+Path(file).name)
    still=Path(file).suffix.lower() in IMAGE;duration=0 if still else float(v.get('duration') or d['format'].get('duration') or 0)
    if not still and (not math.isfinite(duration) or duration<=0):raise ValueError('Vídeo sem duração válida: '+Path(file).name)
    return {'kind':'imagem' if still else 'video','duration':duration,'width':v['width'],'height':v['height']}
def material_info(relative):
    parts=Path(relative).parts;name=Path(parts[-1]).stem.upper();normal=re.sub(r'[_–—-]+',' ',name)
    fmt=re.search(r'[-–—]\s*([VH])(?:\s|[-–—]|$)',name)
    generic=re.match(r'^(ESTEIRA|ESTOQUE|SETA|(?:[A-ZÀ-Ú]+\s+)*UGC)\b',normal)
    category='outro'
    product_generic=bool(re.match(r'^(?:PRODUTO|PRODUCT)(?:\s|$)',normal))
    if generic:
        word=generic.group(1);category='ugc' if 'UGC' in word else word.lower()
    quantity_pattern=r'\b(?:kit|pack)\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:potes?|bottles?|frascos?|units?|unidades?|caixas?|boxes|adesivos?|patches?|produtos?|ugc)\b'
    match=re.search(quantity_pattern,normal,re.I)
    if match:
        kit=quantity(match[1] or match[2])
        if kit:return {'kit':kit,'categoria':'ugc' if re.search(r'\bUGC\b',normal) else 'produto' if re.search(r'\bPRODUTOS?\b',normal) else 'potes','formato':fmt[1] if fmt else None,'identificacao':'nome'}
    if product_generic:return {'kit':None,'categoria':'produto','formato':fmt[1] if fmt else None,'identificacao':'sem_quantidade'}
    if generic:return {'kit':None,'categoria':category,'formato':fmt[1] if fmt else None,'identificacao':'sem_quantidade'}
    for part in reversed(parts[:-1]):
        text=re.sub(r'[_–—-]+',' ',part).strip()
        match=re.fullmatch(r'(?:kit\s*|pack\s*)?(\d{1,2})',text,re.I)
        if not match:
            named=re.search(quantity_pattern,text,re.I)
            if named and quantity(named[1] or named[2]):return {'kit':quantity(named[1] or named[2]),'categoria':'potes','formato':fmt[1] if fmt else None,'identificacao':'pasta'}
        if match and quantity(match[1]):return {'kit':quantity(match[1]),'categoria':'potes','formato':fmt[1] if fmt else None,'identificacao':'pasta'}
    return {'kit':None,'categoria':'outro','formato':fmt[1] if fmt else None,'identificacao':'desconhecido'}

def guess_kit(relative):return material_info(relative)['kit']

def visible_material(name):
    # AppleDouble (._video.mp4), arquivos ocultos e temporários não são takes.
    return not name.startswith(('.', '~$', '~')) and not name.lower().endswith(('.tmp','.part','.partial'))

def material_dirs(parent,dirs):
    return sorted(d for d in dirs if not d.startswith('.') and d not in {'__MACOSX','$RECYCLE.BIN','System Volume Information'} and not (Path(parent)/d).is_symlink())

def inventory(directory):
    directory=Path(directory).resolve();result=[]
    for parent,dirs,files in os.walk(directory):
        dirs[:]=material_dirs(parent,dirs)
        for name in sorted(files):
            if not visible_material(name):continue
            p=Path(parent)/name
            if p.suffix.lower() not in VIDEO|IMAGE or p.is_symlink():continue
            p=p.resolve()
            if p.is_file() and p.is_relative_to(directory):
                st=p.stat();result.append([str(p),st.st_size,st.st_mtime_ns])
            if len(result)>10000:raise ValueError('A biblioteca é muito grande. Escolha uma pasta menor.')
    return sorted(result)

def scan(job,out,root):
    directory=Path(root).expanduser()
    if not directory.is_absolute() or not directory.is_dir():raise ValueError('Escolha uma pasta existente com os materiais dos potes.')
    directory=directory.resolve();old=load(out);prior={a['path']:a for a in old['assets']};assets=[];seen=set();warnings=[];examined=0;files_snapshot=[]
    for parent,dirs,files in os.walk(directory):
        dirs[:]=material_dirs(parent,dirs)
        for name in sorted(files):
            if not visible_material(name):continue
            if job.cancel:raise M.Cancelled()
            examined+=1
            if examined>10000:raise ValueError('A pasta é muito grande. Use uma pasta com até 500 materiais e no máximo 10 mil arquivos.')
            if (Path(parent)/name).is_symlink():continue
            file=(Path(parent)/name).resolve()
            if file.suffix.lower() not in VIDEO|IMAGE or not file.is_relative_to(directory):continue
            job.step='Lendo material visual: '+file.name;job.progress={'tipo':'visuais','fase':'Lendo biblioteca','arquivos':len(assets),'indeterminado':True}
            try:
                stat=file.stat();stamp=[stat.st_size,stat.st_mtime_ns];files_snapshot.append([str(file),*stamp]);previous=prior.get(str(file),{})
                if previous.get('stamp')==stamp:item=dict(previous)
                else:
                    meta=probe(file)
                    if meta['kind']=='video' and meta['duration']<.1:raise ValueError('Material muito curto: '+file.name)
                    digest=hashlib.sha256()
                    with file.open('rb') as fp:
                        while chunk:=fp.read(1048576):
                            if job.cancel:raise M.Cancelled()
                            digest.update(chunk)
                    item={'id':digest.hexdigest()[:24],'path':str(file),'name':str(file.relative_to(directory)),'kit':guess_kit(file.relative_to(directory)),'stamp':stamp,**meta}
                info=material_info(file.relative_to(directory));item.update(name=str(file.relative_to(directory)),categoria=info['categoria'],formato=info['formato'],identificacao=info['identificacao']);item.setdefault('uso','produto' if item.get('kit') or info['categoria']=='produto' else 'depoimento' if info['categoria']=='ugc' else 'apoio')
                if previous.get('stamp')==stamp and 'kit_manual' not in previous and previous.get('kit') is not None and previous.get('kit')!=info['kit']:item['kit_manual']=True
                if not item.get('kit_manual'):item['kit']=info['kit']
                if item['id'] in seen:warnings.append('Cópia idêntica ignorada: '+item['name']);continue
            except M.Cancelled:raise
            except (ValueError,OSError,subprocess.TimeoutExpired) as e:
                warnings.append(str(e))
                continue
            if len(assets) >= 500:
                raise ValueError('A pasta é muito grande. Use uma pasta com até 500 materiais e no máximo 10 mil arquivos.')
            seen.add(item['id']);assets.append(item)
    if not assets:raise ValueError('Nenhum vídeo ou imagem compatível encontrado nesta pasta.')
    with T.LOCK:
        state=load(out);state.update(root=str(directory),assets=assets,segments=[],prepared=None,issues=[],warnings=warnings,inventory=sorted(files_snapshot));write(out,state)
    job.step=f'Biblioteca visual pronta: {len(assets)} materiais';return {'materiais':len(assets),'avisos':warnings}

def _basis_parts(out):
    raw=Path(out)/'transcricao_bruta.json';prices=Path(out)/'precos_TROCA.json'
    months=load(out).get('mapa_meses',{})
    return hashlib.sha256(raw.read_bytes()).hexdigest(),json.loads(prices.read_text()).get('mapa_qtd',{}) if prices.exists() else {},([months] if months else [])
def basis(out):
    raw,kits,months=_basis_parts(out)
    scope=['somente_valores',audio_windows(out)] if T.load(out).get('somente_valores') else []
    return T.digest(['base-2',raw,kits,*T.source_identity(T.source(out))]+months+scope)
def basis_ok(out,stored):
    """A base gravada continua válida, inclusive a calculada pela regra antiga (com o caminho do vídeo)."""
    if stored==basis(out):return True
    if T.load(out).get('somente_valores'):return False
    raw,kits,months=_basis_parts(out);source=T.source(out);stat=source.stat()
    return stored in {T.digest([raw,kits,text,stat.st_size,stat.st_mtime_ns]+months) for text in T.legacy_path_texts(source)}
def sentences(words):
    rows=[];current=[]
    for w in words:
        if current and w.get('speaker')!=current[-1].get('speaker'):rows.append(current);current=[]
        current.append(w);text=w['text']
        if re.search(r'[.?!]["\')\]]*$',text) and text.lower() not in {'dr.','mr.','mrs.','u.s.','vs.','etc.'}:rows.append(current);current=[]
    if current:rows.append(current)
    return rows

def detect(out):
    src=T.source(out);info=T.probe(src)
    if not info['video']:raise ValueError('Sobreposição visual exige o vídeo original. Este trabalho contém somente áudio.')
    raw=json.loads((Path(out)/'transcricao_bruta.json').read_text());prices=Path(out)/'precos_TROCA.json';mapping=json.loads(prices.read_text()).get('mapa_qtd',{}) if prices.exists() else {}
    rows=[];month_map=load(out).get('mapa_meses',{})
    for sentence in sentences(raw.get('words',[])):
        tokens=[]
        for word in sentence:
            for text in re.findall(r'[\w]+',word['text'].lower()):tokens.append((text,word))
        found=[]
        for i,(text,word) in enumerate(tokens):
            qty=quantity(text)
            if not qty:continue
            j=i+1
            while j<len(tokens) and tokens[j][0] in ADJ and j<i+4:j+=1
            probe_j=j
            if j+2<len(tokens) and tokens[j][0] in {'or','ou','o'} and quantity(tokens[j+1][0]):probe_j=j+2
            by_month=probe_j+1<len(tokens) and tokens[probe_j][0] in {'month','months','mes','meses','mês'} and tokens[probe_j+1][0] in {'package','packages','pack','packs','kit','kits','plan','plans','supply','treatment','protocol','pacote','pacotes','plano','planos','tratamento','protocolo'}
            if by_month:
                kit=month_map.get(str(qty))
                if not kit:continue
                found.append({'quantity_word':word,'noun_word':tokens[probe_j+1][1],'kit':kit,'original_kit':kit,'referencia_meses':qty});continue
            if j>=len(tokens) or not NOUN.fullmatch(tokens[j][0]):continue
            noun=tokens[j][0];family='kits' if re.match(r'(kit|pack|package|box|caixa)',noun) else 'frascos'
            new=mapping.get(f'{qty}|{family}');kit=quantity(str(new)) if new else qty
            found.append({'quantity_word':word,'noun_word':tokens[j][1],'kit':kit,'original_kit':qty})
        for i,item in enumerate(found):
            start=max(0,int(item['quantity_word']['start'])-150);end=min(round(info['duration']*1000),int(sentence[-1]['end'])+200)
            if i+1<len(found):end=min(end,max(start+1,int(found[i+1]['quantity_word']['start'])-150))
            if end-start<100:continue
            key=T.digest([item['quantity_word']['start'],item['noun_word']['end']])
            rows.append({'id':key,'start':start,'end':end,'kit':item['kit'],'original_kit':item['original_kit'],'text':' '.join(w['text'] for w in sentence),'selected':True,**({'referencia_meses':item['referencia_meses']} if item.get('referencia_meses') else {})})
    rows.sort(key=lambda r:r['start'])
    for first,second in zip(rows,rows[1:]):first['end']=min(first['end'],second['start'])
    with T.LOCK:
        from .editorial import visual_references
        if T.load(out).get('somente_valores'):rows=price_scope_rows(out,rows)
        else:rows+=visual_references(raw,rows)
        for row in rows:row['end']=min(row['end'],round(info['duration']*1000))
        rows.sort(key=lambda r:r['start'])
        state=load(out);state.update(mentions=rows,segments=[],prepared=None,issues=[],basis=basis(out));write(out,state)
    return state

def audio_windows(out, *, plan=None):
    """Only selection/timing affects coverage; voice approval does not."""
    if plan is None:
        plan = T.load(out)
    return sorted([[r['id'],r['inicio_ms'],r['fim_ms']] for r in plan.get('itens',[]) if r.get('aprovado')],key=lambda r:(r[1],r[2],r[0]))

def price_scope_rows(out, rows, *, windows=None):
    """Na otimização, nenhuma detecção visual amplia o escopo além das falas escolhidas."""
    if windows is None:
        windows = audio_windows(out)
    # Os inícios já estão em ordem. O maior fim até cada ponto permite
    # pular falas anteriores mesmo quando há janelas sobrepostas.
    furthest_ends = []
    for _, _, end in windows:
        furthest_ends.append(max(end, furthest_ends[-1]) if furthest_ends else end)
    result = []
    for row in rows:
        index = bisect_right(furthest_ends, row['start'])
        while index < len(windows):
            rid, start, end = windows[index]
            if start >= row['end']:
                break
            index += 1
            a,b=max(row['start'],start),min(row['end'],end)
            if b<=a:continue
            base=row.get('preco_base_id',row['id'])
            result.append(dict(row,id=T.digest(['visual_preco',base,rid]),preco_base_id=base,preco_fala=rid,start=a,end=b))
    return result

def _covered_mentions(out, state, plan, policy):
    rows=[dict(r) for r in state['mentions'] if r['selected']]
    prices = bool(plan.get('somente_valores'))
    windows = audio_windows(out, plan=plan) if prices or state.get('cobrir_falas') else []
    if prices:
        rows = price_scope_rows(out, rows, windows=windows)
    if not state.get('cobrir_falas'):return rows
    # Quantity/manual intervals take priority. Fill only their uncovered gaps.
    occupied=sorted((r['start'],r['end']) for r in rows)
    from .armazenamento import visual_margin_ms
    from . import montagem as MT
    margin = visual_margin_ms()
    info = T.probe(T.source(out))
    duration = round(info['duration'] * 1000)
    first = 0 if prices else policy['primeira_mencao_ms']
    previous = 0
    original_texts = {r['id']: r['original'] for r in plan.get('itens', []) if 'original' in r}
    for rid,start,end in windows:
        left=MT.mute_start(round(start/1000*info['fps']),round(previous/1000*info['fps']),info['fps'])/info['fps']*1000;previous=end
        # Adaptações anteriores à apresentação continuam apenas marcadas.
        if first is not None and end>first:
            if start>=first:start=max(first,round(left)-margin)
            end=min(duration,end+margin)
        gaps=[(start,end)]
        for a,b in occupied:
            if b <= start:
                continue
            if a >= end or not gaps:
                break
            gaps=[piece for x,y in gaps for piece in ((x,min(y,a)),(max(x,b),y)) if piece[1]>piece[0]]
        for i,(a,b) in enumerate(gaps):
            rows.append({'id':f'fala_{rid}_{i}','start':a,'end':b,'kit':None,'selected':True,'text':original_texts.get(rid,'Cobertura da fala substituída'),'categoria_alvo':'produto','fala':rid})
        insort(occupied, (start,end))
    # As falas anteriores à 1ª menção viram só marcadores no passo seguinte.
    # Não podem retirar a cobertura de um rótulo já aprovado pela detecção.
    if prices:return sorted(rows,key=lambda r:(r['start'],r['end']))
    actual_occupied=[(max(a,first),b) for a,b in occupied if first is not None and b>first]
    return old_product_rows(out,rows,actual_occupied,duration=duration,margin=margin)

BRIDGE_MS=500

def old_product_windows(sightings,duration,margin):
    """Estende aparições confirmadas e une regiões vizinhas que receberiam o mesmo produto."""
    windows=[]
    for sighting in sightings:
        extra=0 if sighting.get('ajustado') else margin
        start=max(sighting.get('limite_inicio_ms',0),sighting['start']-extra)
        end=min(duration,sighting['end']+extra)
        if end>start:
            windows.append(dict(sighting,start=start,end=end))
    joined=[]
    for row in sorted(windows,key=lambda r:(r['start'],r['end'])):
        if joined and row['start']<=joined[-1]['end']:
            joined[-1]['end']=max(joined[-1]['end'],row['end'])
        else:
            joined.append(row)
    return joined


def old_product_rows(out,rows,occupied,*,duration,margin):
    """Produto antigo na imagem: prioridade mais baixa, só nas frestas; fecha lacunas curtas ao lado."""
    from . import deteccao_visual as DV
    for row in old_product_windows(DV.coverage_rows(out),duration,margin):
        gaps=[(row['start'],row['end'])]
        for a,b in occupied:
            if b<=row['start']:continue
            if a>=row['end'] or not gaps:break
            gaps=[piece for x,y in gaps for piece in ((x,min(y,a)),(max(x,b),y)) if piece[1]>piece[0]]
        for i,(a,b) in enumerate(gaps):
            if b>a:rows.append(dict(row,id=row['id']+'_'+str(i),start=a,end=b))
    rows=sorted(rows,key=lambda r:(r['start'],r['end']))
    # Uma fresta de poucos quadros mostraria o pote antigo entre duas coberturas.
    for previous,current in zip(rows,rows[1:]):
        gap=current['start']-previous['end']
        if 0<gap<=BRIDGE_MS and (previous.get('produto_antigo') or current.get('produto_antigo')):
            if previous.get('produto_antigo') and not previous.get('ajustado'):
                previous['end']=current['start']
            elif current.get('produto_antigo') and not current.get('ajustado'):
                current['start']=max(previous['end'],current.get('limite_inicio_ms',0))
    return rows

_FIRST_CACHE={}

def first_product_mention(out, *, plan=None):
    """Limite pela menção literal ao produto/aliases, nunca pela forma de uso.

    Guardado por transcrição e nomes: a mesma consulta é usada várias vezes por tela.
    """
    from .mencoes import names, transcript_words, timed_spans
    if plan is None:
        plan = T.load(out)
    file=Path(out)/'transcricao_bruta.json';stat=file.stat()
    aliases=str(plan.get('produto_aliases',''))+','+str(plan.get('editorial',{}).get('aliases',''))
    key=(str(file.resolve()),stat.st_size,stat.st_mtime_ns,plan.get('produto'),aliases)
    if key in _FIRST_CACHE:return _FIRST_CACHE[key]
    words=transcript_words(json.loads(file.read_text()))
    hits=timed_spans(words,names(plan['produto'],aliases),approximate=False,
                     field='text',time='start',end='end',max_pause=850)
    value=min(int(words[i]['start']) for i,_,_ in hits) if hits else None
    if len(_FIRST_CACHE)>64:_FIRST_CACHE.clear()
    _FIRST_CACHE[key]=value
    return value


def coverage_policy(out, *, plan=None):
    from .armazenamento import visual_margin_ms
    from . import montagem as MT
    from . import deteccao_visual as DV
    from .mencoes import names, compact
    if plan is None:
        plan = T.load(out)
    if plan.get('somente_valores'):
        return {'versao':3,'escopo':'somente_valores','primeira_mencao_ms':None,
                'margem_visual_ms':visual_margin_ms(),'margem_fala_ms':MT.margin_ms()}
    aliases=str(plan.get('produto_aliases',''))+','+str(plan.get('editorial',{}).get('aliases',''))
    policy={'versao':3,'primeira_mencao_ms':first_product_mention(out, plan=plan),'margem_visual_ms':visual_margin_ms(),'margem_fala_ms':MT.margin_ms(),
            'nomes':sorted(set(compact(n) for n in names(plan['produto'],aliases)))}
    # Só entra quando há aprovados: trabalhos sem detecção mantêm os takes já preparados.
    old=DV.coverage_signature(out)
    if old:policy.update(produto_antigo=old,margem_aparicoes_ms=policy['margem_visual_ms'])
    return policy

def covered_mentions(out,state):
    plan = T.load(out)
    policy = coverage_policy(out, plan=plan) if state.get('cobrir_falas') else None
    rows = _covered_mentions(out, state, plan, policy)
    if not state.get('cobrir_falas'):return rows
    first=policy['primeira_mencao_ms'];allowed=[];markers={}
    if policy.get('escopo')=='somente_valores':
        state.update(coverage_markers=[],coverage_policy=policy)
        return rows
    # Antes da apresentação do produto, preserva a imagem e marca a adaptação.
    for row in rows:
        # Produto antigo na imagem já vem recortado pela 1ª menção da detecção (inclui a legenda gravada).
        if row.get('produto_antigo'):
            allowed.append(row);continue
        if first is None or row['start']<first:
            end=row['end'] if first is None else min(row['end'],first)
            if end>row['start']:
                key=T.digest([row['start'],end]);markers[key]={'id':key,'start':row['start'],'end':end,'text':row.get('text',''),'motivo':'Adaptar modo de uso · sem potes antes da primeira menção'}
        if first is not None and row['end']>first:allowed.append(dict(row,start=max(row['start'],first)))
    state['coverage_markers']=list(markers.values());state['coverage_policy']=policy
    return allowed

def refresh_coverage(out,state):
    if not state.get('cobrir_falas'):
        return state
    plan = T.load(out)
    current = audio_windows(out, plan=plan)
    policy = coverage_policy(out, plan=plan)
    if state.get('audio_windows') != current or state.get('coverage_policy') != policy:
        state.update(audio_windows=current,coverage_policy=policy,segments=[],prepared=None,issues=[],coverage_markers=[],manual_markers=[],cobertura_desatualizada=True)
    return state


def current_state(out):
    """Reabrir ou editar as falas reflete imediatamente a nova base visual."""
    with T.LOCK:
        state=load(out)
        before=T.digest(state)
        refresh_coverage(out,state)
        if T.digest(state)!=before:write(out,state)
        return state


def signature(state):
    values=[state['assets'],state['mentions'],float(state['max_clip_s']),state['segments'],state.get('modo_takes','recortes'),state.get('ajustar_janela',False),state.get('kit_sem_quantidade'),state.get('aleatorios_autorizados',{}),state.get('manual_markers',[])]
    if state.get('cobrir_falas'):values.extend([state.get('audio_windows'),state.get('coverage_policy'),state.get('coverage_markers')])
    return T.digest(values)
def save(out,body):
    with T.LOCK:
        state=load(out);before=signature(state);by_asset={a['id']:a for a in state['assets']};by_row={r['id']:r for r in state['mentions']};duration=round(T.probe(T.source(out))['duration']*1000)
        for change in body.get('assets',[]):
            role=change.get('uso')
            if role is not None:
                if role not in ('produto','apoio','depoimento'):raise ValueError('Uso do material inválido.')
                if change.get('id') in by_asset:by_asset[change['id']]['uso']=role
            if change['id'] not in by_asset:raise ValueError('Material desconhecido. Leia a biblioteca novamente.')
            kit=change.get('kit');old_kit=by_asset[change['id']]['kit'];by_asset[change['id']]['kit']=None if kit in ('',None,0,'0') else quantity(str(kit))
            if kit not in ('',None,0,'0') and not by_asset[change['id']]['kit']:raise ValueError('A quantidade do kit deve ser um inteiro entre 1 e 99.')
            if old_kit!=by_asset[change['id']]['kit']:by_asset[change['id']]['kit_manual']=True
        for change in body.get('mentions',[]):
            row=by_row.get(change['id'])
            if not row:raise ValueError('A lista de trechos foi recalculada. Reabra este trabalho para revisar os novos intervalos; seus ajustes não foram aplicados.')
            start,end=float(change['start']),float(change['end']);kit=quantity(str(change.get('kit','')))
            if not all(math.isfinite(v) for v in (start,end)) or not 0<=start<end<=duration or end-start<100:raise ValueError('Confira os tempos visuais: início e fim devem estar dentro da VSL.')
            selected=bool(change.get('selected'))
            if selected and not kit and not row.get('somente_visual'):raise ValueError('Informe o kit das menções selecionadas.')
            row.update(start=round(start),end=round(end),kit=kit,selected=selected)
        if 'mapa_meses' in body:
            clean={}
            for k,v in body['mapa_meses'].items():
                if str(v).strip() in ('','0'):continue
                if not str(k).isdigit() or not quantity(str(k)) or not str(v).isdigit() or not quantity(str(v)):raise ValueError('Informe a correspondência em números de 1 a 99.')
                clean[str(int(k))]=int(v)
            if clean!=state.get('mapa_meses',{}):state.update(mapa_meses=clean,mentions=[],segments=[],prepared=None,issues=[])
        mode=body.get('modo_takes',state.get('modo_takes','recortes'))
        if mode not in ('inteiro','encaixar','recortes'):raise ValueError('Modo de takes inválido.')
        default_kit=body.get('kit_sem_quantidade',state.get('kit_sem_quantidade'))
        if default_kit not in (None,'',0,'0') and (isinstance(default_kit,bool) or not str(default_kit).isdigit() or not quantity(str(default_kit))):raise ValueError('Escolha um kit padrão válido para falas sem quantidade.')
        state['kit_sem_quantidade']=None if default_kit in (None,'',0,'0') else int(default_kit)
        state['modo_takes']=mode;state['ajustar_janela']=bool(body.get('ajustar_janela',state.get('ajustar_janela',False)))
        state['mentions'].sort(key=lambda r:r['start']);limit=float(body.get('max_clip_s',state['max_clip_s']))
        if not math.isfinite(limit) or not 1<=limit<=30:raise ValueError('Duração máxima por material: de 1 a 30 segundos.')
        state['max_clip_s']=limit;state['sem_takes']=bool(body.get('sem_takes',state.get('sem_takes',False)));state['incluir']=bool(body.get('incluir',state['incluir'])) and not state['sem_takes']
        if signature(state)!=before:state.update(segments=[],prepared=None,issues=[])
        write(out,state);return state

def schedule(out,seed=None,job=None):
    with T.LOCK:
        state=refresh_coverage(out,load(out));fps=T.probe(T.source(out))['fps'];selected=covered_mentions(out,state)
        if not selected and not state.get('coverage_markers'):raise ValueError('Selecione ao menos uma menção visual.')
        if not basis_ok(out,state.get('basis')):raise ValueError('A transcrição ou as trocas de kits mudaram. Identifique as menções novamente.')
        if state.get('modo_takes') in ('inteiro','encaixar'):
            from .takes_completos import schedule as full_schedule
            return full_schedule(out,state,seed,job)
        for a,b in zip(selected,selected[1:]):
            if round(a['end']/1000*fps)>round(b['start']/1000*fps):raise ValueError('Os trechos visuais selecionados estão sobrepostos. Ajuste os tempos.')
        rng=random.Random(seed if seed is not None else uuid.uuid4().hex);bags={};last=None;segments=[];issues=[];usage={};screen_time={};fallbacks=[]
        for row in selected:
            local=[];cursor=round(row['start']/1000*fps);end=round(row['end']/1000*fps);choices=[a for a in state['assets'] if a['kit']==row['kit']]
            if row.get('produto_antigo'):
                # Sorteio entre takes de Produto de qualquer kit; apoio nunca cobre o produto automaticamente.
                choices=[a for a in state['assets'] if a.get('uso')=='produto']
            elif row['kit'] is None:
                desired='produto' if row.get('categoria_alvo')=='produto' or row.get('somente_visual') else 'apoio'
                preferred=[a for a in choices if a.get('uso','apoio')==desired]
                if len(preferred)>=2:choices=preferred
                elif desired=='produto' and choices:fallbacks.append({'mention':row['id'],'motivo':'Cobertura usa apoio porque faltam ao menos 2 takes genéricos classificados como produto.'})
            old_bags=copy.deepcopy(bags);old_rng=rng.getstate();old_usage=dict(usage);old_time=dict(screen_time);local_last=last
            try:
                if not choices:raise ValueError(('Produto antigo na imagem: classifique ao menos um take como Produto para cobrir este trecho.' if row.get('produto_antigo') else 'Apoio: adicione takes sem quantidade (ESTEIRA ou ESTOQUE) para cobrir as falas sem kit.' if row['kit'] is None else f'Kit {row["kit"]}: não há material associado.'))
                while cursor<end:
                    ids={a['id']:a for a in choices if a['id']!=local_last}
                    if not ids:raise ValueError(f'{"Apoio" if row["kit"] is None else "Kit "+str(row["kit"])}: há somente 1 material distinto disponível. Adicione outro material diferente para não repetir em sequência.')
                    # Usa todos os elegíveis antes de repetir, equilibrando também o tempo em tela.
                    least=min(usage.get(aid,0) for aid in ids)
                    pool=[aid for aid in ids if usage.get(aid,0)==least]
                    min_time=min(screen_time.get(aid,0) for aid in pool)
                    pool=[aid for aid in pool if screen_time.get(aid,0)==min_time]
                    pick=rng.choice(pool);asset=ids[pick]
                    cap=state['max_clip_s'] if asset['kind']=='imagem' else min(state['max_clip_s'],asset['duration'])
                    frames=min(end-cursor,max(1,math.floor(cap*fps+1e-6)))
                    tail=end-cursor-frames;minimum=max(1,round(.4*fps))
                    if 0<tail<minimum and frames>minimum-tail:frames-=minimum-tail
                    local.append({'mention':row['id'],'asset':pick,'kit':row['kit'],'start_frame':cursor,'end_frame':cursor+frames});usage[pick]=usage.get(pick,0)+1;screen_time[pick]=screen_time.get(pick,0)+frames;cursor+=frames;local_last=pick
                segments.extend(local);last=local_last
            except ValueError as e:issues.append({'mention':row['id'],'error':str(e)});bags=old_bags;usage=old_usage;screen_time=old_time;rng.setstate(old_rng)
        state.update(segments=segments,issues=issues,fallbacks=fallbacks,prepared=None,timeline_final=False,fps=fps,coverage_mentions=[r for r in selected if r.get("fala")]);write(out,state);return state

def schedule_job(job,out):
    job.step='Distribuindo takes completos e verificando as janelas';result=schedule(out,job=job);job.pct=1;job.step='Distribuição pronta' if not result.get('issues') else 'Ajuste as janelas visuais pendentes';return {'segmentos':len(result['segments']),'pendencias':len(result['issues'])}

def valid_prepared(out,require_include=True):
    state=load(out)
    if require_include and not state.get('incluir'):return []
    if state.get('cobrir_falas') and (state.get('audio_windows')!=audio_windows(out) or state.get('coverage_policy')!=coverage_policy(out)):raise ValueError('As falas selecionadas mudaram, ou mudaram os trechos aprovados do produto antigo, o limite de cobertura ou a margem visual. Prepare os takes novamente para cobrir todos os trechos.')
    if state.get('cobrir_falas') and not T.load(out).get('somente_valores') and first_product_mention(out) is None and not state.get('sem_takes'):
        raise ValueError('Não localizei a primeira menção ao produto. Confira o nome e suas variações em Falas antes de preparar os takes.')
    prepared=state.get('prepared')
    if not prepared or prepared.get('signature')!=signature(state) or not basis_ok(out,state.get('basis')):raise ValueError('Prepare os vídeos do plano visual atualizado antes de exportar.')
    if state.get('issues'):raise ValueError('Há menções visuais pendentes. Ajuste ou desmarque essas menções.')
    if not prepared['segments'] and not state.get('coverage_markers'):raise ValueError('Nenhuma sobreposição visual preparada.')
    for segment in prepared['segments']:
        file=(Path(out)/segment['file']).resolve()
        original=segment.get('source_original') and any(Path(a['path']).resolve()==file and a.get('kind')=='video' and a['stamp']==segment.get('stamp') for a in state['assets'])
        if original and file.is_file() and [file.stat().st_size,file.stat().st_mtime_ns]!=segment['stamp']:raise ValueError('Um take original foi alterado. Prepare novamente.')
        if (not original and not file.is_relative_to(Path(out).resolve())) or not file.is_file():raise ValueError('Um vídeo visual preparado não está mais disponível.')
    gaps=coverage_gaps(out,state,prepared['segments'])
    if gaps:
        first=gaps[0]['frestas'][0] if gaps[0].get('frestas') else gaps[0]
        clock=lambda s:f'{int(s//60)}:{s%60:05.2f}'
        premiere=f' · {clock(first["premiere_inicio_s"])} no Premiere' if 'premiere_inicio_s' in first else ''
        raise ValueError(f'Produto antigo na imagem: há {sum(len(g.get("frestas",[1])) for g in gaps)} fresta(s) sem take em V2. '
                         f'Primeira: {clock(first["inicio_ms"]/1000)} a {clock(first["fim_ms"]/1000)} do vídeo original{premiere}. '
                         'Em Takes → Conferir cobertura, ajuste o take, reprepare o intervalo ou marque para revisão no Premiere.')
    return prepared['segments']

def coverage_gaps(out,state,segments,*,include_marked=False):
    """Confere os takes reais, incluindo expansão e fechamento da timeline.

    Um texto aprovado não comprova que exista um clipe em V2. Exceções manuais
    só cobrem o intervalo autorizado com a assinatura atual do projeto. Cada
    fresta traz o início e o fim descobertos no vídeo original e no Premiere.
    """
    from . import deteccao_visual as D, montagem as MT, fechamento as FC
    from .armazenamento import visual_margin_ms
    plan=T.load(out)
    if plan.get('somente_valores'):return []
    sightings=D.coverage_rows(out)
    if not sightings:return []
    info=T.probe(T.source(out));fps=info['fps'];source_frames=round(info['duration']*fps)
    required=old_product_windows(sightings,round(info['duration']*1000),visual_margin_ms())
    final=bool(state.get('timeline_final') or (state.get('prepared') or {}).get('timeline_final'))
    approved=[r for r in plan['itens'] if r.get('aprovado') and r.get('audio',{}).get('fit')]
    changes=MT.edits(out,approved,info)
    closed=FC.windows(changes,fps) if state.get('timeline_fechada') or any(s.get('timeline_fechada') for s in segments) else []
    xml_closures=FC.windows(changes,fps)
    def position(frame):
        return FC.position(MT.shift(frame,changes),closed) if final else frame
    def premiere(frame):
        return FC.position(MT.shift(frame,changes),xml_closures)
    def source_of(pos):
        """Primeiro quadro do original que chega a esta posição (a conversão é crescente)."""
        if not final:return pos
        lo,hi=0,source_frames
        while lo<hi:
            mid=(lo+hi)//2
            if position(mid)<pos:lo=mid+1
            else:hi=mid
        return lo
    covered=[(s['start_frame'],s['end_frame']) for s in segments]
    for mark in state.get('manual_markers',[]):
        if mark.get('token')==manual_token(state,mark['id'],mark['start'],mark['end']):
            covered.append((position(round(mark['start']/1000*fps)),position(round(mark['end']/1000*fps))))
    marked=[] if include_marked else [m for m in state.get('pendencias_visuais',[]) if m.get('token')==gap_token(state,m['id'],m['start'],m['end'])]
    for mark in marked:
        covered.append((position(round(mark['start']/1000*fps)),position(round(mark['end']/1000*fps))))
    markers=D.approved_markers(out)
    result=[]
    for row in required:
        gaps=[(position(round(row['start']/1000*fps)),position(round(row['end']/1000*fps)))]
        for a,b in covered:
            gaps=[piece for lo,hi in gaps for piece in ((lo,min(hi,a)),(max(lo,b),hi)) if piece[1]>piece[0]]
        missing=sum(b-a for a,b in gaps)
        if not missing:continue
        pieces=[]
        for a,b in gaps:
            src_a,src_b=source_of(a),max(source_of(a)+1,source_of(b))
            start_ms,end_ms=round(src_a/fps*1000),round(src_b/fps*1000)
            pa,pb=(a,b) if final else (premiere(a),premiere(b))
            pieces.append({'id':T.digest(['fresta',row['id'],start_ms,end_ms]),'inicio_ms':start_ms,'fim_ms':end_ms,'quadros':b-a,
                           'premiere_inicio_s':round(pa/fps,3),'premiere_fim_s':round(pb/fps,3),
                           'aparicoes':[m['id'] for m in markers if m['inicio_ms']<end_ms+visual_margin_ms() and m['fim_ms']>start_ms-visual_margin_ms()]})
        result.append({'id':row['id'],'inicio_ms':row['start'],'fim_ms':row['end'],'quadros_sem_cobertura':missing,'frestas':pieces})
    return result


def gap_token(state,gap,start,end):
    return T.digest(['pendencia-visual-1',gap,start,end,state.get('coverage_policy'),state.get('audio_windows')])


def gap_report(out):
    """Frestas atuais entre as aparições aprovadas e os takes que ficarão em V2."""
    state=current_state(out)
    prepared=state.get('prepared') or {}
    marked=[m for m in state.get('pendencias_visuais',[]) if m.get('token')==gap_token(state,m['id'],m['start'],m['end'])]
    base={'preparado':bool(prepared),'marcadas':marked,'frestas':[],'fps':state.get('fps')}
    if not prepared or prepared.get('signature')!=signature(state):
        return base|{'mensagem':'Prepare os takes para conferir a cobertura real em V2.'}
    pieces=[p for row in coverage_gaps(out,state,prepared['segments']) for p in row['frestas']]
    return base|{'frestas':pieces,'quadros':sum(p['quadros'] for p in pieces)}


def mark_gaps(out,ids,authorized=False):
    """Marca frestas para revisão no Premiere: os takes e as falas aprovadas ficam como estão."""
    if authorized is not True:raise ValueError('Confirme que estes pontos serão resolvidos no Premiere.')
    with T.LOCK:
        state=current_state(out);prepared=state.get('prepared') or {}
        if not prepared or prepared.get('signature')!=signature(state):raise ValueError('Prepare os takes antes de marcar as frestas.')
        pieces={p['id']:p for row in coverage_gaps(out,state,prepared['segments']) for p in row['frestas']}
        chosen=[pieces[i] for i in ids if i in pieces]
        if not ids or len(chosen)!=len(set(ids)):raise ValueError('As frestas mudaram. Atualize a conferência.')
        marks={m['id']:m for m in state.get('pendencias_visuais',[])}
        for p in chosen:
            marks[p['id']]={'id':p['id'],'start':p['inicio_ms'],'end':p['fim_ms'],'premiere_inicio_s':p['premiere_inicio_s'],
                            'premiere_fim_s':p['premiere_fim_s'],'aparicoes':p['aparicoes'],'token':gap_token(state,p['id'],p['inicio_ms'],p['fim_ms'])}
        state['pendencias_visuais']=list(marks.values());write(out,state)
    return gap_report(out)


def unmark_gaps(out,ids):
    with T.LOCK:
        state=load(out);state['pendencias_visuais']=[m for m in state.get('pendencias_visuais',[]) if m['id'] not in set(ids)];write(out,state)
    return gap_report(out)


def reprepare_gap_job(job,out,ids):
    """Refaz só os takes das janelas com fresta; o restante da montagem é reaproveitado."""
    from .workflow import require_takes
    require_takes(out)
    with T.LOCK:
        state=current_state(out);prepared=state.get('prepared') or {}
        if not prepared:raise ValueError('Prepare os takes antes de refazer um intervalo.')
        pieces=[p for row in coverage_gaps(out,state,prepared['segments']) for p in row['frestas'] if p['id'] in set(ids)]
        if not pieces:raise ValueError('Esta fresta já não existe. Atualize a conferência.')
        fps=state['fps'];final=bool(prepared.get('timeline_final'))
        rows=covered_mentions(out,state)
        def overlaps(row,p):return row['start']<p['fim_ms'] and row['end']>p['inicio_ms']
        affected={r['id'] for r in rows for p in pieces if overlaps(r,p)}
        if not affected:raise ValueError('Nenhuma janela de takes cobre esta fresta. Ajuste o tempo da aparição ou marque para revisão no Premiere.')
        old=state.get('segments',[])
        job.step='Refazendo os takes do intervalo';job.pct=.1
        if state.get('modo_takes') in ('inteiro','encaixar'):
            from .takes_completos import schedule as full_schedule
            state['segments']=[s for s in old if s['mention'] not in affected];state['issues']=[]
            state=full_schedule(out,state,job=job,preserve=True)
        else:
            state=schedule(out,job=job)
            fresh=[s for s in state['segments'] if s['mention'] in affected]
            state['segments']=sorted([s for s in old if s['mention'] not in affected]+fresh,key=lambda s:s['start_frame'])
            write(out,state)
    if state.get('issues'):raise ValueError('O intervalo não tem takes compatíveis: '+' · '.join(dict.fromkeys(i['error'] for i in state['issues'])))
    result=prepare(job,out)
    report=gap_report(out)
    job.pct=1;job.step='Intervalo refeito · '+('sem frestas' if not report['frestas'] else f"{len(report['frestas'])} fresta(s) ainda abertas")
    return {'refeitas':len(affected),'frestas_restantes':len(report['frestas']),'preparo':result}


def prepare(job,out):
    out=Path(out).resolve()
    state=load(out)
    if state.get('cobrir_falas') and state.get('audio_windows')!=audio_windows(out):raise ValueError('As falas mudaram. Sorteie ou prepare automaticamente os takes novamente.')
    if not basis_ok(out,state.get('basis')):raise ValueError('A fonte ou as trocas de kits mudaram. Identifique e sorteie as menções novamente.')
    if (not state.get('segments') and not state.get('coverage_markers')) or state.get('issues'):raise ValueError('Sorteie os materiais e resolva as pendências antes de preparar.')
    if state.get('modo_takes') in ('inteiro','encaixar'):
        from .takes_completos import prepare as full_prepare
        return full_prepare(job,out,state)
    original=T.probe(T.source(out))
    if not original['video']:raise ValueError('Use o vídeo original para preparar sobreposições.')
    expected=signature(state);assets={a['id']:a for a in state['assets']};fps=original['fps'];directory=Path(out)/'trocas/visuais'/('prontos_'+uuid.uuid4().hex[:8]);directory.mkdir(parents=True)
    result=[];total=len(state['segments']);reused=0
    index_path=path(out).parent/'render_index.json'
    try:index=json.loads(index_path.read_text())
    except (OSError,ValueError):index={}
    if not isinstance(index,dict):index={}
    for i,segment in enumerate(state['segments']):
        if job.cancel:raise M.Cancelled()
        asset=assets[segment['asset']];file=Path(asset['path'])
        if not file.is_file() or [file.stat().st_size,file.stat().st_mtime_ns]!=asset['stamp']:raise ValueError('Um material mudou. Leia a biblioteca e sorteie novamente: '+asset['name'])
        frames=segment['end_frame']-segment['start_frame']
        key=T.digest(['v2-render-1',asset['id'],asset['stamp'],frames,fps,original['width'],original['height']])
        cached=index.get(key);target=(Path(out)/cached).resolve() if isinstance(cached,str) else None
        usable=target is not None and target.is_relative_to(Path(out).resolve()) and target.is_file()
        if usable:
            try:usable=abs(probe(target)['duration']-frames/fps)<=max(.002,.1/fps)
            except (ValueError,OSError):usable=False
        label='Apoio' if segment['kit'] is None else 'Kit '+str(segment['kit'])
        job.step=f'Preparando visual {i+1} de {total} · {label}';job.pct=i/total
        job.progress={'tipo':'visuais','fase':'Preparando vídeos em tela inteira','processadas':i,'total':total,'reutilizadas':reused,'indeterminado':False}
        if usable:reused+=1
        else:
            target=directory/f'{i+1:03d}_{"APOIO" if segment["kit"] is None else "KIT_"+str(segment["kit"])}_V2.mp4'
            temporary=target.with_suffix('.partial.mp4');cmd=[M.FFMPEG,'-y','-v','error']
            if asset['kind']=='imagem':cmd+=['-loop','1','-framerate',str(fps)]
            cmd+=['-i',str(file),'-an','-vf',f'fps={fps:.8f},scale={original["width"]}:{original["height"]}:force_original_aspect_ratio=increase,crop={original["width"]}:{original["height"]},setsar=1,tpad=stop_mode=clone:stop_duration=0.1,trim=end_frame={frames},setpts=N/({fps:.8f}*TB)','-r',str(fps),'-fps_mode','cfr','-frames:v',str(frames),'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(temporary)]
            try:
                M.run_proc(job,cmd);check=probe(temporary)
                if abs(check['duration']-frames/fps)>max(.002,.1/fps):raise ValueError('O material não cobriu o intervalo inteiro. Confira: '+asset['name'])
                temporary.replace(target)
            finally:
                if temporary.exists():temporary.unlink()
            index[key]=str(target.relative_to(out))
            # Save incrementally: a cancellation does not discard completed work.
            T.write(index_path,dict(list(index.items())[-512:]))
        result.append(segment|{'file':str(target.relative_to(out)),'render_key':key})
    with T.LOCK:
        current=load(out)
        if signature(current)!=expected:raise ValueError('O plano visual mudou durante o preparo. Prepare novamente.')
        current.pop('cobertura_desatualizada',None);current['prepared']={'signature':expected,'segments':result,'previews':{}};write(out,current)
    job.step='Vídeos visuais preparados para a trilha V2';job.progress={'tipo':'visuais','fase':'Vídeos prontos','processadas':total,'total':total,'reutilizadas':reused,'indeterminado':False};return {'segmentos':total,'reutilizados':reused}

def preview(job,out,mention):
    # Sem preparo, 'prepared' fica nulo: a prévia pede o preparo em vez de quebrar.
    if (load(out).get('prepared') or {}).get('timeline_final'):
        result=T.preview_job(job,out)
        with T.LOCK:
            state=load(out);state['prepared']['previews'][mention]=result['arquivo'];write(out,state)
        return {'arquivo':result['arquivo']}
    segments=[s for s in valid_prepared(out,False) if s['mention']==mention]
    if not segments:raise ValueError('Menção sem vídeos preparados.')
    state=load(out);expected=state['prepared']['signature'];fps=state['fps'];start=segments[0]['start_frame']/fps;duration=(segments[-1]['end_frame']-segments[0]['start_frame'])/fps
    target=Path(out)/'trocas/visuais'/('previa_'+uuid.uuid4().hex[:8]+'.mp4');cmd=[M.FFMPEG,'-y','-v','error']
    for segment in segments:cmd+=['-i',str(Path(out)/segment['file'])]
    cmd+=['-ss',str(start),'-t',str(duration),'-i',str(T.source(out))]
    filters=[]
    for i in range(len(segments)):filters.append(f'[{i}:v:0]setpts=PTS-STARTPTS[v{i}]')
    filters.append(''.join(f'[v{i}]' for i in range(len(segments)))+f'concat=n={len(segments)}:v=1:a=0[v]')
    cmd+=['-filter_complex',';'.join(filters),'-map','[v]','-map',f'{len(segments)}:a:0','-t',str(duration),'-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-movflags','+faststart',str(target)]
    job.step='Gerando prévia visual com o áudio original';M.run_proc(job,cmd)
    with T.LOCK:
        current=load(out)
        if not current.get('prepared') or current['prepared']['signature']!=expected:raise ValueError('O plano mudou. Gere a prévia novamente.')
        current['prepared']['previews'][mention]=str(target.relative_to(out));write(out,current)
    job.step='Prévia visual pronta (áudio original)';return {'arquivo':str(target.relative_to(out))}

def add(out,body):
    with T.LOCK:
        state=load(out);start=float(body['start']);end=float(body['end']);kit=quantity(str(body['kit']));info=T.probe(T.source(out));duration=info['duration']*1000
        if not info['video']:raise ValueError('Use o vídeo original para marcar sobreposições.')
        if not kit or not all(math.isfinite(t) for t in (start,end)) or not 0<=start<end<=duration or end-start<100:raise ValueError('Confira o kit e os tempos do trecho manual.')
        state['mentions'].append({'id':'manual_'+uuid.uuid4().hex[:16],'start':round(start),'end':round(end),'kit':kit,'original_kit':None,'text':'Trecho visual adicionado manualmente','selected':True})
        state['mentions'].sort(key=lambda r:r['start']);state.update(segments=[],prepared=None,issues=[],basis=basis(out));write(out,state);return state

def replace_segment(out,body):
    """Troca só um take, preservando os tempos e a regra de não repetição."""
    with T.LOCK:
        state=load(out);index=int(body['index']);segments=state.get('segments',[])
        if not 0<=index<len(segments):raise ValueError('Take não encontrado. Atualize o plano.')
        if not basis_ok(out,state.get('basis')):raise ValueError('A fonte ou as trocas mudaram. Identifique as menções novamente.')
        segment=segments[index];fps=state['fps'];frames=segment['end_frame']-segment['start_frame']
        excluded={segments[i]['asset'] for i in (index-1,index+1) if 0<=i<len(segments)}
        eligible=[a for a in state['assets'] if (a.get('uso')=='produto' if segment.get('sorteio_produto') else a['kit']==segment['kit']) and a['id'] not in excluded and ((round(a['duration']*fps)==frames if state.get('modo_takes')=='inteiro' else round(a['duration']*fps)>=frames) if state.get('modo_takes') in ('inteiro','encaixar') and a['kind']=='video' else state.get('modo_takes') not in ('inteiro','encaixar')) and math.floor((state['max_clip_s'] if a['kind']=='imagem' else a['duration'] if state.get('modo_takes') in ('inteiro','encaixar') else min(state['max_clip_s'],a['duration']))*fps+1e-6)>=frames]
        choice=body.get('asset')
        if not choice:
            eligible=[a for a in eligible if a['id']!=segment['asset']]
            if not eligible:raise ValueError('Não há outro take deste kit com duração suficiente sem repetir o vizinho.')
            choice=random.choice(eligible)['id']
        if not any(a['id']==choice for a in eligible):raise ValueError('Escolha um take do mesmo kit, com duração suficiente e diferente dos vizinhos.')
        if choice!=segment['asset']:
            segment['asset']=choice
            if segment.get('sorteio_produto'):segment['kit']=next(a.get('kit') for a in eligible if a['id']==choice)
            state['prepared']=None;write(out,state)
        return state

def automatic(job,out,root='',max_clip_s=6):
    """Encadeia o preparo local; reaproveita ajustes e interrompe em pendências."""
    def phase(text):
        if job.cancel:raise M.Cancelled()
        job.step=text
    state=load(out);root=str(root).strip() or state.get('root','')
    if not root:raise ValueError('Escolha a pasta dos takes antes de preparar automaticamente.')
    current_files=inventory(root) if Path(root).is_dir() else []
    old_files=state.get('inventory') or sorted([[a['path'],*a['stamp']] for a in state['assets']])
    if not state['assets'] or Path(root).resolve()!=Path(state.get('root') or '.').resolve() or current_files!=old_files or (not state.get('prepared') and any('identificacao' not in a for a in state['assets'])):
        phase('1/4 · Lendo a biblioteca de takes');scan(job,out,root);state=load(out)
    if not state['assets']:raise ValueError('A pasta não contém imagens ou vídeos compatíveis.')
    phase('2/4 · Identificando as menções')
    if not basis_ok(out,state.get('basis')):
        if state['mentions'] and not T.load(out).get('somente_valores'):raise ValueError('A transcrição ou os kits mudaram. Identifique as menções novamente antes de continuar.')
        state=detect(out)
    state=save(out,{'max_clip_s':max_clip_s,'incluir':True,'sem_takes':False})
    state['cobrir_falas']=True;state=refresh_coverage(out,state);write(out,state)
    if state['coverage_policy'].get('escopo')!='somente_valores' and state['coverage_policy']['primeira_mencao_ms'] is None:
        raise ValueError('Não localizei a primeira menção ao produto. Confira o nome e suas variações em Falas antes de preparar os takes.')
    if not covered_mentions(out,state) and not state.get('coverage_markers'):raise ValueError('Selecione as falas ou identifique as menções antes de preparar os takes.')
    phase('3/4 · Distribuindo os takes sem repetição')
    if not state.get('segments') or state.get('issues'):state=schedule(out,job=job)
    if state.get('issues'):raise ValueError('Há menções sem takes suficientes: '+ ' · '.join(dict.fromkeys(i['error'] for i in state['issues'])))
    phase('4/4 · Preparando os takes em tela inteira')
    try:valid_prepared(out)
    except ValueError:prepare(job,out)
    state=load(out);state.pop('cobertura_desatualizada',None);write(out,state);job.pct=1;job.step='Plano visual pronto — somente preços e kits selecionados' if T.load(out).get('somente_valores') else 'Plano visual pronto — takes após a primeira menção e adaptações anteriores marcadas'
    return {'mentions':len([r for r in state['mentions'] if r['selected']]),'segments':len(state['segments']),'falas_cobertas':len(state.get('audio_windows',[])),'takes_apoio':sum(s['kit'] is None for s in state['segments'])}


def manual_token(state,mention,start,end):
    return T.digest([mention,start,end,state.get('coverage_policy'),state.get('audio_windows')])

def manual_authorized(state,row):
    token=manual_token(state,row['id'],row['start'],row['end'])
    return any(m.get('token')==token for m in state.get('manual_markers',[]))

def mark_manual(out,mentions,authorized=False):
    """Exceção explícita e limitada às pendências atuais; mantém os takes resolvidos."""
    from .workflow import require_takes
    require_takes(out)
    if authorized is not True:raise ValueError('Confirme o ajuste manual destes pontos no Premiere.')
    with T.LOCK:
        state=current_state(out)
        chosen=set(mentions);issues=[i for i in state.get('issues',[]) if i['mention'] in chosen]
        if not chosen or {i['mention'] for i in issues}!=chosen:raise ValueError('As pendências mudaram. Confira os intervalos novamente.')
        markers={m['id']:m for m in state.get('manual_markers',[])}
        for i in issues:
            markers[i['mention']]={'id':i['mention'],'start':i['inicio_ms'],'end':i['fim_ms'],
                'text':'Cobertura de produto pendente: revisar este intervalo no Premiere.',
                'motivo':i['error'],'manual':True,
                'token':manual_token(state,i['mention'],i['inicio_ms'],i['fim_ms'])}
        state.update(manual_markers=list(markers.values()),issues=[i for i in state['issues'] if i['mention'] not in chosen],prepared=None)
        write(out,state)
        return state


def random_token(row):return T.digest([row['id'],row['start'],row['end'],row.get('kit'),row.get('text','')])
def random_authorized(state,row):return state.get('aleatorios_autorizados',{}).get(row['id'])==random_token(row)

def fill_random_job(job,out,mentions,expected):
    from .workflow import require_takes
    from .takes_completos import schedule as full_schedule
    require_takes(out)
    with T.LOCK:
        state=load(out)
        if signature(state)!=expected:raise ValueError('Os takes mudaram. Confira o aviso e autorize novamente.')
        if state.get('modo_takes') not in ('inteiro','encaixar'):raise ValueError('Use o modo Vídeos originais para preencher com vídeos de potes.')
        if not any(a['kind']=='video' and a.get('uso')=='produto' for a in state['assets']):raise ValueError('Não há vídeos classificados como Produto. Confira os materiais antes de preencher.')
        pending={i['mention'] for i in state.get('issues',[])}
        if not mentions or not set(mentions)<=pending:raise ValueError('As pendências mudaram. Confira os avisos novamente.')
        if not basis_ok(out,state.get('basis')):raise ValueError('A transcrição mudou. Identifique e prepare os takes novamente.')
        rows={r['id']:r for r in covered_mentions(out,state)}
        if not set(mentions)<=rows.keys():raise ValueError('Uma janela pendente não está mais selecionada.')
        authorizations=state.setdefault('aleatorios_autorizados',{})
        for rid in mentions:authorizations[rid]=random_token(rows[rid])
        write(out,state)
    job.step='Preenchendo pendências com vídeos aleatórios de produto'
    state=full_schedule(out,state,job=job,preserve=True)
    if state.get('issues'):raise ValueError('Ainda há pendências: '+' · '.join(dict.fromkeys(i['error'] for i in state['issues'])))
    prepare(job,out);job.pct=1;job.step='Pendências preenchidas com potes aleatórios; confira as quantidades'
    return {'preenchidas':len(mentions),'segments':len(state['segments']),'aleatorio_autorizado':True}

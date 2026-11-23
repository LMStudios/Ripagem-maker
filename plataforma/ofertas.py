"""Adaptação local de três ofertas completas; não usa API nem aprova/gera vozes."""
import hashlib,json,re
from decimal import Decimal
from pathlib import Path
from . import trocas as T,otimizacao as OT
from .valores import INPUT_AMOUNT_PATTERN, ONES,TENS,currency,format_amount,input_amount

PT_NUM=dict(zip('um uma dois duas três tres quatro cinco seis sete oito nove dez'.split(),(1,1,2,2,3,3,4,5,6,7,8,9,10)))
NUM=r'(?:\d{1,2}|'+ '|'.join([*ONES,*TENS,*PT_NUM])+r')'
ANCHOR=re.compile(r'\b(?P<n>'+NUM+r')[ -](?:bottles?|jars?|pouches?)\s+(?:kit|pack|package|option)\b|\b(?:kit|pacote)\s+(?:de\s+)?(?P<pt>'+NUM+r')\s+(?:frascos?|potes?)\b|\b(?:full|complete)\s+(?P<month>'+NUM+r')[ -]month\s+supply\b',re.I)
BUY=re.compile(r'\b(?:buy|order|choose|select|start|offer|secure|purchase|kit|pack|compr|escolh|oferec|leve)\w*\b',re.I)
DIRECT_KIT=re.compile(r'\b(?:buy|order|choose|select|purchase|start with|compr[ae]|escolh[ae]|leve)\s+(?:the |a |o |os |as )?(?P<n>'+NUM+r')\s+(?:bottles?|jars?|pouches?|frascos?|potes?)\b',re.I)
TOTAL_START=re.compile(r'^(?:and\s+|or\s+|e\s+)?(?:(?:that|this|it)\s+(?:comes? to|totals?|adds? up to|works out to)\s+|(?:your |the |o )?total\b|(?:for |por )?(?:a |um )?total(?:ing|izando)?\b|in total\b|ao todo\b|no total\b)',re.I)
PRICE=re.compile(r'\b(?:that works out|comes? to|costs?|priced?|price|for|por|per bottle|a bottle|each|cada|custa|preço|total)\b',re.I)
TAIL=re.compile(r"^(?:less than the cost|it['’]s not as complete|\d+[ -]day protocol|but it['’]s still a great option)",re.I)
TRIPLE=re.compile(r'(?<![\w$.,+/−-])'+r'\s*/\s*'.join([INPUT_AMOUNT_PATTERN]*3)+r'(?![\w$+/]|[.,]\d)',re.I)

def config(body):
    demand=str(body.get('demanda','')).strip()
    triples=TRIPLE.findall(demand)
    if len(triples)!=4:raise ValueError('Use: 2/3/6 para 1/3/6 (59/39/29 - 59/117/174). Informe os três kits originais, os novos, o preço por frasco e o total.')
    values=[[v.strip() for v in t.split('/')] for t in triples]
    if not all(re.fullmatch(r'\d{1,2}',v) and 1<=int(v)<=99 for row in values[:2] for v in row):raise ValueError('As quantidades dos kits devem ser inteiras entre 1 e 99.')
    old,new=[[int(v) for v in row] for row in values[:2]]
    if len(set(old))!=3 or len(set(new))!=3:raise ValueError('Informe três kits diferentes, sem quantidades repetidas.')
    tiers=[];symbols=set()
    for source,quantity,unit,total in zip(old,new,*values[2:]):
        unit,unit_currency=input_amount(unit);total,total_currency=input_amount(total)
        symbols.update(s for s in (unit_currency,total_currency) if s)
        if Decimal(unit)*quantity!=Decimal(total):raise ValueError(f'Kit de {quantity}: {quantity} × {unit} deve ser igual ao total informado ({total}).')
        tiers.append({'original':source,'quantidade':quantity,'unitario':unit,'total':total})
    if len(symbols)>1:raise ValueError('Use uma única moeda para os três kits.')
    days=body.get('dias_por_frasco')
    if days in ('',None):days=None
    elif isinstance(days,bool) or not str(days).isdigit() or not 1<=int(days)<=365:raise ValueError('Dias por frasco: informe de 1 a 365, ou deixe vazio.')
    else:days=int(days)
    return {'demanda':demand,'kits':tiers,'dias_por_frasco':days,'moeda_informada':next(iter(symbols),None)}

def sentences(words):
    rows=[];cur=[]
    for w in words:
        if cur and (w.get('speaker')!=cur[-1].get('speaker') or w['start']-cur[-1]['end']>8000):rows.append(cur);cur=[]
        cur.append(w)
        if re.search(r'[.?!]["\x27)\]]*$',w['text']) and w['text'].lower() not in {'dr.','mr.','mrs.','ms.','sr.','sra.'}:rows.append(cur);cur=[]
    if cur:rows.append(cur)
    return [{'text':' '.join(w['text'] for w in row),'start':row[0]['start'],'end':row[-1]['end'],'speaker':str(row[0].get('speaker') or 'A')} for row in rows]

def qty(text):
    match=ANCHOR.search(text) or DIRECT_KIT.search(text)
    if not match or not BUY.search(text):return None
    token=next(v for v in match.groupdict().values() if v).lower()
    return int(token) if token.isdigit() else ONES.get(token,TENS.get(token,PT_NUM.get(token)))

def blocks(raw,price_pattern,price_key):
    rows=sentences(raw.get('words') or []);found=[];occupied=-1
    for index,start in enumerate(rows):
        count=qty(start['text'])
        if not count or index<=occupied:continue
        end=None
        for j in range(index,min(index+10,len(rows))):
            row=rows[j]
            if row['speaker']!=start['speaker'] or row['end']-start['start']>65000:break
            if j>index and (qty(row['text']) or row['start']-rows[j-1]['end']>8000):break
            prices=list(price_pattern.finditer(row['text']))
            if prices and (PRICE.search(row['text']) or prices[0].start()==0):end=j;break
        if end is None:continue
        price_end=end
        original_price=price_key(prices[-1])
        amounts=[price_key(m) for m in prices]
        currencies={currency(m) for m in prices}
        for j in range(end+1,min(end+4,len(rows))):
            row=rows[j]
            if row['speaker']!=start['speaker'] or row['start']-rows[j-1]['end']>2500 or qty(row['text']):break
            continuation=list(price_pattern.finditer(row['text']))
            if continuation and (TOTAL_START.search(row['text']) or re.search(r'\b(?:in total|total|ao todo)\b',row['text'],re.I) and continuation[0].start()==0):
                amounts.extend(price_key(m) for m in continuation)
                currencies.update(currency(m) for m in continuation)
            elif not TAIL.search(row['text']):break
            end=j
        occupied=end
        found.append({'id':T.digest([start['start'],rows[end]['end']]),'quantidade':count,'start':start['start'],'end':rows[end]['end'],'speaker':start['speaker'],
                      'text':' '.join(r['text'] for r in rows[index:end+1]),'antes_preco':' '.join(r['text'] for r in rows[index:price_end]),'frase_preco':rows[price_end]['text'],
                      'preco_detectado':original_price,'precos_detectados':list(dict.fromkeys(amounts)),'moedas':sorted(currencies)})
    return found

def duration_per_bottle(source):
    """Only infer from an explicit day-based treatment/supply in an offer heading."""
    pattern=re.compile(r'\b(?P<n>\d{1,4}|'+ '|'.join([*ONES,*TENS])+r')[ -]day\s+(?:treatment|supply|protocol)\b',re.I)
    candidates=set()
    for block in source:
        for match in pattern.finditer(block['antes_preco']):
            token=match['n'].lower();days=int(token) if token.isdigit() else ONES.get(token,TENS.get(token,0))
            quantity=block['quantidade']
            if days and days%quantity==0 and 1<=days//quantity<=365:candidates.add(days//quantity)
    return candidates.pop() if len(candidates)==1 else None

def template(product,tier,days,portuguese=False,currency_symbol='$'):
    q=tier['quantidade'];unit,total=(currency_symbol+format_amount(tier[key],currency_symbol) for key in ('unitario','total'))
    if portuguese:
        tail=f', para os primeiros {days*q} dias de uso' if days else ''
        return f'Para começar, oferecemos um kit de {q} '+('frasco' if q==1 else 'frascos')+f' de {product} por {unit} cada, totalizando {total}{tail}.'
    if q==1:
        tail=f', covering your first {days} days of treatment' if days else ''
        return f'And if you prefer to start with just the absolute basics, we offer a 1-bottle kit for {total}{tail}.'
    return f'The {q}-bottle kit of {product} costs {unit} per bottle, for a total of {total}.'

def rewritten(block,tier,product,days,currency_symbol='$'):
    portuguese=bool(re.search(r'\b(?:frasco|pote|preço|pacote)\w*\b',block['text'],re.I))
    before=block['antes_preco']
    if tier['original']!=tier['quantidade'] or not before:return template(product,tier,days,portuguese,currency_symbol)
    # Normalize the offer heading, preserving the pay/free split inside unchanged kits.
    before=ANCHOR.sub(lambda m:re.sub(r'\b'+NUM+r'\b',str(tier['quantidade']),m.group(0),count=1,flags=re.I),before,count=1)
    before=re.sub(r'\bninety-day\b','90-day',before,flags=re.I)
    unit,total=(currency_symbol+format_amount(tier[key],currency_symbol) for key in ('unitario','total'))
    price=f'O valor fica em {unit} por frasco, totalizando {total}.' if portuguese else f'That works out to {"just " if re.search(r"\bjust\b",block["frase_preco"],re.I) else ""}{unit} a bottle, for a total of {total}.'
    return before+' '+price

def fingerprint(out):
    plan=T.load(out);raw=Path(out)/'transcricao_bruta.json'
    return T.digest([hashlib.sha256(raw.read_bytes()).hexdigest(),[[r['id'],r['novo'],r['speaker'],r.get('aprovado'),r.get('audio')] for r in plan['itens']]])

def preview(out,body,price_pattern,price_key):
    if not OT.active(out):raise ValueError('Escolha Otimização de preços e kits no início.')
    cfg=config(body);base=fingerprint(out);plan=T.load(out);raw=json.loads((Path(out)/'transcricao_bruta.json').read_text())
    source=blocks(raw,price_pattern,price_key);product=plan.get('produto_novo') or plan['produto']
    tiers={r['original']:r for r in cfg['kits']};items=[];detected=set()
    currencies={c for b in source if b['quantidade'] in tiers for c in b['moedas']}
    if len(currencies)>1:raise ValueError('Encontrei reais e dólares nas ofertas. Confira os trechos e use as trocas avulsas para manter a moeda de cada fala.')
    cfg['moeda']=currency_symbol=next(iter(currencies),'$')
    if cfg['moeda_informada'] and currencies and cfg['moeda_informada']!=currency_symbol:
        raise ValueError('A moeda informada é diferente da oferta original. Confira o símbolo dos valores.')
    cfg['dias_origem']='informado' if cfg['dias_por_frasco'] else 'ausente'
    if cfg['dias_por_frasco'] is None:
        cfg['dias_por_frasco']=duration_per_bottle([b for b in source if b['quantidade'] in tiers])
        if cfg['dias_por_frasco']:cfg['dias_origem']='transcricao'
    for block in source:
        if block['quantidade'] not in tiers:continue
        tier=tiers[block['quantidade']];detected.add(tier['quantidade'])
        items.append({**block,'novo':rewritten(block,tier,product,cfg['dias_por_frasco'],currency_symbol),'kit_novo':tier['quantidade'],'ofertas_incluidas':[tier['quantidade']]})
    if not items:raise ValueError('Não encontrei blocos completos de kit e preço na transcrição disponível. Nenhum texto foi alterado. Confira se a parte da oferta foi transcrita.')
    missing=[tier for tier in cfg['kits'] if tier['quantidade'] not in detected]
    if missing:
        # Extend the last existing offer in place; the montage opens space for the added speech.
        last=items[-1];portuguese=bool(re.search(r'\b(?:frasco|pote|preço)\w*\b',last['text'],re.I))
        for tier in missing:
            last['novo']+=' '+template(product,tier,cfg['dias_por_frasco'],portuguese,currency_symbol)
            last['ofertas_incluidas'].append(tier['quantidade'])
    return {'config':cfg,'base':base,'blocos':items,'novas_ofertas':[t['quantidade'] for t in missing],
            'ofertas':[{**t,'identificada':t['quantidade'] in detected} for t in cfg['kits']],
            'observacao':'Ofertas sem fala própria são acrescentadas ao final do último bloco identificado. O XML abre espaço para a fala completa. Nenhuma voz foi gerada e os textos ainda precisam de aprovação.'}

def apply(out,result):
    with T.LOCK:
        if not OT.active(out):raise ValueError('O modo de otimização mudou. Nenhum texto foi aplicado.')
        if fingerprint(out)!=result['base']:raise ValueError('O trabalho mudou durante a adaptação. Tente novamente; as edições foram preservadas.')
        previous=T.load(out);T.write(Path(out)/'trocas'/('plano_antes_ofertas_'+T.digest(previous)+'.json'),previous)
        file=Path(out)/'precos_TROCA.json';saved=Path(out)/'trocas/ofertas.json'
        old_prices=file.read_bytes() if file.exists() else None
        old_offers=saved.read_bytes() if saved.exists() else None
        if old_prices is not None:T.write(Path(out)/'trocas'/('precos_antes_ofertas_'+hashlib.sha256(old_prices).hexdigest()[:20]+'.json'),json.loads(old_prices))
        phrases=[{'n':i+1,'start':r['start'],'end':r['end'],'text':r['text'],'novo':r['novo'],'speaker':r['speaker'],'revisar':[],'ofertas_incluidas':r['ofertas_incluidas']} for i,r in enumerate(result['blocos'])]
        try:
            T.write(file,{'frases':phrases,'modo':'blocos_oferta','config':result['config'],'mapa_precos':{},'mapa_qtd':{}})
            plan=T.build(out,previous['produto'],True)
            plan['modo_duracao']='expandir'
            by_time={(r['inicio_ms'],r['fim_ms']):r for r in plan['itens']}
            for block in result['blocos']:
                row=by_time.get((block['start'],block['end']))
                if row is not None:block['novo']=row['novo']
                block['sem_alteracao']=row is None
            T.write(T.plan_path(out),plan)
            T.write(saved,result)
        except Exception:
            T.write(T.plan_path(out),previous)
            for target,content in ((file,old_prices),(saved,old_offers)):
                if content is None:target.unlink(missing_ok=True)
                else:T.write(target,json.loads(content))
            raise
        return {**result,'plano':plan}

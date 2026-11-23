"""Correções textuais de SRT com estrutura e timecodes imutáveis."""
import difflib
import json
import re
from pathlib import Path

TC = r'\d{2,}:\d{2}:\d{2}[,.]\d{3}'
BLOCK = re.compile(r'(?m)^(?:\ufeff)?(?P<id>[ \t]*\d+[ \t]*)\r?\n(?P<tc>'+TC+r'[^\r\n]*?-->[^\r\n]*'+TC+r'[^\r\n]*)\r?\n(?P<body>.*?)(?=\r?\n[ \t]*\r?\n|\Z)',re.S)
PROFILE = Path(__file__).parent/'srt_perfil_golden_brain.json'

def plain(text):return ' '.join(text.split())

def millis(text):
    a,b,c,d=map(int,re.split('[:,.]',text))
    if b>=60 or c>=60:raise ValueError('Timecode SRT inválido.')
    return ((a*60+b)*60+c)*1000+d

def parse(text):
    cues=[];cursor=0
    for m in BLOCK.finditer(text):
        if text[cursor:m.start()].strip('\ufeff \t\r\n'):raise ValueError('Há conteúdo fora dos blocos SRT. Confira o arquivo.')
        times=re.findall(TC,m['tc'])
        if len(times)!=2:raise ValueError('Timecode inválido no bloco '+m['id'])
        start,end=map(millis,times)
        if end<start:raise ValueError('Fim anterior ao início no bloco '+m['id'])
        body=m['body'];tail=''
        while body.endswith(('\n','\r')):tail=body[-1]+tail;body=body[:-1]
        if not body.strip():raise ValueError('Legenda vazia no bloco '+m['id'])
        cues.append({'id':m['id'],'tc':m['tc'],'start':start,'end':end,'text':body,'a':m.start('body'),'b':m.end('body')-len(tail)})
        cursor=m.end()
    if not cues or text[cursor:].strip('\ufeff \t\r\n'):raise ValueError('Arquivo SRT inválido ou vazio.')
    return cues

def reflow(new,original):
    """Mantém a quantidade de linhas de cada bloco, sem produzir linhas vazias."""
    lines=re.split(r'\r?\n',original);words=new.split()
    if len(lines)==1:return new
    if len(words)<len(lines):raise ValueError('A troca deixaria uma linha vazia; revise manualmente.')
    counts=[max(1,len(x.split())) for x in lines];total=sum(counts);parts=[];cursor=0
    for i,count in enumerate(counts):
        end=len(words) if i==len(lines)-1 else max(cursor+1,min(len(words)-(len(lines)-i-1),round(sum(counts[:i+1])*len(words)/total)))
        parts.append(' '.join(words[cursor:end]));cursor=end
    return ('\r\n' if '\r\n' in original else '\n').join(parts)

def correct(text,items,reference=None,profile=False):
    cues=parse(text);original=[c['text'] for c in cues];current=original.copy();changes=[];pending=[]
    reference_changes=[]
    if reference:
        refs=parse(reference)
        if [(c['id'],c['tc']) for c in cues]!=[(c['id'],c['tc']) for c in refs]:
            raise ValueError('O SRT de referência deve ter os mesmos blocos e timecodes. Nenhum tempo será ajustado.')
        similarity=difflib.SequenceMatcher(None,plain(' '.join(original)).lower(),plain(' '.join(c['text'] for c in refs)).lower(),autojunk=False).ratio()
        if similarity<.7:raise ValueError('A referência parece pertencer a outro vídeo. Confira os arquivos.')
        reference_changes=[{'index':i,'before':c['text'],'after':r['text']} for i,(c,r) in enumerate(zip(cues,refs)) if c['text']!=r['text']]
    elif profile:
        if not PROFILE.exists():raise ValueError('Exemplo Golden Brain indisponível.')
        data=json.loads(PROFILE.read_text())
        if [[c['id'],c['tc']] for c in cues]!=data['estrutura']:
            raise ValueError('O exemplo Golden Brain só se aplica ao mesmo SRT, com os mesmos blocos e timecodes.')
        reference_changes=data['alteracoes']
    for row in reference_changes:
        i=row['index']
        if plain(current[i])==plain(row['after']):continue
        if plain(current[i]).casefold()!=plain(row['before']).casefold():
            pending.append({'bloco':cues[i]['id'],'motivo':'Texto diferente do exemplo; correção de referência não aplicada.'});continue
        try:current[i]=reflow(row['after'],current[i])
        except ValueError as e:pending.append({'bloco':cues[i]['id'],'motivo':str(e)})
    # Extrai apenas diferenças das frases confirmadas, mantendo o restante da legenda.
    rules=[]
    for item in items:
        if not item.get('novo'):continue
        if item.get('status') not in (None,'ok'):
            pending.append({'trecho':item.get('n'),'motivo':'Alinhamento incerto: troca não aplicada.'});continue
        before=item['text'].split();after=item['novo'].split()
        for op,a,b,c,d in difflib.SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
            if op=='equal':continue
            if op!='replace':
                pending.append({'trecho':item.get('n'),'motivo':'Inserção/remoção exige revisão para preservar os blocos.'});continue
            rules.append({'old':' '.join(before[a:b]),'new':' '.join(after[c:d]),'start':item.get('tl_in',item.get('start',0)),'end':item.get('tl_out',item.get('end',0)),'n':item.get('n')})
    for rule in rules:
        indices=[i for i,c in enumerate(cues) if c['start']<rule['end'] and c['end']>rule['start']]
        if not indices:
            pending.append({'trecho':rule['n'],'motivo':'Não há legendas no intervalo marcado.'});continue
        stream='';spans=[]
        for i in indices:
            if stream:stream+=' '
            a=len(stream);stream+=current[i];spans.append((a,len(stream),i))
        pattern=r'(?<!\w)'+r'\s+'.join(re.escape(w) for w in rule['old'].split())+r'(?!\w)'
        matches=list(re.finditer(pattern,stream,re.I))
        if not matches:
            new_pattern=r'(?<!\w)'+r'\s+'.join(re.escape(w) for w in rule['new'].split())+r'(?!\w)'
            if not re.search(new_pattern,stream,re.I):pending.append({'trecho':rule['n'],'motivo':'Texto antigo não encontrado no intervalo. Confira a fala e a legenda.','antigo':rule['old'],'novo':rule['new']})
            continue
        snapshot={i:current[i] for i in indices}
        for m in reversed(matches):
            touched=[(a,b,i) for a,b,i in spans if a<m.end() and b>m.start()]
            newwords=rule['new'].split()
            if any('<' in current[i] or '>' in current[i] for a,b,i in touched):
                pending.append({'trecho':rule['n'],'motivo':'Bloco com formatação HTML: revise a troca para preservar as tags.'});continue
            if len(newwords)<len(touched):
                pending.append({'trecho':rule['n'],'motivo':'Troca entre blocos deixaria uma legenda vazia. Revisão necessária.'});continue
            cursor=0
            for k,(a,b,i) in enumerate(touched):
                lo=max(0,m.start()-a);hi=min(b-a,m.end()-a)
                count=len(current[i][lo:hi].split())
                end=len(newwords) if k==len(touched)-1 else min(len(newwords)-(len(touched)-k-1),cursor+max(1,count))
                piece=' '.join(newwords[cursor:end]);cursor=end
                changed=current[i][:lo]+piece+current[i][hi:]
                current[i]=changed
        for i in indices:
            if current[i]!=snapshot[i]:
                try:current[i]=reflow(plain(current[i]),snapshot[i])
                except ValueError as e:
                    current[i]=snapshot[i];pending.append({'bloco':cues[i]['id'],'motivo':str(e)})
    output=text
    for i in reversed(range(len(cues))):
        if current[i]!=original[i]:
            output=output[:cues[i]['a']]+current[i]+output[cues[i]['b']:]
            changes.append({'bloco':cues[i]['id'],'timecode':cues[i]['tc'],'antes':original[i],'depois':current[i]})
    after=parse(output)
    if [(c['id'],c['tc']) for c in cues]!=[(c['id'],c['tc']) for c in after]:raise RuntimeError('Falha na verificação dos timecodes. Arquivo não exportado.')
    if [len(c['text'].splitlines()) for c in cues]!=[len(c['text'].splitlines()) for c in after]:raise RuntimeError('A correção alteraria as quebras de linha. Arquivo não exportado.')
    return output,{'blocos':len(cues),'alterados':len(changes),'timecodes_preservados':True,'alteracoes':list(reversed(changes)),'pendencias':pending}


def product_only(text,old,new,aliases=''):
    """Padroniza apenas nomes, em todo o SRT, sem reescrever frases."""
    if not old.strip() or not new.strip():raise ValueError('Informe produto antigo e grafia final do produto novo.')
    cues=parse(text)
    names=list(dict.fromkeys([old.strip()]+[a.strip() for a in re.split('[,;\n]',aliases) if a.strip()]+[new.strip()]))
    stream='';spans=[]
    for i,c in enumerate(cues):
        if stream:stream+=' '
        a=len(stream);stream+=c['text'];spans.append((a,len(stream),i))
    patterns=[r'(?<!\w)'+r'\s+'.join(re.escape(w) for w in name.split())+r'(?!\w)' for name in sorted(names,key=len,reverse=True)]
    matches=list(re.finditer('|'.join(patterns),stream,re.I));edits={};pending=[];oldhits=[]
    oldnorm={plain(x).casefold() for x in names[:-1] if plain(x).casefold()!=plain(new).casefold()}
    for m in matches:
        touched=[(a,b,i) for a,b,i in spans if a<m.end() and b>m.start()]
        if plain(m[0]).casefold() in oldnorm:
            oldhits.append({'blocos':[cues[i]['id'] for a,b,i in touched],'nome':plain(m[0]),'timecode':cues[touched[0][2]]['tc']})
        words=new.split()
        if len(words)<len(touched):
            pending.append({'bloco':cues[touched[0][2]]['id'],'motivo':'Nome dividido entre blocos: substituição deixaria um bloco vazio.'});continue
        proposed=[];cursor=0
        for k,(a,b,i) in enumerate(touched):
            lo=max(0,m.start()-a);hi=min(b-a,m.end()-a)
            oldpart=cues[i]['text'][lo:hi];count=len(oldpart.split())
            end=len(words) if k==len(touched)-1 else min(len(words)-(len(touched)-k-1),cursor+max(1,count))
            part=' '.join(words[cursor:end]);cursor=end
            try:part=reflow(part,oldpart)
            except ValueError:
                pending.append({'bloco':cues[i]['id'],'motivo':'Nome dividido entre linhas: revise para preservar a estrutura.'});proposed=[];break
            proposed.append((i,lo,hi,part))
        for i,lo,hi,part in proposed:edits.setdefault(i,[]).append((lo,hi,part))
    output=text;changes=[]
    for i in reversed(range(len(cues))):
        body=cues[i]['text']
        for lo,hi,part in sorted(edits.get(i,[]),reverse=True):body=body[:lo]+part+body[hi:]
        if body!=cues[i]['text']:
            output=output[:cues[i]['a']]+body+output[cues[i]['b']:]
            changes.append({'bloco':cues[i]['id'],'timecode':cues[i]['tc'],'antes':cues[i]['text'],'depois':body})
    after=parse(output)
    if [(c['id'],c['tc'],len(c['text'].splitlines())) for c in cues]!=[(c['id'],c['tc'],len(c['text'].splitlines())) for c in after]:raise RuntimeError('Falha na preservação da estrutura SRT.')
    remaining=[]
    flat=' '.join(c['text'] for c in after)
    for name in names[:-1]:
        if plain(name).casefold()==plain(new).casefold():continue
        pattern=r'(?<!\w)'+r'\s+'.join(re.escape(w) for w in name.split())+r'(?!\w)'
        if re.search(pattern,flat,re.I):remaining.append(name)
    return output,{'blocos':len(cues),'alterados':len(changes),'timecodes_preservados':True,'alteracoes':list(reversed(changes)),'pendencias':pending,'produto_antigo':old,'grafia_final':new,'mencoes_antigas':oldhits,'resquicios':remaining}

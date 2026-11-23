"""Local suggestions for product-form changes. Never invent doses or instructions."""
import re

FORMS={
 'spray':{'en':('spray','sprays'),'pt':('spray','sprays'),'es':('spray','sprays'),'pattern':r'sprays?|aeross[oó]is|aerossol|aerosoles?|borrifadas?|pulveriza[çc][oõ]es'},
 'patch':{'en':('patch','patches'),'pt':('adesivo','adesivos'),'es':('parche','parches'),'pattern':r'patch(?:es)?|adesivos?|parches?'},
 'dropper':{'en':('dropper','droppers'),'pt':('conta-gotas','conta-gotas'),'es':('gotero','goteros'),'pattern':r'droppers?|drops?|conta[- ]gotas|gotas?|goteros?'},
 'capsule':{'en':('capsule','capsules'),'pt':('cápsula','cápsulas'),'es':('cápsula','cápsulas'),'pattern':r'capsules?|c[áa]psulas?|pills?|tablets?|comprimidos?|pastillas?'},
 'powder':{'en':('powder','powder'),'pt':('pó','pó'),'es':('polvo','polvo'),'pattern':r'powder|p[óo]|polvo'},
 'gummy':{'en':('gummy','gummies'),'pt':('goma','gomas'),'es':('gomita','gomitas'),'pattern':r'gumm(?:y|ies)|gomas?|gomitas?'},
 'liquid':{'en':('liquid','liquid'),'pt':('líquido','líquido'),'es':('líquido','líquido'),'pattern':r'liquid|l[íi]quido'},
}

def normalize(config):
    c=config or {}
    if not c.get('ativo'):return {'ativo':False}
    source,target=c.get('origem'),c.get('destino')
    if source not in FORMS or target not in FORMS:raise ValueError('Escolha a forma original e a nova forma do produto.')
    if source==target:raise ValueError('A forma de origem e a de destino precisam ser diferentes.')
    before=str(c.get('uso_original','')).strip();after=str(c.get('uso_novo','')).strip()
    if before and not after:raise ValueError('Informe a instrução correta do produto novo.')
    if max(len(before),len(after))>1000:raise ValueError('Instrução de uso: máximo de 1000 caracteres.')
    route=str(c.get('via_uso','')).strip()
    if route not in ('','oral','ingerir','sublingual','cutanea'):raise ValueError('Escolha uma via de uso válida.')
    if route and ((target=='patch' and route!='cutanea') or (target not in ('patch','spray') and route=='cutanea')):raise ValueError('Confira a via de uso da forma selecionada.')
    description=str(c.get('descricao_nova','')).strip()
    if len(description)>2000:raise ValueError('Descrição confirmada: máximo de 2000 caracteres.')
    return {'ativo':True,'origem':source,'destino':target,'uso_original':before,'uso_novo':after,'descricao_nova':description,**({'via_uso':route} if route else {})}

FORM_PATTERNS={name:re.compile(r'(?<!\w)(?:'+form['pattern']+r')(?!\w)',re.I) for name,form in FORMS.items()}

def pattern(config):return FORM_PATTERNS[config['origem']]
def language(text,word):
    # Contexto da frase resolve nomes compartilhados (cápsula, líquido, goma).
    if re.search(r'\b(?:producto|presentaci[oó]n|nuestr[oa]s?|contienen|contiene|es|son|nuev[oa]s?|la|las)\b',text,re.I):return 'es'
    if re.search(r'\b(?:produto|apresenta[çc][aã]o|noss[oa]s?|cont[eê]m|você|seu|sua|seus|suas|é|nov[oa]s?|s[aã]o|est[aã]o|com|uma|um)\b',text,re.I):return 'pt'
    if re.search(r'\b(?:el|los|una|parche|parches|gotero|goteros|gomita|gomitas|polvo|pastillas?)\b',text,re.I):return 'es'
    if re.search(r'\b(?:aplique|tome|adesivos?|gotas?|c[áa]psulas?|comprimidos?|pó|l[íi]quido|gomas?)\b',text,re.I) and not re.fullmatch(r'capsules?',word,re.I):return 'pt'
    return 'en'
SKIN_ROUTE=re.compile(r'\b(?:transdermal|transd[eé]rmic[oa]s?|(?:through|via|on|onto) (?:the|your|my|our) skin|pela pele|atrav[eé]s da pele|sobre a pele|a trav[eé]s de la piel|en la piel)\b',re.I)
USAGE={'spray':r'\bpress (?:the )?pump\b|\b(?:spray|spraying|sprayed|spritz|borrife|borrifar|pulverize|pulverizar|roc[ií]a(?:lo)?|pulveriza)\b', 'patch':r'\btransdermal\b|\b(?:through|via|on|onto) (?:the|your|my|our) skin\b|\b(?:apply|applied|applying|stick|wear)\b.{0,55}\b(?:skin|body)\b|\b(?:aplique|cole)\b.{0,55}\bpele\b', 'capsule':r'\b(?:swallow|engolir|engula)\b','powder':r'\b(?:mix|misture|dissolve|dissolva)\b.{0,55}\b(?:water|água|drink|bebida)\b','dropper':r'\b(?:under (?:the|your) tongue|debaixo da l[íi]ngua|sublingual)\b'}
def contradiction(text,config):
    negative=r'\b(?:no|not|never|without|n[aã]o|sem|nunca|sin)\b.{0,45}'
    target=FORMS[config['destino']]['pattern']
    return bool(re.search(negative+r'(?<!\w)(?:'+target+r')(?!\w)',text,re.I))

def match(text,config):return bool(contradiction(text,config) or pattern(config).search(text) or re.search(USAGE.get(config['origem'],r'(?!)'),text,re.I) or (config['origem']=='patch' and re.search(r'\b(?:peel|wear|adhesive|waterproof|retire|cole)\b',text,re.I)) or (config.get('uso_original') and config['uso_original'].casefold() in text.casefold()) or (config['origem']=='patch' and SKIN_ROUTE.search(text)))

def lexical(text,config):
    if not config.get('ativo') or not pattern(config).search(text):return text,[]
    notes=[];original=text
    # An exact user-provided instruction is authoritative, not an inferred dose.
    if config.get('uso_original'):
        text=re.sub(re.escape(config['uso_original']),lambda _:config['uso_novo'],text,flags=re.I)
    def replace(m):
        word=m[0];lang=language(original,word);plural=bool(re.fullmatch(r'patches|adesivos|parches|droppers|drops|gotas|goteros|capsules|c[áa]psulas|pills|tablets|comprimidos|pastillas|gummies|gomas|gomitas|sprays|aerossóis|aerosoles|borrifadas|pulverizações',word,re.I))
        if re.fullmatch(r'conta[- ]gotas',word,re.I):plural=bool(re.search(r'\b(?:os|esses|estes|aqueles|v[aá]rios|dois|tr[eê]s|seis)\s*$',original[:m.start()],re.I))
        value=FORMS[config['destino']][lang][int(plural)]
        return value.upper() if word.isupper() else value[0].upper()+value[1:] if word[0].isupper() else value
    text=pattern(config).sub(replace,text)
    # Common topical wording can be generalized without inventing oral dosage.
    if config['origem']=='patch' and config['destino']!='patch':
        text=re.sub(r'\b(?:apply|wear|stick|put on)\b(?=\s+(?:it|them)\b)','use',text,flags=re.I)
        text=re.sub(r'\b(apply|wear|stick|put on)\b(?=\s+(?:(?:a|an|the|your|this|one|single)\s+)?(?:dropper|capsule|powder|gummy|liquid))','use',text,flags=re.I)
        text=re.sub(r'\s+(?:directly\s+)?(?:on|to|onto)\s+(?:your|the)\s+skin\b','',text,flags=re.I)
        text=re.sub(r'\b(?:aplique|cole|vista)\b(?=\s+(?:(?:o|a|seu|sua|um|uma)\s+)?(?:conta-gotas|cápsula|pó|goma|líquido))','use',text,flags=re.I)
        text=re.sub(r'\s+(?:diretamente\s+)?(?:na|sobre a)\s+(?:sua\s+)?pele\b','',text,flags=re.I)
    target=FORMS[config['destino']]
    en='|'.join(re.escape(w) for w in set(target['en']))
    pt='|'.join(re.escape(w) for w in set(target['pt']))
    text=re.sub(r'\b(?:take|swallow|drink|apply|wear|mix)\b(?=\s+(?:(?:a|an|the|your|this|one|single|two|three)\s+)?(?:'+en+r')\b)','use',text,flags=re.I)
    text=re.sub(r'\ban\s+(?=(?:'+en+r')\b)','a ',text,flags=re.I)
    if config['destino'] in ('powder','liquid'):text=re.sub(r'\ba\s+(?=(?:'+en+r')\b)','the ',text,flags=re.I)
    first=pattern(config).search(original);lang=language(original,first[0]) if first else 'en'
    gender={'pt':{'o':'a','os':'as','um':'uma','uns':'umas','seu':'sua','seus':'suas','este':'esta','estes':'estas','esse':'essa','esses':'essas'},'es':{'el':'la','los':'las','un':'una','unos':'unas','este':'esta','estos':'estas','ese':'esa','esos':'esas'}}
    if lang in gender:
        pairs=gender[lang] if config['destino'] in ('capsule','gummy') else {v:k for k,v in gender[lang].items()}
        noun='|'.join(re.escape(w) for w in set(target[lang]))
        for before,after in pairs.items():text=re.sub(r'\b'+before+r'(?=\s+(?:'+noun+r')\b)',lambda m:after.upper() if m[0].isupper() and len(m[0])>1 else after.capitalize() if m[0][0].isupper() else after,text,flags=re.I)
    if original and original[0].isupper() and text:text=text[0].upper()+text[1:]
    if text!=original:notes.append('Conferir a frase adaptada e a forma de uso do produto novo.')
    if re.search(r'\b(?:\d+|one|two|three|six|daily|day|hours?|mg|ml|dose|doses|dia|vezes|meses|months?)\b',original,re.I):notes.append('Quantidade, frequência ou duração presentes: confira com a instrução real do novo produto; nenhuma dose foi calculada.')
    if re.search(r'\b(?:transdermal|skin|pele|sublingual|swallow|engolir|dissolv\w*|mix|mistur\w*|absorp\w*)\b',text,re.I):notes.append('Há referência a aplicação, absorção ou mecanismo que precisa de revisão manual.')
    return text,list(dict.fromkeys(notes))

# Instruções e mecanismos exigem reescrita da frase, não troca isolada de substantivo.
INSTRUCTIONS={
 'spray':r'\bpress (?:the )?pump\b|\bspray\s+(?:it|them|the|your|once|twice|directly|into|on)\b|\b(?:spraying|sprayed|spritz|pump|pumps|shake|shaking|borrife|borrifar|pulverize|pulverizar|agite|agitar|roc[ií]a(?:lo)?|pulveriza)\b',
 'patch':r'\b(?:apply|applying|applied|wear|wearing|worn|stick|sticking|stuck|peel|peeling|peeled|remove|removing|removed|replace|replacing|replaced|put\s+(?:it|them|on)|aplique|aplicar|cole|colar|retire|retirar|troque|trocar|pegue|coloque|colocar|aplica|aplicar|ponte|retira)\b|\b(?:on|onto|to)\s+(?:your|the)\s+skin\b|\b(?:na|sobre a|en la)\s+(?:sua\s+)?(?:pele|piel)\b',
 'dropper':r'\b(?:drops?\s+(?:under|on|into)|drip|dripping|dripped|put|coloque|administered|take|taking|taken|use|using|used|shake|shaking|shaken|tome|tomar|pingue|pingar|agite|agitar|use|usar|toma|tomar|ag[ií]ta(?:l[oa]s?)?)\b|under (?:the|your) tongue|(?:debaixo|embaixo) da l[íi]ngua|sublingual',
 'capsule':r'\b(?:take|taking|taken|swallow|swallowing|swallowed|tome|tomar|engula|engolir|toma|tr[aá]ga(?:l[oa]s?)?|tragar)\b',
 'powder':r'\b(?:mix|mixing|mixed|dissolve|dissolving|dissolved|stir|stirring|stirred|scoop|scoops|misture|misturar|dissolva|dissolver|beba|beber|mezcla|mezclar|disu[eé]lve(?:l[oa]s?)?)\b',
 'gummy':r'\b(?:take|taking|taken|chew|chewing|chewed|tome|tomar|mastigue|mastigar|mast[ií]ca(?:l[oa]s?)?|masticar)\b',
 'liquid':r'\b(?:take|taking|drink|drinking|mix|mixing|tome|tomar|beba|beber|misture|misturar|b[eé]be(?:l[oa]s?)?|beber|mezcla)\b',
}
MECHANISM=re.compile(r'\b(?:transdermal|transdérmic[oa]|transdermic[oa]|absorp\w*|absor[çc][aã]o|absorb\w*|bloodstream|corrente sangu[ií]nea|torrente sangu[ií]neo|bypass\w*|digestive|digestivo|skin|pele|piel|wearable|gelatin|gelatina|waterproof|imperme[aá]vel|adhesive|adhesiv[oa]|(?:camada|tecnologia|material)\s+adesiv[oa]|nicotine|nicotina|hormone|horm[oô]nio|stomach|est[oô]mago|sublingual|layers?.{0,45}(?:dissolv|releas)|releas\w*.{0,60}(?:throughout the day|different times|all day)|camadas?.{0,45}(?:dissolv|libera)|slow.release|release.{0,25}hours|libera.{0,25}horas)\b',re.I)
DOSE=re.compile(r'\b(?:(?:\d+(?:[.,]\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|um|uma|dois|duas|tr[eê]s|un|una|dos|tres)\s*(?:mg|ml|hours?|horas?|times|vezes|drops?|gotas?|pills?|tablets?|comprimidos?|pastillas?|capsules?|c[aá]psulas?|patch(?:es)?|adesivos?|parches?|gumm(?:y|ies)|gomitas?|gomas?|scoops?|sprays?|pumps?|borrifadas?|pulveriza[çc][oõ]es)|once(?!\s+and\s+for\s+all\b)|twice|daily|per day|every (?:day|morning|night|evening)|each (?:day|morning|night|evening)|por dia|ao dia|todos os dias|cada d[ií]a|al d[ií]a|24.hour)\b',re.I)
# Continuações de uma instrução (só contam ao lado de uma frase de modo de uso já captada).
FOLLOWUP={
 'spray':r'\b(?:press (?:the )?pump|into (?:the|your) mouth|hold (?:it|the spray)|agite|borrife|pulverize|presione|roc[ií]a)\b',
 'dropper':r'\b(?:swallow\w*|hold (?:it|them|the (?:liquid|drops?))|wait\s+\w+\s+(?:seconds?|minutes?)|segure|engula|espere\s+\w+\s+segundos?|trague)\b',
 'patch':r'\b(?:sticks?|stays? (?:on|put)|leave (?:it|them) on|keep (?:it|them) on|(?:in|during) the shower|remove (?:it|them)|take (?:it|them) off|after \w+ hours|deixe (?:o|os) adesivos?|no banho|retire (?:o|os)|tire (?:o|os))\b',
 'capsule':r'\b(?:with (?:a |an )?(?:full )?(?:glass of )?water|with (?:a |your )?meals?|before (?:breakfast|bed|meals?)|com (?:um )?(?:copo de )?[áa]gua|com as refei[çc][õo]es|antes (?:do caf[ée]|de dormir))\b',
 'powder':r'\b(?:scoops?|glass of water|shake (?:it|well)|stir|copo de [áa]gua|agite|mexa)\b',
 'gummy':r'\b(?:chew\w*|mastigue)\b',
 'liquid':r'\b(?:sip|drink (?:it|them)|beba|tome (?:um )?gole)\b',
}
GENERIC_FOLLOW=r'\b(?:do (?:this|it) (?:every|each|once|twice|daily)|repeat (?:this|it)|every (?:morning|night|evening|day)|each (?:morning|night|day)|before (?:bed|sleep)|faça isso|repita|toda (?:manh[ãa]|noite)|todo dia|todos os dias|antes de dormir)\b'
CHECKOUT_ACTION = re.compile(
    r'\b(?:use|using|used|appl(?:y|ied|ying)|put|usar|usando|aplique|aplicar|'
    r'coloque|colocar|utilize|utilizar|usa|aplica|introduce)\s+'
    r'(?:(?:the|this|that|our|your|a|an|o|os|as|este|esta|esse|essa|el|la|los|las|tu)\s+)?'
    r'(?:(?:secure|official|direct|special|discount|promo|promotional|coupon|'
    r'segur[oa]|oficial|diret[oa]|especial|promocional|direct[oa])\s+){0,3}'
    r'(?:links?|website|site|bot[aã]o|button|codes?|c[oó]digos?|cupo(?:m|ns)|coupons?|'
    r'enlaces?|sitio|bot[oó]n|cup[oó]n)\b|\btak(?:e|ing) advantage of\b',
    re.I,
)

def followup(text,config):
    """Frase que só continua a instrução antiga (engolir, segurar, repetir…), sem a palavra da forma."""
    return bool(instruction(text,config) or DOSE.search(text) or re.search(FOLLOWUP.get(config['origem'],r'(?!)'),text,re.I) or re.search(GENERIC_FOLLOW,text,re.I))

PENDING='Adaptação completa pendente: informe a instrução/descrição confirmada do produto novo ou reescreva e confirme esta frase. Não será enviada para gerar voz enquanto estiver pendente.'

def finish(text):
    value=text.strip()
    return value if not value or re.search(r'[.!?][\"\')\]]*$',value) else value+'.'

def instruction(text,config):
    # Navegação e compra podem aparecer ao lado do modo de uso na mesma fala.
    probe=CHECKOUT_ACTION.sub(' ',text)
    probe=re.sub(r'\bput(?:ting)?\s+an\s+end\s+to\b','',probe,flags=re.I)
    probe=re.sub(r'\btake(?:s|n|ing)?\s+(?:a\s+(?:(?:closer|good|quick)\s+)?look|(?:our|your|the)\s+\w+\s+to\s+the\s+next\s+level)\b','',probe,flags=re.I)
    probe=re.sub(r'\b(?:a|the|our|your)\s+mix\s+of\b','',probe,flags=re.I)
    return bool(re.search(INSTRUCTIONS[config['origem']],probe,re.I))

def route_adaptation(text,config):
    """Rota confirmada permite mudar uma pergunta de aplicação sem inventar efeito."""
    route=config.get('via_uso');phrases={'oral':'orally','ingerir':'by mouth','sublingual':'under the tongue'}
    if config.get('origem')!='patch' or route not in phrases:return None
    clean=text.strip()
    simple=re.fullmatch(r'(?P<prefix>So what if|What if) (?P<actor>I|we) (?P<verb>applied|apply|used|use|administered|administer) (?P<owner>my|our|the|this) formula (?:through|via|on|onto) (?:the|my|our|your) skin\?',clean,re.I)
    if simple:
        verb='used' if simple['verb'].lower() in ('applied','used','administered') else 'use'
        return f"{simple['prefix']} {simple['actor']} {verb} {simple['owner']} formula {phrases[route]}?"
    if re.fullmatch(r'transdermal absorption[.!]?',clean,re.I):return 'Sublingual administration.' if route=='sublingual' else 'Oral administration.'
    variants={
        'pt':(r'(?P<prefix>E se|Então e se) (?P<actor>eu|nós) (?P<verb>aplicasse|aplicássemos) (?P<owner>minha|nossa|a) fórmula (?:pela|através da|sobre a) pele\?',{'oral':'por via oral','ingerir':'por ingestão','sublingual':'sob a língua'}),
        'es':(r'(?P<prefix>Y si|¿Y si) (?P<actor>yo|nosotros) (?P<verb>aplicara|aplicáramos) (?P<owner>mi|nuestra|la) fórmula (?:a través de la|en la) piel\?',{'oral':'por vía oral','ingerir':'por ingestión','sublingual':'debajo de la lengua'})}
    for lang,(pattern_,routes) in variants.items():
        m=re.fullmatch(pattern_,clean,re.I)
        if m:return f"{m['prefix']} {m['actor']} {'usasse' if m['actor'].lower()=='eu' else 'usássemos' if lang=='pt' else 'usara' if m['actor'].lower()=='yo' else 'usáramos'} {m['owner']} {'fórmula'} {routes[route]}?"
    return None

def adapt(text,config):
    if not config.get('ativo'):return text,[]
    # Frases inteiras são substituídas por orientações confirmadas, sem herdar dose/rota antigas.
    parts=re.split(r'(?<!\b[Dd][Rr]\.)(?<!\b[Ss][Rr]\.)(?<!\b[A-Z]\.)(?<=[.!?])\s+',text);result=[];notes=[]
    for sentence in parts:
        route_text=route_adaptation(sentence,config)
        if route_text is not None:result.append(route_text);notes.append('Via de uso confirmada aplicada, preservando o tipo de frase, sem dose nem alegação de absorção.');continue
        has_instruction=instruction(sentence,config)
        mechanism=bool(MECHANISM.search(sentence))
        quantified=bool(DOSE.search(sentence)) and match(sentence,config)
        exact=bool(config.get('uso_original') and config['uso_original'].casefold() in sentence.casefold())
        if exact:
            changed=re.sub(re.escape(config['uso_original']),lambda _:config['uso_novo'],sentence,flags=re.I)
            # Confirmação exata protege a orientação nova; verifica resíduos apenas no restante.
            remaining=re.sub(re.escape(config['uso_original']),'',sentence,flags=re.I)
            if match(remaining,config):
                result.append(sentence);notes.append(PENDING);continue
            result.append(changed);notes.append('Instrução específica substituída pela orientação confirmada.');continue
        target_present=re.search(r'(?<!\w)(?:'+FORMS[config['destino']]['pattern']+r')(?!\w)',sentence,re.I)
        if target_present and not match(sentence,config):result.append(sentence);continue
        relevant=match(sentence,config) or has_instruction
        incompatible=contradiction(sentence,config)
        if relevant and (has_instruction or mechanism or quantified or incompatible):
            # Instruções podem conter a rota antiga (pele/língua); ela é retirada junto da frase.
            description=config.get('descricao_nova','').strip();usage=config.get('uso_novo','').strip()
            scientific=bool(re.search(r'transderm|absorp|absor[çc]|absorb|bloodstream|corrente sangu|bypass|digestiv|nicotin|hormon|slow.release',sentence,re.I))
            replacement=description if scientific or incompatible or (mechanism and not has_instruction) else usage
            if replacement:
                result.append(finish(replacement));notes.append('Frase inteira reescrita com '+('a descrição' if replacement==description else 'o modo de uso')+' confirmado do produto novo. A dose, frequência e aplicação antigas não foram reaproveitadas.')
            else:
                # Preserva uma frase legível para editar, em vez de criar uma instrução híbrida.
                result.append(sentence);notes.append(PENDING)
            continue
        changed,local_notes=lexical(sentence,config);result.append(changed);notes.extend(local_notes)
    return _drop_continuations(parts,result,notes,config)

CONTINUATION='Continuação da instrução antiga retirada: o modo de uso confirmado já cobre esta parte.'
def _drop_continuations(parts,result,notes,config):
    # Uma instrução substituída não pode deixar o resto da instrução antiga ("segure…", "depois engula") nem repetir o modo novo.
    usage=finish(config.get('uso_novo','')) if config.get('uso_novo') else None;description=finish(config.get('descricao_nova','')) if config.get('descricao_nova') else None
    replaced=[bool(r) and r!=s and r in (usage,description) for s,r in zip(parts,result)]
    loose=[r==s and followup(s,config) and not pattern(config).search(s) for s,r in zip(parts,result)]
    drop=[False]*len(parts)
    # Em cadeia, para frente e para trás a partir de cada instrução substituída.
    for order in (range(len(parts)),range(len(parts)-1,-1,-1)):
        block=False
        for i in order:
            if replaced[i]:block=True
            elif loose[i] and block:drop[i]=True
            else:block=False
    keep=[]
    for i,text in enumerate(result):
        if drop[i] or (replaced[i] and keep and keep[-1]==text):notes.append(CONTINUATION);continue
        keep.append(text)
    return ' '.join(keep) or ' '.join(result),list(dict.fromkeys(notes))

def pending(notes):return any(note==PENDING for note in notes)

def augment(phrases,raw,config,old_names,new_name):
    if not config.get('ativo'):return phrases
    rows=[dict(r) for r in phrases]
    words=raw.get('words') or [];sentences=[];current=[]
    for word in words:
        if current and word.get('speaker')!=current[-1].get('speaker'):sentences.append(current);current=[]
        current.append(word)
        if re.search(r'[.!?]["\')\]]*$',word['text']) and word['text'].lower() not in {'dr.','mr.','mrs.','u.s.','etc.'}:sentences.append(current);current=[]
    if current:sentences.append(current)
    texts=[' '.join(w['text'] for w in sentence) for sentence in sentences]
    plain=[match(t,config) for t in texts]
    # Only already detected rows can seed usage through a timeline overlap.
    known=sorted((r for r in rows if match(r.get('novo') or r['text'],config)),key=lambda r:r['start'])
    usage=plain.copy()
    pos=0
    for i,sentence in enumerate(sentences):
        start,end=sentence[0]['start'],sentence[-1]['end']
        while pos<len(known) and known[pos]['end']<=start:pos+=1
        usage[i]=usage[i] or (pos<len(known) and known[pos]['start']<end)
    context=[False]*len(sentences)
    def near(i,j):
        if not 0<=j<len(sentences) or sentences[j][0].get('speaker')!=sentences[i][0].get('speaker'):return False
        earlier,later=sorted((i,j))
        return sentences[later][0]['start']-sentences[earlier][-1]['end']<2500
    for i,text in enumerate(texts):
        if not usage[i] and instruction(text,config) and any(near(i,j) and plain[j] for j in (i-1,i+1)):usage[i]=True
    follows=[not usage[i] and followup(t,config) for i,t in enumerate(texts)]
    for order,step in ((range(len(texts)),-1),(range(len(texts)-1,-1,-1),1)):
        for i in order:
            j=i+step
            if follows[i] and near(i,j) and (usage[j] or context[j]):context[i]=True
    def swapped(text):
        changed=text
        if new_name:
            for name in sorted(filter(None,old_names),key=len,reverse=True):changed=re.sub(r'(?<!\w)'+re.escape(name)+r'(?!\w)',lambda _:new_name,changed,flags=re.I)
        return changed
    for index,sentence in enumerate(sentences):
        text=texts[index]
        if not usage[index] and not context[index]:continue
        a,b=sentence[0]['start'],sentence[-1]['end']
        overlapping=[r for r in rows if r['start']<b and r['end']>a]
        if overlapping:
            # Existing product/price rows already use sentence boundaries.
            for row in overlapping:row['forma_detectada']=True
            continue
        if context[index] and not usage[index]:
            # Continuação sem a palavra da forma: entra na frase de uso vizinha para sair junto com ela.
            previous=next((r for r in rows if r.get('forma_detectada') and r['end']<=a and a-r['end']<2500 and r.get('speaker')==sentence[0].get('speaker')),None)
            following=None if previous else next((r for r in rows if r.get('forma_detectada') and r['start']>=b and r['start']-b<2500 and r.get('speaker')==sentence[0].get('speaker')),None)
            target=previous or following
            if target and not any(r is not target and r['start']<max(b,target['end']) and r['end']>min(a,target['start']) for r in rows):
                if previous:target.update(end=b,text=target['text']+' '+text,novo=(target.get('novo') or target['text'])+' '+swapped(text))
                else:target.update(start=a,text=text+' '+target['text'],novo=swapped(text)+' '+(target.get('novo') or target['text']))
                target['forma_contexto']=True;continue
        rows.append({'start':a,'end':b,'text':text,'novo':swapped(text),'speaker':sentence[0].get('speaker'),'origem':'forma','forma_detectada':True,'forma_contexto_isolado':context[index] and not usage[index]})
        rows.sort(key=lambda r:r['start'])
    for row in rows:
        if row.get('forma_detectada') or match(row.get('novo') or row['text'],config):
            row['novo'],row['forma_avisos']=adapt(row.get('novo') or row['text'],config);row['forma_detectada']=True
            if row.pop('forma_contexto_isolado',False) and not row['forma_avisos']:row['forma_avisos']=[PENDING]
            row['forma_pendente']=pending(row['forma_avisos'])
    return sorted(rows,key=lambda r:r['start'])

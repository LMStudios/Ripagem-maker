"""Identificação de nomes na transcrição, com sugestões conservadoras para revisão."""
import re
import unicodedata
from functools import lru_cache
from difflib import SequenceMatcher

_SUFFIXES = {'pro', 'plus', 'max', 'ultra', 'advanced', 'premium', 'extra', 'formula', 'complex'}


def compact(value):
    value = unicodedata.normalize('NFKD', str(value)).casefold()
    return re.sub('[^a-z0-9]', '', ''.join(c for c in value if not unicodedata.combining(c)))


def names(product, aliases=''):
    return list(dict.fromkeys(s.strip() for s in [str(product or ''), *re.split(r'[,;\n]+', str(aliases or ''))] if s.strip()))


def transcript_words(data):
    """Lê palavras com tempos da transcrição principal ou, se ausentes, das falas diarizadas."""
    if data.get('words'):
        return data['words']
    return sorted((dict(w, speaker=w.get('speaker') or u.get('speaker'))
                   for u in data.get('utterances') or [] for w in u.get('words') or []
                   if 'start' in w and 'end' in w and w.get('text')), key=lambda w:w['start'])


def _stem(value):
    words = re.findall(r'[^\W_]+', value.casefold())
    suffix = []
    while len(words) > 1 and words[-1] in _SUFFIXES:
        suffix.insert(0, words.pop())
    return compact(''.join(words)), tuple(suffix)


def _phonetic(value):
    # Erros de ASR no final de marcas: -ance/-ence, -ants/-ents, -anse/-ense.
    return re.sub(r'(?:ance|ence|ants?|ents?|anse|ense)$', 'ns', value)


@lru_cache(maxsize=8192)
def _similar(candidate, target):
    if candidate == target:
        return True
    if abs(len(candidate) - len(target)) > 2 or candidate[:4] != target[:4]:
        return False
    if _phonetic(candidate) == _phonetic(target) or (len(target)>=8 and _one_edit(candidate,target)):
        return True
    ratio = SequenceMatcher(None, candidate, target, autojunk=False).ratio()
    return ratio >= .89 or (min(len(candidate), len(target)) >= 8 and candidate[-4:] == target[-4:] and ratio >= .86)


_CUE = re.compile(
    r"\b(?:try|tried|buy|order|ordered|recommend|recommends|called|named|experimente|compre|recomendo|chamado|llamado|prueba|compra)"
    r"(?: a| the| some| o| el)?$|\b(?:bottles?|jars?|capsules?|pack|supply|kit|frasco|potes?|frascos?|botellas?) (?:of|de|do|del)$")
_STOP = frozenset("i a an and are as at be but by can for from has have in is it me my new not of on one only or our so that the their them then they this to try was we were when which who will with would you your now today two three four five six seven eight nine ten free more just some another all once".split())
# Contrações e palavras de ligação não podem disputar a identificação de uma marca,
# mesmo sem o dicionário opcional do sistema (por exemplo, no Windows).
_SPEECH_WORDS = _STOP | frozenset("""
because however therefore although though while whether about also actually really
well even enough instead everything something nothing anything someone everyone
yes no okay hello thanks thank please dont doesnt didnt cannot cant couldnt
wouldnt shouldnt wont wasnt werent isnt arent havent hasnt hadnt mustnt lets
""".split())
_CONTRACTIONS = frozenset(
    subject + ending
    for subject, endings in {
        "i": ("m", "d", "ll", "ve"),
        "you": ("re", "d", "ll", "ve"),
        "we": ("re", "d", "ll", "ve"),
        "they": ("re", "d", "ll", "ve"),
        "he": ("s", "d", "ll"),
        "she": ("s", "d", "ll"),
        "it": ("s", "d", "ll"),
        "that": ("s", "d", "ll"),
        "this": ("s",),
        "there": ("s", "re", "d", "ll", "ve"),
        "here": ("s",),
        "what": ("s", "re", "d", "ll", "ve"),
        "who": ("s", "re", "d", "ll", "ve"),
        "where": ("s", "re", "d"),
        "when": ("s", "d"),
        "why": ("s", "d"),
        "how": ("s", "d"),
    }.items()
    for ending in endings
)


def is_common_speech_word(value):
    """Compara também apóstrofos curvos e contrações sem apóstrofo do ASR."""
    token = compact(value)
    return token in _SPEECH_WORDS or token in _CONTRACTIONS


_BEFORE_NAME = re.compile(
    r"\b(?:(?:product|brand|formula|supplement|produto|f[oó]rmula|marca|producto) (?:called|named|chamado|chamada|llamado|llamada)"
    r"|(?:bottles?|jars?|capsules?|frasco|potes?|frascos?|botellas?) (?:of|de|do|del))$")
_AFTER_NAME = frozenset("is are was has had helps works comes contains supports improves every today now here online before for at with and e oferece funciona ajuda contém ayuda funciona contiene agora hoy".split())


def _parts(value):
    return tuple(compact(word) for word in re.findall(r"[^\W_]+", str(value)) if compact(word))


@lru_cache(maxsize=8192)
def _one_edit(a, b):
    if abs(len(a)-len(b)) > 1:
        return False
    if len(a) != len(b):
        short, long = sorted((a, b), key=len)
        i = next((i for i, c in enumerate(short) if c != long[i]), len(short))
        return short[i:] == long[i+1:]
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return len(diff) <= 1 or (len(diff) == 2 and diff[1] == diff[0]+1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])


@lru_cache(maxsize=8192)
def _speech_key(word):
    # Variações de escrita de um mesmo som, usadas só com âncora ou contexto.
    word = re.sub(r'([a-z])\1+', r'\1', word)
    word = re.sub(r'(?:eau|ea|ee|ie|ei)', 'e', word)
    word = re.sub(r'(?:ph|ght|th|ck)', lambda m: {'ph':'f','ght':'t','th':'t','ck':'k'}[m[0]], word)
    word = word.replace('x', 'ks')
    return word[:-1] if len(word) >= 5 and word.endswith('e') else word


def _compound(candidate, target, context):
    if len(candidate) != len(target) or len(target) < 2:
        return False
    changed = [(a,b) for a,b in zip(candidate,target) if a != b]
    # Uma palavra do nome continua exata. Nunca transformar um par inteiro só por semelhança.
    if len(changed) != 1:
        return False
    a,b = changed[0]
    if min(len(a),len(b)) < 3 or not a.isalpha() or not b.isalpha() or a in _STOP:
        return False
    phonetic = _speech_key(a) == _speech_key(b)
    if phonetic:
        return True
    if _one_edit(a,b):
        return (min(len(a),len(b)) >= 4 and a[0] == b[0]) or context
    # Ex.: o som de “breath” pode sair “Brett”; exige uma palavra intacta e contexto de produto.
    return context and min(len(a),len(b)) >= 4 and a[:2] == b[:2] and _one_edit(_speech_key(a),_speech_key(b))


def contextual_names(groups):
    """Candidatos em minúsculas: exige repetição em contextos explícitos de produto."""
    from collections import Counter, defaultdict
    counts, evidence = Counter(), defaultdict(set)
    for group in groups:
        tokens = [str(w['text']) for w in group]
        clean = [compact(w) for w in tokens]
        for i in range(1, len(tokens)):
            lead = ' '.join(clean[max(0,i-3):i])
            if not _BEFORE_NAME.search(lead):
                continue
            for size in (2, 1):
                part = clean[i:i+size]
                if len(part)!=size or any(len(x)<3 or not x.isalpha() or is_common_speech_word(x) for x in part):
                    continue
                j=i+size
                if not re.search(r"[.!?,;:][\"')\]]*$",tokens[j-1]) and (j==len(tokens) or clean[j] not in _AFTER_NAME):
                    continue
                if size == 1 and len(part[0]) < 5:
                    continue
                key = ' '.join(part)
                counts[key]+=1
                evidence[key].add(lead.split()[-2])
                break
    return [(name,count) for name,count in counts.most_common() if count>=2 and (len(evidence[name])>=2 or count>=3)]


def spans(tokens, terms, *, approximate=True):
    """(índice, tamanho, confiança). Exatos têm prioridade e não se sobrepõem."""
    token_parts = [_parts(t) for t in tokens]
    normalized = [''.join(parts) for parts in token_parts]
    entries = [(_parts(n), compact(n)) for n in terms if compact(n)]
    exact = {key for _, key in entries}
    compounds = [parts for parts,_ in entries if len(parts)>=2 and len(''.join(parts))>=6]
    short = [key for parts,key in entries if len(parts)==1 and 5<=len(key)<=7 and key.isalpha()]
    if not exact:
        return []
    roots = [(root, suffix) for name in terms for root, suffix in [_stem(name)] if len(root) >= 8 and root.isalpha()]
    max_size = max(3, max(len(parts)+1 for parts,_ in entries))
    precise, suggestions = [], []
    for i in range(len(tokens)):
        text = ''
        context = bool(_CUE.search(' '.join(normalized[max(0,i-3):i]))) if approximate else False
        for size in range(1, min(max_size, len(tokens) - i) + 1):
            part = normalized[i + size - 1]
            if not part:
                break
            text += part
            if text in exact:
                precise.append((i, size, 1.0))
                continue
            if not approximate or not text.isalpha():
                continue
            local = tuple(part for parts in token_parts[i:i+size] for part in parts)
            if any(_compound(local, target, context) for target in compounds):
                suggestions.append((i,size,.88))
                continue
            if context and size==1 and text not in _STOP and any(text[:2] == key[:2] and _one_edit(text,key) for key in short):
                suggestions.append((i,size,.85))
                continue
            for root, suffix in roots:
                ending = ''.join(suffix)
                core = text[:-len(ending)] if ending and text.endswith(ending) else text
                if len(core) >= 6 and _similar(core, root):
                    # Não captura uma palavra extra cuja única contribuição é um sufixo genérico alheio.
                    suggestions.append((i, size, .9 if core == root else .85))
                    break
    occupied, result = set(), []
    for i, size, score in sorted(precise + suggestions, key=lambda hit: (-int(hit[2] == 1), -hit[1], -hit[2], hit[0])):
        indexes = set(range(i, i + size))
        if not indexes & occupied:
            occupied.update(indexes)
            result.append((i, size, score))
    return sorted(result)


def bridged_spans(words, terms, *, field='w', time='s', end='e', max_pause=.85):
    """Nome exato dito em partes, separadas por ponto ou pausa (ex.: “Gluco. Trust. Pro.”).

    Só aceita a grafia exata de um nome conhecido. Duas partes: mesma pessoa, sem fim de
    frase e pausa de até 1,75× o limite normal. Três ou mais partes: pontuação e pausas de
    até 3× o limite, mesmo que a diarização troque o speaker no meio (comum em avatares). Retorna apenas o que
    atravessa uma divisão; o restante já é coberto pela busca dentro de cada frase."""
    entries = [_parts(n) for n in terms if compact(n)]
    exact = {''.join(parts) for parts in entries if len(''.join(parts)) >= 6}
    if not exact or len(words) < 2:
        return []
    max_size = max(4, max(len(parts) + 1 for parts in entries))
    tokens = [''.join(_parts(w[field])) for w in words]
    result = []
    for i in range(len(words)):
        text, crossed = '', False
        for size in range(1, min(max_size, len(words) - i) + 1):
            k = i + size - 1
            if not tokens[k]:
                break
            if size > 1:
                prev, curr = words[k - 1], words[k]
                gap = curr[time] - prev.get(end, prev[time])
                if gap > max_pause * 3:
                    break
                strong = (curr.get('speaker') != prev.get('speaker') or gap > max_pause * 1.75
                          or re.search(r'[.!?][\"\')\]]*$', str(prev[field])))
                if strong:
                    crossed = 'strong'
                elif gap > max_pause and not crossed:
                    crossed = 'pause'
            text += tokens[k]
            if text in exact and crossed and size >= 2:
                # Duas partes só atravessam uma pausa curta da mesma pessoa, sem fim de frase.
                if size == 2 and crossed == 'strong':
                    continue
                result.append((i, size, 1.0))
                break
    occupied, kept = set(), []
    for i, size, score in sorted(result, key=lambda hit: (-hit[1], hit[0])):
        if not occupied.intersection(range(i, i + size)):
            occupied.update(range(i, i + size))
            kept.append((i, size, score))
    return sorted(kept)


def timed_spans(words, terms, *, approximate=True, field='w', time='s', end='e', max_pause=.85):
    """Não costura nomes entre frases, speakers ou pausas longas na auditoria,
    exceto a grafia exata de um nome dito em partes (ver bridged_spans)."""
    result, start = [], 0
    for i in range(1, len(words) + 1):
        if i < len(words):
            prev, curr = words[i-1], words[i]
            if (curr.get('speaker') == prev.get('speaker')
                    and curr[time] - prev.get(end, prev[time]) <= max_pause
                    and not re.search(r'[.!?][\\"\')\]]*$', str(prev[field]))):
                continue
        if i > start:
            result.extend((start + a, size, score) for a, size, score in spans([w[field] for w in words[start:i]], terms, approximate=approximate))
        start = i
    occupied = {k for a, size, _ in result for k in range(a, a + size)}
    for a, size, score in bridged_spans(words, terms, field=field, time=time, end=end, max_pause=max_pause):
        span = set(range(a, a + size))
        if span & occupied:
            # Uma parte isolada (ex.: “Pro.”) cede lugar ao nome completo.
            if any(size <= s2 or not set(range(b, b + s2)) <= span for b, s2, _ in result if set(range(b, b + s2)) & span):
                continue
            result = [hit for hit in result if not set(range(hit[0], hit[0] + hit[1])) & span]
        result.append((a, size, score))
        occupied |= span
    return sorted(result)

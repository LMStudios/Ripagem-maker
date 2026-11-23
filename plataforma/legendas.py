"""Legendas da montagem final: SRT novo no tempo da montagem, com o texto aprovado das falas trocadas.

Diferente do corretor de SRT (que só troca nomes e preserva timecodes): aqui a duração mudou, então
os tempos vêm do áudio final da montagem, transcrito localmente, e o texto vem do roteiro esperado
(transcrição original fora das trocas + texto aprovado das falas novas). O tempo da fala antiga
nunca é reaproveitado para a fala nova. O SRT original nunca é alterado.
"""
import json
import math
import re
import time
import tempfile
import wave
from bisect import bisect_right
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from . import ml_core as M, trocas as T

VERSION = 'legendas-1'
DEFAULTS = {'modo': 'video_inteiro', 'caracteres_linha': 42, 'linhas': 2, 'duracao_max_s': 6.0}
MODES = ('auto', 'video_inteiro', 'coberturas')
PAUSE_S = .6
MIN_CUE_S = .8
HOLD_S = .3
SENTENCE = re.compile(r'[.!?…]["”\')\]]*$')


def folder(out): return Path(out) / 'trocas/legendas'
def path(out): return folder(out) / 'estado.json'


def load(out):
    state = json.loads(path(out).read_text()) if path(out).exists() else {}
    state.setdefault('config', dict(DEFAULTS))
    for key, value in DEFAULTS.items():
        state['config'].setdefault(key, value)
    return state


def norm(text):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def clock(seconds):
    ms = max(0, round(seconds * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


# ---------- mapa de tempo ----------

class TimeMap:
    """Original → montagem final: extensões das falas maiores e margens de limpeza removidas, como no XML."""

    def __init__(self, out):
        from . import montagem as MT, fechamento as FC
        self.MT, self.FC = MT, FC
        plan = T.load(out)
        self.rows = T.approved(plan, True)
        self.info = T.probe(T.source(out))
        self.fps = self.info['fps']
        self.changes = MT.edits(out, self.rows, self.info)
        self.closures = FC.windows(self.changes, self.fps)
        self.mutes, previous = [], 0
        for e in self.changes:
            self.mutes.append((MT.mute_start(e['a'], previous, self.fps), e['b']))
            previous = e['b']
        frames = round(self.info['duration'] * self.fps) + sum(e['extra'] for e in self.changes)
        self.duration_s = self.final_frame(frames) / self.fps

    def final_frame(self, frame): return self.FC.position(frame, self.closures)

    def source_s(self, seconds):
        """Tempo final de um instante do original; None se o áudio original ali foi substituído."""
        frame = round(seconds * self.fps)
        if any(a <= frame < b for a, b in self.mutes):
            return None
        return self.final_frame(self.MT.shift(frame, self.changes)) / self.fps

    def replaced(self):
        return [{'row': e['row'], 'inicio': self.final_frame(e['start']) / self.fps, 'fim': self.final_frame(e['end']) / self.fps} for e in self.changes]


# ---------- texto esperado ----------

def canonical_names(plan):
    """Grafia final do produto novo e nomes antigos (para sinalizar, nunca para trocar em fala original)."""
    new = str(plan.get('produto_novo', '')).strip()
    old = [plan.get('produto', '')] + re.split(r'[,;\n]', str(plan.get('produto_aliases', '')) + ',' + str(plan.get('editorial', {}).get('aliases', '')))
    return new, [] if plan.get('somente_valores') else [n for n in dict.fromkeys(norm(x) for x in old) if n and n != norm(new)]


def standardize(words, new):
    """Padroniza a grafia do produto novo (ex.: GLYCOZEN pro → Glycozen Pro) sem mexer no resto."""
    target = new.split()
    key = norm(new).split()
    if not key:
        return words
    result, i = [], 0
    while i < len(words):
        window = [norm(w['texto']) for w in words[i:i + len(key)]]
        if window == key and len(window) == len(key):
            tail = re.sub(r'^.*?([^\w]*)$', r'\1', words[i + len(key) - 1]['texto'])
            for k, part in enumerate(target):
                result.append(dict(words[i + k], texto=part + (tail if k == len(target) - 1 else '')))
            i += len(key)
        else:
            result.append(words[i])
            i += 1
    return result


def expected(out, tmap, raw=None):
    """Sequência de palavras da montagem: original mapeado + texto aprovado das falas novas, com tempos estimados."""
    plan = T.load(out)
    if raw is None:
        raw = json.loads((Path(out) / 'transcricao_bruta.json').read_text())
    from .mencoes import transcript_words
    words = []
    for w in transcript_words(raw):
        a = tmap.source_s(w['start'] / 1000)
        if a is None or not str(w.get('text', '')).strip():
            continue
        # Palavra que termina dentro da margem removida ainda é ouvida: mantém, com fim curto.
        b = tmap.source_s(max(w['start'], w['end'] - 1) / 1000)
        if b is None:
            b = a + min(.3, max(0, w['end'] - w['start']) / 1000)
        words.append({'texto': str(w['text']).strip(), 'inicio': a, 'fim': max(a, b), 'origem': 'original', 'speaker': w.get('speaker')})
    for item in tmap.replaced():
        row, tokens = item['row'], str(item['row']['novo']).split()
        total = sum(len(t) + 1 for t in tokens) or 1
        cursor, span = item['inicio'], item['fim'] - item['inicio']
        for token in tokens:
            length = span * (len(token) + 1) / total
            words.append({'texto': token, 'inicio': cursor, 'fim': cursor + length, 'origem': 'fala_nova', 'fala': row['id'], 'speaker': row.get('speaker')})
            cursor += length
    words.sort(key=lambda w: (w['inicio'], w['fim']))
    new, _ = canonical_names(plan)
    return standardize(words, new)


# ---------- alinhamento com o áudio final ----------

def align(words, heard, window_s=8.0, chunk=150):
    """Leva os tempos das palavras ouvidas no áudio final para o texto esperado, por blocos próximos no tempo."""
    heard = [h for h in heard if str(h.get('w', '')).strip()]
    hkeys = [norm(h['w']) for h in heard]
    starts = [h['s'] for h in heard]
    import bisect
    last = -1
    for i in range(0, len(words), chunk):
        block = words[i:i + chunk]
        # Só avança no áudio: um bloco novo não pode casar com palavra ouvida antes da anterior.
        lo = max(last + 1, bisect.bisect_left(starts, block[0]['inicio'] - window_s))
        hi = bisect.bisect_right(starts, block[-1]['fim'] + window_s)
        if lo >= hi:
            continue
        keys = [norm(w['texto']) for w in block]
        matcher = SequenceMatcher(None, keys, hkeys[lo:hi], autojunk=False)
        for a, b, size in matcher.get_matching_blocks():
            for k in range(size):
                h = heard[lo + b + k]
                # Palavra solta longe da estimativa costuma ser coincidência (ex.: "for" repetido).
                if size == 1 and abs(h['s'] - block[a + k]['inicio']) > window_s / 2:
                    continue
                block[a + k].update(inicio=h['s'], fim=h['e'], alinhado=True)
                last = max(last, lo + b + k)
    # Palavras sem par ficam entre as vizinhas alinhadas, proporcionalmente à estimativa.
    anchors = [i for i, w in enumerate(words) if w.get('alinhado')]
    for left, right in zip([-1] + anchors, anchors + [len(words)]):
        gap = words[left + 1:right]
        if not gap:
            continue
        a = words[left]['fim'] if left >= 0 else gap[0]['inicio']
        b = words[right]['inicio'] if right < len(words) else gap[-1]['fim']
        if b <= a:
            b = a + .05 * len(gap)
        step = (b - a) / len(gap)
        for k, w in enumerate(gap):
            w.update(inicio=a + k * step, fim=a + (k + 1) * step, estimado=True)
    return words


def alerts(words, heard, tmap, old_names, new_name=''):
    result = []
    for item in tmap.replaced():
        row = item['row']
        mine = [w for w in words if w.get('fala') == row['id']]
        ratio = sum(1 for w in mine if w.get('alinhado')) / max(1, len(mine))
        if ratio < .6:
            said = ' '.join(h['w'].strip() for h in heard if item['inicio'] - .2 <= h['s'] <= item['fim'] + .2)
            result.append({'tipo': 'divergencia', 'inicio': item['inicio'], 'fim': item['fim'], 'aprovado': row['novo'], 'ouvido': said,
                           'motivo': f'Só {round(ratio * 100)}% do texto aprovado foi reconhecido no áudio desta fala. Ouça antes de usar a legenda.'})
    from .mencoes import timed_spans
    protected_new = {k for i, size, _ in timed_spans(heard, [new_name], approximate=False) for k in range(i, i+size)} if new_name else set()
    for i, size, score in timed_spans(heard, old_names):
        if any(k in protected_new for k in range(i, i+size)):
            continue
        result.append({'tipo': 'nome_antigo' if score == 1 else 'nome_antigo_possivel',
                       'inicio': heard[i]['s'], 'fim': heard[i + size - 1]['e'],
                       'motivo': f"Possível nome do produto antigo no áudio: {' '.join(h['w'] for h in heard[i:i+size])}. Confira e inclua a fala nas trocas, se necessário."})
    result.sort(key=lambda r: r['inicio'])
    unique = []
    for item in result:
        if not (unique and item['tipo'] == unique[-1]['tipo'] and item['inicio'] - unique[-1]['inicio'] < 1.0):
            unique.append(item)
    return unique


# ---------- blocos de legenda ----------

def protected(words, names):
    """Índices que não podem ser separados (o nome do produto fica sempre no mesmo bloco e linha)."""
    keys = [norm(w['texto']) for w in words]
    glue = set()
    for name in names:
        parts = name.split()
        for i in range(len(keys) - len(parts) + 1):
            if len(parts) > 1 and keys[i:i + len(parts)] == parts:
                glue.update(range(i, i + len(parts) - 1))
    return glue


def fits(text_words, width, count):
    """Quebra gulosa: cabe em até `count` linhas de `width` caracteres?"""
    used, length = 1, 0
    for word in text_words:
        need = len(word) if not length else length + 1 + len(word)
        if need <= width or not length:
            length = need
        else:
            used, length = used + 1, len(word)
    return used <= count


def lines(text_words, width, count, glue_local):
    if count <= 1 or len(' '.join(text_words)) <= width:
        return [' '.join(text_words)]
    if count > 2:
        result, line = [], []
        for k, word in enumerate(text_words):
            if line and len(' '.join(line + [word])) > width and k - 1 not in glue_local:
                result.append(' '.join(line))
                line = []
            line.append(word)
        return result + [' '.join(line)]
    total = len(' '.join(text_words))
    best, best_cut = None, None
    for cut in range(1, len(text_words)):
        if cut - 1 in glue_local:
            continue
        a, b = ' '.join(text_words[:cut]), ' '.join(text_words[cut:])
        score = abs(len(a) - len(b)) + (0 if max(len(a), len(b)) <= width else 1000)
        if best is None or score < best:
            best, best_cut = score, cut
    if best_cut is None:
        return [' '.join(text_words)]
    return [' '.join(text_words[:best_cut]), ' '.join(text_words[best_cut:])] if total else []


def cues(words, config, names, windows=None):
    """Agrupa palavras em blocos; respeita pausas, frases, troca de speaker, limites e janelas de cobertura."""
    width, count, max_s = int(config['caracteres_linha']), int(config['linhas']), float(config['duracao_max_s'])
    per_block = int(config.get('palavras_bloco') or 0)
    glue = protected(words, names)

    def window_of(w):
        if windows is None:
            return 0
        mid = (w['inicio'] + w['fim']) / 2
        return next((k for k, (a, b) in enumerate(windows) if a <= mid < b), None)

    blocks, current = [], []
    for i, w in enumerate(words):
        win = window_of(w)
        if win is None:
            if current:
                blocks.append(current)
            current = []
            continue
        if current:
            prev = current[-1]
            # O nome do produto conta como uma unidade: não pode ser quebrado entre linhas.
            candidate = []
            for k, x, _ in current + [(i, w, win)]:
                if candidate and k - 1 in glue:
                    candidate[-1] += ' ' + x['texto']
                else:
                    candidate.append(x['texto'])
            text = ' '.join(candidate)
            boundary = (win != prev[2] or w.get('speaker') != prev[1].get('speaker')
                        or w['inicio'] - prev[1]['fim'] >= PAUSE_S)
            breaking = (not fits(candidate, width, count) or w['fim'] - current[0][1]['inicio'] > max_s
                        or per_block and len(candidate) > per_block)
            soft = SENTENCE.search(prev[1]['texto']) and len(text) > width * .6
            if boundary or ((breaking or soft) and prev[0] not in glue):
                blocks.append(current)
                current = []
        current.append((i, w, win))
    if current:
        blocks.append(current)
    result = []
    for n, block in enumerate(blocks):
        start, end = block[0][1]['inicio'], block[-1][1]['fim']
        if windows is not None:
            a, b = windows[block[0][2]]
            start, end = max(start, a), min(end, b)
        result.append({'inicio': start, 'fim': end, 'palavras': [w for _, w, _ in block],
                       'linhas': lines([w['texto'] for _, w, _ in block], width, count, {k for k, (i, _, _) in enumerate(block) if i in glue}),
                       'janela': block[0][2]})
    # Duração mínima e pequena permanência, sem sobrepor o bloco seguinte nem sair da janela.
    for cue, following in zip(result, result[1:] + [None]):
        limit = following['inicio'] if following else cue['fim'] + 10
        if windows is not None:
            limit = min(limit, windows[cue['janela']][1])
        target = max(cue['fim'] + HOLD_S, cue['inicio'] + MIN_CUE_S)
        cue['fim'] = min(max(cue['fim'], min(target, limit)), cue['inicio'] + max_s)
    # Tempos ouvidos podem vir fora de ordem: cada bloco termina antes do seguinte começar.
    # Fragmentos curtos (ex.: no limite de uma cobertura) não chegam a ser lidos e saem.
    while True:
        result.sort(key=lambda c: c['inicio'])
        for previous, cue in zip(result, result[1:]):
            if cue['inicio'] < previous['fim']:
                previous['fim'] = max(previous['inicio'], cue['inicio'])
        kept = [c for c in result if c['fim'] - c['inicio'] >= .3]
        if len(kept) == len(result):
            return kept
        result = kept


def srt(cue_list):
    return ''.join(f"{n}\n{clock(c['inicio'])} --> {clock(c['fim'])}\n" + '\n'.join(c['linhas']) + '\n\n' for n, c in enumerate(cue_list, 1))


# ---------- legendas gravadas e coberturas ----------

def burned_subtitles(out, samples=24):
    """Amostra quadros e procura frases na faixa inferior; vídeos com legendas gravadas pedem legenda só nas coberturas."""
    try:
        from rapidocr import RapidOCR
    except ImportError:
        return None
    import subprocess
    import numpy as np
    info = T.probe(T.source(out), False)
    if not info['video']:
        return None
    width = min(640, info['width'] - info['width'] % 2)
    height = max(2, round(width * info['height'] / info['width'] / 2) * 2)
    engine = RapidOCR(params={'Global.log_level': 'error'})
    hits = 0
    for k in range(samples):
        t = info['duration'] * (k + .5) / samples
        raw = subprocess.run([M.FFMPEG, '-v', 'error', '-ss', f'{t:.3f}', '-i', str(T.source(out)), '-frames:v', '1', '-vf', f'scale={width}:{height}',
                              '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        if len(raw) < width * height * 3:
            continue
        result = engine(np.frombuffer(raw[:width * height * 3], np.uint8).reshape(height, width, 3))
        for box, text in zip(result.boxes if result.boxes is not None else [], result.txts or []):
            if float(np.asarray(box)[:, 1].mean()) / height >= .6 and len(norm(text).split()) >= 2:
                hits += 1
                break
    return {'amostras': samples, 'com_texto_inferior': hits, 'detectado': hits >= samples * .4}


def coverage_windows(out, tmap):
    """Trechos da montagem em que a imagem original está coberta por takes em V2 (tempo final, segundos)."""
    from . import visuais as VIS
    try:
        segments = VIS.valid_prepared(out, False)
    except ValueError:
        return None
    pieces = []
    for s in segments:
        a, b = s['start_frame'], s['end_frame']
        if not s.get('timeline_final'):
            a, b = tmap.MT.shift(a, tmap.changes), tmap.MT.shift(b, tmap.changes)
        a, b = (a / tmap.fps, b / tmap.fps) if s.get('timeline_fechada') else (tmap.final_frame(a) / tmap.fps, tmap.final_frame(b) / tmap.fps)
        if b > a:
            pieces.append([a, b])
    merged = []
    for a, b in sorted(pieces):
        if merged and a <= merged[-1][1] + 1 / tmap.fps:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [tuple(x) for x in merged]


# ---------- tarefa ----------

def signature(out, config):
    from . import visuais as VIS
    plan = T.load(out)
    visual = VIS.load(out)
    prepared = (visual.get('prepared') or {}).get('signature')
    texts = [[r['id'], r.get('novo'), r.get('inicio_ms'), r.get('fim_ms')] for r in plan['itens'] if r.get('aprovado')]
    return T.digest([VERSION, T.preview_signature(out), texts, plan.get('produto_novo'), config, prepared])


def _audio_parts(out):
    from . import montagem as MT
    plan = T.load(out)
    core = [{k: r.get(k) for k in ('id', 'inicio_ms', 'fim_ms', 'novo', 'speaker', 'aprovado')}
            | {'audio': {k: r.get('audio', {}).get(k) for k in ('fit', 'texto_hash', 'aprovado', 'modo_duracao')}} for r in plan['itens']]
    return [MT.margin_ms(), plan.get('modo_duracao', 'fixo'), core, plan.get('trilha', {})]


def audio_signature(out):
    """Só o que muda o áudio final (falas, durações, margens, trilha, fonte); takes, imagens e o caminho da pasta não entram."""
    return T.digest(['audio-final-2', *_audio_parts(out), *T.source_identity(T.source(out))])


def audio_cache(out):
    """Arquivo da transcrição do áudio final; reaproveita o gravado por versões anteriores (chave com o caminho)."""
    target = folder(out) / f'audio_final_{audio_signature(out)}.json'
    if not target.exists():
        src = T.source(out)
        stat = src.stat()
        for text in T.legacy_path_texts(src):
            old = folder(out) / f"audio_final_{T.digest(['audio-final-1', *_audio_parts(out), text, stat.st_size, stat.st_mtime_ns])}.json"
            if old.exists():
                old.rename(target)
                break
    return target


def language(out):
    """Idioma da transcrição original (ex.: en_us → en): permite o modelo local menor e mais rápido."""
    raw = json.loads((Path(out) / 'transcricao_bruta.json').read_text())
    code = str(raw.get('language_code') or raw.get('language') or '').lower()[:2]
    return code if re.fullmatch('[a-z]{2}', code) else 'auto'


def heard_words(job, out):
    """Transcrição local do áudio final da montagem, guardada pela assinatura do áudio."""
    key = audio_signature(out)
    cache = audio_cache(out)
    if cache.exists():
        return json.loads(cache.read_text())['words']
    job.step = 'Montando o áudio final da montagem'
    audio = T.mix(job, out)
    from . import validacao as V
    data = V.transcribe(job, audio, {'motor': 'mlx', 'idioma': language(out)})
    T.write(cache, {'assinatura': key, 'words': data['words'], 'engine': data.get('engine'), 'language': data.get('language'),
                    'audio': str(Path(audio).relative_to(out))})
    return data['words']


def clip_words(job, out, tmap):
    """Alinha só o áudio que mudou; o restante já tem tempos da transcrição original."""
    clips = [(r, Path(out) / r['row']['audio']['fit']) for r in tmap.replaced()]
    ids = [[T.source_identity(p), r['fim']-r['inicio'], r['row']['id']] for r, p in clips]
    lang = language(out)
    # Cache relativo a cada clipe: mudar takes, estilo ou a posição na sequência não força nova transcrição.
    target = folder(out) / f"falas_alinhadas_{T.digest([ids, lang, 'clipes-1'])}.json"
    if target.exists():
        heard = json.loads(target.read_text())
    elif not clips:
        return []
    else:
        from . import validacao as V
        sr, offset, ranges = 16000, 0, []
        with tempfile.TemporaryDirectory(prefix='ripagem-legendas-') as tmp:
            joined = Path(tmp) / 'falas.wav'
            part = Path(tmp) / 'parte.wav'
            with wave.open(str(joined), 'wb') as sink:
                sink.setparams((1, 2, sr, 0, 'NONE', 'not compressed'))
                for i, (row, source) in enumerate(clips, 1):
                    job.step = f'Preparando alinhamento das falas novas ({i}/{len(clips)})'
                    duration = row['fim'] - row['inicio']
                    M.run_proc(job, [M.FFMPEG, '-y', '-v', 'error', '-i', str(source), '-t', str(duration),
                                     '-vn', '-ac', '1', '-ar', str(sr), '-c:a', 'pcm_s16le', str(part)])
                    with wave.open(str(part), 'rb') as clip:
                        length = clip.getnframes()
                        sink.writeframes(clip.readframes(length))
                    ranges.append((offset / sr, (offset + length) / sr))
                    sink.writeframes(b'\0' * (2 * sr))
                    offset += length + sr
            try:
                data = V.transcribe(job, joined, {'motor': 'mlx', 'idioma': lang})
            except ValueError as error:
                if 'Não foi reconhecida fala' not in str(error): raise
                data = {'words': []}
        heard = [[] for _ in clips]
        starts = [a for a, _ in ranges]
        for w in data['words']:
            index = bisect_right(starts, (w['s']+w['e'])/2) - 1
            if index >= 0 and w['s'] < ranges[index][1] and (w['s']+w['e'])/2 < ranges[index][1]:
                a, b = ranges[index]
                heard[index].append(dict(w, s=max(0, w['s']-a), e=min(b,w['e'])-a))
        T.write(target, heard)
    return [[dict(w, s=r['inicio']+w['s'], e=r['inicio']+w['e']) for w in words]
            for (r, _), words in zip(clips, heard)]


def missing_source_words(job, out, cut_ms, raw):
    """Completa projetos antigos sem pagar o custo de retranscrever a metade já conhecida."""
    from . import validacao as V
    source, lang = T.source(out), language(out)
    target = folder(out) / f"fonte_inicio_{T.digest([T.source_identity(source), cut_ms, lang])}.json"
    if target.exists():
        recognized = json.loads(target.read_text())
    else:
        with tempfile.TemporaryDirectory(prefix='ripagem-legendas-inicio-') as tmp:
            head = Path(tmp) / 'inicio.wav'
            job.step = 'Transcrevendo somente o começo ainda não analisado'
            M.run_proc(job, [M.FFMPEG, '-y', '-v', 'error', '-i', str(source), '-t', str(cut_ms / 1000),
                             '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(head)])
            try:
                recognized = V.transcribe(job, head, {'motor': 'mlx', 'idioma': lang})['words']
            except ValueError as error:
                if 'Não foi reconhecida fala' not in str(error): raise
                recognized = []
        T.write(target, recognized)
    prefix = [{'text': w['w'], 'start': round(w['s']*1000), 'end': min(cut_ms, round(w['e']*1000))}
              for w in recognized if w['s']*1000 < cut_ms and w['e'] > w['s']]
    from .mencoes import transcript_words
    return dict(raw, words=prefix + transcript_words(raw))


def fast_words(job, out, tmap, raw):
    words = expected(out, tmap, raw)
    by_row = {}
    heard = []
    for word in words:
        if word['origem'] == 'original':
            word['alinhado'] = True  # o timestamp da fonte foi medido na primeira transcrição
            heard.append({'w': word['texto'], 's': word['inicio'], 'e': word['fim']})
        else:
            by_row.setdefault(word['fala'], []).append(word)
    for item, audio in zip(tmap.replaced(), clip_words(job, out, tmap)):
        align(by_row[item['row']['id']], audio, window_s=2)
        heard.extend(audio)
    heard.sort(key=lambda w: w['s'])
    return words, heard


def prepare_base_job(job, out):
    """Aquece o cache de alinhamento das falas. Os tempos finais continuam a cargo da geração."""
    out = Path(out)
    if load(out)['config'].get('conferencia_integral') or audio_cache(out).exists():
        return {'preparada': False}
    with T.LOCK:
        tmap = TimeMap(out)
    job.step = 'Preparando a base da legenda enquanto os takes são escolhidos'
    clip_words(job, out, tmap)
    return {'preparada': True}


def generate_job(job, out, config=None):
    out = Path(out)
    started = time.perf_counter()
    state = load(out)
    config = dict(state['config'], **(config or {}))
    if config['modo'] not in MODES or not 20 <= int(config['caracteres_linha']) <= 80 or int(config['linhas']) not in (1, 2, 3) or not 1 <= float(config['duracao_max_s']) <= 15:
        raise ValueError('Confira os ajustes das legendas: modo, 20–80 caracteres por linha, 1–3 linhas e 1–15 s por bloco.')
    with T.LOCK:
        initial_signature = signature(out, config)
        plan = T.load(out)
        tmap = TimeMap(out)
    job.step = 'Conferindo se o vídeo original já tem legendas gravadas'
    job.pct = .02
    burned = state.get('legendas_gravadas')
    if config['modo'] == 'auto' and (burned is None or burned.get('fonte') != T.digest(T.source_identity(T.source(out)))):
        burned = burned_subtitles(out) or {'detectado': False, 'indisponivel': True}
        burned['fonte'] = T.digest(T.source_identity(T.source(out)))
    mode = config['modo'] if config['modo'] != 'auto' else ('coberturas' if burned.get('detectado') else 'video_inteiro')
    windows = None
    if mode == 'coberturas':
        windows = coverage_windows(out, tmap)
        if windows is None:
            raise ValueError('Para legendar só as coberturas, prepare os takes (ou prepare de novo, se algo mudou) na etapa Takes. Ou escolha “vídeo inteiro”.')
    raw = json.loads((out / 'transcricao_bruta.json').read_text())
    cut_ms = (raw.get('recorte_transcricao') or {}).get('inicio_ms', 0)
    cut_final = (tmap.source_s(cut_ms / 1000) or cut_ms / 1000) if cut_ms else 0
    missing_coverage = bool(cut_ms and (windows is None or any(a < cut_final for a, _ in windows)))
    integral = bool(config.get('conferencia_integral') or audio_cache(out).exists())
    if integral:
        heard = heard_words(job, out)
        words = align(expected(out, tmap, raw), heard)
        if missing_coverage:
            # Projetos antigos com transcrição parcial precisam de texto também antes do recorte.
            limit = min(cut_final, words[0]['inicio']) if words else cut_final
            prefix = [{'texto': h['w'], 'inicio': h['s'], 'fim': h['e'], 'origem': 'original',
                       'alinhado': True} for h in heard if h['e'] <= limit]
            words = prefix + words
    else:
        if missing_coverage:
            raw = missing_source_words(job, out, cut_ms, raw)
        words, heard = fast_words(job, out, tmap, raw)
    job.step = 'Formatando a legenda nos tempos da montagem'
    job.pct = .92
    new, old_names = canonical_names(plan)
    warnings = alerts(words, heard, tmap, old_names, new)
    if cut_ms and not (integral or missing_coverage):
        warnings.append({'tipo':'cobertura_parcial', 'inicio':0, 'fim':cut_final,
                         'motivo':'A busca de menções cobriu apenas a segunda metade. A primeira metade não foi conferida neste modo.'})
    names = [norm(new)] + old_names
    cue_list = cues(words, config, names, windows)
    if not cue_list:
        raise ValueError('Não há falas nas janelas selecionadas. Escolha “Vídeo inteiro” ou confira as coberturas dos takes.')
    folder(out).mkdir(parents=True, exist_ok=True)
    from . import identidade_entrega as ID
    stem = re.sub(r'[\\/:*?"<>|]+', '-', ID.identity(plan, out)['nome_sequencia']).strip() or 'LEGENDAS'
    target = folder(out) / f'{stem} - LEGENDAS MONTAGEM.srt'
    from .diagnostico import atomic_text
    aligned = sum(1 for w in words if w.get('alinhado'))
    used = [w for c in cue_list for w in c['palavras']]
    result = {'arquivo': str(target.relative_to(out)), 'assinatura': initial_signature, 'config': config, 'modo_usado': mode,
              'conferencia': 'integral' if integral else 'falas_novas', 'blocos': len(cue_list), 'palavras': len(used), 'alinhadas_pct': round(100 * aligned / max(1, len(words)), 1),
              'estimadas': sum(1 for w in used if w.get('estimado')), 'avisos': warnings, 'duracao_montagem_s': round(tmap.duration_s, 3),
              'coberturas': len(windows) if windows is not None else None, 'tempo_s': round(time.perf_counter() - started, 1),
              'alinhamento_por_palavra': aligned / max(1, len(words)) >= .9}
    with T.LOCK:
        if job.cancel:
            raise M.Cancelled()
        if signature(out, config) != initial_signature:
            raise ValueError('A montagem mudou durante a geração da legenda. Gere novamente com a montagem atual.')
        atomic_text(target, srt(cue_list))
        T.write(folder(out) / 'palavras.json', {'assinatura': initial_signature, 'nomes': names, 'janelas': windows,
                                                'alinhamento_por_palavra': sum(1 for w in words if w.get('alinhado')) / max(1, len(words)) >= .9,
                                                'palavras': [{k: w.get(k) for k in ('texto', 'inicio', 'fim', 'speaker', 'estimado')} for w in words]})
        state = load(out)
        state.update(config=config, resultado=result)
        if burned is not None: state['legendas_gravadas'] = burned
        T.write(path(out), state)
    job.pct = 1
    job.step = f'Legendas prontas · {len(cue_list)} blocos' + (f' · {len(warnings)} aviso(s)' if warnings else '')
    return result


def view(out):
    state = load(out)
    result = state.get('resultado')
    if result:
        try:
            state['desatualizado'] = '' if result['assinatura'] == signature(out, result['config']) else 'A montagem, os textos ou os takes mudaram. Gere as legendas novamente.'
        except ValueError as error:
            state['desatualizado'] = str(error)
    return state

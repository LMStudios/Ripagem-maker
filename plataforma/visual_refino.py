"""Segunda leitura local e limitada aos quadros mais informativos do vídeo.

Reutiliza o OCR genérico. O cache desta etapa inclui nomes e versão, pois os
recortes são dirigidos ao produto procurado. Nenhum resultado aprova um take.
"""
import json
import math
import os
import re
import subprocess
import threading
import time
from pathlib import Path

VERSION = 'refino-visual-2'
MAX_POINTS = 176
MAX_REFERENCES = 6


def weak_label(score, text, item, wanted):
    """Rótulo quase completo com prefixo distintivo; 'brain' não é VapoBrain."""
    if not item or score < .70 or float(item[1]) < .8:
        return False
    value = re.sub('[^a-z0-9]', '', text)
    for name in wanted:
        name = name.replace(' ', '')
        if len(name) < 6 or not math.ceil(.75 * len(name)) <= len(value) <= len(name) + 2:
            continue
        prefix = next((i for i, (a, b) in enumerate(zip(name, value)) if a != b), min(len(name), len(value)))
        if prefix >= min(5, len(name) - 2):
            return True
    return False


def spread(values, limit):
    count = min(limit, len(values))
    if not count:
        return []
    if count == 1:
        return [values[len(values) // 2]]
    return [values[round(i * (len(values) - 1) / (count - 1))] for i in range(count)]


def image_size(info, longest):
    scale = min(1, longest / max(info['width'], info['height']))
    return tuple(max(2, round(info[axis] * scale / 2) * 2) for axis in ('width', 'height'))


def targets(samples, changes, wanted, start, end, match, group, reference_points=None):
    """Distribui a leitura entre rótulos prováveis, suas bordas e cenas ainda sem nome."""
    points = {}

    def add(t, priority):
        t = round(t * 4) / 4
        if start <= t < end:
            points[t] = min(points.get(t, priority), priority)

    for t, texts in samples:
        score, text, item = match(texts, wanted)
        if .65 <= score < .95 and weak_label(max(score, .70), text, item, wanted):
            add(t, 0)
    spans = group(samples, changes, wanted)
    for row in spans:
        for edge in ('inicio_ms', 'fim_ms'):
            t = row[edge] / 1000
            add(t - .25, 1)
            add(t + .25, 1)

    for t in reference_points or ():
        add(t, 0)
    cuts = [t for t, difference in changes if difference >= 18 and start < t < end]
    shots = [start, *cuts, end]
    span_index = 0

    def covered(t):
        nonlocal span_index
        while span_index < len(spans) and spans[span_index]['fim_ms'] < 1000 * t:
            span_index += 1
        return span_index < len(spans) and spans[span_index]['inicio_ms'] <= 1000 * t <= spans[span_index]['fim_ms']

    for a, b in zip(shots, shots[1:]):
        length = b - a
        if length < .25:
            continue
        t = min(a + .5, (a + b) / 2) if length <= 4 else (a + b) / 2
        if not covered(t):
            add(t, 2 if length <= 1.5 else 3)

    # Mudanças de contraste menores que um corte completo também introduzem rótulos,
    # por exemplo, um pote animado sobre um fundo que continua em tela.
    span_index = 0
    last = start - 3
    for t, difference in changes:
        if 7 <= difference < 18 and t - last >= 3 and not covered(t):
            add(t, 3)
            last = t

    categories = [[] for _ in range(4)]
    for t in sorted(points):
        categories[points[t]].append(t)
    urgent, borders, short, unseen = categories
    budget_unseen = round(MAX_POINTS * .32) if short or unseen else 0
    selected = set(spread(short, round(budget_unseen * .5) if unseen else budget_unseen))
    selected.update(spread(unseen, budget_unseen - len(selected)))
    selected.update(spread(urgent, (MAX_POINTS - len(selected)) // 2 if borders else MAX_POINTS - len(selected)))
    selected.update(spread(borders, MAX_POINTS - len(selected)))
    for category in categories:
        selected.update(spread([t for t in category if t not in selected], MAX_POINTS - len(selected)))
    return sorted(selected), max(0, len(points) - len(selected))


def reference_candidates(samples, wanted, start, end, match):
    from .deteccao_visual import place
    chosen = []
    last = start - 8
    for t, rows in samples:
        if not start <= t < end or t - last < 8:
            continue
        score, _, item = match([r for r in rows if place(r) == 'imagem'], wanted)
        if score >= .99 and float(item[1]) >= .9:
            chosen.append(t)
            last = t
    return spread(chosen, MAX_REFERENCES)

def run(job, out, samples, changes, wanted, start, end, info, match, group, source_key):
    from . import deteccao_visual as D, trocas as T, ml_core as M
    refs = reference_candidates(samples, wanted, start, end, match)
    points, skipped = targets(samples, changes, wanted, start, end, match, group, refs)
    key = T.digest([VERSION, source_key, wanted, refs])
    directory = D.folder(out) / ('refino_' + key)
    directory.mkdir(parents=True, exist_ok=True)
    cache = directory / 'quadros.json'
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
            saved = {float(t): rows for t, rows in data['leituras']}
            if all(t in saved for t in points):
                return [[t,saved[t]] for t in points], {'quadros':len(points),'pendentes':skipped,'reaproveitado':True}
        except (ValueError, TypeError, KeyError, OSError): pass
    if not points:
        return [], {'quadros': 0, 'pendentes': skipped, 'reaproveitado': False}
    request = directory / 'pedido.json'
    T.write(request, {'pontos': points, 'nomes': wanted, 'referencias': refs})
    width, height = image_size(info, 1440)
    command = [M.PY, str(M.BASE / 'ocr_worker.py'), str(T.source(out)), str(directory), '--ffmpeg', M.FFMPEG,
               '--unidades', '0', '--largura', str(width), '--altura', str(height), '--threads', '2', '--refinar', str(request)]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if getattr(job,'params',{}).get('automatico') and hasattr(os,'setpriority'):
        try: os.setpriority(os.PRIO_PROCESS,proc.pid,10)
        except OSError: pass
    errors, completed = [], []
    def read_progress():
        for line in proc.stdout:
            if line.startswith('REFINO '): completed.append(line)
    def read_errors():
        for line in proc.stderr:
            errors.append(line)
            if len(errors) > 40: del errors[0]
    threads = [threading.Thread(target=fn, daemon=True) for fn in (read_progress, read_errors)]
    for thread in threads: thread.start()
    try:
        while proc.poll() is None:
            if job.cancel: raise M.Cancelled()
            job.pct = .86 + .08 * min(1, len(completed) / len(points))
            job.step = f'Conferindo rótulos e bordas dos takes · {len(completed)} de {len(points)} quadros'
            job.progress = {'tipo':'deteccao','fase':'Conferindo rótulos e bordas','processadas':len(completed),'total':len(points),'indeterminado':False}
            time.sleep(.2)
        for thread in threads: thread.join(timeout=3)
        if proc.returncode: raise RuntimeError(M.process_error(''.join(errors), proc.returncode))
        raw = directory / 'resultado.json'
        data = json.loads(raw.read_text())
        if len(data['leituras']) != len(points): raise ValueError('A conferência visual ficou incompleta. Refazer busca retoma o trabalho já lido.')
        data['estatisticas'] = {'quadros':len(points),'pendentes':skipped,'reaproveitado':False}
        T.write(cache, data)
        return data['leituras'], data['estatisticas']
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()
        for thread in threads: thread.join(timeout=3)
        for stream in (proc.stdout, proc.stderr): stream.close()

"""Referências do pote antigo marcadas pelo editor num quadro do vídeo original.

Cada referência guarda o horário, a região marcada (relativa ao quadro) e a identidade
do vídeo de origem. Se o vídeo mudar, a referência fica desatualizada e não é usada.
Os recortes ficam na pasta do projeto; nada é enviado para fora do computador.
"""
import math
import subprocess
import time
import uuid
from pathlib import Path

from . import ml_core as M, trocas as T

VERSION = 'referencias-1'
MAX_REFS = 12
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def folder(out):
    from .deteccao_visual import folder as detection
    return detection(out) / 'referencias'


def path(out): return folder(out) / 'referencias.json'


def load(out):
    import json
    try:
        data = json.loads(path(out).read_text()) if path(out).exists() else {}
    except ValueError:
        data = {}
    data.setdefault('itens', [])
    return data


def write(out, data): T.write(path(out), data)


def _identity(out):
    return T.source_identity(T.source(out))


def valid(out, data=None):
    """Referências do vídeo atual, com o recorte ainda no disco."""
    data = data or load(out)
    current = _identity(out)
    return [r for r in data['itens'] if r.get('fonte') == current and (Path(out) / r['arquivo']).is_file()]


def signature(out):
    refs = valid(out)
    return T.digest([VERSION, [[r['id'], r['t_ms'], r['caixa']] for r in refs]]) if refs else ''


def view(out):
    data = load(out)
    current = _identity(out)
    items = []
    for r in data['itens']:
        item = dict(r, valida=r.get('fonte') == current and (Path(out) / r['arquivo']).is_file())
        if not item['valida']:
            item['aviso'] = 'O vídeo original mudou: substitua esta referência por um quadro do vídeo atual.'
        items.append(item)
    return {'itens': items, 'validas': sum(i['valida'] for i in items), 'limite': MAX_REFS, 'assinatura': signature(out)}


def _duration_ms(out):
    info = T.probe(T.source(out), False)
    if not info['video']:
        raise ValueError('As referências exigem o vídeo original. Este trabalho contém somente áudio.')
    return info, round(info['duration'] * 1000)


def _time(value, duration):
    try:
        t = float(value)
    except (TypeError, ValueError):
        raise ValueError('Horário do quadro inválido.') from None
    if not math.isfinite(t) or not 0 <= t < duration:
        raise ValueError('Escolha um quadro dentro do vídeo original.')
    return round(t)


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise ValueError('Não foi possível ler este quadro do vídeo original.')


def frame(out, body):
    """Extrai o quadro pausado para o editor marcar o pote (imagem na pasta do projeto)."""
    info, duration = _duration_ms(out)
    t = _time(body.get('t_ms'), duration)
    directory = folder(out) / 'quadros'
    directory.mkdir(parents=True, exist_ok=True)
    key = T.digest([_identity(out), t])[:10]
    target = directory / f'quadro_{t:09d}_{key}.jpg'
    if not target.is_file():
        temporary = target.with_suffix('.partial.jpg')
        width = min(1920, info['width'] - info['width'] % 2)
        _run([M.FFMPEG, '-v', 'error', '-y', '-ss', f'{t / 1000:.3f}', '-i', str(T.source(out)), '-frames:v', '1',
              '-an', '-vf', f'scale={width}:-2', '-q:v', '2', str(temporary)])
        temporary.replace(target)
    # Remove quadros antigos que não viraram referência, mantendo a pasta pequena.
    used = {Path(r.get('quadro', '')).name for r in load(out)['itens']}
    olds = sorted((p for p in directory.glob('quadro_*.jpg') if p.name not in used and p != target), key=lambda p: p.stat().st_mtime)
    for old in olds[:-6]:
        old.unlink(missing_ok=True)
    return {'t_ms': t, 'arquivo': str(target.relative_to(out)), 'largura': info['width'], 'altura': info['height']}


def _box(value):
    try:
        x, y, w, h = (float(v) for v in value)
    except (TypeError, ValueError):
        raise ValueError('Marque o pote arrastando um retângulo sobre o quadro.') from None
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        raise ValueError('Marque o pote arrastando um retângulo sobre o quadro.')
    x0, y0 = max(0.0, x - w / 2), max(0.0, y - h / 2)
    x1, y1 = min(1.0, x + w / 2), min(1.0, y + h / 2)
    if x1 - x0 < .015 or y1 - y0 < .02:
        raise ValueError('A região marcada está pequena demais. Inclua o pote inteiro ou o rótulo.')
    if (x1 - x0) * (y1 - y0) > .8:
        raise ValueError('A região marcada ocupa quase todo o quadro. Marque somente o pote.')
    return [round((x0 + x1) / 2, 5), round((y0 + y1) / 2, 5), round(x1 - x0, 5), round(y1 - y0, 5)]


def _crop(out, ref_id, t, box, info):
    directory = folder(out)
    directory.mkdir(parents=True, exist_ok=True)
    width, height = info['width'], info['height']
    cx, cy, w, h = box
    pw, ph = max(16, round(w * width)), max(16, round(h * height))
    px = min(width - pw, max(0, round((cx - w / 2) * width)))
    py = min(height - ph, max(0, round((cy - h / 2) * height)))
    target = directory / f'ref_{ref_id}.png'
    thumb = directory / f'ref_{ref_id}.jpg'
    source = str(T.source(out))
    _run([M.FFMPEG, '-v', 'error', '-y', '-ss', f'{t / 1000:.3f}', '-i', source, '-frames:v', '1', '-an',
          '-vf', f'crop={pw}:{ph}:{px}:{py}', str(target)])
    _run([M.FFMPEG, '-v', 'error', '-y', '-i', str(target), '-vf', 'scale=-2:120', '-q:v', '4', str(thumb)])
    return target, thumb, [pw, ph]


def add(out, body, replace=None):
    """Salva a região confirmada pelo editor. `replace` substitui uma referência existente no mesmo lugar."""
    info, duration = _duration_ms(out)
    t = _time(body.get('t_ms'), duration)
    box = _box(body.get('caixa'))
    with T.LOCK:
        data = load(out)
        position = None
        if replace:
            position = next((i for i, r in enumerate(data['itens']) if r['id'] == replace), None)
            if position is None:
                raise ValueError('Referência não encontrada. Atualize a lista.')
        elif len(data['itens']) >= MAX_REFS:
            raise ValueError(f'Use no máximo {MAX_REFS} referências. Remova uma antes de adicionar outra.')
        if any(r['t_ms'] == t and r['caixa'] == box for r in data['itens'] if r['id'] != replace):
            raise ValueError('Esta região já é uma referência.')
    ref_id = uuid.uuid4().hex[:12]
    target, thumb, size = _crop(out, ref_id, t, box, info)
    item = {'id': ref_id, 't_ms': t, 'caixa': box, 'tamanho_px': size, 'fonte': _identity(out),
            'arquivo': str(target.relative_to(out)), 'miniatura': str(thumb.relative_to(out)),
            'quadro': str(body.get('quadro', '')), 'origem': body.get('origem', 'editor'),
            'criado': time.strftime('%Y-%m-%dT%H:%M:%S')}
    with T.LOCK:
        data = load(out)
        old = None
        if replace:
            position = next((i for i, r in enumerate(data['itens']) if r['id'] == replace), None)
            if position is None:
                target.unlink(missing_ok=True); thumb.unlink(missing_ok=True)
                raise ValueError('Referência não encontrada. Atualize a lista.')
            old = data['itens'][position]
            data['itens'][position] = item
        else:
            data['itens'].append(item)
        write(out, data)
    if old:
        _discard_files(out, old)
    return view(out)


def _discard_files(out, ref):
    for key in ('arquivo', 'miniatura'):
        file = (Path(out) / ref.get(key, '')).resolve()
        if file.is_file() and file.is_relative_to(folder(out).resolve()):
            file.unlink(missing_ok=True)


def remove(out, ref_id):
    with T.LOCK:
        data = load(out)
        ref = next((r for r in data['itens'] if r['id'] == ref_id), None)
        if not ref:
            raise ValueError('Referência não encontrada. Atualize a lista.')
        data['itens'] = [r for r in data['itens'] if r['id'] != ref_id]
        write(out, data)
    _discard_files(out, ref)
    return view(out)


def request_items(out, width, info):
    """Recortes válidos com o fator para a escala dos quadros analisados."""
    factor = width / info['width']
    return [{'id': r['id'], 'arquivo': str((Path(out) / r['arquivo']).resolve()), 'fator': factor} for r in valid(out)]

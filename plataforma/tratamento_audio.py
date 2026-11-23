"""Tratamento local dos áudios gerados: silêncio excedente nas bordas e redução de ruído suave.

Sempre parte do áudio sem tratamento (o original nunca é alterado) e grava um arquivo novo.
Pausas internas não são removidas; só o início e o fim são aparados, com margens.
"""
import copy
import hashlib
import json
import math
import subprocess
from pathlib import Path

from . import ml_core as M

RATE = 48000
FRAME = 480  # 10 ms
VERSION = 'tratamento-1'


def normalize(value):
    value = value or {}
    def number(key, low, high, default):
        v = value.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f'Valor inválido para {key}: use entre {low} e {high}.')
        return int(round(v))
    clean = {'silencio': bool(value.get('silencio', True)), 'ruido': bool(value.get('ruido', False)),
             'margem_inicio_ms': number('margem_inicio_ms', 20, 500, 80), 'margem_fim_ms': number('margem_fim_ms', 50, 800, 200),
             'intensidade': number('intensidade', 0, 100, 35)}
    if not clean['silencio'] and not clean['ruido']:
        raise ValueError('Escolha pelo menos um tratamento: silêncio nas bordas ou redução de ruído.')
    return clean


def _samples(path):
    import numpy as np
    cmd = [M.FFMPEG, '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    return np.frombuffer(raw, dtype=np.float32)


def analyze(path):
    """Energia por quadro de 10 ms: piso de ruído, fala e as bordas que podem sair sem cortar a voz."""
    import numpy as np
    x = _samples(path)
    duration = len(x) / RATE
    n = len(x) // FRAME
    if n < 5:
        return {'duracao_s': round(duration, 3), 'inicio_fala_s': 0.0, 'fim_fala_s': round(duration, 3), 'piso_db': -90.0, 'pico_db': -90.0, 'sem_fala': True}
    frames = x[:n * FRAME].reshape(n, FRAME)
    db = 20 * np.log10(np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)) + 1e-9)
    floor = float(np.percentile(db, 10))
    peak = float(np.percentile(db, 99))
    # Fala: claramente acima do piso e não muito abaixo do pico.
    threshold = max(floor + 10, peak - 40, -70)
    loud = db > threshold
    # Exige 30 ms seguidos para não confundir um estalo com o começo da fala.
    run = np.convolve(loud.astype(int), np.ones(3, dtype=int), mode='same') >= 3
    idx = np.flatnonzero(run)
    if not len(idx) or peak - floor < 6:
        return {'duracao_s': round(duration, 3), 'inicio_fala_s': 0.0, 'fim_fala_s': round(duration, 3), 'piso_db': round(floor, 1), 'pico_db': round(peak, 1), 'sem_fala': True}
    first, last = int(idx[0]), int(idx[-1])
    # Consoantes iniciais, respirações e finais de palavra decaem devagar: estende enquanto houver energia acima do piso.
    soft = floor + 6
    back = first
    while back > 0 and first - back < 15 and db[back - 1] > soft:
        back -= 1
    forward = last
    while forward < n - 1 and forward - last < 40 and db[forward + 1] > soft:
        forward += 1
    return {'duracao_s': round(duration, 3), 'inicio_fala_s': round(back * FRAME / RATE, 3), 'fim_fala_s': round((forward + 1) * FRAME / RATE, 3),
            'piso_db': round(floor, 1), 'pico_db': round(peak, 1), 'sem_fala': False}


def plan_edges(info, options):
    """Janela que fica: fala detectada + margens. Só apara o que sobra de verdade (mais de 30 ms)."""
    duration = info['duracao_s']
    if not options['silencio'] or info.get('sem_fala'):
        return 0.0, duration
    start = max(0.0, info['inicio_fala_s'] - options['margem_inicio_ms'] / 1000)
    end = min(duration, info['fim_fala_s'] + options['margem_fim_ms'] / 1000)
    if start < 0.03:
        start = 0.0
    if duration - end < 0.03:
        end = duration
    if end - start < 0.1:
        return 0.0, duration
    return start, end


def noise_filter(info, options):
    """afftdn moderado: no máximo 18 dB de redução, com rastreamento do ruído, para não soar metálico."""
    if not options['ruido'] or options['intensidade'] <= 0:
        return None
    strength = options['intensidade'] / 100
    nr = round(4 + strength * 14, 1)
    nf = min(-25.0, max(-80.0, float(info.get('piso_db', -60))))
    return f'highpass=f=60,afftdn=nr={nr}:nf={nf:.1f}:tn=1'


def signature(source, options):
    st = Path(source).stat()
    return hashlib.sha256(json.dumps([VERSION, str(Path(source).name), st.st_size, st.st_mtime_ns, options], sort_keys=True).encode()).hexdigest()[:20]


def process(job, source, target, options):
    """Grava o áudio tratado em `target` (WAV) e devolve antes/depois. A fonte não é alterada."""
    options = normalize(options)
    if job is not None:
        job.step = 'Analisando silêncio e ruído'
    info = analyze(source)
    start, end = plan_edges(info, options)
    filters = [f'atrim=start={start:.6f}:end={end:.6f}', 'asetpts=PTS-STARTPTS']
    denoise = noise_filter(info, options)
    if denoise:
        filters.append(denoise)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name('.' + target.stem + '.parcial' + target.suffix)
    if job is not None:
        job.step = 'Aplicando tratamento'
    cmd = [M.FFMPEG, '-y', '-v', 'error', '-i', str(source), '-vn', '-af', ','.join(filters), '-c:a', 'pcm_s16le', str(temporary)]
    try:
        if job is not None:
            M.run_proc(job, cmd)
        else:
            subprocess.run(cmd, capture_output=True, check=True)
        if not temporary.is_file() or temporary.stat().st_size < 100:
            raise RuntimeError('O tratamento não gerou um áudio válido. O original foi preservado.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    after = end - start
    return {'duracao_antes_s': info['duracao_s'], 'duracao_depois_s': round(after, 3), 'removido_inicio_ms': round(start * 1000),
            'removido_fim_ms': round((info['duracao_s'] - end) * 1000), 'ruido_reduzido': bool(denoise), 'filtro_ruido': denoise,
            'piso_db': info['piso_db'], 'sem_fala_detectada': info.get('sem_fala', False), 'opcoes': options}


# ------------------------------------------------------------------ áudios das trocas
FIT_KEYS = ('raw', 'duracao_s', 'alvo_s', 'diferenca_ms', 'texto_hash', 'aprovado', 'fit', 'status', 'timeline_frames', 'modo_duracao')


def _untreated(audio):
    treated = audio.get('tratamento') or {}
    return treated.get('origem') or audio.get('fonte_preparo') or audio.get('raw')


def _target(out, row, plan):
    import re
    number = next((i for i, r in enumerate(plan['itens'], 1) if r['id'] == row['id']), 1)
    safe = lambda text: re.sub(r'[^A-Za-z0-9_-]+', '_', str(text)).strip('_')[:48] or 'Produto'
    directory = Path(out) / 'trocas' / 'tratados'
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{number:03d}_Speaker_{safe(row['speaker'])}_{safe(plan.get('produto_novo'))}_TRATADO"
    target, version = directory / (stem + '.wav'), 2
    while target.exists():
        target = directory / f'{stem}_V{version:02d}.wav'
        version += 1
    return target


def _refit(job, out, rid, source, extra, drop=(), allow_short=True):
    from . import trocas as T
    from . import editorial as E
    plan, row = E.get_row(out, rid)
    old = copy.deepcopy(row.get('audio') or {})
    fresh = T.fit(job, out, row, source, True, allow_short=allow_short)
    keep = {k: v for k, v in old.items() if k not in FIT_KEYS and k not in drop}
    fresh = keep | fresh
    fresh['raw'] = old['raw']
    fresh.update(extra)
    T.record_audio(out, rid, fresh)
    return fresh


def treat_rows(job, out, ids, options):
    """Trata uma ou várias falas. Não reaplica sobre um áudio já tratado com as mesmas opções."""
    from . import trocas as T
    options = normalize(options)
    plan = T.load(out)
    rows = {r['id']: r for r in plan['itens']}
    results, skipped = [], []
    for i, rid in enumerate(ids):
        if job is not None:
            if job.cancel:
                raise M.Cancelled()
            job.pct = i / max(1, len(ids))
            job.progress = {'tipo': 'tratamento', 'fase': 'Tratando áudios', 'processadas': i, 'total': len(ids), 'indeterminado': False}
        row = rows.get(rid)
        audio = (row or {}).get('audio') or {}
        if not row or not audio.get('raw'):
            skipped.append({'id': rid, 'motivo': 'Sem áudio gerado ou importado.'})
            continue
        base = Path(out) / _untreated(audio)
        if not base.is_file():
            skipped.append({'id': rid, 'motivo': 'Áudio sem tratamento não encontrado.'})
            continue
        sig = signature(base, options)
        if (audio.get('tratamento') or {}).get('assinatura') == sig and audio.get('fit'):
            skipped.append({'id': rid, 'motivo': 'Já tratado com estas opções.'})
            continue
        if job is not None:
            job.step = f'Tratando áudio {i + 1} de {len(ids)}'
        target = _target(out, row, plan)
        report = process(job, base, target, options)
        report.update(assinatura=sig, origem=str(base.relative_to(out)), arquivo=str(target.relative_to(out)))
        fresh = _refit(job, out, rid, target, {'fonte_preparo': str(target.relative_to(out)), 'tratamento': report})
        results.append({'id': rid, 'tratamento': report, 'audio': fresh})
    if job is not None:
        job.pct = 1
        job.step = 'Tratamento concluído — ouça e aprove novamente'
    return {'tratados': results, 'ignorados': skipped, 'observacao': 'Original preservado. A duração mudou nos áudios tratados: a montagem, os takes e o XML usam os novos tempos; prévia e entrega anteriores ficam desatualizadas.'}


def undo_row(job, out, rid):
    from . import editorial as E
    plan, row = E.get_row(out, rid)
    audio = row.get('audio') or {}
    treated = audio.get('tratamento')
    if not treated:
        raise ValueError('Esta fala não tem tratamento para desfazer.')
    base = Path(out) / treated['origem']
    if not base.is_file():
        raise ValueError('O áudio sem tratamento não foi encontrado; não é possível desfazer.')
    extra = {'fonte_preparo': treated['origem']} if treated['origem'] != audio.get('raw') else {}
    fresh = _refit(job, out, rid, base, extra, drop=('tratamento', 'fonte_preparo'))
    return {'id': rid, 'audio': fresh, 'observacao': 'Tratamento desfeito. O arquivo tratado continua na pasta trocas/tratados; ouça e aprove novamente.'}


# ------------------------------------------------------------------ ferramenta avulsa
def standalone_job(job, files, options, folder):
    """Trata arquivos enviados à ferramenta avulsa, sem projeto. Cada original fica ao lado do tratado."""
    folder = Path(folder)
    done = []
    for i, name in enumerate(files):
        if job.cancel:
            raise M.Cancelled()
        job.progress = {'tipo': 'tratamento', 'fase': 'Tratando áudios', 'processadas': i, 'total': len(files), 'indeterminado': False}
        job.pct = i / max(1, len(files))
        source = folder / name
        target = folder / (Path(name).stem + '_TRATADO.wav')
        report = process(job, source, target, options)
        done.append(report | {'original': name, 'tratado': target.name})
    (folder / 'relatorio_tratamento.json').write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding='utf-8')
    job.pct = 1
    job.step = 'Tratamento concluído'
    from . import armazenamento as S
    return {'pasta': str(folder), 'relativo': S.tool_relative(folder), 'arquivos': done}

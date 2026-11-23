"""Relatório local e fila de sincronização por editor, sem mídias ou caminhos no resumo remoto."""
import json
import math
import platform
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import armazenamento, projetos
from .diagnostico import atomic_text

OUTBOX = armazenamento.PROJECT / 'plataforma/workspace/relatorios_pendentes'
LOCK = threading.RLock()
SYNC_LOCK = threading.Lock()
MAX_MS = 30 * 24 * 60 * 60 * 1000
REPORT = 'relatorio_ripagem.json'
STAGES = {
    'transcricao': 'transcricao', 'vozes': 'voz', 'deteccao_visual': 'busca_visual',
    'visual_preparo': 'takes', 'visual_fresta': 'takes', 'visual_automatico': 'takes',
    'entrega_rapida': 'exportacao', 'entrega_final': 'exportacao',
}
FEEDBACK_STAGES = set(STAGES.values()) | {'legenda', 'outro'}


def _read(path, default=None):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else default
    except (OSError, ValueError):
        return default


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _milliseconds(seconds):
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        return None
    return min(MAX_MS, round(seconds * 1000))


def record_operation(out, identifier, kind, status, seconds, *, inicio=None, repeticao=False):
    stage = STAGES.get(kind)
    if not stage or not out or status not in ('concluido', 'erro', 'cancelado'):
        return
    out = Path(out).resolve()
    if not armazenamento.is_job(out):
        return
    path = out / 'trocas/metricas_ripagem.json'
    with LOCK:
        operations = _read(path, {})
        started = round(inicio * 1000) if isinstance(inicio, (int, float)) and math.isfinite(inicio) else None
        operations[str(identifier)] = {'etapa': stage, 'estado': status, 'duracao_ms': _milliseconds(seconds),
                                       'inicio_ms': started, 'retrabalho': bool(repeticao)}
        _write(path, operations)


def _metrics(out):
    operations = _read(out / 'trocas/metricas_ripagem.json', {})
    durations = {}
    failures = {}
    rework = []
    for operation in operations.values():
        if not isinstance(operation, dict) or operation.get('etapa') not in STAGES.values():
            continue
        stage, elapsed = operation['etapa'], operation.get('duracao_ms')
        if isinstance(elapsed, int) and 0 <= elapsed <= MAX_MS:
            durations[stage] = min(MAX_MS, durations.get(stage, 0) + elapsed)
        if operation.get('estado') == 'erro':
            failures[stage] = failures.get(stage, 0) + 1
        start = operation.get('inicio_ms')
        if operation.get('retrabalho') and isinstance(start, int) and isinstance(elapsed, int) and elapsed >= 0:
            rework.append((start, start + elapsed))
    total = 0
    previous = 0
    for a, b in sorted(rework):
        total += max(0, b - max(a, previous))
        previous = max(previous, b)
    return durations, failures, len(operations), min(MAX_MS, total) if rework else None


def _visuals(out):
    from . import conferencia_visual
    try:
        state = conferencia_visual.summary(out)
    except (ValueError, OSError, KeyError):
        return {}, 0
    a, c = state['aparicoes'], state['cobertura']
    return ({
        'sugeridas': max(0, a.get('total', 0) - a.get('manuais', 0)),
        'aprovadas': a.get('aprovadas', 0), 'descartadas': a.get('descartadas', 0),
        'manuais': a.get('manuais', 0), 'marcadas': c.get('aparicoes_marcadas', 0),
    }, c.get('frestas', 0) + c.get('marcadas', 0))


def _queue(summary):
    path = OUTBOX / summary['usuario'] / (summary['projeto_id'] + '.json')
    _write(path, summary)


def saved(out, profile, studio, applied):
    """Primeiro XML fixa autor e duração; novas versões alimentam o mesmo relatório."""
    if not profile or not studio.get('medicao_encerrada'):
        return
    out = Path(out)
    with LOCK:
        project_id = projetos.read_meta(out)['projeto_id']
        path = out / REPORT
        old = _read(path, {})
        summary = dict(old.get('resumo') or {
            'projeto_id': project_id, 'usuario': profile['id'],
            'tempo_ripagem_ms': _milliseconds(studio['app_min'] * 60) if studio['app_min'] is not None else None,
            'medicao_completa': studio['completa'], 'espera_ms': None, 'retrabalho_ms': None, 'fora_app_ms': None,
            'versao_app': (armazenamento.PROJECT / 'VERSION').read_text(encoding='utf-8').strip(),
            'feedback_etapa': None,
            'sistema': {'Darwin': 'macOS', 'Windows': 'Windows', 'Linux': 'Linux'}.get(platform.system(), 'Outro'),
        })
        stages, failures, attempts, rework = _metrics(out)
        visuals, gaps = _visuals(out)
        summary.update(revisao=summary.get('revisao', 0) + 1, etapas_ms=stages, tentativas=attempts, retrabalho_ms=rework, falhas=sum(failures.values()),
                       xml_revisao=studio.get('xml_de_revisao', False), pendencias_visuais=gaps, visuais=visuals)
        event = {'usuario': profile['id'], 'xml': Path(studio['xml_salvo']).name, 'quando': _timestamp()}
        old.update(resumo=summary, falhas_por_etapa=failures, codigo_aplicado=applied, ultimo_salvamento=event)
        _write(path, old)
        _queue(summary)
    schedule_sync(profile['id'])


def read(out, profile):
    report = _read(Path(out) / REPORT)
    if not report:
        raise ValueError('Salve um XML deste projeto para criar o relatório.')
    if report['resumo']['usuario'] != profile['id'] and profile['funcao'] != 'administrador':
        raise PermissionError('O relatório pertence ao editor que salvou a primeira entrega.')
    return report


def feedback(out, profile, body):
    with LOCK:
        report = read(out, profile)
        summary = report['resumo']
        if summary['usuario'] != profile['id']:
            raise PermissionError('O editor que salvou a primeira entrega pode registrar o feedback.')
        stage = body.get('etapa') or None
        if stage is not None and stage not in FEEDBACK_STAGES:
            raise ValueError('Escolha uma etapa válida.')
        mins = body.get('minutos')
        if mins is not None and (isinstance(mins, bool) or not isinstance(mins, (int, float)) or not math.isfinite(mins) or not 0 <= mins <= MAX_MS / 60_000):
            raise ValueError('Informe os minutos de trabalho externo.')
        comment = body.get('comentario', '')
        if not isinstance(comment, str) or len(comment) > 1000:
            raise ValueError('Use até 1000 caracteres na observação.')
        report['observacao_local'] = comment.strip()
        summary.update(revisao=summary.get('revisao', 0) + 1, feedback_etapa=stage, fora_app_ms=round(mins * 60_000) if mins is not None else None)
        _write(Path(out) / REPORT, report)
        _queue(summary)
    schedule_sync(profile['id'])
    return report


def _sync(owner):
    from . import equipe_auth
    try:
        for path in sorted((OUTBOX / owner).glob('*.json'))[:30]:
            pending = _read(path)
            if not pending or pending.get('usuario') != owner:
                continue
            try:
                equipe_auth.sync_report(pending)
            except equipe_auth.AuthError:
                return
            with LOCK:
                if _read(path) == pending:
                    path.unlink(missing_ok=True)
    finally:
        SYNC_LOCK.release()


def schedule_sync(owner):
    if not owner:
        return
    to_send = next((OUTBOX / owner).glob('*.json'), None)
    if to_send and SYNC_LOCK.acquire(blocking=False):
        threading.Thread(target=_sync, args=(owner,), name='ripagem-relatorios', daemon=True).start()

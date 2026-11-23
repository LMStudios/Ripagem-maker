"""Preferências visuais e medição local por projeto, sem serviços externos."""
import hashlib
import json
import math
from pathlib import Path
import threading
import time

from . import armazenamento as S
from .diagnostico import atomic_text

LOCK = threading.RLock()
CONFIG = S.PROJECT / 'plataforma/workspace/studio.json'
DEFAULTS = {'tutorial': None, 'minutos_por_mencao': 5.0, 'minutos_modo_uso': 60.0}

def read(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else default.copy()
    except (OSError, ValueError): return default.copy()

def write(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    atomic_text(Path(path), json.dumps(data, ensure_ascii=False, indent=2))

def preferences(changes=None):
    with LOCK:
        raw = read(CONFIG, {})
        result = DEFAULTS.copy()
        for name in ('minutos_por_mencao', 'minutos_modo_uso'):
            value = raw.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1440:
                result[name] = value
        if raw.get('tutorial') in ('guiado', 'direto'): result['tutorial'] = raw['tutorial']
        if changes is not None:
            if not isinstance(changes, dict): raise ValueError('Configuração inválida.')
            for name in ('minutos_por_mencao', 'minutos_modo_uso'):
                if name in changes:
                    value = changes[name]
                    if isinstance(value, bool): raise ValueError('Informe uma duração válida.')
                    try: value = float(value)
                    except (ValueError, TypeError): raise ValueError('Informe uma duração válida.')
                    if not math.isfinite(value) or not 0 <= value <= 1440:
                        raise ValueError('Use uma duração entre 0 e 1440 minutos.')
                    result[name] = value
            if 'tutorial' in changes:
                if changes['tutorial'] not in ('guiado', 'direto'): raise ValueError('Escolha guiado ou direto.')
                result['tutorial'] = changes['tutorial']
            write(CONFIG, result)
        return result

def create(out, started=None):
    """Só novos projetos recebem medição completa; projetos antigos continuam identificados como parciais."""
    with LOCK:
        now = time.time()
        write(Path(out) / 'tempo_studio.json', {'formato': 1, 'completa': True,
              'segundos': max(0, now - (started or now)), 'ultimo': now, 'pausado': False})

def heartbeat(out, paused=None, plan=None, closing=False):
    with LOCK:
        path = Path(out) / 'tempo_studio.json'
        now = time.time()
        data = read(path, {'formato': 1, 'completa': False, 'segundos': 0, 'ultimo': now, 'pausado': False})
        if paused is not None and not isinstance(paused, bool): raise ValueError('Estado da pausa inválido.')
        completion = data.get('conclusao') or {}
        if completion.get('salvo'):
            return data
        if plan is not None and completion and (not completion.get('legenda') or not current_completion(out, data, plan)):
            data.pop('conclusao', None)
            data['ultimo'] = now
        delta = max(0., now - float(data.get('ultimo', now)))
        # Uma janela não duplica a contagem de outra. Lacunas longas não viram trabalho.
        if delta <= 20 and not data.get('pausado') and not data.get('conclusao'):
            data['segundos'] = float(data.get('segundos', 0)) + delta
        data['ultimo'] = 0 if closing else now
        if paused is not None:
            data['pausado'] = paused
        write(path, data)
        return data

def selection(plan):
    rows = [r for r in plan.get('itens', []) if r.get('aprovado')]
    spans = sorted((float(r['inicio_ms']), float(r['fim_ms'])) for r in rows)
    unique = []
    for start, end in spans:
        if unique and start < unique[-1][1]: unique[-1][1] = max(end, unique[-1][1])
        else: unique.append([start, end])
    usage = not plan.get('somente_valores') and bool(plan.get('forma', {}).get('ativo'))
    return len(unique), usage

def signature(plan):
    # A validade da montagem pode mudar depois que o tempo de edição já foi registrado.
    core = [{k: row.get(k) for k in ('id', 'inicio_ms', 'fim_ms', 'novo', 'speaker', 'aprovado', 'audio')}
            for row in plan.get('itens', [])]
    return hashlib.sha256(json.dumps([core, plan.get('forma'), plan.get('somente_valores'), plan.get('trilha'), plan.get('modo_duracao')], sort_keys=True).encode()).hexdigest()

def _existing_file(out, relative, suffix):
    if not isinstance(relative, str) or not relative:
        return None
    root = Path(out).resolve()
    name = Path(relative.replace('\\', '/'))
    if name.is_absolute() or '..' in name.parts:
        return None
    path = (root / name).resolve()
    if path.is_relative_to(root) and path.suffix.lower() == suffix and path.is_file() and path.stat().st_size > 0:
        return path
    return None


def confirm_xml_save(out, relative, plan, *, download=None):
    """Confirma a cópia feita pelo usuário, inclusive após uma exportação avulsa de montagem."""
    path = _existing_file(out, relative, '.xml')
    if path is None or not path.is_relative_to(Path(out).resolve() / 'trocas'):
        raise ValueError('Confirme um XML de entrega deste projeto para encerrar a medição.')
    name = path.relative_to(Path(out).resolve()).as_posix()
    registered = next((r for r in (plan.get('entrega_revisao'), plan.get('entrega'))
                       if isinstance(r, dict) and _existing_file(out, r.get('xml'), '.xml') == path), None)
    report_path = _existing_file(out, path.with_suffix('.json').relative_to(Path(out).resolve()).as_posix(), '.json')
    report = read(report_path, {}) if report_path else {}
    if registered is None and (_existing_file(out, report.get('arquivo'), '.xml') != path
                               or not {'nomenclatura', 'itens', 'conferencia_mencoes'} <= report.keys()):
        raise ValueError('Este XML não pertence a uma montagem de entrega deste projeto.')
    result = registered or report
    caption = report.get('entrega_final') or {}
    destination = None
    if download is not None:
        source = _existing_file(out, download, '.xml')
        if source != path:
            source = _existing_file(out, download, '.zip')
            if source is None or registered is None or _existing_file(out, registered.get('pacote'), '.zip') != source:
                raise ValueError('O pacote não corresponde ao XML deste trabalho.')
        from .native_files import copy_to_downloads
        destination = copy_to_downloads(source)
    summary = finish(out, result | {'xml': name}, plan, montagem=result.get('assinatura'), caption=caption)
    return dict(summary, destino=destination) if destination else summary


def finish(out, result, plan, montagem=None, *, caption=None):
    """Registra o salvamento sem voltar a medir numa nova exportação ou na etapa de legenda."""
    path = _existing_file(out, result.get('xml'), '.xml')
    if path is None:
        raise ValueError('Gere e confirme o XML antes de encerrar a medição.')
    name = path.relative_to(Path(out).resolve()).as_posix()
    with LOCK:
        time_path = Path(out) / 'tempo_studio.json'
        data = read(time_path, {})
        previous = data.get('conclusao') or {}
        if previous.get('salvo') and previous.get('xml') == name:
            return summary(out, plan)
        data = heartbeat(out, plan=plan)
        previous = data.get('conclusao') or {}
        completion = {'xml': name, 'assinatura': signature(plan), 'quando': previous.get('quando', data['ultimo']),
                      'montagem': montagem, 'salvo': True, 'revisao': result.get('revisao_pendencias') is True}
        if caption and _confirmed_caption(out, caption):
            completion.update(legenda=caption['legenda'], legenda_sha256=caption['legenda_sha256'])
        data.update(conclusao=completion, pausado=False)
        write(time_path, data)
    return summary(out, plan)


def _confirmed_caption(out, completion):
    sub = _existing_file(out, completion.get('legenda'), '.srt')
    return bool(sub and hashlib.sha256(sub.read_bytes()).hexdigest() == completion.get('legenda_sha256'))


def current_completion(out, data, plan):
    completion = data.get('conclusao') or {}
    if not completion or completion.get('assinatura') != signature(plan): return False
    xml = (Path(out) / completion.get('xml', '')).resolve()
    if not xml.is_relative_to(Path(out).resolve()) or not xml.is_file(): return False
    if not completion.get('salvo') and completion.get('legenda') and not _confirmed_caption(out, completion): return False
    montage = completion.get('montagem')
    if not completion.get('salvo'):
        montage = montage or (plan.get('entrega') or {}).get('assinatura')
    if montage:
        from . import trocas as T
        try: return montage == T.preview_signature(out)
        except (OSError, ValueError, KeyError): return False
    return True

def summary(out, plan):
    data = read(Path(out) / 'tempo_studio.json', {})
    config = preferences()
    count, usage = selection(plan)
    manual = count * config['minutos_por_mencao'] + (config['minutos_modo_uso'] if usage else 0)
    completion = data.get('conclusao') or {}
    valid = current_completion(out, data, plan)
    review = bool(completion.get('revisao'))
    final_complete = valid and not review and _confirmed_caption(out, completion)
    stopped = bool(completion.get('salvo') or final_complete)
    measured = float(data.get('segundos', 0)) / 60
    saving = manual - measured
    return {'mencoes': count, 'modo_uso': usage, 'manual_min': manual, 'app_min': measured if data else None,
            'completa': bool(data.get('completa')), 'final_completa': final_complete, 'pausado': bool(data.get('pausado')), 'entrega_valida': valid and not review, 'medicao_encerrada': stopped,
            'xml_salvo': completion.get('xml') if stopped else None, 'xml_de_revisao': review,
            'economia_min': saving if valid and data.get('completa') else None,
            'percentual': round(saving / manual * 100, 1) if valid and data.get('completa') and manual > 0 else None,
            'xml': completion.get('xml') if valid else None, 'parametros': config,
            'referencia': 'Desde a seleção do arquivo nesta versão; inclui envio, processamento e revisão com o projeto aberto até salvar o XML. Pausas e períodos com o projeto fechado ficam fora da contagem.'}

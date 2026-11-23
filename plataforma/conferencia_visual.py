"""Resumo da conferência visual: próxima pendência ao reabrir e números da entrega.

Só lê o estado salvo; nada é recalculado nem apagado. Reaproveita a busca, os takes
e a entrega quando ainda correspondem à montagem atual.
"""
from pathlib import Path

from . import ml_core as M, trocas as T


def _running(out):
    out = Path(out).resolve()
    return next((j for j in list(M.JOBS.values())
                 if j.kind in ('deteccao_visual', 'visual_automatico', 'visual_preparo', 'visual_fresta')
                 and j.status in ('na_fila', 'executando') and Path(j.params.get('out', '')).resolve() == out), None)


def summary(out):
    from . import deteccao_visual as D, visuais as V, workflow as W
    out = Path(out)
    result = {'proxima': None, 'aparicoes': {}, 'cobertura': {}, 'entrega': {}}
    try:
        plan = T.load(out)
    except (ValueError, OSError):
        return result
    if plan.get('somente_valores'):
        result['somente_valores'] = True
    detection = D.view(out) if D.path(out).exists() else {'intervalos': []}
    items = detection.get('intervalos', [])
    approved = [i for i in items if i['status'] == 'aprovado']
    pending = [i for i in items if i['status'] == 'sugerido' and not i.get('coberto_pela_fala')]
    early_only = [i for i in approved if i.get('antes_da_mencao') and not detection.get('cobrir_antes_da_mencao')]
    result['aparicoes'] = {'total': len(items), 'aprovadas': len(approved), 'para_revisar': len(pending),
                           'descartadas': sum(i['status'] == 'descartado' for i in items),
                           'por_referencia': sum('referencia' in i.get('evidencias', []) for i in items),
                           'manuais': sum(i.get('origem') == 'manual' for i in items),
                           'so_marcacao': len(early_only), 'aviso': detection.get('desatualizado') or ''}
    gaps = {'preparado': False, 'frestas': [], 'marcadas': []}
    if V.path(out).exists():
        try:
            gaps = V.gap_report(out)
        except ValueError as error:
            gaps = {'preparado': False, 'frestas': [], 'marcadas': [], 'mensagem': str(error)}
    marked_ids = {a for m in gaps.get('marcadas', []) for a in m.get('aparicoes', [])}
    open_ids = {a for p in gaps.get('frestas', []) for a in p.get('aparicoes', [])}
    to_cover = [i for i in approved if i not in early_only]
    result['cobertura'] = {'preparado': bool(gaps.get('preparado')), 'frestas': len(gaps.get('frestas', [])),
                           'marcadas': len(gaps.get('marcadas', [])),
                           'cobertas': sum(i['id'] not in open_ids and i['id'] not in marked_ids for i in to_cover) if gaps.get('preparado') else 0,
                           'aparicoes_marcadas': len(marked_ids), 'a_cobrir': len(to_cover), 'mensagem': gaps.get('mensagem', '')}
    flow = T.flow_state(out)
    delivery = flow.get('entrega') or {}
    result['entrega'] = {'atual': bool(flow.get('entrega_atual')), 'revisao_atual': bool(flow.get('entrega_revisao_atual')),
                         'xml': delivery.get('xml_nome') if delivery.get('xml_existe') else ''}
    try:
        ready = W.state(out)['takes_liberados']
    except (ValueError, OSError, KeyError):
        ready = False
    job = _running(out)
    visual = V.load(out) if V.path(out).exists() else {}
    prepared_ok = False
    if visual.get('prepared'):
        try:
            prepared_ok = bool(V.valid_prepared(out, False) is not None) and not gaps.get('frestas')
        except ValueError:
            prepared_ok = False
    if not ready:
        result['proxima'] = None
    elif job:
        result['proxima'] = {'acao': 'aguardar', 'rotulo': 'Acompanhar ' + job.title.lower(), 'etapa': 4, 'job': job.to_dict()}
    elif pending:
        result['proxima'] = {'acao': 'revisar_aparicoes', 'rotulo': f'Revisar {len(pending)} aparição(ões)', 'etapa': 4}
    elif gaps.get('frestas'):
        n = len(gaps['frestas'])
        result['proxima'] = {'acao': 'frestas', 'rotulo': f'Resolver {n} fresta' + ('s' if n > 1 else ''), 'etapa': 4}
    elif visual.get('incluir') and not prepared_ok and not visual.get('sem_takes'):
        result['proxima'] = {'acao': 'preparar_takes', 'rotulo': 'Preparar os takes', 'etapa': 4}
    elif not flow.get('entrega_atual'):
        result['proxima'] = {'acao': 'salvar_xml', 'rotulo': 'Salvar XML', 'etapa': 6}
    else:
        result['proxima'] = {'acao': 'concluido', 'rotulo': 'Entrega atual salva', 'etapa': 6}
    return result


def takes_for(out, item_id):
    """Takes em V2 que cobrem uma aparição, para a revisão lado a lado."""
    from . import deteccao_visual as D, visuais as V, montagem as MT, fechamento as FC
    from .armazenamento import visual_margin_ms
    out = Path(out)
    detection = D.view(out)
    item = next((i for i in detection.get('intervalos', []) if i['id'] == item_id), None)
    if not item:
        raise ValueError('Aparição não encontrada. Atualize a lista.')
    info = T.probe(T.source(out), False)
    fps = info['fps']
    result = {'id': item_id, 'inicio_ms': item['inicio_ms'], 'fim_ms': item['fim_ms'],
              'cobertura_inicio_ms': item.get('cobertura_inicio_ms', item['inicio_ms']),
              'cobertura_fim_ms': item.get('cobertura_fim_ms', item['fim_ms']), 'takes': [], 'frestas': [], 'preparado': False}
    if not V.path(out).exists():
        return result
    state = V.load(out)
    prepared = state.get('prepared') or {}
    segments = prepared.get('segments') or []
    result['preparado'] = bool(prepared) and prepared.get('signature') == V.signature(state)
    plan = T.load(out)
    approved = [r for r in plan['itens'] if r.get('aprovado') and r.get('audio', {}).get('fit')]
    changes = MT.edits(out, approved, info)
    final = bool(prepared.get('timeline_final'))
    closed = FC.windows(changes, fps) if any(s.get('timeline_fechada') for s in segments) else []
    position = (lambda ms: FC.position(MT.shift(round(ms / 1000 * fps), changes), closed)) if final else (lambda ms: round(ms / 1000 * fps))
    a, b = position(result['cobertura_inicio_ms']), position(result['cobertura_fim_ms'])
    assets = {x['id']: x for x in state.get('assets', [])}
    folder_name = out.name
    for index, segment in enumerate(segments):
        if segment['end_frame'] <= a or segment['start_frame'] >= b:
            continue
        asset = assets.get(segment['asset'], {})
        if segment.get('source_original'):
            url = '/fatiador/visual-media/' + folder_name + '/' + segment['asset']
        else:
            url = '/files/' + folder_name + '/' + segment['file']
        result['takes'].append({'indice': index, 'asset': segment['asset'], 'nome': asset.get('name', ''), 'kit': segment.get('kit'),
                                'url': url, 'inicio_s': round(segment['start_frame'] / fps, 3), 'fim_s': round(segment['end_frame'] / fps, 3),
                                'cobre_de_s': round(max(a, segment['start_frame']) / fps, 3), 'cobre_ate_s': round(min(b, segment['end_frame']) / fps, 3)})
    if result['preparado']:
        report = V.gap_report(out)
        result['frestas'] = [p for p in report.get('frestas', []) if item_id in p.get('aparicoes', [])]
    result['margem_visual_ms'] = visual_margin_ms()
    return result

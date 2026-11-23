"""Entrega final somente com legenda atual e conferida; XML avulso continua independente."""
import hashlib
import uuid
import zipfile
from pathlib import Path
from . import trocas as T, legendas as L, deteccao_visual as DV


def caption(out):
    plan = T.load(out)
    state = L.view(out)
    result = state.get('resultado') or {}
    imported = plan.get('validacao_srt') or {}
    if imported.get('montagem_assinatura') == T.preview_signature(out) and not imported.get('resquicios') and imported.get('arquivo'):
        candidate = imported['arquivo']
        warnings = []
    elif result and not state.get('desatualizado'):
        candidate = result.get('arquivo')
        warnings = result.get('avisos', [])
    else:
        candidate = None
        warnings = []
    if not candidate: return None
    path = (Path(out) / candidate).resolve()
    if not path.is_relative_to(Path(out).resolve()) or not path.is_file() or not path.stat().st_size: return None
    from .srt_corretor import parse
    data = path.read_bytes()
    text = data.decode('utf-8-sig')
    parse(text)
    if not plan.get('somente_valores') and plan.get('produto', '').casefold() != plan.get('produto_novo', '').casefold():
        from .srt_corretor import product_only
        _, report = product_only(text, plan.get('produto', ''), plan.get('produto_novo', ''), plan.get('produto_aliases', ''))
        if report.get('mencoes_antigas'): raise ValueError('A legenda ainda contém o nome do produto antigo. Corrija os nomes na etapa 6.')
    digest = hashlib.sha256(data).hexdigest()
    return {'arquivo': candidate, 'sha256': digest, 'avisos': len(warnings),
            'assinatura': T.digest([T.preview_signature(out), candidate, digest])}


def state(out, automatic_job=None):
    from .workflow import state as workflow
    from . import ml_core as M
    plan = T.load(out)
    problems = []
    if any(j is not automatic_job and j.kind != 'entrega_completa' and j.status in ('na_fila', 'executando') and Path(j.params.get('out', '')).resolve() == Path(out).resolve() for j in list(M.JOBS.values())):
        problems.append('Há materiais sendo preparados neste projeto. Aguarde as tarefas terminarem.')
    speech = workflow(out)
    if not speech['takes_liberados']: problems.append('Conclua as falas e aprove os áudios na etapa 3.')
    caption_problem = ''
    try: sub = caption(out)
    except ValueError as error: sub = None; caption_problem = str(error)
    if not sub: problems.append(caption_problem or 'Prepare uma legenda atual da montagem na etapa 6.')
    checked = plan.get('legenda_conferida') or {}
    if sub and checked.get('assinatura') != sub['assinatura']: problems.append('Confira a legenda e confirme a revisão na etapa 6.')
    soundtrack_pending = plan.get('trilha', {}).get('modo', 'nao_definida') == 'nao_definida'
    if soundtrack_pending: problems.append('Escolha e salve a trilha na etapa Legenda.')
    from . import visuais as VIS
    visual_plan = VIS.load(out)
    if not visual_plan.get('sem_takes'):
        try:
            if not visual_plan.get('prepared') or visual_plan.get('issues'): raise ValueError('Takes pendentes.')
            VIS.valid_prepared(out)
        except ValueError: problems.append('Prepare os takes atuais na etapa 4.')
    # Não há verificação visual em projetos só de áudio ou de otimização de preços.
    visual = DV.view(out)
    if visual.get('tem_video') and visual.get('automatico', True) and not plan.get('somente_valores'):
        if visual.get('tarefa'): problems.append('A busca visual está em andamento. Aguarde a conclusão.')
        elif not visual.get('analise') or visual.get('desatualizado'): problems.append('Conclua a busca visual ou desative-a explicitamente neste projeto.')
        elif any(r.get('status') == 'sugerido' and not r.get('coberto_pela_fala') for r in visual.get('intervalos', [])): problems.append('Revise as sugestões de produto antigo na etapa Takes.')
    delivery = T.flow_state(out)
    info = delivery['entrega']
    info['atual'] = bool(delivery['entrega_atual'] and sub and info.get('legenda_assinatura') == sub['assinatura'])
    return {'pronto': not problems, 'pendencias': problems, 'legenda': sub, 'legenda_conferida': bool(sub and checked.get('assinatura') == sub['assinatura']),
            'assinatura': T.preview_signature(out), 'entrega': info, 'trilha_pendente': soundtrack_pending, 'xml_atual': delivery['entrega_atual']}


def confirm(out, checked, automatic_job=None):
    if checked is False:
        with T.LOCK:
            plan = T.load(out); plan.pop('legenda_conferida', None); T.write(T.plan_path(out), plan)
        return state(out)
    if checked is not True: raise ValueError('Confira a legenda antes de confirmar.')
    sub = caption(out)
    if not sub: raise ValueError('Gere ou importe uma legenda válida e atual antes de confirmar.')
    with T.LOCK:
        plan = T.load(out)
        plan['legenda_conferida'] = {'assinatura': sub['assinatura'], 'arquivo': sub['arquivo']}
        if automatic_job: plan['legenda_conferida']['automatica'] = True
        T.write(T.plan_path(out), plan)
    return state(out, automatic_job)


def package(out, result, sub):
    """XML e SRT da mesma versão, lado a lado e num único download."""
    out = Path(out).resolve()
    xml, report, caption = [(out / name).resolve() for name in (result['xml'], result['json'], sub['arquivo'])]
    if any(not p.is_relative_to(out) or not p.is_file() for p in (xml, report, caption)):
        raise ValueError('Não foi possível localizar o XML, o relatório e a legenda desta entrega.')
    data = caption.read_bytes()
    if hashlib.sha256(data).hexdigest() != sub['sha256']:
        raise ValueError('A legenda mudou durante a entrega. Confira novamente.')
    sidecar, bundle = xml.with_suffix('.srt'), xml.with_suffix('.zip')
    tmp = bundle.with_name('.' + uuid.uuid4().hex + '.zip.tmp')
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(xml, xml.name)
            z.writestr(sidecar.name, data)
            z.write(report, report.name)
            z.writestr('IMPORTAR NO PREMIERE.txt',
                       'Extraia este ZIP. Importe o XML e o SRT no Premiere. Abra a sequência do XML e arraste o SRT '
                       'para o início da timeline. O Premiere criará a faixa de legendas editável. '
                       'O XML referencia as mídias originais: preserve os arquivos e suas pastas.\n')
        from .diagnostico import atomic_bytes
        atomic_bytes(sidecar, data)
        tmp.replace(bundle)
    finally:
        tmp.unlink(missing_ok=True)
    return {'pacote': bundle.relative_to(out).as_posix(), 'legenda_entrega': sidecar.relative_to(out).as_posix()}


def deliver(job, out, sem_previa=False, assinatura=None, automatic_job=None):
    current = state(out, automatic_job)
    if not current['pronto']: raise ValueError('Entrega incompleta: ' + ' '.join(current['pendencias']))
    sub = current['legenda']
    # Mantém todas as verificações existentes de áudios, takes e assinatura.
    if sem_previa:
        result = T.fast_delivery_job(job, out, True, persist=False)
        result['autorizacao'] = 'Lote autorizado sem assistir à prévia'
    else:
        result = T.export_reviewed(out, assinatura, persist=False)
    with T.LOCK:
        from . import ml_core as M
        if job.cancel:
            raise M.Cancelled()
        latest = state(out, automatic_job)
        if not latest['pronto'] or latest['legenda']['assinatura'] != sub['assinatura']:
            raise ValueError('A montagem ou a legenda mudou durante a entrega. Confira novamente.')
        plan = T.load(out)
        result = result | {'legenda': sub['arquivo'], 'legenda_assinatura': sub['assinatura'],
                           'assinatura': latest['assinatura'], 'completa': True}
        from . import legendas_video as LV
        video_state = LV.load(out); video = video_state.get('final')
        if video:
            try:
                media = (Path(out) / video['arquivo']).resolve()
                if media.is_relative_to(Path(out).resolve()) and media.is_file() and video.get('assinatura') == LV.signature(out, video_state['estilo']): result['video'] = video['arquivo']
            except (OSError, ValueError, KeyError): pass
        report_path = (Path(out) / result['json']).resolve()
        if not report_path.is_relative_to(Path(out).resolve()): raise ValueError('Caminho do relatório inválido.')
        import json
        report = json.loads(report_path.read_text(encoding='utf-8'))
        report['entrega_final'] = {'legenda': sub['arquivo'], 'legenda_sha256': sub['sha256'], 'conferida': True, 'video': result.get('video')}
        if automatic_job:
            report['entrega_final']['conferencia_automatica'] = bool(plan['legenda_conferida'].get('automatica'))
            report['entrega_final']['falas_aprovadas_automaticamente'] = sum(bool(r.get('audio', {}).get('aprovacao_automatica')) for r in plan['itens'])
        sidecar_name = Path(result['xml']).with_suffix('.srt').as_posix()
        report['entrega_final']['legenda_ao_lado_do_xml'] = sidecar_name
        T.write(report_path, report)
        result.update(package(out, result, sub))
        plan['entrega'] = result
        T.write(T.plan_path(out), plan)
    job.step = 'Entrega completa · XML, relatório e legenda conferida'
    return result

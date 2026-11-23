"""Fluxo opt-in por projeto. Reusa o motor manual e deixa pendências recuperáveis."""
import json
import re
from pathlib import Path

from . import formas as FORMS, ml_core as M, ofertas as O, trocas as T

KIND = 'ripagem_automatica'
RUNNING = {'na_fila', 'executando'}


def path(out):
    return Path(out) / 'trocas' / 'automatico.json'


def load(out):
    file = path(out)
    return json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}


def validate(config, prices):
    if config.get('autoriza') is not True:
        raise ValueError('Autorize este projeto a usar a transcrição e as vozes configuradas.')
    root = str(config.get('pasta', '')).strip()
    if not root or not Path(root).is_absolute() or not Path(root).is_dir():
        raise ValueError('Escolha uma pasta de takes que exista neste computador.')
    from .visuais import inventory
    if not inventory(root):
        raise ValueError('A pasta dos takes está vazia ou não contém materiais compatíveis.')
    demand = str(config.get('demanda', '')).strip()
    if prices:
        O.config({'demanda': demand})
    form = FORMS.normalize(config.get('forma'))
    voices = config.get('vozes', {})
    if not isinstance(voices, dict) or len(voices) > 20 or any(
        not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', s) or not isinstance(v, str)
        or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', v) for s, v in voices.items()
    ):
        raise ValueError('Use um ID de voz válido por speaker, como A=id_da_voz.')
    return {'pasta': str(Path(root).resolve()), 'demanda': demand, 'forma': form,
            'vozes': voices, 'autoriza': True, 'renderizar_video': config.get('renderizar_video') is True}


def initialize(out, config, product):
    with T.LOCK:
        T.write(path(out), {'config': config, 'produto': product or '', 'estado': 'preparando',
                            'fase': 'textos', 'mensagem': 'Transcrição concluída.', 'textos': False})
    return submit(out)


def jobs_for(out, kind=None):
    root = Path(out).resolve()
    return [job for job in list(M.JOBS.values()) if job.status in RUNNING and
            (kind is None or job.kind == kind) and job.params.get('out') and
            Path(job.params['out']).resolve() == root]


def active(out):
    return next(iter(jobs_for(out, KIND)), None)


def view(out):
    state = load(out)
    if not state:
        return {'ativo': False}
    job = active(out)
    status = state['estado']
    message = state['mensagem']
    if not job and status in ('preparando', 'executando'):
        status, message = 'pausado', 'A execução foi interrompida. Retome a partir do último material salvo.'
    delivery = state.get('entrega')
    if delivery and not job:
        from .finalizacao import state as final_state
        if not final_state(out)['entrega']['atual']:
            delivery = None
            message = 'A montagem ou os arquivos mudaram. Prepare uma nova entrega na etapa Entrega.'
    return {'ativo': True, 'estado': status, 'fase': state['fase'], 'mensagem': message,
            'job': {'id': job.id, 'passo': job.step} if job else None,
            'entrega': delivery}


def submit(out):
    out = Path(out).resolve()
    with M.STORAGE.LOCK:
        state = load(out)
        if not state:
            raise ValueError('Este projeto foi iniciado no modo manual.')
        running = active(out)
        if running:
            return running
        if state['estado'] == 'concluido':
            raise ValueError('A execução automática já concluiu este projeto.')
        if jobs_for(out):
            raise ValueError('Aguarde terminar a tarefa em execução neste projeto antes de retomar.')
        return M.submit(KIND, 'Ripagem automática', run, 'render', dedupe_key=str(out), out=str(out))


def pause(out):
    job = active(out)
    if job:
        queued = job.status == 'na_fila'
        M.cancel_job(job.id)
        if queued and job.status == 'cancelado':
            state = load(out)
            state.update(estado='pausado', pausa_manual=True, mensagem='Execução pausada por você.')
            T.write(path(out), state)
    return view(out)


def resume_on_edit(out, action):
    state = load(out)
    if state.get('estado') != 'pausado' or state.get('pausa_manual') or jobs_for(out):
        return
    triggers = {
        'textos': {'salvar', 'speaker-confirmar', 'forma', 'ofertas-adaptar', 'plano'},
        'vozes': {'preferencias-voz-salvar', 'aprovar-audio'},
        'takes': {'deteccao-revisar', 'visual-salvar', 'visual-adicionar', 'deteccao-automatico'},
        'legendas': {'finalizacao-confirmada'},
    }
    if action not in triggers.get(state['fase'], set()):
        return
    try:
        plan = T.load(out)
        rows = candidates(plan)
        if any(row.get('mencoes_revisar') and not row.get('aprovado') and not row.get('mencao_descartada') for row in rows):
            return
        T.approved(plan | {'itens': [row | {'aprovado': True} for row in rows]})
        submit(out)
    except ValueError:
        pass


def candidates(plan):
    return [row for row in plan['itens']
            if (not row.get('mencao_descartada') or row.get('novo_sem_sugestoes')) and (row['novo'].strip() != row['original'].strip() or row.get('forma_pendente'))]


def prepare_offer_mentions(out, rows):
    from . import visuais as VIS

    if any(len(row.get('ofertas_incluidas', [])) != 1 for row in rows):
        raise ValueError('Uma fala reúne vários kits ou usa troca avulsa. Associe os takes aos kits em Takes para evitar mostrar uma quantidade errada.')
    if not T.load(out).get('somente_valores') and VIS.first_product_mention(out) is None:
        raise ValueError('Não encontrei a primeira menção do produto no vídeo. Confira a identificação em Falas e os intervalos em Takes.')
    state = VIS.load(out)
    state.update(mentions=[
        {'id': T.digest(['oferta', row['id']]), 'start': row['inicio_ms'], 'end': row['fim_ms'],
         'kit': row['ofertas_incluidas'][0], 'selected': True, 'text': row['novo']}
        for row in rows
    ], basis=VIS.basis(out))
    VIS.write(out, state)


def verify_offer_audio(job, out):
    from collections import Counter
    from . import legendas as L, valores as VAL

    def amounts(text):
        return Counter(VAL.price_key(match) for match in VAL.RX_PRICE.finditer(text))

    tmap = L.TimeMap(out)
    for item, heard in zip(tmap.replaced(), L.clip_words(job, out, tmap), strict=True):
        expected = amounts(item['row']['novo'])
        spoken = amounts(' '.join(word['w'] for word in heard))
        if expected - spoken:
            timestamp = round(item['inicio'])
            raise ValueError(f'Não consegui confirmar todos os preços no áudio em {timestamp // 60:02d}:{timestamp % 60:02d}. '
                             'Confira o áudio e a legenda antes de retomar.')


def run(job, out):
    from . import credenciais as C, deteccao_visual as DV, editorial as E, experiencia as X
    from . import finalizacao as F, legendas as L, legendas_video as LV, otimizacao as OT, valores as VAL
    from . import visuais as VIS, vozes as V, workflow as W

    out = Path(out)
    state = load(out)
    config = state['config']

    def checkpoint(fase, mensagem, estado='executando', **data):
        state.update(fase=fase, mensagem=mensagem, estado=estado, **data)
        T.write(path(out), state)
        job.step = mensagem

    def phase(name, message):
        if job.cancel:
            raise M.Cancelled()
        checkpoint(name, message, pausa_manual=False)

    try:
        phase('textos', 'Preparando as falas a partir da transcrição')
        prices = OT.active(out)
        if not T.plan_path(out).exists():
            if not state['produto']:
                raise ValueError('Informe o produto original em Falas e busque os trechos.')
            T.build(out, state['produto'])
        plan = T.load(out)
        if not state['textos']:
            if prices:
                saved = out / 'trocas' / 'ofertas.json'
                if not saved.exists():
                    O.apply(out, O.preview(out, config, VAL.RX_PRICE, VAL.price_key))
            elif config['forma']['ativo'] and not plan.get('forma', {}).get('ativo'):
                T.build(out, plan['produto'], plan.get('incluir_precos', False), config['forma'])
            checkpoint('textos', 'Falas identificadas', textos=True)
        plan = T.load(out)
        selected = {row['id'] for row in candidates(plan)}
        if not selected:
            raise ValueError('Nenhuma fala para trocar foi encontrada. Confira o produto ou a oferta em Falas.')
        if any(row.get('mencoes_revisar') and not row.get('aprovado') and not row.get('mencao_descartada') for row in candidates(plan)):
            raise ValueError('Há menções com grafia aproximada. Confira os trechos marcados em Falas e selecione as menções corretas antes de retomar.')
        changes = [{'id': row['id'], 'aprovado': row['id'] in selected} for row in plan['itens']
                   if bool(row.get('aprovado')) != (row['id'] in selected)]
        if changes:
            plan = T.save(out, changes)
        T.approved(plan)
        X.cached_pitch(out)

        phase('vozes', 'Verificando vozes e gerando os áudios que faltam')
        speech = W.state(out)
        if speech['estado'] == 'pronto_para_gerar':
            prefs = X.preferences(out)
            provider = prefs.get('provider', 'elevenlabs')
            model = prefs.get('model') or ('speech-2.8-hd' if provider == 'minimax' else 'eleven_multilingual_v2')
            options = {'provider': provider, 'model': model, 'autofit': True,
                       'somente_pendentes': True, 'autoriza_envio': True}
            rows = V.selected_rows(T.load(out), options, out)
            mapping = config['vozes'] | {speaker: voice for speaker, voice in (prefs.get('voices') or {}).items() if voice.strip()}
            missing = sorted({r['speaker'] for r in rows if not mapping.get(r['speaker'], '').strip()})
            if missing:
                T.sample_job(job, out)
                raise ValueError('Defina a voz para speaker ' + ', '.join(missing) +
                                 ' em Gerar falas por speaker. As amostras locais estão disponíveis.')
            options['voices'] = mapping
            key = V.validate(out, options)
            result = V.generate(job, out, options, key)
            error = next((r['erro'] for r in result['resultados'] if 'erro' in r), None)
            if error:
                raise ValueError(error)
        if job.cancel:
            raise M.Cancelled()
        with T.LOCK:
            plan = T.load(out)
            for row in T.approved(plan):
                audio = row.get('audio', {})
                if (not audio.get('fit') or not (out / audio['fit']).is_file() or
                    audio.get('texto_hash') != T.digest([row['novo'], row['speaker']]) or
                    audio.get('modo_duracao', 'fixo') != plan.get('modo_duracao', 'fixo')):
                    raise ValueError('Há uma fala sem áudio válido. Confira a geração e o encaixe em Falas.')
                if not audio.get('aprovado'):
                    if audio.get('analise', {}).get('alertas'):
                        raise ValueError('Um áudio tem alertas. Ouça e aprove em Falas antes de retomar.')
                    audio.update(aprovado=True, aprovacao_automatica=True)
            T.write(T.plan_path(out), plan)

        phase('takes', 'Procurando o produto antigo e preparando os takes')
        visual = DV.view(out)
        if not prices and visual.get('automatico') and visual.get('tem_video'):
            if visual.get('tarefa'):
                raise ValueError('A busca visual está em andamento. Retome quando ela terminar.')
            if not visual.get('analise') or visual.get('desatualizado'):
                DV.analyze_job(job, out)
                visual = DV.view(out)
            if any(r['status'] == 'sugerido' and not r['coberto_pela_fala'] for r in visual['intervalos']):
                raise ValueError('Há possíveis aparições do produto antigo. Confira as sugestões em Takes.')
        visual_plan = VIS.load(out)
        if not visual_plan.get('sem_takes'):
            if prices and not visual_plan.get('mentions'):
                prepare_offer_mentions(out, T.approved(T.load(out)))
            VIS.automatic(job, out, visual_plan.get('root') or config['pasta'], visual_plan.get('max_clip_s', 6))

        phase('legendas', 'Gerando legendas e conferindo o áudio da montagem')
        plan = T.load(out)
        if plan.get('trilha', {}).get('modo', 'nao_definida') == 'nao_definida':
            E.soundtrack(out, {'modo': 'original'})
        sub = F.caption(out)
        if not sub:
            L.generate_job(job, out)
            sub = F.caption(out)
        if not sub:
            raise ValueError('A legenda ficou vazia. Confira os ajustes na etapa Legendas.')
        checked = T.load(out).get('legenda_conferida') or {}
        if checked.get('assinatura') != sub['assinatura']:
            if sub['avisos']:
                raise ValueError('A conferência local encontrou alertas na legenda. Confira os trechos em Legendas.')
            if prices:
                verify_offer_audio(job, out)
            F.confirm(out, True, automatic_job=job)

        if config.get('renderizar_video'):
            phase('legendas', 'Renderizando o vídeo com legendas')
            rendered = LV.view(out).get('final') or {}
            if not rendered.get('atual') or not (out / rendered['arquivo']).is_file():
                LV.render_job(job, out)

        phase('entrega', 'Exportando XML, relatório e legenda')
        result = F.deliver(job, out, sem_previa=True, automatic_job=job)
        checkpoint('entrega', 'Entrega automática pronta.', 'concluido', entrega=result)
        return result
    except M.Cancelled:
        checkpoint(state['fase'], 'Execução interrompida. Os materiais salvos podem ser reutilizados.', 'pausado', pausa_manual=True)
        raise
    except Exception as error:
        if job.cancel:
            checkpoint(state['fase'], 'Execução interrompida. Os materiais salvos podem ser reutilizados.', 'pausado', pausa_manual=True)
            raise M.Cancelled() from None
        from .diagnostico import redact
        message = redact(M.friendly_error(error, job))
        checkpoint(state['fase'], message, 'pausado')
        return {'pendencia': message, 'fase': state['fase']}

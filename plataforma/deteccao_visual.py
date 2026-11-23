"""Produto antigo na imagem: leitura local do nome nos quadros, revisão humana e marcadores no XML.

A leitura (OCR) é guardada por unidade de 60 s, ligada ao arquivo de origem: mudar o nome, os
aliases ou a janela só recalcula os intervalos; cancelar preserva as unidades concluídas.
Os intervalos são sugestões até a aprovação explícita e ficam no tempo do vídeo original.
"""
import json
import math
import os
import re
import subprocess
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

from . import ml_core as M, trocas as T

VERSION = 'ocr-1'
UNIT_S = 60.0
WIDTH = 960
MARGIN_S = 120          # janela começa 2 min antes da 1ª menção falada (aparições visuais vêm antes do nome)
HIGH, MEDIUM, LOW = .95, .85, .8
JOIN_S = 2.0           # une leituras positivas separadas por até uma leitura perdida
STATUSES = ('sugerido', 'aprovado', 'descartado')


def folder(out): return Path(out) / 'trocas/visuais/deteccao'
def path(out): return folder(out) / 'estado.json'


def load(out):
    state = json.loads(path(out).read_text()) if path(out).exists() else {}
    if not state:
        try:
            plan = T.load(out)
            state = {'nome': plan.get('produto', ''), 'aliases': ', '.join(a for a in [plan.get('produto_aliases', ''), plan.get('editorial', {}).get('aliases', '')] if a)}
        except (ValueError, OSError):
            state = {'nome': '', 'aliases': ''}
    state.setdefault('automatico', True)
    state.setdefault('janela', 'apos_mencao')
    state.setdefault('intervalos', [])
    state.setdefault('analise', None)
    return state


def write(out, state): T.write(path(out), state)


def norm(text):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def names(state):
    return [n for n in dict.fromkeys(norm(x) for x in [state.get('nome', '')] + re.split(r'[,;\n]', state.get('aliases', ''))) if n]


def source_key(out):
    return T.digest([VERSION, 'chave-2', *T.source_identity(T.source(out)), WIDTH])


def legacy_keys(out):
    """Chaves gravadas por versões anteriores (com o caminho do vídeo em qualquer forma Unicode)."""
    src = T.source(out)
    stat = src.stat()
    return [T.digest([VERSION, text, stat.st_size, stat.st_mtime_ns, WIDTH]) for text in T.legacy_path_texts(src)]


def legacy_cache_valid(out, key):
    """Leitura gravada por versão anterior: vale se for mais nova que o vídeo (um vídeo trocado depois fica mais novo que ela)."""
    old = folder(out) / ('ocr_' + str(key))
    try:
        return old.is_dir() and old.stat().st_mtime_ns >= T.source(out).stat().st_mtime_ns
    except (OSError, ValueError):
        return False


def cache(out):
    target = folder(out) / ('ocr_' + source_key(out))
    if not target.exists():
        # Leitura feita por uma versão anterior do mesmo vídeo: reaproveita em vez de ler tudo de novo.
        stored = (load(out).get('analise') or {}).get('chave')
        for key in legacy_keys(out) + ([stored] if stored else []):
            if (folder(out) / ('ocr_' + key)).is_dir() and (key in legacy_keys(out) or legacy_cache_valid(out, key)):
                (folder(out) / ('ocr_' + key)).rename(target)
                break
    return target


def window(out, state):
    """Intervalo analisado, em segundos do vídeo original."""
    info = T.probe(T.source(out), False)
    first = None
    try:
        from .visuais import first_product_mention
        first = first_product_mention(out)
    except (ValueError, OSError, KeyError):
        pass
    start = 0.0 if state.get('janela') == 'video_inteiro' or first is None else max(0.0, first / 1000 - MARGIN_S)
    return start, info['duration'], first, info


def config(out, body):
    with T.LOCK:
        state = load(out)
        if 'automatico' in body:
            if not isinstance(body['automatico'], bool): raise ValueError('Escolha válida para a busca automática.')
            state['automatico'] = body['automatico']
        nome = str(body.get('nome', state.get('nome', ''))).strip()
        if not norm(nome):
            raise ValueError('Informe o nome do produto antigo como aparece no rótulo.')
        janela = body.get('janela', state.get('janela'))
        if janela not in ('apos_mencao', 'video_inteiro'):
            raise ValueError('Janela de análise inválida.')
        cover_early = body.get('cobrir_antes_da_mencao', state.get('cobrir_antes_da_mencao', False))
        if not isinstance(cover_early, bool):
            raise ValueError('Escolha válida para cobrir aparições anteriores à primeira menção.')
        state.update(nome=nome, aliases=str(body.get('aliases', state.get('aliases', ''))).strip()[:500],
                     janela=janela, cobrir_antes_da_mencao=cover_early)
        write(out, state)
        return view(out, state)


def automatic(out, enabled=None):
    out = Path(out)
    with T.LOCK:
        state = load(out)
        if enabled is not None:
            if not isinstance(enabled, bool): raise ValueError('Configuração de busca inválida.')
            state['automatico'] = enabled
            write(out, state)
        if not state.get('automatico', True):
            for job in list(M.JOBS.values()):
                if job.kind == 'deteccao_visual' and job.status in ('na_fila', 'executando') and Path(job.params.get('out', '')).resolve() == out.resolve():
                    M.cancel_job(job.id)
            return {'situacao': 'desativado'}
        plan = T.load(out)
        if plan.get('somente_valores'): return {'situacao': 'somente_valores'}
        if not names(state):
            state['nome'] = plan.get('produto', '')
            state['aliases'] = plan.get('produto_aliases', '')
        if not names(state): return {'situacao': 'aguardando_nome'}
        if not T.probe(T.source(out), False)['video']: return {'situacao': 'somente_audio'}
        from .visual_refino import VERSION as refinement_version
        reason_text = outdated(out, state) if state.get('analise') else 'Ainda não analisado.'
        if state.get('analise') and not reason_text: return {'situacao': 'concluido'}
        # Referências novas aguardam o editor pedir a busca. Um aprimoramento da busca roda uma
        # única vez sozinho (a leitura já feita é reaproveitada e as revisões são preservadas).
        if state.get('analise') and reason_text == REFS_CHANGED: return {'situacao': 'concluido', 'aviso': reason_text}
        key = T.digest([source_key(out), names(state), state['janela'], refinement_version, LIMITS_VERSION])
        active = next((j for j in list(M.JOBS.values()) if j.kind == 'deteccao_visual' and j.status in ('na_fila', 'executando') and Path(j.params.get('out', '')).resolve() == out.resolve()), None)
        if active: return {'situacao': active.status, 'job': active.to_dict()}
        if state.get('auto_tentativa') == key: return {'situacao': 'ja_solicitado'}
        state['auto_tentativa'] = key
        write(out, state)
        job = M.submit('deteccao_visual', 'Busca automática do produto antigo na imagem', analyze_job, 'visual', dedupe_key=str(out.resolve()), out=str(out), automatico=True)
        return {'situacao': job.status, 'job': job.to_dict()}


# ---------- análise ----------

def units(start, end):
    first = math.floor(start / UNIT_S) * UNIT_S
    return [round(first + i * UNIT_S, 3) for i in range(max(1, math.ceil((end - first) / UNIT_S)))]


def unit_file(directory, start): return directory / f'unidade_{start:09.3f}.jsonl'


def workers():
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def frame_size(info):
    width = min(WIDTH, info['width'] - info['width'] % 2)
    return width, max(2, round(width * info['height'] / info['width'] / 2) * 2)


def run_workers(job, out, pending, info, directory=None, extra=(), label='Lendo o nome nos quadros', phase='Leitura dos quadros',
                span=(.05, .85)):
    directory = directory or cache(out)
    directory.mkdir(parents=True, exist_ok=True)
    width, height = frame_size(info)
    background = getattr(job, 'params', {}).get('automatico', False)
    count = min(2 if background else workers(), len(pending))
    groups = [pending[i::count] for i in range(count)]
    total = len(pending)
    done = []
    procs = []
    errors = []
    lock = threading.Lock()

    def follow(proc):
        for line in proc.stdout:
            if line.startswith('UNIDADE '):
                with lock:
                    done.append(line.split()[1])

    def drain(proc):
        tail = proc.stderr.read()
        if proc.wait() != 0:
            errors.append(M.process_error(tail, proc.returncode))

    threads = []
    try:
        for group in groups:
            cmd = [M.PY, str(M.BASE / 'ocr_worker.py'), str(T.source(out)), str(directory), '--ffmpeg', M.FFMPEG,
                   '--unidades', ','.join(f'{u:.3f}' for u in group), '--duracao', str(UNIT_S),
                   '--largura', str(width), '--altura', str(height), '--threads', str(1 if background else max(1, (os.cpu_count() or 2) // count)), *extra]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if background and hasattr(os, 'setpriority'):
                try: os.setpriority(os.PRIO_PROCESS, proc.pid, 10)
                except OSError: pass
            procs.append(proc)
            for fn in (follow, drain):
                thread = threading.Thread(target=fn, args=(proc,), daemon=True)
                thread.start()
                threads.append(thread)
        while any(p.poll() is None for p in procs):
            if job.cancel:
                raise M.Cancelled()
            with lock:
                finished = len(done)
            job.pct = span[0] + span[1] * finished / total
            job.step = f'{label} · {finished} de {total} minuto(s) · {count} processo(s)'
            job.progress = {'tipo': 'deteccao', 'fase': phase, 'processadas': finished, 'total': total, 'indeterminado': False}
            time.sleep(.4)
        for thread in threads:
            thread.join(timeout=5)
        if errors:
            raise RuntimeError(errors[0].replace('do motor de transcrição', 'da leitura de texto'))
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    stream.close()


def read_samples(directory, unit_list, start, end):
    reads, changes = {}, []
    for u in unit_list:
        file = unit_file(directory, u)
        for line in file.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if not start - 1 <= row['t'] <= end + 1:
                continue
            if 'd' in row:
                # Uma troca localizada é candidata a refinamento, sem ser tratada como corte de plano.
                changes.append((row['t'], max(7, row['d']) if row.get('local') else row['d']))
            elif 'ocr' in row:
                reads[row['t']] = row['ocr']
            elif 'igual' in row:
                reads[row['t']] = ('igual', row['igual'])
    for t, value in sorted(reads.items()):
        if isinstance(value, tuple):
            reads[t] = reads.get(value[1], [])
    return sorted(reads.items()), sorted(changes)


def match(texts, wanted):
    """Melhor semelhança entre o nome e janelas de palavras lidas; tolera erros de leitura e nome em duas caixas."""
    tokens = [(word, item) for item in texts for word in norm(item[0]).split()]
    best = (0.0, '', None)
    for name in wanted:
        size = len(name.split())
        compact = name.replace(' ', '')
        for k in range(max(1, size - 1), size + 2):
            for i in range(len(tokens) - k + 1):
                window_text = ' '.join(w for w, _ in tokens[i:i + k])
                boxes = [item for _, item in tokens[i:i + k]]
                if max(x[2] for x in boxes) - min(x[2] for x in boxes) > .20:
                    continue
                positioned = [box for box in boxes if len(box) >= 6]
                if positioned and max(box[4] - box[3]/2 for box in positioned) > min(box[4] + box[3]/2 for box in positioned) + .12:
                    continue  # evita unir palavras de rótulos diferentes na mesma altura
                score = max(SequenceMatcher(None, name, window_text).ratio(), SequenceMatcher(None, compact, window_text.replace(' ', '')).ratio())
                if len(compact) >= 6 and compact.isalpha():
                    seen = window_text.replace(' ', '')
                    for translation in ({'0':'o','5':'s','1':'i'}, {'0':'o','5':'s','1':'l'}):
                        mapped = seen.translate(str.maketrans(translation))
                        score = max(score, SequenceMatcher(None, compact, mapped).ratio())
                if score > best[0]:
                    best = (score, window_text, tokens[i][1])
    return best


REFERENCE_TAGS = {'referencia_visual': 'rotulo', 'referencia_editor': 'referencia'}
EVIDENCE = {
    'nome_lido': 'Nome lido no rótulo',
    'legenda': 'Nome na legenda gravada',
    'rotulo': 'Parecido com o rótulo lido em outro quadro',
    'referencia': 'Parecido com a referência',
    'acompanhado': 'Aparição acompanhada entre quadros',
    'manual': 'Marcada pelo editor',
}


def reference_hit(item):
    return bool(item and len(item) >= 7 and item[6] in REFERENCE_TAGS)


def evidence_of(item, where):
    if reference_hit(item):
        return REFERENCE_TAGS[item[6]]
    return 'legenda' if where == 'legenda' else 'nome_lido'


def place(item):
    """Legenda gravada: caixa baixa e larga com frase; senão, nome na imagem (rótulo, tela)."""
    if item is None:
        return 'imagem'
    if reference_hit(item):
        return 'imagem'
    text, _, y, width = item[:4]
    return 'legenda' if y >= .68 and width >= .2 and len(norm(text).split()) >= 3 else 'imagem'


def cut_between(changes, a, b):
    inside = [(d, t) for t, d in changes if a < t <= b]
    if not inside:
        return None
    d, t = max(inside)
    return t if d >= 18.0 else None


def group(samples, changes, wanted):
    from .visual_refino import weak_label
    scored = []
    for t, texts in samples:
        score, text, item = match(texts, wanted)
        # O nome na legenda gravada indica que o narrador o fala ali, mesmo com o rótulo também visível.
        subtitle = match([x for x in texts if place(x) == 'legenda'], wanted)[0] >= MEDIUM
        weak = place(item) == 'imagem' and weak_label(score, text, item, wanted)
        scored.append((t, score, text, place(item), subtitle, weak, float(item[1]) if item else 0, reference_hit(item), item))
    items, current = [], None
    for index, (t, score, text, where, subtitle, weak, ocr_score, reference, item) in enumerate(scored):
        if score < LOW and not weak:
            if current:
                if current['negativo_desde'] is None:
                    current['negativo_desde'] = t
                current['ultimo_negativo'] = t
            continue
        before = scored[index - 1][0] if index else t - 1
        after = scored[index + 1][0] if index + 1 < len(scored) else t + 1
        separated = current and (
            current['negativo_desde'] is not None and current['ultimo_negativo'] - current['negativo_desde'] >= .4
            # Corte de cena entre duas leituras: aparições distintas, mesmo sem leitura negativa no meio.
            or cut_between(changes, current['ultimo'], t) is not None
        )
        note = (score, text, where, ocr_score, reference, t, item)
        if current and t - current['ultimo'] <= JOIN_S + 1e-6 and not separated:
            current.update(ultimo=t, depois=after)
            current['notas'].append(note)
        else:
            current = {'primeiro': t, 'ultimo': t, 'antes': before, 'depois': after, 'notas': [note], 'legendas': []}
            items.append(current)
        if subtitle:
            current['legendas'].append(round(t * 1000))
        current['negativo_desde'] = current['ultimo_negativo'] = None
    result = []
    for it in items:
        a = cut_between(changes, it['antes'], it['primeiro'])
        b = cut_between(changes, it['ultimo'], it['depois'])
        start = a if a is not None else (it['antes'] + it['primeiro']) / 2
        end = b if b is not None else (it['ultimo'] + it['depois']) / 2
        read_notes = [n for n in it['notas'] if not n[4]]
        best = max(read_notes or it['notas'], key=lambda n: (n[0], n[3]))
        places = {n[2] for n in it['notas']}
        kinds = list(dict.fromkeys(evidence_of(n[6], n[2]) for n in it['notas']))
        # Caixa do pote para acompanhar a entrada e a saída: referência do editor ou rótulo com posição.
        boxed = [n for n in it['notas'] if n[6] is not None and len(n[6]) >= 6 and n[2] == 'imagem']
        anchor = max(boxed, key=lambda n: (n[0], n[3])) if boxed else best
        box = [anchor[6][4], anchor[6][2], anchor[6][3], anchor[6][5]] if anchor[6] is not None and len(anchor[6]) >= 6 else None
        refs = sorted({n[6][7] for n in it['notas'] if n[6] is not None and len(n[6]) >= 8 and n[6][6] == 'referencia_editor'})
        result.append({'inicio_ms': round(max(0, start) * 1000), 'fim_ms': round(end * 1000), 'nota': round(best[0], 3), 'texto': best[1],
                       'local': 'imagem' if 'imagem' in places else 'legenda', 'leituras': len(it['notas']), 'legenda_ms': it['legendas'], 'ocr_confianca': best[3],
                       'encaixe_corte': [s for s, v in (('inicio', a), ('fim', b)) if v is not None],
                       'referencia_visual': not read_notes, 'evidencias': kinds, 'referencias': refs,
                       'primeiro_s': it['primeiro'], 'ultimo_s': it['ultimo'], 'antes_s': it['antes'], 'depois_s': it['depois'],
                       'ancora_s': anchor[5], 'caixa': box})
    return result


def confidence(item):
    # Correspondência só por aparência entra na revisão, nunca no lote de confiança alta.
    if item.get('referencia_visual'):
        return 'revisar'
    if item['nota'] >= HIGH and item.get('ocr_confianca', 1) >= .85 and (item['leituras'] >= 2 or item['local'] == 'imagem'):
        return 'alta'
    return 'media' if item['nota'] >= MEDIUM else 'revisar'


def motives(item):
    """Motivos curtos mostrados no card, na ordem de força da evidência."""
    kinds = item.get('evidencias') or (['rotulo'] if item.get('referencia_visual') else ['legenda' if item.get('local') == 'legenda' else 'nome_lido'])
    order = ['manual', 'nome_lido', 'legenda', 'referencia', 'rotulo', 'acompanhado']
    return [EVIDENCE[k] for k in order if k in kinds]


def reason(item):
    if item.get('origem') == 'manual':
        return 'Aparição marcada pelo editor no player.'
    if item.get('referencia_visual'):
        source = ('a referência marcada pelo editor' if 'referencia' in item.get('evidencias', [])
                  else f'o rótulo de “{item["texto"]}” lido em outro quadro')
        text = f'Aparência parecida com {source}. Confira na imagem.'
    else:
        where = 'na legenda gravada' if item['local'] == 'legenda' else 'na imagem (rótulo ou tela)'
        text = f'Nome lido {where}: “{item["texto"]}” · {round(item["nota"] * 100)}% parecido · {item["leituras"]} leitura(s)'
    if 'acompanhado' in item.get('evidencias', []):
        text += ' · entrada e saída acompanhadas quadro a quadro'
    return text


def fala_windows(out):
    try:
        from . import visuais as V, armazenamento as A
        visual = V.load(out)
        if not visual.get('incluir') or not visual.get('cobrir_falas') or visual.get('sem_takes') or visual.get('issues'):
            return []
        first = V.first_product_mention(out)
        if first is None: return []
        margin = A.visual_margin_ms()
        return [(max(first, r['inicio_ms'] - margin), r['fim_ms'] + margin)
                for r in T.load(out).get('itens', []) if r.get('aprovado') and r['fim_ms'] > first]
    except (ValueError, OSError):
        return []


def uncovered_ms(item, windows):
    pieces = [(item['inicio_ms'], item['fim_ms'])]
    for a, b in windows:
        pieces = [p for lo, hi in pieces for p in ((lo, min(hi, a)), (max(lo, b), hi)) if p[1] > p[0]]
    return sum(b - a for a, b in pieces)


def merge_review(old, new):
    """Preserva aprovação, descarte e ajustes quando a nova análise acha o mesmo trecho."""
    used = set()
    for item in new:
        length = item['fim_detectado_ms'] - item['inicio_detectado_ms']
        overlaps = [(min(item['fim_detectado_ms'], o['fim_detectado_ms']) - max(item['inicio_detectado_ms'], o['inicio_detectado_ms']), o) for o in old if o['id'] not in used]
        # Mesma aparição: a maior parte de um dos dois está dentro do outro. Bordas ajustadas
        # quadro a quadro ou leituras unidas no mesmo plano não perdem a revisão já feita.
        matches = [(span, o) for span, o in overlaps if span > 0 and span >= .5 * min(length, o['fim_detectado_ms'] - o['inicio_detectado_ms'])]
        if not matches:
            # Parte de uma aparição já revisada que um corte dividiu: vale a decisão do editor
            # para aquela área (só quando o pedaço está quase todo dentro dela).
            inside = [o for o in old if o['id'] in used and length > 0 and
                      min(item['fim_detectado_ms'], o['fim_detectado_ms']) - max(item['inicio_detectado_ms'], o['inicio_detectado_ms']) >= .9 * length]
            if inside:
                item.update(status=inside[0].get('status', 'sugerido'), parte_de=inside[0]['id'])
            continue
        span, prior = max(matches, key=lambda x: x[0])
        statuses = {o.get('status', 'sugerido') for _, o in matches}
        status = (statuses.pop() if len(statuses) == 1 else
                  'aprovado' if 'aprovado' in statuses and 'descartado' not in statuses else 'sugerido')
        reviewed = sum(o['fim_detectado_ms'] - o['inicio_detectado_ms'] for _, o in matches)
        if status == 'aprovado' and length > 1.5 * reviewed + 3000:
            # A aprovação não passa para uma área muito maior que a revisada: confira a ampliação.
            status = 'sugerido'
            item['ampliada'] = True
            item['motivo'] = item.get('motivo', '') + ' · aparição ampliada pelo acompanhamento entre quadros: confira antes de aprovar'
        item.update(id=prior['id'], status=status)
        if len(matches) > 1:
            item['revisoes_unidas'] = len(matches)
        used.update(o['id'] for _, o in matches)
        if prior.get('ajustado'):
            item.update(inicio_ms=prior['inicio_ms'], fim_ms=prior['fim_ms'], ajustado=True)
    return new


def thumbnails(out, items):
    directory = folder(out) / 'miniaturas'
    directory.mkdir(parents=True, exist_ok=True)
    src = str(T.source(out))
    jobs = []
    for item in items:
        a, b = item['inicio_ms'], item['fim_ms']
        files = []
        for t in (min(b - 1, a + 300), (a + b) // 2, max(a, b - 300)):
            target = directory / f'{source_key(out)[:8]}_{t}.jpg'
            files.append(str(target.relative_to(out)))
            if not target.exists():
                jobs.append([M.FFMPEG, '-v', 'error', '-y', '-ss', f'{t / 1000:.3f}', '-i', src, '-frames:v', '1', '-vf', 'scale=-2:160', '-q:v', '5', str(target)])
        item['miniaturas'] = files
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda cmd: subprocess.run(cmd, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)), jobs))


def effective_first(first, raws):
    """1ª menção: a falada pela transcrição ou o nome na legenda gravada, o que vier antes."""
    seen = [t for raw in raws for t in raw.get('legenda_ms', [])]
    candidates = [x for x in [first] + seen[:1] if x is not None]
    if not candidates:
        return None, None
    value = min(candidates)
    return value, ('legenda' if seen and value == seen[0] and (first is None or seen[0] < first) else 'transcricao')


APPEARANCE_VERSION = 'aparencia-2'
LIMITS_VERSION = 'limites-4'


def appearance_samples(job, out, start, end, info, wanted):
    """Quadros a 2 por segundo comparados com as referências do editor (cache por minuto)."""
    from . import referencias_visuais as RV
    width, _ = frame_size(info)
    refs = RV.request_items(out, width, info)
    if not refs:
        return [], None
    directory = folder(out) / ('aparencia_' + T.digest([APPEARANCE_VERSION, source_key(out), RV.signature(out)]))
    directory.mkdir(parents=True, exist_ok=True)
    request = directory / 'pedido.json'
    T.write(request, {'referencias': refs})
    plan = units(start, end)
    pending = [u for u in plan if not unit_file(directory, u).exists()]
    if pending:
        run_workers(job, out, pending, info, directory=directory, extra=['--aparencia', str(request)],
                    label='Comparando com as referências marcadas', phase='Referências do editor', span=(.86, .04))
    hits = {}
    for u in plan:
        for line in unit_file(directory, u).read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            hits[row['t']] = hits.get(row['igual']) if 'igual' in row else row.get('m')
    rows = []
    for t, m in sorted(hits.items()):
        if m and start - 1 <= t <= end + 1 and 0 <= m['ref'] < len(refs):
            cx, cy, w, h = m['caixa']
            rows.append((t, [wanted[0], .82, cy, w, cx, h, 'referencia_editor', refs[m['ref']]['id']]))
    stats = {'referencias': len(refs), 'quadros': len(hits), 'com_referencia': len(rows),
             'minutos': len(plan), 'minutos_reaproveitados': len(plan) - len(pending)}
    return rows, stats


def merge_samples(samples, extra):
    merged = {t: list(rows) for t, rows in samples}
    for t, row in extra:
        merged.setdefault(float(t), []).append(row)
    return sorted(merged.items())


def _join(a, b):
    """Une duas aparições do mesmo plano que se tocaram depois do ajuste das bordas."""
    a.update(fim_ms=max(a['fim_ms'], b['fim_ms']), ultimo_s=max(a['ultimo_s'], b['ultimo_s']), depois_s=b['depois_s'],
             leituras=a['leituras'] + b['leituras'], legenda_ms=a['legenda_ms'] + b['legenda_ms'],
             evidencias=list(dict.fromkeys(a['evidencias'] + b['evidencias'])), referencias=sorted(set(a['referencias'] + b['referencias'])),
             referencia_visual=a['referencia_visual'] and b['referencia_visual'], local='imagem' if 'imagem' in (a['local'], b['local']) else 'legenda')
    if (b['nota'], b['ocr_confianca']) > (a['nota'], a['ocr_confianca']) and not b['referencia_visual']:
        a.update(nota=b['nota'], texto=b['texto'], ocr_confianca=b['ocr_confianca'])
    return a


def refine_limits(job, out, raws, info, wanted, changes):
    """Analisa quadros perto da entrada e da saída para aproximar o primeiro e o último quadro do pote."""
    from . import referencias_visuais as RV
    stats = {'aparicoes': len(raws), 'ajustadas': 0, 'acompanhadas': 0, 'descartadas_outro_nome': 0, 'unidas': 0, 'reaproveitado': True}
    if not raws:
        return raws, stats
    width, height = frame_size(info)
    refs = RV.request_items(out, width, info)
    directory = folder(out) / 'limites'
    directory.mkdir(parents=True, exist_ok=True)
    groups = []
    for i, raw in enumerate(raws):
        # Legenda gravada não é o pote: só aparições na imagem têm as bordas acompanhadas.
        if raw['local'] != 'imagem':
            continue
        key = T.digest([LIMITS_VERSION, source_key(out), wanted, raw['primeiro_s'], raw['ultimo_s'], raw['ancora_s'], raw['caixa'],
                        RV.signature(out) if raw['referencias'] else ''])
        groups.append({'id': str(i), 'chave': key, 'primeiro': raw['primeiro_s'], 'ultimo': raw['ultimo_s'], 'ancora': raw['ancora_s'],
                       'caixa': raw['caixa'], 'somente_referencia': raw['referencia_visual'] and 'referencia' in raw['evidencias']})
    pending = [g for g in groups if not (directory / f'limite_{g["chave"]}.json').exists()]
    results = {}
    if pending:
        stats['reaproveitado'] = False
        request = directory / f'pedido_{uuid_hex()}.json'
        T.write(request, {'grupos': pending, 'nomes': wanted, 'referencias': refs if any(g['somente_referencia'] or g['caixa'] is None for g in pending) else []})
        command = [M.PY, str(M.BASE / 'ocr_worker.py'), str(T.source(out)), str(directory), '--ffmpeg', M.FFMPEG, '--unidades', '0',
                   '--largura', str(width), '--altura', str(height), '--threads', '2', '--limites', str(request)]
        _run_tracked(job, command, len(pending), 'LIMITE ', 'Ajustando a entrada e a saída das aparições', 'Limites das aparições', (.9, .05))
        request.unlink(missing_ok=True)
    for g in groups:
        file = directory / f'limite_{g["chave"]}.json'
        if file.exists():
            results[g['id']] = json.loads(file.read_text())
    kept = []
    for i, raw in enumerate(raws):
        result = results.get(str(i))
        if not result:
            kept.append(raw)
            continue
        if result.get('conflito'):
            # Outro nome legível no pote encontrado pela aparência: não é o produto antigo.
            stats['descartadas_outro_nome'] += 1
            continue
        if result.get('nome_lido') and raw['referencia_visual']:
            raw.update(referencia_visual=False, texto=result.get('texto') or raw['texto'])
            raw['evidencias'] = list(dict.fromkeys(['nome_lido'] + raw['evidencias']))
        changed = False
        if result.get('inicio') is not None:
            value = round(max(0.0, result['inicio']) * 1000)
            changed |= value != raw['inicio_ms']
            raw['inicio_ms'] = value
        if result.get('fim') is not None:
            value = round(result['fim'] * 1000)
            changed |= value != raw['fim_ms']
            raw['fim_ms'] = max(raw['inicio_ms'] + 100, value)
        if changed:
            stats['ajustadas'] += 1
            raw['limites_acompanhados'] = True
        if result.get('acompanhado_s', 0) >= .25:
            stats['acompanhadas'] += 1
            raw['evidencias'] = list(dict.fromkeys(raw['evidencias'] + ['acompanhado']))
        kept.append(raw)
    kept.sort(key=lambda r: (r['inicio_ms'], r['fim_ms']))
    joined = []
    for raw in kept:
        # Leitura ruim isolada no mesmo plano: as bordas acompanhadas se encontram e viram uma aparição.
        if joined and raw['inicio_ms'] <= joined[-1]['fim_ms'] + 100 and cut_between(changes, joined[-1]['fim_ms'] / 1000 - .05, raw['inicio_ms'] / 1000 + .05) is None:
            _join(joined[-1], raw)
            stats['unidas'] += 1
        else:
            joined.append(raw)
    return joined, stats


def uuid_hex():
    import uuid
    return uuid.uuid4().hex[:10]


def _run_tracked(job, command, total, marker, label, phase, span):
    """Processo de leitura único com progresso por linha e cancelamento."""
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if getattr(job, 'params', {}).get('automatico') and hasattr(os, 'setpriority'):
        try: os.setpriority(os.PRIO_PROCESS, proc.pid, 10)
        except OSError: pass
    errors, done = [], []

    def read_progress():
        for line in proc.stdout:
            if line.startswith(marker): done.append(line)

    def read_errors():
        for line in proc.stderr:
            errors.append(line)
            if len(errors) > 40: del errors[0]
    threads = [threading.Thread(target=fn, daemon=True) for fn in (read_progress, read_errors)]
    for thread in threads: thread.start()
    try:
        while proc.poll() is None:
            if job.cancel: raise M.Cancelled()
            job.pct = span[0] + span[1] * min(1, len(done) / max(1, total))
            job.step = f'{label} · {len(done)} de {total}'
            job.progress = {'tipo': 'deteccao', 'fase': phase, 'processadas': len(done), 'total': total, 'indeterminado': False}
            time.sleep(.2)
        for thread in threads: thread.join(timeout=3)
        if proc.returncode: raise RuntimeError(M.process_error(''.join(errors), proc.returncode))
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()
        for thread in threads: thread.join(timeout=3)
        for stream in (proc.stdout, proc.stderr): stream.close()


def build(out, state, samples, changes, first, end_ms=None, raws=None):
    windows = fala_windows(out)
    raws = group(samples, changes, names(state)) if raws is None else raws
    first, origin = effective_first(first, raws)
    items = []
    for raw in raws:
        if end_ms is not None: raw['fim_ms'] = min(raw['fim_ms'], end_ms)
        if raw['fim_ms'] - raw['inicio_ms'] < 100: continue
        item = dict(raw, id=T.digest(['deteccao-2', raw['inicio_ms'], raw['fim_ms']]), inicio_detectado_ms=raw['inicio_ms'], fim_detectado_ms=raw['fim_ms'],
                    confianca=confidence(raw), motivo=reason(raw), status='sugerido', antes_da_mencao=first is not None and raw['fim_ms'] <= first)
        free = uncovered_ms(item, windows)
        item['sem_cobertura_ms'] = free
        item['coberto_pela_fala'] = free <= 1
        if not item['coberto_pela_fala'] and free < item['fim_ms'] - item['inicio_ms']:
            item['motivo'] += ' · parte já coberta por fala trocada'
        # Nome na legenda gravada fora das falas trocadas: provável menção falada que ficou sem troca.
        loose = [t for t in raw.get('legenda_ms', []) if not any(a <= t <= b for a, b in windows)]
        item['fala_sem_troca'] = bool(loose)
        if loose:
            item['coberto_pela_fala'] = False
            item['motivo'] += ' · a legenda gravada mostra o nome e não há fala trocada aqui: confira se o narrador diz o nome antigo'
        item['motivos'] = motives(item)
        items.append(item)
    old = [i for i in state.get('intervalos', []) if i.get('origem') != 'manual']
    # Aparições marcadas pelo editor nunca são descartadas por uma nova busca.
    manual = [i for i in state.get('intervalos', []) if i.get('origem') == 'manual']
    previous_names = (state.get('analise') or {}).get('nomes', names(state))
    source_changed = state.get('analise') and outdated(out, state).startswith('O vídeo de origem')
    if not set(previous_names).intersection(names(state)) or source_changed:
        old = []
    if source_changed:
        manual = []
    return sorted(merge_review(old, items) + manual, key=lambda i: (i['inicio_ms'], i['fim_ms'])), first, origin


def analyze_job(job, out, automatico=False):
    from . import referencias_visuais as RV
    out = Path(out)
    started = time.perf_counter()
    state = load(out)
    if not names(state):
        raise ValueError('Informe o nome do produto antigo antes de procurar.')
    start, end, first, info = window(out, state)
    from . import visuais as V
    expected_context = (source_key(out), names(state), state.get('janela'), first)
    def check_context(current):
        if (source_key(out), names(current), current.get('janela'), V.first_product_mention(out)) != expected_context:
            raise ValueError('O produto ou o vídeo mudou durante a análise. Os resultados anteriores não foram aplicados; procure novamente com a configuração atual.')
    if not info['video']:
        raise ValueError('A análise visual exige o vídeo original. Este trabalho contém somente áudio.')
    plan = units(start, end)
    directory = cache(out)
    pending = [u for u in plan if not unit_file(directory, u).exists()]
    job.step = 'Preparando a leitura do vídeo'
    job.progress = {'tipo': 'deteccao', 'fase': 'Preparando', 'processadas': 0, 'total': len(pending), 'reutilizadas': len(plan) - len(pending), 'indeterminado': True}
    if pending:
        run_workers(job, out, pending, info)
    job.step = 'Montando os intervalos e as miniaturas'
    job.pct = .92
    samples, changes = read_samples(directory, plan, start, end)
    from . import visual_refino as R
    refined, refinement = R.run(job, out, samples, changes, names(state), start, end, info, match, group, source_key(out))
    merged = dict(samples)
    merged.update((float(t), rows) for t, rows in refined)
    samples = sorted(merged.items())
    wanted = names(state)
    if job.cancel: raise M.Cancelled()
    hits, appearance = appearance_samples(job, out, start, end, info, wanted)
    samples = merge_samples(samples, hits)
    raws = group(samples, changes, wanted)
    if job.cancel: raise M.Cancelled()
    raws, limits = refine_limits(job, out, raws, info, wanted, changes)
    job.step = 'Montando os intervalos e as miniaturas'
    with T.LOCK:
        state = load(out)
        check_context(state)
        items, effective, origin = build(out, state, samples, changes, first, end_ms=round(end*1000), raws=raws)
    thumbnails(out, items)
    with T.LOCK:
        state = load(out)
        check_context(state)
        state.update(intervalos=items, primeira_mencao_ms=first, primeira_mencao_efetiva_ms=effective, origem_primeira_mencao=origin,
                     falas_sem_troca=[{'inicio_ms': i['inicio_ms'], 'fim_ms': i['fim_ms'], 'texto': i['texto']} for i in items if i.get('fala_sem_troca')], analise={
            'chave': source_key(out), 'fonte': T.source_identity(T.source(out)), 'nomes': names(state), 'janela': state.get('janela'), 'inicio_s': round(start, 3), 'fim_s': round(end, 3),
            'minutos': len(plan), 'minutos_reaproveitados': len(plan) - len(pending), 'leituras': len(samples), 'tempo_s': round(time.perf_counter() - started, 1)})
        state['analise'].update(refino_versao=R.VERSION, refino=refinement, aparencia=appearance, limites=limits,
                                limites_versao=LIMITS_VERSION, referencias=RV.signature(out))
        state.pop('auto_erro', None)
        write(out, state)
    pending_count = sum(1 for i in items if i['status'] == 'sugerido' and not i['coberto_pela_fala'])
    job.pct = 1
    job.step = f'Análise pronta · {pending_count} trecho(s) para revisar'
    return {'intervalos': len(items), 'para_revisar': pending_count, 'por_referencia': sum('referencia' in i.get('evidencias', []) for i in items)}


# ---------- revisão ----------

def outdated(out, state):
    analysis = state.get('analise')
    if not analysis:
        return 'Ainda não analisado.'
    try:
        if analysis.get('fonte') is not None:
            changed = analysis['fonte'] != T.source_identity(T.source(out))
        else:
            key = analysis['chave']
            changed = key != source_key(out) and key not in legacy_keys(out) and not legacy_cache_valid(out, key)
            if changed and (folder(out) / ('ocr_' + source_key(out))).is_dir() and not (folder(out) / ('ocr_' + key)).is_dir():
                changed = False  # a leitura antiga já foi migrada para a chave nova
        if changed:
            return 'O vídeo de origem mudou. Procure novamente.'
    except ValueError as error:
        return str(error)
    if analysis['nomes'] != names(state) or analysis['janela'] != state.get('janela'):
        return 'O nome ou a janela mudou. Procure novamente (a leitura já feita é reaproveitada).'
    from .visual_refino import VERSION as refinement_version
    if analysis.get('refino_versao') != refinement_version or analysis.get('limites_versao') != LIMITS_VERSION:
        return IMPROVED
    from . import referencias_visuais as RV
    try:
        current = RV.signature(out)
    except ValueError:
        current = ''
    if (analysis.get('referencias') or '') != current:
        return REFS_CHANGED
    return ''


IMPROVED = 'A busca por imagem foi aprimorada. Refaça a busca para conferir novos trechos com o OCR já guardado.'
REFS_CHANGED = 'As referências do pote mudaram. Busque com as referências atuais; a leitura já feita é reaproveitada.'


def view(out, state=None):
    state = state or load(out)
    result = dict(state, desatualizado=outdated(out, state))
    windows = fala_windows(out)
    result['intervalos'] = [dict(item, sem_cobertura_ms=uncovered_ms(item, windows),
                                coberto_pela_fala=uncovered_ms(item, windows) <= 1 and not item.get('fala_sem_troca'),
                                motivos=item.get('motivos') or motives(item))
                           for item in state.get('intervalos', [])]
    try:
        from .armazenamento import visual_margin_ms
        margin = visual_margin_ms()
        duration = round(T.probe(T.source(out), False)['duration'] * 1000)
        first = state.get('primeira_mencao_efetiva_ms', state.get('primeira_mencao_ms'))
        floor = 0 if state.get('cobrir_antes_da_mencao') or first is None else first
        for item in result['intervalos']:
            a, b = coverage_span(item, margin, duration, floor if item['fim_ms'] > floor else 0)
            item.update(cobertura_inicio_ms=a, cobertura_fim_ms=b)
        result['margem_visual_ms'] = margin
    except (ValueError, OSError, KeyError):
        pass
    from . import referencias_visuais as RV
    try:
        result['referencias'] = RV.view(out)
    except (ValueError, OSError):
        result['referencias'] = {'itens': [], 'validas': 0, 'limite': RV.MAX_REFS}
    active = next((j for j in list(M.JOBS.values()) if j.kind == 'deteccao_visual' and j.status in ('na_fila','executando') and Path(j.params.get('out','')).resolve() == Path(out).resolve()), None)
    result['tarefa'] = active.to_dict() if active else None
    try:
        result['extensao'] = T.source(out).suffix
    except ValueError:
        pass
    try:
        start, end, first, info = window(out, state)
        result.update(janela_inicio_s=round(start, 3), janela_fim_s=round(end, 3), primeira_mencao_ms=first, tem_video=info['video'])
    except (ValueError, OSError, KeyError):
        pass
    return result


def coverage_span(item, margin, duration_ms, floor=0):
    """Intervalo de cobertura: a aparição com a margem visual; tempos ajustados pelo editor valem como estão."""
    extra = 0 if item.get('ajustado') else margin
    return max(floor, item['inicio_ms'] - extra), min(duration_ms, item['fim_ms'] + extra)


def add_manual(out, body):
    """Aparição que ficou de fora, marcada no player. Entra aprovada e vai direto para os takes."""
    import uuid
    info = T.probe(T.source(out), False)
    if not info['video']:
        raise ValueError('A marcação exige o vídeo original. Este trabalho contém somente áudio.')
    duration = info['duration'] * 1000
    try:
        a, b = float(body.get('inicio_ms')), float(body.get('fim_ms'))
    except (TypeError, ValueError):
        raise ValueError('Marque o início e o fim no player.') from None
    if not all(math.isfinite(v) for v in (a, b)) or not 0 <= a < b <= duration or b - a < 100:
        raise ValueError('Confira os tempos: o início deve vir antes do fim e ambos dentro do vídeo.')
    with T.LOCK:
        state = load(out)
        windows = fala_windows(out)
        first = state.get('primeira_mencao_efetiva_ms', state.get('primeira_mencao_ms'))
        item = {'id': 'manual_' + uuid.uuid4().hex[:12], 'origem': 'manual', 'fonte': T.source_identity(T.source(out)),
                'inicio_ms': round(a), 'fim_ms': round(b), 'inicio_detectado_ms': round(a), 'fim_detectado_ms': round(b),
                'status': 'aprovado', 'confianca': 'alta', 'evidencias': ['manual'], 'texto': '', 'nota': 1.0, 'local': 'imagem',
                'leituras': 0, 'legenda_ms': [], 'fala_sem_troca': False, 'antes_da_mencao': first is not None and round(b) <= first}
        item.update(motivo=reason(item), motivos=motives(item))
        free = uncovered_ms(item, windows)
        item.update(sem_cobertura_ms=free, coberto_pela_fala=free <= 1)
    thumbnails(out, [item])
    with T.LOCK:
        state = load(out)
        state['intervalos'] = sorted(state.get('intervalos', []) + [item], key=lambda i: (i['inicio_ms'], i['fim_ms']))
        write(out, state)
        result = view(out, state)
    result['criado'] = item['id']
    return result


def review(out, body):
    with T.LOCK:
        state = load(out)
        if not state.get('intervalos'):
            raise ValueError('Procure o produto no vídeo antes de revisar.')
        duration = T.probe(T.source(out), False)['duration'] * 1000
        by_id = {i['id']: i for i in state['intervalos']}
        for change in body.get('itens', []):
            item = by_id.get(change.get('id'))
            if not item:
                raise ValueError('Trecho não encontrado. Atualize a lista.')
            status = change.get('status', item['status'])
            if status not in STATUSES:
                raise ValueError('Situação inválida.')
            item['status'] = status
            if 'inicio_ms' in change or 'fim_ms' in change:
                a, b = float(change.get('inicio_ms', item['inicio_ms'])), float(change.get('fim_ms', item['fim_ms']))
                if not all(math.isfinite(v) for v in (a, b)) or not 0 <= a < b <= duration or b - a < 100:
                    raise ValueError('Confira os tempos: o início deve vir antes do fim e ambos dentro do vídeo.')
                if (round(a), round(b)) != (item['inicio_ms'], item['fim_ms']):
                    item.update(inicio_ms=round(a), fim_ms=round(b), ajustado=True)
        write(out, state)
        return view(out, state)


def approved_markers(out):
    """Intervalos aprovados e ainda válidos para o vídeo atual."""
    if not path(out).exists():
        return []
    state = load(out)
    if outdated(out, state).startswith('O vídeo de origem'):
        return []
    try:
        current = T.source_identity(T.source(out))
    except (ValueError, OSError):
        current = None
    return [i for i in state['intervalos'] if i['status'] == 'aprovado' and (current is None or i.get('fonte', current) == current)]


def coverage_rows(out):
    """Janelas de cobertura dos aprovados, respeitando a autorização de cobrir antes da apresentação."""
    markers = approved_markers(out)
    if not markers:
        return []
    from .visuais import first_product_mention
    try:
        first = first_product_mention(out)
    except (ValueError, OSError, KeyError):
        return []
    state = load(out)
    effective = state.get('primeira_mencao_efetiva_ms')
    if effective is not None:
        first = effective if first is None else min(first, effective)
    floor = 0 if state.get('cobrir_antes_da_mencao') else first
    if floor is None:
        return []
    rows = []
    for item in markers:
        start = max(item['inicio_ms'], floor)
        if item['fim_ms'] > start:
            rows.append({'id': 'produto_antigo_' + item['id'], 'start': start, 'end': item['fim_ms'], 'kit': None, 'selected': True,
                         'text': 'Produto antigo na imagem · ' + item['motivo'], 'categoria_alvo': 'produto', 'produto_antigo': True,
                         'limite_inicio_ms': floor, 'ajustado': bool(item.get('ajustado'))})
    return rows


def coverage_signature(out):
    """Assinatura dos aprovados; vazia quando não há nenhum, para não invalidar takes de trabalhos sem detecção."""
    markers = approved_markers(out)
    if not markers:
        return ''
    state = load(out)
    data = ['cobertura-2', [[m['id'], m['inicio_ms'], m['fim_ms']] for m in markers], state.get('primeira_mencao_efetiva_ms')]
    if state.get('cobrir_antes_da_mencao'):
        data.append('cobrir_antes_da_mencao')
    return T.digest(data)

#!/usr/bin/env python3
"""
Leitura LOCAL de texto nos quadros (sem internet, sem API) — processo separado para poder ser cancelado.

Uso: ocr_worker.py <video> <pasta> --ffmpeg F --unidades 2040,2100 --duracao 60 --largura 960 --altura 540 [--threads 2]

Cada unidade de tempo vira unidade_<inicio>.jsonl, gravada como .partial e renomeada só quando completa,
para um cancelamento não deixar resultado pela metade. Linhas:
  {"t": s, "d": mudança}                      todo quadro a 4 qps (para achar cortes de cena)
  {"t": s, "ocr": [[texto, conf, y, larg]]}  quadros lidos (y e largura relativos à imagem)
  {"t": s, "igual": s0}                       quadro igual ao último lido; reaproveita a leitura
Imprime "UNIDADE <inicio>" ao concluir cada unidade.
"""
import argparse
import os
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

RATE = 4
CUT = 18.0       # diferença média (0–255) que caracteriza corte de cena
STILL = 1.5      # abaixo disso o quadro é considerado igual ao último lido
EVERY = 1.0      # intervalo máximo entre leituras dentro do mesmo plano
REFRESH = 3.0    # mesmo um plano parado é relido: um rótulo pequeno pode ter mudado


def say(kind, value):
    print(f"{kind} {value}", flush=True)


def tiny(rgb):
    height, width = rgb.shape[:2]
    block_h, block_w = height // 18, width // 32
    # Sum byte pixels by block before converting to floating-point averages.
    blocks = rgb[:18 * block_h, :32 * block_w].reshape(18, block_h, 32, block_w * 3)
    sums = blocks.sum(axis=3, dtype=np.uint32).sum(axis=1, dtype=np.uint32)
    return sums.astype(np.float32) / (block_h * block_w * 3)


def frames(args, start, duration=None, rate=RATE):
    duration = args.duracao if duration is None else duration
    decoder_limits = ['-threads', '1', '-filter_threads', '1'] if sys.platform == 'win32' else []
    encoder_limits = ['-threads', '1'] if sys.platform == 'win32' else []
    cmd = [args.ffmpeg, *decoder_limits, '-v', 'error', '-nostdin', '-ss', f'{max(0, start):.3f}', '-i', args.video, '-t', f'{duration:.3f}', '-an',
           '-vf', f'fps={rate},scale={args.largura}:{args.altura}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', *encoder_limits, '-']
    size = args.largura * args.altura * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        k = 0
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield round(max(0, start) + k / rate, 3), np.frombuffer(buf, np.uint8).reshape(args.altura, args.largura, 3)
            k += 1
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


_LAST_BOXES = None  # caixas (px) da última leitura completa, na ordem das linhas


def read(engine, rgb, details=False):
    global _LAST_BOXES
    result = engine(np.ascontiguousarray(rgb[:, :, ::-1]))
    h, w = rgb.shape[:2]
    rows, boxes = [], []
    for box, text, score in zip(result.boxes if result.boxes is not None else [], result.txts or [], result.scores or []):
        box = np.asarray(box, dtype=float)
        row = [text, round(float(score), 3), round(float(box[:, 1].mean()) / h, 3), round(float(np.ptp(box[:, 0])) / w, 3)]
        if details:
            row += [round(float(box[:, 0].mean()) / w, 3), round(float(np.ptp(box[:, 1])) / h, 3)]
        rows.append(row)
        boxes.append((float(box[:, 0].min()), float(box[:, 1].min()), float(box[:, 0].max()), float(box[:, 1].max())))
    _LAST_BOXES = boxes
    return rows


FULL_EVERY = 3.0   # leitura completa do quadro; entre elas, só a área que mudou é relida
REGION_MAX = .45   # acima desta fração do quadro, a leitura parcial não compensa


def read_full(engine, rgb):
    """Leitura completa; as caixas só existem quando o motor real as informou."""
    global _LAST_BOXES
    _LAST_BOXES = None
    rows = read(engine, rgb)
    boxes = _LAST_BOXES
    return [(row, box) for row, box in zip(rows, boxes)] if boxes is not None and len(boxes) == len(rows) else None, rows


def read_region(engine, rgb, region):
    """Lê só o recorte, na MESMA escala da leitura completa (o detector amplia o lado menor
    do quadro; aqui o recorte recebe o mesmo fator), para não perder nem inventar texto.
    None se o motor não permitir ajustar a escala."""
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = region
    crop = rgb[y0:y1, x0:x1]
    det = getattr(engine, 'text_det', None)
    if det is None or getattr(det, 'limit_type', None) != 'min' or not getattr(det, 'limit_side_len', None) or not crop.size:
        return None
    ratio = max(1.0, det.limit_side_len / min(h, w))
    original = det.limit_side_len
    det.limit_side_len = max(32, round(min(crop.shape[:2]) * ratio))
    try:
        result = engine(np.ascontiguousarray(crop[:, :, ::-1]))
    finally:
        det.limit_side_len = original
    rows = []
    for box, text, score in zip(result.boxes if result.boxes is not None else [], result.txts or [], result.scores or []):
        box = np.asarray(box, dtype=float) + (x0, y0)
        rows.append(([text, round(float(score), 3), round(float(box[:, 1].mean()) / h, 3), round(float(np.ptp(box[:, 0])) / w, 3)],
                     (float(box[:, 0].min()), float(box[:, 1].min()), float(box[:, 0].max()), float(box[:, 1].max()))))
    return rows


def _overlaps(box, region):
    return box[0] < region[2] and box[2] > region[0] and box[1] < region[3] and box[3] > region[1]


def changed_region(small, before, width, height, boxes):
    """Retângulo (px) que cobre os blocos alterados e o texto anterior que eles tocam; None = ler tudo."""
    changed = np.abs(small - before) > 3.0
    if not changed.any() or changed.mean() > REGION_MAX:
        return None
    rows, cols = np.nonzero(changed)
    bh, bw = height / 18, width / 32
    region = [max(0, (cols.min() - 1) * bw), max(0, (rows.min() - 1) * bh),
              min(width, (cols.max() + 2) * bw), min(height, (rows.max() + 2) * bh)]
    grown = True
    while grown:
        grown = False
        for _, box in boxes:
            if _overlaps(box, region) and not (box[0] >= region[0] and box[1] >= region[1] and box[2] <= region[2] and box[3] <= region[3]):
                pad = 8
                region = [max(0, min(region[0], box[0] - pad)), max(0, min(region[1], box[1] - pad)),
                          min(width, max(region[2], box[2] + pad)), min(height, max(region[3], box[3] + pad))]
                grown = True
    region = [int(region[0]), int(region[1]), int(np.ceil(region[2])), int(np.ceil(region[3]))]
    if (region[2] - region[0]) * (region[3] - region[1]) > REGION_MAX * width * height:
        return None
    return tuple(region)


def unit(engine, args, start, target):
    partial = target.with_suffix('.partial')
    previous = last_tiny = pending_cut = last_read = last_ocr = last_detail = None
    last_boxes = last_full = None
    with partial.open('w', encoding='utf-8') as fp:
        for t, rgb in frames(args, start):
            small = tiny(rgb)
            delta = np.abs(small - previous) if previous is not None else None
            change = float(delta.mean()) if delta is not None else 0.0
            local_change = delta is not None and change < CUT and float(np.percentile(delta, 99)) >= 12 and float((delta > 8).mean()) <= .15
            previous = small
            signal = {'t': t, 'd': round(change, 2)}
            if local_change:
                signal['local'] = True
            fp.write(json.dumps(signal) + '\n')
            if change >= CUT:
                pending_cut = t
            due = last_read is None or t - last_read >= EVERY - 1e-6
            detail_due = local_change and (last_detail is None or t - last_detail >= 2) and (last_read is None or t - last_read >= .25)
            # Lê o quadro seguinte ao corte, fora da transição, para não perder planos curtos.
            after_cut = pending_cut is not None and t - pending_cut >= 1 / RATE - 1e-6
            if not (due or after_cut or detail_due):
                continue
            if local_change: last_detail = t
            pending_cut = None
            difference = np.abs(small - last_tiny) if last_tiny is not None else None
            # A média global escondia inserções pequenas do pote. Também mede a
            # parte que mais mudou e limita o tempo de reutilização da leitura.
            unchanged = difference is not None and float(difference.mean()) < STILL and float(np.percentile(difference, 99)) < 8
            if unchanged and last_ocr is not None and t - last_ocr < REFRESH:
                fp.write(json.dumps({'t': t, 'igual': last_read}) + '\n')
            else:
                boxes = rows = None
                if last_boxes is not None and last_tiny is not None and t - last_full < FULL_EVERY - 1e-6:
                    region = changed_region(small, last_tiny, rgb.shape[1], rgb.shape[0], last_boxes)
                    fresh = read_region(engine, rgb, region) if region else None
                    if fresh is not None:
                        boxes = [item for item in last_boxes if not _overlaps(item[1], region)] + fresh
                        boxes.sort(key=lambda item: (round(item[1][1] / 8), item[1][0]))
                        rows = [row for row, _ in boxes]
                if rows is None:
                    boxes, rows = read_full(engine, rgb)
                    last_full = t
                fp.write(json.dumps({'t': t, 'ocr': rows}, ensure_ascii=False) + '\n')
                last_boxes = boxes
                last_tiny = small
                last_ocr = t
            last_read = t
    partial.replace(target)


def extract(args, t):
    command = [args.ffmpeg, '-v', 'error', '-nostdin', '-ss', f'{t:.3f}', '-i', args.video,
               '-frames:v', '1', '-an', '-vf', f'scale={args.largura}:{args.altura}:flags=lanczos',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    result = subprocess.run(command, capture_output=True, check=True, timeout=30,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if len(result.stdout) != args.largura * args.altura * 3:
        raise ValueError(f'Não foi possível ler o quadro em {t:.2f} s.')
    return np.frombuffer(result.stdout, np.uint8).reshape(args.altura, args.largura, 3)


def detailed_read(engine, rgb, wanted):
    from plataforma import deteccao_visual as D, visual_refino as R
    rows = read(engine, rgb, details=True)
    score, text, item = D.match(rows, wanted)
    if score >= .95 and float(item[1]) >= .8:
        return rows

    h, w = rgb.shape[:2]
    # Recortes que se sobrepõem para ampliar também rótulos nas bordas e no centro.
    regions = [(x, y, x + .60, y + .60) for y in (0, .40) for x in (0, .40)]
    if item is not None and R.weak_label(score, text, item, wanted):
        _, _, y, width, x, height = item
        regions.insert(0, (max(0, x-width*.95), max(0, y-max(.045, height*2.5)),
                           min(1, x+width*.95), min(1, y+max(.045, height*2.5))))
    for left, top, right, bottom in regions:
        x0, y0, x1, y1 = round(left*w), round(top*h), round(right*w), round(bottom*h)
        crop = rgb[y0:y1, x0:x1]
        if not crop.size:
            continue
        # A área de interesse tem mais detalhe relativo quando o OCR reduz sua entrada.
        for text, confidence, y, width, x, height in read(engine, crop, details=True):
            row = [text, confidence, round((y0 + y*(y1-y0))/h, 4), round(width*(x1-x0)/w, 4),
                   round((x0 + x*(x1-x0))/w, 4), round(height*(y1-y0)/h, 4)]
            duplicate = next((i for i, prior in enumerate(rows) if D.norm(prior[0]) == D.norm(text)
                              and abs(row[2]-prior[2]) < .025 and abs(row[4]-prior[4]) < .035), None)
            if duplicate is None:
                rows.append(row)
            elif rows[duplicate][1] < confidence:
                rows[duplicate] = row
        score, _, item = D.match(rows, wanted)
        if score >= .95 and float(item[1]) >= .8:
            break
    return rows


def refine(engine, args):
    # A leitura normal continua genérica e reutilizável. Esta segunda passada
    # tem cache próprio porque os recortes e as referências dependem do nome procurado.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from plataforma import deteccao_visual as D
    from plataforma.visual_referencia import LabelReference
    request = json.loads(Path(args.refinar).read_text())
    wanted = request['nomes']
    directory = Path(args.pasta)
    needed = [t for t in request['pontos'] if not (directory / f'quadro_{t:010.3f}.json').exists()]
    reference = LabelReference()
    anchors = {}
    for t in request.get('referencias', []) if needed else ():
        rgb = extract(args, t)
        rows = detailed_read(engine, rgb, wanted)
        for item in rows:
            score, _, _ = D.match([item], wanted)
            if score >= .99 and item[1] >= .87 and D.place(item) == 'imagem':
                reference.add(rgb, item)
        anchors[t] = rows

    readings = []
    for t in request['pontos']:
        target = directory / f'quadro_{t:010.3f}.json'
        if target.exists():
            rows = json.loads(target.read_text())
        else:
            if t in anchors:
                rows = anchors[t]
            else:
                rgb = extract(args, t)
                rows = detailed_read(engine, rgb, wanted)
                if D.match(rows, wanted)[0] < .85:
                    similar = reference.match(rgb)
                    if similar:
                        rows.append(similar)
            partial = target.with_suffix('.partial')
            partial.write_text(json.dumps(rows, ensure_ascii=False))
            partial.replace(target)
        readings.append([t, rows])
        say('REFINO', t)
    target = directory / 'resultado.json'
    partial = target.with_suffix('.partial')
    partial.write_text(json.dumps({'leituras': readings}, ensure_ascii=False))
    partial.replace(target)


APPEARANCE_RATE = 2      # quadros por segundo comparados com as referências do editor
EDGE_RATE = 12           # quadros por segundo perto da entrada e da saída
EDGE_S = 2.5             # quanto procurar antes da entrada e depois da saída


def _image(file):
    """Lê PNG/JPEG também em caminhos com acentos (Windows)."""
    import cv2
    data = np.fromfile(file, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        raise ValueError('Não foi possível abrir a referência ' + Path(file).name)
    return np.ascontiguousarray(image[:, :, ::-1])


def _references(request):
    import cv2
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from plataforma.visual_aparencia import RegionReference
    reference = RegionReference()
    for position, item in enumerate(request.get('referencias', [])):
        rgb = _image(item['arquivo'])
        factor = float(item['fator'])
        size = (max(8, round(rgb.shape[1] * factor)), max(8, round(rgb.shape[0] * factor)))
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC)
        reference.add(rgb, position)
    return reference


def appearance_unit(reference, args, start, target):
    partial = target.with_suffix('.partial')
    last_small = last_t = None
    with partial.open('w', encoding='utf-8') as fp:
        for t, rgb in frames(args, start, rate=APPEARANCE_RATE):
            small = tiny(rgb)
            # Reaproveita só quadros quase idênticos e próximos: um pote pequeno que sai muda pouco a média.
            if last_small is not None and t - last_t < 1.0:
                difference = np.abs(small - last_small)
                if float(difference.mean()) < STILL and float(difference.max()) < 4:
                    fp.write(json.dumps({'t': t, 'igual': last_t}) + '\n')
                    continue
            fp.write(json.dumps({'t': t, 'm': reference.match(rgb)}) + '\n')
            last_small, last_t = small, t
    partial.replace(target)


def appearance(args):
    request = json.loads(Path(args.aparencia).read_text())
    reference = _references(request)
    if not reference.variants:
        raise SystemExit('As referências marcadas não têm detalhe suficiente. Marque o pote com o rótulo visível.')
    folder = Path(args.pasta)
    for value in args.unidades.split(','):
        start = float(value)
        appearance_unit(reference, args, start, folder / f'unidade_{start:09.3f}.jsonl')
        say('UNIDADE', f'{start:.3f}')


MAX_FOLLOW_S = 12.0      # limite do acompanhamento além da última leitura
INSIDE_S = .25            # começa um pouco dentro da aparição, para não cair do outro lado de um corte


def _edge_frames(args, edge, direction):
    """Quadros a partir de um ponto já dentro da aparição, em ordem de afastamento."""
    if direction < 0:
        start = max(0.0, edge - EDGE_S)
        items = list(frames(args, start, edge + INSIDE_S - start, EDGE_RATE))
        return items[::-1]
    start = max(0.0, edge - INSIDE_S)
    return list(frames(args, start, EDGE_S + INSIDE_S, EDGE_RATE))


def _label_box(engine, rgb, wanted):
    from plataforma import deteccao_visual as D
    rows = detailed_read(engine, rgb, wanted)
    score, _, item = D.match(rows, wanted)
    if score < .85 or item is None or len(item) < 6 or D.place(item) != 'imagem':
        return None
    _, _, y, width, x, height = item[:6]
    # O rótulo faz parte do pote: acompanha uma área um pouco maior que as letras.
    return [x, y, min(1.0, width * 1.3), min(1.0, height * 2.2)]


def _region_text(engine, rgb, box, wanted):
    """Lê o texto dentro da região encontrada pela aparência, ampliada para letras pequenas."""
    import cv2
    from plataforma import deteccao_visual as D
    h, w = rgb.shape[:2]
    cx, cy, bw, bh = box
    x0, x1 = max(0, round((cx - bw * .65) * w)), min(w, round((cx + bw * .65) * w))
    y0, y1 = max(0, round((cy - bh * .65) * h)), min(h, round((cy + bh * .65) * h))
    crop = rgb[y0:y1, x0:x1]
    if crop.size == 0:
        return 0.0, '', False
    factor = max(1.0, 420 / max(1, crop.shape[0]))
    if factor > 1:
        crop = cv2.resize(crop, (round(crop.shape[1] * factor), round(crop.shape[0] * factor)), interpolation=cv2.INTER_CUBIC)
    rows = read(engine, crop)
    score, text, _ = D.match(rows, wanted)
    # Outro nome legível no mesmo pote: provável produto parecido, não o antigo.
    other = any(r[1] >= .9 and len(D.norm(r[0]).replace(' ', '')) >= 5 and D.match([r], wanted)[0] < .55 for r in rows)
    return score, text, other and score < .8


def limits(args):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from plataforma.visual_aparencia import Tracker, boundary
    request = json.loads(Path(args.limites).read_text())
    wanted = request['nomes']
    folder = Path(args.pasta)
    reference = _references(request) if request.get('referencias') else None
    engine = None

    def ocr():
        nonlocal engine
        if engine is None:
            from rapidocr import RapidOCR
            engine = RapidOCR(params={'Global.log_level': 'error', 'EngineConfig.onnxruntime.intra_op_num_threads': args.threads})
        return engine

    def locate(rgb, hint):
        if reference is not None:
            found = reference.match(rgb)
            if found:
                return found['caixa']
        box = _label_box(ocr(), rgb, wanted)
        if box:
            return box
        if hint is not None:
            # Plano parado: o pote continua onde estava no quadro de referência do grupo.
            tracker = Tracker(hint[0], hint[1])
            if tracker.step(rgb):
                return tracker.box
        return None

    results = []
    for group in request['grupos']:
        target = folder / f'limite_{group["chave"]}.json'
        if target.exists():
            results.append(json.loads(target.read_text()))
            say('LIMITE', group['id'])
            continue
        anchor_rgb = extract(args, group['ancora'])
        anchor_box = group.get('caixa') or locate(anchor_rgb, None)
        hint = (anchor_rgb, anchor_box) if anchor_box else None
        result = {'id': group['id'], 'chave': group['chave'], 'inicio': None, 'fim': None, 'acompanhado_s': 0.0,
                  'nome_lido': False, 'conflito': False, 'texto': ''}
        for edge, direction, key in ((group['primeiro'], -1, 'inicio'), (group['ultimo'], 1, 'fim')):
            items = _edge_frames(args, edge, direction)
            if not items:
                continue
            # Primeiro quadro (de dentro para fora) em que o pote é localizado.
            first, box = None, None
            for position in range(min(len(items), 4)):
                if direction * (items[position][0] - edge) > 1 / EDGE_RATE:
                    break
                box = locate(items[position][1], hint)
                if box:
                    first = position
                    break
            if first is None:
                continue
            tracker = Tracker(items[first][1], box)
            relocate = lambda rgb: locate(rgb, None)
            reached, window, remaining = items[first][0], items[first:], MAX_FOLLOW_S
            while True:
                index, at_cut = boundary([rgb for _, rgb in window[1:]], tracker, start=window[0][1], relocate=relocate)
                reached = window[index + 1][0] if index >= 0 else reached
                remaining -= EDGE_S
                # O pote seguiu visível até o fim da janela: continua procurando no mesmo plano.
                if at_cut or index < len(window) - 3 or remaining <= 0 or (direction < 0 and reached <= 0):
                    break
                following = (list(frames(args, max(0.0, reached - EDGE_S), min(EDGE_S, reached), EDGE_RATE))[::-1]
                             if direction < 0 else list(frames(args, reached + 1 / EDGE_RATE, EDGE_S, EDGE_RATE)))
                if len(following) < 2:
                    break
                window = [(reached, window[index + 1][1])] + following
            result[key] = round(reached if direction < 0 else reached + 1 / EDGE_RATE, 3)
            result['acompanhado_s'] = round(result['acompanhado_s'] + max(0.0, direction * (reached - edge)), 3)
        if group.get('somente_referencia') and anchor_box:
            score, text, conflict = _region_text(ocr(), anchor_rgb, anchor_box, wanted)
            result.update(nome_lido=score >= .85, conflito=bool(conflict), texto=text if score >= .85 else '')
        partial = target.with_suffix('.partial')
        partial.write_text(json.dumps(result, ensure_ascii=False))
        partial.replace(target)
        results.append(result)
        say('LIMITE', group['id'])
    target = folder / 'resultado.json'
    partial = target.with_suffix('.partial')
    partial.write_text(json.dumps({'grupos': results}, ensure_ascii=False))
    partial.replace(target)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video')
    ap.add_argument('pasta')
    ap.add_argument('--ffmpeg', required=True)
    ap.add_argument('--unidades', required=True)
    ap.add_argument('--duracao', type=float, default=60)
    ap.add_argument('--largura', type=int, required=True)
    ap.add_argument('--altura', type=int, required=True)
    ap.add_argument('--threads', type=int, default=2)
    ap.add_argument('--refinar')
    ap.add_argument('--aparencia')
    ap.add_argument('--limites')
    a = ap.parse_args()
    if sys.platform == 'win32':
        import cv2
        cv2.setNumThreads(1)
        a.threads = 1
    folder = Path(a.pasta)
    folder.mkdir(parents=True, exist_ok=True)
    if a.aparencia:
        appearance(a)
        return
    if a.limites:
        limits(a)
        return
    try:
        from rapidocr import RapidOCR
    except ImportError:
        raise SystemExit('ModuleNotFoundError: No module named \'rapidocr\'')
    engine = RapidOCR(params={'Global.log_level': 'error', 'EngineConfig.onnxruntime.intra_op_num_threads': a.threads})
    folder = Path(a.pasta)
    folder.mkdir(parents=True, exist_ok=True)
    if a.refinar:
        refine(engine, a)
        return
    for value in a.unidades.split(','):
        start = float(value)
        unit(engine, a, start, folder / f'unidade_{start:09.3f}.jsonl')
        say('UNIDADE', f'{start:.3f}')


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f'ERROR {e}', file=sys.stderr, flush=True)
        sys.exit(1)
    # Trabalho concluído e gravado: encerra sem a finalização das bibliotecas nativas,
    # que às vezes trava ao fechar o motor de leitura (recursive_mutex) e marcaria erro à toa.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)

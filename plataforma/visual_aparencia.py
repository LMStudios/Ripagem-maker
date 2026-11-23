"""Comparação local por aparência com as referências marcadas pelo editor.

Usado pelo processo de leitura (ocr_worker.py). Tudo roda neste computador com OpenCV.
Os resultados são candidatos para revisão: nenhuma correspondência aprova um take.

Para não confundir potes parecidos, a decisão final compara os detalhes da região
marcada (rótulo, letras, desenhos) depois de alinhar o quadro à referência. Cor e
formato do pote, sozinhos, nunca bastam.
"""
from typing import NamedTuple

import numpy as np

CUT = 18.0


class _Variant(NamedTuple):
    ref: int
    scale: float
    points: np.ndarray
    descriptors: np.ndarray
    image: np.ndarray        # referência em cinza nesta escala
    tiles: list              # fatias com detalhe nítido (y0, y1, x0, x1)


def gray(cv, rgb):
    return cv.cvtColor(np.ascontiguousarray(rgb), cv.COLOR_RGB2GRAY)


def tiny(rgb):
    g = rgb.astype(np.float32).mean(axis=2)
    h, w = g.shape
    return g[:h - h % 18, :w - w % 32].reshape(18, (h - h % 18) // 18, 32, (w - w % 32) // 32).mean(axis=(1, 3))


def detail_tiles(image, cells=10):
    """Fatias da referência com traços nítidos, da mais detalhada para a menos.

    É no detalhe fino (letras, desenhos do rótulo) que dois potes do mesmo modelo
    diferem; a tampa e a cor de fundo são iguais em embalagens parecidas.
    """
    import cv2
    h, w = image.shape
    rows, cols = max(2, min(cells, h // 8)), max(2, min(cells, w // 8))
    edges = np.abs(cv2.Laplacian(image.astype(np.float32), cv2.CV_32F))
    tiles = []
    for i in range(rows):
        for j in range(cols):
            y0, y1 = i * h // rows, (i + 1) * h // rows
            x0, x1 = j * w // cols, (j + 1) * w // cols
            if y1 - y0 >= 5 and x1 - x0 >= 5 and float(image[y0:y1, x0:x1].std()) >= 12:
                tiles.append((float(edges[y0:y1, x0:x1].mean()), (y0, y1, x0, x1)))
    tiles.sort(key=lambda x: -x[0])
    return [t for _, t in tiles]


def _gradients(cv, image, sigma):
    blurred = cv.GaussianBlur(image.astype(np.float32), (0, 0), sigma)
    return cv.Sobel(blurred, cv.CV_32F, 1, 0), cv.Sobel(blurred, cv.CV_32F, 0, 1)


def edge_agreement(cv, observed, expected, shift=2):
    """Semelhança dos contornos nas células mais detalhadas da referência (1 = idêntico)."""
    h, w = expected.shape
    cell = max(6, min(h, w) // 14)
    sigma = max(.8, cell / 10)
    ox, oy = _gradients(cv, observed, sigma)
    ex, ey = _gradients(cv, expected, sigma)
    magnitude = np.hypot(ex, ey)
    cells = [(float(magnitude[y:y + cell, x:x + cell].mean()), y, x)
             for y in range(0, h - cell + 1, cell) for x in range(0, w - cell + 1, cell)]
    cells.sort(reverse=True)
    scores = []
    for energy, y0, x0 in cells[:max(4, len(cells) // 4)]:
        if energy < 4:
            break
        b = np.concatenate([ex[y0:y0 + cell, x0:x0 + cell].ravel(), ey[y0:y0 + cell, x0:x0 + cell].ravel()])
        nb = float(np.linalg.norm(b)) + 1e-6
        best = -1.0
        for dy in range(-shift, shift + 1):
            for dx in range(-shift, shift + 1):
                y, x = y0 + dy, x0 + dx
                if y < 0 or x < 0 or y + cell > h or x + cell > w:
                    continue
                a = np.concatenate([ox[y:y + cell, x:x + cell].ravel(), oy[y:y + cell, x:x + cell].ravel()])
                best = max(best, float(a @ b) / (float(np.linalg.norm(a)) * nb + 1e-6))
        scores.append(best)
    return scores


def ncc(cv, a, b):
    if a.shape != b.shape or a.size < 16 or float(a.std()) < 3 or float(b.std()) < 3:
        return -1.0
    return float(cv.matchTemplate(a, b, cv.TM_CCOEFF_NORMED)[0, 0])


class RegionReference:
    """Encontra o pote marcado em outros quadros: pontos SIFT + alinhamento + detalhes da região."""

    SCALES = (1.5, 1.0, .7, .5, .35)
    MIN_SIDE = 22
    MIN_DETAIL = .86        # pior célula detalhada aceita (letras do rótulo) com o pote grande
    MIN_DETAIL_SMALL = .91  # pote pequeno: as letras ficam com poucos pixels e nomes diferentes se parecem mais
    SMALL_PX = 160          # altura do pote no quadro abaixo da qual vale o limite mais exigente

    def __init__(self):
        import cv2
        self.cv = cv2
        self.detector = cv2.SIFT_create(nfeatures=2400, contrastThreshold=.02)
        self.small_detector = cv2.SIFT_create(nfeatures=700, contrastThreshold=.012)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        self.variants = []
        self.count = 0

    def add(self, crop_rgb, key=None):
        """Acrescenta uma referência (recorte já na escala dos quadros analisados).

        `key` identifica a referência no resultado; por padrão, a ordem de inclusão.
        """
        cv = self.cv
        base = gray(cv, crop_rgb)
        if min(base.shape) < 12:
            return False
        index, added = (self.count if key is None else key), 0
        for scale in self.SCALES:
            h, w = base.shape
            size = (max(1, round(w * scale)), max(1, round(h * scale)))
            if min(size) < self.MIN_SIDE or max(size) > 1400:
                continue
            image = cv.resize(base, size, interpolation=cv.INTER_AREA if scale < 1 else cv.INTER_CUBIC)
            # Um pote longe ou desfocado perde detalhe: a versão suavizada aceita esse caso.
            for blur in ((0, 1.6) if scale >= .7 else (0,)):
                source = cv.GaussianBlur(image, (0, 0), blur) if blur else image
                points, descriptors = self.small_detector.detectAndCompute(source, None)
                if descriptors is None or len(points) < 8:
                    continue
                tiles = detail_tiles(source)
                if len(tiles) < 2:
                    continue
                self.variants.append(_Variant(index, scale, np.array([p.pt for p in points], np.float32),
                                              descriptors, source, tiles))
                added += 1
        if added:
            self.count += 1
        return bool(added)

    def _verify(self, frame, variant, transform, perspective=False):
        """Alinha o quadro à referência e compara o desenho fino da região marcada.

        Compara a direção dos contornos em células do tamanho de uma letra, com
        pequena folga de posição. Letras diferentes têm contornos em outros lugares,
        mesmo que a cor, o formato e a posição do rótulo sejam iguais. Decide pela
        pior das células mais detalhadas.
        """
        cv = self.cv
        h, w = variant.image.shape
        if perspective:
            registered = cv.warpPerspective(frame, transform, (w, h), flags=cv.INTER_LINEAR | cv.WARP_INVERSE_MAP,
                                            borderMode=cv.BORDER_REPLICATE)
        else:
            registered = cv.warpAffine(frame, transform, (w, h), flags=cv.INTER_LINEAR | cv.WARP_INVERSE_MAP,
                                       borderMode=cv.BORDER_REPLICATE)
        whole = ncc(cv, cv.GaussianBlur(registered, (0, 0), 1.2), cv.GaussianBlur(variant.image, (0, 0), 1.2))
        scores = edge_agreement(cv, registered, variant.image)
        if not scores:
            return whole, -1.0, 0.0
        return whole, float(np.percentile(scores, 5)), sum(s >= .8 for s in scores) / len(scores)

    def match(self, frame_rgb, keypoints=None):
        """Melhor correspondência no quadro ou None. Retorna caixa relativa ao quadro."""
        if not self.variants:
            return None
        cv = self.cv
        frame = gray(cv, frame_rgb)
        if keypoints is None:
            keypoints = self.detector.detectAndCompute(frame, None)
        points, descriptors = keypoints
        if descriptors is None or len(points) < 8:
            return None
        target = np.array([p.pt for p in points], np.float32)
        fh, fw = frame.shape
        best = None
        # Índice do quadro montado uma vez e consultado por todas as variantes das referências.
        index = cv.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=48))
        index.add([descriptors])
        index.train()
        for variant in self.variants:
            pairs = index.knnMatch(variant.descriptors, k=2)
            chosen = {}
            for pair in pairs:
                if len(pair) == 2 and pair[0].distance < .78 * pair[1].distance:
                    prior = chosen.get(pair[0].trainIdx)
                    if prior is None or pair[0].distance < prior.distance:
                        chosen[pair[0].trainIdx] = pair[0]
            if len(chosen) < 7:
                continue
            source = variant.points[[m.queryIdx for m in chosen.values()]]
            destination = target[list(chosen)]
            # Afim completo: aceita o pote de lado (encurtamento numa direção).
            transform, accepted = cv.estimateAffine2D(source, destination, ransacReprojThreshold=3.0,
                                                     maxIters=800, confidence=.99)
            if transform is None:
                continue
            inliers = int(accepted.ravel().astype(bool).sum())
            if inliers < 7 or inliers < .3 * len(chosen):
                continue
            linear = transform[:, :2]
            sx, sy = float(np.linalg.norm(linear[:, 0])), float(np.linalg.norm(linear[:, 1]))
            if not (.45 <= sx <= 2.2 and .45 <= sy <= 2.2 and .45 <= sx / sy <= 2.2) or np.linalg.det(linear) <= 0:
                continue
            h, w = variant.image.shape
            corners = cv.transform(np.array([[[0, 0], [w, 0], [w, h], [0, h]]], np.float32), transform)[0]
            low, high = corners.min(axis=0), corners.max(axis=0)
            size = high - low
            if size.min() < 10 or size[0] > .95 * fw or size[1] > .98 * fh:
                continue
            inside = np.clip(low, 0, [fw, fh]), np.clip(high, 0, [fw, fh])
            visible = float(np.prod(inside[1] - inside[0]) / max(1.0, float(np.prod(size))))
            if visible < .45:
                continue
            needed = self.MIN_DETAIL if size[1] >= self.SMALL_PX else self.MIN_DETAIL_SMALL
            whole, median, share = self._verify(frame, variant, transform)
            if median < needed and inliers >= 10:
                # Pote de lado: a perspectiva alinha melhor as letras do rótulo.
                homography, mask = cv.findHomography(source, destination, cv.RANSAC, 3.0)
                if homography is not None and int(mask.sum()) >= max(8, .6 * inliers):
                    projected = cv.perspectiveTransform(np.array([[[0, 0], [w, 0], [w, h], [0, h]]], np.float32), homography)[0]
                    if cv.isContourConvex(projected.astype(np.float32)) and cv.contourArea(projected) > 80:
                        again = self._verify(frame, variant, homography, perspective=True)
                        if again[1] > median:
                            whole, median, share = again
            # O formato e a cor podem coincidir; o desenho fino da região marcada, não.
            if median < needed or share < .85 or whole < .2:
                continue
            score = round(.6 * median + .2 * share + .2 * min(1, inliers / 30), 4)
            if best is None or score > best['nota']:
                center = (low + high) / 2 / [fw, fh]
                rel = size / [fw, fh]
                best = {'ref': variant.ref, 'nota': score, 'pontos': inliers, 'detalhe': round(median, 3),
                        'caixa': [round(float(center[0]), 4), round(float(center[1]), 4),
                                  round(float(rel[0]), 4), round(float(rel[1]), 4)],
                        'visivel': round(min(1.0, visible), 3)}
        return best


class Tracker:
    """Acompanha o pote quadro a quadro perto da entrada e da saída de uma aparição."""

    SCALES = (.8, .9, 1.0, 1.12, 1.25)

    def __init__(self, frame_rgb, box):
        import cv2
        self.cv = cv2
        self.anchor = self._patch(gray(cv2, frame_rgb), box)
        self.last = self.anchor
        self.box = list(box)

    def restart(self, frame_rgb, box):
        """Novo ponto de partida depois de reencontrar o pote (mantém a âncora original como alternativa)."""
        patch = self._patch(gray(self.cv, frame_rgb), box)
        if patch is not None:
            self.anchor = patch
        self.last = self.anchor
        self.box = list(box)

    def _patch(self, frame, box):
        fh, fw = frame.shape
        cx, cy, w, h = box
        x0, x1 = max(0, round((cx - w / 2) * fw)), min(fw, round((cx + w / 2) * fw))
        y0, y1 = max(0, round((cy - h / 2) * fh)), min(fh, round((cy + h / 2) * fh))
        return frame[y0:y1, x0:x1].copy() if x1 - x0 >= 8 and y1 - y0 >= 8 else None

    def step(self, frame_rgb):
        """True se o pote continua no quadro; atualiza a posição."""
        if self.anchor is None:
            return False
        cv = self.cv
        frame = gray(cv, frame_rgb)
        fh, fw = frame.shape
        cx, cy, w, h = self.box
        pad_w, pad_h = .7 * w, .7 * h
        x0, x1 = max(0, round((cx - w / 2 - pad_w) * fw)), min(fw, round((cx + w / 2 + pad_w) * fw))
        y0, y1 = max(0, round((cy - h / 2 - pad_h) * fh)), min(fh, round((cy + h / 2 + pad_h) * fh))
        region = frame[y0:y1, x0:x1]
        found = {}
        for name, template in (('ancora', self.anchor), ('ultimo', self.last)):
            if template is None:
                continue
            for scale in self.SCALES:
                size = (max(6, round(template.shape[1] * scale)), max(6, round(template.shape[0] * scale)))
                if size[0] >= region.shape[1] or size[1] >= region.shape[0]:
                    continue
                t = cv.resize(template, size, interpolation=cv.INTER_AREA)
                if float(t.std()) < 4:
                    continue
                result = cv.matchTemplate(region, t, cv.TM_CCOEFF_NORMED)
                _, value, _, location = cv.minMaxLoc(result)
                if value > found.get(name, (-1,))[0]:
                    found[name] = (value, location, size)
        anchor = found.get('ancora', (-1, None, None))
        last = found.get('ultimo', (-1, None, None))
        # O pote original precisa continuar reconhecível: o último quadro ajuda no movimento,
        # mas sozinho deixaria o acompanhamento escorregar para outro objeto.
        if anchor[0] >= .55:
            best = anchor if anchor[0] >= last[0] - .1 else last
        elif anchor[0] >= .4 and last[0] >= .8:
            best = last
        else:
            return False
        (x, y), (w_px, h_px) = best[1], best[2]
        # Continuidade: o pote anda pouco de um quadro para o outro. Um salto para outra
        # região só vale com semelhança muito alta (evita seguir o fundo depois que ele sai).
        jump = np.hypot((x0 + x + w_px / 2) / fw - cx, (y0 + y + h_px / 2) / fh - cy) / max(1e-6, max(w, h))
        if jump > .35 and best[0] < .85:
            return False
        self.box = [(x0 + x + w_px / 2) / fw, (y0 + y + h_px / 2) / fh, w_px / fw, h_px / fh]
        patch = self._patch(frame, self.box)
        if patch is not None:
            self.last = patch
        return True


def boundary(frames, tracker, cut=CUT, start=None, relocate=None, retries=2):
    """Percorre quadros (em ordem de afastamento da aparição) até perder o pote ou cruzar um corte.

    `start` é o quadro da borda: um corte logo depois dele também encerra a busca.
    `relocate(rgb)` reencontra o pote (pelo nome ou pela referência) quando o acompanhamento
    se perde, por exemplo com o pote girando; é tentado no máximo `retries` vezes.
    Retorna (índice do último quadro em que o pote aparece ou -1, se parou num corte).
    Uma única falha isolada é tolerada; duas seguidas encerram.
    """
    last_seen, misses = -1, 0
    previous = tiny(start) if start is not None else None
    for i, rgb in enumerate(frames):
        small = tiny(rgb)
        if previous is not None and float(np.abs(small - previous).mean()) >= cut:
            return last_seen, True
        previous = small
        if tracker.step(rgb):
            last_seen, misses = i, 0
            continue
        misses += 1
        if misses >= 2:
            box = relocate(rgb) if relocate and retries > 0 else None
            retries -= 1
            if not box:
                break
            tracker.restart(rgb, box)
            last_seen, misses = i, 0
    return last_seen, False

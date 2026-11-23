"""Referências visuais locais, ancoradas no nome lido com alta confiança."""

from typing import NamedTuple

import numpy as np


class _Anchor(NamedTuple):
    text: str
    box: np.ndarray
    image: np.ndarray
    points: np.ndarray
    descriptors: np.ndarray
    label_points: np.ndarray
    label_slice: tuple


class LabelReference:
    """Reconhece o mesmo rótulo em outro quadro com correspondência geométrica.

    Os resultados são candidatos para revisão. Um pote genérico ou a cor da
    embalagem não são evidências suficientes. O trabalho é limitado por quadro.
    """

    MAX_ANCHORS = 6
    MAX_SIDE = 960

    def __init__(self):
        self.anchors = []
        try:
            import cv2
            self.cv = cv2
            self.detector = cv2.SIFT_create(nfeatures=650, contrastThreshold=.025)
            self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        except (ImportError, AttributeError):
            self.detector = None

    def _gray(self, rgb):
        gray = self.cv.cvtColor(rgb, self.cv.COLOR_RGB2GRAY)
        height, width = gray.shape
        factor = min(1., self.MAX_SIDE / max(height, width))
        if factor < 1:
            gray = self.cv.resize(gray, (max(1, round(width * factor)), max(1, round(height * factor))),
                                  interpolation=self.cv.INTER_AREA)
        return gray

    def add(self, rgb, item):
        if self.detector is None or len(self.anchors) >= self.MAX_ANCHORS or len(item) < 6:
            return False
        text, confidence, y, width, x, height = item[:6]
        values = (confidence, y, width, x, height)
        if not text or not all(np.isfinite(v) for v in values) or confidence < .88:
            return False
        if not 0 < width <= .65 or not 0 < height <= .25:
            return False
        gray = self._gray(rgb)
        frame_h, frame_w = gray.shape
        left, right = (x - width / 2) * frame_w, (x + width / 2) * frame_w
        top, bottom = (y - height / 2) * frame_h, (y + height / 2) * frame_h
        if not (0 <= left < right <= frame_w and 0 <= top < bottom <= frame_h):
            return False
        if right - left < 30 or bottom - top < 9:
            return False
        # Guarda o texto e o detalhe imediatamente ao redor, evitando o cenário.
        x0 = max(0, int(left - .18 * (right - left)))
        x1 = min(frame_w, int(right + .18 * (right - left)) + 1)
        y0 = max(0, int(top - .9 * (bottom - top)))
        y1 = min(frame_h, int(bottom + .9 * (bottom - top)) + 1)
        crop = np.ascontiguousarray(gray[y0:y1, x0:x1])
        a, b, c, d = left - x0, top - y0, right - x0, bottom - y0
        label_slice = np.s_[round(b):round(d), round(a):round(c)]
        if crop[label_slice].std() < 12:
            return False
        points, descriptors = self.detector.detectAndCompute(crop, None)
        if descriptors is None or len(points) < 10:
            return False
        points = np.array([p.pt for p in points], dtype=np.float32)
        in_label = (points[:, 0] >= a) & (points[:, 0] <= c) & (points[:, 1] >= b) & (points[:, 1] <= d)
        if np.count_nonzero(in_label) < 7:
            return False
        box = np.array([[a, b], [c, b], [c, d], [a, d]], dtype=np.float32)
        self.anchors.append(_Anchor(str(text), box, crop, points, descriptors, in_label, label_slice))
        return True

    def _locate(self, anchor, image, target, descriptors):
        pairs = self.matcher.knnMatch(anchor.descriptors, descriptors, k=2)
        best = {}
        for pair in pairs:
            if len(pair) != 2:
                continue
            first, second = pair
            if first.distance < .72 * second.distance:
                prior = best.get(first.trainIdx)
                if prior is None or first.distance < prior.distance:
                    best[first.trainIdx] = first
        if len(best) < 8:
            return None
        source_ids = [m.queryIdx for m in best.values()]
        source = anchor.points[source_ids]
        destination = target[list(best)]
        transform, accepted = self.cv.estimateAffinePartial2D(source, destination,
                                                              ransacReprojThreshold=2.5,
                                                              maxIters=450, confidence=.99)
        if transform is None:
            return None
        inliers = accepted.ravel().astype(bool)
        n_inliers = int(inliers.sum())
        if n_inliers < 8 or n_inliers < .72 * len(best):
            return None
        label = source[inliers & anchor.label_points[source_ids]]
        extent = np.ptp(anchor.box, axis=0)
        if len(label) < 6 or np.any(np.ptp(label, axis=0) < extent * [.38, .34]):
            return None
        scale = np.linalg.norm(transform[:, 0])
        if not .55 <= scale <= 1.9:
            return None
        corners = self.cv.transform(anchor.box[None], transform)[0]
        low, high = corners.min(axis=0), corners.max(axis=0)
        frame_h, frame_w = image.shape
        if np.any(low < 0) or np.any(high > [frame_w, frame_h]):
            return None

        # Compara os pixels do nome no alinhamento encontrado; rejeita o mesmo
        # modelo de pote com outro nome, ainda que o entorno seja parecido.
        registered = self.cv.warpAffine(image, transform, anchor.image.shape[::-1],
                                       flags=self.cv.INTER_LINEAR | self.cv.WARP_INVERSE_MAP)
        observed = self.cv.GaussianBlur(registered[anchor.label_slice], (3, 3), 0)
        original = self.cv.GaussianBlur(anchor.image[anchor.label_slice], (3, 3), 0)
        if observed.std() < 7:
            return None
        resemblance = float(self.cv.matchTemplate(observed, original, self.cv.TM_CCOEFF_NORMED)[0, 0])
        if resemblance < .72:
            return None
        # O mesmo layout com uma letra trocada pode ter semelhança global alta.
        # Compara fatias sobrepostas onde a referência tem traços nítidos.
        step = max(6, original.shape[1] // max(6, sum(c.isalnum() for c in anchor.text)) // 2)
        for x in range(0, original.shape[1] - 2 * step + 1, step):
            expected = original[:, x:x + 2 * step]
            if expected.std() < 18:
                continue
            actual = observed[:, x:x + 2 * step]
            score = self.cv.matchTemplate(actual, expected, self.cv.TM_CCOEFF_NORMED)[0, 0]
            if score < .80:
                return None
        center = (low + high) / 2 / [frame_w, frame_h]
        width, height = (high - low) / [frame_w, frame_h]
        item = [anchor.text, .82, round(float(center[1]), 4), round(float(width), 4),
                round(float(center[0]), 4), round(float(height), 4), 'referencia_visual']
        return (resemblance, n_inliers), item

    def match(self, rgb):
        if not self.anchors:
            return None
        image = self._gray(rgb)
        points, descriptors = self.detector.detectAndCompute(image, None)
        if descriptors is None or len(points) < 8:
            return None
        points = np.array([p.pt for p in points], dtype=np.float32)
        best = None
        for anchor in self.anchors:
            detection = self._locate(anchor, image, points, descriptors)
            if detection and (best is None or detection[0] > best[0]):
                best = detection
        return best[1] if best else None

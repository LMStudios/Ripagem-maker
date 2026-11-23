import unittest

import numpy as np

from plataforma.visual_referencia import LabelReference


class LabelReferenceTests(unittest.TestCase):
    def setUp(self):
        self.ref = LabelReference()
        if self.ref.detector is None:
            self.skipTest('OpenCV sem SIFT')
        self.cv = self.ref.cv

    def label(self, text):
        cv = self.cv
        image = np.full((420, 520, 3), 38, np.uint8)
        cv.rectangle(image, (125, 85), (390, 320), (170, 170, 170), -1)
        cv.rectangle(image, (129, 130), (383, 245), (234, 232, 230), -1)
        cv.circle(image, (170, 215), 17, (25, 65, 100), 3, cv.LINE_AA)
        for i in range(34):
            cv.line(image, (202 + 3 * i, 207), (202 + 3 * i, 223), (10, 10, 10), i % 3 + 1)
        cv.putText(image, text, (151, 190), cv.FONT_HERSHEY_DUPLEX, 1.06, (14, 30, 46), 2, cv.LINE_AA)
        return image

    def target(self, text='VERTILUM'):
        image = self.label(text)
        transform = self.cv.getRotationMatrix2D((265, 177), 7, .83)
        transform[:, 2] += [-20, 28]
        warped = self.cv.warpAffine(image, transform, (520, 420), borderValue=(38, 38, 38))
        return self.cv.GaussianBlur(warped, (5, 5), 1.1)

    @staticmethod
    def coordinates(conf=.99):
        return ('VERTILUM', conf, 178 / 420, 170 / 520, 236 / 520, 33 / 420)

    def test_detects_translated_scaled_and_blurred_label(self):
        self.assertTrue(self.ref.add(self.label('VERTILUM'), self.coordinates()))
        match = self.ref.match(self.target())
        self.assertIsNotNone(match)
        self.assertEqual(match[0], 'VERTILUM')
        self.assertEqual(match[-1], 'referencia_visual')
        self.assertAlmostEqual(match[2], .49, delta=.04)
        self.assertAlmostEqual(match[4], .42, delta=.04)

    def test_rejects_same_pot_with_different_name_or_no_name(self):
        self.assertTrue(self.ref.add(self.label('VERTILUM'), self.coordinates()))
        for text in ('AERALUX', '', 'VELOCITY', 'VEKTILUM', 'VERTILUN', 'VERTILU'):
            with self.subTest(text=text):
                self.assertIsNone(self.ref.match(self.target(text)))

    def test_limits_references_and_rejects_empty_or_uncertain_anchors(self):
        self.assertFalse(self.ref.add(self.label('VERTILUM'), self.coordinates(.4)))
        self.assertFalse(self.ref.add(np.full((420, 520, 3), 38, np.uint8), self.coordinates()))
        for _ in range(self.ref.MAX_ANCHORS):
            self.assertTrue(self.ref.add(self.label('VERTILUM'), self.coordinates()))
        self.assertFalse(self.ref.add(self.label('VERTILUM'), self.coordinates()))


if __name__ == '__main__':
    unittest.main()

"""Shared alignment primitives: asymmetric ink and lossless frozen-glyph shifts."""
import unittest

import numpy as np
from PIL import Image

from prints import move_flat_ink, optical_x


class AlignmentTests(unittest.TestCase):
    def test_centroid_uses_coverage(self):
        mask = Image.new("L", (5, 2))
        mask.putpixel((0, 0), 255)
        mask.putpixel((4, 1), 85)
        self.assertAlmostEqual(optical_x(mask), 1.0)

    def test_empty_centroid_rejected(self):
        with self.assertRaises(ValueError):
            optical_x(Image.new("L", (3, 3)))

    def test_overlapping_translation_preserves_pixels_and_alpha(self):
        image = Image.new("RGBA", (8, 3), (10, 20, 30, 180))
        image.putpixel((2, 1), (110, 120, 130, 180))
        image.putpixel((3, 1), (210, 220, 230, 180))
        mask = Image.new("L", image.size)
        mask.putpixel((2, 1), 255)
        mask.putpixel((3, 1), 255)
        moved, ink = move_flat_ink(image, mask, 1, (10, 20, 30))
        self.assertEqual(moved.getpixel((2, 1)), (10, 20, 30, 180))
        self.assertEqual(moved.getpixel((3, 1)), image.getpixel((2, 1)))
        self.assertEqual(moved.getpixel((4, 1)), image.getpixel((3, 1)))
        self.assertEqual(ink.getbbox(), (3, 1, 5, 2))
        self.assertTrue(np.array_equal(np.array(image)[:, :, 3], np.array(moved)[:, :, 3]))

    def test_translation_outside_canvas_rejected(self):
        mask = Image.new("L", (3, 2))
        mask.putpixel((0, 0), 255)
        with self.assertRaises(ValueError):
            move_flat_ink(Image.new("RGB", mask.size), mask, -1, (0, 0, 0))

    def test_passport_centroid_matches_renderer(self):
        from passport import measure
        mask = Image.new("L", (10, 10))
        for y in range(1, 9):
            for x in range(1, 4):
                mask.putpixel((x, y), 255)
        for y in range(1, 5):
            for x in range(4, 8):
                mask.putpixel((x, y), 170)
        coverage = np.asarray(mask, dtype=float) / 255
        result, _ = measure(coverage > 0, np.zeros((10, 10), bool), coverage, None, 1, "Р")
        self.assertAlmostEqual(result["cx_массы"], optical_x(mask))

    def test_layer_scope_includes_original_and_displaced_line(self):
        from layer_localized import allowed
        mask = allowed((200, 100), [{"labels": [{"box": [30, 30, 50, 50],
                          "сдвиг_строк": [[0, 0], [100, 0]]}]}])
        self.assertEqual(mask.getpixel((40, 40)), 255)
        self.assertEqual(mask.getpixel((140, 40)), 255)
        self.assertEqual(mask.getpixel((90, 40)), 0)


if __name__ == "__main__":
    unittest.main()

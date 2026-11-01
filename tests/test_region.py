import ctypes as C
import unittest

import numpy as np
from PIL import Image

from jcc_assistant.mumu import MuMu
from jcc_assistant.recognition import Recognizer


class FakeLib:
    def __init__(self, image):
        self.image = image
        self.raw = image.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()

    def nemu_capture_display(self, handle, display, length, w, h, buffer):
        C.cast(w, C.POINTER(C.c_int))[0] = self.image.width
        C.cast(h, C.POINTER(C.c_int))[0] = self.image.height
        if length:
            C.memmove(buffer, self.raw, len(self.raw))
        return 0


class RegionTests(unittest.TestCase):
    def test_region_matches_full_frame_crops_and_coordinates(self):
        source = Image.open("tests/fixtures/shop.png").convert("RGB")
        for size in [(2048, 1536), (1024, 768)]:
            with self.subTest(size=size):
                m = MuMu.__new__(MuMu)
                m.lib = FakeLib(source.resize(size))
                m.size = (0, 0)
                m.buffer = None
                m.handle = 1
                m.display = 0
                full, _ = m.capture()
                roi, _ = m.capture_shop()
                self.assertEqual(roi.info["android_size"], size)
                self.assertLess(roi.width * roi.height, full.width * full.height / 20)
                from jcc_assistant.upgrade import hint_boxes

                self.assertEqual(len(roi.info["upgrade_regions"]), 5)
                for box, patch in zip(hint_boxes(size), roi.info["upgrade_regions"]):
                    self.assertTrue(np.array_equal(np.asarray(full.crop(box)), np.asarray(patch)))
                recognizer = Recognizer.__new__(Recognizer)
                for global_box, local_box in zip(
                    recognizer.regions(size), recognizer.regions_for(roi)
                ):
                    self.assertTrue(
                        np.array_equal(
                            np.asarray(full.crop(global_box)), np.asarray(roi.crop(local_box))
                        )
                    )

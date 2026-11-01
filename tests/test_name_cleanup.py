import unittest
from types import SimpleNamespace

from PIL import Image

from jcc_assistant.recognition import Recognizer, clean_name


class NameCleanupTests(unittest.TestCase):
    def test_edge_noise_removed_internal_separator_preserved(self):
        self.assertEqual(clean_name("·菲兹·1"), "菲兹")
        self.assertEqual(clean_name("德文·阿曼博"), "德文·阿曼博")

    def test_batch_slot_and_detail_all_normalize_fizz(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.engine = SimpleNamespace(
            recognize_txt=lambda crops: SimpleNamespace(
                txts=["菲兹·"] * len(crops), scores=[1.0] * len(crops)
            )
        )
        image = Image.new("RGB", (2048, 1536))
        cards, _, _ = recognizer.recognize(image, ["菲兹"])
        self.assertTrue(all(c.name == "菲兹" and c.target for c in cards))
        self.assertEqual(recognizer.recognize_slot(image, 1)[0].name, "菲兹")
        self.assertEqual(recognizer.recognize_detail_name(image)[0], "菲兹")

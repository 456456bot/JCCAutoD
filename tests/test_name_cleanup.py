import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image

from jcc_assistant.recognition import Recognizer, clean_name


class NameCleanupTests(unittest.TestCase):
    def test_observed_fizz_name_reprocessing_crosses_purchase_threshold(self):
        recognizer = Recognizer()
        with Image.open("tests/fixtures/fizz_name.png") as crop:
            raw = recognizer.engine.recognize_txt([np.asarray(crop)[:, :, ::-1].copy()])
            self.assertLess(raw.scores[0], 0.98)
            name, score = recognizer.retry_target(
                crop, clean_name(raw.txts[0]), raw.scores[0], ["菲兹"]
            )
        self.assertEqual(name, "菲兹")
        self.assertGreaterEqual(score, 0.98)

    def test_retry_never_maps_another_hero_to_target(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.engine = SimpleNamespace(
            recognize_txt=lambda crops: SimpleNamespace(txts=["璐璐"], scores=[1.0])
        )
        self.assertEqual(
            recognizer.retry_target(Image.new("RGB", (198, 41)), "菲兹", 0.85, ["菲兹"]),
            ("菲兹", 0.85),
        )

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

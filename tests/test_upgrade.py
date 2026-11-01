import json
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image

from jcc_assistant.purchasing import Buyer
from jcc_assistant.recognition import Card
from jcc_assistant.settings import load_config, load_stop_rules, save_config
from jcc_assistant.targets import TargetList
from jcc_assistant.upgrade import ASSETS, UpgradeDetector


class UpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = UpgradeDetector()

    def test_user_video_contains_normal_two_and_three(self):
        with Image.open(ASSETS / "video_source.png") as image:
            regions = [image.crop((x + 1, 73, x + 73, 109)) for x in (168, 354, 540, 724, 910)]
        self.assertEqual([self.detector.classify(p) for p in regions], [0, 2, 0, 3, 0])
        for factor in (0.75, 1.5):
            self.assertEqual(
                [
                    self.detector.classify(
                        p.resize((round(p.width * factor), round(p.height * factor)))
                    )
                    for p in regions
                ],
                [0, 2, 0, 3, 0],
            )

    def test_existing_shop_has_no_hint(self):
        with Image.open("tests/fixtures/shop.png") as image:
            self.assertEqual(self.detector.detect(image), [0] * 5)
            self.assertEqual(self.detector.detect(image.resize((1024, 768))), [0] * 5)

    def test_expanded_region_preserves_stars_above_old_capture(self):
        with Image.open(ASSETS / "video_source.png") as image:
            star = image.crop((725, 73, 797, 109)).resize((118, 59))
        for y in (0, 20, 40):
            region = Image.new("RGB", (118, 100), "#202020")
            region.paste(star, (0, y))
            self.assertEqual(self.detector.classify(region), 3)

    def test_solid_gold_is_not_a_three_star_hint(self):
        self.assertEqual(self.detector.classify(Image.new("RGB", (118, 100), "#ffdb40")), 0)

    def test_name_strip_without_hint_metadata_never_invents_hint(self):
        image = Image.new("RGB", (1490, 52), "white")
        image.info["origin"] = (430, 1460)
        self.assertEqual(self.detector.detect(image), [0] * 5)

    def run_purchase(self, rule, hint, fail=False):
        targets = TargetList()
        targets.replace(["娑娜", "盖伦"], {"娑娜": rule, "盖伦": 0})
        clicks = []

        class Device:
            def tap(self, *point):
                if fail:
                    raise RuntimeError("touch failed")
                clicks.append(point)

        with tempfile.TemporaryDirectory() as directory:
            buyer = Buyer(None, [], threading.Event(), Path(directory), target_list=targets)
            cards = [
                Card(1, "娑娜", 1, (1, 1), upgrade=hint),
                Card(2, "娑娜", 1, (2, 2), upgrade=hint),
                Card(3, "盖伦", 1, (3, 3)),
            ]
            message = buyer.attempt(Device(), None, cards)
            buyer.flush_logs()
            records = [
                json.loads(line)
                for line in (Path(directory) / "events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
        return targets.snapshot()[1], clicks, message, records

    def test_last_click_removes_target_skips_same_name_and_keeps_other_targets(self):
        names, clicks, message, records = self.run_purchase(3, 3)
        self.assertEqual(names, ("盖伦",))
        self.assertEqual(clicks, [(1, 1), (3, 3)])
        self.assertIn("已从目标列表移除", message)
        self.assertTrue(records[0]["target_removed"])
        self.assertEqual(records[0]["outcome"], "click_sent")

    def test_two_star_goal_also_accepts_three_star_hint(self):
        for hint in (2, 3):
            names, clicks, _, _ = self.run_purchase(2, hint)
            self.assertNotIn("娑娜", names)
            self.assertEqual(clicks, [(1, 1), (3, 3)])

    def test_three_star_goal_keeps_buying_at_two_star_hint(self):
        names, clicks, _, _ = self.run_purchase(3, 2)
        self.assertIn("娑娜", names)
        self.assertEqual(len(clicks), 3)

    def test_continuous_goal_ignores_upgrade_hints(self):
        names, clicks, _, _ = self.run_purchase(0, 3)
        self.assertIn("娑娜", names)
        self.assertEqual(len(clicks), 3)

    def test_touch_error_never_marks_target_as_finished(self):
        names, clicks, message, records = self.run_purchase(3, 3, True)
        self.assertIn("娑娜", names)
        self.assertFalse(clicks)
        self.assertNotIn("已从目标列表移除", message)
        self.assertEqual(records[0]["outcome"], "touch_error")

    def test_rule_persistence_and_readd_uses_default(self):
        targets = TargetList()
        targets.default_rule = 3
        targets.add("娑娜")
        targets.set_rule("娑娜", 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_config(targets.snapshot()[1], path, stop_rules=targets.rules())
            self.assertEqual(load_config(path), ["娑娜"])
            self.assertEqual(load_stop_rules(["娑娜"], path), {"娑娜": 2})
            path.write_text(
                '{"version":3,"targets":["娑娜"],"stop_rules":{"娑娜":9}}', encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                load_stop_rules(["娑娜"], path)
        targets.clear()
        targets.add("娑娜")
        self.assertEqual(targets.rules(), {"娑娜": 3})

    def test_edit_after_auto_removal_does_not_restore_old_target(self):
        targets = TargetList()
        targets.default_rule = 3
        targets.replace(["娑娜", "盖伦"])
        targets.dispatch_purchase("娑娜", lambda: None, 3)
        targets.edit("盖伦", "盖伦", 2)
        self.assertEqual(targets.snapshot()[1], ("盖伦",))
        self.assertEqual(targets.rules(), {"盖伦": 2})
        with self.assertRaises(ValueError):
            targets.edit("娑娜", "娑娜", 2)

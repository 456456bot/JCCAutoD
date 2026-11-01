import json
import tempfile
import threading
import unittest
from pathlib import Path

from jcc_assistant.purchasing import Buyer
from jcc_assistant.recognition import Card


class FakeDevice:
    def __init__(self):
        self.clicks = []

    def capture(self):
        raise AssertionError("Direct dispatch must not capture")

    def tap(self, *point):
        self.clicks.append(point)


class PurchaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cancel = threading.Event()
        self.device = FakeDevice()
        self.buyer = Buyer(object(), ["娑娜", "盖伦"], self.cancel, Path(self.temp.name))
        self.cards = [Card(1, "娑娜", 0.999, (575, 1370)), Card(3, "盖伦", 0.999, (1175, 1370))]

    def tearDown(self):
        self.buyer.flush_logs()

    def test_multiple_targets_direct_click_without_capture_or_ocr(self):
        result = self.buyer.attempt(self.device, None, self.cards)
        self.assertEqual(self.device.clicks, [(575, 1370), (1175, 1370)])
        self.assertIn("未确认购买结果", result)
        self.assertFalse(self.cancel.is_set())

    def test_no_time_cooldown_between_changed_frames(self):
        self.buyer.attempt(self.device, None, self.cards)
        self.buyer.attempt(self.device, None, self.cards)
        self.assertEqual(len(self.device.clicks), 4)

    def test_new_name_same_slot_clicks_immediately(self):
        self.buyer.attempt(self.device, None, self.cards[:1])
        self.buyer.attempt(self.device, None, [Card(1, "盖伦", 0.999, (575, 1370))])
        self.assertEqual(len(self.device.clicks), 2)

    def test_cancel_during_first_touch_prevents_second(self):
        def tap(*point):
            self.device.clicks.append(point)
            self.cancel.set()

        self.device.tap = tap
        self.buyer.attempt(self.device, None, self.cards)
        self.assertEqual(len(self.device.clicks), 1)

    def test_no_quantity_stop(self):
        for i in range(12):
            self.buyer.attempt(self.device, None, self.cards[:1])
        self.assertEqual(self.buyer.counts["娑娜"], 12)
        self.assertFalse(self.cancel.is_set())

    def test_touch_error_stops(self):
        def tap(*point):
            raise RuntimeError("test failure")

        self.device.tap = tap
        result = self.buyer.attempt(self.device, None, self.cards)
        self.assertIn("触控异常", result)
        self.assertTrue(self.cancel.is_set())
        self.assertEqual(self.buyer.count, 0)

    def test_non_target_and_low_confidence_do_not_click(self):
        self.buyer.attempt(
            self.device, None, [Card(1, "慎", 1, (0, 0)), Card(2, "娑娜", 0.5, (0, 0))]
        )
        self.assertEqual(self.device.clicks, [])

    def test_audit_never_claims_successful_purchase(self):
        self.buyer.attempt(self.device, None, self.cards[:1])
        self.buyer.flush_logs()
        row = json.loads((Path(self.temp.name) / "events.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(row["outcome"], "click_sent")
        self.assertNotIn("confirmed_count", row)

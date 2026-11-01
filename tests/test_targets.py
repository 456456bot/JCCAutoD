import tempfile
import threading
import unittest
from pathlib import Path

from jcc_assistant.purchasing import Buyer
from jcc_assistant.recognition import Card
from jcc_assistant.targets import TargetList


class DynamicTargetTests(unittest.TestCase):
    def test_add_delete_replace_and_empty_list(self):
        targets = TargetList()
        self.assertEqual(targets.snapshot()[1], ())
        targets.add("娑娜")
        old = targets.activation_snapshot()[2]["娑娜"]
        targets.add("盖伦")
        self.assertEqual(targets.activation_snapshot()[2]["娑娜"], old)
        targets.replace(["盖伦"])
        self.assertFalse(targets.dispatch("娑娜", lambda: self.fail("deleted target clicked")))
        targets.add("娑娜")
        self.assertGreater(targets.activation_snapshot()[2]["娑娜"], old)
        targets.clear()
        self.assertEqual(targets.snapshot()[1], ())

    def test_f8_invalidates_inflight_selection(self):
        targets = TargetList()
        epoch = targets.selection_epoch()
        targets.clear()
        self.assertIsNone(targets.add_selection("娑娜", epoch))
        self.assertEqual(targets.snapshot()[1], ())
        self.assertTrue(targets.add_selection("盖伦", targets.selection_epoch()))

    def test_latest_list_checked_between_clicks(self):
        targets = TargetList()
        targets.replace(["娑娜", "盖伦"])
        clicks = []

        class Device:
            def tap(self, *point):
                clicks.append(point)
                targets.replace(["娑娜"])

        with tempfile.TemporaryDirectory() as directory:
            buyer = Buyer(None, [], threading.Event(), Path(directory), target_list=targets)
            buyer.attempt(Device(), None, [Card(1, "娑娜", 1, (1, 1)), Card(2, "盖伦", 1, (2, 2))])
            buyer.flush_logs()
            self.assertEqual(clicks, [(1, 1)])

    def test_new_target_only_does_not_reclick_existing_target(self):
        targets = TargetList()
        targets.replace(["娑娜", "盖伦"])
        clicks = []

        class Device:
            def tap(self, *point):
                clicks.append(point)

        with tempfile.TemporaryDirectory() as directory:
            buyer = Buyer(None, [], threading.Event(), Path(directory), target_list=targets)
            buyer.attempt(
                Device(),
                None,
                [Card(1, "娑娜", 1, (1, 1)), Card(2, "盖伦", 1, (2, 2))],
                eligible_names={"盖伦"},
            )
            buyer.flush_logs()
            self.assertEqual(clicks, [(2, 2)])

    def test_clear_before_dispatch_prevents_all_clicks(self):
        targets = TargetList()
        targets.add("娑娜")
        with tempfile.TemporaryDirectory() as directory:
            buyer = Buyer(None, [], threading.Event(), Path(directory), target_list=targets)
            targets.clear()
            buyer.attempt(object(), None, [Card(1, "娑娜", 1, (1, 1))])
            self.assertEqual(buyer.count, 0)

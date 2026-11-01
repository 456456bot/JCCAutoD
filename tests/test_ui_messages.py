import queue
import unittest

from jcc_assistant.ui_messages import UiMessages


class UiMessageTests(unittest.TestCase):
    def test_previews_are_coalesced_and_stop_events_are_delivered_first(self):
        messages = UiMessages()
        for n in range(10000):
            messages.put(("result", n, None))
        messages.put(("cleared", "F8", None))
        self.assertEqual(messages.get_nowait(), ("cleared", "F8", None))
        self.assertEqual(messages.get_nowait(), ("result", 9999, None))
        with self.assertRaises(queue.Empty):
            messages.get_nowait()

    def test_purchase_and_auto_stop_are_not_dropped(self):
        messages = UiMessages()
        messages.put(("search", ("waiting", 1, False), None))
        messages.put(("purchase", "one", None))
        messages.put(("purchase", "two", None))
        messages.put(("search", ("stopped", 2, True), None))
        self.assertEqual(messages.get_nowait()[1], "one")
        self.assertEqual(messages.get_nowait()[1], "two")
        self.assertEqual(messages.get_nowait()[1], ("stopped", 2, True))

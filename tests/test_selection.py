import unittest
from types import SimpleNamespace

from jcc_assistant.hotkey import EmergencyHotkey
from jcc_assistant.selection import read_selection


class SelectionTests(unittest.TestCase):
    def test_read_latest_slot_without_touch(self):
        calls = []
        device = SimpleNamespace(capture_shop=lambda: ("fresh-image", 12))

        def recognize(image, slot):
            calls.append((image, slot))
            return SimpleNamespace(name="娑娜", confidence=0.999), 18

        recognizer = SimpleNamespace(recognize_slot=recognize)
        self.assertEqual(read_selection(device, recognizer, 3, 1, clock=lambda: 1.1), "娑娜")
        self.assertEqual(calls, [("fresh-image", 3)])

    def test_empty_and_low_confidence_rejected(self):
        device = SimpleNamespace(capture_shop=lambda: (None, 0))
        for name, score in [("", 1), ("娑娜", 0.7)]:
            recognizer = SimpleNamespace(
                recognize_slot=lambda *args: (SimpleNamespace(name=name, confidence=score), 0)
            )
            with self.subTest(name=name), self.assertRaises(ValueError):
                read_selection(device, recognizer, 1, 1, clock=lambda: 1.1)

    def test_stale_request_never_reads_screen(self):
        with self.assertRaises(ValueError):
            read_selection(object(), object(), 1, 1, clock=lambda: 2)

    def test_timeout_after_read_rejected(self):
        times = iter([1.1, 2])
        device = SimpleNamespace(capture_shop=lambda: (None, 0))
        recognizer = SimpleNamespace(
            recognize_slot=lambda *args: (SimpleNamespace(name="娑娜", confidence=1), 0)
        )
        with self.assertRaises(ValueError):
            read_selection(device, recognizer, 1, 1, clock=lambda: next(times))

    def test_numpad_and_emergency_routes_are_separate(self):
        events = []
        hotkey = EmergencyHotkey.__new__(EmergencyHotkey)
        hotkey.ok = True
        hotkey.callback = lambda: events.append("stop")
        hotkey.on_select = lambda slot: events.append(slot)
        hotkey.selection_ok = {1: True, 2: False, 3: True, 4: True, 5: True}
        for key in [101, 102, 103, 104, 105, 1, 999]:
            hotkey.dispatch(key)
        self.assertEqual(events, [1, 3, 4, 5, "stop"])

import ctypes as C
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image

from jcc_assistant.detail import (
    detail_anchor_box,
    detail_name_box,
    panel_visible,
    read_detail_selection,
)
from jcc_assistant.hotkey import EmergencyHotkey
from jcc_assistant.mumu import MuMu
from jcc_assistant.recognition import Recognizer
from jcc_assistant.targets import TargetList


class FakeLib:
    def __init__(self, image):
        self.image = image
        self.raw = image.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
        self.captures = 0

    def nemu_capture_display(self, handle, display, length, w, h, buffer):
        C.cast(w, C.POINTER(C.c_int))[0] = self.image.width
        C.cast(h, C.POINTER(C.c_int))[0] = self.image.height
        if length:
            self.captures += 1
            C.memmove(buffer, self.raw, len(self.raw))
        return 0


class DetailTests(unittest.TestCase):
    def test_user_detail_screenshot_recognizes_name_at_two_resolutions(self):
        recognizer = Recognizer()
        with Image.open("assets/detail/reference.png") as original:
            for size in (original.size, (2048, 1536)):
                image = original.resize(size)
                device = MuMu.__new__(MuMu)
                device.lib = FakeLib(image)
                device.handle = 1
                device.display = 0
                device.size = (0, 0)
                device.buffer = None
                crop, _ = device.capture_detail()
                self.assertEqual(device.lib.captures, 1)
                self.assertTrue(crop.info["detail_panel_visible"])
                self.assertTrue(
                    np.array_equal(
                        np.asarray(crop),
                        np.asarray(image.convert("RGB").crop(detail_name_box(size))),
                    )
                )
                name, score = recognizer.recognize_detail_name(crop)
                self.assertEqual(name, "厄斐琉斯")
                self.assertGreaterEqual(score, 0.98)

    def test_closed_panel_rejected_before_ocr(self):
        with Image.open("tests/fixtures/shop.png") as image:
            self.assertFalse(panel_visible(image.crop(detail_anchor_box(image.size))))
        image = Image.new("RGB", (203, 39))
        device = SimpleNamespace(capture_detail=lambda: (image, 0))
        with self.assertRaises(ValueError):
            read_detail_selection(device, object(), 1, clock=lambda: 1.1)

    def test_expired_low_confidence_and_timeout_do_not_mutate_targets(self):
        with self.assertRaises(ValueError):
            read_detail_selection(object(), object(), 1, clock=lambda: 3)
        image = Image.new("RGB", (203, 39))
        image.info["detail_panel_visible"] = True
        device = SimpleNamespace(capture_detail=lambda: (image, 0))
        for name, score in [("", 1), ("厄斐琉斯", 0.7)]:
            ocr = SimpleNamespace(recognize_detail_name=lambda image: (name, score))
            with self.assertRaises(ValueError):
                read_detail_selection(device, ocr, 1, clock=lambda: 1.1)
        ticks = iter((1.1, 3))
        with self.assertRaises(ValueError):
            read_detail_selection(device, ocr, 1, clock=lambda: next(ticks))

    def test_detail_add_continuous_preserves_existing_rule_and_f8_invalidates_reply(self):
        targets = TargetList()
        targets.default_rule = 3
        epoch = targets.selection_epoch()
        self.assertTrue(targets.detail_selection("厄斐琉斯", "add", epoch))
        self.assertEqual(targets.rules(), {"厄斐琉斯": 0})
        targets.set_rule("厄斐琉斯", 2)
        self.assertFalse(targets.detail_selection("厄斐琉斯", "add", epoch))
        self.assertEqual(targets.rules(), {"厄斐琉斯": 2})
        self.assertTrue(targets.detail_selection("厄斐琉斯", "remove", epoch))
        self.assertFalse(targets.snapshot()[1])
        targets.clear()
        self.assertIsNone(targets.detail_selection("厄斐琉斯", "add", epoch))

    def test_plus_minus_are_independent_of_shop_and_emergency_keys(self):
        events = []
        hotkey = EmergencyHotkey.__new__(EmergencyHotkey)
        hotkey.ok = True
        hotkey.callback = lambda: events.append("stop")
        hotkey.on_select = lambda slot: events.append(slot)
        hotkey.selection_ok = {1: True}
        hotkey.on_detail = lambda action: events.append(action)
        hotkey.detail_ok = {"add": True, "remove": True}
        for key in (201, 202, 101, 1, 0xBB, 0xBD):
            hotkey.dispatch(key)
        self.assertEqual(events, ["add", "remove", 1, "stop"])

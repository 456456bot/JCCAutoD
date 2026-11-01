import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from jcc_assistant.economy import Economy, refresh_point
from jcc_assistant.purchasing import Buyer
from jcc_assistant.recognition import Card
from jcc_assistant.search import AUTOMATIC, MANUAL
from jcc_assistant.ui import run


class AutoUiTests(unittest.TestCase):
    def test_mode_requires_start_refreshes_once_and_retains_list_at_coin_floor(self):
        state = {"frame": 0, "captures": 0}
        keys = []
        clicks = []
        buyers = []
        errors = []
        case = self

        class Keys:
            def __init__(self, callback, on_select=None, on_detail=None):
                self.callback = callback
                self.on_detail = on_detail
                self.ok = True
                self.selection_ok = {}
                self.detail_ok = {"add": True, "remove": True}
                keys.append(self)

            def close(self):
                pass

        class Device:
            def capture_shop(self):
                state["captures"] += 1
                image = Image.new("RGB", (100, 20))
                image.info.update(android_size=(2048, 1536), frame=state["frame"])
                return image, 1

            def tap(self, *point):
                clicks.append(point)
                if point == refresh_point((2048, 1536)):
                    state["frame"] += 1

            def close(self):
                pass

        class OCR:
            def recognize(self, image, targets=()):
                name = "其他" if image.info["frame"] == 0 else "新商店"
                return [Card(i, name, 1, (i, 0)) for i in range(1, 6)], 1, None

            def read_economy(self, image, price_slots=()):
                return Economy(
                    20 if image.info["frame"] == 0 else 18, 2, {s: 1 for s in price_slots}
                )

        class Hints:
            def detect(self, image):
                return [0] * 5

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)

        def button(root, text):
            return next(
                w for w in walk(root) if w.winfo_class() == "TButton" and w.cget("text") == text
            )

        def smoke(root):
            root.withdraw()
            root.report_callback_exception = lambda *args: errors.append(args)

            def until(predicate):
                end = time.perf_counter() + 3
                while time.perf_counter() < end:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.005)
                case.fail(f"UI timeout: {state}, {clicks}, {errors}")

            modes = next(
                w for w in walk(root) if w.winfo_class() == "TCombobox" and AUTOMATIC in w["values"]
            )
            case.assertEqual(modes.get(), MANUAL)
            case.assertTrue(button(root, "开始搜牌").instate(["disabled"]))
            modes.set(AUTOMATIC)
            modes.event_generate("<<ComboboxSelected>>")
            root.update()
            floor = next(w for w in walk(root) if w.winfo_class() == "TSpinbox")
            floor.delete(0, "end")
            floor.insert(0, "18")
            root.update()
            keys[0].on_detail("add")
            tree = next(w for w in walk(root) if w.winfo_class() == "Treeview")
            until(lambda: bool(tree.get_children()))
            case.assertEqual(state["captures"], 0)
            case.assertFalse(clicks)
            case.assertEqual(tree.item(tree.get_children()[0], "values")[3], "待开始")
            button(root, "开始搜牌").invoke()
            until(lambda: len(clicks) == 1 and button(root, "开始搜牌").instate(["!disabled"]))
            case.assertEqual(clicks, [refresh_point((2048, 1536))])
            case.assertEqual(tree.item(tree.get_children()[0], "values")[0], "目标")
            case.assertTrue(button(root, "停止搜牌").instate(["disabled"]))
            floor.delete(0, "end")
            floor.insert(0, "0")
            button(root, "开始搜牌").invoke()
            button(root, "停止搜牌").invoke()
            count = len(clicks)
            case.assertEqual(tree.item(tree.get_children()[0], "values")[0], "目标")
            case.assertTrue(button(root, "开始搜牌").instate(["!disabled"]))
            modes.set(MANUAL)
            modes.event_generate("<<ComboboxSelected>>")
            root.update()
            modes.set(AUTOMATIC)
            modes.event_generate("<<ComboboxSelected>>")
            root.update()
            case.assertEqual(len(clicks), count)
            button(root, "开始搜牌").invoke()
            button(root, "清空目标并停止（F8）").invoke()
            root.update()
            case.assertFalse(tree.get_children())
            case.assertTrue(button(root, "开始搜牌").instate(["!disabled"]))
            keys[0].on_detail("add")
            until(lambda: bool(tree.get_children()))
            keys[0].callback()
            until(lambda: not tree.get_children())
            case.assertFalse(errors, errors)
            root.tk.call(root.protocol("WM_DELETE_WINDOW"))

        with tempfile.TemporaryDirectory() as directory:

            def make_buyer(*args, **kwargs):
                buyer = Buyer(*args, **kwargs, log_dir=Path(directory) / "logs")
                buyers.append(buyer)
                return buyer

            with (
                patch("jcc_assistant.ui.EmergencyHotkey", Keys),
                patch("jcc_assistant.ui.MuMu", Device),
                patch("jcc_assistant.ui.Recognizer", OCR),
                patch("jcc_assistant.ui.UpgradeDetector", Hints),
                patch("jcc_assistant.ui.Buyer", make_buyer),
                patch("jcc_assistant.ui.PROFILES", Path(directory) / "profiles"),
                patch("jcc_assistant.ui.read_detail_selection", return_value="目标"),
                patch.object(tk.Tk, "mainloop", smoke),
            ):
                run()
            for buyer in buyers:
                buyer.flush_logs()

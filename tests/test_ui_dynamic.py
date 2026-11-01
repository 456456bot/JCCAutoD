import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from jcc_assistant.lineup.library import profile_path
from jcc_assistant.lineup.storage import make_profile, save_profile
from jcc_assistant.purchasing import Buyer as RealBuyer
from jcc_assistant.recognition import Card
from jcc_assistant.ui import run


class DynamicUiTests(unittest.TestCase):
    def test_list_drives_start_live_add_delete_clear_and_explicit_load(self):
        hooks, clicks, buyers = [], [], []
        state = {"ocr": 0, "scene": 0}
        errors = []
        case = self

        class Keys:
            def __init__(self, callback, on_select=None, on_detail=None):
                self.callback, self.on_select, self.on_detail = callback, on_select, on_detail
                self.detail_ok = {"add": True, "remove": True}
                self.ok = True
                self.selection_ok = {n: True for n in range(1, 6)}
                hooks.append(self)

            def close(self):
                pass

        class Device:
            def capture_shop(self):
                return Image.new("RGB", (100, 20)), 1

            def close(self):
                pass

            def tap(self, *point):
                clicks.append(point)

        class OCR:
            def recognize_slot(self, image, slot):
                return Card(slot, {1: "娑娜", 2: "盖伦"}[slot], 1, (slot, 0)), 1

            def recognize(self, image, targets=()):
                state["ocr"] += 1
                names = ["娑娜", "盖伦", "慎" if state["scene"] == 0 else "凯特琳", "", ""]
                return [Card(n, name, 1, (n, 0)) for n, name in enumerate(names, 1)], 1, None

        class Hints:
            def detect(self, image):
                return [0, state.get("upgrade", 0), 0, 0, 0]

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
            target_tree = next(w for w in walk(root) if w.winfo_class() == "Treeview")

            def names():
                return [target_tree.item(row, "values")[0] for row in target_tree.get_children()]

            def until(condition):
                deadline = time.perf_counter() + 3
                while time.perf_counter() < deadline:
                    root.update()
                    if condition():
                        return
                    time.sleep(0.005)
                case.fail(
                    f"UI timeout: targets={names()}, clicks={clicks}, state={state}, errors={errors}"
                )

            case.assertEqual(names(), [])
            case.assertEqual(state["ocr"], 0)
            labels = [w.cget("text") for w in walk(root) if w.winfo_class() == "TButton"]
            case.assertNotIn("开始任务", labels)
            case.assertNotIn("保存配置", labels)
            case.assertNotIn("载入配置", labels)
            case.assertFalse([w for w in walk(root) if w.winfo_class() == "TCheckbutton"])

            hooks[0].on_select(1)
            until(lambda: clicks == [(1, 0)])
            hooks[0].on_select(2)
            until(lambda: clicks == [(1, 0), (2, 0)])
            row = next(
                row
                for row in target_tree.get_children()
                if target_tree.item(row, "values")[0] == "娑娜"
            )
            target_tree.selection_set(row)
            button(root, "修改目标").invoke()
            dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            rule_box = next(w for w in walk(dialog) if w.winfo_class() == "TCombobox")
            case.assertEqual(rule_box.get(), "三星后移除")
            rule_box.set("二星后移除")
            button(dialog, "确定并生效").invoke()
            row = next(
                row
                for row in target_tree.get_children()
                if target_tree.item(row, "values")[0] == "娑娜"
            )
            case.assertEqual(target_tree.item(row, "values")[2], "二星后移除")
            target_tree.selection_set(row)
            button(root, "删除目标").invoke()
            case.assertEqual(names(), ["盖伦"])
            state["scene"] = 1
            until(lambda: len(clicks) == 3)
            case.assertEqual(clicks[-1], (2, 0))

            hooks[0].callback()
            until(lambda: names() == [])
            count = len(clicks)
            # Re-adding starts again, even with identical shop names.
            hooks[0].on_select(1)
            until(lambda: len(clicks) > count)
            case.assertEqual(clicks[-1], (1, 0))
            button(root, "清空目标并停止（F8）").invoke()
            case.assertEqual(names(), [])
            count = len(clicks)
            season = next(
                w for w in walk(root) if w.winfo_class() == "TCombobox" and "S16" in w["values"]
            )
            season.set("S15")
            season.event_generate("<<ComboboxSelected>>")
            root.update()
            config = next(
                w
                for w in walk(root)
                if w.winfo_class() == "TCombobox" and "另一赛季" in w["values"]
            )
            case.assertEqual(config.get(), "另一赛季")
            season.set("S16")
            season.event_generate("<<ComboboxSelected>>")
            root.update()
            case.assertEqual(config.get(), "示例")
            button(root, "导入配置").invoke()
            until(lambda: len(clicks) > count)
            case.assertEqual(names(), ["盖伦"])
            case.assertEqual(
                target_tree.item(target_tree.get_children()[0], "values")[2], "二星后移除"
            )
            case.assertEqual(clicks[-1], (2, 0))
            # Hint arrives after names have stabilized: one last click, then delete.
            before = len(clicks)
            state["upgrade"] = 2
            until(lambda: names() == [])
            case.assertEqual(len(clicks), before + 1)
            case.assertEqual(clicks[-1], (2, 0))
            # Detail + defaults to continuous, even when the shop shows a 3-star hint.
            before = len(clicks)
            hooks[0].on_detail("add")
            until(lambda: names() == ["盖伦"] and len(clicks) > before)
            row = target_tree.get_children()[0]
            case.assertEqual(target_tree.item(row, "values")[2], "持续购买")
            hooks[0].on_detail("remove")
            until(lambda: names() == [])
            button(root, "清空目标并停止（F8）").invoke()
            case.assertFalse(errors, errors)
            root.tk.call(root.protocol("WM_DELETE_WINDOW"))

        with tempfile.TemporaryDirectory() as directory:
            library_root = Path(directory) / "configurations"
            for sid, title in [("s16", "示例"), ("s15", "另一赛季")]:
                profile = make_profile(title, sid, ["盖伦"], stop_rules={"盖伦": 2})
                save_profile(profile_path(profile, library_root), profile)

            def buyer_factory(*args, **kwargs):
                buyer = RealBuyer(*args, **kwargs, log_dir=Path(directory))
                buyers.append(buyer)
                return buyer

            with (
                patch("jcc_assistant.ui.EmergencyHotkey", Keys),
                patch("jcc_assistant.ui.MuMu", Device),
                patch("jcc_assistant.ui.UpgradeDetector", Hints),
                patch("jcc_assistant.ui.Recognizer", OCR),
                patch("jcc_assistant.ui.Buyer", buyer_factory),
                patch("jcc_assistant.ui.read_detail_selection", return_value="盖伦"),
                patch("jcc_assistant.ui.PROFILES", library_root),
                patch.object(tk.Tk, "mainloop", smoke),
            ):
                run()
            for buyer in buyers:
                buyer.flush_logs()

import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from test_support import fixture_catalog

from jcc_assistant.lineup.storage import load_profile
from jcc_assistant.lineup.ui import run


class LineupUiTests(unittest.TestCase):
    def test_import_recognize_review_and_save_profile(self):
        source = Path("tests/fixtures/lineup.png").resolve()
        if not source.exists():
            self.skipTest("示例截图缺失")
        errors = []
        case = self

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)

        def button(root, text):
            return next(
                w for w in walk(root) if w.winfo_class() == "TButton" and w.cget("text") == text
            )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "S16" / "s16_识别阵容.json"

            def smoke(root):
                root.withdraw()
                root.report_callback_exception = lambda *args: errors.append(args)
                labels = [w.cget("text") for w in walk(root) if w.winfo_class() == "TButton"]
                case.assertIn("资源管理…", labels)
                case.assertNotIn("新增赛季／模式", labels)
                case.assertNotIn("录入选中头像", labels)
                combo = next(w for w in walk(root) if w.winfo_class() == "TCombobox")
                case.assertEqual(combo.get(), "S16-海克斯典籍")
                case.assertEqual(sum(str(v).startswith("S16-") for v in combo["values"]), 1)
                button(root, "资源管理…").invoke()
                popup = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
                case.assertEqual(popup.title(), "头像资源管理")
                case.assertTrue(button(popup, "更新 S16 官方头像").winfo_exists())
                case.assertTrue(button(popup, "框选并补录一个头像").winfo_exists())
                popup.destroy()
                button(root, "导入截图").invoke()
                button(root, "识别配置").invoke()
                tree = next(w for w in walk(root) if w.winfo_class() == "Treeview")
                deadline = time.perf_counter() + 5
                while time.perf_counter() < deadline and len(tree.get_children()) != 8:
                    root.update()
                    time.sleep(0.01)
                case.assertEqual(len(tree.get_children()), 8, errors)
                rule_box = next(
                    w
                    for w in walk(root)
                    if w.winfo_class() == "TCombobox" and "二星后移除" in w["values"]
                )
                tree.selection_set("0")
                root.update()
                rule_box.set("二星后移除")
                rule_box.event_generate("<<ComboboxSelected>>")
                root.update()
                tree.selection_set("1")
                root.update()
                rule_box.set("持续购买")
                rule_box.event_generate("<<ComboboxSelected>>")
                root.update()
                button(root, "保存阵容 JSON").invoke()
                case.assertTrue(output.exists(), errors)
                case.assertEqual(
                    load_profile(output)["targets"],
                    [
                        "艾尼维亚",
                        "泰达米尔",
                        "艾希",
                        "瑟庄妮",
                        "丽桑卓",
                        "布隆",
                        "沃利贝尔",
                        "奥恩",
                    ],
                )
                case.assertEqual(
                    load_profile(output)["stop_rules"],
                    dict(
                        艾尼维亚=2,
                        泰达米尔=0,
                        艾希=0,
                        瑟庄妮=0,
                        丽桑卓=0,
                        布隆=0,
                        沃利贝尔=0,
                        奥恩=0,
                    ),
                )
                with patch(
                    "jcc_assistant.lineup.ui.filedialog.askopenfilename", return_value=str(output)
                ):
                    button(root, "打开阵容 JSON").invoke()
                root.update()
                case.assertEqual(tree.item("0", "values")[1], "二星后移除")
                case.assertEqual(tree.item("1", "values")[1], "持续购买")
                case.assertFalse(errors, errors)
                root.tk.call(root.protocol("WM_DELETE_WINDOW"))

            with (
                patch("jcc_assistant.lineup.ui.PortraitCatalog", side_effect=fixture_catalog),
                patch("jcc_assistant.lineup.ui.PROFILES", Path(directory)),
                patch(
                    "jcc_assistant.lineup.ui.filedialog.askopenfilename", return_value=str(source)
                ),
                patch(
                    "jcc_assistant.lineup.ui.filedialog.asksaveasfilename",
                    side_effect=AssertionError("Automatic save must not open a file dialog"),
                ),
                patch(
                    "jcc_assistant.lineup.ui.messagebox.showerror",
                    side_effect=lambda *args, **kwargs: errors.append(args),
                ),
                patch.object(tk.Tk, "mainloop", smoke),
            ):
                run()

import tkinter as tk
import unittest

from jcc_assistant.windows import center_new_windows


class CenteringTests(unittest.TestCase):
    def test_main_and_dialog_center_once_and_allow_manual_movement(self):
        root = tk.Tk()
        try:
            center_new_windows(root)
            root.geometry("320x180")
            root.update()
            self.assertAlmostEqual(root.winfo_x(), (root.winfo_screenwidth() - 320) // 2, delta=12)
            dialog = tk.Toplevel(root)
            tk.Label(dialog, text="A dialog with a measured width", padx=30, pady=20).pack()
            root.update()
            self.assertAlmostEqual(
                dialog.winfo_x(), (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2, delta=12
            )
            dialog.geometry("+20+20")
            root.update()
            self.assertAlmostEqual(dialog.winfo_x(), 20, delta=12)
        finally:
            root.destroy()

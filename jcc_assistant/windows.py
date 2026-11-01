"""Consistent screen centering for main windows and application dialogs."""

import tkinter as tk


def center_window(window):
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    if width <= 1:
        width = window.winfo_reqwidth()
    if height <= 1:
        height = window.winfo_reqheight()
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f"+{x}+{y}")


def center_new_windows(root):
    """Center each Tk/Toplevel on its first map, after content has its size."""
    centered = set()

    def on_map(event):
        window = event.widget
        if isinstance(window, (tk.Tk, tk.Toplevel)) and window not in centered:
            centered.add(window)
            center_window(window)

    root.bind_all("<Map>", on_map, add="+")

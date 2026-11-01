import ctypes as C
import threading
from ctypes import wintypes as W


class EmergencyHotkey:
    """F8 stops; NumLock-on numpad 1..5 select shop slots."""

    def __init__(self, callback, on_select=None, on_detail=None):
        self.callback = callback
        self.on_select = on_select
        self.on_detail = on_detail
        self.detail_ok = {}
        self.selection_ok = {}
        self.registered = []
        self.ready = threading.Event()
        self.ok = False
        self.thread_id = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(2)

    def _run(self):
        user = C.WinDLL("user32", use_last_error=True)
        kernel = C.WinDLL("kernel32", use_last_error=True)
        user.RegisterHotKey.argtypes = [W.HWND, C.c_int, W.UINT, W.UINT]
        user.RegisterHotKey.restype = W.BOOL
        user.GetMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
        user.GetMessageW.restype = W.BOOL
        self.thread_id = kernel.GetCurrentThreadId()
        self.ok = bool(user.RegisterHotKey(None, 1, 0x4000, 0x77))
        if self.ok:
            self.registered.append(1)
        if self.on_select:
            for slot in range(1, 6):
                success = bool(user.RegisterHotKey(None, 100 + slot, 0x4000, 0x60 + slot))
                self.selection_ok[slot] = success
                if success:
                    self.registered.append(100 + slot)
        if self.on_detail:
            for key_id, action, virtual_key in [(201, "add", 0x6B), (202, "remove", 0x6D)]:
                success = bool(user.RegisterHotKey(None, key_id, 0x4000, virtual_key))
                self.detail_ok[action] = success
                if success:
                    self.registered.append(key_id)
        self.ready.set()
        if not self.registered:
            return
        try:
            msg = W.MSG()
            while user.GetMessageW(C.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    self.dispatch(int(msg.wParam))
        finally:
            for hotkey_id in self.registered:
                user.UnregisterHotKey(None, hotkey_id)

    def dispatch(self, hotkey_id):
        if hotkey_id == 1 and self.ok:
            self.callback()
        elif self.on_select and 101 <= hotkey_id <= 105 and self.selection_ok.get(hotkey_id - 100):
            self.on_select(hotkey_id - 100)
        elif hotkey_id in (201, 202) and getattr(self, "on_detail", None):
            action = "add" if hotkey_id == 201 else "remove"
            if self.detail_ok.get(action):
                self.on_detail(action)

    def close(self):
        if self.registered:
            C.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
            self.thread.join(timeout=1)

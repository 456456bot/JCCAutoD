import ctypes as C
import os
import time
from pathlib import Path

from PIL import Image


class MuMu:
    """Capture and touch in Android display coordinates, independent of HWND."""

    def __init__(self, install=None, instance=None):
        install = install or os.environ.get("JCC_MUMU_PATH", r"D:\MuMuPlayer")
        instance = int(os.environ.get("JCC_MUMU_INSTANCE", "0")) if instance is None else instance
        root = Path(install)
        library = root / "nx_main/sdk/external_renderer_ipc.dll"
        if not library.is_file():
            raise RuntimeError(
                "未找到 MuMu SDK，请用 JCC_MUMU_PATH 设置模拟器安装目录：" + str(root)
            )
        self.lib = C.CDLL(str(library))
        signatures = {
            "nemu_connect": [C.c_wchar_p, C.c_int],
            "nemu_disconnect": [C.c_int],
            "nemu_get_display_id": [C.c_int, C.c_char_p, C.c_int],
            "nemu_capture_display": [
                C.c_int,
                C.c_int,
                C.c_int,
                C.POINTER(C.c_int),
                C.POINTER(C.c_int),
                C.c_void_p,
            ],
            "nemu_input_event_finger_touch_down": [C.c_int] * 5,
            "nemu_input_event_finger_touch_up": [C.c_int] * 3,
        }
        for name, args in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes = args
            fn.restype = C.c_int
        self.handle = self.lib.nemu_connect(str(root), instance)
        if not self.handle:
            raise RuntimeError("无法连接 MuMu 实例，请确认模拟器已启动")
        self.display = self.lib.nemu_get_display_id(self.handle, b"com.tencent.jkchess", 0)
        if self.display < 0:
            self.close()
            raise RuntimeError("没有找到金铲铲游戏画面")
        self.size = (0, 0)
        self.buffer = None

    def capture(self, region=None):
        start = time.perf_counter()
        w, h = C.c_int(), C.c_int()
        fn = self.lib.nemu_capture_display
        if fn(self.handle, self.display, 0, C.byref(w), C.byref(h), None):
            raise RuntimeError("MuMu 查询画面尺寸失败")
        size = (w.value, h.value)
        if not all(0 < n <= 8192 for n in size):
            raise RuntimeError(f"异常画面尺寸: {size}")
        if size != self.size:
            self.buffer = C.create_string_buffer(w.value * h.value * 4)
            self.size = size
        if fn(self.handle, self.display, len(self.buffer), C.byref(w), C.byref(h), self.buffer):
            raise RuntimeError("MuMu 截图失败")
        if (w.value, h.value) != self.size:
            raise RuntimeError("截图过程中分辨率变化，请重试")
        if region == "shop":
            # SDK returns a bottom-up full frame. Copy only rows of the name strip.
            left, top, right, bottom = (
                round(v * size[i % 2] / (2048, 1536)[i % 2])
                for i, v in enumerate((430, 1460, 1920, 1512))
            )
            stride = size[0] * 4
            address = C.addressof(self.buffer)
            pixels = b"".join(
                C.string_at(address + (size[1] - 1 - y) * stride + left * 4, (right - left) * 4)
                for y in range(top, bottom)
            )
            image = Image.frombytes("RGBA", (right - left, bottom - top), pixels).convert("RGB")
            image.info.update(android_size=size, origin=(left, top))
            # Read tiny star regions from the SAME SDK frame; no extra capture.
            from .upgrade import hint_boxes

            hints = []
            for x1, y1, x2, y2 in hint_boxes(size):
                raw = b"".join(
                    C.string_at(address + (size[1] - 1 - y) * stride + x1 * 4, (x2 - x1) * 4)
                    for y in range(y1, y2)
                )
                hints.append(Image.frombytes("RGBA", (x2 - x1, y2 - y1), raw).convert("RGB"))
            image.info["upgrade_regions"] = hints
        elif region == "detail":
            from .detail import detail_anchor_box, detail_name_box, panel_visible

            stride = size[0] * 4
            address = C.addressof(self.buffer)

            def extract(box):
                x1, y1, x2, y2 = box
                pixels = b"".join(
                    C.string_at(address + (size[1] - 1 - y) * stride + x1 * 4, (x2 - x1) * 4)
                    for y in range(y1, y2)
                )
                return Image.frombytes("RGBA", (x2 - x1, y2 - y1), pixels).convert("RGB")

            image = extract(detail_name_box(size))
            image.info.update(
                android_size=size,
                origin=detail_name_box(size)[:2],
                detail_panel_visible=panel_visible(extract(detail_anchor_box(size))),
            )
        elif region is None:
            image = (
                Image.frombytes("RGBA", size, self.buffer.raw)
                .transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                .convert("RGB")
            )
        else:
            raise ValueError("不支持的截图区域")
        return image, (time.perf_counter() - start) * 1000

    def capture_shop(self):
        return self.capture(region="shop")

    def capture_detail(self):
        return self.capture(region="detail")

    def tap(self, x, y):
        """Dispatch coordinates from the Android display space."""
        if not (0 <= x < self.size[0] and 0 <= y < self.size[1]):
            raise ValueError("触控坐标超出安卓画面")
        down = self.lib.nemu_input_event_finger_touch_down(
            self.handle, self.display, 1, int(x), int(y)
        )
        try:
            time.sleep(0.06)
        finally:
            up = self.lib.nemu_input_event_finger_touch_up(self.handle, self.display, 1)
        if down or up:
            raise RuntimeError(f"触控失败: {down}, {up}")

    def close(self):
        if getattr(self, "handle", 0):
            self.lib.nemu_disconnect(self.handle)
            self.handle = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

"""Windowless launchers that always use this project's installed environment."""

import ctypes
import importlib
import os
import subprocess
import sys
import traceback
from pathlib import Path


def launch(module):
    root = Path(__file__).resolve().parents[1]
    interpreter = root / ".venv" / "Scripts" / "pythonw.exe"
    try:
        if Path(sys.prefix).resolve() != (root / ".venv").resolve():
            if not interpreter.exists():
                raise FileNotFoundError(f"未找到运行环境：{interpreter}")
            subprocess.Popen(
                [str(interpreter), str(Path(sys.argv[0]).resolve()), *sys.argv[1:]],
                cwd=root,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return
        os.chdir(root)
        app = importlib.import_module(module)
        if "--check" not in sys.argv:
            app.run()
    except Exception:
        log = root / "artifacts" / "launcher_error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        ctypes.windll.user32.MessageBoxW(None, f"启动失败，详细信息：\n{log}", "金铲铲助手", 0x10)
        raise SystemExit(1)

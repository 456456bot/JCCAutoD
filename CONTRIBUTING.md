# Contributing

Use Windows and 64-bit Python 3.12+; the current local validation uses Python 3.14.
Clone the repository and run `setup.bat`, then install the development tools:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use committed, offline fixtures and simulated devices. They do not require
a running emulator, network downloads, hotkey registration, or real game clicks.
Tk tests create their own windows, so run them in a Windows desktop session.

Keep changes scoped. Include reproduction steps, game layout/resolution and the
season for recognition bugs. Redact account names and other unrelated information
before sharing screenshots. Do not commit credentials, runtime profiles, full
downloaded portrait caches, MuMu DLLs, OCR model binaries, or purchase logs.

Recognition behavior and thresholds are described in `docs/architecture.md`.
When changing calibration, preserve Android-coordinate behavior and test the
region extraction against full-frame fixtures. Preserve live-list checks and F8
invalidation when changing purchasing or shortcut handling.

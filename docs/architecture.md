# Architecture

## Runtime boundaries

JCCAutoD is a Windows source application. Two Tk applications share profile and
portrait storage but run independently. MuMu SDK provides external screenshot and
Android touch operations; no game API or memory access is used.

- `mumu.py`: configurable installation/instance, SDK lifetime, bottom-up RGBA
  extraction, Android-coordinate touch.
- `recognition.py`: fixed shop-name crops and local RapidOCR recognition.
- `targets.py`: authoritative names/rules, revisions, activation tokens and an
  RLock serializing list changes with click dispatch.
- `purchasing.py`: direct touch dispatch and asynchronous JSONL audit.
- `frame_cache.py`: adjacent five-name sequence deduplication.
- `upgrade.py`: tiny shop-star masks/templates from the same captured frame.
- `detail.py`, `selection.py`, `hotkey.py`: fresh read-only selection requests,
  expiration and F8 invalidation; no GUI operations on the hotkey thread.
- `lineup/`: static planner grids, portrait features, plan stars, catalog imports,
  atomic profiles, season-organized library discovery and editor.
- `windows.py`, `launcher.py`: initial screen centering and local `.venv` startup.

## Purchase loop

Wait while the target list is empty. Otherwise capture one SDK frame, extract the
name strip and star regions, OCR five names, and re-read current list membership.
Normal purchases are processed on a changed five-name sequence or a newly activated
target. Matching upgrade hints are processed independently of name deduplication.
Each click checks latest membership under the target lock. A successful touch call
for a matching two/three-star rule removes the name in that same critical section.
No result confirmation or exact quantity accounting is performed.

F8 clears targets and increments the selection epoch; old async read results cannot
repopulate the list. Already-dispatched touch cannot be revoked. Device/OCR/touch
errors clear targets. Tk widgets are updated only through the UI message queue.

## Thresholds

| Stage | Acceptance |
| --- | --- |
| Shop-name / hotkey OCR | Confidence >= 0.98 |
| Planner portrait | Highest normalized correlation > 0.60; no margin gate |
| Shop upgrade / planner stars | Color masks and scaled templates with correlation thresholds in source |

Portrait matching uses a central circular feature to suppress borders, locks and
stars. Unknown portraits remain unnamed. Plan stars generate 0/2/3 rules; missing
stars default to continuous. These static plan stars are separate from runtime
shop upgrade hints and do not identify units on the live board.

## Storage

`configurations/Sx/sx_<name>.json` stores versioned profiles and per-name stop rules.
The shared library discovers legacy flat files too and skips invalid JSON. Writes
use same-directory temporary files and atomic replacement; valid overwritten
profiles have one `.json.bak`. Runtime portrait caches, profiles and purchase logs
are ignored by Git. `tests/fixtures` is an independent, limited offline catalog.

## Supported calibration

The baseline is Android 2048x1536, 4:3, shop below the board, hero details on the
right. Scaling uses the Android image dimensions. Desktop moves/fullscreen do not
change these coordinates. Different aspect ratios or redesigned panels need new
calibration; source templates do not establish recognition accuracy for all modes.

## Deliberate scope

No battlefield inventory counting, model training, unit source tracking, automatic
shop refreshing, precise purchase-count enforcement, or automatic three-star
recognition from battlefield character models.

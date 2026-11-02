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
- `economy.py`, `search.py`: same-frame currency/price crops, explicit auto sessions,
  coin-floor decisions and one-refresh-at-a-time receipts.
- `ui_messages.py`: coalesced frame previews; stop/error/purchase events are never
  queued behind thousands of stale previews.
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
| Shop-name / hotkey OCR | Confidence >= 0.90 |
| Currency and prices | Confidence >= 0.98; refresh cost must be 0, 1 or 2 |
| Planner portrait | Highest normalized correlation > 0.60; no margin gate |
| Shop upgrade / planner stars | Color masks and scaled templates with correlation thresholds in source |

Portrait matching uses a central circular feature to suppress borders, locks and
stars. Unknown portraits remain unnamed. Plan stars generate 0/2/3 rules; missing
stars default to continuous. These static plan stars are separate from runtime
shop upgrade hints and do not identify units on the live board.

Shop hint regions extend above the card border to include animated stars. Resizing
preserves their aspect ratio; template matches also require foreground/background
overlap to reject solid gold decoration. Hints bind by slot ID, not list order.
These changes still need live validation for previously missed three-star effects.

## Storage

`configurations/Sx/sx_<name>.json` stores versioned profiles and per-name stop rules.
The shared library discovers legacy flat files too and skips invalid JSON. Writes
use same-directory temporary files and atomic replacement; valid overwritten
profiles have one `.json.bak`. Runtime portrait caches, profiles and purchase logs
are ignored by Git. `tests/fixtures` is an independent, limited offline catalog.
For upgrade-rule purchases, `artifacts/purchases/hint_00.png` through `hint_29.png`
form a bounded diagnostic ring containing same-frame star regions and shop names.
Purchase audit rows link `hint_frame` and include `name_confidence`; no board image
or portrait training collection is added.

## Supported calibration

The baseline is Android 2048x1536, 4:3, shop below the board, hero details on the
right. Scaling uses the Android image dimensions. Desktop moves/fullscreen do not
change these coordinates. Different aspect ratios or redesigned panels need new
calibration; source templates do not establish recognition accuracy for all modes.

## Deliberate scope

No battlefield inventory counting, model training, unit source tracking,
precise purchase-count enforcement, or automatic three-star
recognition from battlefield character models.

## Automatic search

The default remains manual-refresh assistance. Selecting Auto Search does not
activate purchases; an explicit Start is required. Mode changes, Stop and F8
invalidate an epoch checked immediately before purchases and refresh touches.
Control and live-target locks serialize dispatch so clearing the last target or
stopping cannot dispatch another action from a stale OCR result.

A session processes a shop, attempts affordable target purchases, reserves their
observed prices locally and re-reads gold/cost if necessary. Refresh is allowed
only when effective gold minus the observed 0/1/2 cost is >= the current floor.
This is a refresh floor, not a hard purchase spending limit. No purchase success
confirmation is added; reservations can conservatively stop earlier.

After a refresh, the session only reads until a usable new shop and sufficient
coin evidence appear. A paid identical-name shop requires coin deduction and two
reads. An unobservable free identical-name shop stops after the 3-second receipt
timeout. There is no fixed auto-loop delay or simulated player refresh cadence.
Low-confidence numbers or runtime errors stop auto mode while preserving targets.
Numeric OCR first retries tighter/enlarged/contrast-adjusted crops with the same
98% acceptance threshold. Transient failures then re-read frames for up to two
seconds; during this wait no further purchase/refresh clicks are dispatched.
After a purchase, numeric retries stay inside that step to avoid duplicate buying.
Persistently unreadable numeric crops and raw scores are saved to
`artifacts/diagnostics/economy/`; refresh cost is never inferred or reused blindly.
For the single refresh digit, two brightness masks isolate the largest white
component and render it black on white, excluding orange button glow and coin
fragments. OCR still requires 98%; conflicting numeric variants are rejected.
Automatic-search exceptions are recorded as `search_stopped` audit events.
Refresh touches are audited as `refresh_sent`, independently of purchase counts.

An uncertain nonempty name sequence is re-read once, or for at most 350ms if it
keeps changing. It then proceeds without buying low-confidence slots. An entirely
blank shop waits up to three seconds before stopping. One difficult non-target
name no longer stops the session or prevents a refresh receipt. Leading/trailing
middle dots from OCR noise are removed consistently in shop and detail selection;
internal name separators remain intact.
Low-confidence exact target names get a small batch of tighter crops before the
purchase decision; the name must remain identical and reach 90%. This addresses
short names such as 菲兹 without lowering the general purchase threshold.

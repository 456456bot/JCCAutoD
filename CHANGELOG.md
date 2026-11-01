# Changelog

## Unreleased — 0.2.0

- Add explicit Manual Assist / Auto Search modes, with start and stop controls.
- Read current gold and refresh-button cost (0/1/2) from SDK frame crops.
- Stop before a refresh would go below the configured gold floor; preserve targets.
- Process purchases and refreshes sequentially without a fixed auto-refresh delay.
- Wait for the refreshed shop and coin evidence; stop on uncertain numbers or a
  missing refresh response. Reserve attempted purchase costs without purchase confirmation.
- F8 and mode changes invalidate in-flight actions; add refresh audit records.

## 0.1.0 — 2026-11-01

- MuMu SDK capture/touch in Android coordinates, with local shop-name OCR.
- Dynamic targets, F8 stop, numpad shop selection and detail-panel `+` / `-` selection.
- Buy-and-remove rules based on shop two/three-star hints; no quantity tracking.
- Standalone lineup editor with JSON profiles, portrait matching, manual templates,
  season selection and plan-star-derived purchase goals.
- Public/official portrait download tools and S16 / S16.5 compatibility.
- Centered main windows/dialogs, portable source setup and desktop shortcuts.
- Automatic season folders/file names and season/title-based profile import.
- Planner portrait acceptance above 60%, separate from purchase OCR confidence.
- Offline regression fixtures and Windows CI; no private runtime caches in Git.

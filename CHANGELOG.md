# Changelog

## Unreleased — 0.2.0

- Reprocess uncertain numeric crops and retry transient economy OCR failures for
  two seconds before stopping. Preserve purchase state during post-click retries.
- Reprocess low-confidence exact target names with tighter crops; add an observed
  Fizz regression fixture that previously fell below the purchase threshold.
- Save failed numeric crops and raw OCR scores locally for diagnosis.
- Retry transient/uncertain shop names instead of aborting auto-search for a
  non-target OCR score; retain the confidence gate on purchases and currency.
- Strip spurious leading/trailing OCR middle dots, including the observed 菲兹·.
- Expand upgrade-hint capture vertically without distorting star shapes, filter
  gold-background matches and bind hints explicitly to shop slot IDs.
- Keep a local 30-image diagnostic ring of purchase-time star/name regions for
  upgrade-rule targets; audit the image path and name confidence.
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

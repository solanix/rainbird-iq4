# Development Changelog

This is a **reported milestone history**, not a Git commit history. Exact dates for some intermediate milestones were not recorded; all milestones predate or occurred on 2026-10-10.

## 2026-10-10 — Phase 2C implemented (offline)

- Repositories directly inspected; baseline 102 library / 58 integration tests and all lint/type gates confirmed.
- Found and corrected policy gaps in the uncommitted Phase 2A control boundary: stop always sent `0x40` even when idle; stop verified with a single read; start had no rain-sensor, rain-delay, terminal-availability or irrigation-enabled checks.
- Library: added `LocalIrrigationState.confirms_idle` and `RainBirdIQ4LocalClient.wait_for_idle()` (bounded, read-only, requires complete realtime data).
- Integration: start now performs fresh realtime **and** slow reads inside the shared operation lock and blocks on active or unknown rain state, unavailable terminal or irrigation not confirmed enabled. Stop is a verified-idle no-op, otherwise one write plus bounded idle verification. Connection failure before any write is reported as definitely not sent (`controller_unreachable`).
- Added admin-only actions `rainbird_iq4.start_station` and `rainbird_iq4.stop_irrigation` (registered once in `async_setup`, response data `acknowledged`/`verified`/`no_op`, translated errors), plus `services.yaml`, `icons.json` and strings.
- Added `tests_ha/`, a suite that runs against the real Home Assistant Core checkout (23 tests), alongside the existing stub suite.
- Library repo: untracked `.pyc` and `egg-info` files; added `.gitignore`.
- Results: library 105 passed; integration stub suite 78 passed; real-HA suite 23 passed; Ruff/format/mypy passed.
- Not done: live validation through HA; commits.

## 2026-10-10 — Phase 2B completed

- Live Station 001 start and stop verified on IQ4 firmware 3.11.0.
- Initial `ACKNOWLEDGED verified=False` start was traced to checking one realtime snapshot too soon. Added up to five one-second-spaced **read-only** verification snapshots. Live retest returned `ACKNOWLEDGED verified=True`.
- Idle stop correctly did not send a command (`NOT SENT verified=True`); later active stop sent `0x40` with running zone 1 and ~80 seconds remaining; returned `ACKNOWLEDGED verified=True`.
- Reported checks: library 102 passed, HA integration 58 passed, Ruff/format/mypy passed.

## 2026-10-09–10 — Recorder and entity-state incident investigation

- HA Recorder reported SQLite `database or disk is full`; host and overlay storage heavily used, but no conclusive root cause documented.
- Irrigation-state UI briefly unavailable; realtime and slow local poll logs passed; Recorder later showed 30-sec idle updates; code audit found one correctly registered entity and no reproducing code bug.
- Debug logging restricted to targeted categories then reduced for normal operation.

## Earlier — Phase 2A, local writes (offline)

- Added `start_station`, `stop_irrigation` library methods; HA internal guarded control boundary (not public actions).
- Input validation, error taxonomy, concurrency, no write retry, status verification, mocked tests.
- Tests grew from 82/58 to 99/58 and subsequently 102/58.

## Earlier — Read-only control support diagnostic

- Added explicit `--check-control-support` flag, sending only read-only `CommandSupportRequest`.
- Controller advertised `0x38`, `0x39`, `0x40` SUPPORTED.
- Initial tests: library 75 and HA 50 at one checkpoint.

## Earlier — Phase 1 telemetry and metadata

- Implemented local realtime/slow HA coordinators, connection-close HTTPS transport, cloud discovery/program/station catalog, program effective-vs-reference model, station names and enabled-state tri-state.
- Adjusted station registry defaults, documented lack of retroactive registry reconciliation.
- Regression added for enabled Station 001 with unscheduled Program C.
- Repeatedly passed offline library/HA integration checks.

## Pending decisions

- Recorder filesystem root-cause follow-up and long-running soak.
- User-facing metadata-sensor naming improvement.
- Manual Program A/B/C write numbering validation.
- Dashboard layouts and control UX (station picker instead of raw station ID).
- Migrating the stub-based integration tests to real HA.

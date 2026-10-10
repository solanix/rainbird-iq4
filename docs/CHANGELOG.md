# Development Changelog

This is a **reported milestone history**, not a Git commit history. Exact dates for some intermediate milestones were not recorded; all milestones predate or occurred on 2026-10-10.

## 2026-10-10 — Integration hardening (Phase 4 start)

- **Fixed:** IQ4 rejecting the stored cloud password raised `ConfigEntryAuthFailed`, but the config flow had no `reauth` step, so the re-authentication prompt could not complete. Added `reauth`/`reauth_confirm` (asks for the new password, checks the account still has the controller, updates the entry and reloads).
- Config flow now uses Home Assistant's shared HTTP session.
- Config, reauth and options flows are tested against real HA (`tests_ha/test_config_flow.py`, 18 tests, including the end-to-end reauth trigger and the duplicate-controller abort the stubs could not test). Six superseded stub flow tests removed.
- Added a diagnostics download (Settings → Devices & services → Rain Bird IQ4 → ⋮ → Download diagnostics): coordinator health and latest cloud/local data, with username, passwords, local host/PIN, MAC, location and site name redacted; stations show the derived `is_enabled` next to raw `is_locked`. Snapshot-tested.
- Added concurrency tests: a start issued mid-poll waits for the poll, and a stop sent while a start is writing runs after it; no deadlock.
- Fixed entity names now come from `strings.json` (`translation_key`); station and program entities keep their IQ4-derived names. A snapshot of every entity ID and name confirms nothing changed for existing setups or dashboards.
- Results: library 105; integration stub suite 73; real-HA suite 57.

## 2026-10-10 — Phase 2D started

- Added `select` "Start station" (cloud-enabled stations only, stored by station ID, restored) and `number` "Start duration" (1–30 min, default 5, restored) entities, created only with local control configured. Neither contacts the controller.
- Added `examples/script.yaml` and `examples/dashboard.yaml`. The script is loaded and run in the real-HA tests (starts the selected station; non-admin refused; no selection rejected visibly).
- A failed slow poll now retries after 30/60/120 s instead of waiting the full 5 minutes.
- Dashboard Start/Stop live-tested on desktop with Station 002.
- Remaining runtime now displays whole seconds (`118 s`, not `118.00 s`).
- Results: library 105; integration stub suite 79; real-HA suite 35.

## 2026-10-10 — Phase 2C accepted (live)

- Operator-supervised test through HA Developer Tools on controller 200001: idle stop returned `no_op` with nothing sent; Station 001 one-minute start and the following stop each sent exactly one write and verified; disabled Station 008 was refused. Details in [LIVE_VALIDATION_LOG.md](quality/LIVE_VALIDATION_LOG.md).
- Phase 2A–2C committed locally in both repositories.

## 2026-10-10 — Phase 2C implemented (offline)

- Repositories directly inspected; baseline 102 library / 58 integration tests and all lint/type gates confirmed.
- Found and corrected policy gaps in the uncommitted Phase 2A control boundary: stop always sent `0x40` even when idle; stop verified with a single read; start had no rain-sensor, rain-delay, terminal-availability or irrigation-enabled checks.
- Library: added `LocalIrrigationState.confirms_idle` and `RainBirdIQ4LocalClient.wait_for_idle()` (bounded, read-only, requires complete realtime data).
- Integration: start now performs fresh realtime **and** slow reads inside the shared operation lock and blocks on active or unknown rain state, unavailable terminal or irrigation not confirmed enabled. Stop is a verified-idle no-op, otherwise one write plus bounded idle verification. Connection failure before any write is reported as definitely not sent (`controller_unreachable`).
- Added admin-only actions `rainbird_iq4.start_station` and `rainbird_iq4.stop_irrigation` (registered once in `async_setup`, response data `acknowledged`/`verified`/`no_op`, translated errors), plus `services.yaml`, `icons.json` and strings.
- Added `tests_ha/`, a suite that runs against the real Home Assistant Core checkout (23 tests), alongside the existing stub suite.
- Library repo: untracked `.pyc` and `egg-info` files; added `.gitignore`.
- Results: library 105 passed; integration stub suite 78 passed; real-HA suite 23 passed; Ruff/format/mypy passed.

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

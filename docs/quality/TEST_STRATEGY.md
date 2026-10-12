# Test Strategy, Traceability and Evidence

## Principles

- Mock cloud and local controller I/O for **all automated tests**.
- Use fixtures for queued SIP JSON-RPC responses, errors, cloud catalogs and snapshots.
- No live network calls or watering from pytest, CI, import, HA setup, unload or reload.
- Every write test asserts **exactly one** upstream write attempt (or zero for rejections); verification polls are read-only.
- Keep HA Core untouched and test library/integration responsibilities separately.
- Test HA-facing behaviour (authorization, schemas, registries, lifecycle) against **real** Home Assistant, not stubs.

## Suites

| Suite | Location | Runs against | Command |
|---|---|---|---|
| Library | `pyrainbird-iq4/tests` | Library only | `cd /workspaces/pyrainbird-iq4 && python3 -m pytest` |
| Integration (stub) | `ha-rainbird-iq4/tests` | `tests/stubs/homeassistant` | `cd /workspaces/ha-rainbird-iq4 && python3 -m pytest` |
| Integration (real HA) | `ha-rainbird-iq4/tests_ha` | HA Core checkout + its fixtures | `cd /workspaces/home-assistant-core && python3 -m pytest -c pyproject.toml -p tests.conftest /workspaces/ha-rainbird-iq4/tests_ha` |
| Card | `ha-rainbird-iq4/dashboard/test` | Node's test runner with fixture `hass` objects | `cd ha-rainbird-iq4/dashboard && npm test && npm run typecheck` |

## Latest results (re-run 2026-10-12)

| Suite | pytest | Ruff | Format | mypy |
|---|---:|---|---|---|
| `pyrainbird-iq4` | 106 passed | Passed | Passed | Passed (strict) |
| `ha-rainbird-iq4` stub | 83 passed | Passed | Passed | Passed |
| `ha-rainbird-iq4` real HA | 85 passed | Passed | Passed | — |
| Card | 76 passed | — | — | `tsc` clean |

The stub suite's `addopts` hide the summary line; use `-o addopts=` to see the count, or rely on the exit code.

## Regression coverage

**Library:** input validation (including Python bool-as-int hazard), 1/30-minute bounds, protocol delegation, upstream error types, auth/network/timeouts/NACK/busy, one-write-only, stop acknowledgement, transport serialization, connection-close behavior, no writes from construction or polling, delayed active-terminal updates, queue-only confirmation, wrong-terminal evidence rejection, bounded start verification failure, **bounded idle verification, incomplete-idle rejection, zero-attempt guard**.

**Integration control boundary (stub suite):** station-ID resolution, cross-controller ID, enabled/unknown guard, duration (0, 31, bool, float), stale/incomplete/busy telemetry, fresh-read busy, rain sensor/delay active and unknown, terminal unavailable/unknown, irrigation disabled, preflight read failure, ambiguous start and stop, unconfirmed start and stop, idle stop no-op, unknown-state stop still sent, connect failure not ambiguous; plus existing entity, metadata and polling coverage.

## Phase 2D coverage

`tests_ha/test_controls.py`: picker offers only enabled stations and selecting sends nothing; duplicate names disambiguated; restore by station ID (kept if enabled, cleared if now disabled); duration default, set and restore; no controls without local; selection drives `start_station`; `examples/script.yaml` starts the selected station, keeps the admin check, and rejects a missing selection visibly. The `examples/` dashboard YAML is not machine-validated; it needs UI review. The Lovelace card has its own suite (T01–T18 from the dashboard spec) plus `tests_ha/test_card.py` (served and registered) and a stale-bundle check; manual checks are in `dashboard/VALIDATION.md`.

## Phase 2C traceability

| Scenario | Expected outcome | Covered by |
|---|---|---|
| Admin requests start on enabled station of same controller | One write; verified or meaningful unconfirmed status | `tests_ha::test_start_station_verified`, `::test_start_station_unconfirmed_is_reported_not_retried` |
| Non-admin invokes start/stop | Authorization failure; zero writes | `tests_ha::test_non_admin_is_rejected[start|stop]` |
| Wrong/unknown device or cross-controller station ID | Reject; zero writes | `tests_ha::test_unknown_device_is_rejected`, `::test_foreign_device_is_rejected`, `::test_start_station_rejects_ineligible_station[cross-controller]` |
| Disabled or unknown-state station | Reject; zero writes | `tests_ha::test_start_station_rejects_ineligible_station[disabled|enabled-unknown]` |
| Invalid duration, bool, noninteger, out of range | Reject; zero writes | `tests_ha::test_start_station_schema_rejects_duration[*]`; `tests::test_safe_start_rejects_invalid_preconditions` |
| Running/paused/stale/incomplete realtime state on start | Reject; zero writes | `tests::test_safe_start_rejects_invalid_preconditions`, `::test_safe_start_rejects_fresh_controller_state[started-meanwhile]` |
| Rain sensor or rain delay active (or unknown) | Reject start | `tests_ha::test_start_station_blocked_by_rain_sensor`; `tests::test_safe_start_rejects_fresh_controller_state[rain*|delay*]` |
| Cloud unavailable during start | Reject start | `tests_ha::test_start_station_requires_current_cloud_data` |
| Cloud unavailable during stop | Stop remains available | `tests_ha::test_stop_running_without_cloud`; at startup: `tests_ha::test_cloud_outage_at_startup_keeps_local_stop` |
| Local state stale/unknown during stop | Stop sent once | `tests::test_stop_sends_when_state_is_unknown` |
| Verified idle stop | Safe no-op; no wire command | `tests_ha::test_stop_idle_is_no_op`; `tests::test_stop_verified_idle_is_safe_no_op` |
| Timeout after unknown delivery | Do not retry; explicit ambiguous result | `tests_ha::test_start_station_ambiguous_write`; `tests::test_safe_start_timeout_is_ambiguous_and_not_retried`, `::test_stop_timeout_is_ambiguous_and_not_retried` |
| Ack with no timely state transition | Unconfirmed; do not repeat | `tests::test_safe_start_unconfirmed_is_not_repeated`, `::test_stop_unconfirmed_is_not_repeated` |
| Concurrent HA actions and coordinator polls | Serialized without deadlocks | `tests_ha::test_start_waits_for_in_flight_poll`, `::test_concurrent_start_and_stop_are_serialized`; `tests::test_overlapping_local_coordinator_refreshes_are_serialized` |
| Multiple config entries | Targets only selected controller | `tests_ha::test_stop_targets_only_selected_controller`, `::test_start_station_rejects_ineligible_station` (two entries) |
| Reload, final unload | No duplicates; unloaded entry rejected | `tests_ha::test_setup_and_reload_never_write`, `::test_actions_after_unload_are_rejected` |
| HA startup/reload | No irrigation write ever | `tests_ha::test_setup_and_reload_never_write` |
| Cloud-only entry | Reject | `tests_ha::test_local_not_configured_is_rejected` |
| Automatic tests | Network calls mocked; no real controller access | `tests_ha` autouse `mock_io` patches cloud fetch and local `connect` |

## Live validation log template

```text
Date/time + timezone:
Controller/firmware:
Operator + safe zone:
HA running or stopped:
Operation (SIP / HA action):
Requested station ID / terminal / duration:
Precondition read-only snapshot:
Protocol acknowledgement / action response:
Post-write snapshot(s):
Verification status:
Physical observation:
Any unexpected effects:
Follow-up / rollback:
```

## Release requirements

Test against the exact installed Home Assistant version; run lint/format/types; review Git diff; verify no exposed secrets or site-specific values; soak local polling and Recorder; confirm action registration/admin controls under multiple config entries; verify no automatic writes; document data migration/entity registry consequences.

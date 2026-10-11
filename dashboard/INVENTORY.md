# Phase D0 — Data and action inventory

Audited 2026-10-09 against `ha-rainbird-iq4` at `2d4c23c` and the dev HA registry (one
controller, 38 entities; every unique ID classified by `parseUniqueId`). Exact entity IDs
are not used anywhere: they depend on the device name. The card finds entities by
`platform == "rainbird_iq4"` and unique ID `{controller_id}_{key}` via
`config/entity_registry/list` (not admin-restricted).

## Field mapping

| Dashboard field | Source (unique-ID key → state / attribute) | When missing |
|---|---|---|
| Controller identity | registry `device_id` of any IQ4 entity; name from device registry (`name_by_user` ‖ `name`) | Controller not listed |
| Cloud status | `connected` → `on`/`off`; attr `stale` | `unknown` |
| Local status / age | `irrigation_state` attrs `last_successful_update`, `poll_interval_seconds`, `consecutive_failures` | `offline` (unavailable), `stale` (> 60 s, matches backend `telemetry_stale`), `not_configured` (entity absent) |
| Irrigation state | `irrigation_state` → `idle`/`running`/`paused`/`unknown` | Shown as unknown unless local is fresh |
| Active station | `active_station` attrs `station_id`, `terminal`, `station_name` | Hidden unless running and fresh |
| Active program | `active_program` state (`Manual`, catalog name, `Unknown`) | Hidden |
| Remaining runtime | `remaining_runtime` (s) — controller queue value, **not** an estimate | Hidden |
| Zones queued | `queue_zones_remaining` | Hidden |
| Rain sensor | `rain_sensor_active` `on`/`off` | Unknown → start blocked |
| Rain delay | `rain_delay` (days; local when local configured, else cloud) | Unknown → start blocked |
| Irrigation enabled (AUTO) | `irrigation_enabled` `on`/`off` | Unknown → start blocked |
| Physically present terminals | `irrigation_enabled` attr `available_terminals` (**added for the dashboard**, see below) | `null` → **no station startable** |
| Stations | `station_{id}` attrs `station_id`, `station_name`, `station_enabled` (tri-state), `terminal`, `program_references` (falls back to `assigned_effective_programs`) | Registry-disabled entity → listed with enabled *unknown* |
| Programs | `program_{id}` attrs `program_name`, `effective`, `scheduled`, `scheduled_start_times`, `station_runtimes` | Listed as no longer reported |
| Firmware | `firmware_version` | — |
| History | Recorder `history/history_during_period` of `active_station` | "History unavailable" with the reason |
| Command outcome | action response `{acknowledged, verified, no_op, station_id, terminal}` or translated error key | — |

Not available from the integration (shown as absent, never invented): cloud last-update
timestamp, remaining-time estimates, program start/pause/resume, a run-event ledger.

## Actions (implemented in Phase 2C, commit `bf6f3d1`)

| Action | Fields | Response | Errors |
|---|---|---|---|
| `rainbird_iq4.start_station` | `device_id`, `station_id` (cloud ID, int ≥ 1), `duration_minutes` (int 1–30) | optional; see above | `ServiceValidationError`/`HomeAssistantError` with `translation_key` (`station_not_enabled`, `telemetry_stale`, `rain_sensor_active`, `write_outcome_ambiguous`, …); `unauthorized` for non-admins |
| `rainbird_iq4.stop_irrigation` | `device_id` | `no_op: true` when confirmed idle | as above |

Both are registered with `async_register_admin_service`; the card calls them through
`call_service` with `return_response: true` and never retries.

## Discrepancies with the handoff docs

- Docs say Phase 2C actions are not implemented; they are, with live validation recorded.
- Docs list `Paused or delayed (only if verified)`; the library reports `paused` from protocol
  evidence, so the card shows it, and offers Stop.
- Station-enabled state for a station disabled in IQ4 is only visible if the user enables its
  metadata entity (the integration disables it by default), so the card shows *unknown*.
- Physical terminal presence was not exposed; added as an attribute (below).

## Integration change requested by the dashboard

`binary_sensor.*_irrigation_enabled` gains attribute `available_terminals: list[int] | None`
from the slow local poll. Implemented in `custom_components/rainbird_iq4/binary_sensor.py`
with test `test_irrigation_enabled_exposes_physically_available_terminals`. Status on
2026-10-09: the test was committed in `2d4c23c`, the implementation is still uncommitted —
owned by the integration session.

## Observations for the integration owner

- Every local entity carries `last_successful_update`, which changes on every poll (10–30 s),
  so the Recorder writes a new state row each poll. Measured in the dev DB over the last 24 h:
  1,740 rows each for the five realtime sensors, 195 each for the three slow ones. Relevant
  to the earlier Recorder/disk incident; the integration sets no `_unrecorded_attributes`.
  Excluding the poll-bookkeeping attributes would not affect this card's History view, which
  uses state changes only.
- Disk: `/tmp` 95 % used (17 MB free), `/home` 92 % on the dev host (2026-10-09).

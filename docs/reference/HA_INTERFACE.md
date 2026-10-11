# Home Assistant Surface

## Exposed entities (representative)

Reported Backyard entities include:

- `sensor.backyard_irrigation_state` — realtime state; enum `idle` / `running` / `paused` (shown translated), or HA `unknown` when the controller evidence is inconclusive.
- Diagnostic category (hidden from default dashboards, listed under *Diagnostic* on the device page): firmware version, station count, programs used, program summary, controller connected, station metadata, per-station program runtimes. `binary_sensor.backyard_controller_connected` shows Connected/Disconnected; `binary_sensor.backyard_rain_sensor_active` shows Wet/Dry.
- `binary_sensor.backyard_controller_connected` — cloud-reported connection presence; can be `on` while local telemetry fails.
- `sensor.backyard_active_station` — realtime currently active station, named using cloud metadata when available.
- Realtime data: active program, active station, queue remaining zones, remaining runtime.
- Slow data: irrigation enabled, rain sensor, rain delay, available terminal count/list.
- Station metadata sensor, e.g. `sensor.backyard_station_001` — numeric state is **effective program count**, not enablement; attributes include `station_enabled`, IDs, terminal, references. The cloud **station ID** needed by `start_station` is shown here.
- Program entities (`sensor.backyard_program_a`, `_b`, `_c`, …): one per program that is scheduled or assigned to a station. State is the first start time, or `Not scheduled`; attribute `effective` is true only for scheduled programs. Unavailable only when the program no longer exists in schedules or assignments.
- Effective program count.
- Manual-start controls (only when local control is configured):
  - `select.backyard_start_station` — options are **only** cloud-enabled stations, by IQ4 name (duplicate names get a ` (terminal N)` suffix). Attribute `station_id` holds the stable cloud ID of the choice. The choice is stored by station ID, restored across restarts, and cleared if that station stops being enabled.
  - `number.backyard_start_duration` — 1–30 minutes, slider, default 5, restored across restarts; stays available during cloud outages.
  - Changing either never contacts the controller.

Entity IDs are pinned by `tests_ha/__snapshots__/test_sensor.ambr`; a change there is a breaking change for dashboards. Actual exact entity IDs may vary with naming and registry customizations. Confirm with HA Developer Tools → States.

## Control actions (implemented; live-validated 2026-10-10)

Both actions are registered once in `async_setup` with `async_register_admin_service`, so **only admin users** can call them. Both support optional response data (`return_response: true` in scripts, or "return response" in Developer Tools). Local control must be configured in the integration options (controller address and controller-local PIN).

```yaml
action: rainbird_iq4.start_station
data:
  device_id: YOUR_HA_DEVICE_ID
  station_id: 30000001
  duration_minutes: 5
response_variable: result
```

```yaml
action: rainbird_iq4.stop_irrigation
data:
  device_id: YOUR_HA_DEVICE_ID
response_variable: result
```

### Action contract

| Action | Inputs | Authorization | Precondition | Postcondition |
|---|---|---|---|---|
| `rainbird_iq4.start_station` | HA device ID (device selector filtered to this integration), cloud station ID (whole number ≥ 1), duration (whole minutes 1–30; bools and fractions rejected) | Admin only | Device resolves to one loaded IQ4 entry with local control; last cloud refresh succeeded; station belongs to that controller and `is_enabled is True`; coordinator realtime data ≤ 60 s old, complete and idle; **fresh in-lock** realtime read complete and idle; **fresh in-lock** slow read shows irrigation enabled, terminal available, rain sensor `False`, rain delay `0` | One write; up to 5 read-only checks for the terminal running |
| `rainbird_iq4.stop_irrigation` | HA device ID | Admin only | Device resolves to one loaded IQ4 entry with local control. No cloud or coordinator-freshness requirement | Fresh read confirms idle ⇒ nothing sent. Otherwise one write; up to 5 read-only checks for idle |

### Response data

```yaml
acknowledged: true    # controller acknowledged a write; false for a no-op stop
verified: true        # read-only state confirmed the requested transition
no_op: false          # true when stop found the controller confirmed idle and sent nothing
station_id: 30000001  # start only; null for stop
terminal: 1           # start only; null for stop
```

`acknowledged: true, verified: false` means the command was accepted but the expected state was not observed within ~5 seconds. A warning is logged. **Do not repeat the action automatically**; check the controller first.

### Errors

All errors are translated (`strings.json` → `exceptions`). Input problems raise `ServiceValidationError`; controller, cloud or outcome problems raise `HomeAssistantError`. Schema violations (e.g. `duration_minutes: 31`) are rejected by HA before the action runs.

| Key | Type | Meaning | Write sent? |
|---|---|---|---|
| `invalid_device` | Validation | Device does not exist or is not an IQ4 controller device | No |
| `entry_not_loaded` | Validation | The controller's config entry is not loaded | No |
| `local_not_configured` | Validation | No local host/PIN in options | No |
| `invalid_duration` | Validation | Duration outside 1–30 whole minutes | No |
| `station_not_found` | Validation | Station ID not in this controller's catalog (includes other controllers' stations) | No |
| `station_not_enabled` | Validation | Station disabled or enablement unknown | No |
| `cloud_data_unavailable` | Error | Last cloud refresh failed; enablement cannot be confirmed | No |
| `telemetry_unavailable` / `telemetry_stale` / `telemetry_incomplete` | Error | Coordinator realtime data missing, > 60 s old, or missing authoritative fields | No |
| `telemetry_refresh_failed` | Error | Fresh preflight read failed | No |
| `controller_not_idle` | Error | Controller running, paused or not confirmed idle | No |
| `irrigation_disabled` | Error | Global irrigation flag not confirmed `True` | No |
| `terminal_unavailable` | Error | Terminal not in fresh `available_terminals` (or that list is unknown) | No |
| `rain_state_unknown` / `rain_sensor_active` / `rain_delay_active` | Error | Rain safety data unknown or active | No |
| `controller_unreachable` | Error | Could not connect before writing | No |
| `write_outcome_ambiguous` | Error | Write transport failed; controller **may** have acted | **Maybe** — not retried |

### Design notes

- Station identity is the stable cloud station ID, resolved to a terminal at the server boundary; users never supply a terminal number.
- The device must be owned by the resolved entry **and** carry the identifier `(rainbird_iq4, <controller_id>)`, preventing cross-controller targeting.
- Prefer explicit variable-duration action over switch-per-station; switch semantics do not cleanly reflect timed external runs.
- `station_id` is a number box in the raw action; dashboards use the `select` entity and the example script in `examples/script.yaml`, which passes the selection to `start_station`. Because a script runs with the caller's context, the admin check still applies to the person pressing Start. Automations have no user and are allowed (standard HA behaviour).
- Optional controller-level Stop button may follow live validation.
- Dashboard goal: status, current terminal/program, remaining runtime, enabled station selection, chosen duration, Start/Stop, scheduled program overview; responsive desktop/mobile.

## Stations and programs added or removed in IQ4

New stations, programs and station assignments appear on the next cloud refresh (about 5 minutes) without a reload. Removed ones show *unavailable* until the next HA restart or integration reload, when they are deleted from the entity registry (only with live cloud data; see ADR-015). Dashboards referencing a removed station's entities will show them as missing after that.

## Registry caveat

HA `_attr_entity_registry_enabled_default` is honored when an entity is first created, not automatically on later changes to cloud enablement. Newly discovered disabled stations may have `disabled_by=integration`; existing ones may remain enabled, and re-enabled cloud stations may require manual registry enablement. Never edit `.storage` by hand.

# Data Model, Identity and Semantics

## Site and controller

Observed development data:

| Object | Value |
|---|---|
| Site `Home` | `200101` |
| Site `Backyard` | `200102` |
| Controller `Backyard` | `200001` |
| Controller firmware | `3.11.0` |
| Controller hardware | `57` |
| Local address (development only) | `192.0.2.10` |
| Physical terminals | 1–10 |

## Stations and identities

| Terminal | Cloud station ID | Current reported enablement |
|---:|---:|---|
| 1 | 30000001 | Enabled |
| 2 | 30000002 | Enabled |
| 3 | 30000003 | Enabled |
| 4 | 30000004 | Enabled |
| 5 | 30000005 | Enabled |
| 6 | 30000006 | Enabled |
| 7 | 30000007 | Enabled |
| 8 | 30000008 | Disabled |
| 9 | 30000009 | Disabled |
| 10 | 30000010 | Disabled |

**Important:** `available_terminals=[1..10]` represents controller hardware capacity, **not** permission to water. It cannot be used as an enabled-station filter.

### Cloud station enablement normalization

Verified observed semantics of raw IQ4 `isLocked` property (counterintuitive):

| Raw `isLocked` | Typed `is_locked` | Derived `is_enabled` |
|---|---|---|
| `true` | `True` | `True` |
| `false` | `False` | `False` |
| missing/null/nonboolean | `None` | `None` (unknown) |

Do not negate `isLocked` on intuition. Starts require **explicitly `is_enabled is True`**, not merely “not False”.

### HA entity identity and names

- Stable station entity identity uses **controller ID + station ID** (e.g. `200001_station_30000001`).
- Irrigation-state sensor unique ID: `200001_irrigation_state`.
- HA device identifier: `("rainbird_iq4", "200001")`. Control actions use this to confirm a device belongs to the resolved config entry.
- IQ4 cloud `name` is the default station display name; fallback if blank: `Station {terminal:03d}`. HA user-customized names should remain respected.
- Cloud names can duplicate; never use names as identity keys.
- Entity registry `disabled_by=integration` defaults are only applied on initial entity creation; existing enabled registry entities are not retroactively disabled. Later cloud re-enablement clears `disabled_by=integration` (not `user`) on the next live cloud refresh.

## Programs

Observed IDs include Program A `4000001`, B `4000002`, C `4000003` (C inferred from captured station reference). Programs can exist with runtime references but **without effective scheduled start times**.

- `program_references`: historical/configured runtime reference; retained even when program is not scheduled/effective.
- `assigned_effective_programs`: only assignments that qualify as scheduled/effective and usable per station enablement.
- `assigned_effective_program_count`: numeric station metadata sensor state; **not** station enabled/disabled state.

Example: Station 001 has `station_enabled: true`, an unscheduled Program C reference with adjusted/base runtime `00:10:00`, and `assigned_effective_program_count=0`. That is correct, not a contradiction. Program C is a real configured program, not a fictitious or stale program.

Disabled Stations 008 and 009 may have retained A runtime data but are excluded from operational/effective assignments. Do not erase such references merely because a station is disabled.

### Runtime examples (mutable controller configuration)

At one observed point, Program A scheduled start was 05:00 and B had no effective scheduled start in the UI; a different diagnostic earlier showed B 07:15. Treat schedules as mutable cloud data, not constants. Station runtimes included A ~31 minutes for stations 2–3; A ~23:15 for stations 4–6; B ~16:30 for stations 5–6. These are historic observations only.

## Live state model

Idle sample:

```json
{"active_terminals": [], "queue_page_0": {"program": 0, "running": false, "zonesRemaining": 0}, "queue_page_1": [], "irrigation_state": "idle"}
```

Manual station 1 sample:

```json
{"active_terminals": [1], "queue_page_0": {"program": 4, "running": true, "zonesRemaining": 0}, "queue_page_1": [{"order": 1, "program": 0, "seconds": 80, "zone": 1}], "irrigation_state": "running"}
```

Page-0 program `4` was observed during manual irrigation, **not** validated as “Program D”. In queue-page-1 status outputs, `program=0` was observed for manual station watering, `1` for A, and `2` for B. These are *status decoding observations*, not validation of manual program-start `0x38` input numbering.

### Confirmed idle

`LocalIrrigationState.confirms_idle` is true only when the derived state is `idle` **and** neither `active_terminals` nor `current_queue_page_0` failed in that snapshot. A failed active-terminal read yields an empty tuple, which on its own could look idle; `confirms_idle` prevents that from counting as evidence. Stop no-op and stop verification both use it.

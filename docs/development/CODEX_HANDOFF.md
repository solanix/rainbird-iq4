# Developer Handoff

## Developer operating rules

- Work only in the relevant library and custom integration repositories; **never change Home Assistant Core source**.
- Tests must be offline, mocked, and deterministic; no network/controller access from tests or automated diagnostics.
- Live reads only after deliberate operator invocation; writes require a conspicuous explicit opt-in and in-person safe test conditions.
- Never repeat an ambiguous write automatically; do not claim command acknowledgement is physical state verification.
- Preserve connection-close HTTPS transport, shared local operation lock, independent cloud/realtime/slow coordinators, HA entity IDs and cloud-derived names.
- Resolve stations by stable cloud station ID and explicitly `is_enabled=True`; terminal availability alone is insufficient.
- Unknown safety data (rain, terminal availability, irrigation enabled, idle) **blocks** a start; it never blocks a stop.
- Do not commit, tag, or publish unless the user explicitly requests it.
- Report exact files changed, compatibility assumptions, commands/test results and unknowns.

## Current state (2026-10-10)

Phase 2C is accepted: implemented, offline-tested, committed locally, and live-validated by the operator ([LIVE_VALIDATION_LOG.md](../quality/LIVE_VALIDATION_LOG.md)). Live tests remain operator-only; a developer or agent must **not** perform them.

## Next task: Phase 2D dashboard

```text
Design and implement a Home Assistant dashboard for Rain Bird IQ4 control in
/workspaces/ha-rainbird-iq4.

Baseline:
- Admin-only actions rainbird_iq4.start_station(device_id, station_id,
  duration_minutes 1-30) and rainbird_iq4.stop_irrigation(device_id) exist,
  return {acknowledged, verified, no_op, station_id, terminal}, and raise
  translated errors (see docs/reference/HA_INTERFACE.md).
- Entities: irrigation state, active station, remaining runtime, rain sensor,
  rain delay, station metadata (station_enabled, station ID, terminal).
- 105 library, 78 stub and 23 real-HA integration tests pass.

Requirements:
1. Examine the current Git diff and tests first; do not overwrite uncommitted
   user changes.
2. Show status, active station, remaining time, rain flags; responsive on
   desktop and mobile; handle unavailable entities explicitly.
3. Offer only stations whose station_enabled is true; never disabled or unknown.
4. Explicit duration input (1-30) and explicit Start and Stop with confirmation
   before Start.
5. Surface verified / unconfirmed / no-op / error outcomes clearly; never
   auto-retry.
6. Respect user-customized names.
7. Prefer standard HA cards and helpers; avoid frontend forks.
8. No live controller contact, HA Core modifications, or commits.

Report exact changes, assumptions and a manual UI review checklist.
```

## Next developer orientation

Read `PROJECT_STATUS.md`, `architecture/SYSTEM_ARCHITECTURE.md`, `reference/HA_INTERFACE.md`, `reference/LOCAL_PROTOCOL.md`, `operations/CONTROL_SAFETY.md`, then inspect actual repos and run all three test suites (commands in `development/DEVELOPER_SETUP.md`). Trust current code/fixtures over historical narrative when they disagree; document discrepancies rather than silently overwriting or assuming previously proposed code exists.

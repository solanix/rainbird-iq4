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

## Current state (2026-10-12)

Phase 2C is accepted: implemented, offline-tested and live-validated by the operator ([LIVE_VALIDATION_LOG.md](../quality/LIVE_VALIDATION_LOG.md)). Live tests remain operator-only; a developer or agent must **not** perform them.

Phase 2D is built: the Lovelace card in `dashboard/` ships inside the integration and is validated in dev HA ([VALIDATION.md](../../dashboard/VALIDATION.md)). Local polling now rides out brief controller-port contention (retry once, then a grace window). `pyrainbird-iq4` 0.1.0 is on PyPI and both repositories are public with CI. Test counts and open items: [PROJECT_STATUS.md](../PROJECT_STATUS.md).

## Next tasks

1. Add a short connect timeout to `pyrainbird-iq4`'s local transport, so a hung first connect during a contention outage no longer holds polling ~30 s; release it and bump the integration's pin.
2. Work the Phase 4 / P1 backlog in [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md): migrate the stub suite to real HA.
3. Remaining Phase 2D checks need a browser or the operator: archived screenshots, the admin flow up to the confirmation step (never confirm), a screen-reader pass, and live start/stop under supervision.

## Next developer orientation

Read `PROJECT_STATUS.md`, `architecture/SYSTEM_ARCHITECTURE.md`, `reference/HA_INTERFACE.md`, `reference/LOCAL_PROTOCOL.md`, `operations/CONTROL_SAFETY.md`, then inspect actual repos and run all three test suites (commands in `development/DEVELOPER_SETUP.md`). Trust current code/fixtures over historical narrative when they disagree; document discrepancies rather than silently overwriting or assuming previously proposed code exists.

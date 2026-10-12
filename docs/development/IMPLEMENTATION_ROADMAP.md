# Implementation Roadmap and Acceptance Gates

## Phase 0 — Foundations (completed)

- Python companion library and HA custom integration exist.
- Cloud IQ4 auth/discovery, typed sites/controllers/stations/program metadata.
- Local HTTPS JSON-RPC/SIP read-only diagnostic and model.
- HA devcontainer and editable installation/dev runtime.
- Offline tests and lint/type checks.

## Phase 1 — Read-only observability (completed, monitored)

- Cloud discovery, names, stations, scheduled programs, effective runtime assignments.
- Local realtime and slow coordinators; connection-close transport and adaptive polling.
- Station enablement tri-state, program reference/effective assignment separation.
- HA entities for state, activity, rain/availability and metadata.
- Validated idle, running manual and program queues; HA transient unavailable condition recovered and no reproducing code defect found.

**Operational follow-up:** Recorder 'database or disk is full' root cause is not fully resolved. No errors in the current log as of 2026-10-10; keep tracking filesystem pressure before long soak tests.

## Phase 2A — Local write library and guarded HA internal boundary (completed)

- Implemented `start_station(terminal, duration_minutes)` and `stop_irrigation()`.
- Input validation and exception handling; no blind retries.
- Internal HA coordinator boundary resolves stable station ID, checks enabled status, local idle/freshness, and serializes operations.
- Bounded read-only post-write verification fixes first-snapshot race.
- Policy gaps (idle stop, stop verification, rain/terminal checks) were found on inspection and corrected during Phase 2C.

## Phase 2B — Live write validation (completed)

- Read-only `0x04` capability query showed 0x38/0x39/0x40 SUPPORTED.
- Started Station 001 with 1 and 2 minute requests; verified through local queue and active terminal.
- Stopped active Station 001 through 0x40; acknowledged and verified.
- Did not validate program-start argument numbering or pause/resume.

## Phase 2C — Public Home Assistant actions (accepted 2026-10-10)

| Deliverable | State |
|---|---|
| `rainbird_iq4.start_station` (device ID, stable station ID, 1–30 min) | Done |
| `rainbird_iq4.stop_irrigation` (device ID) | Done |
| Admin-only authorization; device/entry resolution; multi-controller-safe registration | Done (`async_setup` + `async_register_admin_service`; see ADR-011) |
| Start guards: cloud enabled `True`, terminal available, fresh complete idle, serialized, rain policy | Done (fresh in-lock reads; unknown blocks; ADR-012) |
| Stop available without cloud/realtime freshness; idle no-op | Done |
| Distinguish verified / unconfirmed / rejected / ambiguous | Done (response data + translated errors) |
| Tests: setup/reload, auth, multi-controller, inputs, outcomes, teardown; no live writes | Done (78 stub + 23 real-HA) |

**Acceptance gate:**

- [x] HA restarts and loads both actions with no errors and no writes.
- [x] Supervised manual validation via Developer Tools ([log](../quality/LIVE_VALIDATION_LOG.md)).
- [x] Recorder healthy after restart (no disk-full or rollback errors).
- [x] Committed per repository.

## Phase 2D — Dashboard/UI (in progress)

**Delivered (2026-10-10, offline-tested):** `select` station picker (enabled stations only) and `number` duration entities; `examples/script.yaml` (starts the selected station; tested in real HA, including the admin check); `examples/dashboard.yaml` (sections view: status tiles, picker, duration slider, Start with confirmation shown only when idle, Stop always shown).

**Live-tested on desktop 2026-10-10** ([log](../quality/LIVE_VALIDATION_LOG.md)).

**Delivered (2026-10-11/12):** the Rain Bird IQ4 Lovelace card (`dashboard/`, `custom:rainbird-iq4-card`), bundled into `custom_components/rainbird_iq4/frontend/` and loaded on every dashboard by `card.py`, so no resource step is needed. Status, controls, zones, programs, history and diagnostics views; Start only for enabled stations with an explicit review/confirm step; verified/unconfirmed/no-op/error outcomes; view-only for non-admins. Validated in dev HA at 320–1367 px, light and dark, keyboard, admin and view-only ([VALIDATION.md](../../dashboard/VALIDATION.md)). This settles the strategy question: the card ships with the integration and `examples/` stays as the no-custom-card alternative.

**Remaining:** screen-reader pass (operator); live start/stop through the card (operator-authorized and supervised); translations beyond English. The admin flow up to the confirmation step and archived screenshots were done 2026-10-12.

Responsive desktop/mobile status panel with irrigation state, active station/program, remaining time, rain flags, enabled station selector, duration input, explicit Start and Stop. Do not expose disabled or unknown-state stations for start. Use the action response (`verified`, `no_op`) and error keys for feedback. Consider HA card/action confirmations for accidental watering. Plan accessibility, unavailable states and user-customized names.

## Phase 3 — Manual program execution (research + gating)

Investigate SIP `0x38` numeric program argument mapping from actual library encode/decode and safe, explicitly authorized test protocol. Do not infer arguments from queue status codes. Define behavior for unscheduled Program C; policy required. Add typed program action only after independent validation.

## Phase 4 — Hardening and release

- Health/soak tests for cloud WAF outages, local intermittent resets, HA restart/unload, SQLite Recorder behavior, stale data, dual-controller isolation. Offline coverage added 2026-10-12: reload/unload during a write (`test_concurrency.py`), one controller's outage or unload not affecting another (`test_isolation.py`). A long live soak is still open.
- Metrics and structured logs with secrets redacted; controlled release/rollback.
- Entity registry migration and rename policy; documentation and service localization.
- Test on additional compatible IQ4 controllers/firmware if available; avoid assuming device-class equivalence.
- Repository hygiene: review diffs, pin/version dependencies, security audit, remove site-specific values from docs before publishing, deliberate commits/tags and release notes.

## Open backlog (prioritized)

Quality-scale status per rule: `custom_components/rainbird_iq4/quality_scale.yaml` (reviewed 2026-10-10).

| Priority | Item | Reason |
|---|---|---|
| P0 | Verify disk/Recorder health after restart | Earlier SQLite writes failed |
| P0 | Preserve exact-once write semantics | Watering commands have physical effects |
| P1 | Local connect timeout in `pyrainbird-iq4` | A hung first connect still holds polling ~30 s during contention outages |
| P2 | Program-start protocol input mapping | Avoid watering unintended schedules |
| P2 | Support matrix for firmware variations | Current proof covers one device/firmware |

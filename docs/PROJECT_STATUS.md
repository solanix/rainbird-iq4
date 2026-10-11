# Project Status and Completion Matrix

**As of:** October 10, 2026, after Phase 2C live acceptance. Repository source, tests and quality gates were **directly inspected and re-run** on this date. Live controller evidence is from operator-run diagnostics and the supervised HA action test recorded in [LIVE_VALIDATION_LOG.md](quality/LIVE_VALIDATION_LOG.md).

| Capability | Status | Evidence / caveat |
|---|---|---|
| IQ4 cloud login and site/controller discovery | Operational | Backyard/Home site discovery and controller catalog observed; cloud login may be WAF-limited or time out |
| Cloud station metadata and IQ4 names | Implemented and observed | Cloud station name authoritative by default; local overrides respected |
| Tri-state station enablement | Implemented and tested | IQ4 `isLocked` counterintuitively maps True→enabled, False→disabled, unknown→unknown |
| Program and station runtime metadata | Implemented and tested | Effective/scheduled assignments distinguished from raw program references |
| Local HTTPS controller authentication | Live-validated | Encrypted JSON-RPC/SIP on TCP 443 |
| Local realtime irrigation telemetry | Live-validated | Active terminals, running queue, remaining runtime, state |
| Local slow telemetry | Live-validated | Global irrigation-enabled flag, physical terminals, rain sensor/delay |
| Adaptive realtime polling | Implemented and observed | 30 sec idle; 10 sec while running; failure backoff 30/60/120 sec |
| Local connection-close transport | Implemented and observed | Eliminated previously recurring errors in observed baseline; not proof of universal reliability |
| Local command-support query (`0x04`) | Live-validated | `0x38`, `0x39`, `0x40` each returned SUPPORTED |
| Python manual station start (`0x39`) | **Live-validated** | Station 001 terminal 1; state and queue confirmed actual running |
| Python stop irrigation (`0x40`) | **Live-validated** | Active run stopped; diagnostic returned ACKNOWLEDGED verified=True |
| Bounded read-only post-write verification | Implemented and live-observed (start and stop) | Start: `wait_for_station_active`; stop: new `wait_for_idle`. Up to 5 snapshots, 1 sec spacing; never repeats a write |
| Internal HA control boundary | Implemented and offline-tested (inspected) | Corrected on 2026-10-10 to match the safety policy; see discrepancies below |
| Public HA `start_station`/`stop_irrigation` actions | **Live-validated (2026-10-10)** | Admin-only; registered in `async_setup`; 23 real-HA tests. Idle stop no-op, Station 001 start and stop each verified with exactly one write; disabled Station 008 refused |
| Manual Program A/B/C start (`0x38`) | Deferred | Command supported, input numbering unverified |
| Control dashboard | Live-tested (desktop) | Picker and duration entities, example script and dashboard; Station 002 start/stop via dashboard verified. Mobile review pending |
| Published release / upstream submission | Not done | Phase 2A–2C committed locally (no remotes); no release |

## Current test evidence (re-run 2026-10-10)

| Suite | pytest | Ruff | Format | mypy |
|---|---:|---|---|---|
| `pyrainbird-iq4` | **105 passed** | Passed | Passed | Passed (strict) |
| `ha-rainbird-iq4` `tests/` (HA stubs) | **76 passed** | Passed | Passed | Passed |
| `ha-rainbird-iq4` `tests_ha/` (real HA 2026.10.0.dev0) | **80 passed** | Passed | Passed | Not in mypy scope |

Baseline before Phase 2C was confirmed exactly as reported: 102 library / 58 integration, all gates clean. Earlier milestones: 73/50, 82/58, 99/58, 102/58.

## Discrepancies found on inspection

The repository inspection found the following differences between the documented policy and the uncommitted Phase 2A code. All were corrected in code:

| Documented | Code before 2026-10-10 | Now |
|---|---|---|
| Stop is a safe no-op when definitively idle | Always sent `0x40`; a test asserted this | Complete idle snapshot ⇒ `no_op=True`, nothing sent |
| Stop verified with bounded reads | Single post-write read | `wait_for_idle()`: up to 5 reads, requires complete idle |
| Start blocked by rain sensor / rain delay | No rain check | Fresh in-lock slow read; active **or unknown** rain blocks |
| Start requires terminal locally available | Not checked | Fresh `available_terminals` must contain the terminal |
| HA integration tests exercise HA behaviour | All 58 tests ran against hand-written `tests/stubs/homeassistant` | Stub suite kept; new `tests_ha/` runs against the real HA checkout |
| Library repo hygiene | 35 `.pyc` and 6 `egg-info` files tracked | Untracked (staged removal) and `.gitignore` added |

## Live control evidence (historical, library diagnostic)

1. Controller authenticated successfully and showed idle state, with stations 1–10 physically available and no rain-sensor/rain-delay block.
2. Initial one-minute Station 001 start returned `ACKNOWLEDGED verified=False`; subsequent read-only diagnostic showed `active_terminals=[1]`, page-0 `{'program':4,'running':True,'zonesRemaining':0}`, page-1 with `{'program':0,'seconds':5,'zone':1}`. Root cause: single verification read too early.
3. After correction, one-minute start returned `ACKNOWLEDGED verified=True`.
4. Attempted stop while idle returned `NOT SENT verified=True (already idle)`; correctly **not** proof that `0x40` was transmitted.
5. Two-minute start verified true; stop diagnostic observed terminal 1 running, with 80 seconds remaining, and then returned `ACKNOWLEDGED verified=True`. This is the live stop confirmation.

## Operational issues and interpretation

- **Recorder:** one historical incident of `sqlite3.OperationalError: database or disk is full`, then `PendingRollbackError`; root cause not conclusively established. Check on 2026-10-10 (HA stopped): overlay 29 GB / 4.2 GB free (85%), workspace 361 GB / 32 GB free (91%), inodes 21% / 5%, DB 150 MB, WAL 4 MB, **no disk-full or rollback errors in the current log**. Still re-check after the next restart and during soak.
- An HA irrigation-state entity transiently appeared unavailable around 00:34 UTC on Oct 10 and recovered by ~00:37:35. No reproducing integration defect found; no production fix made.
- Disabled stations' HA registry defaults apply at entity creation only; re-enabling a station in IQ4 may require manual enabling in the HA registry.
- Some `active_terminals` requests took ~2.7–2.9 sec, queue reads ~150–200 ms. Note that a start now performs a realtime read **and** a slow read inside the lock before writing, so expect a start action to take several seconds plus up to ~5 sec of verification.

## Immediate next gate

Phase 2C is accepted. In progress: Phase 2D dashboard ([roadmap](development/IMPLEMENTATION_ROADMAP.md#phase-2d--dashboardui-next)). Return HA debug logging to info/warning once no longer needed.

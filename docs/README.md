# Rain Bird IQ4 — Development Documentation

**Project:** Rain Bird IQ4 / Home Assistant integration  
**Documentation baseline:** 2026-10-10 (revised after Phase 2C implementation)  
**Status:** Read-only cloud/local integration operational; local manual station start and stop live-validated through the library; Home Assistant admin-only `start_station`/`stop_irrigation` actions **implemented and offline-tested, not yet live-validated through HA**.  
**Repositories:** `pyrainbird-iq4`, `ha-rainbird-iq4` (this repository, which now hosts these docs), and an unmodified Home Assistant Core development runtime.

## Purpose

Build a secure, reliable, maintainable Home Assistant custom integration for Rain Bird IQ4 controllers. Support cloud-derived discovery and metadata; local HTTPS-based controller state; manual zone operation (and later program operation) and a responsive dashboard. Maintain a clean split between reusable Python protocol access and Home Assistant entities/actions.

## Repository and document map

| Document | Purpose |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Feature-by-feature completion, proof, remaining work, known issues |
| [architecture/SYSTEM_ARCHITECTURE.md](architecture/SYSTEM_ARCHITECTURE.md) | Components, data flow, lifecycle, polling and concurrency |
| [architecture/DATA_MODEL.md](architecture/DATA_MODEL.md) | Controller, station, program and entity semantics |
| [reference/CLOUD_API.md](reference/CLOUD_API.md) | Verified/discovered IQ4 cloud endpoints and constraints |
| [reference/LOCAL_PROTOCOL.md](reference/LOCAL_PROTOCOL.md) | HTTPS/SIP interface, command observations, support and writes |
| [reference/HA_INTERFACE.md](reference/HA_INTERFACE.md) | Existing entities and the HA control actions |
| [development/DEVELOPER_SETUP.md](development/DEVELOPER_SETUP.md) | Workspace, runtime, commands, environment |
| [development/IMPLEMENTATION_ROADMAP.md](development/IMPLEMENTATION_ROADMAP.md) | Completed phases, acceptance gates, work backlog |
| [development/CODEX_HANDOFF.md](development/CODEX_HANDOFF.md) | Developer constraints and reusable next-phase task |
| [operations/RUNBOOK.md](operations/RUNBOOK.md) | Troubleshooting, logs, Recorder, local diagnostics and actions |
| [operations/CONTROL_SAFETY.md](operations/CONTROL_SAFETY.md) | Safety policy, state confirmation, test protocol |
| [quality/TEST_STRATEGY.md](quality/TEST_STRATEGY.md) | Test boundaries, regression matrix, evidence |
| [decisions/ADR_LOG.md](decisions/ADR_LOG.md) | Architecture decision log |
| [CHANGELOG.md](CHANGELOG.md) | Project development history and milestones |

## Quick start

Start the existing HA development runtime (from inside its VS Code Dev Container):

```bash
cd /workspaces/home-assistant-core
/home/vscode/.local/ha-venv/bin/python -m homeassistant -c ./config
```

The HA UI is at `http://localhost:8123`. For a direct **read-only** local diagnostic, stop HA local polling first, then run:

```bash
cd /workspaces/pyrainbird-iq4
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10
```

The diagnostic prompts for a **local controller password**; never store that secret in source files or shared logs. The IP and IDs in these docs are **development-environment example values**, not generic defaults. Do not paste private controller addressing or credentials into public issues, and review these docs for site-specific values before publishing this repository.

## Key status boundary

A controller advertising support for a SIP command is not the same as live command validation. Live tests confirmed station start (`0x39`) and stop (`0x40`) with state verification through the library diagnostic. Program start (`0x38`) is **advertised supported only**; program input numbering has not been verified. The HA actions wrap the same library calls but have **not** yet been exercised against the real controller; see the supervised procedure in [CONTROL_SAFETY.md](operations/CONTROL_SAFETY.md).

## Evidence provenance

The original package was assembled from development reports, terminal outputs and diagnostic observations. On 2026-10-10 the repositories were **directly inspected**, all quality gates were re-run, and discrepancies between the narrative and the code were corrected in code (see [PROJECT_STATUS.md](PROJECT_STATUS.md#discrepancies-found-on-inspection)). Where a statement is still based on historical reports rather than current inspection, the documents say so. Compare against the Git working trees before release.

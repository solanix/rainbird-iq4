# Architecture Decision Records (Condensed)

## ADR-001 — Separate protocol library from HA adapter
**Status:** Accepted.  
**Decision:** `pyrainbird-iq4` contains typed protocol/model/diagnostic logic; `ha-rainbird-iq4` owns HA coordinators, entities and user actions.  
**Reason:** Testability, reusable non-HA client, clear lifecycle and security responsibilities.

## ADR-002 — Cloud discovery, local realtime control
**Status:** Accepted.  
**Decision:** Use cloud IQ4 for site/controller/station/program catalog; local HTTPS for fast status and manual control.  
**Reason:** Cloud contains authoritative names/IDs, while local gives responsive state and control. Cloud availability must not gate stop.

## ADR-003 — Connection-close local transport
**Status:** Accepted, operationally observed.  
**Decision:** Avoid persistent TCP keep-alive; request a fresh connection for each local operation.  
**Reason:** Previously recurrent alternating local connection errors; observed baseline stabilized after change. Monitor latency/performance.

## ADR-004 — Independently scheduled realtime/slow/cloud coordinators
**Status:** Accepted.  
**Decision:** 30-sec idle/10-sec running fast local; 300-sec slow local and cloud; failure backoff.  
**Reason:** Responsive active irrigation UX without unnecessary slow metadata calls.

## ADR-005 — Preserve station tri-state; do not invert `isLocked`
**Status:** Accepted with real-device evidence.  
**Decision:** raw True→enabled, False→disabled, missing→unknown.  
**Reason:** Live IQ4 station data contradicts intuitive meaning of property name.

## ADR-006 — Distinguish program references from effective assignments
**Status:** Accepted.  
**Decision:** Preserve unscheduled Program C reference but keep effective count 0. *Revised 2026-10-10:* every program that is scheduled **or** still assigned to a station gets a program entity; unscheduled ones read `Not scheduled` with `effective: false`. A program entity becomes unavailable only when the program is gone from both.  
**Reason:** A configured program without scheduled starts is real and must not be mislabeled stale or treated as effective watering schedule. Building program entities only from scheduled programs left Program B as an orphaned `unavailable` entity after a restart and gave Program C no entity at all.

## ADR-007 — Exactly-one write; bounded read-only verification
**Status:** Accepted; start live-validated; stop verifier extended 2026-10-10.  
**Decision:** No blind retries of writes; status after acknowledgement confirmed via up to five read-only snapshots, for both start (`wait_for_station_active`) and stop (`wait_for_idle`).  
**Reason:** First live start succeeded but immediate snapshot falsely indicated no watering; stop deserves the same tolerance.

## ADR-008 — Guard application boundary using stable station IDs
**Status:** Accepted; implemented in public actions (Phase 2C).  
**Decision:** User-facing HA selection resolves cloud station ID to terminal and requires `is_enabled is True`; low-level client validates input shape/range.  
**Reason:** Physical capacity is not authorization; protect against disabled/wrong-controller starts.

## ADR-009 — Defer manual program-start API
**Status:** Accepted.  
**Decision:** Do not expose SIP `0x38` until program argument semantics confirmed.  
**Reason:** Queue status program codes do not establish write argument mapping.

## ADR-010 — No HA Core modifications; no automated live controller access
**Status:** Accepted.  
**Decision:** Develop in custom repos, offline mocks, opt-in manual diagnostics, no automatic commits.  
**Reason:** Isolated and reproducible development, prevent unintended watering.

## ADR-011 — Register actions once in `async_setup`
**Status:** Accepted 2026-10-10 (supersedes the handoff's "unregister on last entry").  
**Decision:** Register `start_station`/`stop_irrigation` with `async_register_admin_service` in `async_setup`, never unregister, and reject calls whose device's entry is not loaded (`entry_not_loaded`).  
**Reason:** Current HA practice (Integration Quality Scale rule `action-setup`). Avoids duplicate registration and reload races across multiple entries, keeps actions valid in automations while an entry is reloading, and gives clear errors.

## ADR-012 — Fresh in-lock safety reads; unknown blocks start
**Status:** Accepted 2026-10-10.  
**Decision:** Immediately before a start write, inside the shared operation lock, read realtime **and** slow state fresh. Block on not-idle, incomplete realtime, irrigation not confirmed enabled, terminal not confirmed available, or rain sensor / rain delay active **or unknown**. Also require the latest cloud refresh to have succeeded. Stop has none of these requirements and is a no-op only when a fresh complete read proves idle.  
**Reason:** Slow data can be 5 minutes old; rain and controller state can change in that window. Asymmetric policy: an unnecessary refusal to start is cheap, an unintended start is not; an unnecessary stop is cheap, a blocked stop is not. Cost: a start takes a few extra seconds.

## ADR-015 — Add IQ4 entities live; remove stale ones only at a live setup
**Status:** Accepted 2026-10-11.  
**Decision:** Add station, program and runtime entities whenever a successful cloud refresh shows new ones. Remove registry entries for ones no longer in IQ4 only during setup, only with live cloud data (not the saved snapshot) that contains at least one station, and only for station, program and per-station runtime unique IDs.  
**Reason:** Additions are harmless; deletions discard user customizations and cannot be undone. Deferring them to a live setup and refusing on empty or saved data keeps a cloud hiccup from deleting entities, while still cleaning up real removals.

## ADR-014 — Saved cloud snapshot keeps local stop available
**Status:** Accepted 2026-10-10.  
**Decision:** Persist the last good cloud snapshot per entry in HA storage. If the first cloud refresh fails at startup and local control is configured, load the snapshot and finish setup with the cloud coordinator still marked failed. Cloud entities stay unavailable and starts stay blocked until a live refresh succeeds; local entities and stop work. Without local control or without a snapshot, setup retries as before; credential rejection still triggers reauth. Serialization lives in the integration (`saved_data.py`) as an integration cache, not in the library.  
**Reason:** Every entity is built from cloud data, so the cloud first refresh gated the whole entry; an IQ4/WAF outage at HA startup made local stop unavailable, contradicting ADR-002. Using an old snapshot for display is acceptable only while it is clearly marked unavailable and never used to authorize a start.

## ADR-013 — Real-HA test suite alongside stubs
**Status:** Accepted 2026-10-10.  
**Decision:** Add `tests_ha/`, run from the Core checkout with Core's pytest plugin, for anything that depends on HA behaviour (authorization, schemas, registries, lifecycle). Keep the existing stub suite for now; plan to migrate it.  
**Reason:** The 58-test baseline ran entirely against hand-written stubs, which cannot verify admin authorization or registry behaviour. `pytest-homeassistant-custom-component` would pin a different HA version than the dev checkout; using Core's own fixtures tests the exact installed version without modifying Core.

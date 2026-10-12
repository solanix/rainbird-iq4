# Irrigation Control Safety Policy

## Scope and physical effects

Manual station writes actuate irrigation hardware. Tests require a responsible operator who can visually verify the correct zone and independently stop watering. Consider water damage, sprinkler positioning, property access, simultaneous scheduled operation, rain sensor/delay, pumps and freeze/weather risk. Never run live writes automatically, during startup, on CI, or without deliberate permission.

## Confidence states

| State | Meaning | HA action surface |
|---|---|---|
| **SUPPORTED** | Controller advertises SIP operation capability from read-only query (`0x04`) | — |
| **ACKNOWLEDGED** | Controller/protocol returned expected write acknowledgement; *physical transition is not yet guaranteed* | `acknowledged: true` |
| **VERIFIED** | Read-only post-write state confirms requested terminal is active, or irrigation is idle after stop | `verified: true` |
| **ACKNOWLEDGED / UNCONFIRMED** | Write acknowledged but read verification did not prove the transition | `acknowledged: true, verified: false` + warning log |
| **AMBIGUOUS** | Write transport failed where the controller may have received the request. Do not automatically retry | `write_outcome_ambiguous` error |
| **NOT SENT** | Command intentionally skipped (stop while confirmed idle) or rejected before any write. Not live command validation | `no_op: true`, or any other error key |

## Start guard policy (implemented)

All of the following must hold, otherwise the start is rejected and **nothing is sent**:

1. Admin user; HA device resolves to exactly one loaded IQ4 config entry that owns the device; local control configured.
2. Integer 1–30 minute duration (bool and fractions prohibited) — enforced by both the action schema and the control boundary.
3. Most recent cloud refresh succeeded; stable cloud station ID exists in **this** controller's catalog; `is_enabled is True`.
4. Coordinator realtime snapshot present, ≤ 60 s old, `active_terminals` and queue page 0 both read, and confirmed idle.
5. Inside the shared operation lock, a **fresh** realtime read is complete and confirmed idle, and a **fresh** slow read shows:
   - `irrigation_enabled is True`;
   - the station's terminal in `available_terminals` (unknown list blocks);
   - `rain_sensor_active is False` and `rain_delay_days == 0` (unknown **or** active blocks).
6. Never auto-preempt an existing run.

The low-level transport validates input shape/range, but does not and should not infer enablement from terminal number. Eligibility belongs at the HA/application boundary.

## Stop guard policy (implemented)

Stop does **not** depend on cloud metadata or fresh coordinator telemetry. Inside the operation lock it takes one fresh realtime read:

- Complete and idle ⇒ safe no-op; nothing sent (`no_op: true`).
- Running, paused, unknown, incomplete, or the read failed ⇒ send stop **once**.
- Connection failure before any write ⇒ `controller_unreachable` (definitely not sent).
- Write transport failure ⇒ `write_outcome_ambiguous`; not retried.

## Serialization, retry and verification

- Local read and write operations share the local operation lock.
- The lock also holds across a reload or unload: unloading the entry waits for the operation in progress (a start or stop is never cut off between write and verification), then closes the connection, so the reloaded entry's new connection cannot read or write while an old write is in flight. An operation queued behind the close is refused (`connection_closed`) and sends nothing; service calls made after unload starts are refused earlier (`entry_not_loaded`).
- Start preflight/write/verification is atomic relative to integration local polling.
- After only **one** acknowledged start, observe up to **five** read-only snapshots with one-second waits. An active terminal match or running queue entry matching the requested terminal confirms it.
- After only **one** acknowledged stop, observe up to **five** read-only snapshots with one-second waits; verified only when a complete snapshot is idle (`wait_for_idle` / `confirms_idle`).
- Do not mistake manual queue page-0 program code 4 for Program D or use page-1 status codes as program-start arguments.
- Never automatically repeat writes after timeout, connection drop, ambiguous outcome or failed post-write confirmation.

## Library diagnostic write commands (physically actuate water)

The following are **examples only**. They intentionally include an explicit confirmation token. Do not execute until an operator has selected a known-safe zone and is physically ready. Shut down HA's local polling beforehand to avoid concurrent sessions.

Start terminal 1, 1 minute:

```bash
cd /workspaces/pyrainbird-iq4
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10 \
  --write-test start --station-id 30000001 --terminal 1 \
  --duration-minutes 1 --confirm-write I_UNDERSTAND_THIS_WATERS
```

Stop when watering is running:

```bash
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10 \
  --write-test stop --confirm-write I_UNDERSTAND_THIS_WATERS
```

These commands have already been manually run and validated for controller 200001. Repeating them is not needed for documentation purposes. If status is ambiguous, do **not** rerun the write; inspect physical/controller status and use established app/physical controls to stop unintended watering.

## Supervised HA action validation

**Performed 2026-10-10; all steps passed** — see [LIVE_VALIDATION_LOG.md](../quality/LIVE_VALIDATION_LOG.md). Repeat after changes to the control path, on new firmware, or on a new controller. Operator-only; agents and automation must not run it.

1. Confirm safe conditions: Station 001 area clear, operator can see it, and can stop watering via the IQ4 app or at the controller. No standalone diagnostic running.
2. Restart HA. Check the log for no `rainbird_iq4` errors and that nothing started watering. Developer Tools → States: `sensor.backyard_irrigation_state` is `idle`.
3. Developer Tools → Actions, as an admin: **Rain Bird IQ4: Stop irrigation**, Backyard device, "return response" on. Expect `no_op: true`, `acknowledged: false`, `verified: true`; no watering change.
4. **Start station**: `station_id: 30000001`, `duration_minutes: 1`. Expect after a few seconds `acknowledged: true, verified: true, terminal: 1`, and Station 001 visibly watering. The irrigation-state sensor should switch to `running`.
5. While running, **Stop irrigation**. Expect `acknowledged: true, verified: true, no_op: false`; water stops; sensor returns to `idle`.
6. **Start station** with `station_id: 30000008` (Station 008, disabled). Expect `station_not_enabled`; nothing waters.
7. Optional: as a non-admin user, call either action. Expect an unauthorized error.
8. If any call reports `write_outcome_ambiguous` or `verified: false`, **do not retry**. Inspect the controller and stop with the app if needed.
9. Record each step in the live validation log template in [TEST_STRATEGY.md](../quality/TEST_STRATEGY.md#live-validation-log-template).

## Program starts

`0x38` SUPPORTED does not prove the numeric program argument mapping. Program C can be unscheduled but configured. No program-start write until protocol mapping, safety semantics, acceptance tests, and supervised live validation are complete.

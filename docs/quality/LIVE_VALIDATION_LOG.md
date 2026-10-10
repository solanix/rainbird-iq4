# Live Validation Log

Records of operator-supervised tests that physically actuated irrigation. Use the template in [TEST_STRATEGY.md](TEST_STRATEGY.md#live-validation-log-template). Log lines are from `/workspaces/home-assistant-core/config/home-assistant.log`.

## 2026-10-10 — Phase 2C HA actions (Developer Tools)

```text
Date/time + timezone:   2026-10-10, ~02:09–02:11 UTC
Controller/firmware:    Backyard 200001, firmware 3.11.0
Operator + safe zone:   Repository owner; Station 001 (terminal 1)
HA running or stopped:  HA 2026.10.0.dev0 dev runtime running (started from operator terminal 02:07:13);
                        no standalone diagnostic running
Operation:              HA actions rainbird_iq4.stop_irrigation and rainbird_iq4.start_station
                        (SIP 0x40 / 0x39), admin user, "return response" enabled
Requested:              station_id 30000001 / terminal 1 / 1 minute
Precondition snapshot:  Realtime poll 02:09:51 succeeded, idle interval (30 s)
```

| Step | Action | Result | Evidence |
|---|---|---|---|
| 1 | `stop_irrigation` while idle | `acknowledged: false, verified: true, no_op: true`; nothing sent | Operator screenshot of response; no `stop_irrigation` write logged before 02:10:23 |
| 2 | `start_station` 30000001, 1 min | Acknowledged and verified; Station 001 watered | `02:10:01.155 operation=start_station terminal=1 duration_minutes=1 outcome=acknowledged elapsed_ms=204`; polls at 02:10:03 and 02:10:14 used the 10 s running interval; no "acknowledged but not confirmed" warning |
| 3 | `stop_irrigation` while running | Acknowledged and verified; watering stopped | `02:10:23.344 operation=stop_irrigation outcome=acknowledged elapsed_ms=140`; polls from 02:10:24 returned to the 30 s idle interval; no "acknowledged but not confirmed" warning |
| 4 | `start_station` 30000008 (Station 008, disabled) | Refused (`station_not_enabled`); nothing sent | Operator report. HA does not log validation refusals; the log confirms no further start write |

```text
Write count:            Exactly one start and one stop write in the log for this HA session
Physical observation:   Operator reported all steps passed
Any unexpected effects: None. Unrelated: go2rtc port conflict from a killed earlier HA instance (cleared)
Follow-up / rollback:   None required. Return debug logging to info/warning
```

**Not covered by this session:** non-admin refusal (covered offline by `tests_ha::test_non_admin_is_rejected`), ambiguous-write handling, two-controller targeting.

## 2026-10-10 — Phase 2D dashboard (Start/Stop buttons)

```text
Date/time + timezone:   2026-10-10, ~02:40–02:45 UTC
Controller/firmware:    Backyard 200001, firmware 3.11.0
Operator + safe zone:   Repository owner; Station 002 (terminal 2)
HA running or stopped:  HA 2026.10.0.dev0 dev runtime running
Operation:              Dashboard from examples/dashboard.yaml: picker = Station 002, duration = 2 min,
                        Start (script, with confirmation) then Stop (rainbird_iq4.stop_irrigation)
```

| Time (UTC) | Event | Evidence |
|---|---|---|
| 02:40:17 / 02:40:49 | Start terminal 2 for 2 min, then stop (script run directly, then dashboard Stop) | `operation=start_station terminal=2 duration_minutes=2 outcome=acknowledged`; `operation=stop_irrigation outcome=acknowledged`; no unconfirmed warning |
| 02:44:50 | Dashboard Start, Station 002, 2 min | `operation=start_station terminal=2 duration_minutes=2 outcome=acknowledged elapsed_ms=222`; dashboard showed State `running`, Active station `Station 002`, Remaining 118 s, Start button hidden |
| 02:45:01 | Dashboard Stop | `operation=stop_irrigation outcome=acknowledged elapsed_ms=152`; returned to idle; no unconfirmed warning |

```text
Physical observation:   Operator reported the test looked good
Any unexpected effects: First Start press failed with "script not found": the UI saved the script with a
                        generated ID (backyard_start_selected_station); fixed by pointing the dashboard at
                        that ID and clarifying examples. A 30 s controller connection drop at 02:37 left rain
                        entities unavailable until the next 5-minute slow poll; slow-poll failure backoff added.
Follow-up / rollback:   None required
```

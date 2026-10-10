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

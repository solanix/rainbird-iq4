# Cloud API Reference (Observed / Discovered)

## Endpoints

Observed base and identity endpoints:

```text
https://iq4server.rainbird.com/coreapi/api/
https://iq4server.rainbird.com/coreidentityserver
```

Candidate discovery/list endpoints documented in the project:

| Path | Purpose / notes |
|---|---|
| `/Site/GetSites` | Discover sites |
| `/Satellite/GetSatelliteList` | Discover controllers/satellites |
| `/Satellite/isConnected?...` | Cloud connection status |
| `/Station/GetStationListForSatellite?satelliteId=...` | Station catalog, IDs, terminal, name, raw `isLocked` |
| `/Program/GetProgramList?satelliteId=...` | Program catalog |
| `/Program/GetScheduledStartTimes?satelliteId=...` | Program start-time data |
| `/ProgramStep/GetProgramsAssignedAndRunTimeBySatelliteId?satelliteId=...` | Program/station runtime assignments |

**Do not use** `/Station/GetStation` or `/Satellite/GetSatellite` as required dependencies. Both were observed returning HTTP 403 despite successful cloud authentication.

## Data parsing constraints

- Scheduled starts have been observed as `list[2]` with `programId`, `programName`, and `scheduledTimes`; `scheduledTimes` entries carry `startTime` and `startTimeIndex`.
- Program list and runtime data can vary over time and may include a real but unscheduled program.
- Null or absent station state values must normalize to unknown, not disabled.
- Use the cloud's station `name` as default presentation only, not as identity.
- Availability is separate from local transport; cloud refresh problems must not prevent local stop if controller credentials/local connection are configured.
- The `start_station` action requires the **most recent** cloud refresh to have succeeded (`last_update_success`), so a cloud or WAF outage blocks starts with `cloud_data_unavailable` but never blocks stop.

## Known service behavior

Cloud login has intermittently encountered AWS WAF interference or network timeouts. Reuse authenticated sessions where appropriate and avoid aggressive reauthentication or excessive polling. Do not fabricate support for undocumented endpoints; use offline fixtures or explicit, rate-conscious diagnostics for exploration.

## Security

Keep identity tokens, passwords, cookies and request/response bodies out of logs, screenshots, bug reports and version control. Avoid including personally identifying property/site information in public telemetry examples. Any endpoint details are observational, not a vendor-supported guarantee.

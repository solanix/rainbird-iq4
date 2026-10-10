# Local HTTPS / SIP Protocol Reference

## Controller link

- Development host: `192.0.2.10` (environment-specific)
- Transport: TLS/HTTPS TCP 443, encrypted JSON-RPC/SIP via `AsyncRainbirdController`.
- Firmware: 3.11.0; hardware: 57.
- Authentication: controller-local password provided at runtime, not printed or committed.
- Transport mode: `connection_close` / `keepalive=false` per request to avoid intermittent stale connections. Controller certificate is self-signed; follow the library's existing configured verification behavior rather than weakening TLS globally.

## Read-only local operations

| Operation | Meaning |
|---|---|
| `irrigation_enabled` | Global irrigation-enabled switch; True does **not** mean water is flowing |
| `active_terminals` | Current physical output terminals, e.g. `[]` or `[1]` |
| `available_terminals` | Physical capacity, **not** enabled-station eligibility |
| `rain_sensor` | Active rain-sensor state |
| `rain_delay` | Rain-delay days |
| `current_queue_page_0` | High-level queue running flag, program code, zonesRemaining |
| `current_queue_page_1` | Queue item(s), zone/program codes, remaining seconds |
| `CommandSupportRequest` (`0x04`) | Read-only command capability probe |

## Command support and evidence

| SIP | Upstream method | IQ4 support probe | Live write proof | Status |
|---|---|---|---|---|
| `0x39` | `irrigate_zone(zone, minutes)` | SUPPORTED | Yes: Station 001 one/two minute runs | Implemented/validated; exposed via HA `start_station` |
| `0x40` | `stop_irrigation()` | SUPPORTED | Yes: stopped active Station 001 with ~80s remaining | Implemented/validated; exposed via HA `stop_irrigation` |
| `0x38` | `set_program(program)` | SUPPORTED | No | Deferred pending program input numbering |
| `0x3A` | `test_zone(zone)` | Not established here | No | Out of scope |
| `0x42` | `advance_zone(param)` | Not established here | No | Out of scope |
| `0x4B` | Stack manual station | Not established here | No | Defined but not exposed |
| `0x37` | `set_rain_delay(days)` | Not established here | No | Not initial control scope |
| `0x49` | Controller state write | Not established here | No | Unknown semantics; avoid |

No pause/resume write has been confirmed. A `PAUSED` state value does not demonstrate pause/resume command support.

## Typed Python client

```python
async def start_station(self, terminal: int, duration_minutes: int) -> None: ...
async def stop_irrigation(self) -> None: ...
async def wait_for_station_active(
    self, terminal: int, *, attempts: int = 5, delay_seconds: float = 1.0
) -> bool: ...
async def wait_for_idle(self, *, attempts: int = 5, delay_seconds: float = 1.0) -> bool: ...
async def get_realtime_state(self) -> LocalIrrigationState: ...
async def get_slow_state(self) -> LocalIrrigationState: ...
```

`start_station` checks that terminal is a positive integer (not bool), and duration is an integer (not bool) in **1–30 minutes**, before any transport write. HA imposes **additional** station-ID/catalog, enabled-state, capacity, idle, rain and freshness checks. The library does not silently coerce or clamp parameters.

A successful write return means expected upstream protocol **acknowledgement**; it is not proof of actuation. Error taxonomy includes `ValueError`, `RainbirdAuthException`, `RainbirdConnectionError`, `TimeoutError`, `RainbirdDeviceNackError`, `RainbirdDeviceBusyException`, `RainbirdApiException`. Write failures are logged by classified outcome (`timeout_outcome_unknown`, `connection_outcome_unknown`, `controller_rejected`, …) without payloads.

## Verification policy

**Start:** after **one** acknowledged start, `wait_for_station_active` observes up to five read-only realtime snapshots with one-second spacing. Accept the requested terminal when `active_terminals` contains it, or when queue page 0 is running/active and page 1 refers to the requested terminal. Ignore page-0 `program=4` for program identity. Evidence for another terminal is not success.

**Stop:** after **one** acknowledged stop, `wait_for_idle` observes up to five read-only realtime snapshots with one-second spacing and succeeds only on `confirms_idle` (derived state idle **and** both `active_terminals` and `current_queue_page_0` read successfully).

An exhausted verification window or a failed verification read is `acknowledged=True, verified=False`. Do **not** reissue the write. On ambiguous transport failure during the write, the outcome is unknown; do not automatically retry either.

Stop must be callable without cloud connectivity or fresh coordinator telemetry. When a fresh read decisively shows idle, nothing is sent (`no_op=True`; the diagnostic prints `NOT SENT verified=True (already idle)`). That does **not** validate the stop command. If the pre-stop read fails, idle is unproven and stop is sent once.

## Read-only diagnostic

```bash
cd /workspaces/pyrainbird-iq4
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10 --check-control-support
python3 -m pyrainbird_iq4.local_diagnostic --help
```

The `--check-control-support` flag probes 0x38, 0x39, 0x40 read-only. Write tests are explicitly opt-in; see [Control Safety](../operations/CONTROL_SAFETY.md). Do not run automated writes on live controllers.

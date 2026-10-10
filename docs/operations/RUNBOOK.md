# Development Operations and Troubleshooting Runbook

## Controller read diagnostic

```bash
cd /workspaces/pyrainbird-iq4
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10
```

Normal idle report: `active_terminals=[]`; queue page 0 `running=False`; page 1 empty; `irrigation_enabled=True` is **global enablement**, not an active watering indication.

For command capability (read-only):

```bash
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10 --check-control-support
```

Keep HA local poller stopped during standalone diagnostics to avoid session contention. Never run write-tests as troubleshooting defaults.

## HA logs

Configuration: `/workspaces/home-assistant-core/config/configuration.yaml`.

```yaml
logger:
  default: warning
  logs:
    custom_components.rainbird_iq4: debug
    pyrainbird_iq4.local: debug
```

After restart, capture bounded logs:

```bash
tail -n 0 -F /workspaces/home-assistant-core/config/home-assistant.log \
  | grep --line-buffered -Ei 'rainbird|local.*poll|local control|connectionerror|timeout'
```

Check realtime coordinator **without** `_slow` suffix: `rainbird_iq4_200001_local`. Check slow separately: `rainbird_iq4_200001_local_slow`. Logs of successful slow polls alone do not prove irrigation-state sensor is updated. Return logging to warning/info after capture.

## Control action troubleshooting

| Symptom | Check |
|---|---|
| Actions missing from Developer Tools | HA restarted after code change? Log errors at `rainbird_iq4` setup? Actions register in `async_setup`, even with no entries |
| `Unauthorized` | Calling user is not an administrator (by design) |
| `local_not_configured` | Integration options lack local host/PIN |
| `cloud_data_unavailable` | Cloud coordinator's last refresh failed (WAF/timeout). Stop still works; wait for the next successful cloud poll (~5 min) |
| `telemetry_stale` / `telemetry_unavailable` | Realtime coordinator hasn't succeeded within 60 s; check local poll logs and `consecutive_failures` |
| `controller_not_idle` | Something is running, paused, or the queue is not confirmably idle. Stop first, or wait |
| `rain_*` / `irrigation_disabled` / `terminal_unavailable` | Controller safety state blocks start (unknown also blocks). Check slow sensors and the controller |
| `verified: false` | Acknowledged but not observed within ~5 s. **Do not retry**; check the irrigation-state sensor and the zone |
| `write_outcome_ambiguous` | Command may have executed. **Do not retry**; inspect physically, stop via app if needed |
| `controller_unreachable` | Nothing was sent; check controller network reachability |

## Cloud password changed or rejected

If IQ4 rejects the stored cloud credentials, HA shows **Re-authenticate** for the Rain Bird IQ4 entry (Settings → Devices & services, or the repairs/notifications area). Enter the current IQ4 cloud password; the integration checks that the account can still see the configured controller, then reloads. Until then cloud data is unavailable and `start_station` is refused with `cloud_data_unavailable`; `stop_irrigation` keeps working locally.

## HA sensor unavailable investigation

1. Check Developer Tools → States for `sensor.backyard_irrigation_state` and attributes, including timestamp and `consecutive_failures`.
2. Confirm `binary_sensor.backyard_controller_connected` is cloud connectivity only.
3. Inspect nearest realtime `active_terminals` and `current_queue_page_0` RPC result plus coordinator completion.
4. If backend States shows `idle` but a card shows `unavailable`, hard-refresh UI; do not edit registry or state manually.
5. Inspect entity-registry uniqueness and `disabled_by/hidden_by` only if persistent.
6. Remember actual incident recovered without production changes; avoid speculative transport rewrites.

## Recorder error and storage

Observed exception: SQLite `database or disk is full`, then SQLAlchemy `PendingRollbackError`. Do not conclude root cause solely from disk percent. Inspect filesystem/quota/container overlay, inode use, temp paths and active SQLite WAL.

```bash
df -h / /tmp /workspaces/home-assistant-core/config
df -i / /workspaces/home-assistant-core/config
du -sh /tmp /workspaces/home-assistant-core/config
ls -lhS /workspaces/home-assistant-core/config/home-assistant_v2.db* \
        /workspaces/home-assistant-core/config/home-assistant.log* 2>/dev/null
grep -ciE 'database or disk is full|PendingRollbackError' \
  /workspaces/home-assistant-core/config/home-assistant.log
```

| Measurement | Incident follow-up | 2026-10-10 (HA stopped) |
|---|---|---|
| Overlay `/` | 29G total, 2.2G free (92%) | 29G total, 4.2G free (85%) |
| Workspace `/dev/sda8` | 361G total, 14G free (96%) | 361G total, 32G free (91%) |
| Inodes | Not near exhaustion | 21% overlay / 5% workspace |
| DB / WAL | ~150M / ~2.5M | 150M / 4.0M |
| Disk-full errors in current log | — | 0 |

These are historic values, not current guarantees. **Do not delete** SQLite `-wal` or `-shm` files while HA is running. Avoid destructive Docker pruning or DB deletion as first response. For development, a `recorder` purge retention setting may be appropriate but does not instantly free host storage; verify backup and safe database lifecycle before any repair. Re-check fresh log errors after restart.

## Runtime restart

```bash
# Stop running process with Ctrl+C, then:
cd /workspaces/home-assistant-core
/home/vscode/.local/ha-venv/bin/python -m homeassistant -c ./config
```

A standard custom-integration warning ('not tested by Home Assistant') is not evidence of malfunction. A `go2rtc` default-config startup error was observed historically and is not necessarily Rain Bird related.

## Incident capture checklist

Start with **Download diagnostics** on the Rain Bird IQ4 entry (credentials, local address, MAC, location and site name are redacted). Capture timestamps, HA version, entry/controller ID, affected entity ID and attributes, relevant local realtime and slow logs, any action call with its response or error key, HA config logger level, OS/container disk metrics and whether app/HA/standalone diagnostic were concurrently connected. Redact credentials and internal/private addresses before public reporting.

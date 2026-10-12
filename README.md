# Rain Bird IQ4 for Home Assistant

A Home Assistant custom integration for **Rain Bird IQ4**-connected irrigation
controllers. It shows each controller's live watering state, rain sensor and rain delay,
its stations and programs, and lets administrators **start a station for a set time or
stop watering** — with safety checks before every start.

It combines two sources:

- the **IQ4 cloud** for controller, station and program configuration (names, which
  stations are enabled, program schedules and run times), and
- the controller's **local network interface** for live state and for start/stop, so
  status is fast and stopping works even when the cloud is down.

> Not affiliated with or endorsed by Rain Bird. The IQ4 cloud and local protocol details
> it relies on were observed, not documented by Rain Bird, and could change.

## Supported devices

Rain Bird controllers connected to the IQ4 cloud that are reachable on your local
network. It has been tested with one controller on firmware **3.11.0**; other models and
firmware versions may behave differently — please report what you find.

## Requirements

- Home Assistant with the ability to install custom integrations.
- An IQ4 cloud account that can see the controller.
- For live state and control: the controller's **IP address or hostname** on your network
  and its **controller-local password** — the password set on the controller itself
  during provisioning (the six-digit PIN on Rain Bird 2.0 setups). This is **not** your
  IQ4 cloud password or your Wi-Fi password.

## Installation

**HACS (recommended):** HACS → ⋮ → *Custom repositories* → add
`https://github.com/solanix/rainbird-iq4` with type *Integration*. Then install
*Rain Bird IQ4* and restart Home Assistant.

**Manual:** copy `custom_components/rainbird_iq4` from this repository into your
configuration's `custom_components` folder and restart Home Assistant.

Either way, Home Assistant installs the
[`pyrainbird-iq4`](https://pypi.org/project/pyrainbird-iq4/) library automatically.
Requires Home Assistant 2026.10 or newer.

## Configuration

**Settings → Devices & services → Add integration → Rain Bird IQ4.**

| Step | Field | Description |
|---|---|---|
| Sign in | Username, Password | Your IQ4 cloud account. |
| Select controller | Controller | Shown only if the account has more than one. Add the integration again for each further controller. |

Then open the entry's **Configure** to enable local state and control:

| Option | Description |
|---|---|
| Controller IP address or hostname | The controller on your network. Leave empty to turn local polling and control off. |
| Controller-local PIN | The controller's own password (see Requirements). Leave empty when changing only the address to keep the stored PIN. |

Without local options the integration still shows cloud configuration, but no live state
and no start/stop. **Reconfigure** (entry ⋮ menu) changes the IQ4 account; if IQ4 rejects
the stored password, Home Assistant asks you to re-authenticate.

## What you get

One device per controller, with:

| Entity | Notes |
|---|---|
| **Irrigation state** | Idle, Running or Paused; *unknown* when the controller's answer is inconclusive. |
| **Active station**, **Active program**, **Remaining runtime**, **Queue zones remaining** | What is watering now. |
| **Rain sensor active** (Wet/Dry), **Rain delay** (days), **Irrigation enabled** | The controller's rain and on/off state. |
| **Program A/B/C…** | First start time, or *Not scheduled*; attributes list each station's run time. |
| **Start station** (select), **Start duration** (number, 1–30 min) | Choose what a dashboard Start button waters. Changing them never contacts the controller. |
| Diagnostic: firmware, station and program counts, program summary, *Controller connected*, per-station metadata | Under *Diagnostic* on the device page. |
| Diagnostic, disabled by default: per-station program run time | Enable individually if you want them. |

Stations disabled in IQ4 are never offered for starting.

### Actions (administrators only)

| Action | Fields |
|---|---|
| `rainbird_iq4.start_station` | `device_id` (controller), `station_id` (IQ4 station ID, shown on the station metadata sensor), `duration_minutes` (1–30) |
| `rainbird_iq4.stop_irrigation` | `device_id` |

Both return a response: `acknowledged` (the controller accepted the command), `verified`
(the integration then saw it take effect) and `no_op` (stop found nothing running and sent
nothing). Before every **start**, the integration re-reads the controller and refuses if it
is not idle, irrigation is off, the rain sensor or a rain delay is active or unknown, the
station is not enabled in IQ4, or the IQ4 cloud data is not current. **Stop** needs only
the local connection. Commands are sent once and never retried automatically.

### Dashboard card

A Lovelace card is included and loaded automatically — no resource to add. Add a card of
type `custom:rainbird-iq4-card`:

```yaml
type: custom:rainbird-iq4-card
profile: standard # simple | standard | advanced
```

It has Status, Control, Programs, Zones, History and Diagnostics views, and shows
start/stop outcomes honestly (including "acknowledged but not confirmed"). Options and
details: [dashboard/README.md](dashboard/README.md).

## Examples

Stop watering whenever the rain sensor trips:

```yaml
automation:
  - alias: Stop irrigation when it rains
    triggers:
      - trigger: state
        entity_id: binary_sensor.backyard_rain_sensor_active
        to: "on"
    actions:
      - action: rainbird_iq4.stop_irrigation
        data:
          device_id: YOUR_CONTROLLER_DEVICE_ID
```

Water one station and get notified if the start was not confirmed:

```yaml
script:
  water_front_lawn:
    sequence:
      - action: rainbird_iq4.start_station
        data:
          device_id: YOUR_CONTROLLER_DEVICE_ID
          station_id: 12345678
          duration_minutes: 10
        response_variable: result
      - if: "{{ not result.verified }}"
        then:
          - action: persistent_notification.create
            data:
              message: Front lawn start was not confirmed — check the controller.
```

Automations run without a user, so the admin-only check does not block them; restrict who
can edit automations accordingly. Replace entity IDs to match your controller's name.

## How data updates

| Source | Interval |
|---|---|
| IQ4 cloud (configuration) | every 5 minutes |
| Controller live state | every 30 s when idle, every 10 s while watering |
| Controller rain and on/off state | every 5 minutes |

After a failed local read the integration retries after 2 seconds, then backs off to
30/60/120 s. During brief controller outages the last good values stay visible (live state
up to 90 s, rain state up to 15 minutes) with their age shown; starts always re-read the
controller first. If the IQ4 cloud is down when Home Assistant starts, the integration
loads its last saved copy of the configuration so live state and **stop** keep working;
starts wait until the cloud is back.

## Known limitations

- Tested on one controller and firmware version.
- No program starts, pause/resume, schedule editing or rain-delay setting.
- Starting a station needs current IQ4 cloud data (to confirm the station is enabled).
- The IQ4 cloud sometimes blocks sign-in with a web firewall; the integration backs off and
  retries.
- The Rain Bird app or another IQ4 client can briefly occupy the controller's local
  connection, causing short gaps in live data.
- If a station is re-enabled in IQ4 after Home Assistant disabled its entity, enable the
  entity again manually.
- Queue and remaining-runtime data use a reverse-engineered command and may differ on other
  controller families.

## Troubleshooting

- **Re-authentication requested:** the IQ4 password changed — enter the new one.
- **Start refused:** the error says why (not idle, rain, cloud data not current, station
  not enabled…). Fix the condition; nothing was sent.
- **"The command may or may not have reached the controller":** do not retry blindly.
  Check the controller or Irrigation state, and stop watering from the Rain Bird app if
  needed.
- **Local entities unavailable:** check the controller's IP address and local PIN in
  *Configure*, and that Home Assistant can reach the controller on your network.
- **Report a problem:** attach **Download diagnostics** from the integration entry
  (credentials, addresses and location are redacted) to an issue on this repository.

## Removal

Delete the Rain Bird IQ4 entry under **Settings → Devices & services**; its devices,
entities and saved data are removed with it. Remove any dashboards or cards that used it,
then delete `custom_components/rainbird_iq4` (or uninstall it in HACS) and restart.

## Development

Developer setup, architecture and tests: [docs/](docs/README.md), starting with
[docs/development/DEVELOPER_SETUP.md](docs/development/DEVELOPER_SETUP.md).

## License

MIT

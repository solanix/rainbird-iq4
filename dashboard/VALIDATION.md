# Manual validation in dev HA

Evidence for the manual checks in the dashboard spec (`TEST_AND_ACCEPTANCE.md`). The
automated cases T01–T18 are covered by `test/` (`npm test`). Recorded 2026-10-11/12 on the
dev container instance; production HAOS was not touched.

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Dev, non-production target; HA version | Pass | Dev container `localhost:8123`, HA 2026.10.0.dev0. Card tested on a separate `dashboard-iq4` dashboard and in a page overlay; the existing Irrigation dashboard was not modified. |
| 2 | 320/375, 768, 1280+ px; light and dark | Pass | All six views at 320, 768 and 1000–1367 px in an overlay, and at 500 px (Chrome's minimum window) in HA's own mobile layout; light and dark themes. No horizontal overflow of the card; the tab strip and the Zones/History tables scroll inside their own containers. No screenshots archived. |
| 3 | Keyboard, focus, 44 px targets, screen reader | Partial | Tabs: click, Arrow keys, Home/End move selection and focus, off-screen tabs scroll into view, focus ring visible. Tabs, buttons, inputs, selects and summaries have `min-height: 44px` (buttons also `min-width`). **Screen-reader pass not done** (needs a person). |
| 4 | Read-only states: idle, active, local outage, cloud outage | Partial | Idle and local outage observed live (Status unknown, prominent Stop with warning, Start blocked with reasons, "unavailable for …"). Non-admin view shows "View only" and no confirmation path. **Active run and cloud outage not observed live** (covered by T02/T03). |
| 5 | No direct browser calls to controller or cloud | Pass | Source uses only `hass.callWS` and `hass.callService`; no `fetch`, XHR, WebSocket or URLs in `src/`. While exercising the admin form, a wrapper on `callWS`/`callService` recorded no service calls. |
| 6 | Free space and Recorder health | Pass (at check time) | `/home` 29 GB free; `home-assistant_v2.db` 77 MB, WAL 4 MB; no disk-full, rollback or recorder errors in the current log. Note: the host's separate `/tmp` partition (358 MB) filled once and was cleared. |
| 7 | Live Start/Stop | Not done | Requires explicit operator authorization and physical observation. Start was also blocked throughout by local data availability. |
| 8 | Production and existing dashboard untouched | Pass | Only the dev instance was used; `dashboard-irrigation` unchanged. |

## Defects found and fixed during validation

- Tab labels overlapped at 320 px: a global `button { min-width: 44px }` overrode flex
  sizing, so every tab shrank to 44 px. Tabs no longer shrink; the strip scrolls.
- Keyboard focus was lost after every tab switch: replacing `ha-card` on each render left
  its new contents unfocusable until Lit's slot rendered. `ha-card` is now created once.
- Zones hid unscheduled program membership (Station 001 showed "—" while Program C listed
  it). Zones now show it, muted, e.g. "B (not scheduled)".
- "Last local update: never" while local data was unavailable; now "unavailable for 3 min".

## Remaining

- Screen-reader pass and archived screenshots at the three widths.
- Admin flow up to the confirmation step once Start is not blocked by local data.
- Live Start/Stop with authorization and physical observation.

# Rain Bird IQ4 dashboard card

A Lovelace custom card, `custom:rainbird-iq4-card`, with six views — Status, Control,
Programs, Zones, History, Diagnostics — for the `rainbird_iq4` integration. It reads only
Home Assistant entities and calls only the integration's admin-only actions; it never
contacts the controller or the IQ4 cloud from the browser.

Specification: `../../dashboard/*.md` (handoff package). Data mapping: [INVENTORY.md](INVENTORY.md).

## Why a custom card instead of native cards

The spec prefers native cards. They cannot meet four requirements, so the MVP is one card:

1. **No hard-coded entity IDs.** IDs derive from the device name (`sensor.backyard_*`).
   The card discovers entities by unique ID through the entity registry.
2. **Controller scoping.** One selector scopes every view and action; switching clears the
   selected zone, confirmation and outcome (T17). Native cards have no shared scope.
3. **Honest outcomes.** `start_station`/`stop_irrigation` return `acknowledged` and
   `verified` separately. Native `perform-action` buttons discard responses, so they cannot
   show "acknowledged but not confirmed" (T11) or "outcome unknown" (T12).
4. **Freshness.** Local data older than 60 s (the backend's own start cutoff) is shown as
   stale with its age, never as Idle (T04).

It uses no third-party cards, no runtime npm dependencies and no build toolchain beyond Node's
standard library (TypeScript is a dev-only dependency for `npm run typecheck`). Manual
selections (zone, duration) are per browser tab, not the shared `select`/`number` entities,
so two people cannot change each other's pending start.

## Behaviour summary

- **Start** is offered only to admins, only with fresh local data confirming idle, irrigation
  enabled, rain sensor clear and rain delay 0, current cloud metadata, and only for zones that
  are `enabled == true` *and* on a terminal the controller reports present. The backend
  re-checks all of it; the UI is a hint, not a guard.
- **Stop** is offered to admins whenever local control is configured, including when cloud or
  local data is stale (with a warning).
- Every action needs an explicit confirmation naming controller, zone and duration; one
  confirmation sends at most one request; nothing is retried; Escape cancels.
- Programs are read-only. History shows runs observed from Recorder state changes, labelled
  as observations accurate to the poll interval, or "History unavailable" with the reason.

## Layout

```
src/model.js     pure data mapping, eligibility, outcome mapping, form reducer, history
src/view.js      pure HTML rendering (escaped), one function per view
src/strings.js   English strings, keyed for localization
src/styles.js    theme-variable CSS, 44 px targets, reduced-motion support
src/card.js      custom element: registry discovery, events, HA calls
scripts/build.mjs       bundles src/ into dist/rainbird-iq4-card.js
scripts/install-dev.sh  builds and copies into <config>/www/rainbird-iq4/
test/            node:test suites (model, view, element smoke tests with a fake hass)
dashboard.yaml   a separate dashboard containing the card
```

## Tests

```bash
cd ha-rainbird-iq4/dashboard
npm test          # node --test; Node 20+, no install step
npm install && npm run typecheck   # tsc --checkJs over src/ (jsconfig.json)
```

All tests are offline. The element tests load the built bundle with a minimal DOM shim and
a fake `hass`, and assert exactly which calls reach Home Assistant.

## Install on the dev instance

Development target only. Do not install on production HAOS without approval.

1. Build and copy the card (inside the dev container):
   ```bash
   cd /workspaces/ha-rainbird-iq4/dashboard
   scripts/install-dev.sh /workspaces/home-assistant-core/config
   ```
   If the script reports that `www/` was just created, restart Home Assistant once.
2. Register the resource: **Settings → Dashboards → ⋮ → Resources → Add resource**,
   URL `/local/rainbird-iq4/rainbird-iq4-card.js?v=0.1.0`, type **JavaScript module**.
   (The Resources menu needs **Advanced mode** in your user profile.)
3. Create a separate dashboard: **Settings → Dashboards → Add dashboard → New dashboard
   from scratch**, title "Irrigation (IQ4)". Open it, **⋮ → Edit dashboard → ⋮ → Raw
   configuration editor**, paste `dashboard.yaml`, save.

The existing Irrigation dashboard is not touched.

### Card options

| Option | Values | Default |
|---|---|---|
| `profile` | `simple` (Status, Control, Programs), `standard` (all six), `advanced` (all six + IDs) | `standard` |
| `controller` | HA device ID to pin; otherwise a selector appears for 2+ controllers | first controller |
| `default_view` | `status`, `control`, `programs`, `zones`, `history`, `diagnostics` | first in profile |
| `title` | header text | `Rain Bird IQ4` |

## Upgrade and cache busting

Bump `version` in `package.json` and `CARD_VERSION` in `src/card.js` together (a test
enforces it), rerun `install-dev.sh`, and change the resource URL's `?v=` to match. The
bundle is a single file so one versioned URL covers all of it.

## Rollback

1. Delete the "Irrigation (IQ4)" dashboard (Settings → Dashboards).
2. Remove the `/local/rainbird-iq4/...` resource.
3. Delete `<config>/www/rainbird-iq4/`.

Nothing in the integration depends on the card.

## Integration dependency

Start eligibility needs the `available_terminals` attribute on the *Irrigation enabled*
binary sensor (see INVENTORY.md). Without it, every zone shows "Terminal presence unknown"
and Start stays disabled; Stop and all read-only views still work.

## Not yet done

- Screenshots at 320/375, 768 and 1280+ px in light and dark themes, and a screen-reader pass,
  on the dev instance (Phase D4 manual checklist in the spec).
- Live start/stop through the card: requires explicit operator authorization and physical
  observation; never automated.
- Translations other than English.

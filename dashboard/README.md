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
scripts/build.mjs  bundles src/ into ../custom_components/rainbird_iq4/frontend/
test/            node:test suites (model, view, element smoke tests with a fake hass)
dashboard.yaml   a separate dashboard containing the card
```

## Tests

```bash
cd ha-rainbird-iq4/dashboard
node scripts/build.mjs   # rebuild the bundle the integration ships (commit it)
npm test          # node --test; Node 20+, no install step; fails if the bundle is stale
npm install && npm run typecheck   # tsc --checkJs over src/ (jsconfig.json)
```

All tests are offline. The element tests load the built bundle with a minimal DOM shim and
a fake `hass`, and assert exactly which calls reach Home Assistant.

## Install

The card ships with the integration. On startup the integration serves
`custom_components/rainbird_iq4/frontend/rainbird-iq4-card.js` and loads it on every
dashboard, so there is no resource to register and nothing to copy into `www/`.

To use it, add a card of type `custom:rainbird-iq4-card` to any dashboard, or create a
separate one: **Settings → Dashboards → Add dashboard → New dashboard from scratch**, open
it, **⋮ → Edit dashboard → ⋮ → Raw configuration editor**, paste `dashboard.yaml`, save.

### Card options

| Option | Values | Default |
|---|---|---|
| `profile` | `simple` (Status, Control, Programs), `standard` (all six), `advanced` (all six + IDs) | `standard` |
| `controller` | HA device ID to pin; otherwise a selector appears for 2+ controllers | first controller |
| `default_view` | `status`, `control`, `programs`, `zones`, `history`, `diagnostics` | first in profile |
| `title` | header text | `Rain Bird IQ4` |

## Upgrade and cache busting

Rebuild with `node scripts/build.mjs` and commit the bundle with the source change. The
integration puts a hash of the bundle in the card's URL, so browsers fetch the new file
after Home Assistant restarts. Bump `version` in `package.json` and `CARD_VERSION` in
`src/card.js` together for user-visible releases (a test enforces that they match).

## Removing the card

Delete any dashboards or cards that use it. The file is part of the integration, so it is
removed with the integration.

## Integration dependency

Start eligibility needs the `available_terminals` attribute on the *Irrigation enabled*
binary sensor (see INVENTORY.md). Without it, every zone shows "Terminal presence unknown"
and Start stays disabled; Stop and all read-only views still work.

## Validation

Manual checks in dev HA, defects found and what remains: [VALIDATION.md](VALIDATION.md).

## Not yet done

- A screen-reader pass and archived screenshots (the responsive and theme checks themselves
  are done; see VALIDATION.md).
- Live start/stop through the card: requires explicit operator authorization and physical
  observation; never automated.
- Translations other than English.

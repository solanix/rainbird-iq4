import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { buildControllerViews, deriveRuns, formReducer, initialForm } from "../src/model.js";
import { esc, formatAge, formatDuration, renderCard, tabsForProfile } from "../src/view.js";
import { NOW, buildFixture } from "./fixtures.js";

function ctx({ overrides, ids, isAdmin = true, tab = "status", profile = "standard", form, history } = {}) {
  const { registry, states, devices } = buildFixture(overrides, ids);
  const views = buildControllerViews(registry, { states, devices, now: NOW });
  const selected = views[0];
  return {
    config: { profile },
    lang: "en",
    isAdmin,
    now: NOW,
    views,
    selected,
    ui: {
      tab,
      form: form ?? initialForm(selected?.controllerKey),
      history: history ?? { status: "idle", runs: [] },
    },
  };
}
const html = (options) => renderCard(ctx(options));

describe("formatting", () => {
  test("durations and ages", () => {
    assert.equal(formatDuration(500), "8:20");
    assert.equal(formatDuration(3725), "1:02:05");
    assert.equal(formatDuration(null), "—");
    assert.equal(formatAge(10), "10 s");
    assert.equal(formatAge(600), "10 min");
    assert.equal(formatAge(null), null);
  });

  test("escapes markup in names", () => {
    assert.equal(esc(`<img src=x onerror="a">`), "&lt;img src=x onerror=&quot;a&quot;&gt;");
    const { registry, states, devices } = buildFixture({}, [2002]);
    devices["dev-back"].name = "<script>x</script>";
    const views = buildControllerViews(registry, { states, devices, now: NOW });
    const out = renderCard({ ...ctx({ ids: [2002] }), views, selected: views[0] });
    assert.ok(!out.includes("<script>x"));
    assert.ok(out.includes("&lt;script&gt;x"));
  });
});

describe("navigation", () => {
  test("profiles choose the visible views", () => {
    assert.deepEqual(tabsForProfile("simple"), ["status", "control", "programs"]);
    assert.equal(tabsForProfile("standard").length, 6);
    assert.equal(tabsForProfile("bogus").length, 3);
    const out = html({ profile: "standard" });
    for (const tab of ["Status", "Control", "Programs", "Zones", "History", "Diagnostics"])
      assert.match(out, new RegExp(`role="tab"[^>]*>${tab}<`));
  });

  test("a tab hidden by the profile falls back to the first tab", () => {
    const out = html({ profile: "simple", tab: "diagnostics" });
    assert.match(out, /aria-labelledby="tab-status"/);
  });

  test("one controller shows its name; two show a selector", () => {
    assert.ok(!html({ ids: [1001] }).includes('data-action="select-controller"'));
    assert.ok(html().includes('data-action="select-controller"'));
  });

  test("empty registry explains how to add the integration", () => {
    const out = renderCard({ ...ctx(), views: [], selected: null });
    assert.match(out, /No Rain Bird IQ4 controllers found/);
  });
});

describe("status view", () => {
  test("T01 idle is stated in text with a subdued Stop", () => {
    const out = html();
    assert.match(out, /Idle/);
    assert.match(out, /Nothing is running/);
    assert.match(out, /class="secondary"[^>]*data-kind="stop"/);
  });

  test("T02 running shows station, remaining and a prominent Stop", () => {
    const out = html({ overrides: { 1001: { irrigation: "running", activeStation: 501, remaining: 500 } } });
    assert.match(out, /Watering/);
    assert.match(out, /Front Lawn/);
    assert.match(out, /8:20/);
    assert.match(out, /class="danger big-button"[^>]*data-kind="stop"/);
  });

  test("T04 stale data is labelled with its age, never as idle", () => {
    const out = html({ overrides: { 1001: { localAge: 200 } } });
    assert.match(out, /Status unknown/);
    assert.match(out, /Local data is 3 min old; last reported Idle/);
    assert.match(out, /Local:<\/span> Stale/);
  });

  test("unavailable local data says how long, not never", () => {
    const out = html({ overrides: { 1001: { localUnavailable: true } } });
    assert.match(out, /Last local update<\/dt><dd class="stale">unavailable for 3 min/);
    assert.ok(!/<dd class="stale">never/.test(out));
  });

  test("T03 cloud offline is shown separately from local", () => {
    const out = html({ overrides: { 1001: { cloud: "off" } } });
    assert.match(out, /Cloud:<\/span> Offline/);
    assert.match(out, /Local:<\/span> Connected/);
  });
});

describe("control view", () => {
  test("T05–T07 only enabled, present stations are offered", () => {
    const out = html({ tab: "control" });
    const options = [...out.matchAll(/<option value="(\d+)"/g)].map((m) => m[1]);
    assert.deepEqual(options, ["501", "502"]);
  });

  test("T13 non-admins see why controls are unavailable", () => {
    const out = html({ tab: "control", isAdmin: false });
    assert.match(out, /Administrator permission is required/);
    assert.ok(!out.includes('data-kind="stop"'));
    assert.match(out, /data-action="select-station"[^>]*disabled/);
  });

  test("blocked start lists every reason", () => {
    const out = html({ tab: "control", overrides: { 1001: { rainSensor: "on", rainDelay: 2 } } });
    assert.match(out, /The rain sensor is active/);
    assert.match(out, /A rain delay is active/);
    assert.match(out, /data-key="review-start" disabled/);
  });

  test("confirmation names controller, zone and duration", () => {
    let form = initialForm("dev-front");
    form = formReducer(form, { type: "select_station", stationId: "502" });
    form = formReducer(form, { type: "set_duration", value: 12 });
    form = formReducer(form, { type: "request_confirm", kind: "start" });
    const out = html({ tab: "control", form });
    assert.match(out, /Start Back Beds on Backyard for 12 minutes\?/);
    assert.match(out, /data-action="submit" data-kind="start"/);
  });

  test("pending shows progress and removes the submit button", () => {
    let form = initialForm("dev-front");
    form = formReducer(form, { type: "select_station", stationId: "501" });
    form = formReducer(form, { type: "request_confirm", kind: "start" });
    form = formReducer(form, { type: "submit", kind: "start" });
    const out = html({ tab: "control", form });
    assert.match(out, /Sending start/);
    assert.ok(!out.includes('data-action="submit"'));
    assert.match(out, /data-action="select-controller" data-key="controller-select" disabled/);
  });

  test("T11 unconfirmed outcome offers refresh, not resend", () => {
    const form = { ...initialForm("dev-front"), outcome: { kind: "start", outcome: "unconfirmed" } };
    const out = html({ tab: "control", form });
    assert.match(out, /state not confirmed yet/);
    assert.match(out, /data-action="refresh"/);
    assert.ok(!out.includes('data-action="submit"'));
  });

  test("T12 unknown stop outcome warns to check the controller", () => {
    const form = { ...initialForm("dev-front"), outcome: { kind: "stop", outcome: "unknown" } };
    assert.match(html({ tab: "control", form }), /Stop outcome unknown/);
  });

  test("Stop stays available when local data is stale, with a warning", () => {
    const out = html({ tab: "control", overrides: { 1001: { localAge: 500 } } });
    assert.match(out, /data-kind="stop"/);
    assert.match(out, /the controller may not receive the stop/);
  });
});

describe("zones and programs", () => {
  test("disabled and unknown zones are listed with their reason", () => {
    const out = html({ tab: "zones" });
    assert.match(out, /Drip Line/);
    assert.match(out, /Enabled state unknown/);
    assert.match(out, /Terminal not present/);
  });

  test("a registry-disabled metadata entity is unknown, not assumed disabled", () => {
    const out = html({ tab: "zones" });
    assert.match(out, /Drip Line<br><span class="muted small">metadata entity disabled in Home Assistant/);
  });

  test("a disabled station whose entity the user enabled reads Disabled", () => {
    const { registry, states, devices } = buildFixture({}, [1001]);
    const entry = registry.find((e) => e.unique_id === "1001_station_503");
    entry.disabled_by = null;
    states[entry.entity_id] = {
      entity_id: entry.entity_id,
      state: "0",
      attributes: { station_id: 503, station_name: "Drip Line", station_enabled: false, terminal: 3 },
    };
    const views = buildControllerViews(registry, { states, devices, now: NOW });
    const out = renderCard({ ...ctx({ ids: [1001], tab: "zones" }), views, selected: views[0] });
    assert.match(out, /Drip Line<\/th>\s*<td>3<\/td>\s*<td>Disabled<\/td>\s*<td>Disabled in IQ4/);
  });

  test("zones list unscheduled program membership distinctly", () => {
    const out = html({ tab: "zones" });
    assert.match(out, /Front Lawn<\/th>[\s\S]*?<td>Morning<\/td>/);
    assert.match(out, /Orchard<\/th>[\s\S]*?<td><span class="muted">Spare \(not scheduled\)<\/span><\/td>/);
  });

  test("zones fall back to effective programs when references are absent", () => {
    const { registry, states, devices } = buildFixture({}, [1001]);
    for (const state of Object.values(states)) delete state.attributes.program_references;
    const views = buildControllerViews(registry, { states, devices, now: NOW });
    const out = renderCard({ ...ctx({ ids: [1001], tab: "zones" }), views, selected: views[0] });
    assert.match(out, /Front Lawn<\/th>[\s\S]*?<td>Morning<\/td>/);
    assert.ok(!out.includes("Spare"));
  });

  test("advanced profile adds stable station IDs", () => {
    assert.ok(!html({ tab: "zones" }).includes("<code>501</code>"));
    assert.ok(html({ tab: "zones", profile: "advanced" }).includes("<code>501</code>"));
  });

  test("programs are read-only with no start control", () => {
    const out = html({ tab: "programs" });
    assert.match(out, /Starts at 05:30/);
    assert.match(out, /Not scheduled/);
    assert.match(out, /Read-only/);
    assert.ok(!/data-action="(submit|confirm)"[^>]*program/i.test(out));
  });
});

describe("history", () => {
  const row = (s, lu, a) => ({ s, lu, ...(a ? { a } : {}) });
  const t0 = NOW / 1000 - 3600;

  test("derives observed runs and marks lost contact", () => {
    const runs = deriveRuns(
      [
        row("Idle", t0),
        row("Front Lawn", t0 + 60, { station_id: 501 }),
        row("Front Lawn", t0 + 90, { station_id: 501 }),
        row("Back Beds", t0 + 360, { station_id: 502 }),
        row("unavailable", t0 + 600),
        row("Idle", t0 + 900),
        row("Front Lawn", t0 + 1200, { station_id: 501 }),
      ],
      { now: NOW },
    );
    assert.deepEqual(
      runs.map((r) => [r.stationId, r.durationSeconds, r.ongoing, r.endUnknown]),
      [
        ["501", 3600 - 1200, true, false],
        ["502", 240, false, true],
        ["501", 300, false, false],
      ],
    );
  });

  test("T15 no recorded runs renders an honest empty state", () => {
    assert.deepEqual(deriveRuns([row("Idle", t0)], { now: NOW }), []);
    const out = html({ tab: "history", history: { status: "ready", runs: [] } });
    assert.match(out, /No runs observed in this period/);
  });

  test("T18 recorder failure is reported, not fabricated", () => {
    const out = html({
      tab: "history",
      history: { status: "unavailable", runs: [], reason: "Home Assistant's history could not be read (x)." },
    });
    assert.match(out, /History unavailable: Home Assistant&#39;s history could not be read/);
    assert.ok(!out.includes("<tbody>"));
  });

  test("explains that times are observations, not controller records", () => {
    assert.match(html({ tab: "history" }), /not controller-confirmed run times/);
  });
});

describe("diagnostics", () => {
  test("shows freshness and terminals, no credentials", () => {
    const out = html({ tab: "diagnostics" });
    assert.match(out, /Terminals present<\/dt><dd>1, 2, 3, 4/);
    assert.match(out, /Poll interval<\/dt><dd>30 s/);
    assert.ok(!/password|token|local_host/i.test(out));
  });
});

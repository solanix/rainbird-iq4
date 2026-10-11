import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildControllerViews,
  formReducer,
  initialForm,
  interpretActionResult,
  parseUniqueId,
  startEligibility,
  startableStations,
  stationBlockReason,
  stopEligibility,
  validateDuration,
} from "../src/model.js";
import { NOW, buildFixture } from "./fixtures.js";

function views(overrides, ids) {
  const { registry, states, devices } = buildFixture(overrides, ids);
  return buildControllerViews(registry, { states, devices, now: NOW });
}
const byId = (list, id) => list.find((v) => v.controllerId === String(id));
const admin = { isAdmin: true };

describe("registry discovery", () => {
  test("classifies every unique ID shape the integration creates", () => {
    assert.deepEqual(parseUniqueId("1001_connected"), { controllerId: "1001", role: "connected" });
    assert.deepEqual(parseUniqueId("1001_station_501"), {
      controllerId: "1001",
      role: "station",
      stationId: "501",
    });
    assert.deepEqual(parseUniqueId("1001_station_501_program_71_runtime"), {
      controllerId: "1001",
      role: "station_program_runtime",
      stationId: "501",
      programId: "71",
    });
    assert.deepEqual(parseUniqueId("1001_program_71"), {
      controllerId: "1001",
      role: "program",
      programId: "71",
    });
    assert.equal(parseUniqueId("1001_something_new"), null);
    assert.equal(parseUniqueId("not-an-id"), null);
  });

  test("groups by controller, binds device IDs and ignores other platforms", () => {
    const list = views();
    assert.deepEqual(
      list.map((v) => [v.controllerId, v.controllerKey, v.name]),
      [
        ["1001", "dev-front", "Backyard"],
        ["2002", "dev-back", "Annex"],
      ],
    );
  });

  test("prefers the user's device rename", () => {
    const { registry, states, devices } = buildFixture({}, [1001]);
    devices["dev-front"].name_by_user = "Front yard";
    const [view] = buildControllerViews(registry, { states, devices, now: NOW });
    assert.equal(view.name, "Front yard");
  });
});

describe("status", () => {
  test("T01 fresh idle local status allows start for an admin", () => {
    const view = byId(views(), 1001);
    assert.equal(view.local.state, "online");
    assert.equal(view.irrigation.state, "idle");
    assert.deepEqual(startEligibility(view, admin), { allowed: true, reasons: [] });
  });

  test("T02 active run resolves the stable station ID and keeps Stop offered", () => {
    const view = byId(views({ 1001: { irrigation: "running", activeStation: 502, remaining: 420 } }), 1001);
    assert.equal(view.irrigation.state, "running");
    assert.equal(view.irrigation.activeStationId, "502");
    assert.equal(view.irrigation.activeStationName, "Back Beds");
    assert.equal(view.irrigation.activeProgram, "Manual");
    assert.equal(view.irrigation.remainingSeconds, 420);
    assert.equal(view.irrigation.remainingIsEstimate, false);
    assert.equal(stopEligibility(view, admin).allowed, true);
    assert.ok(startEligibility(view, admin).reasons.includes("controller_busy"));
  });

  test("T03 cloud offline with local online keeps local status and Stop", () => {
    const view = byId(views({ 1001: { cloud: "off" } }), 1001);
    assert.equal(view.cloud.state, "offline");
    assert.equal(view.local.state, "online");
    assert.equal(view.irrigation.state, "idle");
    const stop = stopEligibility(view, admin);
    assert.equal(stop.allowed, true);
    assert.equal(stop.localDegraded, false);
    assert.ok(startEligibility(view, admin).reasons.includes("cloud_metadata_unavailable"));
  });

  test("T04 stale local data never shows idle and blocks start", () => {
    const view = byId(views({ 1001: { localAge: 61 } }), 1001);
    assert.equal(view.local.state, "stale");
    assert.equal(view.local.ageSeconds, 61);
    assert.equal(view.irrigation.state, "unknown");
    assert.equal(view.irrigation.lastReported, "idle");
    assert.ok(startEligibility(view, admin).reasons.includes("local_not_fresh"));
  });

  test("T04 unavailable local data is offline, start blocked, stop still offered", () => {
    const view = byId(views({ 1001: { localUnavailable: true } }), 1001);
    assert.equal(view.local.state, "offline");
    assert.equal(view.irrigation.state, "unknown");
    assert.equal(startEligibility(view, admin).allowed, false);
    const stop = stopEligibility(view, admin);
    assert.equal(stop.allowed, true);
    assert.equal(stop.localDegraded, true);
  });

  test("a stale running snapshot does not claim watering", () => {
    const view = byId(views({ 1001: { irrigation: "running", activeStation: 501, localAge: 300 } }), 1001);
    assert.equal(view.irrigation.state, "unknown");
    assert.equal(view.irrigation.activeStationId, null);
    assert.equal(view.irrigation.remainingSeconds, null);
  });

  test("no local connection means no control at all", () => {
    const view = byId(views({ 1001: { localConfigured: false } }), 1001);
    assert.equal(view.localConfigured, false);
    assert.equal(view.local.state, "not_configured");
    assert.deepEqual(stopEligibility(view, admin).reasons, ["local_not_configured"]);
  });

  test("rain sensor, rain delay and unknown rain each block start", () => {
    const reasons = (o) => startEligibility(byId(views({ 1001: o }), 1001), admin).reasons;
    assert.ok(reasons({ rainSensor: "on" }).includes("rain_sensor_active"));
    assert.ok(reasons({ rainDelay: 2 }).includes("rain_delay_active"));
    assert.ok(reasons({ rainSensor: "unavailable" }).includes("rain_state_unknown"));
    assert.ok(reasons({ irrigationEnabled: "off" }).includes("irrigation_not_enabled"));
  });
});

describe("stations", () => {
  test("T05 disabled stations stay visible but are never startable", () => {
    const view = byId(views(), 1001);
    const drip = view.stations.find((s) => s.stationId === "503");
    assert.equal(drip.displayName, "Drip Line");
    assert.equal(drip.metadataDisabledInHa, true);
    assert.notEqual(stationBlockReason(drip), null);
    assert.ok(!startableStations(view).some((s) => s.stationId === "503"));
  });

  test("T06 unknown enablement is visible as unknown and excluded", () => {
    const view = byId(views(), 1001);
    const side = view.stations.find((s) => s.stationId === "504");
    assert.equal(side.enabled, null);
    assert.equal(stationBlockReason(side), "station_enabled_unknown");
    assert.ok(!startableStations(view).some((s) => s.stationId === "504"));
  });

  test("T07 a terminal the controller does not report is excluded", () => {
    const view = byId(views(), 1001);
    const orchard = view.stations.find((s) => s.stationId === "505");
    assert.equal(orchard.enabled, true);
    assert.equal(orchard.physicallyAvailable, false);
    assert.equal(stationBlockReason(orchard), "terminal_not_present");
    assert.deepEqual(
      startableStations(view).map((s) => s.stationId),
      ["501", "502"],
    );
  });

  test("T07 without terminal telemetry nothing is startable", () => {
    const view = byId(views({ 1001: { availableTerminals: undefined } }), 1001);
    assert.equal(view.availableTerminals, null);
    assert.deepEqual(startableStations(view), []);
    assert.equal(stationBlockReason(view.stations[0]), "terminal_unknown");
    assert.ok(startEligibility(view, admin).reasons.includes("no_startable_stations"));
  });

  test("T08 same zone name on two controllers keeps separate identities", () => {
    const list = views();
    const front = startableStations(byId(list, 1001)).find((s) => s.displayName === "Front Lawn");
    const annex = startableStations(byId(list, 2002)).find((s) => s.displayName === "Front Lawn");
    assert.equal(front.stationId, "501");
    assert.equal(annex.stationId, "901");
    assert.equal(byId(list, 1001).controllerKey, "dev-front");
    assert.equal(byId(list, 2002).controllerKey, "dev-back");
  });

  test("T16 a rename changes the label but not the identity", () => {
    const { registry, states, devices } = buildFixture({}, [1001]);
    const entity = registry.find((e) => e.unique_id === "1001_station_501").entity_id;
    states[entity].attributes.station_name = "Front Lawn North";
    const [view] = buildControllerViews(registry, { states, devices, now: NOW });
    const station = view.stations.find((s) => s.stationId === "501");
    assert.equal(station.displayName, "Front Lawn North");
    assert.equal(station.terminal, 1);
  });
});

describe("programs", () => {
  test("lists scheduled and unscheduled programs distinctly", () => {
    const view = byId(views(), 1001);
    const morning = view.programs.find((p) => p.programId === "71");
    const spare = view.programs.find((p) => p.programId === "72");
    assert.equal(morning.scheduled, true);
    assert.deepEqual(morning.startTimes, ["05:30"]);
    assert.equal(morning.stationRuntimes.length, 2);
    assert.equal(spare.scheduled, false);
  });
});

describe("permissions", () => {
  test("T13 non-admins get read-only affordances", () => {
    const view = byId(views(), 1001);
    assert.ok(startEligibility(view, { isAdmin: false }).reasons.includes("not_admin"));
    assert.equal(stopEligibility(view, { isAdmin: false }).allowed, false);
  });
});

describe("duration", () => {
  test("T09 accepts whole minutes 1–30 only", () => {
    for (const ok of [1, 5, 30, "12"]) assert.equal(validateDuration(ok), Number(ok));
    for (const bad of [0, 31, -1, 2.5, "2.5", "", null, undefined, true, NaN, "abc"])
      assert.equal(validateDuration(bad), null, `rejects ${String(bad)}`);
  });

  test("T09 the form refuses invalid values instead of rounding them", () => {
    let form = initialForm("dev-front");
    for (const bad of [0, 31, 2.5]) form = formReducer(form, { type: "set_duration", value: bad });
    assert.equal(form.duration, 5);
    form = formReducer(form, { type: "set_duration", value: 12 });
    assert.equal(form.duration, 12);
  });
});

describe("control form", () => {
  const confirmed = () => {
    let form = initialForm("dev-front");
    form = formReducer(form, { type: "select_station", stationId: "501" });
    return formReducer(form, { type: "request_confirm", kind: "start" });
  };

  test("start needs a station before confirmation", () => {
    const form = formReducer(initialForm("dev-front"), { type: "request_confirm", kind: "start" });
    assert.equal(form.confirming, null);
  });

  test("T10 a double tap submits at most one request", () => {
    let form = confirmed();
    const first = formReducer(form, { type: "submit", kind: "start" });
    assert.equal(first.pending, "start");
    const second = formReducer(first, { type: "submit", kind: "start" });
    assert.equal(second, first, "second tap is a no-op while pending");
    // Without a fresh confirmation, a later tap cannot submit either.
    const settled = formReducer(second, {
      type: "settle",
      kind: "start",
      result: { outcome: "verified" },
    });
    assert.equal(formReducer(settled, { type: "submit", kind: "start" }), settled);
  });

  test("pending blocks edits, controller switches and new confirmations", () => {
    const pending = formReducer(confirmed(), { type: "submit", kind: "start" });
    for (const event of [
      { type: "select_controller", controllerKey: "dev-back" },
      { type: "select_station", stationId: "502" },
      { type: "set_duration", value: 9 },
      { type: "request_confirm", kind: "stop" },
    ])
      assert.equal(formReducer(pending, event), pending, event.type);
  });

  test("T17 switching controller resets station, confirmation and outcome", () => {
    let form = confirmed();
    form = formReducer(form, { type: "set_duration", value: 12 });
    form = formReducer(form, { type: "request_confirm", kind: "start" });
    const switched = formReducer(form, { type: "select_controller", controllerKey: "dev-back" });
    assert.deepEqual(switched, initialForm("dev-back"));
  });

  test("settle records the outcome against the submitted action only", () => {
    const pending = formReducer(confirmed(), { type: "submit", kind: "start" });
    assert.equal(formReducer(pending, { type: "settle", kind: "stop", result: {} }), pending);
    const done = formReducer(pending, { type: "settle", kind: "start", result: { outcome: "unconfirmed" } });
    assert.equal(done.pending, null);
    assert.deepEqual(done.outcome, { kind: "start", outcome: "unconfirmed" });
  });
});

describe("action outcomes", () => {
  const ok = (r) => ({ response: { response: r } });

  test("verified acknowledgement is the only success", () => {
    assert.deepEqual(interpretActionResult("start", ok({ acknowledged: true, verified: true })), {
      outcome: "verified",
    });
  });

  test("T11 acknowledged but unverified is reported as unconfirmed", () => {
    assert.equal(
      interpretActionResult("start", ok({ acknowledged: true, verified: false })).outcome,
      "unconfirmed",
    );
  });

  test("T12 ambiguous writes and transport failures are unknown", () => {
    const ambiguous = { error: { code: "home_assistant_error", translation_key: "write_outcome_ambiguous" } };
    assert.equal(interpretActionResult("start", ambiguous).outcome, "unknown");
    assert.equal(interpretActionResult("stop", { error: { code: 3, message: "Connection lost" } }).outcome, "unknown");
  });

  test("preflight rejections keep their translation key", () => {
    const rejected = {
      error: { code: "service_validation_error", translation_key: "rain_sensor_active", message: "Rain" },
    };
    assert.deepEqual(interpretActionResult("start", rejected), {
      outcome: "rejected",
      code: "rain_sensor_active",
      message: "Rain",
    });
  });

  test("T13 authorization errors map to permission denied", () => {
    assert.equal(interpretActionResult("stop", { error: { code: "unauthorized" } }).outcome, "permission_denied");
  });

  test("stop on a confirmed-idle controller is already stopped", () => {
    assert.equal(
      interpretActionResult("stop", ok({ acknowledged: false, verified: true, no_op: true })).outcome,
      "already_stopped",
    );
  });

  test("accepts an unwrapped response object", () => {
    assert.equal(
      interpretActionResult("stop", { response: { acknowledged: true, verified: true } }).outcome,
      "verified",
    );
  });
});

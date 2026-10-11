// Smoke tests of the real custom element against a fake `hass`, using a minimal DOM
// shim. They cover the wiring rules that pure tests cannot: what is sent to Home
// Assistant, and when.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { before, describe, test } from "node:test";

import { bundle } from "../scripts/build.mjs";
import { buildFixture } from "./fixtures.js";

class FakeShadowRoot {
  activeElement = null;
  haCard = null;
  addEventListener() {}
  removeEventListener() {}
  set innerHTML(html) {
    this.haCard = html.includes("<ha-card>") ? { innerHTML: "" } : null;
  }
  querySelector(selector) {
    return selector === "ha-card" ? this.haCard : null;
  }
}

before(() => {
  const registry = new Map();
  globalThis.HTMLElement = class {
    attachShadow() {
      this.shadowRoot = new FakeShadowRoot();
      return this.shadowRoot;
    }
    get isConnected() {
      return false;
    }
  };
  globalThis.customElements = {
    get: (name) => registry.get(name),
    define: (name, cls) => registry.set(name, cls),
  };
  globalThis.window = globalThis;
  globalThis.CSS = { escape: (s) => s };
  console.info = () => {};
  // Load the shipped bundle, not the sources, so the build is exercised too.
  new Function(bundle())();
});

function fakeHass({ isAdmin = true, overrides = {}, respond } = {}) {
  const { registry, states, devices } = buildFixture(overrides, undefined, Date.now());
  const calls = [];
  return {
    calls,
    states,
    devices,
    user: { is_admin: isAdmin },
    locale: { language: "en" },
    connection: { subscribeEvents: async () => () => {} },
    async callWS(msg) {
      calls.push(msg);
      if (msg.type === "config/entity_registry/list") return registry;
      if (msg.type === "call_service") return respond ? respond(msg) : { response: { acknowledged: true, verified: true } };
      throw new Error(`unexpected ${msg.type}`);
    },
    async callService(domain, service, data) {
      calls.push({ type: "callService", domain, service, data });
    },
  };
}

async function mount(hassOptions, config = { profile: "standard" }) {
  const Card = customElements.get("rainbird-iq4-card");
  const card = new Card();
  card.setConfig(config);
  const hass = fakeHass(hassOptions);
  card.hass = hass;
  await new Promise((r) => setImmediate(r));
  return { card, hass };
}

const serviceCalls = (hass) => hass.calls.filter((c) => c.type === "call_service" || c.type === "callService");

describe("card element", () => {
  test("registers itself for the card picker", () => {
    assert.ok(customElements.get("rainbird-iq4-card"));
    assert.ok(window.customCards.some((c) => c.type === "rainbird-iq4-card"));
  });

  test("rejects invalid configuration", () => {
    const Card = customElements.get("rainbird-iq4-card");
    assert.throws(() => new Card().setConfig({ profile: "expert" }), /profile/);
    assert.throws(() => new Card().setConfig({ controller: 5 }), /device ID/);
  });

  test("T14 loading, re-rendering and switching tabs or controllers sends no command", async () => {
    const { card, hass } = await mount();
    assert.match(card.shadowRoot.haCard.innerHTML, /Backyard/);
    for (const tab of ["control", "programs", "zones", "diagnostics", "status"]) card._setTab(tab);
    card._selectedKey = "dev-back";
    card.hass = hass;
    card.hass = hass;
    assert.deepEqual(serviceCalls(hass), []);
    assert.deepEqual(
      hass.calls.map((c) => c.type),
      ["config/entity_registry/list"],
    );
  });

  test("T10 double tap sends exactly one start with stable IDs", async () => {
    let release;
    const gate = new Promise((r) => (release = r));
    const { card, hass } = await mount({
      respond: async () => {
        await gate;
        return { response: { acknowledged: true, verified: false } };
      },
    });
    card._dispatch({ type: "select_station", stationId: "502" });
    card._dispatch({ type: "set_duration", value: 7 });
    card._requestConfirm("start");
    const first = card._submit("start");
    const second = card._submit("start");
    release();
    await Promise.all([first, second]);
    const sent = serviceCalls(hass);
    assert.equal(sent.length, 1);
    assert.deepEqual(sent[0], {
      type: "call_service",
      domain: "rainbird_iq4",
      service: "start_station",
      service_data: { device_id: "dev-front", station_id: 502, duration_minutes: 7 },
      return_response: true,
    });
    assert.equal(card._form.outcome.outcome, "unconfirmed");
    assert.match(card.shadowRoot.haCard.innerHTML, /state not confirmed yet/);
  });

  test("T12 a failed call is reported as unknown and never retried", async () => {
    const { card, hass } = await mount({
      respond: async () => {
        throw { code: "home_assistant_error", translation_key: "write_outcome_ambiguous" };
      },
    });
    card._requestConfirm("stop");
    await card._submit("stop");
    assert.equal(serviceCalls(hass).length, 1);
    assert.equal(card._form.outcome.outcome, "unknown");
  });

  test("submit without a confirmation sends nothing", async () => {
    const { card, hass } = await mount();
    card._dispatch({ type: "select_station", stationId: "501" });
    await card._submit("start");
    assert.deepEqual(serviceCalls(hass), []);
  });

  test("T13 a non-admin cannot reach confirmation", async () => {
    const { card, hass } = await mount({ isAdmin: false });
    card._dispatch({ type: "select_station", stationId: "501" });
    card._requestConfirm("start");
    card._requestConfirm("stop");
    assert.equal(card._form.confirming, null);
    await card._submit("stop");
    assert.deepEqual(serviceCalls(hass), []);
  });

  test("T08/T17 stop targets the selected controller after a switch", async () => {
    const { card, hass } = await mount();
    card._dispatch({ type: "select_station", stationId: "501" });
    card._requestConfirm("start");
    card._selectedKey = "dev-back";
    card._render();
    assert.equal(card._form.controllerKey, "dev-back");
    assert.equal(card._form.stationId, null);
    assert.equal(card._form.confirming, null);
    card._requestConfirm("stop");
    await card._submit("stop");
    assert.deepEqual(serviceCalls(hass)[0].service_data, { device_id: "dev-back" });
  });

  test("bundle version matches package.json", () => {
    const { version } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url)));
    assert.match(bundle(), new RegExp(`CARD_VERSION = "${version.replace(/\./g, "\\.")}"`));
  });
});

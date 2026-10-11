// Deterministic HA registry/state fixtures shaped like the integration's real output
// (unique IDs from entity.py, attributes from sensor.py/binary_sensor.py).
// Two controllers deliberately share a zone name to exercise identity isolation.

export const NOW = Date.parse("2026-10-09T12:00:00Z");
export const secondsAgo = (s, now = NOW) => new Date(now - s * 1000).toISOString();

const CONTROLLERS = {
  1001: {
    deviceId: "dev-front",
    slug: "backyard",
    name: "Backyard",
    stations: [
      { id: 501, name: "Front Lawn", terminal: 1, enabled: true },
      { id: 502, name: "Back Beds", terminal: 2, enabled: true },
      { id: 503, name: "Drip Line", terminal: 3, enabled: false },
      { id: 504, name: "Side Yard", terminal: 4, enabled: null },
      { id: 505, name: "Orchard", terminal: 9, enabled: true },
    ],
    programs: [
      { id: 71, name: "Morning", times: ["05:30"], stations: [501, 502] },
      { id: 72, name: "Spare", times: [], stations: [505] },
    ],
  },
  2002: {
    deviceId: "dev-back",
    slug: "annex",
    name: "Annex",
    stations: [{ id: 901, name: "Front Lawn", terminal: 1, enabled: true }],
    programs: [],
  },
};

function entry(controllerId, key, entityId, extra = {}) {
  return {
    entity_id: entityId,
    unique_id: `${controllerId}_${key}`,
    platform: "rainbird_iq4",
    device_id: CONTROLLERS[controllerId].deviceId,
    disabled_by: null,
    original_name: null,
    ...extra,
  };
}

/**
 * Build {registry, states, devices} for the given controllers.
 * `overrides[controllerId]` tweaks the live picture:
 *   irrigation ("idle"|"running"|...), localAge (s), localUnavailable, cloud ("on"|"off"|"unavailable"),
 *   rainSensor ("on"|"off"|"unavailable"), rainDelay (number|"unavailable"), irrigationEnabled,
 *   availableTerminals (array|undefined to omit), activeStation (station id), remaining (s),
 *   localConfigured (default true)
 */
export function buildFixture(overrides = {}, ids = [1001, 2002], now = NOW) {
  const registry = [];
  const states = {};
  const devices = {};
  for (const id of ids) {
    const c = CONTROLLERS[id];
    const o = {
      irrigation: "idle",
      localAge: 5,
      cloud: "on",
      rainSensor: "off",
      rainDelay: 0,
      irrigationEnabled: "on",
      availableTerminals: [1, 2, 3, 4],
      localConfigured: true,
      ...overrides[id],
    };
    devices[c.deviceId] = { id: c.deviceId, name: c.name, name_by_user: null };
    const base = { controller_id: id, site_id: 1, site_name: "Site" };
    const localBase = {
      ...base,
      last_successful_update: secondsAgo(o.localAge, now),
      consecutive_failures: 0,
      poll_interval_seconds: o.irrigation === "running" ? 10 : 30,
    };
    const add = (key, entityId, state, attributes = {}, extra = {}) => {
      registry.push(entry(id, key, entityId, extra));
      if (state !== undefined) states[entityId] = { entity_id: entityId, state, attributes };
    };
    const p = c.slug;
    add("connected", `binary_sensor.${p}_controller_connected`, o.cloud, { ...base, stale: false });
    add("firmware_version", `sensor.${p}_firmware_version`, "4.1.2", base);
    add("station_count", `sensor.${p}_station_count`, String(c.stations.length), base);

    for (const s of c.stations) {
      const disabledInHa = s.enabled === false;
      // sensor.py: every program referencing the station; effective ones also listed separately.
      const references = c.programs
        .filter((prog) => prog.stations.includes(s.id))
        .map((prog) => ({
          program_id: prog.id,
          program_name: prog.name,
          effective: prog.times.length > 0,
          scheduled: prog.times.length > 0,
          adjusted_runtime: "00:10:00",
        }));
      add(
        `station_${s.id}`,
        `sensor.${p}_${s.name.toLowerCase().replace(/ /g, "_")}_metadata`,
        disabledInHa ? undefined : "1",
        {
          ...base,
          station_id: s.id,
          station_name: s.name,
          station_enabled: s.enabled,
          terminal: s.terminal,
          terminal_number: s.terminal,
          assigned_effective_programs: references.filter((r) => r.effective),
          program_references: references,
        },
        disabledInHa ? { disabled_by: "integration", original_name: `${s.name} metadata` } : {},
      );
    }
    for (const prog of c.programs) {
      add(`program_${prog.id}`, `sensor.${p}_${prog.name.toLowerCase()}`, prog.times[0] ?? "Not scheduled", {
        ...base,
        program_id: prog.id,
        program_name: prog.name,
        effective: true,
        scheduled: prog.times.length > 0,
        scheduled_start_times: prog.times,
        participating_stations: prog.stations,
        station_runtimes: prog.stations.map((sid) => ({ station_id: sid, adjusted_runtime: "00:10:00" })),
      });
    }

    if (!o.localConfigured) continue;
    const localState = o.localUnavailable ? "unavailable" : o.irrigation;
    const active = c.stations.find((s) => s.id === o.activeStation);
    // HA drops extra attributes from unavailable entities; last_changed marks when it went.
    add("irrigation_state", `sensor.${p}_irrigation_state`, localState, o.localUnavailable ? {} : localBase);
    if (o.localUnavailable) states[`sensor.${p}_irrigation_state`].last_changed = secondsAgo(180, now);
    add(
      "active_station",
      `sensor.${p}_active_station`,
      o.localUnavailable ? "unavailable" : active ? active.name : "Idle",
      {
        ...localBase,
        terminal: active?.terminal ?? null,
        station_id: active?.id ?? null,
        station_name: active?.name ?? null,
      },
    );
    add("active_program", `sensor.${p}_active_program`, active ? "Manual" : "Idle", localBase);
    add(
      "remaining_runtime",
      `sensor.${p}_remaining_runtime`,
      o.irrigation === "running" ? String(o.remaining ?? 500) : "0",
      localBase,
    );
    add("queue_zones_remaining", `sensor.${p}_queue_zones_remaining`, "1", localBase);
    const slowAttrs = { ...localBase };
    if (o.availableTerminals !== undefined) slowAttrs.available_terminals = o.availableTerminals;
    add("irrigation_enabled", `binary_sensor.${p}_irrigation_enabled`, o.irrigationEnabled, slowAttrs);
    add("rain_sensor_active", `binary_sensor.${p}_rain_sensor_active`, o.rainSensor, localBase);
    add("rain_delay", `sensor.${p}_rain_delay`, String(o.rainDelay), localBase);
    add("start_station_select", `select.${p}_start_station`, "unknown", base);
    add("start_duration", `number.${p}_start_duration`, "5", base);
  }
  // Unrelated integration that must be ignored.
  registry.push({ entity_id: "sensor.other", unique_id: "1001_connected", platform: "other" });
  return { registry, states, devices };
}

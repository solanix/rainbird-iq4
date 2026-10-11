// Pure presentation model for the Rain Bird IQ4 dashboard card.
//
// Everything here is DOM-free and side-effect free so it can be tested with
// `node --test`. It maps Home Assistant entity-registry entries and states to a
// per-controller view, decides what the UI may offer, and interprets action
// results. It is never a safety boundary: the integration's admin-only actions
// re-check every guard before writing.

export const DOMAIN = "rainbird_iq4";
export const MIN_DURATION = 1;
export const MAX_DURATION = 30;
export const DEFAULT_DURATION = 5;

// Matches the integration's start preflight (`telemetry_stale` after 60 s), so the
// UI never offers a start the backend would refuse for staleness.
export const LOCAL_STALE_SECONDS = 60;

const UNAVAILABLE = new Set(["unavailable", "unknown"]);

// Unique IDs are `${controllerId}_${key}`; see entity.py.
const FIXED_KEYS = new Set([
  "connected",
  "irrigation_enabled",
  "rain_sensor_active",
  "firmware_version",
  "station_count",
  "programs_used_count",
  "program_summary",
  "irrigation_state",
  "active_station",
  "active_program",
  "queue_zones_remaining",
  "remaining_runtime",
  "rain_delay",
  "start_station_select",
  "start_duration",
]);

/** Classify one unique ID, or return null when it is not an IQ4 entity we know. */
export function parseUniqueId(uniqueId) {
  const match = /^(\d+)_(.+)$/.exec(String(uniqueId ?? ""));
  if (!match) return null;
  const [, controllerId, key] = match;
  if (FIXED_KEYS.has(key)) return { controllerId, role: key };
  let m = /^station_(\d+)_program_(\d+)_runtime$/.exec(key);
  if (m) return { controllerId, role: "station_program_runtime", stationId: m[1], programId: m[2] };
  m = /^station_(\d+)$/.exec(key);
  if (m) return { controllerId, role: "station", stationId: m[1] };
  m = /^program_(\d+)$/.exec(key);
  if (m) return { controllerId, role: "program", programId: m[1] };
  return null;
}

/**
 * Group registry entries of this integration by controller.
 * Returns [{controllerId, deviceId, entities: {role: entry}, stations: Map, programs: Map}].
 */
export function indexRegistry(registryEntries) {
  const controllers = new Map();
  for (const entry of registryEntries ?? []) {
    if (entry.platform !== DOMAIN) continue;
    const parsed = parseUniqueId(entry.unique_id);
    if (!parsed) continue;
    let controller = controllers.get(parsed.controllerId);
    if (!controller) {
      controller = {
        controllerId: parsed.controllerId,
        deviceId: null,
        entities: {},
        stations: new Map(),
        programs: new Map(),
      };
      controllers.set(parsed.controllerId, controller);
    }
    controller.deviceId ??= entry.device_id ?? null;
    if (parsed.role === "station") controller.stations.set(parsed.stationId, entry);
    else if (parsed.role === "program") controller.programs.set(parsed.programId, entry);
    else if (parsed.role !== "station_program_runtime") controller.entities[parsed.role] = entry;
  }
  return [...controllers.values()].sort((a, b) => a.controllerId.localeCompare(b.controllerId));
}

function stateOf(states, entry) {
  if (!entry || entry.disabled_by) return undefined;
  return states?.[entry.entity_id];
}

function isUsable(stateObj) {
  return stateObj !== undefined && !UNAVAILABLE.has(stateObj.state);
}

function triBool(stateObj) {
  if (!isUsable(stateObj)) return null;
  if (stateObj.state === "on") return true;
  if (stateObj.state === "off") return false;
  return null;
}

function intOrNull(stateObj) {
  if (!isUsable(stateObj)) return null;
  const value = Number(stateObj.state);
  return Number.isFinite(value) ? Math.trunc(value) : null;
}

function strictBool(value) {
  return value === true ? true : value === false ? false : null;
}

/** Seconds between an ISO timestamp and `now`, or null when unknown. */
export function ageSeconds(iso, now) {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.round((now - then) / 1000));
}

function controllerName(controller, devices, states) {
  const device = controller.deviceId ? devices?.[controller.deviceId] : undefined;
  const name = device?.name_by_user || device?.name;
  if (name) return name;
  const connected = stateOf(states, controller.entities.connected);
  return connected?.attributes?.site_name || `Controller ${controller.controllerId}`;
}

function buildLocal(controller, states, now) {
  const entry = controller.entities.irrigation_state;
  if (!entry) return { state: "not_configured", updatedAt: null, ageSeconds: null };
  const stateObj = stateOf(states, entry);
  const attrs = stateObj?.attributes ?? {};
  const updatedAt = attrs.last_successful_update ?? null;
  const age = ageSeconds(updatedAt, now);
  let state;
  if (!stateObj || stateObj.state === "unavailable") state = "offline";
  else if (age === null) state = "unknown";
  else if (age > LOCAL_STALE_SECONDS) state = "stale";
  else state = "online";
  return {
    state,
    updatedAt,
    ageSeconds: age,
    // Attributes vanish while unavailable, so the state change time is all that is left.
    unavailableSeconds: state === "offline" && stateObj ? ageSeconds(stateObj.last_changed ?? null, now) : null,
    pollIntervalSeconds: attrs.poll_interval_seconds ?? null,
    consecutiveFailures: attrs.consecutive_failures ?? null,
  };
}

function buildCloud(controller, states) {
  const stateObj = stateOf(states, controller.entities.connected);
  if (!isUsable(stateObj)) return { state: "unknown", stale: null };
  return {
    state: stateObj.state === "on" ? "online" : "offline",
    stale: strictBool(stateObj.attributes?.stale),
  };
}

function buildIrrigation(controller, states, local, stations) {
  const stateObj = stateOf(states, controller.entities.irrigation_state);
  const reported = isUsable(stateObj) ? stateObj.state : "unknown";
  // Only fresh local data may claim idle or running; anything else is unknown.
  const fresh = local.state === "online";
  const known = ["idle", "running", "paused"].includes(reported) ? reported : "unknown";
  const state = fresh ? known : "unknown";

  const active = stateOf(states, controller.entities.active_station);
  const activeAttrs = isUsable(active) ? active.attributes ?? {} : {};
  const activeStationId =
    activeAttrs.station_id !== undefined && activeAttrs.station_id !== null
      ? String(activeAttrs.station_id)
      : null;
  const activeTerminal = Number.isInteger(activeAttrs.terminal) ? activeAttrs.terminal : null;
  const activeStation = stations.find((s) => s.stationId === activeStationId);

  const program = stateOf(states, controller.entities.active_program);
  const remaining = stateOf(states, controller.entities.remaining_runtime);
  const queued = stateOf(states, controller.entities.queue_zones_remaining);
  const running = state === "running";
  return {
    state,
    lastReported: known,
    activeStationId: running ? activeStationId : null,
    activeTerminal: running ? activeTerminal : null,
    activeStationName: running
      ? activeStation?.displayName ?? (isUsable(active) ? active.state : null)
      : null,
    activeProgram: running && isUsable(program) ? program.state : null,
    // The integration reads this from the controller queue for the active terminal.
    remainingSeconds: running ? intOrNull(remaining) : null,
    remainingIsEstimate: false,
    zonesQueued: running ? intOrNull(queued) : null,
    observedAt: local.updatedAt,
  };
}

/**
 * Programs referencing a station: [{name, effective}]. `program_references` includes
 * unscheduled programs; older integrations only expose `assigned_effective_programs`.
 */
function stationPrograms(attrs) {
  const refs = Array.isArray(attrs.program_references)
    ? attrs.program_references
    : Array.isArray(attrs.assigned_effective_programs)
      ? attrs.assigned_effective_programs.map((p) => ({ ...p, effective: true }))
      : [];
  return refs
    .filter((p) => p.program_name)
    .map((p) => ({ name: String(p.program_name), effective: p.effective === true }))
    .sort((a, b) => Number(b.effective) - Number(a.effective) || a.name.localeCompare(b.name));
}

function buildStations(controller, states, availableTerminals) {
  const stations = [];
  for (const [stationId, entry] of controller.stations) {
    const stateObj = stateOf(states, entry);
    const attrs = stateObj?.attributes ?? {};
    const terminal = Number.isInteger(attrs.terminal) ? attrs.terminal : null;
    const hasMetadata = stateObj !== undefined && stateObj.state !== "unavailable";
    const physicallyAvailable =
      availableTerminals === null || terminal === null ? null : availableTerminals.includes(terminal);
    stations.push({
      stationId,
      displayName:
        attrs.station_name ||
        (entry.original_name ? entry.original_name.replace(/ metadata$/, "") : `Station ${stationId}`),
      terminal,
      enabled: hasMetadata ? strictBool(attrs.station_enabled) : null,
      metadataDisabledInHa: Boolean(entry.disabled_by),
      physicallyAvailable,
      programs: stationPrograms(attrs),
    });
  }
  return stations.sort(
    (a, b) => (a.terminal ?? Infinity) - (b.terminal ?? Infinity) || a.stationId.localeCompare(b.stationId),
  );
}

function buildPrograms(controller, states) {
  const programs = [];
  for (const [programId, entry] of controller.programs) {
    const stateObj = stateOf(states, entry);
    const attrs = stateObj?.attributes ?? {};
    programs.push({
      programId,
      name: attrs.program_name || entry.original_name || `Program ${programId}`,
      available: isUsable(stateObj),
      // Unscheduled programs still assigned to stations exist with effective=false.
      effective: attrs.effective === true,
      scheduled: attrs.scheduled === true,
      startTimes: Array.isArray(attrs.scheduled_start_times) ? attrs.scheduled_start_times : [],
      stationRuntimes: Array.isArray(attrs.station_runtimes) ? attrs.station_runtimes : [],
    });
  }
  return programs.sort((a, b) => a.name.localeCompare(b.name));
}

/** `available_terminals` from the slow local poll, or null when not exposed/unknown. */
function availableTerminalsOf(controller, states) {
  const stateObj = stateOf(states, controller.entities.irrigation_enabled);
  const value = stateObj?.attributes?.available_terminals;
  return Array.isArray(value) && value.every(Number.isInteger) ? value : null;
}

function enabledEntityId(entry) {
  return entry && !entry.disabled_by ? entry.entity_id : null;
}

/** Build one controller view from registry/state snapshots. `now` is epoch ms. */
export function buildControllerView(controller, { states, devices, now }) {
  const local = buildLocal(controller, states, now);
  const availableTerminals = availableTerminalsOf(controller, states);
  const stations = buildStations(controller, states, availableTerminals);
  const firmware = stateOf(states, controller.entities.firmware_version);
  return {
    controllerKey: controller.deviceId,
    controllerId: controller.controllerId,
    name: controllerName(controller, devices, states),
    localConfigured: local.state !== "not_configured",
    local,
    cloud: buildCloud(controller, states),
    irrigation: buildIrrigation(controller, states, local, stations),
    irrigationEnabled: triBool(stateOf(states, controller.entities.irrigation_enabled)),
    rain: {
      sensorActive: triBool(stateOf(states, controller.entities.rain_sensor_active)),
      delayDays: intOrNull(stateOf(states, controller.entities.rain_delay)),
    },
    availableTerminals,
    stations,
    programs: buildPrograms(controller, states),
    firmware: isUsable(firmware) ? firmware.state : null,
    // For read-only refresh and history requests; never used to address actions.
    entityIds: {
      irrigationState: enabledEntityId(controller.entities.irrigation_state),
      activeStation: enabledEntityId(controller.entities.active_station),
      irrigationEnabled: enabledEntityId(controller.entities.irrigation_enabled),
    },
  };
}

export function buildControllerViews(registryEntries, { states, devices, now }) {
  return indexRegistry(registryEntries)
    .filter((controller) => controller.deviceId)
    .map((controller) => buildControllerView(controller, { states, devices, now }));
}

/** Stations the UI may offer for a manual start: enabled AND physically present. */
export function startableStations(view) {
  return view.stations.filter((s) => s.enabled === true && s.physicallyAvailable === true);
}

/** Why a station is not startable, for display in the Zones view. */
export function stationBlockReason(station) {
  if (station.enabled === false) return "station_disabled";
  if (station.enabled !== true) return "station_enabled_unknown";
  if (station.physicallyAvailable === false) return "terminal_not_present";
  if (station.physicallyAvailable !== true) return "terminal_unknown";
  return null;
}

/**
 * Controller-level start eligibility. A UI hint only; the backend re-checks all of it.
 * Returns {allowed, reasons[]} where reasons are stable codes for localization.
 */
export function startEligibility(view, { isAdmin }) {
  const reasons = [];
  if (!isAdmin) reasons.push("not_admin");
  if (!view.localConfigured) reasons.push("local_not_configured");
  else if (view.local.state !== "online") reasons.push("local_not_fresh");
  if (view.localConfigured && view.local.state === "online") {
    if (view.irrigation.state === "running" || view.irrigation.state === "paused")
      reasons.push("controller_busy");
    else if (view.irrigation.state !== "idle") reasons.push("controller_state_unknown");
  }
  if (view.irrigationEnabled !== true) reasons.push("irrigation_not_enabled");
  if (view.rain.sensorActive === null || view.rain.delayDays === null) reasons.push("rain_state_unknown");
  else {
    if (view.rain.sensorActive) reasons.push("rain_sensor_active");
    if (view.rain.delayDays !== 0) reasons.push("rain_delay_active");
  }
  if (view.cloud.state !== "online") reasons.push("cloud_metadata_unavailable");
  if (startableStations(view).length === 0) reasons.push("no_startable_stations");
  return { allowed: reasons.length === 0, reasons };
}

/** Stop is offered whenever a local route exists; it does not depend on cloud freshness. */
export function stopEligibility(view, { isAdmin }) {
  const reasons = [];
  if (!isAdmin) reasons.push("not_admin");
  if (!view.localConfigured) reasons.push("local_not_configured");
  return {
    allowed: reasons.length === 0,
    reasons,
    // Shown as a warning, not a block: the controller may still be reachable.
    localDegraded: view.localConfigured && view.local.state !== "online",
  };
}

/** Whole minutes 1–30 only; returns the integer or null. */
export function validateDuration(value) {
  if (typeof value === "boolean" || value === null || value === undefined || value === "") return null;
  const number = typeof value === "string" ? Number(value.trim()) : value;
  if (typeof number !== "number" || !Number.isInteger(number)) return null;
  return number >= MIN_DURATION && number <= MAX_DURATION ? number : null;
}

/**
 * Interpret a service call outcome.
 * kind: "start" | "stop"; result: {response} on success or {error} on failure.
 * Returns {outcome, code?, message?}; never reports success without `verified`.
 *
 * @param {string} kind
 * @param {{ response?: any, error?: any }} outcome
 */
export function interpretActionResult(kind, { response, error }) {
  if (error) {
    const code = error.code ?? null;
    const key = error.translation_key ?? null;
    if (code === "unauthorized") return { outcome: "permission_denied" };
    if (key === "write_outcome_ambiguous") return { outcome: "unknown" };
    if (key) return { outcome: "rejected", code: key, message: error.message ?? null };
    // Transport failures (connection lost, timeout) say nothing about the controller.
    return { outcome: "unknown", message: error.message ?? null };
  }
  const result = response?.response ?? response ?? {};
  if (kind === "stop" && result.no_op === true) return { outcome: "already_stopped" };
  if (result.acknowledged === true && result.verified === true) return { outcome: "verified" };
  if (result.acknowledged === true) return { outcome: "unconfirmed" };
  return { outcome: "unknown" };
}

/** Initial per-card form state. */
export function initialForm(controllerKey = null) {
  return {
    controllerKey,
    stationId: null,
    duration: DEFAULT_DURATION,
    confirming: null, // "start" | "stop" | null
    pending: null, // "start" | "stop" | null
    outcome: null, // {kind, outcome, code?, message?}
  };
}

/**
 * Reducer for the control form. Pure, so double-submit and controller-switch rules
 * are unit tested. Events: select_controller, select_station, set_duration,
 * request_confirm, cancel_confirm, submit, settle, dismiss_outcome.
 */
export function formReducer(state, event) {
  switch (event.type) {
    case "select_controller":
      if (event.controllerKey === state.controllerKey) return state;
      // Never carry a station, confirmation or result across controllers.
      if (state.pending) return state;
      return initialForm(event.controllerKey);
    case "select_station":
      if (state.pending) return state;
      return { ...state, stationId: event.stationId ?? null, confirming: null, outcome: null };
    case "set_duration": {
      if (state.pending) return state;
      // Out-of-range or fractional input is refused, never rounded into range.
      const duration = validateDuration(event.value);
      return duration === null ? state : { ...state, duration, confirming: null };
    }
    case "request_confirm":
      if (state.pending) return state;
      if (event.kind === "start" && (state.stationId === null || validateDuration(state.duration) === null))
        return state;
      return { ...state, confirming: event.kind, outcome: null };
    case "cancel_confirm":
      return state.pending ? state : { ...state, confirming: null };
    case "submit":
      // Exactly one request per confirmation; repeat taps while pending are ignored.
      if (state.pending || state.confirming !== event.kind) return state;
      return { ...state, pending: event.kind, confirming: null, outcome: null };
    case "settle":
      if (state.pending !== event.kind) return state;
      return {
        ...state,
        pending: null,
        outcome: { kind: event.kind, ...event.result },
      };
    case "dismiss_outcome":
      return { ...state, outcome: null };
    default:
      return state;
  }
}

/**
 * Derive observed runs from Recorder history of the Active station sensor.
 *
 * `entries` are compressed history rows ({s, a?, lu}) as returned by
 * `history/history_during_period`, oldest first, `lu` in epoch seconds. Start and
 * end are when HA observed the change, so they are accurate only to the poll
 * interval; nothing here is reported as a controller-confirmed runtime.
 * Returns newest first: {stationId, name, start, end, ongoing, endUnknown}.
 */
export function deriveRuns(entries, { now }) {
  const runs = [];
  let current = null;
  const close = (end, endUnknown) => {
    if (!current) return;
    runs.push({ ...current, end, ongoing: false, endUnknown });
    current = null;
  };
  let lastAttrs = {};
  for (const entry of entries ?? []) {
    const state = entry.s;
    const at = typeof entry.lu === "number" ? entry.lu * 1000 : null;
    if (at === null) continue;
    if (entry.a) lastAttrs = entry.a;
    if (UNAVAILABLE.has(state)) {
      // The run may have continued or ended while HA could not see it.
      close(at, true);
      continue;
    }
    const idle = state === "Idle";
    const stationId =
      !idle && lastAttrs.station_id !== undefined && lastAttrs.station_id !== null
        ? String(lastAttrs.station_id)
        : null;
    const key = idle ? null : `${stationId ?? ""}|${state}`;
    if (current && current.key === key) continue;
    close(at, false);
    if (!idle) current = { key, stationId, name: state, start: at };
  }
  if (current) runs.push({ ...current, end: null, ongoing: true, endUnknown: false });
  return runs
    .map(({ key, ...run }) => ({ ...run, durationSeconds: Math.round(((run.end ?? now) - run.start) / 1000) }))
    .reverse();
}

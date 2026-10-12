// <rainbird-iq4-card>: Lovelace card wiring. Discovers IQ4 entities through the
// entity registry, renders with view.js, and calls only the integration's registered
// actions through Home Assistant. It never talks to the controller or IQ4 cloud.

import {
  DOMAIN,
  buildControllerViews,
  deriveRuns,
  formReducer,
  initialForm,
  interpretActionResult,
  startEligibility,
  startableStations,
  stopEligibility,
  validateDuration,
} from "./model.js";
import { t } from "./strings.js";
import { STYLES } from "./styles.js";
import { renderCard, tabsForProfile } from "./view.js";

export const CARD_VERSION = "0.1.0";
const PROFILES = ["simple", "standard", "advanced"];
const HISTORY_DAYS = 7;
const TICK_MS = 5000;

class RainbirdIq4Card extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._registry = null;
    this._registryError = null;
    this._selectedKey = null;
    this._form = initialForm();
    this._tab = null;
    this._history = { status: "idle", controllerKey: null, runs: [], reason: null };
    this._lastHtml = "";
    this._unsubRegistry = null;
    this._onClick = this._onClick.bind(this);
    this._onChange = this._onChange.bind(this);
    this._onKeyDown = this._onKeyDown.bind(this);
  }

  static getStubConfig() {
    return { profile: "standard" };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    const profile = config.profile ?? "standard";
    if (!PROFILES.includes(profile)) throw new Error(`profile must be one of ${PROFILES.join(", ")}`);
    if (config.controller !== undefined && typeof config.controller !== "string")
      throw new Error("controller must be a Home Assistant device ID");
    this._config = { ...config, profile };
    const tabs = tabsForProfile(profile);
    this._tab = tabs.includes(config.default_view) ? config.default_view : tabs[0];
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._loadRegistry();
    this._render();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  connectedCallback() {
    const root = this.shadowRoot;
    root.addEventListener("click", this._onClick);
    root.addEventListener("change", this._onChange);
    root.addEventListener("keydown", this._onKeyDown);
    this._timer = setInterval(() => this._render(), TICK_MS);
    if (this._hass && !this._unsubRegistry) this._subscribeRegistry();
  }

  disconnectedCallback() {
    const root = this.shadowRoot;
    root.removeEventListener("click", this._onClick);
    root.removeEventListener("change", this._onChange);
    root.removeEventListener("keydown", this._onKeyDown);
    clearInterval(this._timer);
    this._unsubRegistry?.then?.((unsub) => unsub()).catch(() => {});
    this._unsubRegistry = null;
  }

  // ---- data --------------------------------------------------------------

  async _loadRegistry() {
    if (!this._unsubRegistry && this.isConnected) this._subscribeRegistry();
    try {
      const entries = await this._hass.callWS({ type: "config/entity_registry/list" });
      this._registry = entries.filter((entry) => entry.platform === DOMAIN);
      this._registryError = null;
    } catch (err) {
      this._registryError = err?.message ?? String(err);
    }
    this._render();
  }

  _subscribeRegistry() {
    if (!this._hass?.connection) return;
    let pending = null;
    this._unsubRegistry = this._hass.connection
      .subscribeEvents(() => {
        clearTimeout(pending);
        pending = setTimeout(() => this._loadRegistry(), 500);
      }, "entity_registry_updated")
      .catch(() => null);
  }

  _views() {
    if (!this._registry || !this._hass) return [];
    return buildControllerViews(this._registry, {
      states: this._hass.states,
      devices: this._hass.devices,
      now: Date.now(),
    });
  }

  _select(views) {
    let notice = null;
    let selected = views.find((v) => v.controllerKey === this._selectedKey);
    if (!selected && this._config?.controller) {
      selected = views.find((v) => v.controllerKey === this._config.controller);
      if (!selected && views.length) {
        notice = t(this._lang, "controller_missing", { name: views[0].name });
      }
    }
    selected ??= views[0] ?? null;
    if (selected && selected.controllerKey !== this._selectedKey) {
      this._selectedKey = selected.controllerKey;
    }
    // Per-controller UI state never survives a controller change.
    if (selected && this._form.controllerKey !== selected.controllerKey && !this._form.pending) {
      this._form = formReducer(this._form, { type: "select_controller", controllerKey: selected.controllerKey });
      this._history = { status: "idle", controllerKey: selected.controllerKey, runs: [], reason: null };
    }
    return { selected, notice };
  }

  get _lang() {
    return this._hass?.locale?.language ?? this._hass?.language ?? "en";
  }

  get _isAdmin() {
    return this._hass?.user?.is_admin === true;
  }

  // ---- rendering ---------------------------------------------------------

  _render() {
    if (!this._config || !this.shadowRoot) return;
    const views = this._views();
    const { selected, notice } = this._select(views);
    if (selected && this._tab === "history" && this._history.status === "idle") this._loadHistory(selected);
    const html = renderCard({
      config: this._config,
      lang: this._lang,
      isAdmin: this._isAdmin,
      now: Date.now(),
      views,
      selected,
      notice,
      loading: !this._hass || (this._registry === null && !this._registryError),
      error: this._registryError ? t(this._lang, "load_failed", { message: this._registryError }) : null,
      ui: { tab: this._tab, form: this._form, history: this._history },
    });
    if (html === this._lastHtml) return;
    this._lastHtml = html;

    // Keep focus and any half-typed value across re-renders.
    const active = /** @type {HTMLInputElement | null} */ (this.shadowRoot.activeElement);
    const focusKey = active?.dataset?.key;
    const typed = active?.tagName === "INPUT" ? active.value : null;
    // Create ha-card once and replace only its contents: a fresh ha-card renders its
    // slot asynchronously, and until it has, nothing inside it can take focus.
    let haCard = this.shadowRoot.querySelector("ha-card");
    if (!haCard) {
      this.shadowRoot.innerHTML = `<style>${STYLES}</style><ha-card></ha-card>`;
      haCard = this.shadowRoot.querySelector("ha-card");
    }
    haCard.innerHTML = html;
    const autofocus = /** @type {HTMLInputElement | null} */ (this.shadowRoot.querySelector("[autofocus]"));
    const restore = focusKey
      ? /** @type {HTMLInputElement | null} */ (this.shadowRoot.querySelector(`[data-key="${CSS.escape(focusKey)}"]`))
      : null;
    const target = autofocus && autofocus.dataset.key !== this._autofocused ? autofocus : restore;
    if (autofocus) this._autofocused = autofocus.dataset.key;
    else this._autofocused = null;
    if (target && !target.disabled) {
      if (target === restore && typed !== null) target.value = typed;
      target.focus();
    }
  }

  _dispatch(event) {
    this._form = formReducer(this._form, event);
    this._render();
  }

  // ---- events ------------------------------------------------------------

  _onClick(ev) {
    const el = ev.target.closest?.("[data-action]");
    if (!el || el.disabled) return;
    const action = el.dataset.action;
    switch (action) {
      case "tab":
        this._setTab(el.dataset.tab);
        break;
      case "duration-step":
        this._dispatch({ type: "set_duration", value: this._form.duration + Number(el.dataset.step) });
        break;
      case "confirm":
        this._requestConfirm(el.dataset.kind);
        break;
      case "cancel":
        this._dispatch({ type: "cancel_confirm" });
        break;
      case "submit":
        this._submit(el.dataset.kind);
        break;
      case "dismiss":
        this._dispatch({ type: "dismiss_outcome" });
        break;
      case "refresh":
        this._refreshStatus();
        break;
      case "load-history":
        this._history = { ...this._history, status: "idle" };
        this._render();
        break;
      default:
    }
  }

  _onChange(ev) {
    const el = ev.target;
    switch (el.dataset?.action) {
      case "select-controller":
        if (this._form.pending) return;
        this._selectedKey = el.value;
        this._render();
        break;
      case "select-station":
        this._dispatch({ type: "select_station", stationId: el.value || null });
        break;
      case "duration-input": {
        const value = validateDuration(el.value);
        if (value === null) {
          // Refuse rather than round; restore the last valid value.
          el.value = String(this._form.duration);
          return;
        }
        this._dispatch({ type: "set_duration", value });
        break;
      }
      default:
    }
  }

  _onKeyDown(ev) {
    if (ev.key === "Escape" && this._form.confirming && !this._form.pending) {
      this._dispatch({ type: "cancel_confirm" });
      return;
    }
    const tab = ev.target.closest?.('[role="tab"]');
    if (!tab) return;
    const tabs = tabsForProfile(this._config.profile);
    const index = tabs.indexOf(tab.dataset.tab);
    const next = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index - 1 + tabs.length) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    }[ev.key];
    if (next === undefined) return;
    ev.preventDefault();
    this._setTab(tabs[next]);
    /** @type {HTMLElement | null} */ (this.shadowRoot.querySelector(`#tab-${tabs[next]}`))?.focus();
  }

  _setTab(tab) {
    this._tab = tab;
    this._render();
  }

  _current() {
    const views = this._views();
    return views.find((v) => v.controllerKey === this._selectedKey) ?? null;
  }

  _requestConfirm(kind) {
    const view = this._current();
    if (!view) return;
    const ok =
      kind === "stop"
        ? stopEligibility(view, { isAdmin: this._isAdmin }).allowed
        : startEligibility(view, { isAdmin: this._isAdmin }).allowed &&
          startableStations(view).some((s) => s.stationId === this._form.stationId);
    if (ok) this._dispatch({ type: "request_confirm", kind });
    // Data can go stale between render ticks while the button still looks enabled;
    // re-render so the refusal shows its reason instead of the tap doing nothing.
    else this._render();
  }

  async _submit(kind) {
    const view = this._current();
    const before = this._form;
    this._dispatch({ type: "submit", kind });
    // The reducer ignores repeat taps; only the transition into pending sends.
    if (before.pending || this._form.pending !== kind || !view) return;
    const serviceData =
      kind === "start"
        ? {
            device_id: view.controllerKey,
            station_id: Number(this._form.stationId),
            duration_minutes: this._form.duration,
          }
        : { device_id: view.controllerKey };
    let result;
    try {
      const response = await this._hass.callWS({
        type: "call_service",
        domain: DOMAIN,
        service: kind === "start" ? "start_station" : "stop_irrigation",
        service_data: serviceData,
        return_response: true,
      });
      result = interpretActionResult(kind, { response });
    } catch (error) {
      result = interpretActionResult(kind, { error: error ?? {} });
    }
    // One request per confirmation, never retried here, whatever the outcome.
    this._dispatch({ type: "settle", kind, result });
  }

  async _refreshStatus() {
    const view = this._current();
    const ids = [view?.entityIds.irrigationState, view?.entityIds.irrigationEnabled].filter(Boolean);
    if (!ids.length) return;
    try {
      // Read-only coordinator refresh; it never writes to the controller.
      await this._hass.callService("homeassistant", "update_entity", { entity_id: ids });
    } catch {
      // The status badges already show whether local data is current.
    }
  }

  async _loadHistory(view) {
    const lang = this._lang;
    const entityId = view.entityIds.activeStation;
    const controllerKey = view.controllerKey;
    if (!view.localConfigured) return;
    if (!entityId) {
      this._history = { status: "unavailable", controllerKey, runs: [], reason: t(lang, "history_no_entity") };
      this._render();
      return;
    }
    this._history = { status: "loading", controllerKey, runs: [], reason: null };
    const now = Date.now();
    try {
      const result = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: new Date(now - HISTORY_DAYS * 86400000).toISOString(),
        end_time: new Date(now).toISOString(),
        entity_ids: [entityId],
        minimal_response: false,
        no_attributes: false,
        significant_changes_only: false,
      });
      if (this._history.controllerKey !== controllerKey) return;
      this._history = {
        status: "ready",
        controllerKey,
        runs: deriveRuns(result?.[entityId] ?? [], { now: Date.now() }),
        reason: null,
      };
    } catch (err) {
      if (this._history.controllerKey !== controllerKey) return;
      this._history = {
        status: "unavailable",
        controllerKey,
        runs: [],
        reason: t(lang, "history_recorder_failed", { message: err?.message ?? err?.code ?? "error" }),
      };
    }
    this._render();
  }
}

if (!customElements.get("rainbird-iq4-card")) {
  customElements.define("rainbird-iq4-card", RainbirdIq4Card);
  const win = /** @type {any} */ (window);
  win.customCards = win.customCards || [];
  win.customCards.push({
    type: "rainbird-iq4-card",
    name: "Rain Bird IQ4",
    description: "Status, manual start/stop, programs, zones, history and diagnostics for Rain Bird IQ4.",
  });
  console.info(`%c RAINBIRD-IQ4-CARD %c ${CARD_VERSION} `, "background:#1565c0;color:#fff", "");
}

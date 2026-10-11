// Pure HTML rendering for the Rain Bird IQ4 card. Every function returns a string
// so rendering rules (what is offered, what is hidden, what is labelled stale) are
// testable without a DOM. All dynamic text passes through `esc`.

import {
  MAX_DURATION,
  MIN_DURATION,
  startEligibility,
  startableStations,
  stationBlockReason,
  stopEligibility,
} from "./model.js";
import { t } from "./strings.js";

export const TABS = ["status", "control", "programs", "zones", "history", "diagnostics"];
const PROFILE_TABS = {
  simple: ["status", "control", "programs"],
  standard: TABS,
  advanced: TABS,
};

export function tabsForProfile(profile) {
  return PROFILE_TABS[profile] ?? PROFILE_TABS.simple;
}

export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

export function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return null;
  if (seconds < 90) return `${seconds} s`;
  if (seconds < 90 * 60) return `${Math.round(seconds / 60)} min`;
  if (seconds < 48 * 3600) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86400)} d`;
}

function formatTime(ms, lang) {
  if (ms === null || ms === undefined) return "—";
  try {
    return new Intl.DateTimeFormat(lang, { dateStyle: "medium", timeStyle: "short" }).format(new Date(ms));
  } catch {
    return new Date(ms).toISOString();
  }
}

const icon = (name) => `<ha-icon icon="${esc(name)}" aria-hidden="true"></ha-icon>`;

function badge(label, stateKey, tone, lang, title) {
  return `<span class="badge tone-${tone}"${title ? ` title="${esc(title)}"` : ""}>
    <span class="badge-label">${esc(label)}:</span> ${esc(t(lang, `conn_${stateKey}`))}</span>`;
}

const CONN_TONE = { online: "ok", offline: "error", stale: "warn", unknown: "warn", not_configured: "muted" };

export function renderHeader(ctx) {
  const { views, selected, lang } = ctx;
  const selector =
    views.length > 1
      ? `<label class="controller-select">
          <span class="visually-hidden">${esc(t(lang, "controller"))}</span>
          <select data-action="select-controller" data-key="controller-select"${ctx.ui.form.pending ? " disabled" : ""}>
            ${views
              .map(
                (v) =>
                  `<option value="${esc(v.controllerKey)}"${v.controllerKey === selected.controllerKey ? " selected" : ""}>${esc(v.name)}</option>`,
              )
              .join("")}
          </select></label>`
      : `<span class="controller-name">${esc(selected.name)}</span>`;
  const cloudTitle = selected.cloud.stale ? t(lang, "cloud_report_stale") : null;
  return `<header class="header">
    <div class="title-row">
      <h2 class="title">${icon("mdi:sprinkler-variant")} ${esc(ctx.config.title ?? t(lang, "title"))}</h2>
      ${selector}
    </div>
    <div class="badges" role="status" aria-live="polite">
      ${badge(t(lang, "local"), selected.local.state, CONN_TONE[selected.local.state], lang)}
      ${badge(
        t(lang, "cloud"),
        selected.cloud.state,
        selected.cloud.stale ? "warn" : CONN_TONE[selected.cloud.state],
        lang,
        cloudTitle,
      )}
    </div>
  </header>`;
}

export function renderTabs(ctx) {
  const tabs = tabsForProfile(ctx.config.profile);
  return `<nav class="tabs" role="tablist" aria-label="${esc(t(ctx.lang, "title"))}">
    ${tabs
      .map((tab) => {
        const active = tab === ctx.ui.tab;
        return `<button role="tab" class="tab" id="tab-${tab}" data-action="tab" data-tab="${tab}" data-key="tab-${tab}"
          aria-selected="${active}" aria-controls="panel" tabindex="${active ? 0 : -1}">${esc(t(ctx.lang, `tab_${tab}`))}</button>`;
      })
      .join("")}
  </nav>`;
}

function irrigationHero(ctx) {
  const { selected: v, lang } = ctx;
  const irr = v.irrigation;
  if (irr.state === "running" || irr.state === "paused") {
    const stationName = irr.activeStationName ?? t(lang, "multiple_or_unresolved");
    return `<div class="hero tone-active">
      <p class="hero-state">${icon("mdi:sprinkler")} ${esc(t(lang, `state_${irr.state}`))}</p>
      <dl class="facts">
        <div><dt>${esc(t(lang, "station"))}</dt><dd>${esc(stationName)}</dd></div>
        ${irr.activeProgram ? `<div><dt>${esc(t(lang, "program"))}</dt><dd>${esc(irr.activeProgram)}</dd></div>` : ""}
        ${
          irr.remainingSeconds !== null
            ? `<div><dt>${esc(t(lang, "remaining"))}</dt><dd><span class="big">${esc(formatDuration(irr.remainingSeconds))}</span>
                <span class="muted">${esc(t(lang, "remaining_as_of", { age: formatAge(v.local.ageSeconds) }))}</span></dd></div>`
            : ""
        }
        ${irr.zonesQueued !== null ? `<div><dt>${esc(t(lang, "zones_queued"))}</dt><dd>${esc(irr.zonesQueued)}</dd></div>` : ""}
      </dl>
    </div>`;
  }
  if (irr.state === "idle") {
    return `<div class="hero tone-ok">
      <p class="hero-state">${icon("mdi:check-circle-outline")} ${esc(t(lang, "state_idle"))}</p>
      <p class="muted">${esc(t(lang, "idle_detail"))}</p>
    </div>`;
  }
  const detail =
    v.local.state === "stale"
      ? t(lang, "unknown_local_stale", {
          age: formatAge(v.local.ageSeconds),
          last: t(lang, `state_${irr.lastReported}`),
        })
      : t(lang, `unknown_local_${v.local.state === "online" ? "unknown" : v.local.state}`);
  return `<div class="hero tone-warn">
    <p class="hero-state">${icon("mdi:help-circle-outline")} ${esc(t(lang, "state_unknown"))}</p>
    <p>${esc(detail)}</p>
  </div>`;
}

function outcomeMessage(ctx, outcome) {
  const { lang } = ctx;
  switch (outcome.outcome) {
    case "verified":
      return { tone: "ok", text: t(lang, `outcome_${outcome.kind}_verified`) };
    case "already_stopped":
      return { tone: "ok", text: t(lang, "outcome_already_stopped") };
    case "unconfirmed":
      return { tone: "warn", text: t(lang, "outcome_unconfirmed"), refresh: true };
    case "unknown":
      return {
        tone: "warn",
        text: t(lang, outcome.kind === "stop" ? "outcome_stop_unknown" : "outcome_unknown"),
        refresh: true,
      };
    case "permission_denied":
      return { tone: "error", text: t(lang, "outcome_permission_denied") };
    case "rejected":
      return {
        tone: "error",
        text: t(lang, `outcome_rejected_${outcome.kind}`, { message: outcome.message ?? outcome.code }),
      };
    default:
      return { tone: "warn", text: t(lang, "outcome_unknown") };
  }
}

export function renderOutcome(ctx) {
  const { form } = ctx.ui;
  if (form.pending) {
    return `<div class="notice tone-muted" role="status" aria-live="polite">
      <span class="spinner" aria-hidden="true"></span> ${esc(t(ctx.lang, `pending_${form.pending}`))}</div>`;
  }
  if (!form.outcome) return "";
  const msg = outcomeMessage(ctx, form.outcome);
  return `<div class="notice tone-${msg.tone}" role="alert">
    <p>${esc(msg.text)}</p>
    <div class="row">
      ${msg.refresh ? `<button class="secondary" data-action="refresh" data-key="refresh">${esc(t(ctx.lang, "refresh_status"))}</button>` : ""}
      <button class="secondary" data-action="dismiss" data-key="dismiss">${esc(t(ctx.lang, "dismiss"))}</button>
    </div>
  </div>`;
}

export function renderStop(ctx) {
  const { selected: v, lang, isAdmin, ui } = ctx;
  const stop = stopEligibility(v, { isAdmin });
  if (!v.localConfigured) return "";
  const running = v.irrigation.state === "running" || v.irrigation.state === "paused";
  if (!stop.allowed) {
    return `<p class="muted">${esc(t(lang, "view_only", { reason: t(lang, `reason_${stop.reasons[0]}`) }))}</p>`;
  }
  if (ui.form.confirming === "stop") {
    return `<div class="confirm tone-error" role="group" aria-labelledby="stop-q">
      <p id="stop-q" class="confirm-q">${esc(t(lang, "stop_confirm", { controller: v.name }))}</p>
      <div class="row">
        <button class="danger" data-action="submit" data-kind="stop" data-key="confirm-stop" autofocus>${icon("mdi:water-off")} ${esc(t(lang, "stop_confirm_button"))}</button>
        <button class="secondary" data-action="cancel" data-key="cancel-stop">${esc(t(lang, "cancel"))}</button>
      </div>
    </div>`;
  }
  const notes = [];
  if (stop.localDegraded) notes.push(t(lang, "stop_local_degraded", { state: t(lang, `conn_${v.local.state}`) }));
  else if (!running && v.irrigation.state === "idle") notes.push(t(lang, "stop_nothing_running"));
  return `<div class="stop-block">
    <button class="${running || v.irrigation.state === "unknown" ? "danger big-button" : "secondary"}"
      data-action="confirm" data-kind="stop" data-key="stop"${ui.form.pending ? " disabled" : ""}>
      ${icon("mdi:water-off")} ${esc(t(lang, "stop_irrigation"))}</button>
    ${notes.map((n) => `<p class="muted">${esc(n)}</p>`).join("")}
  </div>`;
}

function localUpdateText(v, lang, age) {
  if (age) return t(lang, "ago", { age });
  if (v.local.unavailableSeconds !== null && v.local.unavailableSeconds !== undefined) {
    return t(lang, "unavailable_for", { age: formatAge(v.local.unavailableSeconds) });
  }
  return t(lang, v.localConfigured ? "never" : "conn_not_configured");
}

function renderStatus(ctx) {
  const { selected: v, lang } = ctx;
  const counts = { enabled: 0, disabled: 0, unknown: 0 };
  for (const s of v.stations) counts[s.enabled === true ? "enabled" : s.enabled === false ? "disabled" : "unknown"]++;
  const scheduled = v.programs.filter((p) => p.available && p.scheduled);
  const yn = (value) => t(lang, value === true ? "yes" : value === false ? "no" : "unknown");
  const rainSensor =
    v.rain.sensorActive === null ? t(lang, "unknown") : t(lang, v.rain.sensorActive ? "rain_sensor_on" : "rain_sensor_off");
  const rainDelay =
    v.rain.delayDays === null
      ? t(lang, "unknown")
      : v.rain.delayDays === 0
        ? t(lang, "rain_delay_none")
        : t(lang, "rain_delay_days", { days: v.rain.delayDays });
  const age = formatAge(v.local.ageSeconds);
  return `<div class="grid">
    <section class="panel-section" aria-labelledby="h-now">
      <h3 id="h-now" class="visually-hidden">${esc(t(lang, "tab_status"))}</h3>
      ${irrigationHero(ctx)}
      ${renderStop(ctx)}
      ${renderOutcome(ctx)}
    </section>
    <section class="panel-section" aria-labelledby="h-health">
      <h3 id="h-health">${esc(t(lang, "health"))}</h3>
      <dl class="facts">
        <div><dt>${esc(t(lang, "last_local_update"))}</dt><dd class="${v.local.state === "online" ? "" : "stale"}">${esc(localUpdateText(v, lang, age))}</dd></div>
        <div><dt>${esc(t(lang, "rain_sensor"))}</dt><dd>${esc(rainSensor)}</dd></div>
        <div><dt>${esc(t(lang, "rain_delay"))}</dt><dd>${esc(rainDelay)}</dd></div>
        <div><dt>${esc(t(lang, "irrigation_enabled"))}</dt><dd>${esc(yn(v.irrigationEnabled))}</dd></div>
      </dl>
    </section>
    <section class="panel-section" aria-labelledby="h-zones-sum">
      <h3 id="h-zones-sum">${esc(t(lang, "zones_summary"))}</h3>
      <p>${esc(t(lang, "zones_summary_text", counts))}</p>
    </section>
    <section class="panel-section" aria-labelledby="h-sched">
      <h3 id="h-sched">${esc(t(lang, "schedule_summary"))}</h3>
      ${
        scheduled.length
          ? `<ul class="plain">${scheduled
              .map((p) => `<li><strong>${esc(p.name)}</strong> — ${esc(p.startTimes.join(", "))}</li>`)
              .join("")}</ul>`
          : `<p class="muted">${esc(t(lang, "no_schedule"))}</p>`
      }
    </section>
  </div>`;
}

function renderControl(ctx) {
  const { selected: v, lang, isAdmin, ui } = ctx;
  const { form } = ui;
  const eligibility = startEligibility(v, { isAdmin });
  const stations = startableStations(v);
  const busy = Boolean(form.pending);
  const formDisabled = !eligibility.allowed || busy;
  const selectedStation = stations.find((s) => s.stationId === form.stationId) ?? null;

  let startBody;
  if (form.confirming === "start" && selectedStation) {
    startBody = `<div class="confirm tone-active" role="group" aria-labelledby="start-q">
      <p id="start-q" class="confirm-q">${esc(
        t(lang, "start_confirm", { station: selectedStation.displayName, controller: v.name, minutes: form.duration }),
      )}</p>
      <p class="muted">${esc(t(lang, "rain_notice"))}</p>
      <div class="row">
        <button class="primary" data-action="submit" data-kind="start" data-key="confirm-start" autofocus>${icon("mdi:play")} ${esc(t(lang, "start_confirm_button"))}</button>
        <button class="secondary" data-action="cancel" data-key="cancel-start">${esc(t(lang, "cancel"))}</button>
      </div>
    </div>`;
  } else {
    const dis = formDisabled ? " disabled" : "";
    startBody = `
      ${
        eligibility.allowed
          ? ""
          : `<div class="notice tone-muted"><p>${esc(t(lang, "start_unavailable"))}</p><ul>${eligibility.reasons
              .map((r) => `<li>${esc(t(lang, `reason_${r}`))}</li>`)
              .join("")}</ul></div>`
      }
      <label class="field">
        <span>${esc(t(lang, "zone"))}</span>
        <select data-action="select-station" data-key="station"${dis}>
          <option value="">${esc(t(lang, "choose_zone"))}</option>
          ${stations
            .map(
              (s) =>
                `<option value="${esc(s.stationId)}"${s.stationId === form.stationId ? " selected" : ""}>${esc(s.displayName)}${s.terminal !== null ? ` (${esc(t(lang, "terminal"))} ${esc(s.terminal)})` : ""}</option>`,
            )
            .join("")}
        </select>
      </label>
      <div class="field">
        <span id="duration-label">${esc(t(lang, "duration"))}</span>
        <div class="stepper" role="group" aria-labelledby="duration-label">
          <button class="secondary" data-action="duration-step" data-step="-1" data-key="dur-dec" aria-label="${esc(t(lang, "decrease"))}"${dis || (form.duration <= MIN_DURATION ? " disabled" : "")}>−</button>
          <input type="number" inputmode="numeric" min="${MIN_DURATION}" max="${MAX_DURATION}" step="1"
            value="${esc(form.duration)}" data-action="duration-input" data-key="duration" aria-labelledby="duration-label"${dis}>
          <span aria-hidden="true">min</span>
          <button class="secondary" data-action="duration-step" data-step="1" data-key="dur-inc" aria-label="${esc(t(lang, "increase"))}"${dis || (form.duration >= MAX_DURATION ? " disabled" : "")}>+</button>
        </div>
      </div>
      <button class="primary" data-action="confirm" data-kind="start" data-key="review-start"${formDisabled || !selectedStation ? " disabled" : ""}>${esc(t(lang, "review_start"))}</button>`;
  }

  return `<div class="grid">
    <section class="panel-section" aria-labelledby="h-ctl-now">
      <h3 id="h-ctl-now" class="visually-hidden">${esc(t(lang, "tab_status"))}</h3>
      ${irrigationHero(ctx)}
      ${renderStop(ctx)}
      ${renderOutcome(ctx)}
    </section>
    <section class="panel-section" aria-labelledby="h-start">
      <h3 id="h-start">${esc(t(lang, "start_heading"))}</h3>
      ${v.localConfigured ? startBody : `<p class="muted">${esc(t(lang, "reason_local_not_configured"))}</p>`}
    </section>
  </div>`;
}

function renderZones(ctx) {
  const { selected: v, lang } = ctx;
  if (!v.stations.length) return `<p class="muted">${esc(t(lang, "no_zones"))}</p>`;
  const advanced = ctx.config.profile === "advanced";
  const rows = v.stations
    .map((s) => {
      const watering = v.irrigation.state === "running" && v.irrigation.activeStationId === s.stationId;
      const enabled =
        s.enabled === true ? "zone_enabled" : s.enabled === false ? "zone_disabled" : "zone_enabled_unknown";
      const block = stationBlockReason(s);
      const programs = s.programs
        .map((p) =>
          p.effective
            ? esc(p.name)
            : `<span class="muted">${esc(t(lang, "zone_program_not_scheduled", { name: p.name }))}</span>`,
        )
        .join(", ");
      return `<tr class="${watering ? "watering" : ""}">
        <th scope="row">${esc(s.displayName)}${s.metadataDisabledInHa ? `<br><span class="muted small">${esc(t(lang, "metadata_disabled_in_ha"))}</span>` : ""}</th>
        <td>${esc(s.terminal ?? "—")}</td>
        <td>${esc(t(lang, enabled))}</td>
        <td>${watering ? `${icon("mdi:sprinkler")} <strong>${esc(t(lang, "zone_watering"))}</strong>` : block ? esc(t(lang, `block_${block}`)) : esc(t(lang, "startable"))}</td>
        <td>${programs || "—"}</td>
        ${advanced ? `<td><code>${esc(s.stationId)}</code></td>` : ""}
      </tr>`;
    })
    .join("");
  return `<div class="table-wrap"><table>
    <thead><tr>
      <th scope="col">${esc(t(lang, "zone_name"))}</th>
      <th scope="col">${esc(t(lang, "terminal"))}</th>
      <th scope="col">${esc(t(lang, "enabled"))}</th>
      <th scope="col">${esc(t(lang, "status"))}</th>
      <th scope="col">${esc(t(lang, "programs"))}</th>
      ${advanced ? `<th scope="col">${esc(t(lang, "station_id"))}</th>` : ""}
    </tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

function renderPrograms(ctx) {
  const { selected: v, lang } = ctx;
  const body = v.programs.length
    ? v.programs
        .map((p) => {
          let status;
          if (!p.available) status = t(lang, "program_unavailable");
          else if (p.scheduled) status = t(lang, "program_scheduled", { times: p.startTimes.join(", ") });
          else status = t(lang, "program_not_scheduled");
          const zones = p.stationRuntimes
            .map((r) => {
              const name = r.station_name || v.stations.find((s) => s.stationId === String(r.station_id))?.displayName;
              return `<li>${esc(name ?? r.station_id)} — ${esc(r.adjusted_runtime ?? "—")}</li>`;
            })
            .join("");
          return `<article class="program${p.available && p.scheduled ? "" : " inactive"}" aria-labelledby="p-${esc(p.programId)}">
            <h3 id="p-${esc(p.programId)}">${icon(p.scheduled ? "mdi:calendar-clock" : "mdi:calendar-remove-outline")} ${esc(p.name)}</h3>
            <p><strong>${esc(status)}</strong></p>
            ${p.available && !p.effective && !p.scheduled ? `<p class="muted">${esc(t(lang, "program_not_effective"))}</p>` : ""}
            ${zones ? `<p class="muted">${esc(t(lang, "program_zones", { count: p.stationRuntimes.length }))}</p><ul class="plain">${zones}</ul>` : ""}
          </article>`;
        })
        .join("")
    : `<p class="muted">${esc(t(lang, "no_programs"))}</p>`;
  return `<p class="notice tone-muted">${esc(t(lang, "programs_note"))}</p><div class="programs">${body}</div>`;
}

function renderHistory(ctx) {
  const { lang, ui, selected: v } = ctx;
  const h = ui.history;
  let body;
  if (!v.localConfigured) body = `<p class="notice tone-muted">${esc(t(lang, "history_unavailable", { reason: t(lang, "history_no_local") }))}</p>`;
  else if (h.status === "loading") body = `<p role="status"><span class="spinner" aria-hidden="true"></span> ${esc(t(lang, "history_loading"))}</p>`;
  else if (h.status === "unavailable")
    body = `<p class="notice tone-muted">${esc(t(lang, "history_unavailable", { reason: h.reason }))}</p>
      <button class="secondary" data-action="load-history" data-key="load-history">${esc(t(lang, "history_load"))}</button>`;
  else if (h.status === "ready" && !h.runs.length) body = `<p class="muted">${esc(t(lang, "history_empty"))}</p>`;
  else if (h.status === "ready")
    body = `<div class="table-wrap"><table>
      <thead><tr>
        <th scope="col">${esc(t(lang, "zone_name"))}</th>
        <th scope="col">${esc(t(lang, "started"))}</th>
        <th scope="col">${esc(t(lang, "ended"))}</th>
        <th scope="col">${esc(t(lang, "observed_duration"))}</th>
      </tr></thead>
      <tbody>${h.runs
        .map(
          (r) => `<tr>
          <th scope="row">${esc(r.name)}</th>
          <td>${esc(formatTime(r.start, lang))}</td>
          <td>${r.ongoing ? esc(t(lang, "ongoing")) : r.endUnknown ? esc(t(lang, "end_unknown")) : esc(formatTime(r.end, lang))}</td>
          <td>${r.endUnknown ? "≥ " : ""}${esc(formatDuration(r.durationSeconds))}</td>
        </tr>`,
        )
        .join("")}</tbody></table></div>`;
  else body = `<button class="secondary" data-action="load-history" data-key="load-history">${esc(t(lang, "history_load"))}</button>`;
  return `<h3>${esc(t(lang, "history_heading"))}</h3><p class="muted small">${esc(t(lang, "history_note"))}</p>${body}`;
}

function renderDiagnostics(ctx) {
  const { selected: v, lang, ui } = ctx;
  const age = formatAge(v.local.ageSeconds);
  const outcome = ui.form.outcome ? outcomeMessage(ctx, ui.form.outcome).text : t(lang, "diag_none");
  const advanced = ctx.config.profile === "advanced";
  return `<dl class="facts diag">
    <div><dt>${esc(t(lang, "diag_cloud"))}</dt><dd>${esc(t(lang, `conn_${v.cloud.state}`))}${v.cloud.stale ? ` — ${esc(t(lang, "cloud_report_stale"))}` : ""}</dd></div>
    <div><dt>${esc(t(lang, "diag_local"))}</dt><dd>${esc(t(lang, `conn_${v.local.state}`))}${age ? ` — ${esc(t(lang, "ago", { age }))}` : ""}</dd></div>
    <div><dt>${esc(t(lang, "diag_poll_interval"))}</dt><dd>${v.local.pollIntervalSeconds ? esc(t(lang, "seconds", { n: v.local.pollIntervalSeconds })) : "—"}</dd></div>
    <div><dt>${esc(t(lang, "diag_failures"))}</dt><dd>${esc(v.local.consecutiveFailures ?? "—")}</dd></div>
    <div><dt>${esc(t(lang, "diag_firmware"))}</dt><dd>${esc(v.firmware ?? "—")}</dd></div>
    <div><dt>${esc(t(lang, "diag_terminals"))}</dt><dd>${esc(v.availableTerminals ? v.availableTerminals.join(", ") : t(lang, "unknown"))}</dd></div>
    <div><dt>${esc(t(lang, "diag_last_command"))}</dt><dd>${esc(outcome)}</dd></div>
  </dl>
  <details${advanced ? " open" : ""}>
    <summary>${esc(t(lang, "diag_advanced"))}</summary>
    <dl class="facts diag">
      <div><dt>${esc(t(lang, "diag_controller_id"))}</dt><dd><code>${esc(v.controllerId)}</code></dd></div>
      <div><dt>${esc(t(lang, "diag_device_id"))}</dt><dd><code>${esc(v.controllerKey)}</code></dd></div>
    </dl>
  </details>`;
}

const PANELS = {
  status: renderStatus,
  control: renderControl,
  programs: renderPrograms,
  zones: renderZones,
  history: renderHistory,
  diagnostics: renderDiagnostics,
};

/**
 * ctx: {config, lang, isAdmin, now, views, selected, ui:{tab, form, history}, loading, error, notice}
 */
export function renderCard(ctx) {
  const lang = ctx.lang;
  if (ctx.error) return `<div class="card-body"><p class="notice tone-error" role="alert">${esc(ctx.error)}</p></div>`;
  if (ctx.loading) return `<div class="card-body"><p role="status"><span class="spinner" aria-hidden="true"></span> ${esc(t(lang, "loading"))}</p></div>`;
  if (!ctx.selected) return `<div class="card-body"><p class="notice tone-muted">${esc(t(lang, "no_controllers"))}</p></div>`;
  const tabs = tabsForProfile(ctx.config.profile);
  const tab = tabs.includes(ctx.ui.tab) ? ctx.ui.tab : tabs[0];
  const inner = { ...ctx, ui: { ...ctx.ui, tab } };
  return `<div class="card-body">
    ${renderHeader(inner)}
    ${ctx.notice ? `<p class="notice tone-warn">${esc(ctx.notice)}</p>` : ""}
    ${renderTabs(inner)}
    <div class="panel" id="panel" role="tabpanel" aria-labelledby="tab-${tab}">${PANELS[tab](inner)}</div>
  </div>`;
}

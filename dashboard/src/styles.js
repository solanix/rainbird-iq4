// Card styles. Colors come from Home Assistant theme variables so light and dark
// themes both work; state is always conveyed by text and icon as well as color.
export const STYLES = `
:host { display: block; }
ha-card { overflow: hidden; }
.card-body { padding: 16px; display: flex; flex-direction: column; gap: 12px; color: var(--primary-text-color); }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.muted { color: var(--secondary-text-color); }
.small { font-size: 0.85em; }
.stale { color: var(--warning-color, #b45309); font-weight: 500; }
h2, h3 { margin: 0; }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: 8px; }
.header { display: flex; flex-direction: column; gap: 8px; }
.title-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.title { font-size: 1.25rem; display: flex; align-items: center; gap: 8px; }
.controller-name { font-weight: 500; }
.badges { display: flex; flex-wrap: wrap; gap: 8px; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 999px;
  border: 1px solid currentColor; font-size: 0.875rem; }
.badge-label { color: var(--secondary-text-color); }
.tone-ok { color: var(--success-color, #2e7d32); }
.tone-warn { color: var(--warning-color, #b45309); }
.tone-error { color: var(--error-color, #c62828); }
.tone-muted { color: var(--secondary-text-color); }
.tone-active { color: var(--primary-color); }
.badge.tone-ok, .badge.tone-warn, .badge.tone-error, .badge.tone-muted { background: transparent; }
.tabs { display: flex; gap: 4px; overflow-x: auto; border-bottom: 1px solid var(--divider-color); scrollbar-width: thin; }
.tab { flex: 0 0 auto; min-height: 44px; padding: 0 14px; background: none; border: none; border-bottom: 3px solid transparent;
  color: var(--secondary-text-color); font: inherit; font-weight: 500; cursor: pointer; white-space: nowrap; }
.tab[aria-selected="true"] { color: var(--primary-color); border-bottom-color: var(--primary-color); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap: 16px; }
.panel-section { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.hero { border: 1px solid currentColor; border-radius: var(--ha-card-border-radius, 12px); padding: 12px 16px; }
.hero p, .hero dd { color: var(--primary-text-color); }
.hero .hero-state { color: inherit; font-size: 1.3rem; font-weight: 600; margin: 0 0 6px; display: flex; align-items: center; gap: 8px; }
.facts { margin: 0; display: grid; gap: 6px; }
.facts > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; }
.facts dt { color: var(--secondary-text-color); }
.facts dd { margin: 0; text-align: end; }
.big { font-size: 1.6rem; font-variant-numeric: tabular-nums; font-weight: 600; }
.row { display: flex; flex-wrap: wrap; gap: 8px; }
button { min-height: 44px; min-width: 44px; padding: 0 16px; border-radius: 8px; font: inherit; font-weight: 500;
  cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
button:disabled { cursor: not-allowed; opacity: 0.5; }
button:focus-visible, select:focus-visible, input:focus-visible, summary:focus-visible, .tab:focus-visible {
  outline: 3px solid var(--primary-color); outline-offset: 2px; }
.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border: none; }
.danger { background: var(--error-color, #c62828); color: #fff; border: none; }
.secondary { background: transparent; color: var(--primary-text-color); border: 1px solid var(--divider-color); }
.big-button { min-height: 56px; width: 100%; font-size: 1.1rem; }
.stop-block { display: flex; flex-direction: column; gap: 6px; }
.stop-block p { margin: 0; }
.notice { border-radius: 8px; padding: 10px 12px; border: 1px solid currentColor; margin: 0; }
.notice p, .notice li { color: var(--primary-text-color); margin: 0 0 6px; }
.notice ul { margin: 0; padding-inline-start: 20px; }
.confirm { border: 2px solid currentColor; border-radius: 8px; padding: 12px; }
.confirm-q { color: var(--primary-text-color); font-weight: 600; margin: 0 0 6px; }
.confirm p.muted { margin: 0 0 8px; }
.field { display: flex; flex-direction: column; gap: 4px; }
select, input { min-height: 44px; font: inherit; color: var(--primary-text-color); background: var(--card-background-color, transparent);
  border: 1px solid var(--divider-color); border-radius: 8px; padding: 0 10px; }
.stepper { display: flex; align-items: center; gap: 8px; }
.stepper input { width: 5em; text-align: center; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: start; padding: 8px; border-bottom: 1px solid var(--divider-color); vertical-align: top; }
thead th { color: var(--secondary-text-color); font-weight: 500; font-size: 0.875rem; }
tr.watering th, tr.watering td { background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
.programs { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 12px; margin-top: 12px; }
.program { border: 1px solid var(--divider-color); border-radius: 8px; padding: 12px; }
.program h3 { display: flex; align-items: center; gap: 6px; }
.program p { margin: 0 0 6px; }
.program.inactive { opacity: 0.85; border-style: dashed; }
ul.plain { list-style: none; padding: 0; margin: 0; display: grid; gap: 4px; }
details summary { min-height: 44px; display: flex; align-items: center; cursor: pointer; }
code { font-family: var(--code-font-family, monospace); }
.spinner { display: inline-block; width: 1em; height: 1em; border: 2px solid currentColor; border-right-color: transparent;
  border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: -0.15em; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation: none; border-right-color: currentColor; opacity: 0.6; } }
`;

// Smart Garden dashboard for Home Assistant's sidebar.
// Drawn from the integration's own entities; every button calls a Home Assistant service, so the
// garden's safety rules (one zone at a time, time limits) still decide what actually happens.

const PALETTE = {   // categorical, fixed order (validated for colour-blind separation, light + dark)
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"],
};
const RANGES = { "24h": 24, "7d": 24 * 7 };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (st) => { const v = parseFloat(st?.state); return Number.isFinite(v) ? v : null; };
const missing = (st) => !st || st.state === "unavailable" || st.state === "unknown";

function fmtMin(v) {
  if (v == null) return "–";
  if (v < 1 && v > 0) return `${Math.round(v * 60)} s`;
  if (v >= 60) return `${Math.floor(v / 60)} h ${Math.round(v % 60)} min`;
  return `${Math.round(v * 10) / 10} min`;
}

function fmtWhen(iso) {
  if (!iso) return "–";
  const d = new Date(iso); if (isNaN(d)) return "–";
  const now = new Date(), day = 86400000;
  const start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((start(d) - start(now)) / day);
  const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diff === 0) return `Today ${t}`;
  if (diff === 1) return `Tomorrow ${t}`;
  return `${d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })} ${t}`;
}

class SmartGardenPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._range = "24h";
    this._history = null;
    this._built = false;
  }

  set panel(p) { this._entryId = p?.config?.entry_id; }
  set narrow(n) { this._narrow = n; if (this._menu) this._menu.narrow = n; }
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (this._menu) this._menu.hass = h;
    if (first) this._load();
    else if (this._built) this._update();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._loadHistory(), 5 * 60 * 1000);
    this._layoutTimer = setInterval(() => this._load(true), 5 * 60 * 1000);
    this._ro = new ResizeObserver(() => this._drawChart());
    this._ro.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._timer); clearInterval(this._layoutTimer);
    this._ro?.disconnect();
  }

  // ---- data -------------------------------------------------------------------------
  async _load(quiet) {
    try {
      const res = await this._hass.callWS({ type: "smart_garden/layout", entry_id: this._entryId });
      const g = res.gardens[0];
      if (!g) { this._message("Smart Garden isn't connected yet - check Settings → Devices & services."); return; }
      const changed = JSON.stringify(g) !== JSON.stringify(this._g);
      this._g = g;
      if (changed || !this._built) { this._build(); this._loadHistory(); }
    } catch (e) {
      if (!quiet) this._message(`Couldn't load the garden: ${e.message || e}`);
    }
  }

  async _loadHistory() {
    if (!this._g) return;
    const ids = this._g.zones.map((z) => z.moisture).filter(Boolean);
    if (!ids.length) { this._history = {}; this._drawChart(); return; }
    const end = new Date(), start = new Date(end - RANGES[this._range] * 3600 * 1000);
    try {
      this._history = await this._hass.callWS({
        type: "history/history_during_period", start_time: start.toISOString(), end_time: end.toISOString(),
        entity_ids: ids, minimal_response: true, no_attributes: true, significant_changes_only: false,
      });
      this._histRange = [start.getTime(), end.getTime()];
    } catch (e) {
      this._history = {};
    }
    this._drawChart();
  }

  _st(id) { return id ? this._hass.states[id] : undefined; }

  async _call(domain, service, data, done) {
    try {
      await this._hass.callService(domain, service, data);
      if (done) this._toast(done);
    } catch (e) {
      this._toast(e.message || String(e));
    }
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  // ---- page -----------------------------------------------------------------------------
  _message(text) {
    this.shadowRoot.innerHTML = `<style>${CSS}</style>${this._toolbar("Smart Garden")}<div class="wrap"><div class="card"><p>${esc(text)}</p></div></div>`;
    this._wireMenu();
  }

  _toolbar(title) {
    return `<div class="toolbar"><ha-menu-button></ha-menu-button><div class="title">${esc(title)}</div><span class="spacer"></span>
      ${this._g?.app_url ? `<a class="tb-link" href="${esc(this._g.app_url)}" target="_blank" rel="noopener">Open full app</a>` : ""}</div>`;
  }

  _wireMenu() {
    this._menu = this.shadowRoot.querySelector("ha-menu-button");
    if (this._menu) { this._menu.hass = this._hass; this._menu.narrow = this._narrow; }
  }

  _build() {
    const g = this._g;
    const zoneCards = g.zones.map((z, i) => `
      <div class="card zone" data-zone="${z.id}">
        <div class="zone-head"><span class="swatch" data-swatch="${i}"></span><h3>${esc(z.name)}</h3>
          <span class="pill" data-pill="${z.id}"></span></div>
        <div class="soil"><div class="soil-row"><span class="muted">Soil</span><b data-soil="${z.id}">–</b></div>
          <div class="bar"><div class="fill" data-bar="${z.id}"></div></div></div>
        <div class="facts"><span class="muted">Today</span> <b data-today="${z.id}">–</b>
          <span class="muted left-l" data-leftl="${z.id}">Time left</span> <b data-left="${z.id}"></b></div>
        <div class="controls">
          <label class="mins"><input type="number" min="0.5" max="${z.max_minutes}" step="0.5" value="${z.default_minutes}" data-mins="${z.id}" aria-label="Minutes for ${esc(z.name)}"> min</label>
          <button class="btn primary" data-water="${z.id}">Water</button>
          <button class="btn" data-until="${z.id}" title="Water until the soil sensor says it's right">Until soil right</button>
          <button class="btn danger" data-stop="${z.id}">Stop</button>
        </div>
        ${g.admin && z.enabled ? `<label class="toggle"><input type="checkbox" data-enable="${z.id}"> Zone on</label>` : ""}
      </div>`).join("");

    const sensors = g.sensors.filter((s) => s.entity).map((s) => `
      <div class="sensor"><span class="muted">${esc(s.name)}</span><b data-sensor="${esc(s.entity)}" data-kind="${esc(s.kind)}">–</b></div>`).join("");

    const schedules = g.schedules.filter((s) => s.button).map((s) => `
      <button class="btn" data-schedule="${esc(s.button)}"><ha-icon icon="mdi:play-circle"></ha-icon> ${esc(s.name)}</button>`).join("");

    this.shadowRoot.innerHTML = `<style>${CSS}</style>${this._toolbar(g.name)}
    <div class="wrap">
      <div class="top">
      <div class="left">
      <div class="card now">
        <div class="now-main">
          <div><div class="muted small">Watering now</div><div class="big" data-now>–</div>
            <div class="muted small" data-queue></div></div>
          <div class="now-left"><div class="muted small">Time left</div><div class="big" data-timeleft>–</div></div>
        </div>
        <div class="now-actions">
          <button class="btn danger" data-stopall><ha-icon icon="mdi:stop-circle"></ha-icon> Stop all</button>
          ${g.admin && g.garden.automatic ? `<label class="toggle"><input type="checkbox" data-auto> Automatic watering</label>` : ""}
        </div>
      </div>

      <div class="kpis">
        <div class="card kpi"><span class="muted small">Water today</span><b data-kpi="water_today">–</b></div>
        <div class="card kpi"><span class="muted small">Next run</span><b data-kpi="next_run">–</b></div>
        <div class="card kpi"><span class="muted small">Rain</span><b data-kpi="raining">–</b></div>
        <div class="card kpi"><span class="muted small">Relay boards</span><b data-kpi="boards_online">–</b></div>
      </div>
      </div>

      <div class="card chart-card">
        <div class="row"><h2>Soil moisture</h2><span class="spacer"></span>
          <div class="seg">${Object.keys(RANGES).map((r) => `<button data-range="${r}" class="${r === this._range ? "on" : ""}">${r}</button>`).join("")}</div></div>
        <div class="legend" data-legend></div>
        <div class="chart" data-chart><p class="muted small">Loading…</p></div>
        <div class="tip" data-tip hidden></div>
      </div>
      </div>

      <h2 class="section">Zones</h2>
      <div class="zones">${zoneCards}</div>

      <div class="extras">
      ${sensors ? `<div class="card"><h2>Sensors</h2><div class="sensors">${sensors}</div></div>` : ""}
      ${schedules ? `<div class="card"><h2>Run a schedule now</h2><div class="schedules">${schedules}</div>
        <p class="muted small">Starts every zone of the schedule, one after another, after anything already watering.</p></div>` : ""}
      </div>
    </div>`;
    this._wireMenu();
    this._wire();
    this._built = true;
    this._update();
  }

  _wire() {
    const r = this.shadowRoot, g = this._g;
    const zone = (id) => g.zones.find((z) => z.id === Number(id));
    r.querySelectorAll("[data-water]").forEach((b) => b.addEventListener("click", () => {
      const z = zone(b.dataset.water), inp = r.querySelector(`[data-mins="${z.id}"]`);
      const m = parseFloat(inp.value);
      if (!(m > 0 && m <= z.max_minutes)) { this._toast(`Choose 0.5 to ${z.max_minutes} minutes for ${z.name}.`); return; }
      this._call("smart_garden", "water", { entity_id: z.water, minutes: m }, `${z.name}: watering ${m} min (waits its turn if another zone is on).`);
    }));
    r.querySelectorAll("[data-until]").forEach((b) => b.addEventListener("click", () => {
      const z = zone(b.dataset.until);
      this._call("smart_garden", "water", { entity_id: z.water, until_soil: true }, `${z.name}: watering until the soil is right.`);
    }));
    r.querySelectorAll("[data-stop]").forEach((b) => b.addEventListener("click", () => {
      const z = zone(b.dataset.stop);
      this._call("switch", "turn_off", { entity_id: z.water }, `${z.name} stopped.`);
    }));
    r.querySelectorAll("[data-enable]").forEach((c) => c.addEventListener("change", () => {
      const z = zone(c.dataset.enable);
      this._call("switch", c.checked ? "turn_on" : "turn_off", { entity_id: z.enabled },
        c.checked ? `${z.name} turned on.` : `${z.name} turned off - it won't water until turned back on.`);
    }));
    r.querySelector("[data-stopall]")?.addEventListener("click", () =>
      this._call("button", "press", { entity_id: g.garden.stop_all }, "All watering stopped."));
    r.querySelector("[data-auto]")?.addEventListener("change", (e) =>
      this._call("switch", e.target.checked ? "turn_on" : "turn_off", { entity_id: g.garden.automatic },
        e.target.checked ? "Automatic watering on." : "Automatic watering off - schedules and top-ups won't run."));
    r.querySelectorAll("[data-schedule]").forEach((b) => b.addEventListener("click", () =>
      this._call("button", "press", { entity_id: b.dataset.schedule }, `Started ${b.textContent.trim()}.`)));
    r.querySelectorAll("[data-range]").forEach((b) => b.addEventListener("click", () => {
      this._range = b.dataset.range;
      r.querySelectorAll("[data-range]").forEach((x) => x.classList.toggle("on", x === b));
      this._loadHistory();
    }));
    const chart = r.querySelector("[data-chart]");
    chart.addEventListener("pointermove", (e) => this._hover(e));
    chart.addEventListener("pointerleave", () => this._hover(null));
  }

  _colors() { return PALETTE[this._hass?.themes?.darkMode ? "dark" : "light"]; }

  _update() {
    const r = this.shadowRoot, g = this._g, set = (sel, text) => { const el = r.querySelector(sel); if (el) el.textContent = text; };
    const colors = this._colors();
    r.querySelectorAll("[data-swatch]").forEach((s) => { s.style.background = colors[Number(s.dataset.swatch) % colors.length]; });

    const now = this._st(g.garden.watering_now);
    const watering = now && !missing(now) && now.state !== "idle" ? now.state : null;
    set("[data-now]", watering || "Nothing watering");
    set("[data-timeleft]", watering ? fmtMin(num(this._st(g.garden.time_left))) : "–");
    const queue = now?.attributes?.queue || [];
    set("[data-queue]", queue.length ? `${queue.length} more waiting: ${queue.map((q) => (g.zones.find((z) => z.id === q.zone_id) || {}).name || `Zone ${q.zone_id}`).join(", ")}` : "");
    r.querySelector(".now")?.classList.toggle("active", !!watering);

    set('[data-kpi="water_today"]', fmtMin(num(this._st(g.garden.water_today))));
    set('[data-kpi="next_run"]', fmtWhen(this._st(g.garden.next_run)?.state));
    const rain = this._st(g.garden.raining);
    set('[data-kpi="raining"]', missing(rain) ? "–" : rain.state === "on" ? "Raining" : "Dry");
    const boards = this._st(g.garden.boards_online);
    set('[data-kpi="boards_online"]', missing(boards) ? "–" : boards.state === "on" ? "Online" : "Offline");
    r.querySelector('[data-kpi="boards_online"]')?.classList.toggle("bad", boards?.state === "off");
    const auto = r.querySelector("[data-auto]");
    if (auto) auto.checked = this._st(g.garden.automatic)?.state === "on";

    for (const z of g.zones) {
      const w = this._st(z.water), en = this._st(z.enabled);
      const isOn = !!w?.attributes?.watering, queued = !!w?.attributes?.queued;
      const off = en ? en.state === "off" : w?.state === "unavailable";
      const pill = r.querySelector(`[data-pill="${z.id}"]`);
      pill.textContent = off ? "Off" : isOn ? "Watering" : queued ? "Waiting" : "";
      pill.className = "pill " + (off ? "off" : isOn ? "on" : queued ? "wait" : "");
      r.querySelector(`[data-zone="${z.id}"]`).classList.toggle("active", isOn);
      const m = num(this._st(z.moisture));
      set(`[data-soil="${z.id}"]`, m == null ? "no sensor" : `${Math.round(m)}%`);
      const bar = r.querySelector(`[data-bar="${z.id}"]`);
      bar.style.width = `${m == null ? 0 : Math.max(0, Math.min(100, m))}%`;
      set(`[data-today="${z.id}"]`, fmtMin(num(this._st(z.today))));
      const left = num(this._st(z.left));
      set(`[data-left="${z.id}"]`, isOn && left ? fmtMin(left) : "");
      r.querySelector(`[data-leftl="${z.id}"]`).hidden = !(isOn && left);
      r.querySelector(`[data-until="${z.id}"]`).hidden = m == null;
      r.querySelectorAll(`[data-water="${z.id}"], [data-until="${z.id}"]`).forEach((b) => { b.disabled = off; });
      r.querySelector(`[data-stop="${z.id}"]`).disabled = !(isOn || queued);
      const cb = r.querySelector(`[data-enable="${z.id}"]`);
      if (cb) cb.checked = !off;
    }
    r.querySelectorAll("[data-sensor]").forEach((el) => {
      const st = this._st(el.dataset.sensor), kind = el.dataset.kind;
      if (missing(st)) { el.textContent = "–"; return; }
      if (kind === "rain") el.textContent = st.state === "on" ? "Wet" : "Dry";
      else if (kind === "alarm") el.textContent = st.state === "on" ? "Alarm" : "OK";
      else el.textContent = `${Math.round(num(st) * 10) / 10}${st.attributes.unit_of_measurement ? " " + st.attributes.unit_of_measurement : ""}`;
    });
  }

  // ---- chart ------------------------------------------------------------------------------
  _series() {
    const g = this._g, h = this._history || {}, colors = this._colors();
    return g.zones.map((z, i) => ({ z, color: colors[i % colors.length], pts: (h[z.moisture] || [])
      .map((p) => { const v = parseFloat(p.s); return [((p.lu ?? p.lc) || 0) * 1000, Number.isFinite(v) ? v : null]; }) }))
      .filter((s) => s.pts.some((p) => p[1] != null));
  }

  _drawChart() {
    const box = this.shadowRoot?.querySelector("[data-chart]");
    if (!box || !this._g || this._history == null) return;
    const series = this._series();
    const legend = this.shadowRoot.querySelector("[data-legend]");
    if (!series.length) {
      legend.innerHTML = "";
      box.innerHTML = `<p class="muted small">No soil readings in this period${this._g.zones.some((z) => z.moisture) ? "" : " - none of the zones has a soil sensor"}.</p>`;
      return;
    }
    legend.innerHTML = series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.z.name)}</span>`).join("");
    const W = Math.max(280, box.clientWidth || 600), H = 220, L = 36, R = 92, T = 10, B = 24;
    const [t0, t1] = this._histRange;
    const x = (t) => L + ((Math.max(t0, t) - t0) / (t1 - t0)) * (W - L - R), y = (v) => T + (1 - Math.max(0, Math.min(100, v)) / 100) * (H - T - B);
    this._scale = { x, y, t0, t1, L, R, W, H, T, B, series };
    const grid = [0, 25, 50, 75, 100].map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${L - 6}" y="${y(v) + 4}" class="axis" text-anchor="end">${v}%</text>`).join("");
    const ticks = [];
    const hours = (t1 - t0) / 3600000, step = hours > 48 ? 24 : 6;
    const first = new Date(t0); first.setMinutes(0, 0, 0); first.setHours(Math.ceil(first.getHours() / step) * step);
    for (let t = first.getTime(); t <= t1; t += step * 3600000) {
      const d = new Date(t);
      const label = step === 24 ? d.toLocaleDateString([], { weekday: "short" }) : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      ticks.push(`<text x="${x(t)}" y="${H - 6}" class="axis" text-anchor="middle">${label}</text>`);
    }
    const lines = series.map((s) => {
      const pts = [...s.pts, [t1, s.pts[s.pts.length - 1][1]]];           // carry the latest state to now
      let d = "", prev = null;
      for (const [t, v] of pts) {                                          // readings are steps; no reading = gap
        if (v == null) { if (prev != null) d += `H${x(t)}`; prev = null; continue; }
        d += prev == null ? `M${x(t)},${y(v)}` : `H${x(t)}V${y(v)}`; prev = v;
      }
      return `<path d="${d}" stroke="${s.color}" class="line"/>`;
    }).join("");
    // direct labels at the right end (only for zones reading now), nudged apart so they never overlap
    const ends = series.filter((s) => s.pts[s.pts.length - 1][1] != null)
      .map((s) => ({ s, v: s.pts[s.pts.length - 1][1], yy: y(s.pts[s.pts.length - 1][1]) })).sort((a, b) => a.yy - b.yy);
    for (let i = 1; i < ends.length; i++) ends[i].yy = Math.max(ends[i].yy, ends[i - 1].yy + 13);
    const labels = ends.map((e) => `<circle cx="${W - R + 6}" cy="${e.yy}" r="3.5" fill="${e.s.color}"/><text x="${W - R + 13}" y="${e.yy + 4}" class="end">${esc(e.s.z.name)} ${Math.round(e.v)}%</text>`).join("");
    box.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Soil moisture by zone">${grid}${ticks.join("")}${lines}${labels}<line class="cross" data-cross x1="0" x2="0" y1="${T}" y2="${H - B}" visibility="hidden"/></svg>`;
  }

  _hover(e) {
    const tip = this.shadowRoot.querySelector("[data-tip]"), cross = this.shadowRoot.querySelector("[data-cross]");
    const sc = this._scale;
    if (!e || !sc || !cross) { if (tip) tip.hidden = true; cross?.setAttribute("visibility", "hidden"); return; }
    const rect = e.currentTarget.getBoundingClientRect(), px = e.clientX - rect.left;
    if (px < sc.L || px > sc.W - sc.R) { tip.hidden = true; cross.setAttribute("visibility", "hidden"); return; }
    const t = sc.t0 + ((px - sc.L) / (sc.W - sc.L - sc.R)) * (sc.t1 - sc.t0);
    const rows = sc.series.map((s) => { let v = null; for (const [pt, pv] of s.pts) { if (pt <= t) v = pv; else break; } return { s, v }; }).filter((r) => r.v != null);  // null = no reading then
    cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("visibility", "visible");
    tip.innerHTML = `<b>${new Date(t).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}</b>` +
      rows.map((r) => `<div><i style="background:${r.s.color}"></i>${esc(r.s.z.name)} <b>${Math.round(r.v)}%</b></div>`).join("");
    tip.hidden = !rows.length;
    const card = tip.parentElement.getBoundingClientRect();
    const left = e.clientX - card.left + 14;
    tip.style.left = `${Math.min(left, card.width - tip.offsetWidth - 8)}px`;
    tip.style.top = `${e.clientY - card.top + 10}px`;
  }
}

const CSS = `
:host { display: block; background: var(--primary-background-color); color: var(--primary-text-color); min-height: 100%; font-family: var(--paper-font-body1_-_font-family, inherit); }
.toolbar { display: flex; align-items: center; height: var(--header-height, 56px); padding: 0 12px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); position: sticky; top: 0; z-index: 2; }
.toolbar .title { font-size: 20px; margin-left: 8px; }
.tb-link { color: inherit; font-size: 14px; text-decoration: none; border: 1px solid currentColor; border-radius: 16px; padding: 4px 12px; opacity: .9; }
.spacer { flex: 1; }
.wrap { max-width: 2200px; margin: 0 auto; padding: 16px; display: grid; gap: 16px; container-type: inline-size; }
.top, .left, .extras { display: grid; gap: 16px; align-content: start; min-width: 0; }
.chart-card { min-width: 0; }
/* Wide screens: status and figures beside the chart, sensors beside schedules - no empty sides */
@container (min-width: 1000px) {
  .top { grid-template-columns: minmax(360px, 2fr) 3fr; }
  .left .kpis { grid-template-columns: repeat(2, 1fr); }
  .extras { grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); }
}
.card { background: var(--card-background-color, #fff); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color); padding: 16px; position: relative; }
h2 { font-size: 16px; font-weight: 500; margin: 0 0 12px; }
h2.section { margin: 8px 0 -4px; }
h3 { font-size: 16px; font-weight: 500; margin: 0; flex: 1; }
.muted { color: var(--secondary-text-color); }
.small { font-size: 13px; }
.row { display: flex; align-items: center; gap: 8px; }
.now { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; align-items: center; }
.now.active { border-color: var(--primary-color); }
.now-main { display: flex; gap: 32px; flex-wrap: wrap; }
.big { font-size: 26px; font-weight: 500; }
.now-actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }
.kpi { display: flex; flex-direction: column; gap: 4px; }
.kpi b { font-size: 20px; font-weight: 500; }
.kpi b.bad { color: var(--error-color); }
.zones { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 16px; }
.zone.active { border-color: var(--primary-color); box-shadow: 0 0 0 1px var(--primary-color); }
.zone-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.swatch { width: 10px; height: 10px; border-radius: 50%; flex: none; }
.pill { font-size: 12px; border-radius: 10px; padding: 2px 8px; }
.pill:empty { display: none; }
.pill.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
.pill.wait { background: var(--warning-color, #ffa600); color: #000; }
.pill.off { background: var(--disabled-color, #bdbdbd); color: var(--primary-text-color); }
.soil-row { display: flex; justify-content: space-between; margin-bottom: 4px; }
.bar { height: 8px; border-radius: 4px; background: var(--secondary-background-color, #eee); overflow: hidden; }
.fill { height: 100%; background: var(--primary-color); border-radius: 4px; transition: width .4s; }
.facts { margin: 12px 0; font-size: 14px; }
.left-l { margin-left: 12px; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.mins { display: flex; align-items: center; gap: 4px; font-size: 14px; color: var(--secondary-text-color); }
.mins input { width: 64px; padding: 6px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
.btn { font: inherit; font-size: 14px; border-radius: 18px; padding: 6px 14px; border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color); cursor: pointer; display: inline-flex; align-items: center; gap: 4px; min-height: 36px; }
.btn ha-icon { --mdc-icon-size: 18px; }
.btn:hover:not(:disabled) { background: var(--secondary-background-color); }
.btn:disabled { opacity: .45; cursor: default; }
.btn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
.btn.danger { color: var(--error-color); border-color: var(--error-color); }
.btn[hidden] { display: none; }
.toggle { display: flex; align-items: center; gap: 6px; font-size: 14px; margin-top: 10px; cursor: pointer; }
.now-actions .toggle { margin-top: 0; }
.sensors { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
.sensor { display: flex; flex-direction: column; gap: 2px; }
.sensor b { font-size: 18px; font-weight: 500; }
.schedules { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.seg { display: inline-flex; border: 1px solid var(--divider-color); border-radius: 16px; overflow: hidden; }
.seg button { font: inherit; font-size: 13px; border: 0; background: transparent; color: var(--secondary-text-color); padding: 4px 12px; cursor: pointer; min-height: 30px; }
.seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 13px; color: var(--secondary-text-color); margin-bottom: 6px; }
.legend i, .tip i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: -1px; }
.chart { width: 100%; overflow: hidden; touch-action: pan-y; }
.chart svg { display: block; }
.grid { stroke: var(--divider-color); stroke-width: 1; }
.axis { fill: var(--secondary-text-color); font-size: 11px; }
.line { fill: none; stroke-width: 2; stroke-linejoin: round; }
.end { fill: var(--primary-text-color); font-size: 12px; }
.cross { stroke: var(--secondary-text-color); stroke-width: 1; stroke-dasharray: 3 3; }
.tip { position: absolute; pointer-events: none; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 8px; padding: 8px 10px; font-size: 13px; box-shadow: 0 2px 8px rgba(0,0,0,.15); z-index: 3; min-width: 140px; }
.tip div { margin-top: 2px; }
@media (max-width: 600px) { .wrap { padding: 8px; gap: 12px; } .big { font-size: 22px; } }
`;

customElements.get("smart-garden-panel") || customElements.define("smart-garden-panel", SmartGardenPanel);

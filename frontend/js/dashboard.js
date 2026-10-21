/* Dashboard orchestration: onboarding, fetch, render widgets, wire actions. */

const state = { profile: null, summary: null, history: null, forecast: null,
                peak: null, heatmap: null, appliances: null, budget: null, anomalies: null };

const TARIFF = { low: 60, middle: 68, high: 75 };

/* ---------- bootstrap ---------- */
async function initDashboard() {
  if (!API.token()) { window.location.href = "/login"; return; }
  renderUser();
  wireActions();
  await boot();
}

function renderUser() {
  const u = API.user() || {};
  setText("userName", u.full_name || "User");
  setText("userEmail", u.email || "");
  setText("userAvatar", initials(u.full_name));
  setText("meterSub", `Meter ${u.meter_id || "—"}`);
}

/* Decide between onboarding and the populated dashboard. */
async function boot() {
  try {
    const profile = await API.get("/profile");
    state.profile = profile.has_profile ? profile : null;
    if (!state.profile) {
      openSetup(null);   // first run -> mandatory setup
      return;
    }
    await loadAll();
  } catch (e) {
    toast(e.message || "Could not load your meter", true);
  }
}

async function loadAll() {
  try {
    const [summary, history, forecast, peak, heatmap, appliances, budget, anomalies] =
      await Promise.all([
        API.get("/usage/summary"),
        API.get("/usage/history?days=30"),
        API.get("/usage/forecast"),
        API.get("/usage/peak-hours"),
        API.get("/usage/heatmap"),
        API.get("/usage/appliances"),
        API.get("/usage/budget"),
        API.get("/usage/anomalies"),
      ]);
    Object.assign(state, { summary, history, forecast, peak, heatmap, appliances, budget, anomalies });

    renderSummary();
    renderSmartAlerts();
    renderCharts();
    renderHeatmap();
    renderAppliances();
    renderAnomalies();
    renderRecharges();
    renderBudget();
    loadAI();
  } catch (e) {
    toast(e.message || "Failed to load dashboard", true);
  }
}

/* ---------- KPIs ---------- */
function renderSummary() {
  const s = state.summary, f = state.forecast;
  if (!s || !s.has_data) return;

  setHtml("kpiAvgDaily", `${fmt(s.avg_daily_kwh, 1)}<small>kWh/day</small>`);
  setText("kpiAvgDailyFoot", `${s.household_size} people · ${s.income_level} income`);

  setHtml("kpiMonthly", `${fmt(s.total_month_kwh, 0)}<small>kWh</small>`);
  setText("kpiMonthlyFoot", `Estimated 30 days`);

  setHtml("kpiBalance", naira(s.remaining_balance));
  setText("kpiBalanceFoot", `≈ ${naira(s.avg_daily_cost)}/day spend`);

  setText("kpiExhaust", s.predicted_exhaustion_date);
  setText("kpiExhaustFoot", `~${f.days_until_exhaustion} days of cover left`);

  const spikePct = Math.round((f.spike_probability || 0) * 100);
  setHtml("kpiSpike", `${spikePct}<small>%</small>`);
  setText("kpiSpikeFoot", `Peak hour ${s.peak_hour_label}`);
}

/* ---------- Smart alerts ---------- */
function renderSmartAlerts() {
  const s = state.summary, f = state.forecast, a = state.anomalies;
  const wrap = document.getElementById("smartAlerts");
  if (!wrap) return;
  const alerts = [];

  if (f.days_until_exhaustion <= 4)
    alerts.push(["high", "Recharge soon",
      `Balance likely runs out in about ${f.days_until_exhaustion} days (around ${f.recharge_exhaustion_date}).`]);

  const nightHit = (a.anomalies || []).some((x) => x.type === "Night usage");
  if (nightHit)
    alerts.push(["high", "Night usage high", "Unusual overnight consumption was detected recently — worth checking."]);

  if ((f.spike_probability || 0) >= 0.5)
    alerts.push(["medium", "Spike risk", `Elevated chance (${Math.round(f.spike_probability * 100)}%) of a usage spike this week.`]);

  if ((s.weekend_avg_kwh || 0) > (s.weekday_avg_kwh || 0) * 1.25)
    alerts.push(["medium", "Weekend heavy", "Weekend usage runs notably higher than weekdays."]);

  if (!alerts.length)
    alerts.push(["ok", "On track", "Consumption is steady and your balance is on track."]);

  wrap.innerHTML = alerts.slice(0, 3).map(([sev, t, m]) => `
    <div class="alert ${sev === "high" ? "high" : sev === "medium" ? "medium" : ""}">
      <span class="sev" style="${sev === "ok" ? "background:var(--green);box-shadow:0 0 0 3px rgba(70,192,138,.16)" : ""}"></span>
      <div class="body"><div class="t">${esc(t)}</div><div class="m">${esc(m)}</div></div>
    </div>`).join("");
}

/* ---------- Charts ---------- */
function renderCharts() {
  if (state.history && state.forecast)
    Charts.usageTrend("usageChart", state.history.daily, state.forecast.next_days);
  if (state.peak)
    Charts.peakHours("peakChart", state.peak.hours, state.peak.values);
  if (state.appliances)
    Charts.appliances("applianceChart", state.appliances.appliances);
}

/* ---------- Heatmap ---------- */
function hexToRgb(hex) {
  const m = hex.replace("#", "");
  const n = parseInt(m.length === 3 ? m.split("").map((c) => c + c).join("") : m, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function renderHeatmap() {
  const hm = state.heatmap;
  const wrap = document.getElementById("heatmap");
  if (!hm || !wrap) return;
  const [r, g, b] = hexToRgb(cssVar("--accent") || "#5b8cff");
  const max = Math.max(...hm.matrix.flat(), 0.001);

  let html = "";
  hm.matrix.forEach((row, di) => {
    html += `<div class="hm-row"><span class="hm-label">${hm.days[di]}</span>`;
    row.forEach((v, hh) => {
      const a = Math.max(0.05, v / max);
      html += `<div class="hm-cell" style="background:rgba(${r},${g},${b},${a.toFixed(2)})" title="${hm.days[di]} ${String(hh).padStart(2, "0")}:00 · ${fmt(v, 2)} kWh"></div>`;
    });
    html += `</div>`;
  });
  html += `<div class="hm-axis"><span></span>` +
    hm.hours.map((h) => (h % 3 === 0 ? `<span>${String(h).padStart(2, "0")}</span>` : "<span></span>")).join("") +
    `</div>`;
  wrap.innerHTML = html;

  const legend = document.getElementById("heatmapLegend");
  if (legend) {
    legend.innerHTML = `Low <span class="scale">` +
      [0.1, 0.3, 0.55, 0.8, 1].map((a) => `<i style="background:rgba(${r},${g},${b},${a})"></i>`).join("") +
      `</span> High`;
  }
}

/* ---------- Appliances legend ---------- */
function renderAppliances() {
  const ap = state.appliances;
  const el = document.getElementById("applianceLegend");
  if (!ap || !el) return;
  const ramp = [cssVar("--accent"), cssVar("--green"), cssVar("--amber"), cssVar("--accent-2"), cssVar("--red"), cssVar("--muted")];
  el.innerHTML = ap.appliances.map((a, i) => `
    <div class="leg-row">
      <span class="leg-dot" style="background:${ramp[i % ramp.length]}"></span>
      <span class="leg-name">${esc(a.name)}</span>
      <span class="leg-val mono">${fmt(a.kwh, 0)} kWh · ${fmt(a.pct, 0)}%</span>
    </div>`).join("");
}

/* ---------- Anomalies ---------- */
function renderAnomalies() {
  const a = state.anomalies;
  const list = document.getElementById("anomalyList");
  setText("anomalyCount", String(a.count || 0));
  if (!a.anomalies || !a.anomalies.length) {
    list.innerHTML = `<div class="empty-state">No anomalies in your estimated usage. Detection sharpens as your real pattern builds up.</div>`;
    return;
  }
  list.innerHTML = a.anomalies.map((x) => `
    <div class="alert ${x.severity}">
      <span class="sev"></span>
      <div class="body">
        <div class="t">${esc(x.type)} <span class="pill ${x.severity === "high" ? "red" : "amber"}"><span class="dot"></span>${x.severity}</span></div>
        <div class="m">${esc(x.message)}</div>
        <div class="ts">${esc(x.timestamp)} · ${fmt(x.units, 2)} kWh (≈${fmt(x.deviation_pct, 0)}% above norm)</div>
      </div>
    </div>`).join("");
}

/* ---------- Recharge timeline ---------- */
function renderRecharges() {
  const rows = (state.history && state.history.recharges) || [];
  const body = document.getElementById("rechargeBody");
  if (!body) return;
  if (!rows.length) { body.innerHTML = `<tr><td colspan="3" class="empty-state">No recharges logged yet.</td></tr>`; return; }
  body.innerHTML = rows.slice(0, 8).map((r) => `
    <tr>
      <td>${r.date}</td>
      <td class="num tag-amt">+${naira(r.amount)}</td>
      <td class="num mono">${naira(r.balance_after)}</td>
    </tr>`).join("");
}

/* ---------- Budget ---------- */
function renderBudget() {
  const b = state.budget;
  if (!b || !b.available) return;
  setHtml("budgetAmount", `${naira(b.recommended_amount)}`);
  setText("budgetCovers", `${fmt(b.covers_days, 0)} days`);
  setText("budgetDaily", naira(b.avg_daily_cost));
  setText("budgetBalance", naira(b.current_balance));
  setText("budgetTariff", `${naira(b.tariff)}/kWh`);
  const pct = Math.min(100, (b.covers_days / (b.cover_target_days * 1.5)) * 100);
  const bar = document.getElementById("budgetBar");
  if (bar) bar.style.width = pct + "%";
}

/* ---------- AI ---------- */
async function loadAI(focus) {
  const body = document.getElementById("aiBody");
  const btn = document.getElementById("aiRegen");
  body.classList.add("skeleton");
  body.textContent = "Generating analysis...";
  if (btn) btn.disabled = true;
  try {
    const res = await API.post("/ai/analyze", { focus: focus || null });
    body.classList.remove("skeleton");
    body.innerHTML = formatAI(res.analysis);
    setText("aiSource", res.source === "gemini" ? "Gemini" : "Built-in model");
  } catch (e) {
    body.classList.remove("skeleton");
    body.textContent = "Could not generate analysis right now.";
  } finally {
    if (btn) btn.disabled = false;
  }
}

function formatAI(text) {
  return (text || "").split("\n").map((line) => {
    const t = line.trim();
    if (/^\d+\.\s/.test(t)) return `<span class="h">${esc(t)}</span>`;
    return esc(line);
  }).join("\n");
}

/* ---------- Setup / edit profile modal ---------- */
function openSetup(prefill) {
  const editing = !!prefill;
  setText("setupTitle", editing ? "Edit your meter" : "Set up your meter");
  document.getElementById("setupCancel").style.display = editing ? "" : "none";
  document.getElementById("setupError").textContent = "";

  const p = prefill || {};
  setVal("pfHousehold", p.household_size ?? 4);
  document.getElementById("pfIncome").value = p.income_level ?? "middle";
  setVal("pfAc", p.ac_hours ?? 0);
  setVal("pfTv", p.tv_hours ?? 5);
  setVal("pfFan", p.fan_hours ?? 10);
  setVal("pfWasher", p.washer_loads ?? 2);
  document.getElementById("pfFridge").checked = p.has_fridge === undefined ? true : !!p.has_fridge;
  setVal("pfBalance", p.balance ?? 5000);

  showModal("setupModal");
}

async function submitProfile(e) {
  e.preventDefault();
  const btn = document.getElementById("setupSave");
  const err = document.getElementById("setupError");
  err.textContent = "";
  btn.disabled = true; btn.textContent = "Saving...";
  try {
    const body = {
      household_size: parseInt(getVal("pfHousehold"), 10),
      income_level: document.getElementById("pfIncome").value,
      ac_hours: parseFloat(getVal("pfAc")) || 0,
      has_fridge: document.getElementById("pfFridge").checked,
      tv_hours: parseFloat(getVal("pfTv")) || 0,
      fan_hours: parseFloat(getVal("pfFan")) || 0,
      washer_loads: parseFloat(getVal("pfWasher")) || 0,
      balance: parseFloat(getVal("pfBalance")) || 0,
    };
    const res = await API.post("/profile", body);
    state.profile = { has_profile: true, ...res };
    hideModal("setupModal");
    toast("Meter updated — analyzing your usage");
    await loadAll();
  } catch (e2) {
    err.textContent = e2.message || "Could not save";
  } finally {
    btn.disabled = false; btn.textContent = "Save & analyze";
  }
}

/* ---------- Recharge modal ---------- */
function openRecharge() {
  if (!state.profile) { openSetup(null); return; }
  document.getElementById("rechargeError").textContent = "";
  setVal("rcAmount", 5000);
  updateRechargeUnits();
  showModal("rechargeModal");
}

function currentTariff() {
  if (state.summary && state.summary.tariff) return state.summary.tariff;
  const inc = state.profile && state.profile.income_level;
  return TARIFF[inc] || 68;
}

function updateRechargeUnits() {
  const amt = parseFloat(getVal("rcAmount")) || 0;
  const units = amt / currentTariff();
  setText("rcUnits", amt > 0 ? `≈ ${fmt(units, 1)} units (kWh) at ${naira(currentTariff())}/kWh` : "");
}

async function submitRecharge(e) {
  e.preventDefault();
  const err = document.getElementById("rechargeError");
  err.textContent = "";
  try {
    const amount = parseFloat(getVal("rcAmount"));
    if (!amount || amount <= 0) { err.textContent = "Enter an amount"; return; }
    const res = await API.post("/recharge", { amount });
    hideModal("rechargeModal");
    toast(`Recharged ${naira(amount)} — new balance ${naira(res.balance)}`);
    await loadAll();
  } catch (e2) {
    err.textContent = e2.message || "Recharge failed";
  }
}

/* ---------- Modal helpers ---------- */
function showModal(id) { document.getElementById(id).classList.add("show"); }
function hideModal(id) { document.getElementById(id).classList.remove("show"); }

/* ---------- Exports ---------- */
async function downloadAuthed(path, fallback) {
  toast("Preparing export...");
  try {
    const res = await fetch(API.base + path, { headers: { Authorization: "Bearer " + API.token() } });
    if (!res.ok) throw new Error();
    const blob = await res.blob();
    const cd = res.headers.get("content-disposition") || "";
    const m = cd.match(/filename="?([^"]+)"?/);
    const name = m ? m[1] : fallback;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast("Export ready");
  } catch {
    toast("Export failed", true);
  }
}

/* ---------- Wiring ---------- */
function toggleDrawer() {
  document.querySelector(".sidebar").classList.toggle("open");
  document.getElementById("sidebarBackdrop").classList.toggle("show");
}
function closeDrawer() {
  document.querySelector(".sidebar").classList.remove("open");
  document.getElementById("sidebarBackdrop").classList.remove("show");
}

function wireActions() {
  // Mobile navigation drawer (hamburger)
  const menuBtn = document.getElementById("menuBtn");
  const backdrop = document.getElementById("sidebarBackdrop");
  if (menuBtn) menuBtn.addEventListener("click", toggleDrawer);
  if (backdrop) backdrop.addEventListener("click", closeDrawer);

  document.getElementById("themeToggle").addEventListener("click", () => {
    Theme.toggle();
    renderCharts(); renderHeatmap(); renderAppliances();
  });
  document.getElementById("logoutBtn").addEventListener("click", () => {
    API.clear(); window.location.href = "/login";
  });
  document.getElementById("refreshBtn").addEventListener("click", () => { if (state.profile) { loadAll(); toast("Refreshed"); } });
  document.getElementById("exportCsv").addEventListener("click", () => downloadAuthed("/export/csv", "usage.csv"));
  document.getElementById("exportPdf").addEventListener("click", () => downloadAuthed("/export/pdf", "report.pdf"));
  document.getElementById("aiRegen").addEventListener("click", () => loadAI(document.getElementById("aiFocus").value.trim()));
  document.getElementById("aiFocus").addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadAI(e.target.value.trim());
  });

  // Profile + recharge
  document.getElementById("editProfileBtn").addEventListener("click", () => openSetup(state.profile));
  document.getElementById("rechargeBtn").addEventListener("click", openRecharge);
  document.getElementById("profileForm").addEventListener("submit", submitProfile);
  document.getElementById("rechargeForm").addEventListener("submit", submitRecharge);
  document.getElementById("setupCancel").addEventListener("click", () => hideModal("setupModal"));
  document.getElementById("rechargeCancel").addEventListener("click", () => hideModal("rechargeModal"));
  document.getElementById("rcAmount").addEventListener("input", updateRechargeUnits);

  // Click backdrop to close (only when not the mandatory first setup)
  document.querySelectorAll(".modal-overlay").forEach((ov) =>
    ov.addEventListener("click", (e) => {
      if (e.target !== ov) return;
      if (ov.id === "setupModal" && !state.profile) return; // first setup is mandatory
      ov.classList.remove("show");
    }));

  // Sidebar nav smooth-scroll to sections.
  document.querySelectorAll(".nav-item[data-section]").forEach((it) =>
    it.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
      it.classList.add("active");
      const target = document.getElementById(it.dataset.section);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      closeDrawer();
    }));
}

/* ---------- tiny DOM helpers ---------- */
function setText(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }
function setHtml(id, v) { const e = document.getElementById(id); if (e) e.innerHTML = v; }
function setVal(id, v) { const e = document.getElementById(id); if (e) e.value = v; }
function getVal(id) { const e = document.getElementById(id); return e ? e.value : ""; }
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

document.addEventListener("DOMContentLoaded", initDashboard);

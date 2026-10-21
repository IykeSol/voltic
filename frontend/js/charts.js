/* Chart.js builders. Each reads the current theme's CSS variables so charts
   restyle correctly when the user flips dark/light. */

const Charts = (() => {
  const registry = {};

  function palette() {
    return {
      accent: cssVar("--accent") || "#5b8cff",
      accent2: cssVar("--accent-2") || "#7aa2ff",
      text: cssVar("--text") || "#f5f7fa",
      muted: cssVar("--muted") || "#9aa4b2",
      grid: cssVar("--border") || "rgba(255,255,255,0.06)",
      green: cssVar("--green") || "#46c08a",
      amber: cssVar("--amber") || "#e0a548",
      red: cssVar("--red") || "#e5654b",
    };
  }

  function baseOpts(p) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: cssVar("--card"),
          borderColor: cssVar("--border-strong"),
          borderWidth: 1,
          titleColor: p.text,
          bodyColor: p.muted,
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
        },
      },
      scales: {
        x: {
          grid: { display: false, drawBorder: false },
          ticks: { color: p.muted, font: { size: 11, family: "Inter" }, maxRotation: 0, autoSkipPadding: 16 },
        },
        y: {
          grid: { color: p.grid, drawBorder: false },
          border: { display: false },
          ticks: { color: p.muted, font: { size: 11, family: "Inter" }, padding: 8 },
        },
      },
    };
  }

  function destroy(id) {
    if (registry[id]) { registry[id].destroy(); delete registry[id]; }
  }

  function gradient(ctx, color) {
    const g = ctx.createLinearGradient(0, 0, 0, 260);
    g.addColorStop(0, color + "55");
    g.addColorStop(1, color + "02");
    return g;
  }

  /* Daily usage history + dashed forecast on one timeline. */
  function usageTrend(id, history, forecast) {
    const cv = document.getElementById(id);
    if (!cv) return;
    destroy(id);
    const p = palette();
    const ctx = cv.getContext("2d");

    const histLabels = history.map((d) => d.date.slice(5));
    const fcLabels = forecast.map((d) => d.date.slice(5));
    const labels = histLabels.concat(fcLabels);

    const histData = history.map((d) => d.kwh).concat(forecast.map(() => null));
    // Bridge the gap so the dashed line connects to the last actual point.
    const fcData = history.map(() => null);
    if (history.length) fcData[history.length - 1] = history[history.length - 1].kwh;
    forecast.forEach((d) => fcData.push(d.predicted_kwh));

    const opts = baseOpts(p);
    opts.plugins.tooltip.callbacks = {
      label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y, 2)} kWh`,
    };

    registry[id] = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Actual", data: histData, borderColor: p.accent,
            backgroundColor: gradient(ctx, p.accent), borderWidth: 2,
            fill: true, tension: 0.34, pointRadius: 0, pointHoverRadius: 4,
            pointHoverBackgroundColor: p.accent,
          },
          {
            label: "Forecast", data: fcData, borderColor: p.accent2,
            borderWidth: 2, borderDash: [5, 4], fill: false, tension: 0.34,
            pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: p.accent2,
          },
        ],
      },
      options: opts,
    });
  }

  function peakHours(id, hours, values) {
    const cv = document.getElementById(id);
    if (!cv) return;
    destroy(id);
    const p = palette();
    const peak = values.indexOf(Math.max(...values));
    const colors = values.map((_, i) => (i === peak ? p.accent : p.accent + "4d"));

    const opts = baseOpts(p);
    opts.plugins.tooltip.callbacks = { label: (c) => `${fmt(c.parsed.y, 2)} kWh avg` };

    registry[id] = new Chart(cv.getContext("2d"), {
      type: "bar",
      data: {
        labels: hours.map((h) => String(h).padStart(2, "0")),
        datasets: [{ data: values, backgroundColor: colors, borderRadius: 4, borderSkipped: false, maxBarThickness: 18 }],
      },
      options: opts,
    });
  }

  function appliances(id, items) {
    const cv = document.getElementById(id);
    if (!cv) return;
    destroy(id);
    const p = palette();
    const colorRamp = [p.accent, p.green, p.amber, p.accent2, p.red, p.muted];
    const labels = items.map((i) => i.name);
    const data = items.map((i) => i.kwh);

    registry[id] = new Chart(cv.getContext("2d"), {
      type: "doughnut",
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: items.map((_, i) => colorRamp[i % colorRamp.length]),
          borderColor: cssVar("--card"), borderWidth: 2, hoverOffset: 6,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: "66%",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: cssVar("--card"), borderColor: cssVar("--border-strong"), borderWidth: 1,
            titleColor: p.text, bodyColor: p.muted, padding: 10, cornerRadius: 8,
            callbacks: { label: (c) => ` ${c.label}: ${fmt(c.parsed, 1)} kWh` },
          },
        },
      },
    });
  }

  /* Small sparkline used on the landing hero. */
  function spark(id, values) {
    const cv = document.getElementById(id);
    if (!cv) return;
    destroy(id);
    const p = palette();
    const ctx = cv.getContext("2d");
    registry[id] = new Chart(ctx, {
      type: "line",
      data: {
        labels: values.map((_, i) => i),
        datasets: [{
          data: values, borderColor: p.accent, backgroundColor: gradient(ctx, p.accent),
          borderWidth: 2, fill: true, tension: 0.4, pointRadius: 0,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
        animation: { duration: 1200 },
      },
    });
  }

  return { usageTrend, peakHours, appliances, spark, destroy };
})();

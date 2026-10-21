/* Landing page: hero sparkline + a gently animating "live" demo reading. */

function genSeries(n, base, vary) {
  const out = [];
  let v = base;
  for (let i = 0; i < n; i++) {
    v += (Math.random() - 0.5) * vary;
    v = Math.max(base * 0.45, Math.min(base * 1.6, v));
    // Evening bump to look like real household usage.
    const hourBump = i % 24 >= 18 && i % 24 <= 22 ? base * 0.4 : 0;
    out.push(Number((v + hourBump).toFixed(2)));
  }
  return out;
}

function initLanding() {
  // Reflect auth state in the nav.
  if (API.token()) {
    const cta = document.getElementById("navCta");
    if (cta) { cta.textContent = "Open dashboard"; cta.href = "/dashboard"; }
    const login = document.getElementById("navLogin");
    if (login) login.classList.add("hidden");
  }

  const tt = document.getElementById("themeToggle");
  if (tt) tt.addEventListener("click", () => {
    Theme.toggle();
    drawCharts(); // re-theme
  });

  drawCharts();
  animateLiveValue();
}

let liveBase = 1.9;
function drawCharts() {
  Charts.spark("heroSpark", genSeries(48, 1.8, 0.6));
  Charts.spark("previewSpark", genSeries(60, 2.2, 0.8));
}

function animateLiveValue() {
  const el = document.getElementById("liveValue");
  if (!el) return;
  setInterval(() => {
    liveBase += (Math.random() - 0.5) * 0.25;
    liveBase = Math.max(0.6, Math.min(3.4, liveBase));
    el.textContent = liveBase.toFixed(2);
  }, 1800);
}

document.addEventListener("DOMContentLoaded", initLanding);

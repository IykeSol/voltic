/* Shared API client, session, theme and small helpers (loaded on every page). */

const API = {
  base: "",

  token() { return localStorage.getItem("pm_token"); },
  user() {
    try { return JSON.parse(localStorage.getItem("pm_user")); }
    catch { return null; }
  },
  setSession(token, user) {
    localStorage.setItem("pm_token", token);
    localStorage.setItem("pm_user", JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem("pm_token");
    localStorage.removeItem("pm_user");
  },

  async req(path, opts = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    const t = this.token();
    if (t) headers["Authorization"] = "Bearer " + t;

    const res = await fetch(this.base + path, Object.assign({}, opts, { headers }));
    if (res.status === 401 && !path.startsWith("/auth")) {
      this.clear();
      window.location.href = "/login";
      throw new Error("Session expired");
    }
    const ct = res.headers.get("content-type") || "";
    if (!res.ok) {
      let msg = "Request failed";
      if (ct.includes("json")) {
        const j = await res.json().catch(() => ({}));
        msg = j.detail || msg;
      }
      throw new Error(msg);
    }
    return ct.includes("json") ? res.json() : res;
  },

  get(p) { return this.req(p); },
  post(p, body) { return this.req(p, { method: "POST", body: JSON.stringify(body) }); },
};

/* ---------- Theme ---------- */
const Theme = {
  init() {
    const t = localStorage.getItem("pm_theme") || "dark";
    document.documentElement.setAttribute("data-theme", t);
  },
  current() { return document.documentElement.getAttribute("data-theme") || "dark"; },
  toggle() {
    const next = this.current() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("pm_theme", next);
    window.dispatchEvent(new CustomEvent("themechange", { detail: next }));
    return next;
  },
};
Theme.init();

/* ---------- Helpers ---------- */
function naira(n) {
  return "₦" + Number(n || 0).toLocaleString("en-NG", { maximumFractionDigits: 0 });
}
function fmt(n, d = 1) {
  return Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function initials(name) {
  return (name || "U").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
}

let _toastTimer;
function toast(msg, isError = false) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* Login / signup page logic. */

function switchTab(tab) {
  document.querySelectorAll(".auth-tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === tab));
  document.getElementById("loginForm").classList.toggle("hidden", tab !== "login");
  document.getElementById("signupForm").classList.toggle("hidden", tab !== "signup");
  document.getElementById("authError").textContent = "";
}

function showError(msg) {
  document.getElementById("authError").textContent = msg;
}

async function submit(btn, fn) {
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "Please wait...";
  showError("");
  try {
    const data = await fn();
    API.setSession(data.access_token, data.user);
    window.location.href = "/dashboard";
  } catch (e) {
    showError(e.message || "Something went wrong");
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

function initAuthPage() {
  // Already signed in -> straight to the dashboard.
  if (API.token()) { window.location.href = "/dashboard"; return; }

  document.querySelectorAll(".auth-tab").forEach((t) =>
    t.addEventListener("click", () => switchTab(t.dataset.tab)));

  document.getElementById("loginForm").addEventListener("submit", (e) => {
    e.preventDefault();
    submit(e.submitter, () =>
      API.post("/auth/login", {
        email: document.getElementById("loginEmail").value,
        password: document.getElementById("loginPassword").value,
      }));
  });

  document.getElementById("signupForm").addEventListener("submit", (e) => {
    e.preventDefault();
    submit(e.submitter, () =>
      API.post("/auth/signup", {
        full_name: document.getElementById("suName").value,
        email: document.getElementById("suEmail").value,
        password: document.getElementById("suPassword").value,
      }));
  });

  document.getElementById("demoBtn").addEventListener("click", (e) => {
    submit(e.currentTarget, () =>
      API.post("/auth/login", { email: "demo@meter.ng", password: "demo1234" }));
  });

  const tt = document.getElementById("themeToggle");
  if (tt) tt.addEventListener("click", () => Theme.toggle());
}

document.addEventListener("DOMContentLoaded", initAuthPage);

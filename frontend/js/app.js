import { register, start, navigate, forceResolve } from "./router.js";
import { setToken, setRefreshToken, isLoggedIn } from "./api.js";
import { renderNav, initSidebar } from "./components/nav.js";
import { showToast } from "./components/toast.js";
import { openModal, closeModal } from "./components/modal.js";
import { initLang, t, currentLang, setLang, supportedLangs } from "./utils/i18n.js";
import { initTheme, toggleTheme, currentTheme } from "./utils/theme.js";

// Pages
import { renderHome } from "./pages/home.js";
import { renderCommunity } from "./pages/community.js";
import { renderPlanner } from "./pages/planner.js";
import { renderNews } from "./pages/news.js";
import { renderLostFound } from "./pages/lostfound.js";
import { renderProfile } from "./pages/profile.js";
import { renderMessages } from "./pages/messages.js";
import { api } from "./api.js";

// Cached auth config
let _googleClientId = "";

// --- Route registration ---
register("/", renderHome);
register("/community", renderCommunity);
register("/planner", renderPlanner);
register("/news", renderNews);
register("/lostfound", renderLostFound);
register("/profile", renderProfile, { auth: true });
register("/profile/:id", renderProfile, { auth: true });
register("/messages", renderMessages, { auth: true });
register("/reset-password", renderResetPassword);
register("/verify-email", renderVerifyEmail);

// --- Auth modal ---
function showAuthModal(mode = "login") {
  const isLogin = mode === "login";

  const googleClientId = _googleClientId;

  let formHtml = `
    <div class="flex gap-2 mb-4 border-b">
      <button class="auth-tab ${isLogin ? "active" : ""}" data-mode="login">${t("auth.login")}</button>
      <button class="auth-tab ${!isLogin ? "active" : ""}" data-mode="register">${t("auth.register")}</button>
    </div>
  `;

  if (isLogin) {
    formHtml += `
      <form id="auth-form" class="space-y-3">
        <input type="text" name="username" placeholder="${t("auth.username")}" aria-label="${t("auth.username")}" required>
        <input type="password" name="password" placeholder="${t("auth.password")}" aria-label="${t("auth.password")}" required>
        <div id="auth-error" class="field-error hidden"></div>
        <button type="submit" class="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors">
          ${t("auth.login")}
        </button>
      </form>
      <div class="auth-divider"><span>${t("auth.or")}</span></div>
    `;
    if (googleClientId) {
      formHtml += `
        <div id="google-btn-container" class="flex justify-center mb-3">
          <div id="g_id_onload"
               data-client_id="${googleClientId}"
               data-callback="handleGoogleSignIn"
               data-auto_prompt="false">
          </div>
          <button type="button" id="google-signin-btn" class="google-signin-btn">
            <svg viewBox="0 0 24 24" width="20" height="20"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
            <span>${t("auth.login_google")}</span>
          </button>
        </div>
        <div class="auth-divider"><span>${t("auth.or")}</span></div>
      `;
    }
    formHtml += `
      <form id="email-login-form" class="space-y-3">
        <input type="email" name="email" placeholder="${t("auth.email_placeholder")}" aria-label="${t("auth.email")}" required>
        <input type="password" name="password" placeholder="${t("auth.password")}" aria-label="${t("auth.password")}" required>
        <div id="email-auth-error" class="field-error hidden"></div>
        <button type="submit" class="w-full bg-green-600 text-white py-2 rounded-lg hover:bg-green-700 transition-colors">
          ${t("auth.login_email")}
        </button>
      </form>
      <div class="text-center mt-3">
        <a href="#/reset-password" class="text-sm text-blue-600 hover:underline" id="forgot-password-link">${t("auth.forgot_password")}</a>
      </div>
    `;
  } else {
    formHtml += `
      <form id="auth-form" class="space-y-3">
        <input type="email" name="email" placeholder="${t("auth.email")}" aria-label="${t("auth.email")}" required>
        <input type="text" name="nickname" placeholder="${t("auth.nickname")}" aria-label="${t("auth.nickname")}" required>
        <input type="password" name="password" placeholder="${t("auth.password")}" aria-label="${t("auth.password")}" required>
        <input type="text" name="student_id" placeholder="${t("auth.student_id")}" aria-label="${t("auth.student_id")}">
        <div id="auth-error" class="field-error hidden"></div>
        <button type="submit" class="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors">
          ${t("auth.register_email")}
        </button>
      </form>
    `;
    if (googleClientId) {
      formHtml += `
        <div class="auth-divider"><span>${t("auth.or")}</span></div>
        <div id="google-btn-container" class="flex justify-center">
          <button type="button" id="google-signin-btn" class="google-signin-btn">
            <svg viewBox="0 0 24 24" width="20" height="20"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
            <span>${t("auth.login_google")}</span>
          </button>
        </div>
      `;
    }
  }

  openModal(isLogin ? t("auth.welcome") : t("auth.create"), formHtml);

  // Tab switching
  document.querySelectorAll(".auth-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      showAuthModal(tab.dataset.mode);
    });
  });

  // Google button click
  const googleBtn = document.getElementById("google-signin-btn");
  if (googleBtn && googleClientId && window.google) {
    googleBtn.addEventListener("click", () => {
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: window.handleGoogleSignIn,
      });
      window.google.accounts.id.prompt();
    });
  } else if (googleBtn && !googleClientId) {
    googleBtn.addEventListener("click", () => {
      showToast(t("auth.google_failed"), "error");
    });
  }

  // Username/password form (login) or email register form
  const authForm = document.getElementById("auth-form");
  if (authForm) {
    authForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = Object.fromEntries(fd.entries());
      const isLoginMode = !!document.querySelector('.auth-tab.active[data-mode="login"]');

      try {
        document.getElementById("auth-error").classList.add("hidden");

        let url, body;
        if (isLoginMode) {
          url = "/api/v1/auth/login";
          body = { username: data.username, password: data.password };
        } else {
          url = "/api/v1/auth/email/register";
          body = {
            email: data.email,
            password: data.password,
            nickname: data.nickname,
            student_id: data.student_id || null,
          };
        }

        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Request failed");
        }

        const result = await res.json();

        if (isLoginMode) {
          setToken(result.access_token);
          if (result.refresh_token) setRefreshToken(result.refresh_token);
          closeModal();
          showToast(t("auth.logged_in"), "success");
          _onAuthChange();
        } else {
          showToast(t("auth.registered"), "success");
          showAuthModal("login");
        }
      } catch (err) {
        const el = document.getElementById("auth-error");
        el.textContent = err.message;
        el.classList.remove("hidden");
      }
    });
  }

  // Email login form
  const emailForm = document.getElementById("email-login-form");
  if (emailForm) {
    emailForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = Object.fromEntries(fd.entries());

      try {
        document.getElementById("email-auth-error").classList.add("hidden");

        const res = await fetch("/api/v1/auth/email/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: data.email, password: data.password }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Request failed");
        }

        const result = await res.json();
        setToken(result.access_token);
        if (result.refresh_token) setRefreshToken(result.refresh_token);
        closeModal();
      } catch (err) {
        const el = document.getElementById("email-auth-error");
        el.textContent = err.message;
        el.classList.remove("hidden");
      }
    });
  }

  // Forgot password link → close modal and navigate
  const forgotLink = document.getElementById("forgot-password-link");
  if (forgotLink) {
    forgotLink.addEventListener("click", () => closeModal());
  }
}

// Google Sign-In callback (must be on window for GIS SDK)
window.handleGoogleSignIn = async (response) => {
  try {
    const res = await fetch("/api/v1/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: response.credential }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Google login failed");
    }

    const result = await res.json();
    setToken(result.access_token);
    if (result.refresh_token) setRefreshToken(result.refresh_token);
    closeModal();
    showToast(t("auth.logged_in"), "success");
    _onAuthChange();
  } catch (err) {
    showToast(t("auth.google_failed"), "error");
  }
};

function _onAuthChange() {
  renderNav();
}

// --- Event listeners ---
window.addEventListener("auth:show-login", () => showAuthModal("login"));

window.addEventListener("auth:logout", () => {
  setToken(null);
  setRefreshToken(null);
  showToast(t("auth.logged_out"), "info");
  _onAuthChange();
  navigate("/");
});

// --- Language change → refresh nav + re-render current page ---
window.addEventListener("lang:change", () => {
  renderNav();
  forceResolve();
});

// --- Reset Password Page ---
function renderResetPassword() {
  const params = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const token = params.get("token");

  const container = document.getElementById("app-content");

  if (token) {
    // Show new password form
    container.innerHTML = `
      <div class="max-w-md mx-auto mt-16 p-6 bg-white rounded-2xl shadow-lg" data-page="auth-form">
        <h2 class="text-xl font-bold mb-4 text-gray-800">${t("auth.reset_password")}</h2>
        <form id="reset-form" class="space-y-3">
          <input type="password" name="new_password" placeholder="${t("auth.new_password")}" aria-label="${t("auth.new_password")}" required minlength="6">
          <input type="password" name="confirm" placeholder="${t("auth.confirm_password")}" aria-label="${t("auth.confirm_password")}" required minlength="6">
          <div id="reset-error" class="field-error hidden"></div>
          <button type="submit" class="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors">
            ${t("auth.reset_password")}
          </button>
        </form>
      </div>
    `;
    document.getElementById("reset-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const pw = fd.get("new_password");
      const confirm = fd.get("confirm");
      if (pw !== confirm) {
        const el = document.getElementById("reset-error");
        el.textContent = t("auth.password_mismatch");
        el.classList.remove("hidden");
        return;
      }
      try {
        await api.post("/auth/reset-password", { token, new_password: pw });
        showToast(t("auth.password_reset_ok"), "success");
        navigate("/");
        window.dispatchEvent(new CustomEvent("auth:show-login"));
      } catch (err) {
        const el = document.getElementById("reset-error");
        el.textContent = err.message || t("auth.invalid_token");
        el.classList.remove("hidden");
      }
    });
  } else {
    // Show "enter email" form
    container.innerHTML = `
      <div class="max-w-md mx-auto mt-16 p-6 bg-white rounded-2xl shadow-lg" data-page="auth-form">
        <h2 class="text-xl font-bold mb-2 text-gray-800">${t("auth.reset_password")}</h2>
        <p class="text-sm text-gray-500 mb-4">${t("auth.reset_password_desc")}</p>
        <form id="forgot-form" class="space-y-3">
          <input type="email" name="email" placeholder="${t("auth.email_placeholder")}" aria-label="${t("auth.email")}" required>
          <div id="forgot-error" class="field-error hidden"></div>
          <button type="submit" class="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors">
            ${t("auth.send_reset_link")}
          </button>
        </form>
      </div>
    `;
    document.getElementById("forgot-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await api.post("/auth/forgot-password", { email: fd.get("email") });
        showToast(t("auth.reset_sent"), "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  }
}

// --- Verify Email Page ---
function renderVerifyEmail() {
  const params = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const token = params.get("token");
  const container = document.getElementById("app-content");

  if (!token) {
    container.innerHTML = `
      <div class="max-w-md mx-auto mt-16 p-6 bg-white rounded-2xl shadow-lg text-center" data-page="auth-form">
        <h2 class="text-xl font-bold mb-2 text-gray-800">${t("auth.verify_failed")}</h2>
        <p class="text-gray-500">${t("auth.invalid_token")}</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="max-w-md mx-auto mt-16 p-6 bg-white rounded-2xl shadow-lg text-center" data-page="auth-form">
      <h2 class="text-xl font-bold mb-2 text-gray-800">${t("auth.verify_email")}</h2>
      <p class="text-gray-500" id="verify-status">${t("auth.verifying")}</p>
    </div>
  `;

  api.post("/auth/verify-email", { token }).then(() => {
    document.getElementById("verify-status").textContent = t("auth.verified");
    showToast(t("auth.verified"), "success");
  }).catch(() => {
    document.getElementById("verify-status").textContent = t("auth.verify_failed");
    showToast(t("auth.verify_failed"), "error");
  });
}

// --- Init ---
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  initLang();
  initSidebar();
  // Fetch Google Client ID from API (no longer in HTML meta)
  try {
    const res = await fetch("/api/v1/auth/config");
    if (res.ok) {
      const cfg = await res.json();
      _googleClientId = cfg.google_client_id || "";
    }
  } catch { /* non-critical */ }
  renderNav();
  start();
});

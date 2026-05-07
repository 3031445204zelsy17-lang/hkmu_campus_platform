import { register, start, navigate } from "./router.js";
import { setToken, isLoggedIn } from "./api.js";
import { renderNav, initSidebar } from "./components/nav.js";
import { showToast } from "./components/toast.js";
import { openModal, closeModal } from "./components/modal.js";

// Pages
import { renderHome } from "./pages/home.js";
import { renderCommunity } from "./pages/community.js";
import { renderPlanner } from "./pages/planner.js";
import { renderNews } from "./pages/news.js";
import { renderLostFound } from "./pages/lostfound.js";
import { renderProfile } from "./pages/profile.js";
import { renderMessages } from "./pages/messages.js";

// --- Route registration ---
register("/", renderHome);
register("/community", renderCommunity);
register("/planner", renderPlanner);
register("/news", renderNews);
register("/lostfound", renderLostFound);
register("/profile", renderProfile);
register("/profile/:id", renderProfile);
register("/messages", renderMessages);

// --- Auth modal ---
function showAuthModal(mode = "login") {
  const isLogin = mode === "login";

  const formHtml = `
    <div class="flex gap-2 mb-4 border-b">
      <button class="auth-tab ${isLogin ? "active" : ""}" data-mode="login">Login</button>
      <button class="auth-tab ${!isLogin ? "active" : ""}" data-mode="register">Register</button>
    </div>
    <form id="auth-form" class="space-y-3">
      ${!isLogin ? '<input type="text" name="nickname" placeholder="Nickname" required>' : ""}
      <input type="text" name="username" placeholder="Username" required>
      <input type="password" name="password" placeholder="Password (min 6 chars)" required>
      ${!isLogin ? '<input type="text" name="student_id" placeholder="Student ID (optional)">' : ""}
      <div id="auth-error" class="field-error hidden"></div>
      <button type="submit" class="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors">
        ${isLogin ? "Login" : "Register"}
      </button>
    </form>
  `;

  openModal(isLogin ? "Welcome Back" : "Create Account", formHtml);

  // Tab switching
  document.querySelectorAll(".auth-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      showAuthModal(tab.dataset.mode);
    });
  });

  // Form submit
  document.getElementById("auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());
    const isLoginMode = !!document.querySelector('.auth-tab.active[data-mode="login"]');

    try {
      document.getElementById("auth-error").classList.add("hidden");

      const body = isLoginMode
        ? { username: data.username, password: data.password }
        : { username: data.username, password: data.password, nickname: data.nickname, student_id: data.student_id || null };

      const res = await fetch(
        `/api/v1/auth/${isLoginMode ? "login" : "register"}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Request failed");
      }

      const result = await res.json();

      if (isLoginMode) {
        setToken(result.access_token);
        closeModal();
        showToast("Logged in!", "success");
        _onAuthChange();
      } else {
        showToast("Account created! Please login.", "success");
        showAuthModal("login");
      }
    } catch (err) {
      const el = document.getElementById("auth-error");
      el.textContent = err.message;
      el.classList.remove("hidden");
    }
  });
}

function _onAuthChange() {
  renderNav();
}

// --- Event listeners ---
window.addEventListener("auth:show-login", () => showAuthModal("login"));

window.addEventListener("auth:logout", () => {
  setToken(null);
  showToast("Logged out", "info");
  _onAuthChange();
  navigate("/");
});

// --- Init ---
document.addEventListener("DOMContentLoaded", () => {
  initSidebar();
  renderNav();
  start();
});

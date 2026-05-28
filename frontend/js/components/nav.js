import { isLoggedIn } from "../api.js";
import { t, currentLang, setLang, supportedLangs } from "../utils/i18n.js";
import { toggleTheme, currentTheme } from "../utils/theme.js";

const NAV_ITEMS = [
  { path: "/", labelKey: "nav.home", icon: "home" },
  { path: "/community", labelKey: "nav.community", icon: "message-circle" },
  { path: "/planner", labelKey: "nav.planner", icon: "book-open" },
  { path: "/news", labelKey: "nav.news", icon: "newspaper" },
  { path: "/lostfound", labelKey: "nav.lostfound", icon: "search" },
];

const NAV_ITEMS_AUTH = [
  { path: "/messages", labelKey: "nav.messages", icon: "mail" },
  { path: "/profile", labelKey: "nav.profile", icon: "user" },
];

export const SIDEBAR_CATEGORIES = [
  { value: null,         icon: "layout-grid",     labelKey: "community.cat_all" },
  { value: "discussion", icon: "message-square",   labelKey: "community.cat_discussion" },
  { value: "question",   icon: "help-circle",      labelKey: "community.cat_question" },
  { value: "sharing",    icon: "share-2",          labelKey: "community.cat_sharing" },
  { value: "news",       icon: "newspaper",         labelKey: "community.cat_news" },
  { value: "other",      icon: "more-horizontal",   labelKey: "community.cat_other" },
];

function _createIconLink(item, active) {
  const a = document.createElement("a");
  a.href = `#${item.path}`;
  a.dataset.navPath = item.path;
  a.className = `app-nav-item ${active}`;
  a.setAttribute("aria-label", t(item.labelKey));
  a.title = t(item.labelKey);
  const i = document.createElement("i");
  i.setAttribute("data-lucide", item.icon);
  i.className = "app-nav-icon";
  a.appendChild(i);
  const span = document.createElement("span");
  span.textContent = t(item.labelKey);
  a.appendChild(span);
  return a;
}

function _renderMobileAccountAction(current) {
  const navShell = document.querySelector("#app-nav > div");
  if (!navShell) return;

  const previous = document.getElementById("mobile-account-action");
  if (previous) previous.remove();

  const button = document.createElement(isLoggedIn() ? "a" : "button");
  button.id = "mobile-account-action";
  button.className = "mobile-account-action";
  button.setAttribute("aria-label", isLoggedIn() ? t("nav.profile") : t("nav.login"));
  button.title = isLoggedIn() ? t("nav.profile") : t("nav.login");

  if (isLoggedIn()) {
    button.href = "#/profile";
    if (current.startsWith("/profile") || current.startsWith("/messages")) {
      button.classList.add("is-active");
    }
  } else {
    button.type = "button";
    button.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:show-login")));
  }

  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", isLoggedIn() ? "user" : "log-in");
  icon.className = "app-nav-icon";
  button.appendChild(icon);

  navShell.appendChild(button);
}

export function renderNav() {
  const container = document.getElementById("nav-links");
  if (!container) return;

  const hash = window.location.hash || "#/";
  const current = hash.slice(1).split("?")[0];

  container.innerHTML = "";

  for (const item of NAV_ITEMS) {
    const isActive = current === item.path || (item.path !== "/" && current.startsWith(item.path));
    const active = isActive ? "is-active" : "";
    container.appendChild(_createIconLink(item, active));
  }

  if (isLoggedIn()) {
    for (const item of NAV_ITEMS_AUTH) {
      const isActive = current === item.path;
      const active = isActive ? "is-active" : "";
      container.appendChild(_createIconLink(item, active));
    }

    const logoutBtn = document.createElement("button");
    logoutBtn.id = "nav-logout-btn";
    logoutBtn.className = "app-nav-item app-nav-utility";
    const logoutIcon = document.createElement("i");
    logoutIcon.setAttribute("data-lucide", "log-out");
    logoutIcon.className = "app-nav-icon";
    logoutBtn.appendChild(logoutIcon);
    const logoutText = document.createElement("span");
    logoutText.textContent = t("nav.logout");
    logoutBtn.appendChild(logoutText);
    logoutBtn.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:logout")));
    container.appendChild(logoutBtn);
  } else {
    const loginBtn = document.createElement("button");
    loginBtn.id = "nav-login-btn";
    loginBtn.className = "app-nav-item app-nav-login";
    const loginIcon = document.createElement("i");
    loginIcon.setAttribute("data-lucide", "log-in");
    loginIcon.className = "app-nav-icon";
    loginBtn.appendChild(loginIcon);
    const loginText = document.createElement("span");
    loginText.textContent = t("nav.login");
    loginBtn.appendChild(loginText);
    loginBtn.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:show-login")));
    container.appendChild(loginBtn);
  }

  // Theme toggle
  const themeBtn = document.createElement("button");
  themeBtn.className = "app-nav-control app-nav-theme";
  themeBtn.title = t("nav.toggle_theme");
  themeBtn.setAttribute("aria-label", t("nav.toggle_theme"));
  const themeIcon = document.createElement("i");
  themeIcon.setAttribute("data-lucide", currentTheme() === "dark" ? "sun" : "moon");
  themeIcon.className = "app-nav-icon";
  themeBtn.appendChild(themeIcon);
  themeBtn.addEventListener("click", () => {
    const next = toggleTheme();
    themeIcon.setAttribute("data-lucide", next === "dark" ? "sun" : "moon");
    if (window.lucide) window.lucide.createIcons();
  });
  container.appendChild(themeBtn);

  // Language switcher
  const langWrap = document.createElement("div");
  langWrap.className = "app-lang-wrap";
  const langBtn = document.createElement("button");
  langBtn.className = "app-nav-control app-lang-btn";
  langBtn.setAttribute("aria-haspopup", "listbox");
  langBtn.setAttribute("aria-expanded", "false");
  const currentCode = currentLang();
  langBtn.textContent = { en: "EN", "zh-CN": "中", "zh-TW": "繁" }[currentCode] || "EN";
  langWrap.appendChild(langBtn);

  const langMenu = document.createElement("div");
  langMenu.className = "hidden absolute right-0 top-full mt-1 rounded-lg shadow-lg border py-1 z-50 min-w-[120px]";
  langMenu.setAttribute("role", "listbox");
  langMenu.setAttribute("aria-label", "Language");
  langMenu.style.background = "var(--bg-card)";
  langMenu.style.borderColor = "var(--border-color)";
  for (const lang of supportedLangs()) {
    const opt = document.createElement("button");
    opt.className = `block w-full text-left px-3 py-1.5 text-sm ${lang.code === currentCode ? "font-semibold" : ""}`;
    opt.style.color = lang.code === currentCode ? "var(--color-primary)" : "var(--text-secondary)";
    opt.addEventListener("mouseenter", () => { opt.style.background = "var(--bg-hover)"; });
    opt.addEventListener("mouseleave", () => { opt.style.background = ""; });
    opt.textContent = lang.label;
    opt.addEventListener("click", () => {
      setLang(lang.code);
      langMenu.classList.add("hidden");
    });
    langMenu.appendChild(opt);
  }
  langWrap.appendChild(langMenu);
  langBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    langMenu.classList.toggle("hidden");
    langBtn.setAttribute("aria-expanded", !langMenu.classList.contains("hidden"));
  });
  document.addEventListener("click", () => {
    langMenu.classList.add("hidden");
    langBtn.setAttribute("aria-expanded", "false");
  });
  container.appendChild(langWrap);

  _renderMobileAccountAction(current);
  renderSidebar();

  if (window.lucide) window.lucide.createIcons();
}

export function renderSidebar() {
  const ul = document.getElementById("sidebar-categories");
  if (!ul) return;

  const hash = window.location.hash || "#/";
  const hashQuery = hash.split("?")[1] || "";
  const urlParams = new URLSearchParams(hashQuery);
  const activeCategory = urlParams.get("category") || null;

  ul.innerHTML = "";

  for (const cat of SIDEBAR_CATEGORIES) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = cat.value ? `#/community?category=${cat.value}` : "#/community";

    if (activeCategory === cat.value) {
      a.classList.add("active");
    }

    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", cat.icon);
    a.appendChild(icon);

    const text = document.createElement("span");
    text.textContent = t(cat.labelKey);
    a.appendChild(text);

    a.addEventListener("click", () => {
      const drawer = document.getElementById("drawer-sidebar");
      const overlay = document.getElementById("sidebar-overlay");
      if (drawer) drawer.classList.remove("open");
      if (overlay) overlay.classList.remove("show");
    });

    li.appendChild(a);
    ul.appendChild(li);
  }
}

export function initSidebar() {
  const toggle = document.getElementById("sidebar-toggle");
  const drawer = document.getElementById("drawer-sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  if (!toggle || !drawer || !overlay) return;

  toggle.setAttribute("aria-controls", "drawer-sidebar");
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-label", "Toggle sidebar menu");

  toggle.addEventListener("click", () => {
    const isOpen = drawer.classList.toggle("open");
    overlay.classList.toggle("show");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  overlay.addEventListener("click", () => {
    drawer.classList.remove("open");
    overlay.classList.remove("show");
    toggle.setAttribute("aria-expanded", "false");
  });
}

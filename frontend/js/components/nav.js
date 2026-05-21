import { isLoggedIn } from "../api.js";
import { t, currentLang, setLang, supportedLangs } from "../utils/i18n.js";
import { toggleTheme, currentTheme } from "../utils/theme.js";

const SIDEBAR_NAV = [
  { path: "/", labelKey: "nav.home", icon: "home" },
  { path: "/community", labelKey: "nav.community", icon: "message-circle", hasSubmenu: true },
  { path: "/planner", labelKey: "nav.planner", icon: "book-open" },
  { path: "/news", labelKey: "nav.news", icon: "newspaper" },
];

const SIDEBAR_NAV_AUTH = [
  { path: "/messages", labelKey: "nav.messages", icon: "mail" },
  { path: "/profile", labelKey: "nav.profile", icon: "user" },
];

export const SIDEBAR_CATEGORIES = [
  { value: null,         icon: "layout-grid",     labelKey: "community.cat_all" },
  { value: "discussion", icon: "message-square",   labelKey: "community.cat_discussion" },
  { value: "question",   icon: "help-circle",      labelKey: "community.cat_question" },
  { value: "sharing",    icon: "share-2",          labelKey: "community.cat_sharing" },
  { value: "news",       icon: "newspaper",         labelKey: "community.cat_news" },
  { value: "lostfound",  icon: "search",            labelKey: "community.cat_lostfound" },
  { value: "other",      icon: "more-horizontal",   labelKey: "community.cat_other" },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function _getCurrentPath() {
  const hash = window.location.hash || "#/";
  return hash.slice(1).split("?")[0];
}

function _createNavLi(item, active) {
  const li = document.createElement("li");
  const a = document.createElement("a");
  a.href = `#${item.path}`;
  if (active) a.classList.add("active");

  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", item.icon);
  a.appendChild(icon);

  const span = document.createElement("span");
  span.textContent = t(item.labelKey);
  a.appendChild(span);

  if (item.hasSubmenu && active) {
    const chevron = document.createElement("i");
    chevron.setAttribute("data-lucide", "chevron-down");
    chevron.className = "ml-auto";
    chevron.style.width = "14px";
    chevron.style.height = "14px";
    a.appendChild(chevron);
  }

  a.addEventListener("click", () => {
    if (window.innerWidth < 768) _closeSidebar();
  });

  li.appendChild(a);
  return li;
}

// ── Render Top Bar Utilities ──────────────────────────────────────────────────

function _renderTopBar() {
  const container = document.getElementById("nav-utilities");
  if (!container) return;
  container.innerHTML = "";

  // Theme toggle
  const themeBtn = document.createElement("button");
  themeBtn.title = t("nav.toggle_theme");
  themeBtn.setAttribute("aria-label", t("nav.toggle_theme"));
  const themeIcon = document.createElement("i");
  themeIcon.setAttribute("data-lucide", currentTheme() === "dark" ? "sun" : "moon");
  themeIcon.style.width = "16px";
  themeIcon.style.height = "16px";
  themeBtn.appendChild(themeIcon);
  themeBtn.addEventListener("click", () => {
    const next = toggleTheme();
    themeIcon.setAttribute("data-lucide", next === "dark" ? "sun" : "moon");
    if (window.lucide) window.lucide.createIcons();
  });
  container.appendChild(themeBtn);

  // Language switcher
  const langWrap = document.createElement("div");
  langWrap.className = "lang-wrap";
  const langBtn = document.createElement("button");
  langBtn.className = "lang-btn";
  langBtn.setAttribute("aria-haspopup", "listbox");
  langBtn.setAttribute("aria-expanded", "false");
  const currentCode = currentLang();
  langBtn.textContent = { en: "EN", "zh-CN": "中", "zh-TW": "繁" }[currentCode] || "EN";

  const langMenu = document.createElement("div");
  langMenu.className = "lang-menu hidden";
  langMenu.setAttribute("role", "listbox");
  langMenu.setAttribute("aria-label", "Language");
  for (const lang of supportedLangs()) {
    const opt = document.createElement("button");
    opt.textContent = lang.label;
    if (lang.code === currentCode) {
      opt.style.color = "var(--color-primary)";
      opt.style.fontWeight = "600";
    }
    opt.addEventListener("click", () => {
      setLang(lang.code);
      langMenu.classList.add("hidden");
    });
    langMenu.appendChild(opt);
  }

  langBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    langMenu.classList.toggle("hidden");
    langBtn.setAttribute("aria-expanded", !langMenu.classList.contains("hidden"));
  });
  document.addEventListener("click", () => {
    langMenu.classList.add("hidden");
    langBtn.setAttribute("aria-expanded", "false");
  });

  langWrap.appendChild(langBtn);
  langWrap.appendChild(langMenu);
  container.appendChild(langWrap);

  // Auth button
  if (isLoggedIn()) {
    const userBtn = document.createElement("button");
    const userIcon = document.createElement("i");
    userIcon.setAttribute("data-lucide", "user");
    userIcon.style.width = "16px";
    userIcon.style.height = "16px";
    userBtn.appendChild(userIcon);
    userBtn.addEventListener("click", () => {
      window.location.hash = "#/profile";
    });
    container.appendChild(userBtn);
  } else {
    const loginBtn = document.createElement("button");
    const loginIcon = document.createElement("i");
    loginIcon.setAttribute("data-lucide", "log-in");
    loginIcon.style.width = "16px";
    loginIcon.style.height = "16px";
    loginBtn.appendChild(loginIcon);
    loginBtn.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent("auth:show-login"));
    });
    container.appendChild(loginBtn);
  }
}

// ── Render Sidebar Main Nav ──────────────────────────────────────────────────

function _renderSidebarNav(current) {
  const ul = document.getElementById("sidebar-main-nav");
  if (!ul) return;
  ul.innerHTML = "";

  for (const item of SIDEBAR_NAV) {
    const isActive = current === item.path ||
      (item.path !== "/" && current.startsWith(item.path));
    ul.appendChild(_createNavLi(item, isActive));
  }

  if (isLoggedIn()) {
    for (const item of SIDEBAR_NAV_AUTH) {
      const isActive = current === item.path;
      ul.appendChild(_createNavLi(item, isActive));
    }
  }

  // Divider
  const divider = document.createElement("li");
  divider.className = "sidebar-divider";
  divider.setAttribute("role", "separator");
  ul.appendChild(divider);

  // Auth item at bottom
  const authLi = document.createElement("li");
  authLi.className = "sidebar-auth-item";
  if (isLoggedIn()) {
    const btn = document.createElement("button");
    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", "log-out");
    btn.appendChild(icon);
    const span = document.createElement("span");
    span.textContent = t("nav.logout");
    btn.appendChild(span);
    btn.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent("auth:logout"));
    });
    authLi.appendChild(btn);
  } else {
    const a = document.createElement("a");
    a.href = "#";
    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", "log-in");
    a.appendChild(icon);
    const span = document.createElement("span");
    span.textContent = t("nav.login");
    a.appendChild(span);
    a.addEventListener("click", (e) => {
      e.preventDefault();
      window.dispatchEvent(new CustomEvent("auth:show-login"));
    });
    authLi.appendChild(a);
  }
  ul.appendChild(authLi);
}

// ── Render Sidebar Community Categories ───────────────────────────────────────

function _renderSidebarCategories(current) {
  const ul = document.getElementById("sidebar-community-cats");
  const section = document.getElementById("sidebar-community-section");
  if (!ul || !section) return;

  // Show/hide accordion based on current path
  if (current === "/community") {
    section.classList.remove("hidden");
  } else {
    section.classList.add("hidden");
  }

  ul.innerHTML = "";

  const hashQuery = window.location.hash.split("?")[1] || "";
  const urlParams = new URLSearchParams(hashQuery);
  const activeCategory = urlParams.get("category") || null;

  for (const cat of SIDEBAR_CATEGORIES) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = cat.value ? `#/community?category=${cat.value}` : "#/community";

    if (activeCategory === cat.value || (!activeCategory && !cat.value)) {
      a.classList.add("active");
    }

    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", cat.icon);
    a.appendChild(icon);

    const text = document.createElement("span");
    text.textContent = t(cat.labelKey);
    a.appendChild(text);

    a.addEventListener("click", () => {
      if (window.innerWidth < 768) _closeSidebar();
    });

    li.appendChild(a);
    ul.appendChild(li);
  }
}

// ── Main Export ───────────────────────────────────────────────────────────────

export function renderNav() {
  const current = _getCurrentPath();
  _renderTopBar();
  _renderSidebarNav(current);
  _renderSidebarCategories(current);
  if (window.lucide) window.lucide.createIcons();
}

// ── Sidebar Init ──────────────────────────────────────────────────────────────

function _closeSidebar() {
  const sidebar = document.getElementById("app-sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  const toggle = document.getElementById("sidebar-toggle");
  if (sidebar) sidebar.classList.remove("open");
  if (overlay) overlay.classList.remove("show");
  if (toggle) toggle.setAttribute("aria-expanded", "false");
}

export function initSidebar() {
  const toggle = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("app-sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  if (!toggle || !sidebar || !overlay) return;

  toggle.setAttribute("aria-controls", "app-sidebar");
  toggle.setAttribute("aria-expanded", "false");

  toggle.addEventListener("click", () => {
    const isOpen = sidebar.classList.toggle("open");
    overlay.classList.toggle("show");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  overlay.addEventListener("click", _closeSidebar);

  sidebar.addEventListener("click", (e) => {
    if (e.target.closest("a") && window.innerWidth < 768) _closeSidebar();
  });
}

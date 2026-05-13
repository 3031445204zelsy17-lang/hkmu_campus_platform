import { isLoggedIn } from "../api.js";
import { t, currentLang, setLang, supportedLangs } from "../utils/i18n.js";

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
  a.className = `${active} transition-colors flex items-center gap-1.5`;
  const i = document.createElement("i");
  i.setAttribute("data-lucide", item.icon);
  i.className = "w-4 h-4";
  a.appendChild(i);
  const span = document.createElement("span");
  span.textContent = t(item.labelKey);
  a.appendChild(span);
  return a;
}

export function renderNav() {
  const container = document.getElementById("nav-links");
  if (!container) return;

  const hash = window.location.hash || "#/";
  const current = hash.slice(1).split("?")[0];

  container.innerHTML = "";

  for (const item of NAV_ITEMS) {
    const isActive = current === item.path || (item.path !== "/" && current.startsWith(item.path));
    const active = isActive ? "text-blue-600 font-semibold" : "text-gray-600 hover:text-blue-600";
    container.appendChild(_createIconLink(item, active));
  }

  if (isLoggedIn()) {
    for (const item of NAV_ITEMS_AUTH) {
      const isActive = current === item.path;
      const active = isActive ? "text-blue-600 font-semibold" : "text-gray-600 hover:text-blue-600";
      container.appendChild(_createIconLink(item, active));
    }

    const logoutBtn = document.createElement("button");
    logoutBtn.id = "nav-logout-btn";
    logoutBtn.className = "text-gray-600 hover:text-red-500 transition-colors flex items-center gap-1.5";
    const logoutIcon = document.createElement("i");
    logoutIcon.setAttribute("data-lucide", "log-out");
    logoutIcon.className = "w-4 h-4";
    logoutBtn.appendChild(logoutIcon);
    const logoutText = document.createElement("span");
    logoutText.textContent = t("nav.logout");
    logoutBtn.appendChild(logoutText);
    logoutBtn.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:logout")));
    container.appendChild(logoutBtn);
  } else {
    const loginBtn = document.createElement("button");
    loginBtn.id = "nav-login-btn";
    loginBtn.className = "text-blue-600 font-semibold hover:text-blue-800 transition-colors flex items-center gap-1.5";
    const loginIcon = document.createElement("i");
    loginIcon.setAttribute("data-lucide", "log-in");
    loginIcon.className = "w-4 h-4";
    loginBtn.appendChild(loginIcon);
    const loginText = document.createElement("span");
    loginText.textContent = t("nav.login");
    loginBtn.appendChild(loginText);
    loginBtn.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:show-login")));
    container.appendChild(loginBtn);
  }

  // Language switcher
  const langWrap = document.createElement("div");
  langWrap.className = "relative ml-2";
  const langBtn = document.createElement("button");
  langBtn.className = "text-gray-500 hover:text-gray-700 text-sm flex items-center gap-1 px-2 py-1 rounded border border-gray-200";
  const currentCode = currentLang();
  langBtn.textContent = { en: "EN", "zh-CN": "中", "zh-TW": "繁" }[currentCode] || "EN";
  langWrap.appendChild(langBtn);

  const langMenu = document.createElement("div");
  langMenu.className = "hidden absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50 min-w-[120px]";
  for (const lang of supportedLangs()) {
    const opt = document.createElement("button");
    opt.className = `block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 ${lang.code === currentCode ? "text-blue-600 font-semibold" : "text-gray-700"}`;
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
  });
  document.addEventListener("click", () => langMenu.classList.add("hidden"));
  container.appendChild(langWrap);

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

  toggle.addEventListener("click", () => {
    drawer.classList.toggle("open");
    overlay.classList.toggle("show");
  });

  overlay.addEventListener("click", () => {
    drawer.classList.remove("open");
    overlay.classList.remove("show");
  });
}

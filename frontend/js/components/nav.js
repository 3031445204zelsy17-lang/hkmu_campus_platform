import { isLoggedIn } from "../api.js";

const NAV_ITEMS = [
  { path: "/", label: "Home", icon: "home" },
  { path: "/community", label: "Community", icon: "message-circle" },
  { path: "/planner", label: "Planner", icon: "book-open" },
  { path: "/news", label: "News", icon: "newspaper" },
  { path: "/lostfound", label: "Lost & Found", icon: "search" },
];

const NAV_ITEMS_AUTH = [
  { path: "/messages", label: "Messages", icon: "mail" },
  { path: "/profile", label: "Profile", icon: "user" },
];

export const SIDEBAR_CATEGORIES = [
  { value: null,         icon: "layout-grid",     label: "All" },
  { value: "discussion", icon: "message-square",   label: "Discussion" },
  { value: "question",   icon: "help-circle",      label: "Q&A" },
  { value: "sharing",    icon: "share-2",          label: "Sharing" },
  { value: "news",       icon: "newspaper",         label: "Campus News" },
  { value: "other",      icon: "more-horizontal",   label: "Other" },
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
  span.textContent = item.label;
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
    logoutText.textContent = "Logout";
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
    loginText.textContent = "Login";
    loginBtn.appendChild(loginText);
    loginBtn.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:show-login")));
    container.appendChild(loginBtn);
  }

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
    text.textContent = cat.label;
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

let _container = null;

function _ensureContainer() {
  if (!_container) {
    _container = document.createElement("div");
    _container.id = "toast-container";
    _container.style.cssText = "position:fixed;top:1rem;right:1rem;z-index:9999;display:flex;flex-direction:column;gap:0.5rem;";
    document.body.appendChild(_container);
  }
  return _container;
}

export function showToast(message, type = "info", duration = 3000) {
  const container = _ensureContainer();
  const el = document.createElement("div");

  const colors = {
    success: "bg-green-500",
    error: "bg-red-500",
    info: "bg-blue-500",
    warning: "bg-yellow-500 text-black",
  };

  el.className = `${colors[type] || colors.info} text-white px-4 py-2 rounded-lg shadow-lg text-sm transition-all duration-300 opacity-0 translate-x-4`;
  el.textContent = message;
  container.appendChild(el);

  requestAnimationFrame(() => {
    el.classList.remove("opacity-0", "translate-x-4");
  });

  setTimeout(() => {
    el.classList.add("opacity-0", "translate-x-4");
    setTimeout(() => el.remove(), 300);
  }, duration);
}

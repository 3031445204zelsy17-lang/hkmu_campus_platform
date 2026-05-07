const routes = {};
let _currentPath = null;

export function register(path, handler) {
  routes[path] = handler;
}

export function navigate(path) {
  window.location.hash = path;
}

export function start() {
  window.addEventListener("hashchange", _resolve);
  _resolve();
}

function _resolve() {
  const hash = window.location.hash || "#/";
  const path = hash.slice(1).split("?")[0]; // remove '#' and query string

  if (path === _currentPath) return;
  _currentPath = path;

  // exact match first
  if (routes[path]) {
    routes[path]();
    return;
  }

  // pattern match: /posts/123 → /posts/:id
  for (const pattern of Object.keys(routes)) {
    const param = _match(pattern, path);
    if (param !== null) {
      routes[pattern](param);
      return;
    }
  }

  // fallback to home
  if (routes["/"]) {
    routes["/"]();
  }
}

function _match(pattern, path) {
  const pParts = pattern.split("/");
  const pathParts = path.split("/");
  if (pParts.length !== pathParts.length) return null;

  let param = null;
  for (let i = 0; i < pParts.length; i++) {
    if (pParts[i].startsWith(":")) {
      param = pathParts[i];
    } else if (pParts[i] !== pathParts[i]) {
      return null;
    }
  }
  return param;
}

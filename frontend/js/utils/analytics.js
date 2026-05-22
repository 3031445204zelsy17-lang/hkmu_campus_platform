// analytics.js — GA4 + Mixpanel centralized tracking module
// Meta tags in index.html control enablement:
//   <meta name="ga4-measurement-id" content="G-XXXXXX">
//   <meta name="mixpanel-token" content="xxxxx">
// Empty values = noop (dev mode). localhost = noop by default.

let _enabled = false;
let _debug = false;
let _ga4Id = "";
let _mpToken = "";

function _readMeta(name) {
  const el = document.querySelector(`meta[name="${name}"]`);
  return el?.getAttribute("content")?.trim() || "";
}

function _isLocalhost() {
  return (
    location.hostname === "localhost" ||
    location.hostname === "127.0.0.1"
  );
}

function _getUserId() {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) return null;
    const payload = token.split(".")[1];
    const decoded = JSON.parse(atob(payload));
    return decoded.sub || decoded.user_id || decoded.id || null;
  } catch {
    return null;
  }
}

function _log(event, props) {
  if (_debug) console.log(`[analytics] ${event}`, props);
}

// --- SDK Loaders ---

function _loadGA4(id) {
  const gtagScript = document.createElement("script");
  gtagScript.async = true;
  gtagScript.src = `https://www.googletagmanager.com/gtag/js?id=${id}`;
  document.head.appendChild(gtagScript);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function () {
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", id, { send_page_view: false }); // manual page views
}

function _loadMixpanel(token) {
  // Mixpanel snippet (lightweight loader)
  (function (c, a) {
    if (!a.__SV) {
      var b = window;
      try {
        var d,
          m,
          j,
          k = b.location,
          f = k.hash;
        j = f && f.substring(1);
        if (j) {
          try {
            d = JSON.parse(decodeURIComponent(j));
          } catch {
            d = {};
          }
        }
        if (d.__mp) {
          b[c] = d.__mp;
          return;
        }
      } catch {}
      var g = b[c] || {};
      b[c] = g;
      g._i = [];
      g.init = function (e, h, l) {
        var p = g;
        if (l) p = g[l] = g[l] || {};
        p._q = p._q || [];
        if (typeof h !== "undefined" && h !== null) {
          var n = {};
          for (var o in h)
            if (h.hasOwnProperty(o)) n[o] = h[o];
          n.__$s = 1;
          p._q.push(["init", n]);
        }
        p._q.push(["_init", e]);
      };
      g.__SV = 1.2;
      var s = document.createElement("script");
      s.async = true;
      s.src = "https://cdn.mxpnl.com/libs/mixpanel-2-latest.min.js";
      document.head.appendChild(s);
    }
  })("mixpanel", window);

  if (window.mixpanel?.init) {
    window.mixpanel.init(token, { persistence: "localStorage" });
  }
}

// --- Public API ---

export function initAnalytics() {
  _ga4Id = _readMeta("ga4-measurement-id");
  _mpToken = _readMeta("mixpanel-token");
  _debug = localStorage.getItem("analytics_debug") === "true";

  if (!_ga4Id && !_mpToken) return; // noop mode
  if (_isLocalhost() && !_debug) return; // suppress in dev unless debug

  _enabled = true;

  if (_ga4Id) _loadGA4(_ga4Id);
  if (_mpToken) _loadMixpanel(_mpToken);

  // Auto page view tracking from router
  window.addEventListener("analytics:page_view", (e) => {
    const path = e.detail?.path || location.hash;
    track("page_view", { page_path: path });
  });

  // Auto-identify if already logged in
  const uid = _getUserId();
  if (uid) identify(uid);
}

export function track(event, props = {}) {
  if (!_enabled) {
    _log(event, props); // debug log even when disabled
    return;
  }
  _log(event, props);

  if (_ga4Id && window.gtag) {
    window.gtag("event", event, props);
  }
  if (_mpToken && window.mixpanel?.track) {
    window.mixpanel.track(event, props);
  }
}

export function identify(userId) {
  if (!_enabled || !userId) return;

  if (_ga4Id && window.gtag) {
    window.gtag("config", _ga4Id, { user_id: userId });
  }
  if (_mpToken && window.mixpanel) {
    window.mixpanel.identify(String(userId));
    if (window.mixpanel.people) {
      window.mixpanel.people.set({
        language: navigator.language,
        theme: document.documentElement.classList.contains("dark")
          ? "dark"
          : "light",
      });
    }
  }
  _log("identify", { user_id: userId });
}

export function resetIdentity() {
  if (!_enabled) return;

  if (_ga4Id && window.gtag) {
    window.gtag("config", _ga4Id, { user_id: undefined });
  }
  if (_mpToken && window.mixpanel) {
    window.mixpanel.reset();
  }
  _log("reset_identity", {});
}

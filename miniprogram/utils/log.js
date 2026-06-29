// 轻量日志封装(内测错误监控,B3):
// 优先微信原生 RealtimeLogManager → 后台「运维中心 → 实时日志」可见(分钟级延迟);
// devtools 或无该 API 时降级 console,绝不阻塞业务。无需第三方依赖。
//
// 用法:
//   const log = require("./log");
//   log.error("api", err, { path, status });    // 关键失败 → 后台实时日志 + console
//   log.warn("dm", "reconnect failed", {...});   // 警告 → 后台实时日志 + console
//   log.info("home", "loaded", { count });       // 信息 → 仅后台实时日志(不污染 console)

let _rt = null;
function rt() {
  // 懒加载 RealtimeLogManager;缓存:null=还没取,false=不可用
  if (_rt === null) {
    try {
      _rt =
        typeof wx !== "undefined" && typeof wx.getRealtimeLogManager === "function"
          ? wx.getRealtimeLogManager()
          : false;
    } catch (e) {
      _rt = false;
    }
  }
  return _rt || null;
}

function _stringifyErr(err) {
  if (err == null) return "";
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  try {
    return JSON.stringify(err);
  } catch (e) {
    return String(err);
  }
}

// error(tag, err, extra?) — 关键失败,上报后台实时日志 + console
function error(tag, err, extra) {
  const detail = _stringifyErr(err);
  const m = rt();
  if (m) {
    try {
      m.error(tag, detail, extra || {});
    } catch (e) {}
  }
  if (typeof console !== "undefined" && console.error) {
    console.error("[error]", tag, detail, extra || "");
  }
}

// warn(tag, msg, extra?) — 警告
function warn(tag, msg, extra) {
  const m = rt();
  if (m) {
    try {
      m.warn(tag, msg, extra || {});
    } catch (e) {}
  }
  if (typeof console !== "undefined" && console.warn) {
    console.warn("[warn]", tag, msg, extra || "");
  }
}

// info(tag, msg, extra?) — 信息,只进后台实时日志(不落 console,避免噪音)
function info(tag, msg, extra) {
  const m = rt();
  if (m) {
    try {
      m.info(tag, msg, extra || {});
    } catch (e) {}
  }
}

module.exports = { error, warn, info };

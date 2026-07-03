const { API_ORIGIN } = require("./config");
const { request } = require("./request");

// 私信传输层:WebSocket 单例 + REST 封装 + 事件总线。
// 刻意只依赖 config/request(不依赖 auth),避免与 auth.js 的登录回调互相 require 形成环。
// token / 当前用户 id 直接读 storage + globalData。

const TOKEN_KEY = "hkmu_access_token";
const USER_KEY = "hkmu_current_user";
const WS_PATH = "/api/v1/messages/ws";

const HISTORY_PAGE_SIZE = 30;
const HEARTBEAT_MS = 30000;
const PONG_TIMEOUT_MS = 45000;
const RECONNECT_BASE_MS = 5000;
const RECONNECT_MAX_MS = 30000;
const POLL_INTERVAL_MS = 5000;
const SEEN_CAP = 500; // 去重消息 id 上限,超过则整体清空(v1 简化)

// ── 状态 ────────────────────────────────────────────────────────────
let _task = null;
let _state = "closed"; // closed | connecting | open
let _userClose = false;
let _heartbeatTimer = null;
let _pongTimer = null;
let _reconnectTimer = null;
let _reconnectDelay = RECONNECT_BASE_MS;
let _pollTimer = null;
let _pollRefCount = 0;
let _unread = 0;
const _seen = new Set();
const _listeners = { chat: [], unread: [], open: [], close: [] };

// ── 工具 ────────────────────────────────────────────────────────────
function _wsUrl() {
  const token = wx.getStorageSync(TOKEN_KEY);
  if (!token) return "";
  const base = API_ORIGIN.replace(/^http/i, "ws"); // http→ws / https→wss
  return `${base}${WS_PATH}?token=${encodeURIComponent(token)}`;
}

function _myId() {
  try {
    const app = getApp();
    const u = app && app.globalData && app.globalData.user;
    if (u && u.id) return u.id;
  } catch (e) {}
  const stored = wx.getStorageSync(USER_KEY);
  return stored && stored.id ? stored.id : null;
}

function _emit(event, payload) {
  const cbs = _listeners[event];
  if (!cbs) return;
  for (let i = 0; i < cbs.length; i++) {
    try {
      cbs[i](payload);
    } catch (e) {}
  }
}

function on(event, cb) {
  if (_listeners[event] && typeof cb === "function") _listeners[event].push(cb);
  return cb;
}

function off(event, cb) {
  const cbs = _listeners[event];
  if (!cbs || !cb) return;
  const i = cbs.indexOf(cb);
  if (i >= 0) cbs.splice(i, 1);
}

function getUnread() {
  return _unread;
}

function setUnread(n) {
  const next = Math.max(0, Math.floor(n || 0));
  if (next === _unread) return;
  _unread = next;
  _emit("unread", _unread);
}

function getState() {
  return _state;
}

function _setState(s) {
  _state = s;
  if (s === "open") _emit("open");
  else if (s === "closed") _emit("close");
}

// ── 心跳 ────────────────────────────────────────────────────────────
function _startHeartbeat() {
  _stopHeartbeat();
  _heartbeatTimer = setInterval(() => {
    _send({ type: "ping" });
    _armPongWatch();
  }, HEARTBEAT_MS);
}

function _stopHeartbeat() {
  if (_heartbeatTimer) {
    clearInterval(_heartbeatTimer);
    _heartbeatTimer = null;
  }
  _clearPongWatch();
}

function _armPongWatch() {
  _clearPongWatch();
  _pongTimer = setTimeout(() => {
    // 心跳无应答,判定连接死亡 → 重连
    _teardown(false);
    _scheduleReconnect();
  }, PONG_TIMEOUT_MS);
}

function _clearPongWatch() {
  if (_pongTimer) {
    clearTimeout(_pongTimer);
    _pongTimer = null;
  }
}

// ── 发送 ────────────────────────────────────────────────────────────
function _send(obj) {
  if (_state !== "open" || !_task) return false;
  try {
    _task.send({ data: JSON.stringify(obj) });
    return true;
  } catch (e) {
    return false;
  }
}

function send(obj) {
  return _send(obj);
}

// ── 收消息 ──────────────────────────────────────────────────────────
function _handleMessage(raw) {
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return;
  }
  if (!data || !data.type) return;

  if (data.type === "pong") {
    _clearPongWatch();
    return;
  }
  if (data.type === "unread_count") {
    setUnread(data.count || 0);
    return;
  }
  if (data.type === "error") {
    return;
  }
  if (data.type === "chat") {
    if (data.id != null) {
      if (_seen.has(data.id)) return;
      _seen.add(data.id);
      if (_seen.size > SEEN_CAP) _seen.clear();
    }
    _clearPongWatch(); // 任何入站都说明链路活着
    _emit("chat", {
      id: data.id,
      senderId: data.sender_id,
      receiverId: data.receiver_id,
      content: data.content,
      isRead: data.is_read,
      createdAt: data.created_at,
    });
    // 别人发来的(非自己回显)→ 本地未读 +1(服务端 unread_count 会随后校正)
    const me = _myId();
    if (data.sender_id != null && me != null && data.sender_id !== me) {
      setUnread(_unread + 1);
    }
  }
}

// ── 连接生命周期 ────────────────────────────────────────────────────
function _teardown(userInitiated) {
  _userClose = !!userInitiated;
  _stopHeartbeat();
  if (_task) {
    try {
      _task.close && _task.close({});
    } catch (e) {}
  }
  _task = null;
  _setState("closed");
}

function connect() {
  const url = _wsUrl();
  if (!url) return; // 未登录
  if (_state === "open" || _state === "connecting") return;

  _userClose = false;
  _setState("connecting");

  let task;
  try {
    task = wx.connectSocket({
      url,
      fail: () => {
        if (_state === "connecting") {
          _setState("closed");
          _scheduleReconnect();
        }
      },
    });
  } catch (e) {
    _setState("closed");
    _scheduleReconnect();
    return;
  }
  if (!task) {
    _scheduleReconnect();
    return;
  }
  _task = task;

  _task.onOpen(() => {
    _setState("open");
    _reconnectDelay = RECONNECT_BASE_MS;
    _startHeartbeat();
  });
  _task.onMessage((res) => _handleMessage(res.data));
  _task.onError(() => {
    // onClose 随后会触发,重连在那里处理
  });
  _task.onClose(() => {
    _stopHeartbeat();
    _task = null;
    _setState("closed");
    if (!_userClose) _scheduleReconnect();
  });
}

function ensureConnected() {
  if (_state === "open" || _state === "connecting") return;
  connect();
}

function disconnect() {
  _cancelReconnect();
  _teardown(true);
}

function _cancelReconnect() {
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
}

function _scheduleReconnect() {
  if (_userClose) return;
  _cancelReconnect();
  if (!_wsUrl()) return; // 未登录就不转
  _reconnectTimer = setTimeout(() => {
    _reconnectTimer = null;
    connect();
  }, _reconnectDelay);
  _reconnectDelay = Math.min(_reconnectDelay * 2, RECONNECT_MAX_MS);
}

// ── 轮询降级(WS 断且在消息页时,仅维持未读计数)─────────────────────
function startPolling() {
  _pollRefCount += 1;
  if (_pollTimer) return;
  // Don't poll when logged out — otherwise a dead session (request.js clears the
  // token on 401) makes this fire /messages/unread-count every 5s → endless 401s.
  if (!wx.getStorageSync(TOKEN_KEY)) return;
  _pollTimer = setInterval(() => {
    if (_state === "open") return;
    if (!wx.getStorageSync(TOKEN_KEY)) {
      // session died → stop polling entirely (no page should poll while logged out)
      clearInterval(_pollTimer);
      _pollTimer = null;
      _pollRefCount = 0;
      return;
    }
    fetchUnread().catch(() => {
      // 401 → request.js cleared the token; if now logged out, stop hammering.
      if (!wx.getStorageSync(TOKEN_KEY)) {
        clearInterval(_pollTimer);
        _pollTimer = null;
        _pollRefCount = 0;
      }
    });
  }, POLL_INTERVAL_MS);
}

function stopPolling() {
  _pollRefCount = Math.max(0, _pollRefCount - 1);
  if (_pollRefCount > 0) return;
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

// ── REST 封装(复用 request.js,自动 Bearer + 401 刷新)──────────────
function fetchConversations() {
  return request({ path: "/messages/conversations", auth: true });
}

function fetchHistory(partnerId, page) {
  const p = Math.max(1, page || 1);
  return request({
    path: `/messages/history/${partnerId}?page=${p}&page_size=${HISTORY_PAGE_SIZE}`,
    auth: true,
  });
}

function postMessage(partnerId, content) {
  return request({
    method: "POST",
    path: `/messages/${partnerId}`,
    data: { content },
    auth: true,
  });
}

function markRead(partnerId) {
  // WS 优先(服务端会重算未读并推送),REST 兜底保证落库
  _send({ type: "mark_read", partner_id: partnerId });
  return request({ method: "PUT", path: `/messages/read/${partnerId}`, auth: true });
}

function fetchUnread() {
  return request({ path: "/messages/unread-count", auth: true }).then((r) => {
    const count = (r && r.count) || 0;
    setUnread(count);
    return count;
  });
}

// 应用回到前台时尝试重连(系统可能在后台杀掉 WS)
let _appShowWired = false;
function _wireAppShow() {
  if (_appShowWired) return;
  _appShowWired = true;
  try {
    wx.onAppShow(() => ensureConnected());
  } catch (e) {}
}
_wireAppShow();

module.exports = {
  on,
  off,
  connect,
  ensureConnected,
  disconnect,
  send,
  getUnread,
  setUnread,
  getState,
  startPolling,
  stopPolling,
  fetchConversations,
  fetchHistory,
  postMessage,
  markRead,
  fetchUnread,
  HISTORY_PAGE_SIZE,
};

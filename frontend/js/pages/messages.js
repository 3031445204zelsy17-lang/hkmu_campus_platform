import { api, getToken, isLoggedIn } from "../api.js";
import { showToast } from "../components/toast.js";
import { openModal, closeModal } from "../components/modal.js";
import { t } from "../utils/i18n.js";
import { errorState } from "../components/skeleton.js";

let _ws = null;
let _wsReconnectDelay = 5000;
let _wsReconnectTimer = null;
let _wsHeartbeatTimer = null;
let _pollTimer = null;
let _onMessage = null;
let _onUnreadCount = null;

// --- WebSocket client ---

function wsConnect() {
  const token = getToken();
  if (!token) return;

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  _ws = new WebSocket(`${proto}//${location.host}/api/v1/messages/ws?token=${token}`);

  _ws.onopen = () => {
    _wsReconnectDelay = 5000;
    startHeartbeat();
    stopPolling();
    updateBanner(false);
  };

  _ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === "chat" && _onMessage) _onMessage(data);
    else if (data.type === "unread_count" && _onUnreadCount) _onUnreadCount(data.count);
  };

  _ws.onclose = () => {
    _ws = null;
    stopHeartbeat();
    updateBanner(true);
    startPolling();
    scheduleReconnect();
  };

  _ws.onerror = () => {
    _ws?.close();
  };
}

function startHeartbeat() {
  stopHeartbeat();
  _wsHeartbeatTimer = setInterval(() => {
    if (_ws?.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 30000);
}

function stopHeartbeat() {
  if (_wsHeartbeatTimer) {
    clearInterval(_wsHeartbeatTimer);
    _wsHeartbeatTimer = null;
  }
}

function scheduleReconnect() {
  if (_wsReconnectTimer) return;
  _wsReconnectTimer = setTimeout(() => {
    _wsReconnectTimer = null;
    if (isLoggedIn()) wsConnect();
  }, _wsReconnectDelay);
  _wsReconnectDelay = Math.min(_wsReconnectDelay * 2, 30000);
}

function wsSend(data) {
  if (_ws?.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(data));
    return true;
  }
  return false;
}

// --- REST polling fallback ---

let _lastPollTs = null;

function startPolling() {
  stopPolling();
  _pollTimer = setInterval(async () => {
    try {
      if (_onUnreadCount) {
        const { count } = await api.get("/messages/unread-count");
        _onUnreadCount(count);
      }
    } catch {}
  }, 5000);
}

function stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

// --- Disconnect banner ---

function updateBanner(disconnected) {
  const banner = document.getElementById("disconnect-banner");
  if (banner) banner.style.display = disconnected ? "block" : "none";
}

// --- Helpers ---

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return t("time.just_now");
  if (diff < 3600) return t("time.minutes_ago", {n: Math.floor(diff / 60)});
  if (diff < 86400) return t("time.hours_ago", {n: Math.floor(diff / 3600)});
  return t("time.days_ago", {n: Math.floor(diff / 86400)});
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function avatarHtml(nickname, avatarUrl) {
  const initial = (nickname || "?")[0].toUpperCase();
  if (avatarUrl) {
    return `<div class="conv-avatar"><img src="${escapeHtml(avatarUrl)}" alt=""></div>`;
  }
  return `<div class="conv-avatar">${escapeHtml(initial)}</div>`;
}

// --- Components ---

function renderConversationList(conversations, activeId, onSelect) {
  if (!conversations.length) {
    return `<div class="msg-empty">${t("messages.no_conversations")}</div>`;
  }

  return conversations
    .map(
      (c) => `
    <div class="conv-item ${c.partner_id === activeId ? "active" : ""}" data-partner="${c.partner_id}">
      ${avatarHtml(c.partner_nickname, c.partner_avatar)}
      <div class="conv-info">
        <div class="conv-name">${escapeHtml(c.partner_nickname)}</div>
        <div class="conv-preview">${escapeHtml(c.last_message || "")}</div>
      </div>
      <div class="conv-meta">
        <span class="conv-time">${timeAgo(c.last_time)}</span>
        ${c.unread_count > 0 ? `<span class="conv-badge">${c.unread_count}</span>` : ""}
      </div>
    </div>
  `
    )
    .join("");
}

function renderMessageBubble(msg, myId) {
  const sent = msg.sender_id === myId;
  return `
    <div class="msg-bubble-wrap ${sent ? "sent" : "received"}">
      <div class="msg-bubble">${escapeHtml(msg.content)}</div>
      <span class="msg-time">${formatTime(msg.created_at)}</span>
    </div>
  `;
}

// --- Main page ---

let _state = {
  conversations: [],
  activePartner: null,
  partnerInfo: null,
  messages: [],
  page: 1,
  hasMore: true,
  loading: false,
};

export function renderMessages() {
  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "messages");

  if (!isLoggedIn()) {
    app.innerHTML = `<p class="text-gray-500 text-center py-8">${t("messages.login_required")}</p>`;
    return;
  }

  // Reset state
  _state = { conversations: [], activePartner: null, partnerInfo: null, messages: [], page: 1, hasMore: true, loading: false };

  app.innerHTML = `
    <div class="msg-layout" id="msg-layout">
      <div class="msg-sidebar" id="msg-sidebar">
        <div class="msg-sidebar-header">
          <h3>${t("messages.title")}</h3>
          <button class="msg-new-btn" id="msg-new-conv-btn">${t("messages.new_btn")}</button>
        </div>
        <div class="conv-list" id="conv-list">
          <div class="msg-loading">${t("messages.loading")}</div>
        </div>
      </div>
      <div class="msg-chat" id="msg-chat">
        <div class="disconnect-banner" id="disconnect-banner" style="display:none">
          ${t("messages.connection_lost")}
        </div>
        <div class="msg-empty-chat" id="msg-empty-chat">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
          </svg>
          <span>${t("messages.select_conversation")}</span>
        </div>
        <div id="msg-chat-active" style="display:none">
          <div class="msg-chat-header" id="msg-chat-header"></div>
          <div class="msg-messages" id="msg-messages-area"></div>
          <div class="msg-input-area">
            <textarea class="msg-input" id="msg-input" placeholder="${t("messages.type_placeholder")}" rows="1"></textarea>
            <button class="msg-send-btn" id="msg-send-btn">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  bindEvents();
  loadConversations();
  setupWebSocket();
}

function setupWebSocket() {
  _onMessage = handleIncomingMessage;
  _onUnreadCount = () => loadConversations();

  if (!_ws || _ws.readyState !== WebSocket.OPEN) {
    wsConnect();
  }
}

function bindEvents() {
  // Conversation list clicks
  document.getElementById("conv-list").addEventListener("click", (e) => {
    const item = e.target.closest(".conv-item");
    if (!item) return;
    const partnerId = parseInt(item.dataset.partner);
    openChat(partnerId);
  });

  // New conversation
  document.getElementById("msg-new-conv-btn").addEventListener("click", showNewConvModal);

  // Send message
  const input = document.getElementById("msg-input");
  const sendBtn = document.getElementById("msg-send-btn");

  sendBtn.addEventListener("click", sendMessage);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });

  // Scroll to top to load more
  const msgArea = document.getElementById("msg-messages-area");
  msgArea.addEventListener("scroll", () => {
    if (msgArea.scrollTop < 50 && _state.hasMore && !_state.loading) {
      loadMoreMessages();
    }
  });
}

// --- Data loading ---

async function loadConversations() {
  try {
    _state.conversations = await api.get("/messages/conversations");
    renderConvList();
  } catch {
    const list = document.getElementById("conv-list");
    if (list) list.innerHTML = errorState(t("error.load_failed"));
  }
}

function renderConvList() {
  const list = document.getElementById("conv-list");
  if (!list) return;
  list.innerHTML = renderConversationList(_state.conversations, _state.activePartner);
}

async function openChat(partnerId) {
  _state.activePartner = partnerId;
  _state.messages = [];
  _state.page = 1;
  _state.hasMore = true;

  // Find partner info from conversations
  const conv = _state.conversations.find((c) => c.partner_id === partnerId);
  if (conv) {
    _state.partnerInfo = { nickname: conv.partner_nickname, avatar_url: conv.partner_avatar };
  } else {
    try {
      const user = await api.get(`/users/${partnerId}`);
      _state.partnerInfo = { nickname: user.nickname, avatar_url: user.avatar_url };
    } catch {
      _state.partnerInfo = { nickname: "User", avatar_url: null };
    }
  }

  // Show chat area, hide empty state
  document.getElementById("msg-empty-chat").style.display = "none";
  document.getElementById("msg-chat-active").style.display = "flex";
  document.getElementById("msg-chat-active").style.flexDirection = "column";
  document.getElementById("msg-chat-active").style.flex = "1";
  document.getElementById("msg-chat-active").style.minHeight = "0";

  // Mobile: open chat
  document.getElementById("msg-layout").classList.add("chat-open");

  // Render header
  const online = _ws?.readyState === WebSocket.OPEN;
  document.getElementById("msg-chat-header").innerHTML = `
    <button class="msg-back-btn" id="msg-back-btn">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    </button>
    ${avatarHtml(_state.partnerInfo.nickname, _state.partnerInfo.avatar_url)}
    <span class="chat-partner-name">${escapeHtml(_state.partnerInfo.nickname)}</span>
    <span class="${online ? "online-dot" : "offline-dot"}"></span>
  `;

  // Back button for mobile
  const backBtn = document.getElementById("msg-back-btn");
  if (backBtn) {
    backBtn.addEventListener("click", () => {
      document.getElementById("msg-layout").classList.remove("chat-open");
      _state.activePartner = null;
      renderConvList();
    });
  }

  // Mark as read via WS
  wsSend({ type: "mark_read", partner_id: partnerId });

  renderConvList();
  await loadMessages();

  // Focus input
  document.getElementById("msg-input").focus();
}

async function loadMessages() {
  if (!_state.activePartner) return;
  _state.loading = true;

  try {
    const msgs = await api.get(`/messages/history/${_state.activePartner}?page=${_state.page}&page_size=30`);
    _state.messages = msgs;
    _state.hasMore = msgs.length >= 30;
    renderMessagesArea();
    scrollToBottom();
  } catch {
    showToast(t("error.load_failed"), "error");
  } finally {
    _state.loading = false;
  }
}

async function loadMoreMessages() {
  if (!_state.activePartner || !_state.hasMore) return;
  _state.loading = true;
  _state.page++;

  const area = document.getElementById("msg-messages-area");
  const prevHeight = area.scrollHeight;

  try {
    const msgs = await api.get(`/messages/history/${_state.activePartner}?page=${_state.page}&page_size=30`);
    _state.messages = [...msgs, ..._state.messages];
    _state.hasMore = msgs.length >= 30;
    renderMessagesArea();
    area.scrollTop = area.scrollHeight - prevHeight;
  } catch {
  } finally {
    _state.loading = false;
  }
}

function renderMessagesArea() {
  const area = document.getElementById("msg-messages-area");
  if (!area) return;

  const token = getToken();
  // Extract user id from JWT payload (lightweight, no lib needed)
  let myId = 0;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    myId = parseInt(payload.sub);
  } catch {}

  area.innerHTML = _state.messages.map((m) => renderMessageBubble(m, myId)).join("");
}

function scrollToBottom() {
  const area = document.getElementById("msg-messages-area");
  if (area) area.scrollTop = area.scrollHeight;
}

// --- Send message ---

async function sendMessage() {
  const input = document.getElementById("msg-input");
  const content = input.value.trim();
  if (!content || !_state.activePartner) return;

  input.value = "";
  input.style.height = "auto";

  // Try WS first
  const sent = wsSend({ type: "chat", receiver_id: _state.activePartner, content });

  if (!sent) {
    // REST fallback
    try {
      const msg = await api.post(`/messages/${_state.activePartner}`, { content });
      _state.messages.push(msg);
      renderMessagesArea();
      scrollToBottom();
      loadConversations();
    } catch {
      showToast(t("messages.send_failed"), "error");
    }
  }
}

// --- Incoming WS message ---

function handleIncomingMessage(data) {
  const token = getToken();
  let myId = 0;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    myId = parseInt(payload.sub);
  } catch {}

  // If this message belongs to current chat
  const partnerId = data.sender_id === myId ? data.receiver_id : data.sender_id;

  if (_state.activePartner === partnerId) {
    // Deduplicate
    if (!_state.messages.some((m) => m.id === data.id)) {
      _state.messages.push(data);
      renderMessagesArea();
      scrollToBottom();
    }
    // Mark as read
    if (data.sender_id !== myId) {
      wsSend({ type: "mark_read", partner_id: data.sender_id });
    }
  }

  loadConversations();
}

// --- New conversation modal ---

function showNewConvModal() {
  let searchTimeout;

  const html = `
    <input type="text" class="msg-search-input" id="msg-search-input" placeholder="${t("messages.search_placeholder")}">
    <div class="msg-search-results" id="msg-search-results">
      <p style="color:#9ca3af;text-align:center;padding:20px 0;font-size:0.9rem;">${t("messages.type_to_search")}</p>
    </div>
  `;

  openModal("New Conversation", html);

  const searchInput = document.getElementById("msg-search-input");
  const resultsEl = document.getElementById("msg-search-results");

  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    const q = searchInput.value.trim();
    if (!q) {
      resultsEl.innerHTML = `<p style="color:#9ca3af;text-align:center;padding:20px 0;font-size:0.9rem;">${t("messages.type_to_search")}</p>`;
      return;
    }
    searchTimeout = setTimeout(async () => {
      try {
        const users = await api.get(`/users/search?q=${encodeURIComponent(q)}`);
        if (!users.length) {
          resultsEl.innerHTML = `<p style="color:#9ca3af;text-align:center;padding:20px 0;font-size:0.9rem;">${t("messages.no_users")}</p>`;
          return;
        }
        resultsEl.innerHTML = users
          .map(
            (u) => `
          <div class="msg-search-item" data-uid="${u.id}">
            ${avatarHtml(u.nickname, u.avatar_url)}
            <div>
              <div style="font-weight:600;font-size:0.9rem">${escapeHtml(u.nickname)}</div>
              <div style="font-size:0.8rem;color:#6b7280">@${escapeHtml(u.username)}</div>
            </div>
          </div>
        `
          )
          .join("");

        resultsEl.querySelectorAll(".msg-search-item").forEach((item) => {
          item.addEventListener("click", () => {
            const uid = parseInt(item.dataset.uid);
            closeModal();
            openChat(uid);
          });
        });
      } catch {
        resultsEl.innerHTML = `<p style="color:#ef4444;text-align:center;padding:20px 0;font-size:0.9rem;">${t("messages.search_failed")}</p>`;
      }
    }, 300);
  });

  setTimeout(() => searchInput.focus(), 100);
}

// --- Cleanup on page leave ---

let _cleanupBound = false;

function ensureCleanup() {
  if (_cleanupBound) return;
  _cleanupBound = true;

  window.addEventListener("hashchange", () => {
    if (location.hash !== "#/messages") {
      stopPolling();
      stopHeartbeat();
      if (_wsReconnectTimer) {
        clearTimeout(_wsReconnectTimer);
        _wsReconnectTimer = null;
      }
      // Don't close WS — keep it alive for other pages
      _onMessage = null;
      _onUnreadCount = null;
    }
  });
}

ensureCleanup();

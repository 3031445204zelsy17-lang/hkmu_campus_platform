const { getLocale, getTexts } = require("../../utils/i18n");
const { request } = require("../../utils/request");
const { resolveUrl } = require("../../utils/post");
const { getInitial, formatChatTime } = require("../../utils/format");
const messages = require("../../utils/messages");
const auth = require("../../utils/auth");

// WS 连不上服务端时(wx.connectSocket 握手不兼容,见 utils/messages.js connect),
// 聊天页降级轮询拉新消息的间隔。WS 通时跳过,只用推送。
const CHAT_POLL_MS = 3000;

function dayLabel(iso, now, text) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  if (d.toDateString() === now.toDateString()) return text.today;
  const y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return text.yesterday;
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}/${d.getDate()}`;
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
}

// 后端 get_history 已 ASC(旧→新) 返回(DB DESC 查最近 N 条 + return list(reversed(...)));
// 前端勿再反转,否则双重 reverse 变新→旧,历史最早消息会跑到列表底部(退出再打开复现)
function normalizeMessages(rawList, myId) {
  const chrono = (rawList || []).slice();
  return chrono.map((m) => ({
    id: "m" + m.id,
    realId: m.id,
    mine: m.sender_id === myId,
    content: String(m.content || ""),
    createdAt: m.created_at,
    timeLabel: "",
    dateLabel: "",
    status: "sent",
    isRead: !!m.is_read,
  }));
}

Page({
  data: {
    text: getTexts("chat"),
    locale: getLocale(),
    loggedIn: false,
    partnerId: 0,
    partnerName: "",
    partnerAvatar: "",
    partnerInitial: "H",
    myId: 0,
    isSelf: false,
    loading: false,
    draft: "",
    messages: [],
    toView: "",
    hasMore: true,
    page: 1,
    notFound: false,
    emptyChat: false,
  },

  onLoad(options) {
    this._locale = getLocale();
    const partnerId = Number(options.user_id || 0);
    const storedUser = auth.getStoredUser();
    const myId = (storedUser && storedUser.id) || 0;
    const initialName = options.name ? decodeURIComponent(options.name) : "";
    const initialAvatar = options.avatar ? decodeURIComponent(options.avatar) : "";
    const loggedIn = !!(myId && wx.getStorageSync("hkmu_access_token"));

    this._seenIds = new Set();
    this._pending = new Map();
    this._chatHandler = null;

    this.setData({
      text: getTexts("chat"),
      locale: this._locale,
      partnerId,
      partnerName: initialName,
      partnerAvatar: initialAvatar,
      partnerInitial: getInitial(initialName),
      myId,
      isSelf: !!partnerId && partnerId === myId,
      loggedIn,
    });

    if (!loggedIn || this.data.isSelf || !partnerId) return;

    this.fetchPartner();
    this.loadHistory(true);
    messages.ensureConnected();
    messages.startPolling();
    this._startChatPoll();
    this._wireEvents();
    messages
      .markRead(partnerId)
      .then(() => messages.fetchUnread().catch(() => {}))
      .catch(() => {});
  },

  onShow() {
    this._locale = getLocale();
    this.setData({ text: getTexts("chat"), locale: this._locale });
    if (!this.data.loggedIn || this.data.isSelf) return;
    messages.ensureConnected();
    messages.startPolling();
    this._startChatPoll();
    this._wireEvents();
    if (this.data.partnerId && !this.data.loading) {
      // 回到本页:重拉兜底漏收 + 重新标已读
      this.loadHistory(true);
      messages.markRead(this.data.partnerId).catch(() => {});
    }
  },

  onHide() {
    this._unwireEvents();
    messages.stopPolling();
    this._stopChatPoll();
  },

  onUnload() {
    this._unwireEvents();
    messages.stopPolling();
    this._stopChatPoll();
    if (this._pending) {
      this._pending.forEach((p) => p.timer && clearTimeout(p.timer));
      this._pending.clear();
    }
  },

  handleLanguageChange(event) {
    this._locale = event.detail.locale;
    const text = getTexts("chat");
    const now = new Date();
    const msgs = this.data.messages.map((m) =>
      Object.assign({}, m, { timeLabel: formatChatTime(m.createdAt, text) }),
    );
    this._applyDayLabels(msgs, now);
    this.setData({ text, messages: msgs });
  },

  goToLogin() {
    wx.navigateTo({ url: "/pages/login/login" });
  },

  fetchPartner() {
    request({ path: `/users/${this.data.partnerId}`, auth: true })
      .then((u) => {
        if (!u) {
          this.setData({ notFound: true });
          return;
        }
        const name = u.nickname || u.username || "HKMU";
        this.setData({
          partnerName: name,
          partnerAvatar: resolveUrl(u.avatar_url),
          partnerInitial: getInitial(name),
        });
      })
      .catch(() => {
        /* 用入口传来的 name 兜底,不阻断 */
      });
  },

  loadHistory(reset) {
    if (this.data.loading) return Promise.resolve();
    const page = reset ? 1 : this.data.page;
    this.setData({ loading: true });
    return messages
      .fetchHistory(this.data.partnerId, page)
      .then((list) => {
        const text = getTexts("chat");
        const now = new Date();
        const normalized = normalizeMessages(list || [], this.data.myId);
        normalized.forEach((m) => {
          m.timeLabel = formatChatTime(m.createdAt, text);
          if (m.realId != null) this._seenIds.add(m.realId);
        });

        if (reset) {
          this._applyDayLabels(normalized, now);
          const toView = normalized.length ? normalized[normalized.length - 1].id : "msg-bottom";
          this.setData({
            messages: normalized,
            toView,
            page: 1,
            hasMore: normalized.length >= messages.HISTORY_PAGE_SIZE,
            loading: false,
            emptyChat: normalized.length === 0,
          });
          messages.fetchUnread().catch(() => {});
        } else {
          const boundaryId = this.data.messages.length ? this.data.messages[0].id : "";
          const merged = normalized.concat(this.data.messages);
          this._applyDayLabels(merged, now);
          this.setData({
            messages: merged,
            toView: boundaryId || (merged.length ? merged[0].id : ""),
            hasMore: normalized.length >= messages.HISTORY_PAGE_SIZE,
            loading: false,
          });
        }
      })
      .catch(() => {
        this.setData({ loading: false });
      });
  },

  loadOlder() {
    if (!this.data.hasMore || this.data.loading) return;
    this.setData({ page: this.data.page + 1 });
    this.loadHistory(false);
  },

  _applyDayLabels(msgs, now) {
    const text = this.data.text;
    const ref = now || new Date();
    let prevDay = "";
    for (const m of msgs) {
      const dl = dayLabel(m.createdAt, ref, text);
      const show = !!dl && dl !== prevDay;
      if (show) prevDay = dl;
      m.dateLabel = show ? dl : "";
    }
  },

  _wireEvents() {
    if (this._chatHandler) return;
    this._chatHandler = (payload) => this._handleIncoming(payload);
    messages.on("chat", this._chatHandler);
  },

  _unwireEvents() {
    if (this._chatHandler) {
      messages.off("chat", this._chatHandler);
      this._chatHandler = null;
    }
  },

  // ── 降级轮询:WS 断时定时拉当前会话新消息 ──────────────────────────
  // 根因 wx.connectSocket 连不上服务端 WS(python 标准客户端可连,微信 WS 握手不兼容),
  // 详见 utils/messages.js connect 注释。WS 通时 getState()==="open" 跳过只用推送;断时每
  // CHAT_POLL_MS 拉 page1 历史,增量 append 对方新消息(后端 history 端点会顺带把当前
  // 会话未读标已读,故只补 fetchUnread 校正全局角标)。自己发的 WS 断时已由 REST 走
  // _confirmSent 确认进 _seenIds,轮询不重复处理。
  _startChatPoll() {
    if (this._chatPollTimer) return;
    this._chatPollTimer = setInterval(() => this._pollNewMessages(), CHAT_POLL_MS);
  },

  _stopChatPoll() {
    if (this._chatPollTimer) {
      clearInterval(this._chatPollTimer);
      this._chatPollTimer = null;
    }
  },

  _pollNewMessages() {
    if (messages.getState() === "open") return; // WS 通 → 用推送,不轮询
    if (!wx.getStorageSync("hkmu_access_token")) {
      this._stopChatPoll(); // session 已失效(request.js 401 清了 token)→ 停轮询
      return;
    }
    if (!this.data.partnerId || this.data.isSelf || !this.data.loggedIn) return;
    messages
      .fetchHistory(this.data.partnerId, 1)
      .then((list) => {
        const myId = this.data.myId;
        const partnerId = this.data.partnerId;
        const text = this.data.text;
        const fresh = [];
        for (const m of (list || [])) {
          if (m.id == null) continue;
          if (this._seenIds.has(m.id)) continue; // 去重:历史/推送已见过
          // 只补对方发来的新消息;自己发的 WS 断时已由 REST 走 _confirmSent 确认进 _seenIds
          if (m.sender_id !== partnerId || m.receiver_id !== myId) continue;
          this._seenIds.add(m.id);
          fresh.push(m);
        }
        if (!fresh.length) return;
        const msgs = this.data.messages.slice();
        for (const m of fresh) {
          msgs.push({
            id: "m" + m.id,
            realId: m.id,
            mine: false,
            content: String(m.content || ""),
            createdAt: m.created_at,
            timeLabel: formatChatTime(m.created_at, text),
            dateLabel: "",
            status: "sent",
            isRead: true,
          });
        }
        this._applyDayLabels(msgs);
        this.setData({ messages: msgs, toView: "m" + fresh[fresh.length - 1].id });
        messages.fetchUnread().catch(() => {}); // history 已标已读,校正全局角标
      })
      .catch(() => {});
  },

  _handleIncoming(payload) {
    if (!payload) return;
    const myId = this.data.myId;
    const partnerId = this.data.partnerId;

    // 我自己的回显 → 确认 pending(按 content 匹配最早的)
    if (payload.senderId === myId && payload.receiverId === partnerId) {
      let matched = null;
      this._pending.forEach((p, tempId) => {
        if (!matched && p.content === payload.content) matched = tempId;
      });
      if (matched) {
        const p = this._pending.get(matched);
        this._pending.delete(matched);
        if (p && p.timer) clearTimeout(p.timer);
        this._confirmSent(matched, { id: payload.id });
        return;
      }
      if (payload.id != null) {
        if (this._seenIds.has(payload.id)) return;
        this._seenIds.add(payload.id);
      }
      return;
    }

    // 对方发来的
    if (payload.senderId === partnerId && payload.receiverId === myId) {
      if (payload.id != null) {
        if (this._seenIds.has(payload.id)) return;
        this._seenIds.add(payload.id);
      }
      const id = payload.id != null ? "m" + payload.id : "r" + Date.now();
      const msg = {
        id,
        realId: payload.id,
        mine: false,
        content: String(payload.content || ""),
        createdAt: payload.createdAt,
        timeLabel: formatChatTime(payload.createdAt, this.data.text),
        dateLabel: "",
        status: "sent",
        isRead: true,
      };
      const msgs = this.data.messages.concat(msg);
      this._applyDayLabels(msgs);
      this.setData({ messages: msgs, toView: id });
      // 正在该会话 → 标已读并刷新角标(纠正 transport 层的 +1)
      messages
        .markRead(partnerId)
        .then(() => messages.fetchUnread().catch(() => {}))
        .catch(() => {});
    }
  },

  onDraftInput(event) {
    this.setData({ draft: event.detail.value });
  },

  send() {
    const content = (this.data.draft || "").trim();
    if (!content || !this.data.loggedIn || this.data.isSelf) return;
    if (content.length > 2000) {
      wx.showToast({ title: this.data.text.tooLong, icon: "none" });
      return;
    }
    this.setData({ draft: "" });

    const nowIso = new Date().toISOString();
    const tempId = "t" + Date.now() + "_" + Math.floor(Math.random() * 1000);
    const tempMsg = {
      id: tempId,
      realId: null,
      mine: true,
      content,
      createdAt: nowIso,
      timeLabel: formatChatTime(nowIso, this.data.text),
      dateLabel: "",
      status: "pending",
      isRead: false,
    };
    const msgs = this.data.messages.concat(tempMsg);
    this._applyDayLabels(msgs);
    this.setData({ messages: msgs, toView: tempId });

    this._pending.set(tempId, { content, timer: null });
    const wsOk = messages.send({
      type: "chat",
      receiver_id: this.data.partnerId,
      content,
    });
    if (!wsOk) {
      this._deliverViaRest(tempId, content);
    } else {
      const entry = this._pending.get(tempId);
      entry.timer = setTimeout(() => {
        if (this._pending.has(tempId)) this._deliverViaRest(tempId, content);
      }, 6000);
    }
  },

  _deliverViaRest(tempId, content) {
    const p = this._pending.get(tempId);
    if (!p) return;
    this._pending.delete(tempId);
    if (p.timer) clearTimeout(p.timer);
    messages
      .postMessage(this.data.partnerId, content)
      .then((msg) => this._confirmSent(tempId, msg))
      .catch((err) => this._markFailed(tempId, err));
  },

  _confirmSent(tempId, realMsg) {
    const realId = realMsg && realMsg.id;
    const idx = this.data.messages.findIndex((m) => m.id === tempId);
    if (idx < 0) return;
    const msgs = this.data.messages.slice();
    msgs[idx] = Object.assign({}, msgs[idx], {
      id: realId != null ? "m" + realId : msgs[idx].id,
      realId,
      status: "sent",
    });
    if (realId != null) this._seenIds.add(realId);
    this.setData({ messages: msgs });
  },

  _markFailed(tempId, err) {
    const idx = this.data.messages.findIndex((m) => m.id === tempId);
    if (idx < 0) return;
    const msgs = this.data.messages.slice();
    msgs[idx] = Object.assign({}, msgs[idx], { status: "failed" });
    this.setData({ messages: msgs });
    const m = String((err && err.message) || "");
    if (/429|too many|rate/i.test(m)) {
      wx.showToast({ title: this.data.text.rateLimited, icon: "none" });
    }
  },

  retrySend(event) {
    const tempId = event.currentTarget.dataset.id;
    const target = this.data.messages.find((m) => m.id === tempId);
    if (!target) return;
    const idx = this.data.messages.findIndex((m) => m.id === tempId);
    const msgs = this.data.messages.slice();
    msgs[idx] = Object.assign({}, target, { status: "pending" });
    this.setData({ messages: msgs });

    this._pending.set(tempId, { content: target.content, timer: null });
    const wsOk = messages.send({
      type: "chat",
      receiver_id: this.data.partnerId,
      content: target.content,
    });
    if (!wsOk) {
      this._deliverViaRest(tempId, target.content);
    } else {
      const entry = this._pending.get(tempId);
      entry.timer = setTimeout(() => {
        if (this._pending.has(tempId)) this._deliverViaRest(tempId, target.content);
      }, 6000);
    }
  },
});

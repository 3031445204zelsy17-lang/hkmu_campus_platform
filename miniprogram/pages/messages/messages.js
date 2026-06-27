const { syncTabBar } = require("../../utils/tabbar");
const { getLocale, getTexts } = require("../../utils/i18n");
const { resolveUrl } = require("../../utils/post");
const { getInitial, formatChatTime } = require("../../utils/format");
const messages = require("../../utils/messages");
const auth = require("../../utils/auth");

function normalizeConversation(c, text) {
  const name = c.partner_nickname || "HKMU";
  const unread = Math.max(0, c.unread_count || 0);
  const preview = c.last_message
    ? String(c.last_message).replace(/\s+/g, " ").trim()
    : text.noMessage;
  return {
    partnerId: c.partner_id,
    name,
    avatar: resolveUrl(c.partner_avatar),
    initial: getInitial(name),
    preview,
    time: formatChatTime(c.last_time, text),
    isUnread: unread > 0,
    unread,
    unreadLabel: unread > 99 ? "99+" : String(unread),
  };
}

Page({
  data: {
    text: getTexts("messages"),
    locale: getLocale(),
    loggedIn: false,
    loading: false,
    searchKw: "",
    conversations: [],
    visibleConversations: [],
  },

  onLoad() {
    syncTabBar(this, 2);
  },

  onShow() {
    syncTabBar(this, 2);
    this._locale = getLocale();
    const loggedIn = !!(auth.getStoredUser() && wx.getStorageSync("hkmu_access_token"));
    this.setData({ text: getTexts("messages"), locale: this._locale, loggedIn });

    if (loggedIn) {
      messages.ensureConnected();
      messages.startPolling();
      messages.fetchUnread().catch(() => {});
      this._wireEvents();
      this.loadConversations();
    } else {
      this._unwireEvents();
    }
  },

  onHide() {
    this._unwireEvents();
    messages.stopPolling();
  },

  onUnload() {
    this._unwireEvents();
    messages.stopPolling();
  },

  onPullDownRefresh() {
    this.loadConversations(true).finally(() => wx.stopPullDownRefresh());
  },

  handleLanguageChange(event) {
    this._locale = event.detail.locale;
    this.setData({
      text: getTexts("messages"),
      locale: this._locale,
      visibleConversations: this._applySearch(this.data.conversations),
    });
  },

  _wireEvents() {
    if (this._onChat) return;
    this._onChat = () => this._scheduleReload();
    messages.on("chat", this._onChat);
  },

  _unwireEvents() {
    if (this._onChat) {
      messages.off("chat", this._onChat);
      this._onChat = null;
    }
    if (this._reloadTimer) {
      clearTimeout(this._reloadTimer);
      this._reloadTimer = null;
    }
  },

  // WS 连续到达时合并刷新,避免每条消息都重拉列表
  _scheduleReload() {
    if (this._reloadTimer) return;
    this._reloadTimer = setTimeout(() => {
      this._reloadTimer = null;
      if (this.data.loggedIn) {
        this.loadConversations(true);
      }
    }, 800);
  },

  loadConversations(silent) {
    if (!silent) {
      this.setData({ loading: true });
    }
    return messages
      .fetchConversations()
      .then((list) => {
        const text = getTexts("messages");
        const convs = (list || []).map((c) => normalizeConversation(c, text));
        this.setData({
          conversations: convs,
          visibleConversations: this._applySearch(convs),
          loading: false,
        });
      })
      .catch(() => {
        this.setData({ loading: false });
      });
  },

  _applySearch(convs) {
    const kw = (this.data.searchKw || "").trim().toLowerCase();
    if (!kw) {
      return convs;
    }
    return convs.filter((c) => {
      return (
        (c.name || "").toLowerCase().indexOf(kw) >= 0 ||
        (c.preview || "").toLowerCase().indexOf(kw) >= 0
      );
    });
  },

  onSearchInput(event) {
    this.setData({
      searchKw: event.detail.value,
      visibleConversations: this._applySearch(this.data.conversations),
    });
  },

  openConversation(event) {
    const ds = event.currentTarget.dataset;
    const params =
      `user_id=${ds.partnerId}` +
      `&name=${encodeURIComponent(ds.name || "")}` +
      `&avatar=${encodeURIComponent(ds.avatar || "")}`;
    wx.navigateTo({ url: `/pages/chat/chat?${params}` });
  },

  openNewChat() {
    wx.navigateTo({ url: "/pages/new-chat/new-chat" });
  },

  goToCommunity() {
    wx.switchTab({ url: "/pages/community/community" });
  },

  goToLogin() {
    wx.navigateTo({ url: "/pages/login/login" });
  },
});

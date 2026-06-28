const { getLocale, getTexts } = require("../../utils/i18n");
const { request } = require("../../utils/request");
const { resolveUrl } = require("../../utils/post");
const { getInitial } = require("../../utils/format");
const auth = require("../../utils/auth");
const social = require("../../utils/social");

// 把后端 UserOut 映射成 nc-user 卡片字段。results(搜索)/friends/suggest 三处复用,
// suggest 额外带 reason 标签(见 _applySocial)。
function toCard(u, text) {
  const name = u.nickname || u.username || (text && text.defaultAuthor) || "HKMU";
  return {
    id: u.id,
    name,
    avatar: resolveUrl(u.avatar_url),
    initial: getInitial(name),
    handle: u.username ? `@${u.username}` : "",
  };
}

// reason 是后端 i18n 信号(same_programme | hkmu_peer),这里翻成本地化标签文案。
function reasonLabel(reason, text) {
  if (!text) return "";
  if (reason === "same_programme") return text.suggestReasonSameProgramme;
  if (reason === "hkmu_peer") return text.suggestReasonHkmuPeer;
  return "";
}

Page({
  data: {
    text: getTexts("newChat"),
    locale: getLocale(),
    loggedIn: false,
    kw: "",
    results: [],
    searched: false,
    loading: false,
    friends: [],
    friendsLoaded: false,
    suggest: [],
    suggestLoaded: false,
  },

  onLoad() {
    this._locale = getLocale();
    // 缓存后端原始数据,语言切换时用当前文案重映射(见 _applySocial)。
    this._friendsRaw = [];
    this._suggestRaw = [];
    this.setData({ text: getTexts("newChat"), locale: this._locale });
  },

  onShow() {
    this._locale = getLocale();
    const loggedIn = !!(auth.getStoredUser() && wx.getStorageSync("hkmu_access_token"));
    this.setData({ text: getTexts("newChat"), locale: this._locale, loggedIn });

    if (!loggedIn) {
      // 登出态:清掉过期发现数据,搜索主路径仍可用
      if (this.data.friends.length || this.data.suggest.length) {
        this.setData({
          friends: [],
          suggest: [],
          friendsLoaded: false,
          suggestLoaded: false,
        });
      }
      return;
    }
    // 好友列表每次回来都刷(便宜,能反映新加的好友);推荐只首次加载(会话内很少变)。
    this.loadFriends();
    if (!this.data.suggestLoaded) this.loadSuggest();
  },

  handleLanguageChange(event) {
    this._locale = event.detail.locale;
    this.setData({ text: getTexts("newChat"), locale: this._locale });
    this._applySocial(); // reason 标签 / defaultAuthor 跟随语言重译
  },

  onInput(event) {
    const kw = event.detail.value;
    this.setData({ kw });
    if (this._debounce) {
      clearTimeout(this._debounce);
    }
    this._debounce = setTimeout(() => this.search(kw), 300);
  },

  search(kw) {
    const q = (kw || "").trim();
    if (!q) {
      this.setData({ results: [], searched: false, loading: false });
      return;
    }
    this.setData({ loading: true });
    const text = getTexts("newChat");
    request({ path: `/users/search?q=${encodeURIComponent(q)}`, auth: true })
      .then((list) => {
        const results = (list || []).map((u) => toCard(u, text));
        this.setData({ results, searched: true, loading: false });
      })
      .catch(() => {
        this.setData({ results: [], searched: true, loading: false });
      });
  },

  openUser(event) {
    const ds = event.currentTarget.dataset;
    const params =
      `user_id=${ds.id}` +
      `&name=${encodeURIComponent(ds.name || "")}` +
      `&avatar=${encodeURIComponent(ds.avatar || "")}`;
    wx.navigateTo({ url: `/pages/chat/chat?${params}` });
  },

  // ── Phase 5 社交冷启动:好友 + 同学推荐(C.6) ──────────────────────────────

  loadFriends() {
    social
      .fetchFriends()
      .then((list) => {
        this._friendsRaw = list || [];
        this._applySocial();
        this.setData({ friendsLoaded: true });
      })
      .catch(() => {
        // best-effort:失败当空,不阻塞搜索主路径
        this._friendsRaw = [];
        this.setData({ friends: [], friendsLoaded: true });
      });
  },

  loadSuggest() {
    social
      .fetchSuggest()
      .then((list) => {
        this._suggestRaw = list || [];
        this._applySocial();
        this.setData({ suggestLoaded: true });
      })
      .catch(() => {
        this._suggestRaw = [];
        this.setData({ suggest: [], suggestLoaded: true });
      });
  },

  // 用当前语言把缓存的原始数据重映射成展示卡片(load 成功 + 语言切换都调)。
  _applySocial() {
    const text = getTexts("newChat");
    const friends = (this._friendsRaw || []).map((f) => toCard(f.friend, text));
    const suggest = (this._suggestRaw || []).map((u) => {
      const card = toCard(u, text);
      card.reason = reasonLabel(u.reason, text);
      return card;
    });
    this.setData({ friends, suggest });
  },
});

const { getLocale, getTexts } = require("../../utils/i18n");
const { request } = require("../../utils/request");
const { resolveUrl } = require("../../utils/post");
const { getInitial } = require("../../utils/format");

Page({
  data: {
    text: getTexts("newChat"),
    locale: getLocale(),
    kw: "",
    results: [],
    searched: false,
    loading: false,
  },

  onLoad() {
    this._locale = getLocale();
    this.setData({ text: getTexts("newChat"), locale: this._locale });
  },

  handleLanguageChange(event) {
    this._locale = event.detail.locale;
    this.setData({ text: getTexts("newChat"), locale: this._locale });
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
    request({ path: `/users/search?q=${encodeURIComponent(q)}`, auth: true })
      .then((list) => {
        const results = (list || []).map((u) => {
          const name = u.nickname || u.username || "HKMU";
          return {
            id: u.id,
            name,
            avatar: resolveUrl(u.avatar_url),
            initial: getInitial(name),
            handle: u.username ? `@${u.username}` : "",
          };
        });
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
});

const { request } = require("../../utils/request");
const { formatDate } = require("../../utils/format");
const { syncTabBar } = require("../../utils/tabbar");
const { getLocale, getTexts } = require("../../utils/i18n");
const { PAGE_SIZE } = require("../../utils/config");

function normalizeNews(items, text = getTexts("news")) {
  return items.map((item) => ({
    category: item.category || text.defaultCategory,
    id: item.id,
    publishedAtLabel: formatDate(item.published_at) || text.justNow,
    sourceLabel: item.source_url ? text.copyableSource : "HKMU",
    sourceUrl: item.source_url,
    summary: item.summary || text.noSummary,
    title: item.title,
  }));
}

function filterNews(items, keyword) {
  const text = keyword.trim().toLowerCase();
  if (!text) {
    return items;
  }

  return items.filter((item) =>
    [item.title, item.summary, item.category].some((value) =>
      String(value || "").toLowerCase().includes(text),
    ),
  );
}

function buildView(items, keyword) {
  const filteredItems = filterNews(items, keyword);
  return {
    featuredItem: filteredItems[0] || null,
    filteredItems,
    listItems: filteredItems.slice(1),
  };
}

Page({
  data: {
    featuredItem: null,
    filteredItems: [],
    hasNext: true,
    items: [],
    keyword: "",
    listItems: [],
    loading: false,
    locale: getLocale(),
    page: 1,
    rawItems: [],
    text: getTexts("news"),
  },

  onShow() {
    this.applyLocale(getLocale());
    syncTabBar(this, 3);
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("news", locale);
    const items = normalizeNews(this.data.rawItems, text);

    this.setData(Object.assign({
      items,
      locale,
      text,
    }, buildView(items, this.data.keyword)));

    syncTabBar(this, 3);
  },

  onLoad() {
    this.loadNews(true);
  },

  onPullDownRefresh() {
    this.loadNews(true).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  onReachBottom() {
    if (!this.data.loading && this.data.hasNext) {
      this.loadNews(false);
    }
  },

  updateKeyword(event) {
    const keyword = event.detail.value;
    this.setData(
      Object.assign(
        { keyword },
        buildView(this.data.items, keyword),
      ),
    );
  },

  clearKeyword() {
    this.setData(
      Object.assign(
        { keyword: "" },
        buildView(this.data.items, ""),
      ),
    );
  },

  loadNews(reset) {
    if (this.data.loading) {
      return Promise.resolve();
    }

    const nextPage = reset ? 1 : this.data.page;
    this.setData({ loading: true });

    return request({
      path: `/news?page=${nextPage}&page_size=${PAGE_SIZE.list}`,
    })
      .then((data) => {
        const nextRawItems = data.items || [];
        const rawItems = reset ? nextRawItems : this.data.rawItems.concat(nextRawItems);
        const items = normalizeNews(rawItems, this.data.text);

        this.setData(
          Object.assign(
            {
              hasNext: !!data.has_next,
              items,
              page: nextPage + 1,
              rawItems,
            },
            buildView(items, this.data.keyword),
          ),
        );
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || this.data.text.loadFail,
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  copySourceLink(event) {
    const url = event.currentTarget.dataset.url;
    if (!url) {
      wx.showToast({
        title: this.data.text.noSource,
        icon: "none",
      });
      return;
    }

    const text = this.data.text;
    wx.setClipboardData({
      data: url,
      success() {
        wx.showToast({
          title: text.linkCopied,
          icon: "success",
        });
      },
    });
  },
});

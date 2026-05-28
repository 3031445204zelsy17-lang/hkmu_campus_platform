const { request } = require("../../utils/request");
const { formatDate } = require("../../utils/format");

function normalizeNews(items) {
  return items.map((item) => ({
    category: item.category || "校园",
    id: item.id,
    publishedAtLabel: formatDate(item.published_at) || "刚刚",
    sourceLabel: item.source_url ? "原文可复制" : "HKMU",
    sourceUrl: item.source_url,
    summary: item.summary || "暂无摘要",
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
    page: 1,
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
      path: `/news?page=${nextPage}&page_size=12`,
    })
      .then((data) => {
        const nextItems = normalizeNews(data.items || []);
        const items = reset ? nextItems : this.data.items.concat(nextItems);

        this.setData(
          Object.assign(
            {
              hasNext: !!data.has_next,
              items,
              page: nextPage + 1,
            },
            buildView(items, this.data.keyword),
          ),
        );
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || "加载失败",
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
        title: "暂无原文链接",
        icon: "none",
      });
      return;
    }

    wx.setClipboardData({
      data: url,
      success() {
        wx.showToast({
          title: "链接已复制",
          icon: "success",
        });
      },
    });
  },
});

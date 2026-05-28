const { request } = require("../../utils/request");
const { formatDate, getInitial } = require("../../utils/format");

function normalizeItems(items) {
  return items.map((item) => {
    const isFound = item.item_type === "found";
    const isResolved = item.status === "resolved";
    const author = item.author_nickname || "匿名用户";

    return {
      author,
      authorInitial: getInitial(author),
      category: item.category || "未分类",
      createdAtLabel: formatDate(item.created_at) || "刚刚",
      description: item.description,
      id: item.id,
      location: item.location || "地点未填写",
      statusClass: isResolved ? "mini-pill" : "mini-pill green",
      statusLabel: isResolved ? "已解决" : "进行中",
      title: item.title,
      typeClass: isFound ? "mini-pill orange" : "mini-pill red",
      typeLabel: isFound ? "招领" : "失物",
    };
  });
}

function filterItems(items, keyword) {
  const text = keyword.trim().toLowerCase();
  if (!text) {
    return items;
  }

  return items.filter((item) =>
    [item.title, item.description, item.category, item.location, item.author].some((value) =>
      String(value || "").toLowerCase().includes(text),
    ),
  );
}

function getTypeTabClasses(typeFilter) {
  return {
    allTabClass: typeFilter === "all" ? "segment-item active" : "segment-item",
    foundTabClass: typeFilter === "found" ? "segment-item active" : "segment-item",
    lostTabClass: typeFilter === "lost" ? "segment-item active" : "segment-item",
  };
}

function getStatusTabClasses(statusFilter) {
  return {
    activeStatusClass: statusFilter === "active" ? "segment-item active" : "segment-item",
    allStatusClass: statusFilter === "all" ? "segment-item active" : "segment-item",
    resolvedStatusClass: statusFilter === "resolved" ? "segment-item active" : "segment-item",
  };
}

Page({
  data: {
    activeStatusClass: "segment-item active",
    allStatusClass: "segment-item",
    allTabClass: "segment-item active",
    filteredItems: [],
    foundTabClass: "segment-item",
    hasNext: true,
    items: [],
    keyword: "",
    loading: false,
    lostTabClass: "segment-item",
    page: 1,
    resolvedStatusClass: "segment-item",
    statusFilter: "active",
    typeFilter: "all",
  },

  onLoad() {
    this.loadItems(true);
  },

  onPullDownRefresh() {
    this.loadItems(true).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  onReachBottom() {
    if (!this.data.loading && this.data.hasNext) {
      this.loadItems(false);
    }
  },

  setTypeFilter(event) {
    const typeFilter = event.currentTarget.dataset.filter;
    if (typeFilter === this.data.typeFilter) {
      return;
    }

    this.setData(Object.assign({ typeFilter }, getTypeTabClasses(typeFilter)));
    this.loadItems(true);
  },

  setStatusFilter(event) {
    const statusFilter = event.currentTarget.dataset.status;
    if (statusFilter === this.data.statusFilter) {
      return;
    }

    this.setData(Object.assign({ statusFilter }, getStatusTabClasses(statusFilter)));
    this.loadItems(true);
  },

  updateKeyword(event) {
    const keyword = event.detail.value;
    this.setData({
      filteredItems: filterItems(this.data.items, keyword),
      keyword,
    });
  },

  loadItems(reset) {
    if (this.data.loading) {
      return Promise.resolve();
    }

    const nextPage = reset ? 1 : this.data.page;
    const query = [`page=${nextPage}`, "page_size=12"];

    if (this.data.typeFilter !== "all") {
      query.push(`item_type=${this.data.typeFilter}`);
    }

    if (this.data.statusFilter !== "all") {
      query.push(`status=${this.data.statusFilter}`);
    }

    this.setData({ loading: true });

    return request({
      path: `/lostfound?${query.join("&")}`,
    })
      .then((data) => {
        const nextItems = normalizeItems(data.items || []);
        const items = reset ? nextItems : this.data.items.concat(nextItems);

        this.setData({
          filteredItems: filterItems(items, this.data.keyword),
          hasNext: !!data.has_next,
          items,
          page: nextPage + 1,
        });
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
});

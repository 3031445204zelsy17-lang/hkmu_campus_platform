const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { API_ORIGIN } = require("../../utils/config");
const { formatDate, getInitial } = require("../../utils/format");

const FEED_TABS = [
  { key: "newest", label: "最新" },
  { key: "hot", label: "热门" },
];

function avatarUrl(value) {
  if (!value) {
    return "";
  }

  return value.startsWith("/") ? `${API_ORIGIN}${value}` : value;
}

function compactNumber(value) {
  const number = Number(value || 0);
  if (number >= 1000) {
    return `${(number / 1000).toFixed(1)}k`;
  }
  return String(number);
}

function buildTabs(activeKey) {
  return FEED_TABS.map((tab) => ({
    className: tab.key === activeKey ? "segment-item active" : "segment-item",
    key: tab.key,
    label: tab.label,
  }));
}

function normalizePost(item) {
  const authorName = item.author_nickname || "HKMU 同学";
  const content = String(item.content || "").trim();

  return {
    authorAvatar: avatarUrl(item.author_avatar),
    authorInitial: getInitial(authorName),
    authorName,
    category: item.category || "校园",
    commentsLabel: compactNumber(item.comments_count),
    content,
    createdAtLabel: formatDate(item.created_at) || "刚刚",
    handle: `@campus${item.author_id || item.id}`,
    id: item.id,
    isLiked: !!item.is_liked,
    likeClass: item.is_liked ? "feed-action is-active" : "feed-action",
    likeLabel: compactNumber(item.likes_count),
    title: item.title,
    topicClass: item.likes_count > 0 ? "topic-pill hot" : "topic-pill",
  };
}

Page({
  data: {
    feedTabs: buildTabs("newest"),
    hasNext: true,
    keyword: "",
    loading: false,
    page: 1,
    posts: [],
    sort: "newest",
    user: null,
    userInitial: "H",
  },

  onShow() {
    auth.bootstrapSession().then((user) => {
      this.setData({
        user: user || null,
        userInitial: user ? user.initial : "H",
      });
      this.loadPosts(true);
    });
  },

  onPullDownRefresh() {
    this.loadPosts(true).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  onReachBottom() {
    if (!this.data.loading && this.data.hasNext) {
      this.loadPosts(false);
    }
  },

  updateKeyword(event) {
    this.setData({
      keyword: event.detail.value,
    });
  },

  submitSearch() {
    this.loadPosts(true);
  },

  clearSearch() {
    this.setData({ keyword: "" });
    this.loadPosts(true);
  },

  switchSort(event) {
    const sort = event.currentTarget.dataset.sort;
    if (!sort || sort === this.data.sort) {
      return;
    }

    this.setData({
      feedTabs: buildTabs(sort),
      sort,
    });
    this.loadPosts(true);
  },

  loadPosts(reset) {
    if (this.data.loading) {
      return Promise.resolve();
    }

    const nextPage = reset ? 1 : this.data.page;
    const query = [`page=${nextPage}`, "page_size=12", `sort=${this.data.sort}`];
    const keyword = this.data.keyword.trim();

    if (keyword) {
      query.push(`search=${encodeURIComponent(keyword)}`);
    }

    this.setData({ loading: true });

    return request({
      path: `/posts?${query.join("&")}`,
      auth: !!this.data.user,
    })
      .then((data) => {
        const nextPosts = (data.items || []).map(normalizePost);
        const posts = reset ? nextPosts : this.data.posts.concat(nextPosts);

        this.setData({
          hasNext: !!data.has_next,
          page: nextPage + 1,
          posts,
        });
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || "动态加载失败",
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  toggleLike(event) {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    const index = Number(event.currentTarget.dataset.index);
    const post = this.data.posts[index];
    if (!post) {
      return;
    }

    request({
      method: "POST",
      path: `/posts/${post.id}/like`,
      auth: true,
    })
      .then((updatedPost) => {
        const posts = this.data.posts.slice();
        posts[index] = normalizePost(updatedPost);
        this.setData({ posts });
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || "操作失败",
          icon: "none",
        });
      });
  },

  openComments() {
    wx.showToast({
      title: "评论详情页下一步接入",
      icon: "none",
    });
  },

  goCompose() {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    wx.navigateTo({ url: "/pages/compose/compose" });
  },

  goProfileOrLogin() {
    if (this.data.user) {
      wx.switchTab({ url: "/pages/profile/profile" });
      return;
    }

    wx.navigateTo({ url: "/pages/login/login" });
  },
});

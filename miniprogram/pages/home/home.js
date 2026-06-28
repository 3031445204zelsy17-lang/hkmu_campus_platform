const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { syncTabBar } = require("../../utils/tabbar");
const { getLocale, getTexts } = require("../../utils/i18n");
const { normalizePost, resolveUrl } = require("../../utils/post");
const { PAGE_SIZE } = require("../../utils/config");
const { openDMWith } = require("../../utils/dm");
const social = require("../../utils/social");

const FEED_TAB_KEYS = ["newest", "hot"];

function buildTabs(activeKey, text = getTexts("home")) {
  return FEED_TAB_KEYS.map((key) => ({
    className: key === activeKey ? "segment-item active" : "segment-item",
    key,
    label: text.feedTabs[key],
  }));
}

Page({
  data: {
    feedTabs: buildTabs("newest"),
    hasNext: true,
    keyword: "",
    loading: false,
    locale: getLocale(),
    page: 1,
    posts: [],
    rawPosts: [],
    sort: "newest",
    text: getTexts("home"),
    user: null,
    userInitial: "H",
  },

  onShow() {
    this.applyLocale(getLocale());
    syncTabBar(this, 0);

    const app = getApp();
    if (app.globalData && app.globalData.postsNeedRefresh) {
      app.globalData.postsNeedRefresh = false;
      this._hasLoadedPosts = false;
    }

    auth.bootstrapSession().then((user) => {
      this.setData({
        user: user || null,
        userInitial: user ? user.initial : "H",
      });
      if (!this._hasLoadedPosts) {
        this._hasLoadedPosts = true;
        this.loadPosts(true);
      }
      this._consumePendingInvite(user || null); // C.7 消费邀请码
    });
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("home", locale);
    const posts = this.data.rawPosts.map((item) => normalizePost(item, text));

    this.setData({
      feedTabs: buildTabs(this.data.sort, text),
      locale,
      posts,
      text,
    });

    syncTabBar(this, 0);
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
      feedTabs: buildTabs(sort, this.data.text),
      sort,
    });
    this.loadPosts(true);
  },

  loadPosts(reset) {
    if (this.data.loading) {
      return Promise.resolve();
    }

    const nextPage = reset ? 1 : this.data.page;
    const query = [`page=${nextPage}`, `page_size=${PAGE_SIZE.feed}`, `sort=${this.data.sort}`];
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
        const nextRawPosts = data.items || [];
        const rawPosts = reset ? nextRawPosts : this.data.rawPosts.concat(nextRawPosts);
        const posts = rawPosts.map((item) => normalizePost(item, this.data.text));

        this.setData({
          hasNext: !!data.has_next,
          page: nextPage + 1,
          posts,
          rawPosts,
        });
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
    this._likeLocks = this._likeLocks || {};
    if (this._likeLocks[post.id]) {
      return;
    }
    this._likeLocks[post.id] = true;

    const previousRawPost = this.data.rawPosts[index] || {};
    const previousLiked = !!post.isLiked;
    const nextLiked = !previousLiked;
    const currentLikes = Number((previousRawPost && previousRawPost.likes_count) || 0);
    const optimisticRawPosts = this.data.rawPosts.slice();
    optimisticRawPosts[index] = {
      ...previousRawPost,
      is_liked: nextLiked,
      likes_count: Math.max(0, currentLikes + (nextLiked ? 1 : -1)),
    };
    this.setData({
      posts: optimisticRawPosts.map((item) => normalizePost(item, this.data.text)),
      rawPosts: optimisticRawPosts,
    });

    request({
      method: "POST",
      path: `/posts/${post.id}/like`,
      auth: true,
    })
      .then((updatedPost) => {
        const rawPosts = this.data.rawPosts.slice();
        rawPosts[index] = updatedPost;
        const posts = rawPosts.map((item) => normalizePost(item, this.data.text));
        this.setData({ posts, rawPosts });
      })
      .catch((error) => {
        const rawPosts = this.data.rawPosts.slice();
        rawPosts[index] = previousRawPost;
        this.setData({
          posts: rawPosts.map((item) => normalizePost(item, this.data.text)),
          rawPosts,
        });
        wx.showToast({
          title: error.message || this.data.text.actionFail,
          icon: "none",
        });
      })
      .finally(() => {
        delete this._likeLocks[post.id];
      });
  },

  openComments() {
    wx.showToast({
      title: this.data.text.commentsSoon,
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

  goCommunity() {
    wx.switchTab({ url: "/pages/community/community" });
  },

  goLostFound() {
    wx.navigateTo({ url: "/pages/lostfound/lostfound" });
  },

  goNews() {
    wx.navigateTo({ url: "/pages/news/news" });
  },

  goPlanner() {
    wx.switchTab({ url: "/pages/planner/planner" });
  },

  openDM(event) {
    openDMWith(event.currentTarget.dataset.authorId);
  },

  // C.7: 消费 app.js 暂存的邀请码(?inv=xxx) → 自动双向好友 → 提示 + 可选跳 chat。
  // 未登录时保留 pendingInvite,等登录后 home onShow 再次触发时消费。
  _consumePendingInvite(user) {
    const app = getApp();
    const code = app.globalData && app.globalData.pendingInvite;
    if (!code) return;
    if (!user) return; // 未登录:留待登录后再消费
    // 立即清暂存,防 onShow 多次触发重复消费
    app.globalData.pendingInvite = null;

    const text = getTexts("social");
    wx.showLoading({ title: text.inviteLoading, mask: true });
    social
      .consumeInvite(code)
      .then((res) => {
        wx.hideLoading();
        const friend = (res && res.friend) || null;
        const created = !!(res && res.created);
        const name =
          (friend && (friend.nickname || friend.username)) || text.defaultAuthor;
        if (created && friend) {
          wx.showModal({
            title: text.inviteAddedTitle,
            content: text.inviteAddedDesc.replace("{name}", name),
            confirmText: text.inviteGoChat,
            cancelText: text.inviteDismiss,
            success: (m) => {
              if (m.confirm) {
                const params =
                  `user_id=${friend.id}` +
                  `&name=${encodeURIComponent(name)}` +
                  `&avatar=${encodeURIComponent(resolveUrl(friend.avatar_url) || "")}`;
                wx.navigateTo({ url: `/pages/chat/chat?${params}` });
              }
            },
          });
        } else {
          // 已是好友 / 自邀(后端 created=false)
          wx.showToast({ title: text.inviteAlreadyFriend, icon: "none" });
        }
      })
      .catch(() => {
        wx.hideLoading();
        wx.showToast({ title: text.inviteFail, icon: "none" });
      });
  },
});

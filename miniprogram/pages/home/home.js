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

    // PERF-2: 首屏 /users/me 与 /posts 并行(原串行,首屏耗时=sum 现在=max)。
    // loadPosts 提前触发;其 auth 读 storage 登录态(见 loadPosts),不依赖 bootstrap
    // 后的 setData,故登录用户首屏也能带上 is_liked 私有态。
    if (!this._hasLoadedPosts) {
      this._hasLoadedPosts = true;
      this.loadPosts(true);
    }

    // PERF-3: 暖路径——优先用 storage 缓存 user 渲染,跳过 bootstrapSession 的 /users/me。
    // storage 由 login/profile/bootstrapSession 更新,切 tab 不必每次重拉;
    // token 过期由 request 层 401 自动 refresh 兜底,不影响登录态。
    const cachedUser = auth.getStoredUser();
    if (cachedUser) {
      this.setData({ user: cachedUser, userInitial: cachedUser.initial });
      this._consumePendingInvite(cachedUser); // C.7 消费邀请码
    } else {
      auth.bootstrapSession().then((user) => {
        this.setData({
          user: user || null,
          userInitial: user ? user.initial : "H",
        });
        this._consumePendingInvite(user || null); // C.7 消费邀请码
      });
    }
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
      // PERF-2: 读 storage 登录态(非 this.data.user)——首屏并行时 user 尚未 setData,
      // 仍能正确带 Bearer,登录用户首屏保留 is_liked 私有态。
      auth: !!auth.getStoredUser(),
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

  onAvatarError(e) {
    this.setData({ [`posts[${e.currentTarget.dataset.idx}].authorAvatar`]: "" });
  },
  onImageError(e) {
    this.setData({ [`posts[${e.currentTarget.dataset.idx}].imageUrl`]: "" });
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

    // 乐观翻转立即生效。原 _likeLocks 硬锁会在点赞请求飞行期(Azure 往返 1-3s)拦截
    // "取消"点击 → 红心不动 = "不能取消"。现改乐观前置 + per-post 串行队列。
    this._applyOptimisticLike(index, !post.isLiked);

    // per-post 串行队列:后端 toggle 基于 DB 翻转,并发请求会竞态(同时读未赞都 INSERT)。
    // 串行保证翻转顺序 = 点击顺序;仅"链尾"请求完成时同步 UI,避免中途返回覆盖闪烁。
    this._likeChain = this._likeChain || {};
    const prev = (this._likeChain[post.id] || Promise.resolve()).catch(() => {});
    const mine = prev.then(() =>
      request({ method: "POST", path: `/posts/${post.id}/like`, auth: true })
        .then((updatedPost) => {
          if (this._likeChain[post.id] === mine) {
            this._syncLikeFromServer(post.id, updatedPost);
          }
        })
        .catch(() => {
          // 失败:若仍为链尾,重拉单帖真实态纠回(防乐观与 DB 偏离)
          if (this._likeChain[post.id] === mine) {
            request({ path: `/posts/${post.id}`, auth: !!auth.getStoredUser() })
              .then((p) => this._syncLikeFromServer(post.id, p))
              .catch(() => {});
          }
          wx.showToast({ title: this.data.text.actionFail, icon: "none" });
        }),
    );
    this._likeChain[post.id] = mine;
  },

  // 乐观更新单帖(翻转 is_liked + likes_count)并立即 setData
  // PERF-6: 单条 setData(`posts[i]`)只 patch 点赞这一条,不全量 map 重建整个 feed。
  _applyOptimisticLike(index, nextLiked) {
    const previousRawPost = this.data.rawPosts[index] || {};
    const currentLikes = Number((previousRawPost && previousRawPost.likes_count) || 0);
    const newRawPost = {
      ...previousRawPost,
      is_liked: nextLiked,
      likes_count: Math.max(0, currentLikes + (nextLiked ? 1 : -1)),
    };
    const rawPosts = this.data.rawPosts.slice();
    rawPosts[index] = newRawPost;
    this.setData({
      rawPosts,
      [`posts[${index}]`]: normalizePost(newRawPost, this.data.text),
    });
  },

  // 用后端真实态同步单帖(按 id 定位,因列表 index 可能随翻页变动)
  _syncLikeFromServer(postId, updatedPost) {
    const idx = this.data.rawPosts.findIndex((r) => r && r.id === postId);
    if (idx < 0) return;
    const rawPosts = this.data.rawPosts.slice();
    rawPosts[idx] = updatedPost;
    this.setData({
      rawPosts,
      [`posts[${idx}]`]: normalizePost(updatedPost, this.data.text),
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

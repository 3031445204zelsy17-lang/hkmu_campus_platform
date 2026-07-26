const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { syncTabBar } = require("../../utils/tabbar");
const { getLocale, getTexts } = require("../../utils/i18n");
const { normalizePost, resolveUrl, getPostsRevision, bumpPostsRevision, mergePostsById } = require("../../utils/post");
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

    // revision 比较(不清零):别处发帖/删帖/点赞/评论 bump 后,探测到比自己新 → 触发重拉。
    // 不在此处记已消费——仅 loadPosts 成功渲染后记(失败则下次 onShow 仍重试)。
    if (getPostsRevision() > (this._lastFeedRevision || 0)) {
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
    // append 去重(在途时丢弃后续 append);reset 不受 loading 拦截——总要发并作废在途。
    if (!reset && this.data.loading) {
      return Promise.resolve();
    }

    // generation guard:reset 自增代次,响应回调比对代次——旧请求迟到响应一律丢弃,
    // 修 sort 切换 / 下拉刷新 / 触底叠切换时「旧响应覆盖新 tab」竞态。
    this._feedGen = this._feedGen || 0;
    const gen = reset ? ++this._feedGen : this._feedGen;

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
        if (gen !== this._feedGen) return; // 旧代次:不写 data/page/hasNext
        const nextRawPosts = data.items || [];
        // 按 id 去重合并(reset 全量替换;append 去重),修 hot 位移/分页不稳重复帖。
        const rawPosts = reset ? nextRawPosts : mergePostsById(this.data.rawPosts, nextRawPosts);
        const posts = rawPosts.map((item) => normalizePost(item, this.data.text));

        this.setData({
          hasNext: !!data.has_next,
          page: nextPage + 1,
          posts,
          rawPosts,
        });
        this._lastFeedRevision = getPostsRevision(); // 仅成功响应后记已消费
      })
      .catch((error) => {
        if (gen !== this._feedGen) return; // 旧代次:不写错误态
        wx.showToast({
          title: error.message || this.data.text.loadFail,
          icon: "none",
        });
      })
      .finally(() => {
        // 仅当前代次清 loading:旧代次不清(reset 作废 append 后,由 reset 自己的 finally 释放)
        if (gen === this._feedGen) this.setData({ loading: false });
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
            // cross-tab 同步:别处(community/详情页)刷新点赞态;自己已是新态,记已消费免自刷。
            this._lastFeedRevision = bumpPostsRevision({ type: "like", postId: post.id });
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

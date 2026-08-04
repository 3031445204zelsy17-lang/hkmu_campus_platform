const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { syncTabBar } = require("../../utils/tabbar");
const { getLocale, getTexts } = require("../../utils/i18n");
const { normalizePost, getPostsRevision, bumpPostsRevision, mergePostsById } = require("../../utils/post");
const { PAGE_SIZE } = require("../../utils/config");
const { openDMWith } = require("../../utils/dm");

const FEED_TAB_KEYS = ["newest", "hot"];
const COMMUNITY_BOARD_KEYS = [
  "all",
  "discussion",
  "qa",
  "sharing",
  "campusNews",
  "lostfound",
  "other",
];

const COMMUNITY_BOARD_ROUTES = {
  campusNews: "/pages/news/news",
  lostfound: "/pages/lostfound/lostfound",
};

function buildTabs(activeKey, text = getTexts("community")) {
  return FEED_TAB_KEYS.map((key) => ({
    className: key === activeKey ? "segment-item active" : "segment-item",
    key,
    label: text.feedTabs[key],
  }));
}

function buildCommunityBoards(activeKey, text = getTexts("community")) {
  return COMMUNITY_BOARD_KEYS.map((key) => {
    const item = text.boards[key];

    return {
      className: key === activeKey ? "community-board-item active" : "community-board-item",
      icon: item.icon,
      key,
      label: item.label,
      route: COMMUNITY_BOARD_ROUTES[key] || "",
    };
  });
}

function inferCommunityBoardKey(item) {
  const source = [
    item.category,
    item.title,
    item.content,
  ].join(" ").toLowerCase();

  if (/lost|found|失物|招领|招領/.test(source)) return "lostfound";
  if (/news|notice|announcement|新聞|新闻|公告/.test(source)) return "campusNews";
  if (/q&a|qa|question|ask|問答|问答|求助|help/.test(source)) return "qa";
  if (/share|sharing|分享|life|activity|生活|活動|活动/.test(source)) return "sharing";
  if (/discussion|discuss|course|campus|討論|讨论|課程|课程|校園|校园/.test(source)) return "discussion";
  return "other";
}

function buildVisiblePosts(rawPosts, text, activeBoard) {
  const posts = rawPosts.map((item, index) => {
    // PERF-8: boardKey 基于 content,点赞/翻页/切 board 都不改 content →
    // 缓存到 rawPost._boardKey,避免每次 buildVisiblePosts(applyLocale/switchBoard/
    // 点赞同步)都对全量 rawPosts 重跑 5 条正则。content 编辑走别页,此处只读快照。
    if (!item._boardKey) {
      item._boardKey = inferCommunityBoardKey(item);
    }
    return normalizePost(item, text, {
      rawIndex: index,
      sectionKey: item._boardKey,
    });
  });

  if (activeBoard === "all") {
    return posts;
  }

  return posts.filter((item) => item.sectionKey === activeBoard);
}

Page({
  data: {
    categoryFilter: "all",
    communityBoards: buildCommunityBoards("all"),
    feedTabs: buildTabs("newest"),
    hasNext: true,
    keyword: "",
    loading: false,
    locale: getLocale(),
    page: 1,
    posts: [],
    rawPosts: [],
    sort: "newest",
    text: getTexts("community"),
    user: null,
  },

  onShow() {
    this.applyLocale(getLocale());
    syncTabBar(this, 1);

    // F6: 首次进社区弹一次规范摘要,点「我知道了」记 storage 不再重弹。
    // (storage 不绑语言,换语言不重弹——可接受:这是首访引导,非每次提醒。)
    if (!wx.getStorageSync("hkmu_community_terms_ack")) {
      wx.showModal({
        title: this.data.text.termsModalTitle,
        content: this.data.text.termsModalContent,
        showCancel: false,
        confirmText: this.data.text.termsModalConfirm,
        success: (res) => {
          if (res.confirm) {
            wx.setStorageSync("hkmu_community_terms_ack", true);
          }
        },
      });
    }

    // revision 比较(不清零):别处发帖/删帖/点赞/评论 bump 后,探测到比自己新 → 触发重拉。
    // 不在此处记已消费——仅 loadPosts 成功渲染后记(失败则下次 onShow 仍重试)。
    if (getPostsRevision() > (this._lastFeedRevision || 0)) {
      this._hasLoadedPosts = false;
    }

    // PERF-2: 首屏 /users/me 与 /posts 并行(原串行,首屏耗时=sum 现在=max)
    if (!this._hasLoadedPosts) {
      this._hasLoadedPosts = true;
      this.loadPosts(true);
    }

    // PERF-3: 暖路径——storage 有 user 直接用,跳过 bootstrapSession 的 /users/me
    const cachedUser = auth.getStoredUser();
    if (cachedUser) {
      this.setData({ user: cachedUser });
    } else {
      auth.bootstrapSession().then((user) => {
        this.setData({ user: user || null });
      });
    }
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("community", locale);
    const posts = buildVisiblePosts(this.data.rawPosts, text, this.data.categoryFilter);

    this.setData({
      communityBoards: buildCommunityBoards(this.data.categoryFilter, text),
      feedTabs: buildTabs(this.data.sort, text),
      locale,
      posts,
      text,
    });

    syncTabBar(this, 1);
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

  switchCommunityBoard(event) {
    const key = event.currentTarget.dataset.key;
    const route = event.currentTarget.dataset.route;

    if (!key || key === this.data.categoryFilter) {
      return;
    }

    if (route) {
      wx.navigateTo({ url: route });
      return;
    }

    this.setData({
      categoryFilter: key,
      communityBoards: buildCommunityBoards(key, this.data.text),
      posts: buildVisiblePosts(this.data.rawPosts, this.data.text, key),
    });
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
        const posts = buildVisiblePosts(rawPosts, this.data.text, this.data.categoryFilter);

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
    // 头像加载失败 → 置空，触发 wxml wx:else 走 authorInitial 字母兜底
    this.setData({ [`posts[${e.currentTarget.dataset.idx}].authorAvatar`]: "" });
  },
  onImageError(e) {
    // 配图加载失败 → 置空，wxml wx:if 隐藏（避免破损图标）
    this.setData({ [`posts[${e.currentTarget.dataset.idx}].imageUrl`]: "" });
  },
  toggleLike(event) {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    const index = Number(event.currentTarget.dataset.index);
    const post = this.data.posts[index];
    if (!post || post.rawIndex < 0) {
      return;
    }

    // 乐观翻转立即生效 + per-post 串行队列(原 _likeLocks 硬锁拦截取消点击 = "不能取消")
    this._applyOptimisticLike(post.rawIndex, !post.isLiked);

    this._likeChain = this._likeChain || {};
    const prev = (this._likeChain[post.id] || Promise.resolve()).catch(() => {});
    const mine = prev.then(() =>
      request({ method: "POST", path: `/posts/${post.id}/like`, auth: true })
        .then((updatedPost) => {
          if (this._likeChain[post.id] === mine) {
            this._syncLikeFromServer(post.id, updatedPost);
            // cross-tab 同步:别处(home/详情页)刷新点赞态;自己已是新态,记已消费免自刷。
            this._lastFeedRevision = bumpPostsRevision({ type: "like", postId: post.id });
          }
        })
        .catch(() => {
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

  _applyOptimisticLike(rawIndex, nextLiked) {
    const previousRawPost = this.data.rawPosts[rawIndex] || {};
    const currentLikes = Number((previousRawPost && previousRawPost.likes_count) || 0);
    const newRawPost = {
      ...previousRawPost,
      is_liked: nextLiked,
      likes_count: Math.max(0, currentLikes + (nextLiked ? 1 : -1)),
    };
    const rawPosts = this.data.rawPosts.slice();
    rawPosts[rawIndex] = newRawPost;
    this.setData({ rawPosts });
    // PERF-6: 单条 patch 可见列表(community posts 经 board filter,可见 index≠rawIndex)
    this._patchVisiblePost(rawIndex, newRawPost);
  },

  _syncLikeFromServer(postId, updatedPost) {
    const idx = this.data.rawPosts.findIndex((r) => r && r.id === postId);
    if (idx < 0) return;
    const rawPosts = this.data.rawPosts.slice();
    rawPosts[idx] = updatedPost;
    this.setData({ rawPosts });
    this._patchVisiblePost(idx, updatedPost);
  },

  // PERF-6: 单条 setData 可见列表里 rawIndex 匹配的那条,不全量 buildVisiblePosts。
  // 当前 board filter 下不可见(visibleIdx<0)则只更 rawPosts,不动 posts。
  _patchVisiblePost(rawIndex, rawPost) {
    const visibleIdx = this.data.posts.findIndex((p) => p && p.rawIndex === rawIndex);
    if (visibleIdx < 0) return;
    this.setData({
      [`posts[${visibleIdx}]`]: normalizePost(rawPost, this.data.text, {
        rawIndex,
        sectionKey: rawPost._boardKey || inferCommunityBoardKey(rawPost),
      }),
    });
  },

  openDetail(event) {
    const id = event.currentTarget.dataset.id;
    if (!id) {
      return;
    }
    wx.navigateTo({ url: `/pages/post-detail/post-detail?id=${id}` });
  },

  goCompose() {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    wx.navigateTo({ url: "/pages/compose/compose" });
  },

  openDM(event) {
    openDMWith(event.currentTarget.dataset.authorId);
  },
});

const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { syncTabBar } = require("../../utils/tabbar");
const { getLocale, getTexts } = require("../../utils/i18n");
const { formatDate, getInitial } = require("../../utils/format");
const { normalizePost, resolveUrl } = require("../../utils/post");
const { PAGE_SIZE } = require("../../utils/config");

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
  const posts = rawPosts.map((item, index) =>
    normalizePost(item, text, {
      rawIndex: index,
      sectionKey: inferCommunityBoardKey(item),
    }),
  );

  if (activeBoard === "all") {
    return posts;
  }

  return posts.filter((item) => item.sectionKey === activeBoard);
}

// Map a backend CommentOut row into the view shape used by community.wxml.
function normalizeComment(comment, text) {
  const authorName = comment.author_nickname || text.defaultAuthor;

  return {
    id: comment.id,
    authorInitial: getInitial(authorName),
    authorName,
    authorAvatar: resolveUrl(comment.author_avatar),
    content: String(comment.content || "").trim(),
    createdAtLabel: formatDate(comment.created_at) || text.justNow,
  };
}

Page({
  data: {
    categoryFilter: "all",
    commentState: {},
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

    const app = getApp();
    if (app.globalData && app.globalData.postsNeedRefresh) {
      app.globalData.postsNeedRefresh = false;
      this._hasLoadedPosts = false;
    }

    auth.bootstrapSession().then((user) => {
      this.setData({ user: user || null });
      if (!this._hasLoadedPosts) {
        this._hasLoadedPosts = true;
        this.loadPosts(true);
      }
    });
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
      if (key === "campusNews") {
        wx.switchTab({ url: route });
      } else {
        wx.navigateTo({ url: route });
      }
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
        const posts = buildVisiblePosts(rawPosts, this.data.text, this.data.categoryFilter);

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
    if (!post || post.rawIndex < 0) {
      return;
    }
    this._likeLocks = this._likeLocks || {};
    if (this._likeLocks[post.id]) {
      return;
    }
    this._likeLocks[post.id] = true;

    const previousRawPost = this.data.rawPosts[post.rawIndex] || {};
    const nextLiked = !post.isLiked;
    const currentLikes = Number((previousRawPost && previousRawPost.likes_count) || 0);
    const optimisticRawPosts = this.data.rawPosts.slice();
    optimisticRawPosts[post.rawIndex] = {
      ...previousRawPost,
      is_liked: nextLiked,
      likes_count: Math.max(0, currentLikes + (nextLiked ? 1 : -1)),
    };
    this.setData({
      posts: buildVisiblePosts(optimisticRawPosts, this.data.text, this.data.categoryFilter),
      rawPosts: optimisticRawPosts,
    });

    request({
      method: "POST",
      path: `/posts/${post.id}/like`,
      auth: true,
      })
      .then((updatedPost) => {
        const rawPosts = this.data.rawPosts.slice();
        rawPosts[post.rawIndex] = updatedPost;
        const posts = buildVisiblePosts(rawPosts, this.data.text, this.data.categoryFilter);
        this.setData({ posts, rawPosts });
      })
      .catch((error) => {
        const rawPosts = this.data.rawPosts.slice();
        rawPosts[post.rawIndex] = previousRawPost;
        this.setData({
          posts: buildVisiblePosts(rawPosts, this.data.text, this.data.categoryFilter),
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

  toggleComments(event) {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    const postId = Number(event.currentTarget.dataset.id);
    const prev = this.data.commentState[postId] || {};
    const willExpand = !prev.expanded;

    this.setData({
      [`commentState.${postId}.expanded`]: willExpand,
      [`commentState.${postId}.loading`]: willExpand && !prev.list,
      [`commentState.${postId}.list`]: prev.list || [],
      [`commentState.${postId}.draft`]: prev.draft || "",
    });

    if (willExpand && !prev.list) {
      this.loadComments(postId);
    }
  },

  loadComments(postId) {
    return request({
      path: `/posts/${postId}/comments?page=1&page_size=${PAGE_SIZE.comments}`,
      auth: !!this.data.user,
    })
      .then((data) => {
        const list = (data.items || []).map((comment) =>
          normalizeComment(comment, this.data.text),
        );
        this.setData({
          [`commentState.${postId}.list`]: list,
          [`commentState.${postId}.total`]: data.total || list.length,
          [`commentState.${postId}.loading`]: false,
        });
      })
      .catch((error) => {
        this.setData({
          [`commentState.${postId}.loading`]: false,
        });
        wx.showToast({
          title: error.message || this.data.text.loadFail,
          icon: "none",
        });
      });
  },

  updateCommentDraft(event) {
    const postId = Number(event.currentTarget.dataset.id);
    this.setData({
      [`commentState.${postId}.draft`]: event.detail.value,
    });
  },

  submitComment(event) {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    const postId = Number(event.currentTarget.dataset.id);
    const state = this.data.commentState[postId] || {};
    const content = (state.draft || "").trim();

    if (!content || state.submitting) {
      return;
    }

    this.setData({
      [`commentState.${postId}.submitting`]: true,
    });

    request({
      method: "POST",
      path: `/posts/${postId}/comments`,
      data: { content },
      auth: true,
    })
      .then((comment) => {
        const list = (state.list || []).concat(
          normalizeComment(comment, this.data.text),
        );
        this._bumpCommentsCount(postId, 1);
        this.setData({
          [`commentState.${postId}.list`]: list,
          [`commentState.${postId}.total`]: (state.total || 0) + 1,
          [`commentState.${postId}.draft`]: "",
          [`commentState.${postId}.submitting`]: false,
        });
        wx.showToast({
          title: this.data.text.commentSent,
          icon: "success",
        });
      })
      .catch((error) => {
        this.setData({
          [`commentState.${postId}.submitting`]: false,
        });
        wx.showToast({
          title: error.message || this.data.text.actionFail,
          icon: "none",
        });
      });
  },

  _bumpCommentsCount(postId, delta) {
    const index = this.data.rawPosts.findIndex((post) => post.id === postId);
    if (index < 0) {
      return;
    }
    const rawPosts = this.data.rawPosts.slice();
    const previous = rawPosts[index] || {};
    rawPosts[index] = {
      ...previous,
      comments_count: Math.max(0, Number(previous.comments_count || 0) + delta),
    };
    this.setData({
      rawPosts,
      posts: buildVisiblePosts(rawPosts, this.data.text, this.data.categoryFilter),
    });
  },

  goCompose() {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    wx.navigateTo({ url: "/pages/compose/compose" });
  },
});

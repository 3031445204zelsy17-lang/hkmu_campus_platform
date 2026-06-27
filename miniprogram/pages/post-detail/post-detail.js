const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");
const { formatDate, getInitial } = require("../../utils/format");
const { normalizePost, resolveUrl } = require("../../utils/post");
const { PAGE_SIZE } = require("../../utils/config");

// Map a backend CommentOut row into the view shape used by post-detail.wxml.
// (Moved here from community.js as part of Phase 1 ⑦ — community now links to
// this page instead of rendering comments inline.)
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
    postId: null,
    loading: true,
    notFound: false,
    post: null,
    rawPost: null,
    comments: [],
    rawComments: [],
    commentsTotal: 0,
    commentsLoading: true,
    draft: "",
    submitting: false,
    locale: getLocale(),
    text: getTexts("postDetail"),
    user: null,
  },

  onLoad(options) {
    this.setData({ postId: Number(options.id) });
  },

  onShow() {
    this.applyLocale(getLocale());

    auth.bootstrapSession().then((user) => {
      this.setData({ user: user || null });

      if (!this._loaded) {
        this._loaded = true;
        this.loadPost();
        this.loadComments();
      }
    });
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("postDetail", locale);
    const update = { locale, text };

    if (this.data.rawPost) {
      update.post = normalizePost(this.data.rawPost, text);
    }
    if (this.data.rawComments && this.data.rawComments.length) {
      update.comments = this.data.rawComments.map((comment) =>
        normalizeComment(comment, text),
      );
    }

    this.setData(update);
  },

  onPullDownRefresh() {
    Promise.all([this.loadPost(), this.loadComments()]).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  loadPost() {
    if (!this.data.postId) {
      // No id in the route (e.g. a malformed deep link) — show not-found
      // instead of hanging on the loading line.
      this.setData({ loading: false, notFound: true });
      return Promise.resolve();
    }

    this.setData({ loading: true, notFound: false });

    return request({
      path: `/posts/${this.data.postId}`,
      auth: !!this.data.user,
    })
      .then((rawPost) => {
        this.setData({
          rawPost,
          post: normalizePost(rawPost, this.data.text),
          loading: false,
          notFound: false,
        });
      })
      .catch((error) => {
        const message = String((error && error.message) || "");
        // 404 from get_post → show the not-found state instead of a toast.
        const notFound = /not found|404/i.test(message);
        this.setData({ loading: false, notFound });
        if (!notFound) {
          wx.showToast({
            title: message || this.data.text.loadFail,
            icon: "none",
          });
        }
      });
  },

  loadComments() {
    if (!this.data.postId) {
      return Promise.resolve();
    }

    this.setData({ commentsLoading: true });

    return request({
      path: `/posts/${this.data.postId}/comments?page=1&page_size=${PAGE_SIZE.comments}`,
      auth: !!this.data.user,
    })
      .then((data) => {
        const rawComments = data.items || [];
        this.setData({
          rawComments,
          comments: rawComments.map((comment) =>
            normalizeComment(comment, this.data.text),
          ),
          commentsTotal: data.total || rawComments.length,
          commentsLoading: false,
        });
      })
      .catch((error) => {
        this.setData({ commentsLoading: false });
        wx.showToast({
          title: (error && error.message) || this.data.text.loadFail,
          icon: "none",
        });
      });
  },

  toggleLike() {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    if (this._likeLock || !this.data.rawPost) {
      return;
    }
    this._likeLock = true;

    const previous = this.data.rawPost;
    const nextLiked = !previous.is_liked;
    const currentLikes = Number(previous.likes_count || 0);
    const optimistic = Object.assign({}, previous, {
      is_liked: nextLiked,
      likes_count: Math.max(0, currentLikes + (nextLiked ? 1 : -1)),
    });

    this.setData({
      rawPost: optimistic,
      post: normalizePost(optimistic, this.data.text),
    });

    request({
      method: "POST",
      path: `/posts/${this.data.postId}/like`,
      auth: true,
    })
      .then((updatedPost) => {
        this.setData({
          rawPost: updatedPost,
          post: normalizePost(updatedPost, this.data.text),
        });
      })
      .catch((error) => {
        this.setData({
          rawPost: previous,
          post: normalizePost(previous, this.data.text),
        });
        wx.showToast({
          title: (error && error.message) || this.data.text.actionFail,
          icon: "none",
        });
      })
      .finally(() => {
        this._likeLock = false;
      });
  },

  updateDraft(event) {
    this.setData({ draft: event.detail.value });
  },

  submitComment() {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }

    const content = (this.data.draft || "").trim();
    if (!content || this.data.submitting) {
      return;
    }

    this.setData({ submitting: true });

    request({
      method: "POST",
      path: `/posts/${this.data.postId}/comments`,
      data: { content },
      auth: true,
    })
      .then((comment) => {
        const rawComments = this.data.rawComments.concat(comment);
        // Keep the post's comment count label in sync with the new total.
        const rawPost = Object.assign({}, this.data.rawPost, {
          comments_count: Math.max(
            0,
            Number(this.data.rawPost.comments_count || 0) + 1,
          ),
        });

        this.setData({
          rawComments,
          comments: rawComments.map((item) => normalizeComment(item, this.data.text)),
          commentsTotal: this.data.commentsTotal + 1,
          rawPost,
          post: normalizePost(rawPost, this.data.text),
          draft: "",
          submitting: false,
        });

        // Nudge community to refetch on return so its comment counts stay fresh.
        const app = getApp();
        if (app && app.globalData) {
          app.globalData.postsNeedRefresh = true;
        }

        wx.showToast({
          title: this.data.text.commentSent,
          icon: "success",
        });
      })
      .catch((error) => {
        this.setData({ submitting: false });
        wx.showToast({
          title: (error && error.message) || this.data.text.actionFail,
          icon: "none",
        });
      });
  },

  goLogin() {
    wx.navigateTo({ url: "/pages/login/login" });
  },
});

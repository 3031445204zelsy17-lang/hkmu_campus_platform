const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");
const { formatDate, getInitial } = require("../../utils/format");
const { normalizePost, resolveUrl, bumpPostsRevision } = require("../../utils/post");
const { openDMWith } = require("../../utils/dm");
const { PAGE_SIZE } = require("../../utils/config");
const report = require("../../utils/report");

// Map a backend CommentOut row into the view shape used by post-detail.wxml.
// (Moved here from community.js as part of Phase 1 ⑦ — community now links to
// this page instead of rendering comments inline.)
function normalizeComment(comment, text) {
  const authorName = comment.author_nickname || text.defaultAuthor;

  return {
    id: comment.id,
    authorId: comment.author_id,
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
    reportSubmitted: false,
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

  openDM(event) {
    openDMWith(event.currentTarget.dataset.authorId);
  },

  // 头像加载失败 → 置空走字母兜底(对齐 home/community FR6)
  onAuthorAvatarError() {
    if (this.data.post) {
      this.setData({ "post.authorAvatar": "" });
    }
  },

  onCommentAvatarError(e) {
    const idx = Number(e.currentTarget.dataset.idx);
    if (!isNaN(idx)) {
      this.setData({ [`comments[${idx}].authorAvatar`]: "" });
    }
  },

  // 长按评论 → 举报该评论(走通用 report util,后端 target_type=comment)
  onReportComment(e) {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }
    const commentId = Number(e.currentTarget.dataset.id);
    if (!commentId) return;
    report.openReport("comment", commentId);
  },

  // 作者本人删帖(后端 posts.py delete_post: owner/admin 可删)
  onDeletePost() {
    if (!this.data.post || !this.data.user || this._deleting) {
      return;
    }
    wx.showModal({
      title: this.data.text.deleteAction,
      content: this.data.text.deleteConfirm,
      confirmText: this.data.text.deleteAction,
      success: (res) => {
        if (!res.confirm) return;
        this._deleting = true;
        request({ method: "DELETE", path: `/posts/${this.data.postId}`, auth: true })
          .then(() => {
            bumpPostsRevision({ type: "delete", postId: this.data.postId });
            wx.showToast({ title: this.data.text.deleteSuccess, icon: "success" });
            wx.navigateBack();
          })
          .catch((error) => {
            this._deleting = false;
            wx.showToast({
              title: (error && error.message) || this.data.text.actionFail,
              icon: "none",
            });
          });
      },
    });
  },

  // 分享这篇帖子(右上角「···」→ 转发/复制链接)。path 带 postId 回到该帖。
  onShareAppMessage() {
    const post = this.data.post || {};
    return {
      title: post.title || "HKMU Campus",
      path: `/pages/post-detail/post-detail?id=${this.data.postId || ""}`,
    };
  },

  // 举报这篇帖子(仅非作者可见)。原因走 actionSheet,可选补充说明,
  // 提交 POST /reports。重复举报(后端 UNIQUE 去重 409)→ 标记已举报并提示。
  onReportPost() {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }
    if (this.data.reportSubmitted) {
      wx.showToast({ title: this.data.text.reportAlready, icon: "none" });
      return;
    }
    const reasons = this.data.text.reportReasons || [];
    if (!reasons.length) return;
    const text = this.data.text;
    wx.showActionSheet({
      itemList: reasons.map((r) => r.label),
      success: (res) => {
        const reason = reasons[res.tapIndex];
        if (!reason) return;
        wx.showModal({
          title: text.reportSheetTitle,
          editable: true,
          placeholderText: text.reportDetailPrompt,
          confirmText: text.reportSubmit,
          success: (mres) => {
            if (!mres.confirm) return;
            this._submitReport(reason.code, (mres.content || "").trim() || null);
          },
        });
      },
    });
  },

  _submitReport(reasonCode, detail) {
    const text = this.data.text;
    request({
      method: "POST",
      path: "/reports",
      data: {
        target_type: "post",
        target_id: this.data.postId,
        reason_code: reasonCode,
        detail,
      },
      auth: true,
    })
      .then(() => {
        this.setData({ reportSubmitted: true });
        wx.showToast({ title: text.reportSuccess, icon: "success" });
      })
      .catch((error) => {
        const msg = String((error && error.message) || "");
        if (/already reported|409|已举报|已檢舉/i.test(msg)) {
          this.setData({ reportSubmitted: true });
          wx.showToast({ title: text.reportAlready, icon: "none" });
          return;
        }
        wx.showToast({ title: msg || text.reportFail, icon: "none" });
      });
  },

  // 长按作者头像 → 举报这个用户(匿名帖 authorId 为 null,守卫跳过)
  onReportAuthor(e) {
    if (!this.data.user) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }
    const authorId = Number(e.currentTarget.dataset.authorId);
    if (!authorId) return;
    report.openReport("user", authorId);
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
        bumpPostsRevision({ type: "like", postId: this.data.postId });
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

        // Bump feed revision:返回列表时刷新评论数(home/community 都受益)
        bumpPostsRevision({ type: "comment", postId: this.data.postId });

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

// pages/course-detail/course-detail.js
// Phase 7 Module A — 课程详情 + 内联标记 + 课评(后端零改,4 端点全就绪)
// 从 planner「我的课程」点课卡 navigateTo 进入。
// 参考 post-detail(detail + 评论列表 + composer)与 planner(标记/先修/categories 标签)。

const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");
const { formatDate, getInitial } = require("../../utils/format");
const { PAGE_SIZE } = require("../../utils/config");

const STATUS_ORDER = ["not_started", "in_progress", "completed"];

// prerequisites 是 JSON 文本列(如 '["COMP1080SEF"]'),复刻 planner.js:parsePrereqs
function parsePrereqs(raw) {
  try {
    const parsed = JSON.parse(raw || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch (e) {
    return [];
  }
}

// 把 1-5 的评分渲染成 5 格星字符串(列表/汇总用;composer 用可点的 view 列表)
function buildStarsText(rating) {
  const n = Math.max(0, Math.min(5, Number(rating) || 0));
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function buildComposerStars(draftRating) {
  const r = Number(draftRating) || 0;
  return [1, 2, 3, 4, 5].map((v) => ({ value: v, filled: v <= r }));
}

// 课程行 → 视图模型。categories/semester/year 标签复用 planner scope(同源学术词汇,不重复造 key)
function normalizeCourse(raw, plannerText, text) {
  const semKey = String(raw.semester || "").toLowerCase();
  const semLabelMap = {
    autumn: plannerText.semAutumn,
    spring: plannerText.semSpring,
    summer: plannerText.semSummer,
  };
  const yearLabel = (plannerText.yearLabel || "").replace(
    "{n}",
    raw.year != null ? raw.year : "",
  );
  const categoryLabel =
    (plannerText.categories && plannerText.categories[raw.category]) ||
    raw.category ||
    "";
  const prereqIds = parsePrereqs(raw.prerequisites);
  return {
    code: raw.code || "",
    name: raw.name || "",
    creditsLabel:
      (raw.credits != null ? raw.credits : "") + " " + (text.creditsSuffix || ""),
    categoryLabel,
    yearLabel,
    semesterLabel: semLabelMap[semKey] || raw.semester || "",
    description: raw.description || "",
    prereqText: prereqIds.join(", "),
    hasPrereqs: prereqIds.length > 0,
  };
}

function normalizeReview(raw, user, text) {
  const authorName = raw.author_nickname || text.defaultAuthor;
  const helpful = Number(raw.helpful_count) || 0;
  return {
    id: raw.id,
    authorId: raw.author_id,
    authorName,
    authorInitial: getInitial(authorName),
    starsText: buildStarsText(raw.rating),
    content: String(raw.content || "").trim(),
    dateLabel: formatDate(raw.created_at) || text.justNow,
    helpfulLabel: helpful > 0 ? " · " + helpful + " " + (text.helpfulSuffix || "") : "",
    isMine: !!(user && raw.author_id === user.id),
  };
}

Page({
  data: {
    courseId: null,
    loading: true,
    notFound: false,
    loggedIn: false,
    user: null,
    course: null,
    status: "not_started",
    statusSegments: [],
    reviews: [],
    reviewsTotal: 0,
    reviewsLoading: true,
    avgRatingLabel: "",
    avgStarsText: "",
    myReviewId: null,
    draftRating: 0,
    draftContent: "",
    composerStars: [],
    submitting: false,
    locale: getLocale(),
    text: getTexts("courseDetail"),
  },

  onLoad(options) {
    this.setData({ courseId: (options && options.id) || "" });
  },

  onShow() {
    this.applyLocale(getLocale());

    auth.bootstrapSession().then((user) => {
      const wasLoggedIn = this._wasLoggedIn;
      this._wasLoggedIn = !!user;
      this.setData({ user: user || null, loggedIn: !!user });

      if (!this._loaded) {
        this._loaded = true;
        this.loadCourse();
        this.loadReviews();
      } else if (user && !wasLoggedIn) {
        // 登录态变化(未登录 → 已登录):重拉课评以拿到 isMine/myReviewId
        this.loadReviews();
      }

      if (user) {
        this.loadProgress();
      }
    });
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("courseDetail", locale);
    const plannerText = getTexts("planner", locale);
    const update = { locale, text };

    if (this._rawCourse) {
      update.course = normalizeCourse(this._rawCourse, plannerText, text);
    }
    if (this._rawReviews && this._rawReviews.length) {
      update.reviews = this._rawReviews.map((r) =>
        normalizeReview(r, this.data.user, text),
      );
    }
    update.statusSegments = this._buildSegments(this.data.status, text);
    update.composerStars = buildComposerStars(this.data.draftRating);

    this.setData(update);
  },

  _buildSegments(status, text) {
    const labelMap = {
      not_started: text.statusNotStarted,
      in_progress: text.statusInProgress,
      completed: text.statusCompleted,
    };
    return STATUS_ORDER.map((key) => ({
      key,
      label: labelMap[key] || key,
      active: key === status,
    }));
  },

  onPullDownRefresh() {
    const tasks = [this.loadCourse(), this.loadReviews()];
    if (this.data.loggedIn) {
      tasks.push(this.loadProgress());
    }
    Promise.all(tasks).finally(() => wx.stopPullDownRefresh());
  },

  loadCourse() {
    if (!this.data.courseId) {
      this.setData({ loading: false, notFound: true });
      return Promise.resolve();
    }

    this.setData({ loading: true, notFound: false });

    return request({
      path: `/courses/${encodeURIComponent(this.data.courseId)}`,
      auth: false,
    })
      .then((raw) => {
        this._rawCourse = raw;
        this.setData({
          course: normalizeCourse(
            raw,
            getTexts("planner", this.data.locale),
            this.data.text,
          ),
          loading: false,
          notFound: false,
        });
      })
      .catch((error) => {
        const message = String((error && error.message) || "");
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

  loadProgress() {
    if (!this.data.courseId || !this.data.loggedIn) {
      return Promise.resolve();
    }
    return request({ path: "/courses/progress/me", auth: true })
      .then((rows) => {
        const map = {};
        (rows || []).forEach((r) => {
          if (r && r.course_id) {
            map[r.course_id] = r.status;
          }
        });
        this._progressMap = map;
        const status = map[this.data.courseId] || "not_started";
        this.setData({
          status,
          statusSegments: this._buildSegments(status, this.data.text),
        });
      })
      .catch(() => {
        // 进度拉取失败不阻塞页面(标记段保持默认未修)
      });
  },

  loadReviews() {
    if (!this.data.courseId) {
      return Promise.resolve();
    }
    this.setData({ reviewsLoading: true });

    return request({
      path: `/courses/${encodeURIComponent(this.data.courseId)}/reviews?page=1&page_size=${PAGE_SIZE.comments}`,
      auth: false,
    })
      .then((data) => {
        const items = (data && data.items) || [];
        this._rawReviews = items;
        const reviews = items.map((r) =>
          normalizeReview(r, this.data.user, this.data.text),
        );
        const total = (data && data.total) || items.length;
        const mine = items.find(
          (r) => this.data.user && r.author_id === this.data.user.id,
        );

        let avgRatingLabel = "";
        let avgStarsText = "";
        if (total > 0) {
          const sum = items.reduce((acc, r) => acc + (Number(r.rating) || 0), 0);
          const avg = sum / total;
          avgRatingLabel = avg.toFixed(1);
          avgStarsText = buildStarsText(Math.round(avg));
        }

        this.setData({
          reviews,
          reviewsTotal: total,
          reviewsLoading: false,
          myReviewId: mine ? mine.id : null,
          avgRatingLabel,
          avgStarsText,
        });
      })
      .catch((error) => {
        this.setData({ reviewsLoading: false });
        wx.showToast({
          title: (error && error.message) || this.data.text.loadFail,
          icon: "none",
        });
      });
  },

  // ── 内联标记(复用 PUT /courses/progress,与 planner 同语义)──

  onMark(e) {
    if (!this.data.loggedIn) {
      this.goLogin();
      return;
    }
    const next = e.currentTarget.dataset.status;
    if (!next || next === this.data.status || this._markLock) {
      return;
    }
    this._markLock = true;

    const prev = this.data.status;
    this.setData({
      status: next,
      statusSegments: this._buildSegments(next, this.data.text),
    });

    // 通知 planner 回返后重拉进度(本课状态变了)
    const app = getApp();
    if (app && app.globalData) {
      app.globalData.coursesNeedRefresh = true;
    }

    request({
      method: "PUT",
      path: "/courses/progress",
      data: { course_id: this.data.courseId, status: next },
      auth: true,
    })
      .then(() => {
        wx.showToast({ title: this.data.text.markSuccess, icon: "success" });
      })
      .catch((error) => {
        this.setData({
          status: prev,
          statusSegments: this._buildSegments(prev, this.data.text),
        });
        wx.showToast({
          title: (error && error.message) || this.data.text.actionFail,
          icon: "none",
        });
      })
      .finally(() => {
        this._markLock = false;
      });
  },

  // ── 课评 composer ──

  onPickStar(e) {
    const value = Number(e.currentTarget.dataset.value);
    if (!value || this.data.submitting) {
      return;
    }
    this.setData({ draftRating: value, composerStars: buildComposerStars(value) });
  },

  onDraftInput(e) {
    this.setData({ draftContent: e.detail.value });
  },

  submitReview() {
    if (!this.data.loggedIn) {
      this.goLogin();
      return;
    }
    if (this.data.submitting) {
      return;
    }

    const content = (this.data.draftContent || "").trim();
    const rating = Number(this.data.draftRating) || 0;
    if (rating < 1 || rating > 5 || !content) {
      wx.showToast({ title: this.data.text.reviewInvalid, icon: "none" });
      return;
    }

    this.setData({ submitting: true });

    request({
      method: "POST",
      path: `/courses/${encodeURIComponent(this.data.courseId)}/reviews`,
      data: { rating, content },
      auth: true,
    })
      .then(() => {
        this.setData({
          submitting: false,
          draftRating: 0,
          draftContent: "",
          composerStars: buildComposerStars(0),
        });
        return this.loadReviews().then(() => {
          wx.showToast({ title: this.data.text.reviewSent, icon: "success" });
        });
      })
      .catch((error) => {
        this.setData({ submitting: false });
        const message = String((error && error.message) || "");
        const already = /already|409/i.test(message);
        if (already) {
          // 后端一人一课一条:同步 myReviewId 以隐 composer、显删除
          this.loadReviews();
          wx.showToast({ title: this.data.text.alreadyReviewed, icon: "none" });
        } else {
          wx.showToast({
            title: message || this.data.text.actionFail,
            icon: "none",
          });
        }
      });
  },

  onDeleteReview(e) {
    const id = Number(e.currentTarget.dataset.id);
    if (!id) {
      return;
    }
    wx.showModal({
      title: this.data.text.deleteAction,
      content: this.data.text.deleteConfirm,
      confirmText: this.data.text.deleteAction,
      confirmColor: "#B42318",
      success: (res) => {
        if (!res.confirm) {
          return;
        }
        request({
          method: "DELETE",
          path: `/courses/reviews/${id}`,
          auth: true,
        })
          .then(() => {
            wx.showToast({ title: this.data.text.deleteSuccess, icon: "success" });
            this.setData({
              draftRating: 0,
              draftContent: "",
              composerStars: buildComposerStars(0),
            });
            this.loadReviews();
          })
          .catch((error) => {
            wx.showToast({
              title: (error && error.message) || this.data.text.actionFail,
              icon: "none",
            });
          });
      },
    });
  },

  goLogin() {
    wx.navigateTo({ url: "/pages/login/login" });
  },
});

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

// T15: GET review-stats → 三维汇总卡视图。某维无人评(avg=null)则不出行;
// 三维全无但有老 5 星 → legacy 字段走老样式展示(T17 兼容)。
function buildRatingStats(stats, text) {
  if (!stats || !stats.review_count) return null;
  const defs = [
    { key: "teaching", label: text.dimTeaching, hint: text.gradingHint, avg: stats.teaching_avg },
    { key: "workload", label: text.dimWorkload, hint: text.workloadHint, avg: stats.workload_avg },
    { key: "gain", label: text.dimGain, hint: "", avg: stats.gain_avg },
  ];
  const dims = defs
    .filter((d) => d.avg != null)
    .map((d) => ({
      key: d.key,
      label: d.label,
      hint: d.hint,
      value: Number(d.avg).toFixed(1),
      pct: Math.round((Number(d.avg) / 5) * 100),
    }));
  return {
    count: stats.review_count,
    dims,
    legacyAvg: stats.rating_avg != null ? Number(stats.rating_avg).toFixed(1) : "",
    legacyStars: stats.rating_avg != null ? buildStarsText(Math.round(stats.rating_avg)) : "",
  };
}

// T15: composer 三维草稿(给分/工作量/收获),每组 5 星,0 = 未选
function buildDimDrafts(draftDims, text) {
  const d = draftDims || {};
  return [
    { key: "teaching", label: text.dimTeaching, hint: text.gradingHint },
    { key: "workload", label: text.dimWorkload, hint: text.workloadHint },
    { key: "gain", label: text.dimGain, hint: "" },
  ].map((dim) => Object.assign({}, dim, {
    value: d[dim.key] || 0,
    stars: buildComposerStars(d[dim.key] || 0),
  }));
}

// T16: 避坑标签云 — 固定白名单全量渲染(0 票也出,可点即投票),tone 控配色。
// 键名与后端 models.REVIEW_TAGS 一一对应,i18n key = "tag_" + 键名。
const TAG_DEFS = [
  { key: "generous_grading", tone: "good" },
  { key: "tough_grading", tone: "bad" },
  { key: "heavy_workload", tone: "warn" },
  { key: "light_workload", tone: "good" },
  { key: "high_gain", tone: "good" },
  { key: "open_book", tone: "good" },
  { key: "group_project", tone: "bad" },
  { key: "attendance_strict", tone: "warn" },
];

function buildTagCloud(raw, text) {
  const byTag = {};
  ((raw && raw.tags) || []).forEach((t) => { byTag[t.tag] = t; });
  return TAG_DEFS.map((d) => ({
    tag: d.key,
    tone: d.tone,
    label: text["tag_" + d.key] || d.key,
    count: (byTag[d.key] && byTag[d.key].count) || 0,
    voted: !!(byTag[d.key] && byTag[d.key].voted),
  }));
}

// GE 官方目录信息 → 视图模型(backend _ge_info_for 富化的 raw.ge)。
// moi/学院名走 i18n 映射;学院反查由后端按目录打印完成,兜底 school_name 原文。
// 介绍段落是官方原文(单语:中授课→中文/英授课→英文,Bilingual→两段),不翻译。
function buildGeInfo(g, plannerText, text) {
  if (!g) return null;
  const moiMap = {
    english: text.geMoiEnglish,
    chinese: text.geMoiChinese,
    bilingual: text.geMoiBilingual,
  };
  const schoolKey = {
    "A&SS": "geSchoolASS",
    "B&A": "geSchoolBA",
    "E&L": "geSchoolEL",
    "N&HS": "geSchoolNHS",
    "S&T": "geSchoolST",
  }[g.school];
  const semMap = {
    autumn: plannerText.semAutumn,
    spring: plannerText.semSpring,
    summer: plannerText.semSummer,
  };
  const rows = [
    { label: text.geLevelLabel, value: g.level ? String(g.level) : "" },
    { label: text.geMoiLabel, value: moiMap[g.moi] || g.moi || "" },
    { label: text.geSchoolLabel, value: (schoolKey && text[schoolKey]) || g.school_name || "" },
  ].filter((r) => r.value);
  return {
    rows,
    terms: (g.terms || []).map((t) => semMap[t] || t),
    excludedText: (g.excluded || []).join(" · "),
    description: g.description || "",
  };
}

// 课程行 → 视图模型。categories/semester/year 标签复用 planner scope(同源学术词汇,不重复造 key)
function normalizeCourse(raw, plannerText, text) {
  const semKey = String(raw.semester || "").toLowerCase();
  const semLabelMap = {
    autumn: plannerText.semAutumn,
    spring: plannerText.semSpring,
    summer: plannerText.semSummer,
  };
  const ge = raw.ge || null;
  const yearLabel = (plannerText.yearLabel || "").replace(
    "{n}",
    raw.year != null ? raw.year : "",
  );
  const categoryLabel =
    (plannerText.categories && plannerText.categories[raw.category]) ||
    raw.category ||
    "";
  const prereqIds = parsePrereqs(raw.prerequisites);
  // meta 行:非 GE 保持「学分 · 第n年 · 学期」;GE 的 year=0/semester=any 是
  // seed sentinel(无意义),只显示学分,其余信息在官方資訊卡里
  const metaParts = [
    (raw.credits != null ? raw.credits : "") + " " + (text.creditsSuffix || ""),
  ];
  if (!ge) {
    metaParts.push(yearLabel, semLabelMap[semKey] || raw.semester || "");
  }
  return {
    code: raw.code || "",
    name: raw.name || "",
    metaLine: metaParts.filter(Boolean).join(" · "),
    categoryLabel,
    // GE:DB description 是 seed 的「中文名·领域」,让位官方介绍段(geInfo.description)
    description: ge ? "" : raw.description || "",
    geInfo: buildGeInfo(ge, plannerText, text),
    prereqText: prereqIds.join(", "),
    hasPrereqs: prereqIds.length > 0,
  };
}

// T17: 新式评论无老 5 星 → 星条让位三维摘要("给分 5 · 工作量 2 · 收获 4")
function buildDimsSummary(raw, text) {
  const parts = [];
  if (raw.rating_teaching != null) parts.push(text.dimTeaching + " " + raw.rating_teaching);
  if (raw.rating_workload != null) parts.push(text.dimWorkload + " " + raw.rating_workload);
  if (raw.rating_gain != null) parts.push(text.dimGain + " " + raw.rating_gain);
  return parts.join(" · ");
}

function normalizeReview(raw, user, text) {
  const authorName = raw.author_nickname || text.defaultAuthor;
  const helpful = Number(raw.helpful_count) || 0;
  return {
    id: raw.id,
    authorId: raw.author_id,
    authorName,
    authorInitial: getInitial(authorName),
    starsText: raw.rating != null ? buildStarsText(raw.rating) : "",
    dimsSummary: buildDimsSummary(raw, text),
    tagLabels: (raw.tags || []).map((t) => text["tag_" + t] || t),
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
    ratingStats: null,
    tagCloud: [],
    myReviewId: null,
    draftDims: { teaching: 0, workload: 0, gain: 0 },
    dimDrafts: [],
    draftContent: "",
    submitting: false,
    locale: getLocale(),
    text: getTexts("courseDetail"),
  },

  onLoad(options) {
    this.setData({ courseId: (options && options.id) || "" });
  },

  // 转发本课程(未定义此 handler 的页面,「···」菜单里的「转发」会置灰)。
  // 标题带课码+课名,path 带 id 让接收方点开直达这门课。
  onShareAppMessage() {
    const c = this.data.course || {};
    return {
      title: `${c.code || "Course"} · ${c.name || "HKMU Campus"}`,
      path: `/pages/course-detail/course-detail?id=${this.data.courseId || ""}`,
    };
  },

  // 点亮收藏(把单门课程页收进「我的小程序收藏」)
  onAddToFavorites() {
    const c = this.data.course || {};
    return {
      title: `${c.code || "Course"} · ${c.name || "HKMU Campus"}`,
      path: `/pages/course-detail/course-detail?id=${this.data.courseId || ""}`,
    };
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
        this.loadRatingStats();
        this.loadTagCloud();
      } else if (user && !wasLoggedIn) {
        // 登录态变化(未登录 → 已登录):重拉课评以拿到 isMine/myReviewId;
        // 标签云要带 token 重拉才有 voted 标记
        this.loadReviews();
        this.loadTagCloud();
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
    update.dimDrafts = buildDimDrafts(this.data.draftDims, text);
    if (this._rawStats) {
      update.ratingStats = buildRatingStats(this._rawStats, text);
    }
    if (this._rawTagCloud) {
      update.tagCloud = buildTagCloud(this._rawTagCloud, text);
    }

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
    const tasks = [this.loadCourse(), this.loadReviews(), this.loadRatingStats(), this.loadTagCloud()];
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

        this.setData({
          reviews,
          reviewsTotal: total,
          reviewsLoading: false,
          myReviewId: mine ? mine.id : null,
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

  // T15: 三维均分卡(失败不阻塞,列表/老汇总照常)
  loadRatingStats() {
    if (!this.data.courseId) {
      return Promise.resolve();
    }
    return request({
      path: `/courses/${encodeURIComponent(this.data.courseId)}/review-stats`,
      auth: false,
    })
      .then((stats) => {
        this._rawStats = stats;
        this.setData({ ratingStats: buildRatingStats(stats, this.data.text) });
      })
      .catch(() => {});
  },

  // T16: 避坑标签云(登录态带 token 才有 voted 标记;失败不阻塞)
  loadTagCloud() {
    if (!this.data.courseId) {
      return Promise.resolve();
    }
    return request({
      path: `/courses/${encodeURIComponent(this.data.courseId)}/review-tags`,
      auth: this.data.loggedIn,
    })
      .then((raw) => {
        this._rawTagCloud = raw;
        this.setData({ tagCloud: buildTagCloud(raw, this.data.text) });
      })
      .catch(() => {});
  },

  // T16: 点标签 → 投票/撤票(乐观更新,失败回滚)
  onTagVote(e) {
    if (!this.data.loggedIn) {
      this.goLogin();
      return;
    }
    const tag = e.currentTarget.dataset.tag;
    const cur = (this.data.tagCloud || []).find((t) => t.tag === tag);
    if (!tag || !cur || this._tagLock) {
      return;
    }
    this._tagLock = true;
    const prevCloud = this.data.tagCloud;
    const nextVoted = !cur.voted;
    this.setData({
      tagCloud: prevCloud.map((t) =>
        t.tag === tag
          ? Object.assign({}, t, {
              voted: nextVoted,
              count: Math.max(0, t.count + (nextVoted ? 1 : -1)),
            })
          : t,
      ),
    });
    request({
      method: nextVoted ? "POST" : "DELETE",
      path: `/courses/${encodeURIComponent(this.data.courseId)}/review-tags/${tag}`,
      auth: true,
    })
      .then(() => {
        this._rawTagCloud = null; // 原始缓存失效,下次进页重拉对齐计数
      })
      .catch(() => {
        this.setData({ tagCloud: prevCloud }); // 回滚
        wx.showToast({ title: this.data.text.actionFail, icon: "none" });
      })
      .finally(() => {
        this._tagLock = false;
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

  // ── 课评 composer(三维:给分/工作量/收获)──

  onPickDimStar(e) {
    const key = e.currentTarget.dataset.key;
    const value = Number(e.currentTarget.dataset.value);
    if (!key || !value || this.data.submitting) {
      return;
    }
    const draftDims = Object.assign({}, this.data.draftDims);
    draftDims[key] = value;
    this.setData({ draftDims, dimDrafts: buildDimDrafts(draftDims, this.data.text) });
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
    const d = this.data.draftDims || {};
    if (!content || !(d.teaching || d.workload || d.gain)) {
      wx.showToast({ title: this.data.text.reviewInvalid, icon: "none" });
      return;
    }

    this.setData({ submitting: true });

    request({
      method: "POST",
      path: `/courses/${encodeURIComponent(this.data.courseId)}/reviews`,
      data: {
        rating_teaching: d.teaching || null,
        rating_workload: d.workload || null,
        rating_gain: d.gain || null,
        content,
      },
      auth: true,
    })
      .then(() => {
        this.setData({
          submitting: false,
          draftDims: { teaching: 0, workload: 0, gain: 0 },
          dimDrafts: buildDimDrafts({ teaching: 0, workload: 0, gain: 0 }, this.data.text),
          draftContent: "",
        });
        this.loadRatingStats();
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
              draftDims: { teaching: 0, workload: 0, gain: 0 },
              dimDrafts: buildDimDrafts({ teaching: 0, workload: 0, gain: 0 }, this.data.text),
              draftContent: "",
            });
            this.loadRatingStats();
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

const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");
const { syncTabBar } = require("../../utils/tabbar");

// 小程序 locale → programmes.name 的字典 key
const LOCALE_NAME_KEY = {
  "zh-Hans": "zh-CN",
  "zh-Hant": "zh-TW",
  en: "en",
};

function localizeName(name, locale) {
  if (!name) {
    return "";
  }
  const key = LOCALE_NAME_KEY[locale] || "en";
  return name[key] || name.en || "";
}

function categoryPercent(earned, required) {
  if (!required || required <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((earned / required) * 100));
}

function fillTemplate(tpl, vars) {
  if (!tpl) {
    return "";
  }
  return tpl.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? vars[k] : ""));
}

// prerequisites 是 JSON 文本列(如 '["COMP1080SEF"]'),复刻网页 planner.js:1451
function parsePrereqs(raw) {
  try {
    const parsed = JSON.parse(raw || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch (e) {
    return [];
  }
}

function prereqsMet(prereqIds, progress) {
  if (!prereqIds || !prereqIds.length) return true;
  return prereqIds.every((id) => progress[id] === "completed");
}

const SEMESTER_ORDER = { autumn: 0, spring: 1, summer: 2 };

function semesterRank(name) {
  const key = String(name || "").toLowerCase();
  return SEMESTER_ORDER[key] != null ? SEMESTER_ORDER[key] : 99;
}

// 当前专业的课程按学年学期分组,每张卡带 status + 先修提示(仅提示,不阻塞标记)
function buildCoursesView(prog, idToCourse, progress, keyword, text) {
  if (!prog || !idToCourse) return { semesters: [], empty: true };
  const cats = prog.categories || {};
  const all = [];
  Object.keys(cats).forEach((key) => {
    (cats[key].courses || []).forEach((cid) => {
      const c = idToCourse[cid];
      if (c) all.push(c);
    });
  });
  const kw = keyword ? keyword.toLowerCase() : "";
  const filtered = kw
    ? all.filter((c) =>
        (c.code && String(c.code).toLowerCase().includes(kw)) ||
        (c.name && String(c.name).toLowerCase().includes(kw)))
    : all;
  const groups = {};
  filtered.forEach((c) => {
    const yr = c.year != null ? c.year : 0;
    const sem = c.semester || "other";
    const gk = yr + "::" + sem;
    if (!groups[gk]) groups[gk] = { year: yr, semester: sem, courses: [] };
    groups[gk].courses.push(c);
  });
  const semLabelMap = {
    autumn: text.semAutumn, spring: text.semSpring, summer: text.semSummer,
  };
  const semesters = Object.keys(groups).map((k) => groups[k]).sort((a, b) => {
    if (a.year !== b.year) return a.year - b.year;
    return semesterRank(a.semester) - semesterRank(b.semester);
  });
  semesters.forEach((g) => {
    g.label = fillTemplate(text.yearLabel, { n: g.year }) + " · " +
      (semLabelMap[String(g.semester).toLowerCase()] || g.semester);
    g.courses = g.courses.map((c) => {
      const status = progress[c.id] || "not_started";
      const prereqIds = parsePrereqs(c.prerequisites);
      const met = prereqsMet(prereqIds, progress);
      let prereqLabel = "";
      if (prereqIds.length) {
        prereqLabel = met ? text.prereqMet : (text.prereqPrefix + prereqIds.join(", "));
      }
      return {
        courseId: c.id,
        code: c.code,
        name: c.name,
        credits: c.credits,
        statusKey: status,
        statusLabel: status === "completed" ? text.statusCompleted :
          status === "in_progress" ? text.statusInProgress : "",
        prereqsMet: met,
        prereqLabel,
      };
    });
  });
  return { semesters, empty: !filtered.length };
}

Page({
  // ── 非响应式缓存：所有渲染都从缓存算，_emit() 是唯一的 setData 出口 ──
  // 这样每次切 tab / 换语言只触发一次 setData，避免密集 setData 跨原生桥卡顿。
  _locale: getLocale(),
  _catalogue: null,        // /courses/programmes 结果
  _status: null,           // /courses/graduation-status 结果
  _user: null,             // bootstrapSession 结果
  _userProgrammeCode: null,
  _selectedCode: null,     // 用户手动选的专业（优先于 saved）
  _loading: true,
  _loadError: null,
  _courses: null,           // /courses?page_size=50 → items
  _idToCourse: null,        // {course_id: course 对象}
  _progress: null,          // /courses/progress/me → {course_id: status}
  _activeTab: "overview",   // "overview" | "courses"
  _searchKeyword: "",
  _searchTimer: null,

  // ── 生命周期 ──────────────────────────────────────────────────────────

  onShow() {
    syncTabBar(this, 3);
    this._locale = getLocale();
    // course-detail 页标记课程后回返:作废会话级进度缓存,强制重拉(仪表盘/卡片状态)
    const app = getApp();
    if (app && app.globalData && app.globalData.coursesNeedRefresh) {
      app.globalData.coursesNeedRefresh = false;
      this._progress = null;
    }
    // 只有首次（无 catalogue）才显示 loading 占位；之后切回都用缓存瞬间渲染
    this._loading = !this._catalogue;
    this._emit();
    this._refresh();
  },

  onPullDownRefresh() {
    this._refresh().finally(() => wx.stopPullDownRefresh());
  },

  handleLanguageChange(event) {
    this._locale = event.detail.locale;
    syncTabBar(this, 3);
    this._emit(); // 仅本地重算三语，一次 setData，不发请求
  },

  // ── 异步数据：只更新缓存，再 _emit ────────────────────────────────────

  _refresh() {
    const catDone = this._catalogue
      ? Promise.resolve()
      : request({ path: "/courses/programmes", auth: false })
          .then((data) => {
            this._catalogue = data;
            this._loading = false;
            this._loadError = null;
          })
          .catch((error) => {
            this._loading = false;
            this._loadError = error.message;
          });

    return catDone.then(() => {
      this._emit();
      // 暖路径：本会话已解析过 user → 跳过 bootstrapSession（省 /users/me 一跳），
      // 直接刷 status。request 层遇 401 会自动刷新 access token；若最终失败则
      // fallback 回完整 bootstrap 重新校验登录态（也会捕获在别处登出的情况）。
      if (this._user) {
        return this._loadStatus().catch(() => this._bootstrapAndLoad());
      }
      return this._bootstrapAndLoad();
    });
  },

  _bootstrapAndLoad() {
    return auth
      .bootstrapSession()
      .then((user) => {
        this._user = user;
        this._userProgrammeCode = (user && user.programme_code) || null;
        this._emit();
        if (user) {
          return this._loadStatus();
        }
        return null;
      })
      .catch(() => {
        this._user = null;
        this._emit();
      });
  },

  _loadStatus() {
    const code = this._selectedCode || this._userProgrammeCode;
    if (!code) {
      return Promise.resolve();
    }
    const path = `/courses/graduation-status?programme_code=${encodeURIComponent(code)}`;
    // 并行预拉课程全量 + 用户进度(会话级缓存),再拉仪表盘
    return Promise.all([this._loadCourses(), this._loadProgress()])
      .then(() => request({ path, auth: true }))
      .then((status) => {
        this._status = status;
        this._emit();
      })
      .catch((error) => {
        wx.showToast({ title: error.message || getTexts("planner", this._locale).loadFail, icon: "none" });
        // 保留上次 status，不 blank 仪表盘
      });
  },

  _loadCourses() {
    if (this._courses) return Promise.resolve();
    return request({ path: "/courses?page_size=50", auth: false })
      .then((data) => {
        this._courses = (data && data.items) || [];
        const map = {};
        this._courses.forEach((c) => { if (c && c.id) map[c.id] = c; });
        this._idToCourse = map;
      })
      .catch(() => {
        this._courses = [];
        this._idToCourse = {};
      });
  },

  _loadProgress() {
    if (this._progress) return Promise.resolve();
    return request({ path: "/courses/progress/me", auth: true })
      .then((data) => {
        const map = {};
        (data || []).forEach((r) => { if (r && r.course_id) map[r.course_id] = r.status; });
        this._progress = map;
      })
      .catch(() => {
        this._progress = {};
      });
  },

  // ── 交互 ──────────────────────────────────────────────────────────────

  onProgrammeChange(event) {
    const idx = Number(event.detail.value);
    const prog = this._catalogue && this._catalogue.programmes[idx];
    this._selectedCode = prog ? prog.code : "";
    this._emit(); // 立刻切到新专业（_emit 会因 _status.programme_code 不匹配而落到静态视图）
    if (!this._user) {
      return;
    }
    // 持久化（best-effort）后按新专业重算进度
    request({ method: "PUT", path: "/users/me", data: { programme_code: this._selectedCode }, auth: true })
      .catch(() => {})
      .then(() => this._loadStatus());
  },

  goLogin() {
    wx.navigateTo({ url: "/pages/login/login" });
  },

  onTabChange(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab && tab !== this._activeTab) {
      this._activeTab = tab;
      this._emit();
    }
  },

  onSearchInput(e) {
    const kw = (e.detail.value || "").trim().toLowerCase();
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this._searchKeyword = kw;
      this._emit();
    }, 300);
  },

  openCourseDetail(e) {
    // 课程卡只在登录态渲染(showTabs = _user && status),点按即进详情页(页内内联标记)
    const courseId = e.currentTarget.dataset.courseId;
    if (!courseId) {
      return;
    }
    wx.navigateTo({
      url: `/pages/course-detail/course-detail?id=${encodeURIComponent(courseId)}`,
    });
  },

  // ── 唯一渲染出口：从缓存算出完整 view model，一次 setData ─────────────

  _emit() {
    const locale = this._locale;
    const text = getTexts("planner", locale);
    const catalogue = this._catalogue;
    const programmes = catalogue ? catalogue.programmes : [];

    // 选中优先级：手动选 > 用户已保存 > 后端默认
    const wanted = this._selectedCode || this._userProgrammeCode || (catalogue && catalogue.default_code) || "";
    let idx = programmes.findIndex((p) => p.code === wanted);
    if (idx < 0) {
      idx = 0;
    }
    const prog = programmes[idx];

    const programmeOptions = programmes.map((p) => ({
      code: p.code,
      label: localizeName(p.name, locale) + (p.coming_soon ? ` (${text.comingSoonTag})` : ""),
    }));

    const view = {
      locale,
      text,
      loading: this._loading,
      loggedIn: !!this._user,
      programmeOptions,
      programmeIndex: idx,
      programmeCode: prog ? prog.code : "",
      programmeName: prog ? localizeName(prog.name, locale) : "",
      programmeSchool: prog ? prog.school || "" : "",
      comingSoon: prog ? !!prog.coming_soon : false,
      percent: 0,
      creditsSummary: "",
      categoriesView: [],
      recommendations: [],
      heroCopy: "",
      activeTab: this._activeTab,
      showTabs: false,
      searchKeyword: this._searchKeyword,
      coursesView: { semesters: [], empty: true },
    };

    if (!prog || this._loading) {
      // 首次加载 / 无目录：留给 WXML 的 loading 或空态
      this.setData(view);
      return;
    }

    // 仅当 status 属于当前选中专业时才用它（切专业后旧 status 自动失效）
    const status =
      this._status && this._status.programme_code === prog.code && !prog.coming_soon
        ? this._status
        : null;

    if (this._user && status) {
      // 登录态仪表盘
      view.percent = Math.round(status.percent || 0);
      view.creditsSummary = fillTemplate(text.creditsSummary, {
        earned: status.earned_credits,
        total: status.total_credits,
      });
      view.categoriesView = (status.categories || []).map((c) => ({
        key: c.key,
        label: text.categories[c.key] || c.key,
        earned: c.earned_credits,
        required: c.min_credits,
        pct: categoryPercent(c.earned_credits, c.min_credits),
        color: c.color,
      }));
      view.recommendations = (status.recommendations || []).map((r) => ({
        course_id: r.course_id,
        code: r.code,
        name: r.name,
        credits: r.credits,
        categoryLabel: text.categories[r.category_key] || r.category_key,
      }));
      view.showTabs = true;
      if (this._idToCourse && this._progress) {
        view.coursesView = buildCoursesView(prog, this._idToCourse, this._progress, this._searchKeyword, text);
      }
    } else if (prog.coming_soon) {
      view.heroCopy = text.comingSoonCopy;
      view.activeTab = "overview";
    } else {
      // 未登录 / status 未到：用目录静态学分要求
      view.categoriesView = (prog.categories || []).map((c) => ({
        key: c.key,
        label: text.categories[c.key] || c.key,
        earned: null,
        required: c.min_credits,
        pct: 0,
        color: c.color,
      }));
      view.heroCopy = this._user ? "" : text.heroCopy;
    }

    this.setData(view);
  },
});

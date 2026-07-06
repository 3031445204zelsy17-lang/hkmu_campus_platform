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
  _courseCatalogue: null,        // /courses/catalogue/programmes (全校 ~107 专业 browse 目录)
  _catalogueCoursesCache: {},    // programme_code -> /courses/catalogue 课程分组（失败也写入 _failed:true 负缓存，防 _emit 死循环）
  _catalogueInflight: {},        // programme_code -> 进行中的 promise（去重并发请求）
  _catalogueCollapsed: {},       // bucket key -> false(已展开) 巨型专业折叠态
  _pickerList: [],               // _emit 算出的扁平 picker 项（onSelectProgramme 按 code 取）
  _programmeQuery: "",           // 专业搜索词（实时过滤）
  _programmeSearchTimer: null,   // 搜索防抖 timer

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
    const planningP = this._catalogue
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

    // browse 目录（全校专业）非关键：失败时 picker 回退到 planning 3 专业
    const browseP = this._courseCatalogue
      ? Promise.resolve()
      : request({ path: "/courses/catalogue/programmes", auth: false })
          .then((data) => { this._courseCatalogue = data; })
          .catch(() => {});

    return Promise.all([planningP, browseP]).then(() => {
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

  onProgrammeSearchInput(e) {
    const v = e.detail.value || "";
    if (this._programmeSearchTimer) clearTimeout(this._programmeSearchTimer);
    this._programmeSearchTimer = setTimeout(() => {
      this._programmeQuery = v;
      this._emit();
    }, 200);
  },

  onSelectProgramme(e) {
    const code = e.currentTarget.dataset.code;
    if (!code) return;
    const entry = (this._pickerList || []).find((p) => p.code === code);
    this._selectedCode = code;
    this._programmeQuery = "";
    if (this._user) {
      if (entry && entry.has_full_planning) {
        // 完整规划专业：持久化（best-effort）后按新专业重算进度
        request({ method: "PUT", path: "/users/me", data: { programme_code: code }, auth: true })
          .catch(() => {})
          .then(() => this._loadStatus());
      } else {
        // 目录专业：清旧 status（_emit 缓存未命中会自动拉目录并 re-emit）
        this._status = null;
      }
    }
    this._emit();
  },

  // 拉某专业的官方课程目录（会话级缓存 + in-flight 去重 + 失败负缓存，
  // 防 _emit 缓存未命中→重拉→失败→re-emit 的死循环）
  _loadCatalogueCourses(code) {
    if (!code) return Promise.resolve(null);
    if (Object.prototype.hasOwnProperty.call(this._catalogueCoursesCache, code)) {
      return Promise.resolve(this._catalogueCoursesCache[code]);
    }
    if (this._catalogueInflight[code]) {
      return this._catalogueInflight[code];
    }
    const path = `/courses/catalogue?programme_code=${encodeURIComponent(code)}`;
    const p = request({ path, auth: false })
      .then((data) => {
        this._catalogueCoursesCache[code] = data;
        return data;
      })
      .catch((err) => {
        // 负缓存：失败也写入（_failed 标记），UI 显加载失败、不再重拉
        this._catalogueCoursesCache[code] = {
          buckets: [],
          _failed: true,
          _error: err && err.message,
        };
        return this._catalogueCoursesCache[code];
      })
      .then((res) => {
        this._catalogueInflight[code] = null;
        return res;
      });
    this._catalogueInflight[code] = p;
    return p;
  },

  // 目录课程 → 桶视图（巨型桶默认折叠显前 10）
  _buildCatalogueBuckets(data, text) {
    const collapsed = this._catalogueCollapsed || {};
    return (data.buckets || []).map((b) => {
      const labelKey = `bucket_${b.key}`;
      const label = text[labelKey] || b.key.replace(/-/g, " ");
      const all = (b.courses || []).map((c) => ({
        code: c.course_code,
        name: c.display_name,
        credits: c.credits,
        system: c.code_system,
      }));
      const isMega = all.length > 30;
      const isCollapsed = isMega && collapsed[b.key] !== false;
      return {
        key: b.key,
        label,
        total: all.length,
        courses: isCollapsed ? all.slice(0, 10) : all,
        collapsed: isCollapsed,
        showAllLabel: fillTemplate(text.catalogueShowAll, { n: all.length }),
      };
    });
  },

  onToggleBucket(e) {
    const key = e.currentTarget.dataset.bucket;
    this._catalogueCollapsed = this._catalogueCollapsed || {};
    this._catalogueCollapsed[key] = false; // 展开
    this._emit();
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
    const planning = this._catalogue;
    const browse = this._courseCatalogue;

    // 扁平 picker 列表：优先 browse 目录（全校 ~107），否则回退 planning 3 专业
    let pickerList = [];
    if (browse && browse.schools) {
      for (const sch of browse.schools) {
        for (const p of sch.programmes) {
          const known = planning && planning.programmes.find((x) => x.code === p.programme_code);
          const name = known ? localizeName(known.name, locale) : p.programme_name;
          pickerList.push({
            code: p.programme_code,
            has_full_planning: !!p.has_full_planning,
            school: p.school || (known && known.school) || "",
            label: name + (p.has_full_planning ? ` (${text.catalogueTagFull})` : ` (${text.catalogueTagCatalogue})`),
          });
        }
      }
    } else if (planning) {
      pickerList = planning.programmes.map((p) => ({
        code: p.code,
        has_full_planning: !p.coming_soon,
        school: p.school || "",
        label: localizeName(p.name, locale) + (p.coming_soon ? ` (${text.catalogueTagCatalogue})` : ` (${text.catalogueTagFull})`),
      }));
    }
    this._pickerList = pickerList;

    // 选中优先级：手动选 > 已保存(须完整规划专业) > 默认
    const saved = this._userProgrammeCode;
    const savedValid = saved && pickerList.some((p) => p.code === saved && p.has_full_planning);
    const wanted = this._selectedCode
      || (savedValid ? saved : "")
      || (planning && planning.default_code)
      || (browse && browse.default_programme_code)
      || "";
    let idx = pickerList.findIndex((p) => p.code === wanted);
    if (idx < 0) idx = 0;
    const entry = pickerList[idx];

    // 专业搜索过滤 + 按学院分组（picker 已改为搜索列表）
    const pq = (this._programmeQuery || "").trim().toLowerCase();
    const searchGroups = [];
    let programmeSearchEmpty = false;
    if (pickerList.length) {
      const gmap = new Map();
      for (const p of pickerList) {
        if (pq) {
          const hay = `${p.label} ${p.code} ${p.school || ""}`.toLowerCase();
          if (!hay.includes(pq)) continue;
        }
        if (!gmap.has(p.school)) gmap.set(p.school, []);
        gmap.get(p.school).push({
          code: p.code,
          label: p.label,
          has_full_planning: p.has_full_planning,
          selected: !!entry && p.code === entry.code,
        });
      }
      for (const [school, progs] of gmap) searchGroups.push({ school, programmes: progs });
      programmeSearchEmpty = !!pq && searchGroups.length === 0;
    }

    const view = {
      locale,
      text,
      loading: this._loading,
      loggedIn: !!this._user,
      programmeOptions: pickerList,
      programmeIndex: idx,
      programmeQuery: this._programmeQuery,
      programmeSearchResults: searchGroups,
      programmeSearchEmpty,
      programmeCode: entry ? entry.code : "",
      programmeName: entry ? entry.label.replace(/\s*\([^)]*\)\s*$/, "") : "",
      programmeSchool: entry ? entry.school || "" : "",
      comingSoon: false,
      viewMode: "planning",
      catalogueDisclaimer: "",
      catalogueProgrammeName: "",
      catalogueSchool: "",
      catalogueTotal: 0,
      catalogueBuckets: [],
      catalogueLoading: false,
      catalogueLoadError: "",
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

    if (!entry || this._loading) {
      // 首次加载 / 无目录：留给 WXML 的 loading 或空态
      this.setData(view);
      return;
    }

    // ── 目录专业（非完整规划）→ 只读课程目录视图 ──
    if (!entry.has_full_planning) {
      view.viewMode = "catalogue";
      view.catalogueDisclaimer = text.catalogueDisclaimer;
      const cached = this._catalogueCoursesCache[entry.code];
      if (cached && cached._failed) {
        // 负缓存命中：显加载失败，不再重拉（避免死循环）
        view.catalogueProgrammeName = view.programmeName;
        view.catalogueSchool = view.programmeSchool;
        view.catalogueLoadError = text.catalogueLoadFail;
      } else if (cached) {
        view.catalogueProgrammeName = cached.programme_name || view.programmeName;
        view.catalogueSchool = cached.school || view.programmeSchool;
        view.catalogueBuckets = this._buildCatalogueBuckets(cached, text);
        view.catalogueTotal = (cached.buckets || []).reduce(
          (n, b) => n + (b.courses ? b.courses.length : 0), 0,
        );
      } else {
        view.catalogueProgrammeName = view.programmeName;
        view.catalogueSchool = view.programmeSchool;
        view.catalogueLoading = true;
        this._loadCatalogueCourses(entry.code).then(() => this._emit());
      }
      this.setData(view);
      return;
    }

    // ── 完整规划专业（DSAI）→ 既有仪表盘/课程流 ──
    const programmes = planning ? planning.programmes : [];
    const prog = programmes.find((p) => p.code === entry.code) || programmes[0];
    view.programmeName = prog ? localizeName(prog.name, locale) : view.programmeName;
    view.programmeSchool = prog ? prog.school || "" : view.programmeSchool;
    view.comingSoon = prog ? !!prog.coming_soon : false;

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

const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");
const { syncTabBar } = require("../../utils/tabbar");
const { localizeField } = require("../../utils/gefields");

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

function getAppHeaderHeight() {
  const info = wx.getWindowInfo();
  const statusBarHeight = info.statusBarHeight || 24;
  let navBarHeight = 56;

  if (wx.getMenuButtonBoundingClientRect) {
    const menu = wx.getMenuButtonBoundingClientRect();
    if (menu && menu.height && menu.top) {
      navBarHeight = Math.max(menu.height + (menu.top - statusBarHeight) * 2, 56);
    }
  }

  return statusBarHeight + navBarHeight;
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

// ── T07: entry_term → 当前学年 + 毕业年 ────────────────────────────────
// entry_term 形如 "2025-autumn" / "2025-spring"（T06 引导步骤③写入）。
// HKMU 两学期制下的学年归属：
//   秋入学 E：Y1 = {E 秋, E+1 春} → 4 年最后一学期 = E+4 春
//   春入学 E：Y1 = {E 春, E 秋}   → 4 年最后一学期 = E+3 秋
// 当前时间归属：8 月起进入新学年的秋学期；1-7 月仍属上一学年（春/暑期）。
// 纯函数：entry_term 缺失/格式错 → null（展示层自行降级隐藏年份信息）。
function computeStudyInfo(entryTerm, now) {
  const m = /^(\d{4})-(autumn|spring)$/.exec(String(entryTerm || "").trim());
  if (!m) return null;
  const entryYear = parseInt(m[1], 10);
  const springEntry = m[2] === "spring";
  const curYear = now.getFullYear();
  const curMonth = now.getMonth() + 1; // 1-12
  const studyYear = springEntry
    ? curYear - entryYear + 1                       // 春入学：学年随公历年切换
    : (curMonth >= 8 ? curYear - entryYear + 1 : curYear - entryYear); // 秋入学：8 月进新学年
  return {
    entryYear,
    entrySem: m[2],
    studyYear, // 1 起整数；0 = 秋季准新生（选了未来年份），>4 = 超期在读——展示层自行处理
    gradYear: springEntry ? entryYear + 3 : entryYear + 4,
    gradSem: springEntry ? "autumn" : "spring",
  };
}

const SEMESTER_ORDER = { autumn: 0, spring: 1, summer: 2 };

function semesterRank(name) {
  const key = String(name || "").toLowerCase();
  return SEMESTER_ORDER[key] != null ? SEMESTER_ORDER[key] : 99;
}

// 当前专业的课程按学年学期分组,每张卡带 status + 先修提示(仅提示,不阻塞标记)。
// T11: opts.year 传学年时只出该年两组学期(标签不带年份,年份在页内 seg 上)
// T28/T29: schedule(用户排课覆盖)优先于课程默认 year/semester;卡上带"改学期"
// 下拉(picker)与先修顺序校验(先修未完成且排在本人之后 → 琥珀提示,不阻塞)。
const MOVE_OPTIONS = [
  { year: 1, semester: "autumn" }, { year: 1, semester: "spring" },
  { year: 2, semester: "autumn" }, { year: 2, semester: "spring" },
  { year: 3, semester: "autumn" }, { year: 3, semester: "spring" },
  { year: 3, semester: "summer" },
  { year: 4, semester: "autumn" }, { year: 4, semester: "spring" },
];

function placementOf(course, schedule) {
  const ov = schedule && schedule[course.id];
  if (ov) return { year: ov.year, semester: ov.semester, planned: true };
  return { year: course.year != null ? course.year : 0, semester: course.semester || "other", planned: false };
}

function placementRank(p) {
  return p.year * 10 + semesterRank(p.semester);
}

function buildCoursesView(prog, idToCourse, progress, keyword, text, opts, schedule) {
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
  let filtered = kw
    ? all.filter((c) =>
        (c.code && String(c.code).toLowerCase().includes(kw)) ||
        (c.name && String(c.name).toLowerCase().includes(kw)))
    : all;
  const yearFilter = opts && opts.year;
  if (yearFilter) {
    filtered = filtered.filter((c) => placementOf(c, schedule).year === yearFilter);
  }
  const groups = {};
  filtered.forEach((c) => {
    const p = placementOf(c, schedule);
    const gk = p.year + "::" + p.semester;
    if (!groups[gk]) groups[gk] = { year: p.year, semester: p.semester, courses: [] };
    groups[gk].courses.push(c);
  });
  const semLabelMap = {
    autumn: text.semAutumn, spring: text.semSpring, summer: text.semSummer,
  };
  const semesters = Object.keys(groups).map((k) => groups[k]).sort((a, b) => {
    if (a.year !== b.year) return a.year - b.year;
    return semesterRank(a.semester) - semesterRank(b.semester);
  });
  const moveLabels = MOVE_OPTIONS.map((m) =>
    fillTemplate(text.yearLabel, { n: m.year }) + " · " + semLabelMap[m.semester]);
  semesters.forEach((g) => {
    g.label = yearFilter
      ? (semLabelMap[String(g.semester).toLowerCase()] || g.semester)
      : fillTemplate(text.yearLabel, { n: g.year }) + " · " +
        (semLabelMap[String(g.semester).toLowerCase()] || g.semester);
    g.courses = g.courses.map((c) => {
      const status = progress[c.id] || "not_started";
      const prereqIds = parsePrereqs(c.prerequisites);
      const met = prereqsMet(prereqIds, progress);
      let prereqLabel = "";
      if (prereqIds.length) {
        prereqLabel = met ? text.prereqMet : (text.prereqPrefix + prereqIds.join(", "));
      }
      // T28 先修顺序校验: 先修未完成且排在本人之后(含同期) → 提示,不阻塞
      const myPlacement = placementOf(c, schedule);
      const myRank = placementRank(myPlacement);
      const after = prereqIds.filter((id) => {
        if (progress[id] === "completed") return false;
        const pc = idToCourse[id];
        if (!pc) return false;
        return placementRank(placementOf(pc, schedule)) >= myRank;
      });
      const moveIndex = MOVE_OPTIONS.findIndex((m) =>
        m.year === myPlacement.year &&
        m.semester === String(myPlacement.semester).toLowerCase());
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
        orderWarn: after.length ? (text.prereqOrderPrefix + after.join(", ")) : "",
        planned: myPlacement.planned,
        placementLabel: moveIndex >= 0 ? moveLabels[moveIndex] : "",
        moveIndex: moveIndex >= 0 ? moveIndex : 0,
      };
    });
    g.crTotal = g.courses.reduce((n, c) => n + (c.credits || 0), 0);
  });
  return { semesters, moveLabels, empty: !filtered.length };
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
  _courses: null,           // /courses?page_size=200 → items
  _idToCourse: null,        // {course_id: course 对象}
  _progress: null,          // /courses/progress/me → {course_id: status}
  _schedule: null,          // T28: /courses/progress/schedule → {course_id: {year,semester}} 覆盖
  _activeYear: null,        // T11: 课表展示学年(1-4);首次算出 studyInfo 时按当前学年初始化
  _viewTab: "plan",         // T12: 二级视图 "plan"(合并规划屏) | "courses"(全课程列表);"通识"项开 GE 浮层
  _searchKeyword: "",
  _searchTimer: null,
  _courseCatalogue: null,        // /courses/catalogue/programmes (全校 ~107 专业 browse 目录)
  _catalogueCoursesCache: {},    // programme_code -> /courses/catalogue 课程分组（失败也写入 _failed:true 负缓存，防 _emit 死循环）
  _catalogueInflight: {},        // programme_code -> 进行中的 promise（去重并发请求）
  _catalogueCollapsed: {},       // bucket key -> false(已展开) 巨型专业折叠态
  _pickerList: [],               // _emit 算出的扁平 picker 项（onSelectProgramme 按 code 取）
  _programmeQuery: "",           // 专业搜索词（实时过滤）
  _programmeSearchTimer: null,   // 搜索防抖 timer
  _programmeSearchOpen: false,   // 全屏专业搜索浮层开关（点 hero 触发，默认收起）
  _programmePrompted: false,     // 首屏引导：本会话是否已判过自动弹引导（防反复弹）
  _onboardingActive: false,      // T04: 新生引导全屏开关（无 programme 时激活，替代弹浮层）
  _onboardingStep: 1,            // T04: 引导当前步 1/2/3
  _obStatusBar: 0,               // T04: 状态栏高度(px)，引导 nav 避让用
  _onboardingProgrammeCode: "",  // T05: 步骤①选的专业 code
  _onboardingProgrammeName: "",  // T05: 步骤①选的专业名
  _onboardingYears: [],          // T05: 步骤②候选年份
  _onboardingYear: 0,            // T05: 步骤②选中年份
  _onboardingSemester: "autumn", // T05: 步骤②选中学期
  _geList: null,                 // /courses/ge 结果（GEListOut）— GE 选择浮层数据源
  _geListCode: null,             // _geList 对应专业码（切专业后失效重拉）
  _gePickerOpen: false,          // GE 选择浮层开关（overview 通识分类行触发）
  _gePickerLoadError: null,      // GE 列表加载失败标记
  _geMode: "fields",             // T19: GE 浮层视图 "fields"(按领域) | "ranking"(评分榜)
  _geRanking: null,              // /courses/ge/ranking 结果（会话级，随 code 失效）
  _geRankingCode: null,
  _geGuide: null,                // T24: /courses/ge/guide 静态配置（会话级，select_url 等）

  // ── 生命周期 ──────────────────────────────────────────────────────────

  onShow() {
    syncTabBar(this, 3);
    this._setTabBarHidden(this._programmeSearchOpen || this._gePickerOpen || this._onboardingActive);
    this._locale = getLocale();
    if (!this._obStatusBar) {
      this._obStatusBar = (wx.getWindowInfo().statusBarHeight || 24);
    }
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
        this._maybePromptProgramme();
        if (user) {
          return this._loadStatus();
        }
        return null;
      })
      .catch(() => {
        this._user = null;
        this._emit();
        this._maybePromptProgramme();
      });
  },

  // 首屏引导：用户态确定后，若本会话未引导过且没选过任何专业（未登录 / 账户无 programme）
  // → 自动弹专业搜索浮层，把"选专业"主动推到用户面前，而非默认 DSAI 让人找入口。
  // _programmePrompted 保证本会话只判一次：用户手动关掉浮层后，切 tab 回来不会重弹。
  _maybePromptProgramme() {
    if (this._programmePrompted) return;
    this._programmePrompted = true;
    const pickerList = this._pickerList || [];
    if (pickerList.length && !this._selectedCode && !this._userProgrammeCode) {
      // T04: 进全屏 3 步引导(选专业/选学期/生成),替代原"突然弹选专业浮层"。
      // T05: 初始化步骤①②选择(年份=当前年,学期默认秋季)
      this._onboardingActive = true;
      this._onboardingStep = 1;
      this._onboardingProgrammeCode = "";
      this._onboardingProgrammeName = "";
      if (!this._onboardingYears.length) {
        const cy = new Date().getFullYear();
        this._onboardingYears = [cy - 3, cy - 2, cy - 1, cy, cy + 1];
      }
      this._onboardingYear = new Date().getFullYear();
      this._onboardingSemester = "autumn";
      this._setTabBarHidden(true);
      this._emit();
    }
  },

  _loadStatus() {
    const code = this._selectedCode || this._userProgrammeCode;
    if (!code) {
      return Promise.resolve();
    }
    const path = `/courses/graduation-status?programme_code=${encodeURIComponent(code)}`;
    // 并行预拉课程全量 + 用户进度 + 排课覆盖(会话级缓存),再拉仪表盘
    return Promise.all([this._loadCourses(), this._loadProgress(), this._loadSchedule()])
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
    // page_size 要覆盖全表：courses 表含 DSAI 41 + GE 73 = 114 门，
    // page_size=50 时 GE（GEN*）排在 DSAI（COMP/MATH/...）前 → DSAI 课程
    // 被挤出前 50 → "我的课程"拿不到课程显示空。给 200 余量。
    return request({ path: "/courses?page_size=200", auth: false })
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

  // T28 排课台: 用户学年覆盖(GET /progress/schedule)。失败静默 — 拉不到就
  // 全按课程默认安排渲染,下拉改学期时 PUT 仍可写。
  _loadSchedule() {
    if (this._schedule) return Promise.resolve();
    return request({ path: "/courses/progress/schedule", auth: true })
      .then((data) => {
        const map = {};
        (data || []).forEach((r) => {
          if (r && r.course_id && r.planned_year) {
            map[r.course_id] = { year: r.planned_year, semester: r.planned_semester || "autumn" };
          }
        });
        this._schedule = map;
      })
      .catch(() => {
        this._schedule = {};
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

  onOpenProgrammeSearch() {
    // 点 hero → 打开全屏专业搜索浮层，清空上次搜索词
    this._programmeSearchOpen = true;
    this._programmeQuery = "";
    this._setTabBarHidden(true);
    this._emit();
  },

  onCloseProgrammeSearch() {
    this._programmeSearchOpen = false;
    this._setTabBarHidden(false);
    this._emit();
  },

  // ── 屏④:新生引导(T04 骨架)── 步骤前进/后退;完成关闭进主屏 ──
  onObNext() {
    const text = getTexts("planner", this._locale);
    if (this._onboardingStep === 1) {
      if (!this._onboardingProgrammeCode) {
        wx.showToast({ title: text.obPickProgramme, icon: "none" });
        return;
      }
      this._onboardingStep = 2;
      this._emit();
    } else if (this._onboardingStep === 2) {
      if (!this._onboardingYear || !this._onboardingSemester) {
        wx.showToast({ title: text.obPickTerm, icon: "none" });
        return;
      }
      this._onboardingStep = 3;
      this._emit();
    } else {
      // 步骤③:生成课表 + 持久化 programme_code/entry_term + 进主屏
      this._obFinish();
    }
  },

  onObBack() {
    if (this._onboardingStep > 1) {
      this._onboardingStep -= 1;
      this._emit();
    }
  },

  // T05: 当前步"下一步"是否可走(步骤①需选专业,②需选学期)
  _obCanNext() {
    if (this._onboardingStep === 1) return !!this._onboardingProgrammeCode;
    if (this._onboardingStep === 2) return !!this._onboardingYear && !!this._onboardingSemester;
    return true;
  },

  onObPickProgramme(e) {
    const { code, name } = e.detail;
    this._onboardingProgrammeCode = code;
    this._onboardingProgrammeName = name;
    this._emit();
  },

  onObPickYear(e) {
    this._onboardingYear = e.currentTarget.dataset.year;
    this._emit();
  },

  onObPickSem(e) {
    this._onboardingSemester = e.currentTarget.dataset.sem;
    this._emit();
  },

  // T06: 入学学期展示串(年份 + 本地化学期)
  _obEntryTermDisplay() {
    const text = getTexts("planner", this._locale);
    const sem = this._onboardingSemester === "spring" ? text.obSpring : text.obAutumn;
    return (this._onboardingYear || "") + " " + (sem || "");
  },

  // T06: 步骤③完成 — 持久化 programme_code + entry_term,按专业生成课表,进主屏
  _obFinish() {
    const text = getTexts("planner", this._locale);
    const code = this._onboardingProgrammeCode;
    if (!code) return;
    const entryTerm = this._onboardingYear + "-" + this._onboardingSemester; // 2025-autumn
    const entry = (this._pickerList || []).find((p) => p.code === code);
    const hasFull = entry ? entry.has_full_planning : false;

    // 未登录：引导无关闭入口，硬走 PUT 必 401 会把人困在步骤③ — 对齐
    // onSelectProgramme 的未登录路径仅本会话生效（entry_term 不落库，
    // T07 studyInfo 维持 null，hero 不显毕业年）
    if (!this._user) {
      this._obApplyResult(code, hasFull, null);
      return;
    }

    wx.showLoading({ title: text.obGenerating, mask: true });
    request({
      method: "PUT",
      path: "/users/me",
      data: { programme_code: code, entry_term: entryTerm },
      auth: true,
    })
      .then((user) => this._obApplyResult(code, hasFull, user))
      .catch((err) => {
        wx.hideLoading();
        wx.showToast({ title: (err && err.message) || text.obGenFail, icon: "none" });
      });
  },

  // 引导完成落屏：选中专业生效 + 清旧 status 触发重拉(完整规划专业走
  // graduation-status; catalogue 专业 _emit 自动进目录视图)。user 非空时同步
  // 缓存（PUT 返回含 entry_term 的 UserOut，T07 当前学年/毕业年无需等下次
  // bootstrap 即可算出）
  _obApplyResult(code, hasFull, user) {
    if (user) this._user = user;
    this._selectedCode = code;
    this._userProgrammeCode = code;
    this._status = null;
    this._onboardingActive = false;
    this._setTabBarHidden(false);
    this._emit();
    wx.hideLoading();
    wx.showToast({ title: getTexts("planner", this._locale).obGenSuccess, icon: "success" });
    if (hasFull) this._loadStatus();
  },

  _setTabBarHidden(hidden) {
    const tabBar = typeof this.getTabBar === "function" ? this.getTabBar() : null;
    if (tabBar) {
      tabBar.setData({ externallyHidden: !!hidden });
    }
  },

  onSelectProgramme(e) {
    const code = e.currentTarget.dataset.code;
    if (!code) return;
    const entry = (this._pickerList || []).find((p) => p.code === code);
    this._selectedCode = code;
    this._programmeQuery = "";
    this._programmeSearchOpen = false; // 选完关浮层
    this._setTabBarHidden(false);
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
        // F8: zh-CN viewers get the OpenCC-simplified name when available;
        // everyone else (and English-only courses with name_zh_cn=null) falls
        // back to display_name (Traditional humanities / English as stored).
        name: (this._locale === "zh-Hans" && c.name_zh_cn) ? c.name_zh_cn : c.display_name,
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

  // ── GE 通识选择浮层（屏③）── 复用 programmeSearch 的全屏浮层范式 ──────

  // T09: 分类格点按 — 仅通识格（有 GE 池）进 GE 选择浮层，其余格无动作
  onCatCellTap(e) {
    if (e.currentTarget.dataset.ge) {
      this.onOpenGePicker();
    }
  },

  onOpenGePicker() {
    if (!this._user) { this.goLogin(); return; }
    this._gePickerOpen = true;
    this._setTabBarHidden(true);
    this._gePickerLoadError = null;
    this._emit();
    const code = this._selectedCode || this._userProgrammeCode;
    if (code) {
      this._loadGe(code);
      this._loadGeRanking(code); // T19: 评分榜数据并行预拉
    }
    this._loadGeGuide(); // T24: 教程配置（select_url 等）一并预拉
  },

  onCloseGePicker() {
    this._gePickerOpen = false;
    this._setTabBarHidden(false);
    this._emit();
  },

  _loadGe(code) {
    if (!code) return Promise.resolve(null);
    if (this._geList && this._geListCode === code) return Promise.resolve(this._geList);
    const path = `/courses/ge?programme_code=${encodeURIComponent(code)}`;
    return request({ path, auth: false })
      .then((data) => {
        this._geList = data;
        this._geListCode = code;
        this._gePickerLoadError = null;
        this._emit();
        return data;
      })
      .catch((err) => {
        this._gePickerLoadError = (err && err.message) || "fail";
        this._emit();
        return null;
      });
  },

  // T19: GE 评分榜数据（会话级缓存，失败静默 — ranking tab 显 loading/空态）
  _loadGeRanking(code) {
    if (!code) return Promise.resolve(null);
    if (this._geRanking && this._geRankingCode === code) return Promise.resolve(this._geRanking);
    const path = `/courses/ge/ranking?programme_code=${encodeURIComponent(code)}`;
    return request({ path, auth: false })
      .then((data) => {
        this._geRanking = data;
        this._geRankingCode = code;
        this._emit();
        return data;
      })
      .catch(() => null);
  },

  // T24: GE 教程配置（select_url 等，静态端点）— 会话级缓存，失败静默：
  // footer 的「去 MyHKMU 选课」复制按钮在未拉到前隐藏，教程入口不受影响。
  _loadGeGuide() {
    if (this._geGuide) return Promise.resolve(this._geGuide);
    return request({ path: "/courses/ge/guide", auth: false })
      .then((data) => {
        this._geGuide = data || null;
        this._emit();
        return data;
      })
      .catch(() => null);
  },

  // T19: GE 浮层 按领域/评分榜 视图切换
  onGeModeTap(e) {
    const mode = e.currentTarget.dataset.mode;
    if ((mode === "fields" || mode === "ranking") && mode !== this._geMode) {
      this._geMode = mode;
      this._emit();
    }
  },

  // T24: 教程入口 → ge-guide 页（传本专业 own_fields 供步骤③高亮；浮层保留，
  // 返回键回到浮层继续选课）。未拉到 GE 列表时传空数组，页内走通用文案。
  onOpenGeGuide() {
    const code = this._selectedCode || this._userProgrammeCode;
    const geData = (this._geList && this._geListCode === code) ? this._geList : null;
    const fields = (geData && Array.isArray(geData.own_fields)) ? geData.own_fields : [];
    wx.navigateTo({
      url: `/pages/ge-guide/ge-guide?fields=${encodeURIComponent(JSON.stringify(fields))}`,
    });
  },

  // T24: 去 MyHKMU 选课 — 复制链接（小程序开不了外链，复制是既定交互）
  onCopyMyhkmuLink() {
    const url = this._geGuide && this._geGuide.select_url;
    if (!url) return;
    const text = getTexts("planner", this._locale);
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: text.geLinkCopied, icon: "none" }),
      fail: () => wx.showToast({ title: text.geLinkCopyFail, icon: "none" }),
    });
  },

  // T19: 评分榜行点按 → 关浮层进课程详情（去三维评价/避坑投票）
  onOpenGeCourse(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    this._gePickerOpen = false;
    this._setTabBarHidden(false);
    this._emit();
    wx.navigateTo({ url: `/pages/course-detail/course-detail?id=${encodeURIComponent(id)}` });
  },

  // T28 排课台: 卡上"改学期"picker → 乐观写入 _schedule + PUT /progress/schedule。
  // 失败回滚 + toast;成功后若先修(未完成)排在新区之后,顺手 toast 提示(不阻塞)。
  onMoveCourse(e) {
    if (!this._user) { this.goLogin(); return; }
    const courseId = e.currentTarget.dataset.courseId;
    const idx = Number(e.detail.value);
    const target = MOVE_OPTIONS[idx];
    if (!courseId || !target) return;
    const prevSchedule = this._schedule || {};
    const prev = prevSchedule[courseId] || null;

    this._schedule = Object.assign({}, prevSchedule, {
      [courseId]: { year: target.year, semester: target.semester },
    });
    this._emit(); // 卡片即时挪组

    request({
      path: "/courses/progress/schedule",
      method: "PUT",
      data: {
        course_id: courseId,
        planned_year: target.year,
        planned_semester: target.semester,
      },
      auth: true,
    })
      .then(() => {
        const text = getTexts("planner", this._locale);
        // 先修顺序校验(toast 级,仅提示): 挪完后先修未完成且排在 >= 新位次
        const c = (this._idToCourse || {})[courseId];
        const prereqIds = c ? parsePrereqs(c.prerequisites) : [];
        const myRank = target.year * 10 + semesterRank(target.semester);
        const after = prereqIds.filter((id) => {
          if ((this._progress || {})[id] === "completed") return false;
          const pc = (this._idToCourse || {})[id];
          if (!pc) return false;
          const pp = placementOf(pc, this._schedule);
          return placementRank(pp) >= myRank;
        });
        if (after.length) {
          wx.showToast({ title: text.prereqOrderPrefix + after.join(", "), icon: "none", duration: 2500 });
        }
      })
      .catch(() => {
        // 回滚乐观更新
        const restored = Object.assign({}, this._schedule);
        if (prev) restored[courseId] = prev; else delete restored[courseId];
        this._schedule = restored;
        this._emit();
        wx.showToast({ title: getTexts("planner", this._locale).schedUpdateFail, icon: "none" });
      });
  },

  // picker 载体: 吞掉冒泡,避免触发卡片 openCourseDetail
  stopBubble() {},

  // 点 GE 课 → 乐观切换 completed（复用 PUT /courses/progress，与 course-detail 同语义）
  onToggleGeCourse(e) {
    if (!this._user) { this.goLogin(); return; }
    const ds = e.currentTarget.dataset;
    if (ds.blocked) {
      // 本专业领域的 GE 不可选（官方规则）— 提示并拦截
      wx.showToast({ title: getTexts("planner", this._locale).geFieldBlocked, icon: "none" });
      return;
    }
    const id = ds.id;
    if (!id) return;
    const prev = (this._progress || {})[id];
    const next = prev === "completed" ? "not_started" : "completed";
    this._progress = Object.assign({}, this._progress, { [id]: next });
    this._emit(); // 即时反馈：taken 计数 + 行高亮
    request({
      method: "PUT",
      path: "/courses/progress",
      data: { course_id: id, status: next },
      auth: true,
    })
      .then(() => {
        wx.showToast({ title: this.data.text.geMarkSuccess, icon: "success" });
        // 进度变了：回 overview 后重拉 graduation-status
        const app = getApp();
        if (app && app.globalData) app.globalData.coursesNeedRefresh = true;
      })
      .catch(() => {
        this._progress = Object.assign({}, this._progress, { [id]: prev }); // 回滚
        this._emit();
        wx.showToast({ title: getTexts("planner", this._locale).loadFail, icon: "none" });
      });
  },

  // GE 浮层 view：按 field 分组（GE_FIELD_ORDER 顺序）、taken/blocked、实时门数（field 去重）
  // T19: mode="ranking" 时出评分榜（分数降序）；T20: 空榜显"抢首评"空态。
  _buildGePicker(prog, entry, locale, text) {
    if (!this._gePickerOpen || !prog) return { open: false };
    const geCat = (prog.categories || {})["general-ed"] || {};
    const need = geCat.pick_n || 2;
    // 维度/避坑标签词条与 course-detail 同源,不重复造 key
    const cdText = getTexts("courseDetail", locale);
    const base = {
      open: true,
      title: text.gePickerTitle,
      ruleNote: text.geRuleNote,
      need,
      mode: this._geMode,
      tabFields: text.geTabFields,
      tabRanking: text.geTabRanking,
      // T24: 浮层底部常驻 footer — 教程入口 + 去 MyHKMU 选课（复制链接，
      // 静态配置未拉到前隐藏该按钮）
      guideEntry: text.geGuideEntry,
      selectLabel: text.geMyhkmuLink,
      selectUrl: (this._geGuide && this._geGuide.select_url) || "",
    };
    if (this._gePickerLoadError) {
      return Object.assign(base, { loadError: text.geLoadFail });
    }
    if (this._geMode === "ranking") {
      const rk = (this._geRanking && this._geRankingCode === entry.code) ? this._geRanking : null;
      if (!rk) {
        return Object.assign(base, { rankingLoading: true });
      }
      const rankRows = (rk.items || []).map((i) => ({
        id: i.id,
        code: i.code,
        name: locale === "en" ? i.name_en : i.name_zh,
        fieldLabel: localizeField(i.field, locale),
        score: Number(i.score).toFixed(1),
        dimsLine: cdText.dimTeaching + " " + i.teaching_avg + " · " +
          cdText.dimWorkload + " " + i.workload_avg + " · " +
          cdText.dimGain + " " + i.gain_avg,
        countLabel: fillTemplate(text.geRankCount, { n: i.review_count }),
        tags: (i.top_tags || []).map((t) => ({
          label: cdText["tag_" + t.tag] || t.tag,
          count: t.count,
        })),
      }));
      return Object.assign(base, {
        rankingLoading: false,
        rankingEmpty: rankRows.length ? "" : text.geRankEmpty,
        rankRows,
      });
    }
    const geData = (this._geList && this._geListCode === entry.code) ? this._geList : null;
    if (!geData) {
      return Object.assign(base, { loading: true });
    }
    const order = geData.field_order || [];
    const ownFields = new Set(geData.own_fields || []);
    const progress = this._progress || {};
    const byField = new Map();
    for (const c of geData.courses || []) {
      if (!byField.has(c.field)) byField.set(c.field, []);
      byField.get(c.field).push(c);
    }
    // 实时算已选门数（field 去重，对齐后端 _compute_graduation 规则）
    const usedFields = new Set();
    let taken = 0;
    for (const c of geData.courses || []) {
      if (progress[c.id] === "completed" && !c.blocked && !usedFields.has(c.field)) {
        usedFields.add(c.field);
        taken++;
      }
    }
    const fields = order
      .filter((f) => byField.has(f))
      .map((f) => {
        const fBlocked = ownFields.has(f);
        const fCourses = byField.get(f);
        return {
          name: localizeField(f, locale),
          blocked: fBlocked,
          headRight: fBlocked
            ? text.geFieldBlocked
            : fillTemplate(text.geFieldCount, { n: fCourses.length }),
          courses: fCourses.map((c) => ({
            id: c.id,
            code: c.code,
            name: locale === "en" ? c.name_en : c.name_zh,
            credits: 3, // GE 课程统一 3 学分（3cru 体系，ge_courses.py）
            taken: progress[c.id] === "completed",
            blocked: !!c.blocked,
          })),
        };
      });
    return Object.assign(base, {
      progress: fillTemplate(text.geProgress, { taken, need }),
      taken,
      fields,
    });
  },

  // T11: 年份 seg 点按 — 切课表展示学年(Y1-Y4)
  onYearTap(e) {
    const y = parseInt(e.currentTarget.dataset.year, 10);
    if (y >= 1 && y <= 4 && y !== this._activeYear) {
      this._activeYear = y;
      this._emit();
    }
  },

  // T12: 二级 seg(规划/课程/通识)— 通识项直接开 GE 浮层,不切内联视图
  onViewSegTap(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab === "ge") {
      this.onOpenGePicker();
      return;
    }
    if ((tab === "plan" || tab === "courses") && tab !== this._viewTab) {
      this._viewTab = tab;
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
    // 课程卡只在登录态仪表盘渲染(_user && status),点按即进详情页(页内内联标记)
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
            name,
            // 仅完整规划专业挂徽章；其余 106 个目录专业不再每行重复"课程目录"标签
            badge: p.has_full_planning ? text.catalogueTagFull : "",
          });
        }
      }
    } else if (planning) {
      pickerList = planning.programmes.map((p) => ({
        code: p.code,
        has_full_planning: !p.coming_soon,
        school: p.school || "",
        name: localizeName(p.name, locale),
        badge: p.coming_soon ? "" : text.catalogueTagFull,
      }));
    }
    this._pickerList = pickerList;

    // 选中优先级：手动选 > 已保存(须完整规划专业) > 默认
    const saved = this._userProgrammeCode;
    // 账户存的专业即采用（含 catalogue，会进目录视图）；不再只认完整规划专业，
    // 否则选了 catalogue 专业下次会被静默回退到 DSAI（"选了没记住"的根因）
    const savedValid = saved && pickerList.some((p) => p.code === saved);
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
          const hay = `${p.name} ${p.code} ${p.school || ""}`.toLowerCase();
          if (!hay.includes(pq)) continue;
        }
        if (!gmap.has(p.school)) gmap.set(p.school, []);
        gmap.get(p.school).push({
          code: p.code,
          name: p.name,
          badge: p.badge,
          selected: !!entry && p.code === entry.code,
        });
      }
      for (const [school, progs] of gmap) searchGroups.push({ school, programmes: progs });
      programmeSearchEmpty = !!pq && searchGroups.length === 0;
    }

    // T07: 入学学期 → 当前学年/毕业年（T08 hero 毕业年、T10 下学期建议、T11 年份 tab 数据源）。
    // entry_term 未存（老用户/未走引导）→ null，消费方 wx:if 降级隐藏。
    const studyInfo = computeStudyInfo(this._user && this._user.entry_term, new Date());

    const view = {
      locale,
      text,
      studyInfo,
      loading: this._loading,
      loggedIn: !!this._user,
      programmeOptions: pickerList,
      programmeIndex: idx,
      programmeQuery: this._programmeQuery,
      programmeTotal: pickerList.length,
      programmeSearchResults: searchGroups,
      programmeSearchEmpty,
      programmeSearchOpen: this._programmeSearchOpen,
      programmeOverlayTop: getAppHeaderHeight(),
      programmeCode: entry ? entry.code : "",
      programmeName: entry ? entry.name : "",
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
      viewSeg: this._viewTab,
      activeYear: 0,
      yearsView: [],
      searchKeyword: this._searchKeyword,
      coursesView: { semesters: [], empty: true },
      gePicker: { open: false },
      onboarding: {
        active: !!this._onboardingActive,
        step: this._onboardingStep || 1,
        statusBar: this._obStatusBar || 0,
        programmeCode: this._onboardingProgrammeCode || "",
        programmeName: this._onboardingProgrammeName || "",
        years: this._onboardingYears || [],
        year: this._onboardingYear || 0,
        semester: this._onboardingSemester || "",
        entryTermDisplay: this._obEntryTermDisplay(),
        canNext: this._obCanNext(),
      },
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
      // T08: hero 绿渐变卡统计 —— 距毕业学分 + 进度行（有 entry_term 才拼毕业年）
      const gradSemLabel = studyInfo
        ? (studyInfo.gradSem === "spring" ? text.heroSemSpring : text.heroSemAutumn)
        : "";
      const gradLabel = studyInfo
        ? (locale === "en"
            ? gradSemLabel + " " + studyInfo.gradYear
            : studyInfo.gradYear + " " + gradSemLabel)
        : "";
      view.heroStat = {
        remainText: fillTemplate(text.heroRemaining, {
          n: Math.max((status.total_credits || 0) - (status.earned_credits || 0), 0),
        }),
        progressLine: fillTemplate(text.heroProgress, {
          earned: status.earned_credits,
          total: status.total_credits,
        }) + (gradLabel ? " · " + gradLabel : ""),
      };
      view.categoriesView = (status.categories || []).map((c) => ({
        key: c.key,
        label: text.categories[c.key] || c.key,
        earned: c.earned_credits,
        required: c.min_credits,
        pct: categoryPercent(c.earned_credits, c.min_credits),
        done: (c.earned_credits || 0) >= (c.min_credits || 0) && (c.min_credits || 0) > 0,
        color: c.color,
        hasGePool: c.key === "general-ed",
      }));
      view.recommendations = (status.recommendations || []).map((r) => ({
        course_id: r.course_id,
        code: r.code,
        name: r.name,
        credits: r.credits,
        categoryKey: r.category_key,
        categoryLabel: text.categories[r.category_key] || r.category_key,
      }));
      // T10: 系统建议卡 —— "排进下学期"一句话（替代逐条 course-row 列表）。
      // 学期边界与 entry 类型对齐：秋入学按秋切换班级年，春入学按春切换。
      if (view.recommendations.length) {
        const recs = status.recommendations || [];
        const codes = recs.map((r) => r.code).filter(Boolean).join(" · ");
        const credits = recs.reduce((n, r) => n + (r.credits || 0), 0);
        const month = new Date().getMonth() + 1;
        let heading = text.adviceHeadingPlain;
        if (studyInfo && studyInfo.studyYear >= 1) {
          const nextSem = month >= 8 ? "spring" : "autumn";
          const nextY = studyInfo.studyYear + (studyInfo.entrySem === nextSem ? 1 : 0);
          heading = fillTemplate(text.adviceHeadingTerm, {
            y: nextY,
            sem: nextSem === "spring" ? text.heroSemSpring : text.heroSemAutumn,
          });
        }
        // 推荐全属同一分类时拼"XX还差 N cr"子句，多分类则省略
        let gapClause = "";
        const catKeys = Array.from(new Set(recs.map((r) => r.category_key)));
        if (catKeys.length === 1) {
          const cat = (status.categories || []).find((c) => c.key === catKeys[0]);
          if (cat && cat.min_credits > 0) {
            gapClause = fillTemplate(text.adviceGap, {
              cat: text.categories[catKeys[0]] || catKeys[0],
              gap: Math.max(cat.min_credits - (cat.earned_credits || 0), 0),
            });
          }
        }
        view.advice = {
          heading,
          text: gapClause + fillTemplate(text.adviceBody, { codes, credits }),
        };
      }
      // T11: 年份 seg(当前学年高亮)+ 该学年两学期课表,合并一屏滚动
      const curY = studyInfo ? Math.min(Math.max(studyInfo.studyYear, 1), 4) : 1;
      if (!this._activeYear) this._activeYear = curY;
      view.activeYear = this._activeYear;
      view.yearsView = [1, 2, 3, 4].map((n) => ({
        n,
        label: "Y" + n,
        current: n === curY,
        active: n === this._activeYear,
      }));
      if (this._idToCourse && this._progress) {
        // T12: 规划视图出当前学年两学期;课程视图出全量分组(带搜索)
        view.coursesView = this._viewTab === "courses"
          ? buildCoursesView(prog, this._idToCourse, this._progress, this._searchKeyword, text, null, this._schedule)
          : buildCoursesView(prog, this._idToCourse, this._progress, this._searchKeyword, text, { year: this._activeYear }, this._schedule);
      }
    } else if (prog.coming_soon) {
      view.heroCopy = text.comingSoonCopy;
    } else {
      // 未登录 / status 未到：用目录静态学分要求
      view.categoriesView = (prog.categories || []).map((c) => ({
        key: c.key,
        label: text.categories[c.key] || c.key,
        earned: null,
        required: c.min_credits,
        pct: 0,
        color: c.color,
        hasGePool: c.key === "general-ed",
      }));
      view.heroCopy = this._user ? "" : text.heroCopy;
    }

    // ── GE 选择浮层 view（仅完整规划专业 + 已打开）──
    view.gePicker = this._buildGePicker(prog, entry, locale, text);

    this.setData(view);
  },
});

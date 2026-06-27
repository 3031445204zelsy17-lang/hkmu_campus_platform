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

  // ── 生命周期 ──────────────────────────────────────────────────────────

  onShow() {
    syncTabBar(this, 2);
    this._locale = getLocale();
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
    syncTabBar(this, 2);
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

    return catDone
      .then(() => {
        this._emit();
        return auth.bootstrapSession();
      })
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
    return request({ path, auth: true })
      .then((status) => {
        this._status = status;
        this._emit();
      })
      .catch((error) => {
        wx.showToast({ title: error.message || getTexts("planner", this._locale).loadFail, icon: "none" });
        // 保留上次 status，不 blank 仪表盘
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
      }));
      view.heroCopy = this._user ? "" : text.heroCopy;
    }

    this.setData(view);
  },
});

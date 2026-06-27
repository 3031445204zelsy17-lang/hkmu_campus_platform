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
  data: {
    locale: getLocale(),
    text: getTexts("planner"),
    loading: true,
    loggedIn: false,
    // 专业目录（/courses/programmes）
    programmes: [],
    programmeOptions: [],
    programmeIndex: 0,
    programmeCode: "",
    programmeName: "",
    programmeSchool: "",
    comingSoon: false,
    // 毕业进度视图（/courses/graduation-status 计算后填充）
    percent: 0,
    creditsSummary: "",
    categoriesView: [],
    recommendations: [],
    heroCopy: "",
  },

  // 非响应式缓存
  _catalogue: null,
  _status: null,
  _userProgrammeCode: null,

  onShow() {
    this.applyLocale(getLocale());
    syncTabBar(this, 2);
    this.refresh();
  },

  onPullDownRefresh() {
    this.refresh().finally(() => wx.stopPullDownRefresh());
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
    this.refresh();
  },

  applyLocale(locale = getLocale()) {
    this.setData({ locale, text: getTexts("planner", locale) });
    if (this._catalogue) {
      this._buildOptions();
    }
    this._renderStatus();
    syncTabBar(this, 2);
  },

  // ── 数据加载 ──────────────────────────────────────────────────────────

  ensureCatalogue() {
    if (this._catalogue) {
      return Promise.resolve();
    }
    return request({ path: "/courses/programmes", auth: false })
      .then((data) => {
        this._catalogue = data;
        this.setData({ programmes: data.programmes || [] });
        this._buildOptions();
      })
      .catch((error) => {
        wx.showToast({ title: error.message || this.data.text.loadFail, icon: "none" });
      });
  },

  refresh() {
    this.setData({ loading: true });
    return this.ensureCatalogue()
      .then(() => auth.bootstrapSession())
      .then((user) => {
        this._userProgrammeCode = (user && user.programme_code) || null;
        this.setData({ loggedIn: !!user });
        // 登录后可能拿到用户已保存的专业，重建选项让其优先选中
        if (this._catalogue) {
          this._buildOptions();
        }
        if (user) {
          return this.loadStatus();
        }
        this._renderLoggedOut();
        return null;
      })
      .catch(() => {
        this.setData({ loggedIn: false });
        this._renderLoggedOut();
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  loadStatus() {
    const code = this.data.programmeCode;
    if (!code) {
      return Promise.resolve();
    }
    const path = `/courses/graduation-status?programme_code=${encodeURIComponent(code)}`;
    return request({ path, auth: true })
      .then((status) => {
        this._status = status;
        this._renderStatus();
      })
      .catch((error) => {
        wx.showToast({ title: error.message || this.data.text.loadFail, icon: "none" });
        this._renderLoggedOut();
      });
  },

  // ── 选项与渲染 ────────────────────────────────────────────────────────

  _buildOptions() {
    const data = this._catalogue;
    if (!data) {
      return;
    }
    const locale = this.data.locale;
    const text = this.data.text;
    const options = data.programmes.map((p) => ({
      code: p.code,
      label: localizeName(p.name, locale) + (p.coming_soon ? ` (${text.comingSoonTag})` : ""),
    }));

    // 选中优先级：当前已选 > 用户已保存 > 后端默认
    const wanted = this.data.programmeCode || this._userProgrammeCode || data.default_code;
    let idx = data.programmes.findIndex((p) => p.code === wanted);
    if (idx < 0) {
      idx = 0;
    }

    this.setData({ programmeOptions: options, programmeIndex: idx });
    this._renderProgramme();
  },

  _renderProgramme() {
    const prog = this.data.programmes[this.data.programmeIndex];
    if (!prog) {
      return;
    }
    this.setData({
      programmeCode: prog.code,
      programmeName: localizeName(prog.name, this.data.locale),
      programmeSchool: prog.school || "",
      comingSoon: !!prog.coming_soon,
    });
  },

  _renderStatus() {
    if (!this.data.loggedIn) {
      this._renderLoggedOut();
      return;
    }
    const status = this._status;
    const text = this.data.text;

    if (!status) {
      return;
    }
    if (status.coming_soon) {
      this.setData({
        percent: 0,
        creditsSummary: "",
        categoriesView: [],
        recommendations: [],
        heroCopy: text.comingSoonCopy,
      });
      return;
    }

    const categoriesView = (status.categories || []).map((c) => ({
      key: c.key,
      label: text.categories[c.key] || c.key,
      earned: c.earned_credits,
      required: c.min_credits,
      pct: categoryPercent(c.earned_credits, c.min_credits),
      color: c.color,
    }));
    const recommendations = (status.recommendations || []).map((r) => ({
      course_id: r.course_id,
      code: r.code,
      name: r.name,
      credits: r.credits,
      categoryLabel: text.categories[r.category_key] || r.category_key,
    }));

    this.setData({
      percent: Math.round(status.percent || 0),
      creditsSummary: fillTemplate(text.creditsSummary, {
        earned: status.earned_credits,
        total: status.total_credits,
      }),
      categoriesView,
      recommendations,
      heroCopy: "",
    });
  },

  _renderLoggedOut() {
    const prog = this.data.programmes[this.data.programmeIndex];
    const text = this.data.text;
    if (!prog) {
      this.setData({ categoriesView: [], recommendations: [], percent: 0, creditsSummary: "", heroCopy: "" });
      return;
    }
    // 未登录：用目录里的静态学分要求展示分类，不带已修进度
    const categoriesView = (prog.categories || []).map((c) => ({
      key: c.key,
      label: text.categories[c.key] || c.key,
      earned: null,
      required: c.min_credits,
      pct: 0,
      color: c.color,
    }));
    this.setData({
      percent: 0,
      creditsSummary: "",
      categoriesView,
      recommendations: [],
      heroCopy: "",
    });
  },

  // ── 交互 ──────────────────────────────────────────────────────────────

  onProgrammeChange(event) {
    const idx = Number(event.detail.value);
    this.setData({ programmeIndex: idx });
    this._renderProgramme();

    if (!this.data.loggedIn) {
      this._renderLoggedOut();
      return;
    }

    // 持久化到用户档案（best-effort），无论成功与否都按新专业重算进度
    const code = this.data.programmeCode;
    request({ method: "PUT", path: "/users/me", data: { programme_code: code }, auth: true })
      .catch(() => {})
      .finally(() => this.loadStatus());
  },

  goLogin() {
    wx.navigateTo({ url: "/pages/login/login" });
  },
});

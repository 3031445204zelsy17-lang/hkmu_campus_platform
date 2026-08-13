const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");
const { localizeField } = require("../../utils/gefields");

// T23: GE 选课官方教程页（4 步 · 1 屏看懂）。
// 文案：i18n geGuide scope 为主，后端 /courses/ge/guide 按 step key 对齐
// （key 一致才对得上，后端 title/detail 只作缺词条兜底）；链接（select_url /
// pdf_url / pdf_updated）只来自后端，换版只改后端不动前端。
// ownFields（本专业禁选领域，英文原名数组）由入口（planner GE 浮层，T24）
// 以 encodeURIComponent(JSON.stringify(fields)) 传入；无参进入时步骤③
// 退化为通用文案，不挡渲染。
function fillTemplate(tpl, vars) {
  if (!tpl) return "";
  return tpl.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? vars[k] : ""));
}

Page({
  data: {
    locale: getLocale(),
    text: getTexts("geGuide"),
    guide: null,        // { select_url, pdf_url, updatedLabel }
    stepsA: [],         // 步骤 1-3（本应用段）
    stepB: null,        // 步骤 4（MyHKMU 注册段）
    ownFieldLabels: [], // 本专业禁选领域（三语），空则步骤③显通用文案
    loadFail: false,
  },

  onLoad(options) {
    this._ownFields = [];
    if (options && options.fields) {
      try {
        const parsed = JSON.parse(decodeURIComponent(options.fields));
        if (Array.isArray(parsed)) this._ownFields = parsed.filter((f) => typeof f === "string");
      } catch (e) {
        // 参数坏了不致命 — 步骤③走通用文案
      }
    }
    this._loadGuide();
  },

  onShow() {
    this.applyLocale(getLocale());
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    this._locale = locale;
    this.setData({ locale, text: getTexts("geGuide", locale) });
    this._render();
  },

  _loadGuide() {
    this.setData({ loadFail: false });
    request({ path: "/courses/ge/guide", auth: false })
      .then((guide) => {
        this._guide = guide;
        this._render();
      })
      .catch(() => {
        // 静态配置端点失败属罕见 — 显重试面板
        this.setData({ loadFail: true });
      });
  },

  // 组视图：后端 steps 顺序固定 4 步（key 见 courses.py _GE_GUIDE），但按
  // key 而非下标取语义（pick_two/different_fields/avoid_own_field → A 段，
  // enrol → B 段），后端加步骤前端自动跟上。
  _render() {
    const text = this.data.text;
    const locale = this._locale || getLocale();
    const guide = this._guide;
    const ownFieldLabels = this._ownFields
      .map((f) => localizeField(f, locale))
      .filter(Boolean);

    const stepsA = [];
    let stepB = null;
    (guide && guide.tutorial_steps ? guide.tutorial_steps : []).forEach((s) => {
      const row = {
        key: s.key,
        title: text["step_" + s.key] || s.title,
        detail: text["step_" + s.key + "_detail"] || s.detail,
      };
      if (s.key === "enrol") {
        stepB = row;
      } else {
        stepsA.push(row);
      }
    });

    this.setData({
      guide: guide ? {
        select_url: guide.select_url,
        pdf_url: guide.pdf_url,
        updatedLabel: fillTemplate(text.updatedLabel, { date: guide.pdf_updated || "" }),
      } : null,
      stepsA,
      stepB,
      ownFieldLabels,
    });
  },

  onCopySelect() {
    this._copyLink(this._guide && this._guide.select_url);
  },

  onCopyPdf() {
    this._copyLink(this._guide && this._guide.pdf_url);
  },

  _copyLink(url) {
    if (!url) return;
    const text = this.data.text;
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: text.copied, icon: "none" }),
      fail: () => wx.showToast({ title: text.copyFail, icon: "none" }),
    });
  },

  onRetry() {
    this._loadGuide();
  },
});

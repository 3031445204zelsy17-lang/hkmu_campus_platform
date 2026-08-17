const { request } = require("../../utils/request");
const { getTexts } = require("../../utils/i18n");

// 小程序 locale → programmes.name 字典 key（复刻 planner.js）
const LOCALE_NAME_KEY = {
  "zh-Hans": "zh-CN",
  "zh-Hant": "zh-TW",
  en: "en",
};

function localizeName(name, locale) {
  if (!name) return "";
  const key = LOCALE_NAME_KEY[locale] || "en";
  return name[key] || name.en || "";
}

// 目录条目的三语名:中文优先官方目录名(name_zh_cn/tw),缺失回退英文。
// 规则专业(/programmes 载荷)只有英文名,中文展示全靠这里的目录字段。
function catalogueName(p, locale) {
  if (!p) return "";
  if (locale === "zh-Hans") return p.name_zh_cn || p.name_zh_tw || p.programme_name || "";
  if (locale === "zh-Hant") return p.name_zh_tw || p.name_zh_cn || p.programme_name || "";
  return p.programme_name || "";
}

// 浮层 top = 状态栏 + 胶囊导航高度（复刻 planner.getAppHeaderHeight），
// 让浮层从 header 下方铺开，header 仍可见可用（含语言切换）。
function appHeaderHeight() {
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

// 全屏专业搜索浮层组件。自包含：拉 programmes + catalogue、搜索过滤、按学院分组，
// 选中后 triggerEvent('select', {code,name,has_full_planning})。文案复用 planner i18n。
Component({
  properties: {
    open: { type: Boolean, value: false },
    selectedCode: { type: String, value: "" },
    locale: { type: String, value: "en" },
    mode: { type: String, value: "overlay" }, // overlay(全屏浮层) | inline(嵌入引导)
  },

  data: {
    query: "",
    groups: [],
    total: 0,
    empty: false,
    loading: false,
    top: 0,
    text: getTexts("planner", "en"),
  },

  observers: {
    open(v) {
      if (v) {
        // 打开：清搜索词 → 确保数据就绪 → 重算分组
        this.setData({ query: "" });
        this._ensureData().then(() => this._rebuild());
      }
    },
    selectedCode() {
      if (this._dataReady) this._rebuild();
    },
    locale(v) {
      this.setData({ text: getTexts("planner", v) });
      if (this._dataReady) {
        this._pickerList = this._buildPickerList();
        this._rebuild();
      }
    },
  },

  lifetimes: {
    attached() {
      // 非响应式缓存（不在 data，避免无谓 setData）
      this._planning = null;
      this._browse = null;
      this._pickerList = [];
      this._dataReady = false;
      this._queryTimer = null;
      this.setData({
        top: appHeaderHeight(),
        text: getTexts("planner", this.properties.locale),
      });
      // inline 模式(嵌入引导):无 open 触发,attached 即拉数据
      if (this.properties.mode === "inline") {
        this._ensureData().then(() => this._rebuild());
      }
    },
    detached() {
      if (this._queryTimer) clearTimeout(this._queryTimer);
    },
  },

  methods: {
    _ensureData() {
      if (this._dataReady) return Promise.resolve();
      this.setData({ loading: true });
      const planningP = this._planning
        ? Promise.resolve()
        : request({ path: "/courses/programmes", auth: false })
            .then((d) => { this._planning = d; })
            .catch(() => {});
      const browseP = this._browse
        ? Promise.resolve()
        : request({ path: "/courses/catalogue/programmes", auth: false })
            .then((d) => { this._browse = d; })
            .catch(() => {});
      return Promise.all([planningP, browseP]).then(() => {
        this._pickerList = this._buildPickerList();
        this._dataReady = true;
        this.setData({ loading: false, total: this._pickerList.length });
      });
    },

    // 扁平 picker 列表：browse 目录（全校 ~107）优先，否则回退 planning 完整规划专业。
    // 复刻 planner._emit 的 pickerList 构建（line 635-660）。
    _buildPickerList() {
      const locale = this.properties.locale;
      const text = getTexts("planner", locale);
      const planning = this._planning;
      const browse = this._browse;
      const list = [];
      if (browse && browse.schools) {
        for (const sch of browse.schools) {
          for (const p of sch.programmes) {
            const known = planning && planning.programmes.find((x) => x.code === p.programme_code);
            // 与 planner._emit 同步:DB flag(仅 DSAI)或 /programmes 载荷已收录的
            // 规则专业(55 门,DB 列未回填)都算完整规划,否则 GE 选课对规则专业不可达
            const knownFull = !!(known && !known.coming_soon);
            const name = (locale === "zh-Hans" || locale === "zh-Hant")
              ? (catalogueName(p, locale) || localizeName(known && known.name, locale))
              : (known ? localizeName(known.name, locale) : p.programme_name);
            list.push({
              code: p.programme_code,
              has_full_planning: !!p.has_full_planning || knownFull,
              school: p.school || (known && known.school) || "",
              name,
              badge: (p.has_full_planning || knownFull) ? text.catalogueTagFull
                : (p.discontinued ? text.catalogueTagDiscontinued : ""),
            });
          }
        }
      } else if (planning) {
        planning.programmes.forEach((p) => {
          list.push({
            code: p.code,
            has_full_planning: !p.coming_soon,
            school: p.school || "",
            name: localizeName(p.name, locale),
            badge: p.coming_soon ? "" : text.catalogueTagFull,
          });
        });
      }
      return list;
    },

    // 搜索过滤 + 按学院分组（复刻 planner._emit line 678-698）
    _rebuild() {
      const pq = (this.data.query || "").trim().toLowerCase();
      const sel = this.properties.selectedCode;
      const groups = [];
      let empty = false;
      if (this._pickerList.length) {
        const gmap = new Map();
        for (const p of this._pickerList) {
          if (pq) {
            const hay = `${p.name} ${p.code} ${p.school || ""}`.toLowerCase();
            if (!hay.includes(pq)) continue;
          }
          if (!gmap.has(p.school)) gmap.set(p.school, []);
          gmap.get(p.school).push({
            code: p.code,
            name: p.name,
            badge: p.badge,
            selected: !!sel && p.code === sel,
          });
        }
        for (const [school, progs] of gmap) groups.push({ school, programmes: progs });
        empty = !!pq && groups.length === 0;
      }
      this.setData({ groups, total: this._pickerList.length, empty });
    },

    onQueryInput(e) {
      const v = e.detail.value || "";
      if (this._queryTimer) clearTimeout(this._queryTimer);
      this._queryTimer = setTimeout(() => {
        this.setData({ query: v });
        this._rebuild();
      }, 200);
    },

    onSelect(e) {
      const code = e.currentTarget.dataset.code;
      if (!code) return;
      const entry = this._pickerList.find((p) => p.code === code);
      this.triggerEvent("select", {
        code,
        name: entry ? entry.name : "",
        has_full_planning: entry ? entry.has_full_planning : false,
      });
    },

    onClose() {
      this.triggerEvent("close");
    },
  },
});

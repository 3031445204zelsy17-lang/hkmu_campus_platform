const {
  getLocale,
  isSupportedLocale,
  LANGUAGE_OPTIONS,
  setLocale,
} = require("../../utils/i18n");

// 量测一次，缓存在模块级。若放在 attached() 里 setData，首帧会先按默认值
// （statusBarHeight 24 / rightReserve 0）排版，下一帧才跳到真实值 —— 标题栏、
// 语言开关和下方 headerHeight 占位块同时位移，就是进页面/切 tab 时看到的那一下闪。
// 模块加载发生在 App.onLaunch 之后，此处调 wx 同步接口是安全的；顺带让五个 tab
// 页共用同一份结果，不必各自重量一遍。
function measureHeaderMetrics() {
  // wx.getSystemInfoSync 已废弃 → wx.getWindowInfo（本项目只用到 statusBarHeight / windowWidth，字段名相同）
  const info = wx.getWindowInfo();
  const statusBarHeight = info.statusBarHeight || 24;
  let navBarHeight = 56;
  let rightReserve = 96;

  if (wx.getMenuButtonBoundingClientRect) {
    const menu = wx.getMenuButtonBoundingClientRect();
    if (menu && menu.height && menu.top) {
      navBarHeight = Math.max(menu.height + (menu.top - statusBarHeight) * 2, 56);
    }
    if (menu && menu.left && info.windowWidth) {
      rightReserve = Math.max(info.windowWidth - menu.left + 12, 96);
    }
  }

  return {
    headerHeight: statusBarHeight + navBarHeight,
    languageRight: rightReserve + 8,
    navBarHeight,
    rightReserve,
    statusBarHeight,
    titleRight: rightReserve + 112,
  };
}

const HEADER_METRICS = measureHeaderMetrics();

Component({
  properties: {
    title: {
      type: String,
      value: "HKMU Campus",
    },
    // Show a back button on the left. Off by default so the five tab pages
    // are unaffected; sub-pages (lostfound/compose/login) opt in via show-back.
    showBack: {
      type: Boolean,
      value: false,
    },
  },

  data: Object.assign({
    languageOptions: LANGUAGE_OPTIONS,
    locale: getLocale(),
  }, HEADER_METRICS),

  lifetimes: {
    attached() {
      // 尺寸已在 data 里就位，这里只补语言：locale 可能在模块加载后被切过。
      const locale = getLocale();
      if (locale !== this.data.locale) {
        this.setData({ locale });
      }
    },
  },

  methods: {
    onBack() {
      // Sub-pages are reached via navigateTo, so a page stack usually exists.
      // Fall back to the home tab when there's nothing to pop (e.g. deep link
      // or simulator reLaunch), otherwise navigateBack would silently no-op.
      const pages = getCurrentPages();
      if (pages.length > 1) {
        wx.navigateBack({ delta: 1 });
      } else {
        wx.switchTab({ url: "/pages/home/home" });
      }
    },

    selectLanguage(event) {
      const requestedLocale = event.currentTarget.dataset.locale;
      if (!isSupportedLocale(requestedLocale) || requestedLocale === this.data.locale) {
        return;
      }

      const locale = setLocale(requestedLocale);
      this.setData({ locale });
      this.triggerEvent("languagechange", { locale });

      const pages = getCurrentPages();
      const currentPage = pages.length ? pages[pages.length - 1] : null;
      if (currentPage && typeof currentPage.applyLocale === "function") {
        currentPage.applyLocale(locale);
      }

      if (currentPage && typeof currentPage.getTabBar === "function") {
        const tabBar = currentPage.getTabBar();
        if (tabBar && typeof tabBar.applyLocale === "function") {
          tabBar.applyLocale(locale);
        }
      }
    },
  },
});

const {
  getLocale,
  isSupportedLocale,
  LANGUAGE_OPTIONS,
  setLocale,
} = require("../../utils/i18n");

Component({
  properties: {
    title: {
      type: String,
      value: "HKMU Campus",
    },
  },

  data: {
    headerHeight: 104,
    languageOptions: LANGUAGE_OPTIONS,
    languageRight: 108,
    locale: getLocale(),
    navBarHeight: 56,
    rightReserve: 0,
    statusBarHeight: 24,
    titleRight: 224,
  },

  lifetimes: {
    attached() {
      const info = wx.getSystemInfoSync();
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

      this.setData({
        headerHeight: statusBarHeight + navBarHeight,
        languageRight: rightReserve + 8,
        locale: getLocale(),
        navBarHeight,
        rightReserve,
        statusBarHeight,
        titleRight: rightReserve + 112,
      });
    },
  },

  methods: {
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

const { getLocale, getTexts } = require("../../utils/i18n");

// B5 隐私声明:纯展示页,三语 scope = privacy。入口文案 openAction 由
// login/profile 页引用(getTexts("privacy").openAction),这里只负责声明本体。
Page({
  data: {
    locale: getLocale(),
    text: getTexts("privacy"),
  },

  onLoad() {
    this.applyLocale(getLocale());
  },

  onShow() {
    this.applyLocale(getLocale());
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    this.setData({
      locale,
      text: getTexts("privacy", locale),
    });
  },
});

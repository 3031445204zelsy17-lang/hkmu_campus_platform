const { getLocale, getTexts } = require("../../utils/i18n");

// 用户服务协议:纯展示页,三语 scope = terms。入口文案 openAction 由
// login 页引用(getTexts("terms").openAction),这里只负责协议本体。
// ⚠️ i18n 里的协议正文是 DRAFT 草案,上线前须经法务复核。
Page({
  data: {
    locale: getLocale(),
    text: getTexts("terms"),
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
      text: getTexts("terms", locale),
    });
  },
});

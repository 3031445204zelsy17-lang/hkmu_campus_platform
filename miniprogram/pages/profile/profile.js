const auth = require("../../utils/auth");
const { formatDate } = require("../../utils/format");
const { getLocale, getTexts } = require("../../utils/i18n");

function identityLabel(identity, text = getTexts("profile")) {
  if (!identity || identity === "student") {
    return text.student;
  }

  return identity;
}

Page({
  data: {
    identityLabel: "",
    joinedAtDisplay: getTexts("profile").today,
    joinedAtLabel: "",
    loading: false,
    locale: getLocale(),
    text: getTexts("profile"),
    user: null,
  },

  onShow() {
    this.applyLocale(getLocale());
    this.refreshProfile();
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("profile", locale);
    const joinedAtDisplay = this.data.user && this.data.user.created_at
      ? formatDate(this.data.user.created_at)
      : text.today;

    this.setData({
      identityLabel: identityLabel(this.data.user && this.data.user.identity, text),
      joinedAtDisplay,
      locale,
      text,
    });
  },

  onPullDownRefresh() {
    this.refreshProfile().finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  refreshProfile() {
    this.setData({ loading: true });

    return auth
      .bootstrapSession()
      .then((user) => {
        this.setData({
          identityLabel: identityLabel(user && user.identity, this.data.text),
          joinedAtDisplay: user && user.created_at ? formatDate(user.created_at) : this.data.text.today,
          joinedAtLabel: user && user.created_at ? formatDate(user.created_at) : "",
          user: user || null,
        });
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || this.data.text.loadFail,
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  goToLogin() {
    wx.navigateTo({
      url: "/pages/login/login",
    });
  },

  goCompose() {
    wx.navigateTo({
      url: "/pages/compose/compose",
    });
  },

  logout() {
    auth.logout();
    this.setData({
      identityLabel: "",
      joinedAtDisplay: this.data.text.today,
      joinedAtLabel: "",
      user: null,
    });
    wx.showToast({
      title: this.data.text.loggedOut,
      icon: "success",
    });
  },
});

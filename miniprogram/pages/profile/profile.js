const auth = require("../../utils/auth");
const { formatDate } = require("../../utils/format");

Page({
  data: {
    identityLabel: "",
    joinedAtDisplay: "今天",
    joinedAtLabel: "",
    loading: false,
    user: null,
  },

  onShow() {
    this.refreshProfile();
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
          identityLabel: user && user.identity ? user.identity : "student",
          joinedAtDisplay: user && user.created_at ? formatDate(user.created_at) : "今天",
          joinedAtLabel: user && user.created_at ? formatDate(user.created_at) : "",
          user: user || null,
        });
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || "加载失败",
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
      joinedAtDisplay: "今天",
      joinedAtLabel: "",
      user: null,
    });
    wx.showToast({
      title: "已退出",
      icon: "success",
    });
  },
});

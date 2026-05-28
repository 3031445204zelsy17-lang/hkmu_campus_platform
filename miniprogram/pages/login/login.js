const auth = require("../../utils/auth");

function getModeMeta(mode) {
  if (mode === "email") {
    return {
      accountPlaceholder: "your@email.com",
      emailModeClass: "segment-item active",
      modeLabel: "邮箱",
      usernameModeClass: "segment-item",
    };
  }

  return {
    accountPlaceholder: "testuser",
    emailModeClass: "segment-item",
    modeLabel: "用户名",
    usernameModeClass: "segment-item active",
  };
}

Page({
  data: {
    account: "",
    accountPlaceholder: "testuser",
    emailModeClass: "segment-item",
    loading: false,
    mode: "username",
    modeLabel: "用户名",
    password: "",
    usernameModeClass: "segment-item active",
  },

  onLoad() {
    this.setData(getModeMeta(this.data.mode));
  },

  switchMode(event) {
    const mode = event.currentTarget.dataset.mode;
    this.setData(
      Object.assign(
        {
          account: "",
          mode,
          password: "",
        },
        getModeMeta(mode),
      ),
    );
  },

  updateField(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({
      [field]: event.detail.value,
    });
  },

  finishLogin() {
    wx.showToast({
      title: "登录成功",
      icon: "success",
    });

    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.switchTab({
      url: "/pages/home/home",
    });
  },

  submitAccountLogin() {
    if (this.data.loading) {
      return;
    }

    const account = this.data.account.trim();
    const password = this.data.password;

    if (!account || !password) {
      wx.showToast({
        title: "请输入账号和密码",
        icon: "none",
      });
      return;
    }

    this.setData({ loading: true });

    auth
      .loginWithAccount({
        account,
        mode: this.data.mode,
        password,
      })
      .then(() => this.finishLogin())
      .catch((error) => {
        wx.showToast({
          title: error.message || "登录失败",
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  submitWechatLogin() {
    if (this.data.loading) {
      return;
    }

    this.setData({ loading: true });

    auth
      .loginWithWechat()
      .then(() => this.finishLogin())
      .catch((error) => {
        wx.showToast({
          title: error.message || "微信登录失败",
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },
});

const auth = require("../../utils/auth");
const { getLocale, getTexts } = require("../../utils/i18n");

function getModeMeta(mode, text = getTexts("login")) {
  if (mode === "email") {
    return {
      accountPlaceholder: text.emailPlaceholder,
      emailModeClass: "segment-item active",
      modeLabel: text.emailMode,
      usernameModeClass: "segment-item",
    };
  }

  return {
    accountPlaceholder: text.usernamePlaceholder,
    emailModeClass: "segment-item",
    modeLabel: text.usernameMode,
    usernameModeClass: "segment-item active",
  };
}

Page({
  data: {
    account: "",
    accountPlaceholder: "testuser",
    emailModeClass: "segment-item",
    loading: false,
    locale: getLocale(),
    mode: "username",
    modeLabel: getTexts("login").usernameMode,
    password: "",
    text: getTexts("login"),
    usernameModeClass: "segment-item active",
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
    const text = getTexts("login", locale);
    this.setData(Object.assign({
      locale,
      text,
    }, getModeMeta(this.data.mode, text)));
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
        getModeMeta(mode, this.data.text),
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
      title: this.data.text.loginSuccess,
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
        title: this.data.text.missingCredentials,
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
          title: error.message || this.data.text.loginFail,
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
          title: error.message || this.data.text.wechatLoginFail,
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },
});

const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

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

// Mirrors backend EmailRegister.password_strength: >=8 chars + upper + lower + digit.
function isStrongPassword(password) {
  return (
    typeof password === "string" &&
    password.length >= 8 &&
    password.length <= 128 &&
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /\d/.test(password)
  );
}

Page({
  data: {
    account: "",
    accountPlaceholder: "testuser",
    emailModeClass: "segment-item",
    isRegister: false,
    loading: false,
    locale: getLocale(),
    mode: "username",
    modeLabel: getTexts("login").usernameMode,
    nickname: "",
    password: "",
    studentId: "",
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

  // Flip between login and email-register. Keep `account` (email) so it carries
  // from the register form into the email-login form after a successful signup.
  toggleRegister() {
    const isRegister = !this.data.isRegister;
    this.setData(Object.assign({
      isRegister,
      mode: "email",
      nickname: "",
      password: "",
      studentId: "",
    }, getModeMeta("email", this.data.text)));
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

  // Email registration. Backend creates the user (email_verified=false) and
  // emails a verification link, but does NOT issue a token — email/login blocks
  // unverified accounts. So we return the user to the email-login form to
  // verify-then-sign-in, rather than auto-logging-in.
  submitRegister() {
    if (this.data.loading) {
      return;
    }

    const text = this.data.text;
    const email = this.data.account.trim();
    const password = this.data.password;
    const nickname = this.data.nickname.trim();
    const studentId = this.data.studentId.trim();

    if (!EMAIL_RE.test(email)) {
      wx.showToast({ title: text.invalidEmail, icon: "none" });
      return;
    }
    if (!isStrongPassword(password)) {
      wx.showToast({ title: text.passwordRule, icon: "none" });
      return;
    }
    if (!nickname) {
      wx.showToast({ title: text.missingNickname, icon: "none" });
      return;
    }

    this.setData({ loading: true });

    const data = { email, password, nickname };
    if (studentId) {
      data.student_id = studentId;
    }

    request({
      method: "POST",
      path: "/auth/email/register",
      data,
    })
      .then(() => {
        wx.showToast({ title: text.registerSuccess, icon: "none", duration: 3000 });
        this.setData(Object.assign({
          isRegister: false,
          mode: "email",
          nickname: "",
          password: "",
          studentId: "",
        }, getModeMeta("email", this.data.text)));
      })
      .catch((error) => {
        const message = error && error.message ? error.message : "";
        const title = /already registered/i.test(message)
          ? text.emailExists
          : message || text.registerFail;
        wx.showToast({ title, icon: "none" });
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

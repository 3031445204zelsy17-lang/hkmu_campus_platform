const { API_ORIGIN } = require("./config");
const requestStore = require("./request");
const { getInitial } = require("./format");

function setGlobalUser(user) {
  const app = getApp();
  if (app && app.globalData) {
    app.globalData.user = user || null;
  }
}

function decorateUser(user) {
  if (!user) {
    return null;
  }

  const displayName = user.nickname || user.username || "HKMU";
  const avatarUrl =
    user.avatar_url && user.avatar_url.startsWith("/")
      ? `${API_ORIGIN}${user.avatar_url}`
      : user.avatar_url || "";

  return Object.assign({}, user, {
    avatar_url: avatarUrl,
    bioLabel: user.bio || "这个账号还没有填写个人简介。",
    displayName,
    emailLabel: user.email || "未填写",
    initial: getInitial(displayName),
    providerLabel: user.oauth_provider || "账号密码",
    studentIdLabel: user.student_id || "未填写",
  });
}

function syncCurrentUser() {
  return requestStore
    .request({
      path: "/users/me",
      auth: true,
    })
    .then((user) => {
      const decoratedUser = decorateUser(user);
      requestStore.setSession({ user: decoratedUser });
      setGlobalUser(decoratedUser);
      return decoratedUser;
    });
}

function bootstrapSession() {
  const session = requestStore.getSession();

  if (!session.accessToken) {
    setGlobalUser(null);
    return Promise.resolve(null);
  }

  if (session.user) {
    setGlobalUser(session.user);
  }

  return syncCurrentUser().catch(() => {
    const nextSession = requestStore.getSession();
    const fallbackUser = nextSession.accessToken ? session.user || nextSession.user || null : null;
    setGlobalUser(fallbackUser);
    return fallbackUser;
  });
}

function loginWithWechat() {
  return new Promise((resolve, reject) => {
    wx.login({
      timeout: 10000,
      success(res) {
        if (!res.code) {
          reject(new Error("WeChat did not return a login code"));
          return;
        }

        requestStore
          .request({
            method: "POST",
            path: "/auth/wechat/miniprogram",
            data: { code: res.code },
          })
          .then((tokens) => {
            requestStore.setSession({
              accessToken: tokens.access_token,
              refreshToken: tokens.refresh_token || "",
            });
            return syncCurrentUser();
          })
          .then(resolve)
          .catch(reject);
      },
      fail(error) {
        reject(new Error(error.errMsg || "WeChat login failed"));
      },
    });
  });
}

function loginWithAccount({ mode, account, password }) {
  const useEmail = mode === "email";

  return requestStore
    .request({
      method: "POST",
      path: useEmail ? "/auth/email/login" : "/auth/login",
      data: useEmail
        ? { email: account, password }
        : { username: account, password },
    })
    .then((tokens) => {
      requestStore.setSession({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token || "",
      });
      return syncCurrentUser();
    });
}

function logout() {
  requestStore.clearSession();
  setGlobalUser(null);
}

function getStoredUser() {
  return requestStore.getSession().user || null;
}

module.exports = {
  bootstrapSession,
  getStoredUser,
  loginWithAccount,
  loginWithWechat,
  logout,
  syncCurrentUser,
};

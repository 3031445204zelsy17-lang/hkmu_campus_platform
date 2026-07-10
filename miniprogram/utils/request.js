const { API_BASE, CLIENT_PLATFORM, PREVIEW_MODE, REQUEST_TIMEOUT } = require("./config");
const { mockRawRequest } = require("./mock-api");
const log = require("./log");

const STORAGE_KEYS = {
  accessToken: "hkmu_access_token",
  refreshToken: "hkmu_refresh_token",
  user: "hkmu_current_user",
};

function getSession() {
  return {
    accessToken: wx.getStorageSync(STORAGE_KEYS.accessToken) || "",
    refreshToken: wx.getStorageSync(STORAGE_KEYS.refreshToken) || "",
    user: wx.getStorageSync(STORAGE_KEYS.user) || null,
  };
}

function setSession({ accessToken, refreshToken, user }) {
  if (accessToken !== undefined) {
    if (accessToken) {
      wx.setStorageSync(STORAGE_KEYS.accessToken, accessToken);
    } else {
      wx.removeStorageSync(STORAGE_KEYS.accessToken);
    }
  }

  if (refreshToken !== undefined) {
    if (refreshToken) {
      wx.setStorageSync(STORAGE_KEYS.refreshToken, refreshToken);
    } else {
      wx.removeStorageSync(STORAGE_KEYS.refreshToken);
    }
  }

  if (user !== undefined) {
    if (user) {
      wx.setStorageSync(STORAGE_KEYS.user, user);
    } else {
      wx.removeStorageSync(STORAGE_KEYS.user);
    }
  }
}

function clearSession() {
  setSession({
    accessToken: "",
    refreshToken: "",
    user: null,
  });
}

function rawRequest({ method = "GET", path, data = null, header = {} }) {
  if (PREVIEW_MODE) {
    return mockRawRequest({ method, path, data, header });
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE}${path}`,
      method,
      data,
      timeout: REQUEST_TIMEOUT,
      header: Object.assign(
        {
          "Content-Type": "application/json",
          "X-Client-Platform": CLIENT_PLATFORM,
        },
        header,
      ),
      success: resolve,
      fail: (error) => {
        reject(new Error(error.errMsg || "Network request failed"));
      },
    });
  });
}

let _refreshPromise = null;

// 并发 401 复用同一个 refresh 请求(后端 refresh token 是 rotation 模式 —— 刷新即删旧
// token)。若多个请求各自 POST /auth/refresh(带同一 refresh_token),第二个会因旧 token
// 已被第一个 rotate 删除而失败 → clearSession 把全局 session 搞坏。典型触发:小程序启动
// 时 app.onLaunch + home.onShow 并发 bootstrapSession → 两个 /users/me 同时 401。这里用
// 单例 promise 保证同一时刻只真正刷新一次,其他并发 401 等同一个结果。
function refreshSession() {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = _doRefresh().finally(() => {
    _refreshPromise = null;
  });
  return _refreshPromise;
}

function _doRefresh() {
  const session = getSession();

  if (!session.refreshToken) {
    return Promise.reject(new Error("Missing refresh token"));
  }

  return rawRequest({
    method: "POST",
    path: "/auth/refresh",
    data: {
      refresh_token: session.refreshToken,
    },
  }).then((response) => {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      clearSession();
      throw new Error(response.data && response.data.detail ? response.data.detail : "Session expired");
    }

    setSession({
      accessToken: response.data.access_token,
      refreshToken: response.data.refresh_token || session.refreshToken,
    });

    return response.data;
  });
}

function request({ method = "GET", path, data = null, auth = false, retry = true }) {
  const session = getSession();
  const header = {};

  if (auth && session.accessToken) {
    header.Authorization = `Bearer ${session.accessToken}`;
  }

  return rawRequest({ method, path, data, header }).then((response) => {
    if (response.statusCode === 401 && auth && retry && session.refreshToken) {
      return refreshSession().then(() =>
        request({ method, path, data, auth, retry: false }),
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      if (response.statusCode === 401) {
        clearSession();
      }

      const errMsg = response.data && (response.data.detail || response.data.message)
        ? response.data.detail || response.data.message
        : `Request failed (${response.statusCode})`;
      // 内测监控 B3:失败请求上报后台实时日志(带 path/method/status,便于定位)
      log.error("api", errMsg, { path, method, status: response.statusCode });
      throw new Error(errMsg);
    }

    return response.data;
  });
}

module.exports = {
  clearSession,
  getSession,
  request,
  setSession,
};

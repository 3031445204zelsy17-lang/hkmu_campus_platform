const { API_BASE, CLIENT_PLATFORM, REQUEST_TIMEOUT } = require("./config");

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

function refreshSession() {
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

      throw new Error(
        response.data && (response.data.detail || response.data.message)
          ? response.data.detail || response.data.message
          : `Request failed (${response.statusCode})`,
      );
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

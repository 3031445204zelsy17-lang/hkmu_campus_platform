const API_BASE = "https://hkmu-campus-sea.azurewebsites.net/api/v1";
const CLIENT_PLATFORM = "wechat-miniprogram";
const REQUEST_TIMEOUT = 10000;
const API_ORIGIN = API_BASE.replace(/\/api\/v1\/?$/, "");
const PREVIEW_MODE = false;

module.exports = {
  API_BASE,
  API_ORIGIN,
  CLIENT_PLATFORM,
  PREVIEW_MODE,
  REQUEST_TIMEOUT,
};

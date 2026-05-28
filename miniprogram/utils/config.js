const API_BASE = "http://192.168.20.147:3002/api/v1";
const CLIENT_PLATFORM = "wechat-miniprogram";
const REQUEST_TIMEOUT = 10000;
const API_ORIGIN = API_BASE.replace(/\/api\/v1\/?$/, "");

module.exports = {
  API_BASE,
  API_ORIGIN,
  CLIENT_PLATFORM,
  REQUEST_TIMEOUT,
};

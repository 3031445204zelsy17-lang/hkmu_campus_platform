const API_BASE = "https://hkmu-campus-sea.azurewebsites.net/api/v1";
const CLIENT_PLATFORM = "wechat-miniprogram";
const REQUEST_TIMEOUT = 10000;
const API_ORIGIN = API_BASE.replace(/\/api\/v1\/?$/, "");
const PREVIEW_MODE = false;

// 分页大小（值沿用历史；集中常量化便于将来统一调整）
const PAGE_SIZE = {
  feed: 2, // home / community 信息流
  list: 12, // news / lostfound 列表
  comments: 50, // 帖子评论
};

module.exports = {
  API_BASE,
  API_ORIGIN,
  CLIENT_PLATFORM,
  PAGE_SIZE,
  PREVIEW_MODE,
  REQUEST_TIMEOUT,
};

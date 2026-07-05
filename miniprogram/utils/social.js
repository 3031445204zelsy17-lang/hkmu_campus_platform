// 社交冷启动传输层(Phase 5):邀请码 / 同学推荐 / 好友关系。
// 纯 REST,复用 utils/request;刻意不依赖 auth.js,避免环(与 messages.js 一致)。
// 登录态由调用方保证:所有端点 auth:true,request 自动加 Bearer token 并处理 401 刷新。
//
// 对应后端(C.3):
//   GET  /users/me/invite-code  → { invite_code, share_path }
//   GET  /users/suggest?limit=  → SuggestOut[](带 reason i18n 信号 same_programme | hkmu_peer)
//   GET  /users/me/friends      → FriendshipOut[]
//   POST /users/me/friends      → { friend, created }(自邀后端 no-op,双向 ON CONFLICT 幂等)

const { request } = require("./request");

// GET /users/me/invite-code — 懒生成我的邀请码 + 分享路径
function getInviteCode() {
  return request({ method: "GET", path: "/users/me/invite-code", auth: true });
}

// 构建小程序分享 path(带邀请码),供 onShareAppMessage 使用
function buildSharePath(inviteCode) {
  return `/pages/home/home?inv=${encodeURIComponent(inviteCode)}`;
}

// POST /users/me/friends — 兑换邀请码,自动双向好友
// 返回 { friend: UserOut, created: bool }(自邀 created=false,重复 created=false)
function consumeInvite(inviteCode) {
  return request({
    method: "POST",
    path: "/users/me/friends",
    data: { invite_code: inviteCode },
    auth: true,
  });
}

// GET /users/me/friends — 我的 accepted 好友(FriendshipOut[])
function fetchFriends() {
  return request({ method: "GET", path: "/users/me/friends", auth: true });
}

// GET /users/suggest — 推荐同学(SuggestOut[],带 reason 信号)
function fetchSuggest(limit) {
  const query = limit ? `?limit=${limit}` : "";
  return request({ method: "GET", path: `/users/suggest${query}`, auth: true });
}

// POST /users/me/bind-email — 已登录用户补绑 HKMU 邮箱(后端发验证邮件,verify 后解锁 hkmu_verified)
function bindEmail(email) {
  return request({
    method: "POST",
    path: "/users/me/bind-email",
    data: { email },
    auth: true,
  });
}

module.exports = {
  getInviteCode,
  buildSharePath,
  consumeInvite,
  fetchFriends,
  fetchSuggest,
  bindEmail,
};

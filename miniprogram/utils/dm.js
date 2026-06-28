const auth = require("./auth");

// 头像点按 → 打开与该用户的私信(IG「Message from profile」式入口)。
// 自己 → no-op;未登录 → 跳登录;无 uid → no-op。
function openDMWith(uid) {
  if (!uid) {
    return;
  }
  const me = auth.getStoredUser();
  if (me && Number(me.id) === Number(uid)) {
    return;
  }
  if (!me || !wx.getStorageSync("hkmu_access_token")) {
    wx.navigateTo({ url: "/pages/login/login" });
    return;
  }
  wx.navigateTo({ url: `/pages/chat/chat?user_id=${uid}` });
}

module.exports = { openDMWith };

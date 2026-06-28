const auth = require("./utils/auth");

App({
  globalData: {
    postsNeedRefresh: false,
    user: null,
    pendingInvite: null, // Phase 5: 暂存邀请码,home 页 onShow 消费
  },

  // Phase 5: 捕获分享卡片带来的邀请码(?inv=xxx),暂存待 home 消费
  _captureInvite(options) {
    try {
      const inv = options && options.query && options.query.inv;
      if (inv) this.globalData.pendingInvite = inv;
    } catch (e) {}
  },

  onLaunch(options) {
    this._captureInvite(options);
    auth.bootstrapSession();
  },

  onShow(options) {
    this._captureInvite(options);
  },
});

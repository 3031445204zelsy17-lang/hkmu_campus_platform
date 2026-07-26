const auth = require("./utils/auth");
const log = require("./utils/log");

App({
  globalData: {
    postsRevision: 0, // Feed 版本号:写操作(发帖/删帖/点赞/评论)成功后 bump。列表页比较不清零(替代旧 postsNeedRefresh 布尔)
    user: null,
    pendingInvite: null, // Phase 5: 暂存邀请码,home 页 onShow 消费
  },

  // 全局错误兜底(内测监控 B3):未捕获错误 / 未处理 Promise 拒绝 → 上报微信后台实时日志。
  // 后台「运维中心 → 错误日志」也会自动收,这里补一层带 tag 的上下文。
  onError(err) {
    log.error("app.onError", err);
  },
  onUnhandledRejection(res) {
    log.error("app.unhandledRejection", res && res.reason);
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

const { syncTabBar } = require("../../utils/tabbar");

// Phase 3.1 stub — 收件箱实装见 Phase 3.3(列表 + WS 接入 + 未读)
Page({
  data: {},
  onLoad() {
    syncTabBar(this, 2);
  },
  onShow() {
    syncTabBar(this, 2);
  },
});

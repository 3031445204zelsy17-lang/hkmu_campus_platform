const auth = require("./utils/auth");

App({
  globalData: {
    postsNeedRefresh: false,
    user: null,
  },

  onLaunch() {
    auth.bootstrapSession();
  },
});

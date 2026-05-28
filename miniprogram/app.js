const auth = require("./utils/auth");

App({
  globalData: {
    user: null,
  },

  onLaunch() {
    auth.bootstrapSession();
  },
});

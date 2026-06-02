const { getLocale } = require("./i18n");

function syncTabBar(page, index) {
  const tabBar = typeof page.getTabBar === "function" ? page.getTabBar() : null;

  if (tabBar && typeof tabBar.applyLocale === "function") {
    tabBar.applyLocale(getLocale());
  }

  if (tabBar && typeof tabBar.setSelected === "function") {
    tabBar.setSelected(index);
  }
}

module.exports = {
  syncTabBar,
};

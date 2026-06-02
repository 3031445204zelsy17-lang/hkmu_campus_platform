const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");

const CATEGORY_KEYS = ["campus", "course", "life", "activity", "help"];

function buildCategories(activeCategoryKey, text = getTexts("compose")) {
  return CATEGORY_KEYS.map((key) => ({
    className: key === activeCategoryKey ? "category-chip active" : "category-chip",
    key,
    name: text.categories[key],
  }));
}

Page({
  data: {
    categories: buildCategories("campus"),
    category: getTexts("compose").categories.campus,
    categoryKey: "campus",
    content: "",
    displayName: getTexts("compose").defaultDisplayName,
    loading: false,
    locale: getLocale(),
    text: getTexts("compose"),
    title: "",
    user: null,
    userInitial: "H",
  },

  onShow() {
    this.applyLocale(getLocale());

    auth.bootstrapSession().then((user) => {
      if (!user) {
        wx.navigateTo({ url: "/pages/login/login" });
        return;
      }

      this.setData({
        displayName: user.displayName,
        user,
        userInitial: user.initial,
      });
    });
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("compose", locale);

    this.setData({
      categories: buildCategories(this.data.categoryKey, text),
      category: text.categories[this.data.categoryKey],
      displayName: this.data.user ? this.data.displayName : text.defaultDisplayName,
      locale,
      text,
    });
  },

  updateField(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({
      [field]: event.detail.value,
    });
  },

  selectCategory(event) {
    const categoryKey = event.currentTarget.dataset.category;
    const category = this.data.text.categories[categoryKey];
    this.setData({
      categories: buildCategories(categoryKey, this.data.text),
      category,
      categoryKey,
    });
  },

  submitPost() {
    if (this.data.loading) {
      return;
    }

    const title = this.data.title.trim();
    const content = this.data.content.trim();

    if (!title || !content) {
      wx.showToast({
        title: this.data.text.validationRequired,
        icon: "none",
      });
      return;
    }

    this.setData({ loading: true });

    request({
      method: "POST",
      path: "/posts",
      data: {
        category: this.data.category,
        content,
        title,
      },
      auth: true,
    })
      .then(() => {
        wx.showToast({
          title: this.data.text.success,
          icon: "success",
        });
        wx.switchTab({ url: "/pages/home/home" });
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || this.data.text.fail,
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },
});

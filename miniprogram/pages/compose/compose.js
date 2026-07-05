const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");
const { uploadImage } = require("../../utils/upload");

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
    imageTempPath: "",
    isAnonymous: false,
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

  chooseImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      sizeType: ["compressed"],
      success: (res) => {
        const file = res.tempFiles && res.tempFiles[0];
        if (file) {
          this.setData({ imageTempPath: file.tempFilePath });
        }
      },
    });
  },

  removeImage() {
    this.setData({ imageTempPath: "" });
  },

  toggleAnonymous(event) {
    this.setData({ isAnonymous: event.detail.value });
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

    const finalize = (imageUrl) => {
      request({
        method: "POST",
        path: "/posts",
        data: {
          category: this.data.category,
          content,
          is_anonymous: this.data.isAnonymous,
          title,
          image_url: imageUrl,
        },
        auth: true,
      })
        .then(() => {
          const app = getApp();
          if (app.globalData) {
            app.globalData.postsNeedRefresh = true;
          }
          wx.showToast({
            title: this.data.text.success,
            icon: "success",
          });
          wx.switchTab({ url: "/pages/community/community" });
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
    };

    if (this.data.imageTempPath) {
      uploadImage({ filePath: this.data.imageTempPath, module: "posts" })
        .then((url) => finalize(url))
        .catch((error) => {
          // Upload failed — abort submit, keep the picked image so the user can retry.
          wx.showToast({
            title: error.message || this.data.text.fail,
            icon: "none",
          });
          this.setData({ loading: false });
        });
    } else {
      finalize(null);
    }
  },
});

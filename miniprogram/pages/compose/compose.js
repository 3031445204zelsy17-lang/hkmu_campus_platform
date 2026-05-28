const auth = require("../../utils/auth");
const { request } = require("../../utils/request");

const CATEGORY_OPTIONS = ["校园", "课程", "生活", "活动", "求助"];

function buildCategories(activeCategory) {
  return CATEGORY_OPTIONS.map((name) => ({
    className: name === activeCategory ? "category-chip active" : "category-chip",
    name,
  }));
}

Page({
  data: {
    categories: buildCategories("校园"),
    category: "校园",
    content: "",
    displayName: "HKMU 同学",
    loading: false,
    title: "",
    user: null,
    userInitial: "H",
  },

  onShow() {
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

  updateField(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({
      [field]: event.detail.value,
    });
  },

  selectCategory(event) {
    const category = event.currentTarget.dataset.category;
    this.setData({
      categories: buildCategories(category),
      category,
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
        title: "标题和正文都要填写",
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
          title: "已发布",
          icon: "success",
        });
        wx.switchTab({ url: "/pages/home/home" });
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || "发布失败",
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },
});

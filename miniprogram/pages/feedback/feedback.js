const { request } = require("../../utils/request");
const { getLocale, getTexts } = require("../../utils/i18n");

const STARS = [1, 2, 3, 4, 5];

Page({
  data: {
    rating: 0,
    content: "",
    contact: "",
    submitting: false,
    locale: getLocale(),
    text: getTexts("feedback"),
    stars: STARS,
  },

  onLoad() {
    this.applyLocale(getLocale());
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    this.setData({ locale, text: getTexts("feedback", locale) });
  },

  onRatingTap(event) {
    this.setData({ rating: event.currentTarget.dataset.value });
  },

  onContentInput(event) {
    this.setData({ content: event.detail.value });
  },

  onContactInput(event) {
    this.setData({ contact: event.detail.value });
  },

  onSubmit() {
    const text = this.data.text;
    if (this.data.submitting) return;

    const content = (this.data.content || "").trim();
    if (!content) {
      wx.showToast({ title: text.contentRequired, icon: "none" });
      return;
    }

    // Default to 5 if the user writes but forgets to tap a star.
    const rating = this.data.rating || 5;

    this.setData({ submitting: true });
    request({
      method: "POST",
      path: "/feedback",
      data: {
        rating,
        content,
        contact: (this.data.contact || "").trim() || null,
      },
      auth: true,
    })
      .then(() => {
        wx.showToast({ title: text.success, icon: "success" });
        setTimeout(() => wx.navigateBack(), 1200);
      })
      .catch((error) => {
        wx.showToast({
          title: (error && error.message) || text.fail,
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ submitting: false });
      });
  },
});

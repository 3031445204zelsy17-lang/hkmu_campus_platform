const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { API_ORIGIN } = require("../../utils/config");
const { uploadImage } = require("../../utils/upload");
const { formatDate } = require("../../utils/format");
const { getLocale, getTexts } = require("../../utils/i18n");

function identityLabel(identity, text = getTexts("profile")) {
  if (!identity || identity === "student") {
    return text.student;
  }

  return identity;
}

// Supabase uploads come back absolute; legacy /assets/uploads paths are relative.
function absoluteUrl(url) {
  return url && url.startsWith("/") ? `${API_ORIGIN}${url}` : url || "";
}

Page({
  data: {
    editing: false,
    saving: false,
    draftNickname: "",
    draftBio: "",
    draftAvatarUrl: "",
    // Server-side avatar URL returned by /upload, sent to PUT /users/me on save.
    pendingAvatarUrl: "",
    identityLabel: "",
    joinedAtDisplay: getTexts("profile").today,
    joinedAtLabel: "",
    loading: false,
    locale: getLocale(),
    text: getTexts("profile"),
    user: null,
  },

  onShow() {
    this.applyLocale(getLocale());
    this.refreshProfile();
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("profile", locale);
    const joinedAtDisplay = this.data.user && this.data.user.created_at
      ? formatDate(this.data.user.created_at)
      : text.today;

    this.setData({
      identityLabel: identityLabel(this.data.user && this.data.user.identity, text),
      joinedAtDisplay,
      locale,
      text,
    });
  },

  onPullDownRefresh() {
    this.refreshProfile().finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  refreshProfile() {
    this.setData({ loading: true });

    return auth
      .bootstrapSession()
      .then((user) => {
        this.setData({
          identityLabel: identityLabel(user && user.identity, this.data.text),
          joinedAtDisplay: user && user.created_at ? formatDate(user.created_at) : this.data.text.today,
          joinedAtLabel: user && user.created_at ? formatDate(user.created_at) : "",
          user: user || null,
        });
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || this.data.text.loadFail,
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  enterEdit() {
    const user = this.data.user || {};
    this.setData({
      editing: true,
      draftNickname: user.nickname || "",
      draftBio: user.bio || "",
      draftAvatarUrl: user.avatar_url || "",
      pendingAvatarUrl: "",
    });
  },

  cancelEdit() {
    this.setData({ editing: false, pendingAvatarUrl: "" });
  },

  updateDraft(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({
      [field]: event.detail.value,
    });
  },

  chooseAvatar() {
    if (this.data.saving) {
      return;
    }

    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      sizeType: ["compressed"],
      success: (res) => {
        const file = res.tempFiles && res.tempFiles[0];
        if (!file) {
          return;
        }

        wx.showLoading({ title: this.data.text.avatarLoading, mask: true });
        uploadImage({ filePath: file.tempFilePath, module: "avatars" })
          .then((url) => {
            // Preview the absolute URL; keep the raw server URL to send on save.
            this.setData({
              draftAvatarUrl: absoluteUrl(url),
              pendingAvatarUrl: url,
            });
          })
          .catch((error) => {
            wx.showToast({
              title: error.message || this.data.text.avatarFail,
              icon: "none",
            });
          })
          .finally(() => {
            wx.hideLoading();
          });
      },
    });
  },

  saveProfile() {
    if (this.data.saving) {
      return;
    }

    const text = this.data.text;
    const nickname = (this.data.draftNickname || "").trim();
    const bio = (this.data.draftBio || "").trim();
    const user = this.data.user || {};

    if (!nickname) {
      wx.showToast({ title: text.nicknameRequired, icon: "none" });
      return;
    }

    const payload = {};
    if (nickname !== (user.nickname || "")) {
      payload.nickname = nickname;
    }
    if (bio !== (user.bio || "")) {
      payload.bio = bio;
    }
    if (this.data.pendingAvatarUrl) {
      payload.avatar_url = this.data.pendingAvatarUrl;
    }

    // Nothing changed — just leave edit mode without a redundant request.
    if (Object.keys(payload).length === 0) {
      this.setData({ editing: false, pendingAvatarUrl: "" });
      return;
    }

    this.setData({ saving: true });
    request({
      method: "PUT",
      path: "/users/me",
      data: payload,
      auth: true,
    })
      .then(() => {
        wx.showToast({ title: text.saveSuccess, icon: "success" });
        this.setData({ editing: false, pendingAvatarUrl: "" });
        // refreshProfile re-fetches /users/me and updates storage + global user.
        return this.refreshProfile();
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || text.saveFail,
          icon: "none",
        });
      })
      .finally(() => {
        this.setData({ saving: false });
      });
  },

  goToLogin() {
    wx.navigateTo({
      url: "/pages/login/login",
    });
  },

  goCompose() {
    wx.navigateTo({
      url: "/pages/compose/compose",
    });
  },

  logout() {
    auth.logout();
    this.setData({
      editing: false,
      identityLabel: "",
      joinedAtDisplay: this.data.text.today,
      joinedAtLabel: "",
      user: null,
    });
    wx.showToast({
      title: this.data.text.loggedOut,
      icon: "success",
    });
  },
});

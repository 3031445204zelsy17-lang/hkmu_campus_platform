const auth = require("../../utils/auth");
const { request } = require("../../utils/request");
const { API_ORIGIN } = require("../../utils/config");
const { uploadImage } = require("../../utils/upload");
const { formatDate } = require("../../utils/format");
const { getLocale, getTexts } = require("../../utils/i18n");
const { syncTabBar } = require("../../utils/tabbar");
const social = require("../../utils/social");

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
    privacyAction: getTexts("privacy").openAction,
    feedbackAction: getTexts("feedback").title,
    text: getTexts("profile"),
    user: null,
    sharePath: "", // Phase 5: 预取的邀请分享路径(onShareAppMessage 用)
  },

  onShow() {
    this.applyLocale(getLocale());
    syncTabBar(this, 4);

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
      privacyAction: getTexts("privacy", locale).openAction,
      feedbackAction: getTexts("feedback", locale).title,
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
        if (user) this._prefetchSharePath();
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

  openPrivacy() {
    wx.navigateTo({
      url: "/pages/privacy/privacy",
    });
  },

  openFeedback() {
    wx.navigateTo({
      url: "/pages/feedback/feedback",
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

  // Phase 5: 预取邀请码 → 分享路径(onShareAppMessage 同步返回,须提前就绪)
  _prefetchSharePath() {
    social
      .getInviteCode()
      .then((res) => {
        this.setData({ sharePath: social.buildSharePath(res.invite_code) });
      })
      .catch(() => {
        // 静默失败:未验证/网络异常时分享按钮走默认 path(不带 inv)
      });
  },

  // Phase 5 P0: 补绑 HKMU 邮箱,解锁同校验证层
  startBindEmail() {
    const text = this.data.text;
    wx.showModal({
      title: text.bindEmailTitle,
      editable: true,
      placeholderText: text.bindEmailPlaceholder,
      confirmText: text.bindEmailSend,
      success: (res) => {
        if (!res.confirm) return;
        const email = (res.content || "").trim();
        if (!email) return;
        social
          .bindEmail(email)
          .then(() => {
            wx.showToast({ title: text.bindEmailSent, icon: "success" });
          })
          .catch((err) => {
            wx.showToast({ title: (err && err.message) || text.bindEmailFail, icon: "none" });
          });
      },
    });
  },

  // Phase 5 P1: 邀请好友分享(带 inv 落地自动双向好友)
  onShareAppMessage() {
    return {
      title: this.data.text.inviteShareTitle,
      path: this.data.sharePath || "/pages/home/home",
    };
  },
});

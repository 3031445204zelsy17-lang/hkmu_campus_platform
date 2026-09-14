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
    termsAction: getTexts("terms").openAction,
    feedbackAction: getTexts("feedback").title,
    text: getTexts("profile"),
    user: null,
    sharePath: "", // Phase 5: 预取的邀请分享路径(onShareAppMessage 用)
    pickerOpen: false, // T03: 专业选择浮层开关
    programmeName: "", // T03: 当前专业名（catalogue code→name 映射）
    // 入学时间修改浮层（仿 T03）：entry_term 形如 "2025-autumn"，planner 的
    // 当前学年/毕业年/年份 tab 全由它推导
    entryTermOpen: false,
    entryTermDisplay: "",
    entryYears: [],
    entryPickYear: 0,
    entryPickSem: "autumn",
    entryTermSaving: false,
  },

  onShow() {
    this.applyLocale(getLocale());
    syncTabBar(this, 4);

    // PERF-7: 暖路径——切 tab 优先用 storage 缓存 user 立即渲染,后台静默刷新
    // (仿 home/community PERF-3)。有缓存则不显示 loading,避免已渲染内容闪烁。
    const cachedUser = auth.getStoredUser();
    if (cachedUser) {
      this._renderUser(cachedUser);
    }
    this.refreshProfile(!cachedUser);
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
    this._applyProgrammeName(); // 专业名随语言切换重取(中文/英文)
    this._applyEntryTermDisplay(); // 学期名(秋季/春季)随语言切换重取
  },

  onPullDownRefresh() {
    this.refreshProfile().finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  // PERF-7: 抽出 user 渲染逻辑(暖路径 + refreshProfile 共用,不含 prefetch)
  _renderUser(user) {
    this.setData({
      identityLabel: identityLabel(user && user.identity, this.data.text),
      joinedAtDisplay: user && user.created_at ? formatDate(user.created_at) : this.data.text.today,
      joinedAtLabel: user && user.created_at ? formatDate(user.created_at) : "",
      user: user || null,
    });
    this._applyEntryTermDisplay();
  },

  refreshProfile(showLoading = true) {
    if (showLoading) {
      this.setData({ loading: true });
    }

    return auth
      .bootstrapSession()
      .then((user) => {
        this._renderUser(user);
        if (user) {
          this._prefetchSharePath();
          this._loadProgrammeName();
        }
      })
      .catch((error) => {
        wx.showToast({
          title: error.message || this.data.text.loadFail,
          icon: "none",
        });
      })
      .finally(() => {
        if (showLoading) {
          this.setData({ loading: false });
        }
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

  // 用户协议(登录后入口;登录页另有入口)。terms 页正文含第 9 段禁止行为。
  openTerms() {
    wx.navigateTo({
      url: "/pages/terms/terms",
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

  // ── T03: 我的专业展示 + 切换（programme-picker 组件）──

  // 拉全校专业建 code→name 映射,展示"我的专业"名（仅登录态调）。
  // 存原始三语字段,应用时按 locale 取:中文优先官方目录名,缺失回退英文
  _loadProgrammeName() {
    if (this._progNameMap) {
      this._applyProgrammeName();
      return;
    }
    request({ path: "/courses/catalogue/programmes", auth: false })
      .then((data) => {
        const map = {};
        ((data && data.schools) || []).forEach((sch) => {
          (sch.programmes || []).forEach((p) => {
            map[p.programme_code] = {
              en: p.programme_name,
              zh_cn: p.name_zh_cn || "",
              zh_tw: p.name_zh_tw || "",
            };
          });
        });
        this._progNameMap = map;
        this._applyProgrammeName();
      })
      .catch(() => {
        // 静默失败:拉不到专业名时 value 显 programmeUnset
      });
  },

  _programmeNameForLocale(entry, locale) {
    if (!entry) return "";
    if (locale === "zh-Hans") return entry.zh_cn || entry.zh_tw || entry.en;
    if (locale === "zh-Hant") return entry.zh_tw || entry.zh_cn || entry.en;
    return entry.en;
  },

  _applyProgrammeName() {
    const code = this.data.user && this.data.user.programme_code;
    const entry = code && this._progNameMap && this._progNameMap[code];
    const name = this._programmeNameForLocale(entry, this.data.locale) || "";
    this.setData({ programmeName: name });
  },

  onOpenProgrammePicker() {
    this.setData({ pickerOpen: true });
    this._setPickerTabBarHidden(true);
  },

  onProgrammePickerClose() {
    this.setData({ pickerOpen: false });
    this._setPickerTabBarHidden(false);
  },

  onProgrammeSelect(e) {
    const { code, name } = e.detail;
    const text = this.data.text;
    this.setData({ pickerOpen: false });
    this._setPickerTabBarHidden(false);
    request({ method: "PUT", path: "/users/me", data: { programme_code: code }, auth: true })
      .then(() => {
        // 通知 planner 跟随切换(其 _selectedCode 优先级压过已存专业,不主动同步
        // 会一直显示旧专业直到冷启动)
        const app = getApp();
        if (app && app.globalData) app.globalData.programmeSwitched = code;
        wx.showToast({ title: text.saveSuccess, icon: "success" });
        this.setData({ programmeName: name || "" }); // 即时反馈
        return this.refreshProfile(false); // 兜底:同步 storage + 重拉 user
      })
      .catch((err) => {
        wx.showToast({ title: (err && err.message) || text.saveFail, icon: "none" });
      });
  },

  // ── 入学时间修改（仿 T03 换专业：行触发 → 浮层选择 → PUT /users/me）──────

  // entry_term "2025-autumn" → "2025 秋季"（随 locale 本地化学期名）。
  // 格式异常原样展示，缺失 → ""（行值显示 entryTermUnset）。
  _applyEntryTermDisplay() {
    const text = this.data.text;
    const raw = this.data.user && this.data.user.entry_term;
    const m = /^(\d{4})-(autumn|spring)$/.exec(raw || "");
    if (!m) {
      this.setData({ entryTermDisplay: raw || "" });
      return;
    }
    const sem = m[2] === "spring" ? text.entryTermSpring : text.entryTermAutumn;
    this.setData({ entryTermDisplay: `${m[1]} ${sem}` });
  },

  onOpenEntryTermPicker() {
    const cy = new Date().getFullYear();
    // 候选年份对齐 planner 引导步骤②（cy-3..cy+1）；已存值优先回显
    const m = /^(\d{4})-(autumn|spring)$/.exec((this.data.user && this.data.user.entry_term) || "");
    const year = m ? parseInt(m[1], 10) : cy;
    const sem = m ? m[2] : "autumn";
    const years = [cy - 3, cy - 2, cy - 1, cy, cy + 1];
    // 历史值可能落在候选窗口外(如转校生早年入学)→ 补进候选,保证回显可选
    if (!years.includes(year)) years.unshift(year);
    this.setData({
      entryTermOpen: true,
      entryYears: years,
      entryPickYear: year,
      entryPickSem: sem,
    });
    this._setPickerTabBarHidden(true);
  },

  onEntryTermClose() {
    this.setData({ entryTermOpen: false, entryTermSaving: false });
    this._setPickerTabBarHidden(false);
  },

  onEntryPickYear(e) {
    this.setData({ entryPickYear: parseInt(e.currentTarget.dataset.year, 10) });
  },

  onEntryPickSem(e) {
    this.setData({ entryPickSem: e.currentTarget.dataset.sem });
  },

  onEntryTermSave() {
    const text = this.data.text;
    if (this.data.entryTermSaving) return;
    const entryTerm = `${this.data.entryPickYear}-${this.data.entryPickSem}`;
    // 值没变 → 直接关,免一次无效 PUT
    if (entryTerm === ((this.data.user && this.data.user.entry_term) || "")) {
      this.onEntryTermClose();
      return;
    }
    this.setData({ entryTermSaving: true });
    request({ method: "PUT", path: "/users/me", data: { entry_term: entryTerm }, auth: true })
      .then((user) => {
        // 通知 planner 作废暖路径 user 缓存重拉(否则当前学年/毕业年/年份 tab
        // 停留旧学期直到冷启动,同 programmeSwitched 的理由)
        const app = getApp();
        if (app && app.globalData) app.globalData.entryTermChanged = true;
        this.setData({ entryTermOpen: false, entryTermSaving: false });
        this._setPickerTabBarHidden(false);
        wx.showToast({ title: text.saveSuccess, icon: "success" });
        if (user && user.entry_term) {
          this.setData({ user }); // 即时反馈(refreshProfile 兜底同步 storage)
          this._applyEntryTermDisplay();
        }
        return this.refreshProfile(false);
      })
      .catch((err) => {
        this.setData({ entryTermSaving: false });
        wx.showToast({ title: (err && err.message) || text.saveFail, icon: "none" });
      });
  },

  noop() {},

  _setPickerTabBarHidden(hidden) {
    const tabBar = typeof this.getTabBar === "function" ? this.getTabBar() : null;
    if (tabBar) tabBar.setData({ externallyHidden: !!hidden });
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

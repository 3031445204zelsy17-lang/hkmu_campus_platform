const { request } = require("../../utils/request");
const { formatDate, getInitial } = require("../../utils/format");
const { getLocale, getTexts } = require("../../utils/i18n");
const { PAGE_SIZE } = require("../../utils/config");
const auth = require("../../utils/auth");
const { uploadImage } = require("../../utils/upload");
const { openDMWith } = require("../../utils/dm");

function normalizeItems(items, text = getTexts("lostfound"), currentUserId = null) {
  return items.map((item) => {
    const isFound = item.item_type === "found";
    const isResolved = item.status === "resolved";
    const author = item.author_nickname || text.defaultAuthor;

    return {
      author,
      authorId: item.author_id,
      authorInitial: getInitial(author),
      category: item.category || text.uncategorized,
      createdAtLabel: formatDate(item.created_at) || text.justNow,
      description: item.description,
      id: item.id,
      isMine: currentUserId !== null && item.author_id === currentUserId,
      location: item.location || text.locationMissing,
      statusClass: isResolved ? "mini-pill" : "mini-pill green",
      statusLabel: isResolved ? text.statusResolved : text.statusActive,
      title: item.title,
      typeClass: isFound ? "mini-pill orange" : "mini-pill red",
      typeLabel: isFound ? text.typeFound : text.typeLost,
    };
  });
}

function filterItems(items, keyword) {
  const text = keyword.trim().toLowerCase();
  if (!text) {
    return items;
  }

  return items.filter((item) =>
    [item.title, item.description, item.category, item.location, item.author].some((value) =>
      String(value || "").toLowerCase().includes(text),
    ),
  );
}

function getTypeTabClasses(typeFilter) {
  return {
    allTabClass: typeFilter === "all" ? "segment-item active" : "segment-item",
    foundTabClass: typeFilter === "found" ? "segment-item active" : "segment-item",
    lostTabClass: typeFilter === "lost" ? "segment-item active" : "segment-item",
  };
}

function getStatusTabClasses(statusFilter) {
  return {
    activeStatusClass: statusFilter === "active" ? "segment-item active" : "segment-item",
    allStatusClass: statusFilter === "all" ? "segment-item active" : "segment-item",
    resolvedStatusClass: statusFilter === "resolved" ? "segment-item active" : "segment-item",
  };
}

Page({
  data: {
    activeStatusClass: "segment-item active",
    allStatusClass: "segment-item",
    allTabClass: "segment-item active",
    filteredItems: [],
    foundTabClass: "segment-item",
    hasNext: true,
    items: [],
    keyword: "",
    loading: false,
    locale: getLocale(),
    lostTabClass: "segment-item",
    page: 1,
    rawItems: [],
    resolvedStatusClass: "segment-item",
    statusFilter: "active",
    text: getTexts("lostfound"),
    typeFilter: "all",
    // Publish-form state (kept separate from the list browsing state above so
    // submitting a new item never toggles the list's `loading` line).
    // editingId: null = creating new, number = editing an existing item.
    // draftImageUrl: existing remote image when editing; draftImageTempPath is a
    // newly-picked local file that overrides it on submit.
    currentUserId: null,
    draftCategory: "",
    draftDescription: "",
    draftImageTempPath: "",
    draftImageUrl: "",
    draftItemType: "lost",
    draftLocation: "",
    draftTitle: "",
    editingId: null,
    formOpen: false,
    submitting: false,
  },

  onShow() {
    // Resolve the current user id so the list can flag the viewer's own items
    // (isMine) and show edit/resolve/delete actions on them.
    auth.bootstrapSession().then((user) => {
      this.setData({ currentUserId: (user && user.id) || null });
      this.applyLocale(getLocale());
    });
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  openDM(event) {
    openDMWith(event.currentTarget.dataset.authorId);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("lostfound", locale);
    const items = normalizeItems(this.data.rawItems, text, this.data.currentUserId);

    this.setData({
      filteredItems: filterItems(items, this.data.keyword),
      items,
      locale,
      text,
    });

  },

  onLoad() {
    this.loadItems(true);
  },

  onPullDownRefresh() {
    this.loadItems(true).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  onReachBottom() {
    if (!this.data.loading && this.data.hasNext) {
      this.loadItems(false);
    }
  },

  setTypeFilter(event) {
    const typeFilter = event.currentTarget.dataset.filter;
    if (typeFilter === this.data.typeFilter) {
      return;
    }

    this.setData(Object.assign({ typeFilter }, getTypeTabClasses(typeFilter)));
    this.loadItems(true);
  },

  setStatusFilter(event) {
    const statusFilter = event.currentTarget.dataset.status;
    if (statusFilter === this.data.statusFilter) {
      return;
    }

    this.setData(Object.assign({ statusFilter }, getStatusTabClasses(statusFilter)));
    this.loadItems(true);
  },

  updateKeyword(event) {
    const keyword = event.detail.value;
    this.setData({
      filteredItems: filterItems(this.data.items, keyword),
      keyword,
    });
  },

  // --- Publish form (page-inline form-sheet) ---
  openForm() {
    auth.bootstrapSession().then((user) => {
      if (!user) {
        wx.showToast({ title: this.data.text.loginRequired, icon: "none" });
        wx.navigateTo({ url: "/pages/login/login" });
        return;
      }
      // Default item_type to whatever the user is currently viewing, falling
      // back to "lost" when the list filter is "all".
      const draftItemType = this.data.typeFilter === "found" ? "found" : "lost";
      this.setData({
        draftCategory: "",
        draftDescription: "",
        draftImageTempPath: "",
        draftImageUrl: "",
        draftItemType,
        draftLocation: "",
        draftTitle: "",
        editingId: null,
        formOpen: true,
      });
    });
  },

  closeForm() {
    if (this.data.submitting) {
      return;
    }
    this.setData({ draftImageUrl: "", editingId: null, formOpen: false });
  },

  // Swallow taps on the form-sheet body so they don't bubble up to the
  // overlay's closeForm handler (only tapping the backdrop closes it).
  noop() {},

  selectDraftType(event) {
    const draftItemType = event.currentTarget.dataset.type;
    if (draftItemType === this.data.draftItemType) {
      return;
    }
    this.setData({ draftItemType });
  },

  updateDraft(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({ [field]: event.detail.value });
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
          this.setData({ draftImageTempPath: file.tempFilePath });
        }
      },
    });
  },

  removeDraftImage() {
    this.setData({ draftImageTempPath: "" });
  },

  submitItem() {
    if (this.data.submitting) {
      return;
    }

    const title = this.data.draftTitle.trim();
    const description = this.data.draftDescription.trim();

    if (!title || !description) {
      wx.showToast({ title: this.data.text.validationRequired, icon: "none" });
      return;
    }

    this.setData({ submitting: true });

    const isEditing = this.data.editingId !== null;

    const finalize = (imageUrl) => {
      const data = {
        title,
        description,
        item_type: this.data.draftItemType,
        category: this.data.draftCategory.trim() || null,
        location: this.data.draftLocation.trim() || null,
      };
      // For creates: always send image_url (null is fine). For edits: only send
      // it when a new image was just uploaded, otherwise leave the field out so
      // the PUT doesn't overwrite the existing image.
      if (!isEditing || imageUrl !== null) {
        data.image_url = imageUrl;
      }

      request({
        method: isEditing ? "PUT" : "POST",
        path: isEditing ? `/lostfound/${this.data.editingId}` : "/lostfound",
        data,
        auth: true,
      })
        .then(() => {
          wx.showToast({
            title: isEditing ? this.data.text.editSuccess : this.data.text.submitSuccess,
            icon: "success",
          });
          this.setData({ draftImageUrl: "", editingId: null, formOpen: false });
          this.loadItems(true);
        })
        .catch((error) => {
          wx.showToast({ title: error.message || this.data.text.submitFail, icon: "none" });
        })
        .finally(() => {
          this.setData({ submitting: false });
        });
    };

    if (this.data.draftImageTempPath) {
      uploadImage({ filePath: this.data.draftImageTempPath, module: "lostfound" })
        .then((url) => finalize(url))
        .catch((error) => {
          // Upload failed — abort submit, keep the picked image so user can retry.
          wx.showToast({ title: error.message || this.data.text.submitFail, icon: "none" });
          this.setData({ submitting: false });
        });
    } else {
      finalize(null);
    }
  },

  // --- Author actions on own items (edit / mark resolved / delete) ---
  // The buttons are only rendered on items where isMine is true (see wxml),
  // and the backend re-checks authorship on PUT/DELETE, so no client-side
  // permission guard is needed here.
  openEditForm(event) {
    const id = Number(event.currentTarget.dataset.id);
    const raw = this.data.rawItems.find((it) => it.id === id);
    if (!raw) {
      return;
    }
    this.setData({
      draftCategory: raw.category || "",
      draftDescription: raw.description || "",
      draftImageTempPath: "",
      draftImageUrl: raw.image_url || "",
      draftItemType: raw.item_type || "lost",
      draftLocation: raw.location || "",
      draftTitle: raw.title || "",
      editingId: id,
      formOpen: true,
    });
  },

  markResolved(event) {
    const id = Number(event.currentTarget.dataset.id);
    request({
      method: "PUT",
      path: `/lostfound/${id}`,
      data: { status: "resolved" },
      auth: true,
    })
      .then(() => {
        wx.showToast({ title: this.data.text.resolveSuccess, icon: "success" });
        this.loadItems(true);
      })
      .catch((error) => {
        wx.showToast({ title: error.message || this.data.text.loadFail, icon: "none" });
      });
  },

  deleteItem(event) {
    const id = Number(event.currentTarget.dataset.id);
    wx.showModal({
      title: this.data.text.deleteAction,
      content: this.data.text.deleteConfirm,
      confirmText: this.data.text.deleteAction,
      cancelText: this.data.text.formCancel,
      confirmColor: "#e5484d",
      success: (res) => {
        if (!res.confirm) {
          return;
        }
        request({
          method: "DELETE",
          path: `/lostfound/${id}`,
          auth: true,
        })
          .then(() => {
            wx.showToast({ title: this.data.text.deleteSuccess, icon: "success" });
            this.loadItems(true);
          })
          .catch((error) => {
            wx.showToast({ title: error.message || this.data.text.loadFail, icon: "none" });
          });
      },
    });
  },

  loadItems(reset) {
    if (this.data.loading) {
      return Promise.resolve();
    }

    const nextPage = reset ? 1 : this.data.page;
    const query = [`page=${nextPage}`, `page_size=${PAGE_SIZE.list}`];

    if (this.data.typeFilter !== "all") {
      query.push(`item_type=${this.data.typeFilter}`);
    }

    if (this.data.statusFilter !== "all") {
      query.push(`status=${this.data.statusFilter}`);
    }

    this.setData({ loading: true });

    return request({
      path: `/lostfound?${query.join("&")}`,
    })
      .then((data) => {
        const nextRawItems = data.items || [];
        const rawItems = reset ? nextRawItems : this.data.rawItems.concat(nextRawItems);
        const items = normalizeItems(rawItems, this.data.text, this.data.currentUserId);

        this.setData({
          filteredItems: filterItems(items, this.data.keyword),
          hasNext: !!data.has_next,
          items,
          page: nextPage + 1,
          rawItems,
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
});

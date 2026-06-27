const { getLocale, getTabBarItems } = require("../utils/i18n");
const messages = require("../utils/messages");

const SWITCH_LOCK_MS = 1200;
const SWITCH_COMMIT_DELAY_MS = 180;
const DRAG_STALE_MS = 1600;
const STUCK_REFRESH_MS = 10000;
const MOVE_FRAME_MS = 28;

let switchLockIndex = -1;
let switchLockTime = 0;
let navVisualState = {
  displaySelected: 0,
  pillPercent: 12.5,
  pillStyle: "opacity: 1; left: 12.50%;",
  selected: 0,
};

function lockSwitch(index) {
  switchLockIndex = index;
  switchLockTime = Date.now();
}

function clearSwitchLock(index = null) {
  if (index === null || switchLockIndex === index) {
    switchLockIndex = -1;
    switchLockTime = 0;
  }
}

function getSwitchLock() {
  if (switchLockIndex < 0) {
    return -1;
  }

  if (Date.now() - switchLockTime > SWITCH_LOCK_MS) {
    clearSwitchLock();
    return -1;
  }

  return switchLockIndex;
}

function updateNavVisualState(nextState) {
  navVisualState = Object.assign({}, navVisualState, nextState);
}

Component({
  data: {
    selected: navVisualState.selected,
    displaySelected: navVisualState.displaySelected,
    dragging: false,
    hydrating: true,
    pressedIndex: -1,
    pillStyle: navVisualState.pillStyle,
    switching: false,
    unread: 0,
    list: getTabBarItems(),
  },

  lifetimes: {
    attached() {
      this.setData({
        selected: navVisualState.selected,
        displaySelected: navVisualState.displaySelected,
        hydrating: true,
        pillStyle: navVisualState.pillStyle,
      });
      this.applyLocale();
      this.refreshBadge();
      this._badgeHandler = (n) => this.setData({ unread: n });
      messages.on("unread", this._badgeHandler);
      this.syncSelected();
      this.clearHydration();
      this._hydrationTimer = setTimeout(() => {
        this._hydrationTimer = null;
        this.setData({ hydrating: false });
      }, 80);
    },
    detached() {
      this._pendingTouchStart = false;
      if (this._badgeHandler) {
        messages.off("unread", this._badgeHandler);
        this._badgeHandler = null;
      }
      this.clearHydration();
      this.clearPendingSwitch();
      this.clearDragSafety();
      this.clearStuckRefresh();
    },
  },

  pageLifetimes: {
    show() {
      this.syncSelected();
      this.refreshBadge();
    },
    hide() {
      this.clearTransientInteraction();
    },
    resize() {
      this.measureCapsule(this.data.displaySelected);
    },
  },

  methods: {
    applyLocale(locale = getLocale()) {
      this.setData({
        list: getTabBarItems(locale),
      }, () => this.measureCapsule(this.data.displaySelected));
    },

    refreshBadge() {
      this.setData({ unread: messages.getUnread() });
    },

    currentRouteIndex() {
      const pages = getCurrentPages();
      const current = pages.length ? `/${pages[pages.length - 1].route}` : "";
      return this.data.list.findIndex((item) => item.pagePath === current);
    },

    getActiveIndex() {
      const lockedIndex = getSwitchLock();
      if (lockedIndex >= 0) return lockedIndex;

      const routeIndex = this.currentRouteIndex();
      if (routeIndex >= 0) return routeIndex;
      if (this.data.selected >= 0) return this.data.selected;
      return 0;
    },

    clampIndex(index, fallback = this.getActiveIndex()) {
      if (Number.isNaN(index) || index < 0 || index >= this.data.list.length) {
        return fallback;
      }
      return index;
    },

    clampPercent(percent) {
      return Math.min(98, Math.max(2, percent));
    },

    indexToPercent(index) {
      const count = Math.max(this.data.list.length, 1);
      const selected = this.clampIndex(index, 0);
      return this.clampPercent(((selected + 0.5) / count) * 100);
    },

    pillStyleForPercent(percent) {
      return `opacity: 1; left: ${this.clampPercent(percent).toFixed(2)}%;`;
    },

    rememberVisualState(index = this.data.displaySelected, percent = null) {
      const selected = this.clampIndex(index, this.getActiveIndex());
      const pillPercent = typeof percent === "number" ? this.clampPercent(percent) : this.indexToPercent(selected);

      updateNavVisualState({
        displaySelected: selected,
        pillPercent,
        pillStyle: this.pillStyleForPercent(pillPercent),
        selected: this.clampIndex(this.data.selected, selected),
      });
    },

    clearPendingSwitch() {
      if (this._switchTimer) {
        clearTimeout(this._switchTimer);
        this._switchTimer = null;
      }
    },

    clearHydration() {
      if (this._hydrationTimer) {
        clearTimeout(this._hydrationTimer);
        this._hydrationTimer = null;
      }
    },

    clearDragSafety() {
      if (this._dragSafetyTimer) {
        clearTimeout(this._dragSafetyTimer);
        this._dragSafetyTimer = null;
      }
    },

    clearStuckRefresh() {
      if (this._stuckRefreshTimer) {
        clearTimeout(this._stuckRefreshTimer);
        this._stuckRefreshTimer = null;
      }
    },

    armStuckRefresh() {
      this.clearStuckRefresh();
      this._stuckRefreshTimer = setTimeout(() => {
        this._stuckRefreshTimer = null;

        if (this._touchState || this.data.dragging || this.data.switching || getSwitchLock() >= 0) {
          this.resetInteraction();
        }
      }, STUCK_REFRESH_MS);
    },

    armDragSafety() {
      this.clearDragSafety();
      if (!this._touchState) return;

      const token = this._touchState.token;
      this._dragSafetyTimer = setTimeout(() => {
        if (this._touchState && this._touchState.token === token) {
          this.resetInteraction();
        }
      }, DRAG_STALE_MS);
    },

    currentStableIndex() {
      const lockedIndex = getSwitchLock();
      if (lockedIndex >= 0) return lockedIndex;

      const routeIndex = this.currentRouteIndex();
      if (routeIndex >= 0) return routeIndex;
      return this.clampIndex(this.data.selected, 0);
    },

    clearTransientInteraction() {
      this._pendingTouchStart = false;
      this._touchState = null;
      this._lastMoveApplyAt = 0;
      this.clearDragSafety();

      if (this.data.dragging || this.data.pressedIndex !== -1) {
        this.setData({
          dragging: false,
          pressedIndex: -1,
        });
      }
    },

    resetInteraction(index = this.currentStableIndex()) {
      this._pendingTouchStart = false;
      this._touchState = null;
      this._lastMoveApplyAt = 0;
      this.clearPendingSwitch();
      this.clearDragSafety();
      this.clearStuckRefresh();
      clearSwitchLock();

      const selected = this.clampIndex(index, 0);
      const pillPercent = this.indexToPercent(selected);
      const pillStyle = this.pillStyleForPercent(pillPercent);
      updateNavVisualState({
        displaySelected: selected,
        pillPercent,
        pillStyle,
        selected,
      });
      this.setData({
        selected,
        displaySelected: selected,
        dragging: false,
        pillStyle,
        pressedIndex: -1,
        switching: false,
      });
    },

    syncSelected() {
      this._pendingTouchStart = false;
      this.clearDragSafety();
      this.clearStuckRefresh();
      this._touchState = null;
      const selected = this.currentRouteIndex();
      const lockedIndex = getSwitchLock();

      if (lockedIndex >= 0 && selected !== lockedIndex) {
        this.armStuckRefresh();
        const pillPercent = this.indexToPercent(lockedIndex);
        const pillStyle = this.pillStyleForPercent(pillPercent);
        updateNavVisualState({
          displaySelected: lockedIndex,
          pillPercent,
          pillStyle,
          selected: lockedIndex,
        });
        this.setData({
          selected: lockedIndex,
          displaySelected: lockedIndex,
          dragging: false,
          pressedIndex: -1,
          pillStyle,
          switching: true,
        });
        return;
      }

      if (selected >= 0) {
        clearSwitchLock(selected);
        const pillPercent = this.indexToPercent(selected);
        const pillStyle = this.pillStyleForPercent(pillPercent);
        updateNavVisualState({
          displaySelected: selected,
          pillPercent,
          pillStyle,
          selected,
        });
        this.setData({
          selected,
          displaySelected: selected,
          dragging: false,
          pressedIndex: -1,
          pillStyle,
          switching: false,
        });
      } else {
        this.measureCapsule(this.data.displaySelected);
      }
    },

    setSelected(index) {
      const selected = this.clampIndex(Number(index), this.getActiveIndex());
      clearSwitchLock(selected);
      this._pendingTouchStart = false;
      this.clearPendingSwitch();
      this.clearDragSafety();
      this.clearStuckRefresh();
      this._touchState = null;
      const pillPercent = this.indexToPercent(selected);
      const pillStyle = this.pillStyleForPercent(pillPercent);
      updateNavVisualState({
        displaySelected: selected,
        pillPercent,
        pillStyle,
        selected,
      });
      this.setData({
        selected,
        displaySelected: selected,
        dragging: false,
        pressedIndex: -1,
        pillStyle,
        switching: false,
      });
    },

    measureNavRect(callback) {
      this.createSelectorQuery()
        .select(".tabbar-pill")
        .boundingClientRect()
        .exec((res) => {
          const navRect = res && res[0];
          if (!navRect || !navRect.width) return;
          this._navRect = navRect;
          if (callback) callback(navRect);
        });
    },

    measureCapsule(index = this.data.displaySelected, clientX = null) {
      this.measureNavRect(() => {
        if (typeof clientX === "number") {
          const target = this.getNavTarget(clientX);
          this.applyCapsule(target.index, target.xPercent);
          return;
        }

        this.applyCapsule(index);
      });
    },

    getNavTarget(clientX) {
      const count = Math.max(this.data.list.length, 1);
      const fallbackIndex = this.getActiveIndex();

      if (!this._navRect || !this._navRect.width) {
        return {
          index: fallbackIndex,
          xPercent: this.indexToPercent(fallbackIndex),
        };
      }

      const rawRatio = (clientX - this._navRect.left) / this._navRect.width;
      const ratio = Math.min(0.98, Math.max(0.02, rawRatio));
      const index = this.clampIndex(Math.floor(ratio * count), count - 1);

      return {
        index,
        xPercent: ratio * 100,
      };
    },

    applyCapsule(index = this.data.displaySelected, xPercent = null, extraData = {}) {
      const selected = this.clampIndex(index, this.getActiveIndex());
      const percent = typeof xPercent === "number" ? xPercent : this.indexToPercent(selected);
      const pillStyle = this.pillStyleForPercent(percent);
      this.rememberVisualState(selected, percent);

      this.setData(Object.assign({
        pillStyle,
      }, extraData));
    },

    beginDrag(clientX, clientY) {
      this.clearPendingSwitch();
      clearSwitchLock();
      const currentIndex = this.getActiveIndex();
      const target = this.getNavTarget(clientX);
      const token = `${Date.now()}-${Math.random()}`;

      this._touchState = {
        startX: clientX,
        startY: clientY,
        startIndex: currentIndex,
        targetIndex: target.index,
        targetPercent: target.xPercent,
        token,
      };
      this._lastMoveApplyAt = 0;
      this.armDragSafety();
      this.armStuckRefresh();
      updateNavVisualState({
        displaySelected: target.index,
        pillPercent: target.xPercent,
        pillStyle: this.pillStyleForPercent(target.xPercent),
        selected: currentIndex,
      });

      this.setData({
        selected: currentIndex,
        dragging: true,
        displaySelected: target.index,
        pressedIndex: target.index,
        pillStyle: this.pillStyleForPercent(target.xPercent),
        switching: false,
      });
    },

    handleTouchStart(event) {
      const touch = event.touches && event.touches[0];
      if (!touch) return;

      const clientX = touch.clientX;
      const clientY = touch.clientY;
      this._pendingTouchStart = true;

      if (this._navRect && this._navRect.width) {
        this.beginDrag(clientX, clientY);
        return;
      }

      this.measureNavRect(() => {
        if (this._pendingTouchStart) {
          this.beginDrag(clientX, clientY);
        }
      });
    },

    handleTouchMove(event) {
      if (!this._touchState || !this._navRect) return;
      const touch = event.touches && event.touches[0];
      if (!touch) return;

      this.armDragSafety();
      const target = this.getNavTarget(touch.clientX);
      this._touchState.targetIndex = target.index;
      this._touchState.targetPercent = target.xPercent;

      const now = Date.now();
      if (now - (this._lastMoveApplyAt || 0) < MOVE_FRAME_MS) {
        return;
      }
      this._lastMoveApplyAt = now;

      const nextData = {
        pillStyle: this.pillStyleForPercent(target.xPercent),
      };

      if (target.index !== this.data.displaySelected) {
        nextData.displaySelected = target.index;
        nextData.pressedIndex = target.index;
      }

      updateNavVisualState({
        displaySelected: target.index,
        pillPercent: target.xPercent,
        pillStyle: nextData.pillStyle,
        selected: this.data.selected,
      });
      this.setData(nextData);
    },

    handleTouchEnd() {
      this._pendingTouchStart = false;
      if (!this._touchState) return;
      this.clearDragSafety();
      this._lastMoveApplyAt = 0;
      const startIndex = this._touchState.startIndex;
      const targetIndex = this.clampIndex(this._touchState.targetIndex, startIndex);
      this._touchState = null;
      const item = this.data.list[targetIndex];
      const currentIndex = this.getActiveIndex();

      if (!item) {
        const pillPercent = this.indexToPercent(currentIndex);
        const pillStyle = this.pillStyleForPercent(pillPercent);
        updateNavVisualState({
          displaySelected: currentIndex,
          pillPercent,
          pillStyle,
          selected: currentIndex,
        });
        this.setData({
          dragging: false,
          displaySelected: currentIndex,
          selected: currentIndex,
          pressedIndex: -1,
          pillStyle,
          switching: false,
        }, () => this.clearStuckRefresh());
        return;
      }

      const targetPercent = this.indexToPercent(targetIndex);
      const targetPillStyle = this.pillStyleForPercent(targetPercent);
      updateNavVisualState({
        displaySelected: targetIndex,
        pillPercent: targetPercent,
        pillStyle: targetPillStyle,
        selected: targetIndex,
      });
      this.setData({
        dragging: false,
        displaySelected: targetIndex,
        pressedIndex: -1,
        pillStyle: targetPillStyle,
        switching: targetIndex !== currentIndex,
      });

      if (targetIndex !== currentIndex) {
        this.armStuckRefresh();
        lockSwitch(targetIndex);
        this.clearPendingSwitch();
        this._switchTimer = setTimeout(() => {
          this._switchTimer = null;
          wx.switchTab({
            url: item.pagePath,
            success: () => {
              clearSwitchLock(targetIndex);
              this.clearStuckRefresh();
              updateNavVisualState({
                displaySelected: targetIndex,
                pillPercent: targetPercent,
                pillStyle: targetPillStyle,
                selected: targetIndex,
              });
              this.setData({
                selected: targetIndex,
                displaySelected: targetIndex,
                pressedIndex: -1,
                pillStyle: targetPillStyle,
                switching: false,
              });
            },
            fail: () => {
              clearSwitchLock(targetIndex);
              this.clearStuckRefresh();
              const currentPercent = this.indexToPercent(currentIndex);
              const currentPillStyle = this.pillStyleForPercent(currentPercent);
              updateNavVisualState({
                displaySelected: currentIndex,
                pillPercent: currentPercent,
                pillStyle: currentPillStyle,
                selected: currentIndex,
              });
              this.setData({
                selected: currentIndex,
                displaySelected: currentIndex,
                pressedIndex: -1,
                pillStyle: currentPillStyle,
                switching: false,
              });
            },
          });
        }, SWITCH_COMMIT_DELAY_MS);
      } else {
        this.clearStuckRefresh();
      }
    },

    handleTouchCancel() {
      this._pendingTouchStart = false;
      this.resetInteraction();
    },
  },
});

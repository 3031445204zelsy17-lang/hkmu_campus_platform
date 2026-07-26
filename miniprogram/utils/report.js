const { request } = require("./request");
const { getTexts } = require("./i18n");

// 会话内记忆已举报的目标,避免对同一目标重复走流程(后端 UNIQUE 也会 409 兜底)。
const _reported = new Set(); // key: `${targetType}:${targetId}`

// 通用举报流:actionSheet 选原因 → 可选补充说明 → POST /reports。
// targetType 用后端 reports 表枚举:post | comment | lostfound | news_comment | user。
// 调用方负责登录守卫(未登录应先跳 login 再调本函数)。
// 返回 Promise<boolean>:true=已提交(或之前已举报),false=用户取消/失败。
function openReport(targetType, targetId) {
  const key = `${targetType}:${targetId}`;
  const t = getTexts("report");
  if (_reported.has(key)) {
    wx.showToast({ title: t.already, icon: "none" });
    return Promise.resolve(false);
  }
  const reasons = (t.reasons || []).slice();
  if (!reasons.length) return Promise.resolve(false);

  return new Promise((resolve) => {
    wx.showActionSheet({
      itemList: reasons.map((r) => r.label),
      success: (res) => {
        const reason = reasons[res.tapIndex];
        if (!reason) return resolve(false);
        wx.showModal({
          title: t.sheetTitle,
          editable: true,
          placeholderText: t.detailPrompt,
          confirmText: t.submit,
          success: (mres) => {
            if (!mres.confirm) return resolve(false);
            const detail = (mres.content || "").trim() || null;
            request({
              method: "POST",
              path: "/reports",
              data: {
                target_type: targetType,
                target_id: targetId,
                reason_code: reason.code,
                detail,
              },
              auth: true,
            })
              .then(() => {
                _reported.add(key);
                wx.showToast({ title: t.success, icon: "success" });
                resolve(true);
              })
              .catch((error) => {
                const msg = String((error && error.message) || "");
                if (/already reported|409|已举报|已檢舉/i.test(msg)) {
                  _reported.add(key);
                  wx.showToast({ title: t.already, icon: "none" });
                  resolve(true);
                  return;
                }
                wx.showToast({ title: msg || t.fail, icon: "none" });
                resolve(false);
              });
          },
          fail: () => resolve(false),
        });
      },
      fail: () => resolve(false),
    });
  });
}

module.exports = { openReport };

const { API_BASE, CLIENT_PLATFORM } = require("./config");
const { getSession } = require("./request");

// ── 上传前压缩 ─────────────────────────────────────────────────────
// Supabase storage 免费版无 CDN / 动态缩放,存原图(手机照片 2-5MB)加载很慢。
// 上传前用 offscreen canvas 按用途缩放 + jpg 压缩:头像 200px,配图 750px。
// 压缩任一环节失败 → resolve 原图(降级,绝不阻断上传)。
function _maxDimFor(moduleName) {
  return moduleName === "avatars" ? 200 : 750;
}

function compressImage(filePath, maxDim, quality) {
  return new Promise((resolve) => {
    if (!filePath) {
      resolve(filePath);
      return;
    }
    wx.getImageInfo({
      src: filePath,
      success: (info) => {
        const w0 = info.width || maxDim;
        const h0 = info.height || maxDim;
        const scale = Math.min(1, maxDim / Math.max(w0, h0));
        if (scale >= 1) {
          resolve(filePath); // 原图已够小,不压缩
          return;
        }
        const w = Math.max(1, Math.round(w0 * scale));
        const h = Math.max(1, Math.round(h0 * scale));
        let canvas;
        try {
          canvas = wx.createOffscreenCanvas({ type: "2d", width: w, height: h });
        } catch (e) {
          resolve(filePath);
          return;
        }
        const ctx = canvas.getContext("2d");
        const img = canvas.createImage();
        img.onload = () => {
          try {
            ctx.drawImage(img, 0, 0, w, h);
            wx.canvasToTempFilePath({
              canvas,
              fileType: "jpg",
              quality: quality == null ? 0.8 : quality,
              success: (res) => resolve((res && res.tempFilePath) || filePath),
              fail: () => resolve(filePath),
            });
          } catch (e) {
            resolve(filePath);
          }
        };
        img.onerror = () => resolve(filePath);
        img.src = filePath;
      },
      fail: () => resolve(filePath), // getImageInfo 失败 → 用原图
    });
  });
}

// ── 上传单个图片到 /api/v1/upload?module=<module> ──────────────────
// 返回 Promise<公开 URL 字符串>。
//
// Notes:
// - wx.uploadFile 自己设 multipart boundary,不能手动设 Content-Type(会覆盖 boundary)。
// - res.data 是字符串,需 JSON.parse。
// - wx.uploadFile 绕过 request.js,401 不会自动 refresh;这里抛错,由下一个普通 request() 触发刷新。
function _doUpload(filePath, moduleName) {
  const token = getSession().accessToken;

  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${API_BASE}/upload?module=${moduleName}`,
      filePath,
      name: "file",
      header: Object.assign(
        { "X-Client-Platform": CLIENT_PLATFORM },
        token ? { Authorization: `Bearer ${token}` } : {},
      ),
      success: (res) => {
        let data;
        try {
          data = typeof res.data === "string" ? JSON.parse(res.data) : res.data;
        } catch (e) {
          reject(new Error("Upload failed: invalid response"));
          return;
        }
        if (res.statusCode === 401) {
          reject(new Error("Session expired, please log in again"));
          return;
        }
        if (res.statusCode < 200 || res.statusCode >= 300 || !data || !data.url) {
          reject(new Error((data && data.detail) || `Upload failed (${res.statusCode})`));
          return;
        }
        resolve(data.url);
      },
      fail: (err) => {
        reject(new Error(err.errMsg || "Upload failed"));
      },
    });
  });
}

// 公共入口:先按 module 压缩再上传。接口不变 —— 头像/帖子/失物三处调用方无需改动。
function uploadImage({ filePath, module: moduleName }) {
  return compressImage(filePath, _maxDimFor(moduleName), 0.8).then((target) =>
    _doUpload(target, moduleName)
  );
}

module.exports = { uploadImage };

const { API_BASE, CLIENT_PLATFORM } = require("./config");
const { getSession } = require("./request");

// Upload a single image to /api/v1/upload?module=<module>.
// Returns a Promise that resolves with the public URL string.
//
// Notes:
// - wx.uploadFile sets the multipart/form-data boundary itself, so we must NOT
//   set Content-Type (doing so overwrites the boundary and breaks the upload).
// - res.data comes back as a STRING, so it must be JSON.parse'd.
// - wx.uploadFile bypasses utils/request.js, so a 401 will NOT auto-refresh the
//   token here; we surface the error and let the next normal request() refresh.
function uploadImage({ filePath, module: moduleName }) {
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

module.exports = { uploadImage };

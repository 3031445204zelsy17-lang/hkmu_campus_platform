/**
 * Reusable image-upload component.
 *
 * Usage (any page):
 *   import { createImageUploader } from "../components/image_upload.js";
 *   const uploader = createImageUploader({ module: "lostfound" });
 *   someContainer.appendChild(uploader.el);
 *   // On submit:
 *   const url = uploader.getUrl();   // string | null
 *
 * The component:
 *  - renders a drop-zone + file input
 *  - previews the selected image
 *  - uploads immediately on selection (calls POST /api/v1/upload)
 *  - stores the returned public URL
 *  - supports removal (re-select)
 */

import { api } from "../api.js";
import { getToken } from "../api.js";
import { showToast } from "../components/toast.js";

const MAX_SIZE = 10 * 1024 * 1024; // 10 MB
const ACCEPT = "image/jpeg,image/png,image/webp,image/gif";

/**
 * @param {{ module: string, compact?: boolean }} opts
 *   compact: render a minimal inline control (📷 button + thumbnail) instead
 *   of the full drop zone — for space-tight surfaces like comment boxes.
 *   Defaults to false; existing callers are unaffected.
 * @returns {{ el: HTMLElement, getUrl: () => string|null, setUrl: (url: string|null) => void }}
 */
export function createImageUploader({ module, compact = false }) {
  let _url = null;
  let _uploading = false;

  // ── Root container ──────────────────────────────────────────
  const wrap = document.createElement("div");
  wrap.className = "img-upload-wrap" + (compact ? " compact" : "");

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = ACCEPT;
  fileInput.className = "hidden";
  fileInput.setAttribute("aria-hidden", "true");

  // ── Control surface: drop zone (default) or inline button (compact) ──
  let hint = null;
  let pickBtn = null;

  if (compact) {
    pickBtn = document.createElement("button");
    pickBtn.type = "button";
    pickBtn.className = "img-upload-compact-btn";
    // heroicons-style outline camera, matching the page's SVG icon idiom
    // (stroke=currentColor picks up the button's CSS color)
    pickBtn.innerHTML =
      '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
      '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" ' +
      'd="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"/>' +
      '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" ' +
      'd="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z"/></svg>';
    pickBtn.title = "Attach image";
    pickBtn.setAttribute("aria-label", "Attach image");
    pickBtn.addEventListener("click", () => {
      if (!_uploading) fileInput.click();
    });
    wrap.appendChild(pickBtn);
    wrap.appendChild(fileInput);
  } else {
    const dropZone = document.createElement("div");
    dropZone.className = "img-upload-dropzone";
    dropZone.setAttribute("role", "button");
    dropZone.setAttribute("tabindex", "0");
    dropZone.setAttribute("aria-label", "Upload image");

    hint = document.createElement("span");
    hint.className = "img-upload-hint";
    hint.textContent = "📷 Click or drag image here (max 10 MB)";
    dropZone.appendChild(hint);
    dropZone.appendChild(fileInput);

    dropZone.addEventListener("click", () => {
      if (!_uploading) fileInput.click();
    });

    dropZone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (!_uploading) fileInput.click();
      }
    });

    // Drag & drop
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("dragover");
    });
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      if (e.dataTransfer.files?.[0]) _doUpload(e.dataTransfer.files[0]);
    });

    wrap.appendChild(dropZone);
  }

  // ── Preview area ────────────────────────────────────────────
  const preview = document.createElement("div");
  preview.className = "img-upload-preview" + (compact ? " compact" : " hidden");
  wrap.appendChild(preview);

  // ── Upload logic ────────────────────────────────────────────
  async function _doUpload(file) {
    // Client-side validation
    if (!ACCEPT.split(",").includes(file.type)) {
      showToast("Unsupported image format", "error");
      return;
    }
    if (file.size > MAX_SIZE) {
      showToast("File too large (max 10 MB)", "error");
      return;
    }

    _uploading = true;
    if (hint) hint.textContent = "⏳ Uploading…";
    if (pickBtn) pickBtn.classList.add("uploading");

    try {
      const fd = new FormData();
      fd.append("file", file);

      // We need a raw fetch because api.request() stringifies JSON bodies.
      const token = getToken();
      const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
      const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : null;

      const headers = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      if (csrf) headers["X-CSRF-Token"] = csrf;

      const res = await fetch(`/api/v1/upload?module=${module}`, {
        method: "POST",
        headers,
        body: fd,
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || res.statusText);
      }

      const data = await res.json();
      _url = data.url;
      _showPreview(_url);
      _emitChange();
      showToast("Image uploaded", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      _uploading = false;
      if (hint) hint.textContent = "📷 Click or drag image here (max 10 MB)";
      if (pickBtn) pickBtn.classList.remove("uploading");
    }
  }

  // ── Preview rendering ───────────────────────────────────────
  // Notify listeners (e.g. a comment box re-enabling its send button) that
  // the attached URL changed. Bubbles so parents can listen without holding
  // a reference to this component.
  function _emitChange() {
    wrap.dispatchEvent(new CustomEvent("img-upload-change", { bubbles: true }));
  }

  function _showPreview(url) {
    preview.innerHTML = "";
    if (compact) {
      preview.classList.add("has-image");
    } else {
      preview.classList.remove("hidden");
    }

    const img = document.createElement("img");
    img.src = url;
    img.alt = "Uploaded image preview";
    img.className = "img-upload-preview-img";
    preview.appendChild(img);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "img-upload-remove";
    removeBtn.textContent = "✕";
    removeBtn.title = "Remove image";
    removeBtn.addEventListener("click", () => {
      _url = null;
      if (compact) {
        preview.classList.remove("has-image");
      } else {
        preview.classList.add("hidden");
      }
      preview.innerHTML = "";
      fileInput.value = "";
      _emitChange();
    });
    preview.appendChild(removeBtn);
  }

  // ── Events ──────────────────────────────────────────────────
  fileInput.addEventListener("change", () => {
    if (fileInput.files?.[0]) _doUpload(fileInput.files[0]);
  });

  // ── Public API ──────────────────────────────────────────────
  return {
    el: wrap,
    getUrl: () => _url,
    setUrl(url) {
      _url = url;
      if (url) {
        _showPreview(url);
      } else {
        // clear: hide the preview so the control can be reset after a submit
        if (compact) {
          preview.classList.remove("has-image");
        } else {
          preview.classList.add("hidden");
        }
        preview.innerHTML = "";
        fileInput.value = "";
      }
      _emitChange();
    },
  };
}

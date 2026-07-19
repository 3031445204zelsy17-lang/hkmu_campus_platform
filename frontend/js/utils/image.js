/**
 * Responsive image helpers (Phase 2 image pipeline).
 *
 * The backend stores per-size variants at versioned paths like
 * ``…/uploads/posts/12/abc@640.jpg`` and ``…/abc@1280.jpg``, and returns the
 * feed-friendly size (640) as the canonical ``image_url``. ``responsiveSrcset``
 * derives the 2x URL by swapping the size label so a retina/wide viewport
 * fetches the larger variant instead of always loading the 1x one.
 *
 * Legacy uploads (pre-pipeline, no ``@<size>`` label) return "" so the caller
 * falls back to a plain ``src`` — no broken srcset.
 */

/**
 * Build a ``1x, 2x`` srcset for a versioned image URL.
 *
 * @param {string|null|undefined} url  The canonical (1x) image URL.
 * @param {{oneX?: number, twoX?: number}} [opts] Size labels to swap between.
 * @returns {string} srcset string, or "" if the URL isn't a versioned variant.
 */
export function responsiveSrcset(url, { oneX = 640, twoX = 1280 } = {}) {
  if (!url) return "";
  // Only version for known image extensions; anything else (legacy URL, OAuth
  // avatar on a different host, etc.) gets no srcset.
  if (!RegExp(`@${oneX}\\.(jpg|jpeg|png|webp)$`).test(url)) return "";
  return `${url} 1x, ${url.replace(`@${oneX}.`, `@${twoX}.`)} 2x`;
}

let _activeModal = null;

export function openModal(title, bodyHtml, { onClose } = {}) {
  closeModal();

  const overlay = document.createElement("div");
  overlay.id = "modal-overlay";
  overlay.className = "fixed inset-0 z-50 flex items-center justify-center bg-black/50";
  overlay.innerHTML = `
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 max-h-[90vh] overflow-auto">
      <div class="flex items-center justify-between px-6 py-4 border-b">
        <h3 class="text-lg font-semibold text-gray-800">${title}</h3>
        <button id="modal-close-btn" class="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
      </div>
      <div id="modal-body" class="px-6 py-4"></div>
    </div>
  `;

  const bodyEl = overlay.querySelector("#modal-body");
  if (typeof bodyHtml === "string") {
    bodyEl.innerHTML = bodyHtml;
  } else if (bodyHtml instanceof HTMLElement) {
    bodyEl.appendChild(bodyHtml);
  }

  const close = () => {
    closeModal();
    onClose?.();
  };

  overlay.querySelector("#modal-close-btn").addEventListener("click", close);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });

  document.body.appendChild(overlay);
  _activeModal = overlay;
}

export function closeModal() {
  if (_activeModal) {
    _activeModal.remove();
    _activeModal = null;
  }
}

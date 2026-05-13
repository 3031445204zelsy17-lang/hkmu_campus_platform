export function skeletonCard(count = 3) {
  return Array.from({ length: count }, () => `
    <div class="animate-pulse bg-white rounded-xl p-4 shadow-sm space-y-3">
      <div class="h-4 bg-gray-200 rounded w-3/4"></div>
      <div class="h-3 bg-gray-200 rounded w-full"></div>
      <div class="h-3 bg-gray-200 rounded w-5/6"></div>
      <div class="flex gap-4 mt-2">
        <div class="h-3 bg-gray-200 rounded w-12"></div>
        <div class="h-3 bg-gray-200 rounded w-12"></div>
      </div>
    </div>
  `).join("");
}

export function skeletonDetail() {
  return `
    <div class="animate-pulse bg-white rounded-xl p-6 shadow-sm space-y-4">
      <div class="h-6 bg-gray-200 rounded w-1/2"></div>
      <div class="h-4 bg-gray-200 rounded w-full"></div>
      <div class="h-4 bg-gray-200 rounded w-3/4"></div>
      <div class="h-4 bg-gray-200 rounded w-5/6"></div>
    </div>
  `;
}

export function errorState(title, detail = "") {
  return `
    <div class="flex flex-col items-center justify-center py-16 text-center">
      <div class="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
        <svg class="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
      </div>
      <h3 class="text-lg font-semibold text-gray-800 mb-1">${title}</h3>
      ${detail ? `<p class="text-sm text-gray-500">${detail}</p>` : ""}
    </div>
  `;
}

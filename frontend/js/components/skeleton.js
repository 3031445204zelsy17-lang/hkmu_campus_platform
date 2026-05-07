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

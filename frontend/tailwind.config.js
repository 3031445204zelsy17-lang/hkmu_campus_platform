/** @type {import('tailwindcss').Config} */
// Build-time Tailwind config (replaces the cdn.tailwindcss.com Play CDN that
// JIT-compiled in the browser on every load — a heavy render-blocking fetch).
//
// content globs MUST cover every file that authored a Tailwind class literal:
// index.html + offline.html + all JS (pages/components/utils). Classes are
// all static literals in this codebase (verified — no `bg-${x}` computed
// fragments), so the scanner captures them. The miniprogram/ dir is a separate
// WeChat app with its own wxss and is intentionally NOT scanned here.
module.exports = {
  content: [
    "./*.html",
    "./js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // Port of the inline tailwind.config from index.html (keep verbatim).
        'hkmu-blue': '#0066CC',
        'hkmu-green': '#2E7D52',
        'hkmu-light-blue': '#E3F2FD',
        'hkmu-light-green': '#E8F5E9',
        'page-bg': '#F5F7FA',
        'text-primary': '#1A1A2E',
        'text-secondary': '#6B7280',
      },
    },
  },
  plugins: [],
};

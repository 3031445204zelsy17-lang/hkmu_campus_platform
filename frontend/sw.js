const CACHE_NAME = 'hkmu-campus-v9';
const STATIC_CACHE = `${CACHE_NAME}-static`;
const DYNAMIC_CACHE = `${CACHE_NAME}-dynamic`;

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/css/main.css?v=phase11',
  '/css/nav.css?v=phase11',
  '/css/auth.css?v=phase11',
  '/css/community.css?v=phase11',
  '/css/academic.css?v=phase11',
  '/css/profile.css?v=phase11',
  '/css/news.css?v=phase11',
  '/css/lostfound.css?v=phase11',
  '/css/messages.css?v=phase11',
  '/js/app.js?v=phase11',
  '/js/router.js',
  '/js/api.js',
  '/js/pages/home.js?v=phase11',
  '/js/pages/community.js',
  '/js/pages/planner.js?v=phase11',
  '/js/pages/profile.js',
  '/js/pages/news.js',
  '/js/pages/lostfound.js',
  '/js/pages/messages.js',
  '/js/components/toast.js',
  '/js/components/skeleton.js',
  '/js/components/modal.js',
  '/js/components/nav.js',
  '/js/utils/i18n.js',
  '/js/utils/storage.js',
  '/js/utils/time.js',
  '/icons/HKMU.png',
  '/manifest.json',
  '/offline.html',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== DYNAMIC_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API requests: Network Only
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // CDN resources (Tailwind, fonts, Lucide): Stale-While-Revalidate
  if (url.origin !== self.location.origin) {
    event.respondWith(
      caches.open(DYNAMIC_CACHE).then((cache) =>
        cache.match(request).then(
          (cached) =>
            cached ||
            fetch(request).then((response) => {
              if (response.ok) cache.put(request, response.clone());
              return response;
            })
        )
      )
    );
    return;
  }

  // HTML pages: Network First with offline fallback
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(DYNAMIC_CACHE).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() =>
          caches.match(request).then((cached) => cached || caches.match('/offline.html'))
        )
    );
    return;
  }

  // Static assets (CSS/JS/images): Cache First
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((response) => {
          const clone = response.clone();
          caches.open(STATIC_CACHE).then((cache) => cache.put(request, clone));
          return response;
        })
    )
  );
});

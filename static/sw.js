const CACHE_NAME = 'ethrix-v3';
const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/js/script.js',
  '/static/manifest.json',
  '/static/images/logo.png',
  '/static/images/favicon.png'
];

// Install — cache only pure static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — clean old caches immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network first for HTML navigations & APIs, cache only for static assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Dynamic routes, APIs, and HTML navigations — always network
  if (
    event.request.mode === 'navigate' ||
    url.pathname === '/' ||
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/auth/') ||
    url.pathname.startsWith('/guest') ||
    url.pathname.startsWith('/bypass')
  ) {
    return;
  }

  // Static assets only — cache first
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
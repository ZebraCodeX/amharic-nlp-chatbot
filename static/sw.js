/* ሕሳር — service worker: cache the app shell + the static NLP data so the
   installable web app loads fast (and mostly works offline) on mobile. */
const CACHE = 'hisar-v1';
const SHELL = [
    '/',
    '/manifest.json',
    '/static/amharic-keyboard.css',
    '/static/amharic-keyboard.js',
    '/api/words',
    '/api/ngram',
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE)
            .then((c) => c.addAll(SHELL))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys
                .filter((k) => k !== CACHE)
                .map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

function cacheFirstRefresh(req) {
    return caches.match(req).then((hit) => {
        const fresh = fetch(req).then((res) => {
            if (res && res.ok && res.type === 'basic') {
                const copy = res.clone();
                caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return res;
        }).catch(() => hit);
        return hit || fresh;
    });
}

self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);
    if (url.origin !== location.origin) return;
    if (e.request.method !== 'GET') return;
    // live endpoints: never serve stale
    if (url.pathname === '/api/chat' ||
        url.pathname.startsWith('/api/suggest') ||
        url.pathname.startsWith('/api/translate')) {
        return;
    }
    if (url.pathname.startsWith('/api/')) {
        // static model data: cache-first with background refresh
        e.respondWith(cacheFirstRefresh(e.request));
        return;
    }
    e.respondWith(cacheFirstRefresh(e.request));
});
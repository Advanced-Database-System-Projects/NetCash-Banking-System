
const CACHE_NAME = "bankingsys-offline-v1";
const OFFLINE_URL = "/offline/";

// Save only the public offline page
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.add(OFFLINE_URL);
        })
    );

    self.skipWaiting();
});

// Remove old PWA caches
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys
                    .filter((key) =>
                        key.startsWith("bankingsys-offline-") &&
                        key !== CACHE_NAME
                    )
                    .map((key) => caches.delete(key))
            );
        })
    );

    self.clients.claim();
});

// Never cache financial or personal data
self.addEventListener("fetch", (event) => {
    const request = event.request;

    if (
        request.method !== "GET" ||
        request.mode !== "navigate"
    ) {
        return;
    }

    event.respondWith(
        fetch(request).catch(async () => {
            const cache = await caches.open(CACHE_NAME);
            return cache.match(OFFLINE_URL);
        })
    );
});

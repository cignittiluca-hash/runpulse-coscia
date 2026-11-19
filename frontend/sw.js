const CACHE_NAME = "runpulse-v3";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Never intercept API calls (avoids iOS Safari SW wake latency)
  if (event.request.url.includes("/api/")) {
    return;
  }
});

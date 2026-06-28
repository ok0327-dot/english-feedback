// 당근영어 PWA service worker — 설치 가능 + 가벼운 오프라인 캐시
// network-first: 온라인이면 항상 최신, 오프라인이면 캐시 폴백. (하위경로 GitHub Pages 호환)
const CACHE = "carrot-en-v2";

self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  e.respondWith(
    fetch(req)
      .then((res) => {
        try {
          if (res && res.status === 200 && new URL(req.url).origin === location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
        } catch (_) {}
        return res;
      })
      .catch(() =>
        caches.match(req).then((m) => m || caches.match(self.registration.scope))
      )
  );
});

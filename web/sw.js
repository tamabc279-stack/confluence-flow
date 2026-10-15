/* Service worker: đủ điều kiện cài PWA + ép tải lại trang (chép từ kiem-mua/docs/sw.js, bỏ phần push — app không gửi thông báo).
   Không cache offline — trang dựng lại mỗi ngày, cache cũ nguy hiểm hơn là không có. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.mode === "navigate" || /\.(js|css|webmanifest|json|html)$/.test(url.pathname)) {
    e.respondWith(fetch(new Request(e.request, { cache: "reload" })).catch(() => fetch(e.request)));
  }
});

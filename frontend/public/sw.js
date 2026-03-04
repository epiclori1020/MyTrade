// IMPORTANT: Bump version on every production deploy to invalidate cached assets
const CACHE_VERSION = "v2";
const STATIC_CACHE = `mytrade-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `mytrade-dynamic-${CACHE_VERSION}`;

const PRE_CACHE_URLS = [
  "/offline.html",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

// ─── Install ────────────────────────────────────────────────────────────────

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRE_CACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// ─── Activate ───────────────────────────────────────────────────────────────

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) =>
                key.startsWith("mytrade-") &&
                key !== STATIC_CACHE &&
                key !== DYNAMIC_CACHE
            )
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

function cloneAndCache(cacheName, request, response) {
  if (!response || !response.ok) return response;
  const cloned = response.clone();
  caches.open(cacheName).then((cache) => cache.put(request, cloned));
  return response;
}

// ─── Fetch ───────────────────────────────────────────────────────────────────

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 1. Auth Bypass — never cache auth routes or Supabase traffic
  if (
    url.pathname.startsWith("/auth") ||
    url.pathname.startsWith("/api/auth") ||
    url.hostname.includes("supabase.co")
  ) {
    return;
  }

  // 2. App Shell (Cache-First) — Next.js static chunks and icons
  if (
    url.pathname.startsWith("/_next/static") ||
    url.pathname.startsWith("/icons/")
  ) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) =>
          cloneAndCache(STATIC_CACHE, request, response)
        );
      })
    );
    return;
  }

  // 3. API — bypass SW entirely (financial data must never be served from cache)
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // 4. Navigation (Network-First + Offline Fallback)
  // SSR-rendered HTML may contain user-specific data (email, analysis_runs)
  // — never cache it. Only serve offline.html when network is unavailable.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/offline.html"))
    );
    return;
  }

  // 5. Static Assets (Cache-First) — default for everything else
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) =>
        cloneAndCache(DYNAMIC_CACHE, request, response)
      );
    })
  );
});

// ─── Push ────────────────────────────────────────────────────────────────────

self.addEventListener("push", (event) => {
  let data = { title: "MyTrade", body: "Neue Benachrichtigung" };
  try {
    if (event.data) data = event.data.json();
  } catch {
    /* Malformed payload */
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windowClients) => {
        for (const client of windowClients) {
          if (client.url.includes(self.location.origin) && "focus" in client) {
            return client.focus();
          }
        }
        return self.clients.openWindow("/dashboard");
      })
  );
});

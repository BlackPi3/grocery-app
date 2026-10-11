// The page's service worker: the phone keeps its own copy of the page, so a
// reload does not wait for a server that is starting up (12-20 s on Cloud
// Run after a quiet spell; kept that way because a server that never sleeps
// costs every hour of the day, Parham 2026-10-11).
//
// Only the page itself is handled here. The data the page shows is kept by
// the page (`saveCopy` in review.html), and every /v1 call and picture goes
// to the network untouched.
"use strict";
const CACHE = "basket-page";
// Long enough for an awake server, short enough that a sleeping one is not
// waited for: then the kept copy is shown, and the next reload is fresh.
const WAIT_MS = 1500;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.mode !== "navigate" || new URL(request.url).pathname !== "/") return;
  event.respondWith(page(event));
});

async function page(event) {
  const request = event.request;
  const cache = await caches.open(CACHE);
  // The network answer is kept whenever it comes, also after the copy was shown.
  const fresh = fetch(request).then(response => {
    if (response.ok) cache.put("/", response.clone());
    return response;
  });
  event.waitUntil(fresh.catch(() => null));
  const kept = await cache.match("/");
  if (!kept) return fresh;
  const late = new Promise(resolve => setTimeout(() => resolve(kept), WAIT_MS));
  return Promise.race([fresh.catch(() => kept), late]);
}

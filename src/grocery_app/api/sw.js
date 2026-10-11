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
  const kept = await cache.match("/");
  let keptShown = false;
  // The network answer is kept whenever it comes, also after the copy was
  // shown; if the copy was shown and is older, the page is told, so a phone
  // never stays on a page from before a deploy (2026-10-11: an old copy kept
  // a turned-away photo "reading" with its clock running).
  const fresh = fetch(request).then(async response => {
    if (response.ok) {
      const text = await response.clone().text();
      const before = kept ? await kept.clone().text() : null;
      await cache.put("/", response.clone());
      if (keptShown && before !== text) await tellPages("page-updated");
    }
    return response;
  });
  event.waitUntil(fresh.catch(() => null));
  if (!kept) return fresh;
  const shown = () => { keptShown = true; return kept.clone(); };
  const late = new Promise(resolve => setTimeout(() => resolve(shown()), WAIT_MS));
  return Promise.race([fresh.catch(shown), late]);
}

async function tellPages(message) {
  for (const client of await self.clients.matchAll({ type: "window" })) {
    client.postMessage(message);
  }
}

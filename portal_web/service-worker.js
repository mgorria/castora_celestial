'use strict';

// Push-only worker: it never intercepts fetch, caches a page or reads a conversation.
const OFFICE_PATH = '/castori/';
const DEFAULT_URL = OFFICE_PATH + '#conversations';
const ROUTES = /^(?:#(?:inicio|conversations|library|memories|wishes|clinic|vaca)|#chat\/(?:castori|mimosuga|salchicher|vaca|dulcimiel|corte)|#carta\/vaca)$/;
function officeURL(value) {
  try {
    const url = new URL(typeof value === 'string' ? value : DEFAULT_URL, self.location.origin);
    if (url.origin !== self.location.origin || url.username || url.password || url.pathname !== OFFICE_PATH || url.search || !ROUTES.test(url.hash)) return new URL(DEFAULT_URL, self.location.origin).href;
    return url.href;
  } catch (_) { return new URL(DEFAULT_URL, self.location.origin).href; }
}
function pushCount(value) { return Number.isSafeInteger(value) && value >= 0 ? value : 0; }
async function updateBadge(count) {
  try {
    if (count > 0) await self.navigator.setAppBadge?.(count);
    else await self.navigator.clearAppBadge?.();
  } catch (_) { /* Badges are an optional enhancement. */ }
}
self.addEventListener('install', event => { event.waitUntil(self.skipWaiting()); });
self.addEventListener('activate', event => { event.waitUntil(self.clients.claim()); });
self.addEventListener('push', event => {
  let payload = {};
  try { payload = event.data?.json() || {}; } catch (_) { /* Even an empty push must show a visible notice. */ }
  if (!payload || typeof payload !== 'object') payload = {};
  const count = pushCount(payload.unread_count);
  // Fixed copy prevents names or message contents reaching the lock screen.
  const displayed = self.registration.showNotification('Oficina Castori', {
    body: 'Hay mensajes nuevos sin leer en la Oficina Castori.',
    icon: OFFICE_PATH + 'assets/castori.png',
    tag: 'castori-unread',
    data: { url: officeURL(payload.url) }
  });
  // Always display, including when a window is focused. Apple disallows silent pushes.
  event.waitUntil(Promise.all([displayed, updateBadge(count)]));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = officeURL(event.notification.data?.url);
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      let url;
      try { url = new URL(client.url); } catch (_) { continue; }
      if (url.origin !== self.location.origin || !url.pathname.startsWith(OFFICE_PATH)) continue;
      try {
        const navigated = client.url === target ? client : await client.navigate(target);
        if (navigated) { await navigated.focus(); return; }
      } catch (_) { /* Another office window may still be usable. */ }
    }
    await self.clients.openWindow(target);
  })());
});

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
function forecastNotice(payload) {
  if (payload.kind !== 'vaca-forecast' || typeof payload.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(payload.date)
      || !Number.isInteger(payload.chance) || payload.chance < 1 || payload.chance > 99) return null;
  const day = new Date(payload.date + 'T12:00:00Z');
  if (!Number.isFinite(day.getTime()) || day.toISOString().slice(0, 10) !== payload.date) return null;
  const formatted = new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long' }).format(day).replace(',', '');
  const label = formatted[0].toUpperCase() + formatted.slice(1);
  const signal = payload.chance < 30 ? 'Bruma en el establo' : payload.chance < 50 ? 'Cascabeles lejanos' : payload.chance < 70 ? 'Huellas en la nieve' : 'Magia muy cerca';
  return { title: 'Parte vacunológico de mañana',
    body: `${label}: ${payload.chance} % de probabilidad de visita. ${signal}. La Vaca aún guarda sus sorpresas.`,
    tag: 'castori-vaca-forecast-' + payload.date, url: OFFICE_PATH + '#inicio' };
}
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
  const isTest = payload.kind === 'test';
  const forecast = forecastNotice(payload);
  const count = pushCount(payload.unread_count);
  // Conversations retain fixed private copy. A requested forecast is built only
  // from a validated date and percentage, never from arbitrary message content.
  const displayed = self.registration.showNotification(forecast?.title || 'Oficina Castori', {
    body: forecast?.body || (isTest ? 'Esta es una notificación de prueba de Oficina Castori.' : 'Hay mensajes nuevos sin leer en la Oficina Castori.'),
    icon: OFFICE_PATH + 'assets/castori.png',
    tag: forecast?.tag || (isTest ? 'castori-test' : 'castori-unread'),
    data: { url: officeURL(forecast?.url || payload.url) }
  });
  // Always display, including when a window is focused. Apple disallows silent pushes.
  event.waitUntil(isTest || forecast ? displayed : Promise.all([displayed, updateBadge(count)]));
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

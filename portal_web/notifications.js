(function () {
  'use strict';
  const preferenceKey = 'castori-notification-prompt-dismissed-v1';
  const escape = value => String(value || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const standalone = () => window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true;
  const ios = () => /iPad|iPhone|iPod/.test(navigator.userAgent || '') || navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
  const supportsPush = () => window.isSecureContext === true && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  const wantsInstall = () => ios() && !standalone();
  const permission = () => window.Notification?.permission || 'default';
  function dismissed() { try { return localStorage.getItem(preferenceKey) === '1'; } catch (_) { return false; } }
  function rememberDismissal() { try { localStorage.setItem(preferenceKey, '1'); } catch (_) { /* The choice still applies until this page closes. */ } }
  function keyBytes(value) {
    const base64 = value.replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(window.atob(base64 + '='.repeat((4 - base64.length % 4) % 4)), c => c.charCodeAt(0));
  }
  async function deviceId(subscription) {
    if (!subscription?.endpoint || !window.crypto?.subtle) return '';
    const bytes = await window.crypto.subtle.digest('SHA-256', new TextEncoder().encode(subscription.endpoint));
    return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
  }
  function badge(count) {
    try {
      const result = Number.isSafeInteger(count) && count > 0 ? navigator.setAppBadge?.(count) : navigator.clearAppBadge?.();
      Promise.resolve(result).catch(() => {});
    } catch (_) { /* Badges are optional and never mark messages as read. */ }
  }
  function create({ bridge, toast = () => {} }) {
    const root = document.getElementById('castori-notifications');
    let eligible = false, closing = false, version = 0, expanded = !dismissed();
    let registration = null, subscription = null, status = null, confirmed = false;
    let preparation = null, action = null, busy = false, checkedAt = 0, notice = '', renderedHTML = null;
    const current = stamp => eligible && !closing && stamp === version;
    function paint(html) {
      // Preserve the actual button between pointerdown and click, and keyboard focus during polling.
      if (renderedHTML === html) return;
      root.innerHTML = html;
      renderedHTML = html;
    }
    function render() {
      if (!root) return;
      root.hidden = !eligible || closing;
      if (root.hidden) { paint(''); return; }
      const enabled = confirmed && permission() === 'granted';
      if (!expanded) {
        paint(`<div class="notification-settings">${enabled ? '<span class="notification-state">Avisos activados en este dispositivo</span>' : ''}<button class="text-button" type="button" data-notification-action="settings">Ajustes de avisos</button></div>`);
        return;
      }
      let title = '¿Quieres que la oficina te avise cuando haya mensajes nuevos?';
      let description = '<p>Te llegará un aviso de la oficina, sin mostrar el contenido de las conversaciones.</p>';
      let primary = '';
      if (wantsInstall()) {
        description = '<p>En iPhone y iPad, guarda primero este rincón como una app:</p><ol><li>Abre esta página en Safari y pulsa <strong>Compartir</strong>.</li><li>Elige <strong>Añadir a pantalla de inicio</strong>.</li><li>Abre Oficina Castori desde su icono y pulsa <strong>Activar</strong>.</li></ol>';
      } else if (!supportsPush()) {
        title = 'Los avisos no están disponibles en este navegador.';
        description = '<p>Puedes seguir entrando en tu rincón para ver los mensajes nuevos.</p>';
      } else if (permission() === 'denied') {
        title = 'Los avisos están desactivados en este dispositivo.';
        description = '<p>Si te apetece activarlos, permite las notificaciones de Oficina Castori en los ajustes del navegador o del dispositivo. Después vuelve aquí y pulsa Activar.</p>';
      } else if (enabled) {
        title = 'La oficina ya puede avisarte aquí.';
        description = '<p>Recibirás un aviso cuando haya mensajes nuevos sin leer.</p>';
        primary = '<button class="text-button" type="button" data-notification-action="disable">Desactivar en este dispositivo</button>';
      } else if (!status || preparation && !registration?.active) {
        description = '<p>Preparando los avisos de este dispositivo…</p>';
      } else if (!status.available || !status.public_key || !registration?.active) {
        description = '<p>Ahora no podemos preparar los avisos. Puedes volver a intentarlo en un ratito.</p>';
        primary = '<button class="button secondary" type="button" data-notification-action="retry">Volver a comprobar</button>';
      } else {
        primary = '<button class="button" type="button" data-notification-action="enable">Activar</button>';
      }
      if (busy) primary = '<button class="button" type="button" disabled>Un momentito…</button>';
      paint(`<div class="notification-card"><div class="notification-copy"><strong>${title}</strong>${description}${notice ? `<p class="notification-notice" role="status">${escape(notice)}</p>` : ''}</div><div class="notification-actions">${primary}<button class="text-button" type="button" data-notification-action="later">${enabled ? 'Cerrar ajustes' : 'Ahora no'}</button></div></div>`);
    }
    async function prepare(stamp) {
      let phase = 'status';
      try {
        const nextStatus = await bridge.pushStatus();
        if (!current(stamp)) return;
        if (!supportsPush() || wantsInstall() || !nextStatus.available || !nextStatus.public_key) { status = nextStatus; return; }
        // Registration and the existing subscription are ready before the user taps Activar.
        phase = 'worker';
        const registered = await navigator.serviceWorker.register('/castori/service-worker.js', { scope: '/castori/', updateViaCache: 'none' });
        if (!current(stamp)) return;
        const activeRegistration = registered.active ? registered : await navigator.serviceWorker.ready;
        if (!current(stamp)) return;
        phase = 'device';
        const localSubscription = await activeRegistration.pushManager.getSubscription();
        const id = await deviceId(localSubscription);
        if (!current(stamp)) return;
        status = nextStatus;
        registration = activeRegistration;
        subscription = localSubscription;
        confirmed = Boolean(id && Array.isArray(status.device_ids) && status.device_ids.includes(id));
      } catch (_) {
        if (current(stamp)) {
          if (!registration?.active) { status = { available: false }; confirmed = false; }
          notice = phase === 'status' ? 'No hemos podido contactar con la oficina para preparar los avisos. Comprueba la conexión y vuelve a intentarlo.'
            : phase === 'worker' ? 'No hemos podido preparar los avisos en este dispositivo. Cierra y vuelve a abrir la oficina desde su icono.'
              : 'No hemos podido comprobar los avisos guardados en este dispositivo. Vuelve a intentarlo.';
        }
      } finally {
        if (current(stamp)) { preparation = null; checkedAt = Date.now(); render(); }
      }
    }
    function startPreparation() {
      if (preparation || busy || !eligible || closing) return preparation;
      preparation = prepare(version);
      render();
      return preparation;
    }
    async function discardSubscription(value, removeServer = false) {
      if (!value) return;
      try { if (removeServer) await bridge.pushUnsubscribe({ endpoint: value.endpoint }); }
      finally { await value.unsubscribe(); }
    }
    function subscriptionFailure(error) {
      if (permission() === 'denied') return 'Los avisos no se han autorizado. Puedes permitirlos en los ajustes de notificaciones del dispositivo.';
      if (error?.name === 'NotAllowedError') return 'El dispositivo no ha autorizado los avisos. Pulsa Activar para volver a intentarlo.';
      return 'El dispositivo no ha podido activar sus avisos. Pulsa Activar para volver a intentarlo.';
    }
    async function finishActivation(pendingSubscription, stamp) {
      let nextSubscription, saved = false, phase = 'subscribe';
      try {
        nextSubscription = await pendingSubscription;
        if (!current(stamp)) { await discardSubscription(nextSubscription); return; }
        // Retain a browser-approved subscription so a failed server save can be retried by a tap.
        subscription = nextSubscription;
        phase = 'save';
        await bridge.pushSubscribe({ subscription: { ...nextSubscription.toJSON(), userVisibleOnly: true } });
        saved = true;
        if (!current(stamp)) { await discardSubscription(nextSubscription, true); return; }
        subscription = nextSubscription;
        confirmed = true;
        notice = '';
        expanded = false;
        rememberDismissal();
        toast('La oficina ya puede avisarte en este dispositivo.');
      } catch (error) {
        // If registration could not be confirmed, a subsequent explicit tap can retry it.
        if (current(stamp)) {
          confirmed = false;
          notice = phase === 'save'
            ? 'El permiso está listo, pero no hemos podido guardar este dispositivo en la oficina. Comprueba la conexión y pulsa Activar de nuevo.'
            : subscriptionFailure(error);
          expanded = true;
        } else if (nextSubscription && !saved) {
          try { await discardSubscription(nextSubscription, true); } catch (_) { /* Local expiry is also pruned by the server. */ }
        }
      } finally {
        if (stamp === version) { busy = false; action = null; checkedAt = Date.now(); render(); }
      }
    }
    // Safari requires subscribe itself in the gesture handler; it presents the permission prompt.
    // https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers
    function enable() {
      if (!eligible || closing || busy) return;
      if (wantsInstall() || !supportsPush() || permission() === 'denied') { expanded = true; render(); return; }
      if (!status?.available || !registration?.active) {
        notice = 'Los avisos todavía se están preparando. Vuelve a comprobarlos en un momento.'; render(); return;
      }
      // Invalidate a background check begun before this explicit action; its result is now stale.
      const stamp = ++version;
      preparation = null;
      let pendingSubscription;
      try {
        pendingSubscription = permission() === 'granted' && subscription
          ? subscription
          : registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(status.public_key) });
      } catch (error) { notice = subscriptionFailure(error); render(); return; }
      busy = true;
      notice = '';
      action = finishActivation(pendingSubscription, stamp);
      render();
    }
    async function disable() {
      if (!eligible || closing || busy) return;
      const stamp = ++version;
      preparation = null;
      busy = true;
      render();
      try {
        const value = subscription || await registration?.pushManager.getSubscription();
        await discardSubscription(value, true);
        if (!current(stamp)) return;
        subscription = null; confirmed = false;
        notice = 'Los avisos están desactivados en este dispositivo.';
        badge(0);
      } catch (_) {
        if (current(stamp)) {
          const remaining = await registration?.pushManager.getSubscription().catch(() => subscription);
          if (!remaining) { subscription = null; confirmed = false; }
          notice = 'No hemos podido confirmar el cambio. Vuelve a comprobar los ajustes.';
        }
      } finally { if (stamp === version) { busy = false; action = null; checkedAt = Date.now(); render(); } }
    }
    root?.addEventListener('click', event => {
      const button = event.target.closest('[data-notification-action]');
      if (!button || !root.contains(button) || button.disabled) return;
      const name = button.dataset.notificationAction;
      if (name === 'enable') { enable(); return; }
      if (name === 'disable') { action = disable(); return; }
      if (name === 'later') { expanded = false; rememberDismissal(); render(); return; }
      if (name === 'settings') { expanded = true; notice = ''; startPreparation(); render(); return; }
      if (name === 'retry') { notice = ''; startPreparation(); }
    });
    async function update({ portal, authenticated, actor, unreadCount = 0 }) {
      const allowed = portal === true && authenticated === true && (actor === 'sandra' || actor?.role === 'sandra');
      if (!allowed) { reset(); return; }
      if (closing) return;
      if (!eligible) { eligible = true; version += 1; checkedAt = 0; }
      badge(unreadCount);
      if (!busy && !preparation && (!checkedAt || Date.now() - checkedAt > 60000)) startPreparation();
      render();
      await preparation;
    }
    async function beforeLogout() {
      closing = true;
      eligible = false;
      version += 1;
      const pending = [preparation, action];
      render();
      try {
        await Promise.allSettled(pending);
        const activeRegistration = registration || await navigator.serviceWorker?.getRegistration('/castori/');
        const value = await activeRegistration?.pushManager.getSubscription();
        await discardSubscription(value, true);
        const shown = await activeRegistration?.getNotifications?.();
        shown?.forEach(notification => notification.close());
      } finally { badge(0); }
    }
    function reset() {
      version += 1;
      eligible = false; closing = false; status = null; confirmed = false;
      preparation = null; action = null; subscription = null; busy = false; checkedAt = 0; notice = '';
      badge(0);
      render();
    }
    return Object.freeze({ update, beforeLogout, reset });
  }
  window.CastoriNotifications = Object.freeze({ create });
}());

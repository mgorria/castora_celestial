(function () {
  'use strict';
  const messages = { unauthorized: 'Esta sesión no tiene acceso a los bots.', forbidden: 'Esta acción no está disponible para tu sesión.', sign_in_required: 'Inicia sesión para entrar en tu rincón.', identity_not_linked: 'Tu cuenta todavía no está vinculada a este rincón.', bridge_not_configured: 'El acceso a los bots aún no está conectado.', bridge_unavailable: 'El acceso a los bots no está disponible en este momento.', origin_not_allowed: 'Abre este rincón desde su dirección original para continuar.', actor_not_supported: 'Esta sesión no está habilitada para este acceso.', callback_not_allowed: 'Este botón ya no está disponible para tu sesión.', unavailable: 'El acceso a los bots aún no está conectado.', animal_unavailable: 'Este personaje todavía no está disponible.', invalid_callback: 'Este botón ya no está disponible. Abre el mensaje más reciente.', callback_expired: 'Este botón ya ha caducado.', request_not_found: 'No se encuentra la confirmación de este envío.' };
  Object.assign(messages, { history_unavailable: 'No se pueden recuperar los mensajes anteriores en este momento.', stories_unavailable: 'No se puede consultar el archivo de cuentos en este momento.', story_not_found: 'Este cuento no está disponible en tu biblioteca.' });
  Object.assign(messages, { invalid_credentials: 'El usuario o la contraseña no coinciden. Prueba de nuevo.', invalid_invitation: 'Esta invitación ya no está disponible. Pídele a Miguel una nueva llave.', invalid_username: 'Elige otro nombre de usuario siguiendo las indicaciones.', weak_password: 'Elige una contraseña más larga para guardar bien tu rincón.', rate_limited: 'Ha habido varios intentos seguidos. Espera un momento antes de volver a probar.', temporarily_unavailable: 'No hemos podido abrir la puerta en este momento. Vuelve a intentarlo en un ratito.' });
  let unauthorizedHandler;
  Object.assign(messages, { invalid_password: 'Elige una contraseña de entre 12 y 128 caracteres.', account_exists: 'Esta cuenta ya tiene su llave. Entra con tu usuario o pide a Miguel una invitación de recuperación.', no_account: 'Todavía no hay una cuenta que recuperar. Primero hace falta una invitación de entrada.', accounts_unavailable: 'La puerta de acceso no está disponible en este momento. Vuelve a intentarlo en un ratito.', account_identity_unavailable: 'Tu rincón todavía necesita una conexión. Miguel puede comprobarla desde la Centralita.' });
  async function request(path, options = {}) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (options.signal) { options.signal.addEventListener('abort', abort, { once: true }); if (options.signal.aborted) controller.abort(); }
    const timer = setTimeout(abort, 15000);
    try {
      const response = await fetch((options.prefix || '/api/bridge') + path, { method: options.body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}) }, ...(options.body ? { body: JSON.stringify(options.body) } : {}), signal: controller.signal });
      if (options.portalProbe && response.status === 404) return { portal: false };
      if (!options.prefix && response.status === 401) unauthorizedHandler?.();
      let data;
      try { data = await response.json(); }
      catch (_) { const error = new Error(options.body ? 'No se ha podido confirmar el envío. Comprueba su estado antes de volver a enviarlo.' : 'El acceso a los bots aún no está conectado.'); error.status = response.status; error.uncertain = Boolean(options.body && (response.ok || response.status >= 500)); throw error; }
      if (!response.ok || data?.error) { const error = new Error(messages[data?.error] || (response.status === 401 || response.status === 403 ? messages.unauthorized : 'No se pudo completar la conexión. Vuelve a intentarlo.')); error.code = data?.error; error.status = response.status; error.uncertain = Boolean(options.body && response.status >= 500); throw error; }
      return data;
    } catch (error) {
      if (options.signal?.aborted) { error.cancelled = true; throw error; }
      if (error.name === 'AbortError' || error instanceof TypeError) { const failure = new Error(options.body ? 'No se ha podido confirmar el envío. Comprueba su estado antes de volver a enviarlo.' : 'El acceso a los bots aún no está conectado.'); failure.uncertain = Boolean(options.body); throw failure; }
      throw error;
    } finally { clearTimeout(timer); if (options.signal) options.signal.removeEventListener('abort', abort); }
  }
  window.CastoriBridge = Object.freeze({
    state: signal => request('/state', { signal }),
    events: (animal, after, signal) => request('/events?animal=' + encodeURIComponent(animal) + '&after=' + encodeURIComponent(after || 0), { signal }),
    history: (animal, before, signal) => request('/history?animal=' + encodeURIComponent(animal) + '&limit=30' + (before == null ? '' : '&before=' + encodeURIComponent(before)), { signal }),
    stories: (before, signal) => request('/stories?limit=12' + (before == null ? '' : '&before=' + encodeURIComponent(before)), { signal }),
    story: (id, signal) => request('/story?id=' + encodeURIComponent(id), { signal }),
    adminState: signal => request('/admin-state', { signal }),
    adminEvents: (after, signal) => request('/admin-events?after=' + encodeURIComponent(after ?? '0'), { signal }),
    adminAction: body => request('/admin-action', { body }),
    adminCallback: body => request('/admin-callback', { body }),
    invitation: signal => request('/admin-invitation', { signal }),
    invitationAction: action => request('/admin-invitation', { body: { action } }),
    accountSession: signal => request('/session', { prefix: '/api/account', portalProbe: true, signal }),
    accountLogin: body => request('/login', { prefix: '/api/account', body }),
    accountRegister: body => request('/register', { prefix: '/api/account', body }),
    accountLogout: () => request('/logout', { prefix: '/api/account', body: {} }),
    onUnauthorized: handler => { unauthorizedHandler = handler; },
    message: body => request('/message', { body }), callback: body => request('/callback', { body }),
    receipt: requestId => request('/request?request_id=' + encodeURIComponent(requestId)),
    requestId: () => window.crypto?.randomUUID ? window.crypto.randomUUID() : Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + '-' + Math.random().toString(36).slice(2)
  });
}());

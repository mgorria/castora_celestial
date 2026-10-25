(function () {
  'use strict';
  const { reply, stories } = window.CastoriDialogue;
  const characters = { ...window.CastoriDialogue.characters, corte: { name: 'La Corte Celestial', suggestions: [], greeting: '' } };
  const bridge = window.CastoriBridge;
  const ids = ['castori', 'mimosuga', 'salchicher', 'vaca', 'dulcimiel', 'corte'];
  const details = {
    castori: { short: 'Asuntos de mucho cariño', quote: 'Todo lo bonito merece su propio expediente.', description: 'Sellos, cartas y pequeños asuntos importantes. Castori recibe tus cartas y las atiende con calma, entre sellos y tazas de té.' },
    mimosuga: { short: 'Cuentos y abrazos de abuela', quote: 'Ven, nietecita. Tenemos todo el tiempo del mundo.', description: 'Una abuela tortuga, un bolsillo lleno de historias y esa manera suya de hacerte sentir en casa.' },
    salchicher: { short: 'Pequeños cuidados, mucho mimo', quote: 'A veces, la mejor pausa empieza con un «¿cómo estás?».', description: 'Gafitas, bata y un consultorio de cuento para revisar las alas, escuchar a Patita y preparar recetas de mimos.' },
    vaca: { short: 'Profecías, pistas y mucha ilusión', quote: 'Mi campanilla sabe cosas. Pero es muuuuy discreta.', description: 'Una profecía entre risitas, un secreto a medias y muuuuchas ganas de escucharte.' },
    dulcimiel: { short: 'Helados, horchata y felicidad', quote: 'Las cosas pequeñas también pueden endulzar un día.', description: 'La prima de la Vaca Mágica: pañuelo turquesa, sabores por descubrir y un poquito de leche mágica.' },
    corte: { short: 'Pequeños juicios y grandes mimos', quote: 'Toda historia merece escuchar las dos versiones.', description: 'Presenta una acusación de cuento y sigue el caso con los mismos botones de defensa de la Corte Celestial.' }
  };
  const actions = {
    castori: [], mimosuga: [{ label: 'Pedir un cuento', command: '/cuento', compose: true }],
    salchicher: [{ label: 'Abrir consulta', command: '/consulta' }, { label: 'Cómo funciona', command: '/ayuda' }, { label: 'Olvidar consulta', command: '/olvidar' }],
    vaca: [{ label: 'Ver mis deseos', command: '/lista' }, { label: 'Apuntar un deseo', command: '/pedir', compose: true }, { label: 'Marcar favorito', command: '/favorito', compose: true }, { label: 'Quitar un deseo', command: '/quitar', compose: true }, { label: 'Olvidar charla', command: '/olvidar' }],
    dulcimiel: [], corte: [{ label: 'Presentar una acusación', command: '/acusar', compose: true }]
  };
  const storageKey = 'oficina-castori-demo-v1';
  let state = { chats: {}, memories: [], wishes: [], theme: 'day' };
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved && typeof saved === 'object') {
      state.chats = saved.chats && typeof saved.chats === 'object' ? saved.chats : {};
      state.memories = Array.isArray(saved.memories) ? saved.memories.filter(m => m && typeof m.text === 'string') : [];
      state.wishes = Array.isArray(saved.wishes) ? saved.wishes.filter(w => w && typeof w.text === 'string') : [];
      state.theme = saved.theme === 'moon' ? 'moon' : 'day';
    }
  } catch (_) { /* Old local memories and the previous light preference. */ }
  const appearanceKey = 'oficina-castori-appearance-v1';
  const palettes = {
    patita: { name: 'Rosa Patita', description: 'Blanco de nube y rosa de mejillas.', day: '#fff7fa', moon: '#2d2029' },
    castor: { name: 'Castor', description: 'Marrón cacao y naranja de merienda.', day: '#fbf5ed', moon: '#2d241e' },
    celestial: { name: 'Casa Celestial', description: 'El verde suave de nuestro bosque.', day: '#f8f7f2', moon: '#202b25' }
  };
  let appearance = { palette: 'patita', light: state.theme };
  try {
    const saved = JSON.parse(localStorage.getItem(appearanceKey));
    if (saved && typeof saved === 'object') {
      if (typeof saved.palette === 'string' && Object.hasOwn(palettes, saved.palette)) appearance.palette = saved.palette;
      if (saved.light === 'day' || saved.light === 'moon') appearance.light = saved.light;
    }
  } catch (_) { /* Colours still work when device storage is unavailable. */ }
  const main = document.getElementById('main'), modal = document.getElementById('modal');
  const account = { actor: null, ownerInvite: false, checked: false, portal: false, authenticated: false, username: '', screen: 'login', code: '', loading: false, error: '', help: false };
  let accountVersion = 0;
  const invitation = { data: null, secret: null, loading: false, error: '', uncertain: false, version: 0, controller: null };
  const ownerInvitation = { data: null, secret: null, loading: false, error: '', uncertain: false, version: 0, controller: null };
  let deskAnimal = 'mimosuga';
  let view = 'home', activeId = 'mimosuga', mode = 'checking', toastTimer;
  let serverState = { characters: [], wishes: [] }, connectionError = '', connectionStatus = 0, connectVersion = 0, actorKey, liveEpoch = 0;
  let pollTimer, pollController, pollVersion = 0;
  const liveChats = {}, cursors = {}, deliveryNotes = {}, requests = new Map();
  const readReceipts = new Map(), readRequests = new Map(), unreadBoundaries = new Map();
  let unreadPollTimer, unreadPollVersion = 0, stateReadVersion = 0, initialChatScroll = null;
  // Connected text stays in memory only, scoped to the signed-in actor.
  const archives = {};
  const newPage = () => ({ items: [], loaded: false, loading: false, error: '', nextCursor: null, hasMore: false, available: true, version: 0, controller: null });
  let storyShelf = newPage(), storyController = null, storyVersion = 0;
  const admin = { data: null, events: [], cursor: '0', loading: false, error: '', busy: false, note: '', requestId: null, check: false, preview: null };
  const adminAuth = { portalPrepared: false, checked: false, configured: false, unlocked: false, expiresAt: null, loading: false, error: '', version: 0, controller: null, timer: null, requirePassword: false, revocationPending: false };
  let portalAuthQueue = Promise.resolve();
  const adminRequests = new Map();
  let adminTab = 'overview', adminController, adminPollController, adminTimer, adminVersion = 0;
  let demoAdminEvents = [], demoAdminSequence = 0;
  const adminFormDrafts = { live: {}, demo: {} };
  const pending = new Set(), sending = new Set(), callbackBusy = new Set();
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const uid = () => bridge.requestId();
  const config = id => serverState.characters.find(c => c && c.id === id);
  const ready = id => mode === 'demo' ? id !== 'corte' : mode === 'live' && Boolean(config(id)?.available);
  const isOwner = () => serverState.actor === 'owner' || serverState.actor?.role === 'owner';
  const readOnly = () => mode === 'live' && (isOwner() || serverState.read_only === true);
  const canOpenControl = () => mode === 'demo' || mode === 'live' && isOwner();
  const deskChatVisible = () => view === 'control' && adminTab === 'chats' && canUseControl();
  const chatVisible = id => view === 'chat' && activeId === id || deskChatVisible() && deskAnimal === id;
  const isSandra = () => serverState.actor === 'sandra' || serverState.actor?.role === 'sandra';
  const installedApp = () => window.navigator?.standalone === true || Boolean(window.matchMedia?.('(display-mode: standalone)').matches);
  // In an installed app, visibility is the foreground signal even when WebKit
  // does not report keyboard focus. Ordinary unfocused windows still wait.
  const readingForeground = () => document.visibilityState === 'visible' && (!document.hasFocus || document.hasFocus() || installedApp());
  function readingEndVisible(log) {
    if (!installedApp()) return true;
    const bounds = log?.getBoundingClientRect?.(), viewport = window.visualViewport;
    const top = viewport?.offsetTop || 0, bottom = top + (viewport?.height || window.innerHeight || document.documentElement?.clientHeight || 0);
    return Boolean(bounds && bounds.width > 0 && bounds.height > 0 && bounds.bottom > top && bounds.bottom <= bottom + 1);
  }
  const unreadKey = (animal, consultationId = null) => animal + ':' + (consultationId || '');
  const nonnegative = value => Number.isSafeInteger(value) && value >= 0 ? value : 0;
  function unreadAnimal(id) { return mode === 'live' ? serverState.unread?.animals?.[id] || {} : {}; }
  function unreadCount(id, consultationId) {
    const animal = unreadAnimal(id);
    if (consultationId === undefined) return nonnegative(animal.count);
    return nonnegative(animal.scopes?.find(scope => (scope.consultation_id || null) === (consultationId || null))?.count);
  }
  function unreadTotal() { return mode === 'live' ? ids.reduce((total, id) => total + unreadCount(id), 0) : 0; }
  function orderedIds() { return ids.slice().sort((a, b) => Number(unreadCount(b) > 0) - Number(unreadCount(a) > 0)); }
  function unreadBadge(count, extra = '') { return count > 0 ? `<span class="unread-badge ${extra}" aria-label="${count} ${count === 1 ? 'mensaje nuevo' : 'mensajes nuevos'}"><strong>${count > 99 ? '99+' : count}</strong> ${count === 1 ? 'Nuevo' : 'Nuevos'}</span>` : ''; }
  function unreadBoundary(animal, consultationId = null) {
    if (mode !== 'live') return null;
    const key = unreadKey(animal, consultationId);
    const item = unreadAnimal(animal);
    const scope = item.scopes?.find(scope => (scope.consultation_id || null) === (consultationId || null));
    const cursor = scope?.read_id ?? (consultationId == null ? item.read_id : undefined);
    if (Number.isSafeInteger(cursor) && cursor >= 0) unreadBoundaries.set(key, Math.max(unreadBoundaries.get(key) || 0, cursor));
    if (!unreadBoundaries.has(key)) return null;
    return unreadBoundaries.get(key);
  }
  function isUnreadMessage(animal, message, consultationId = null) {
    const cursor = unreadBoundary(animal, consultationId), eventId = message.event_id ?? message.id;
    return mode === 'live' && message.role === 'assistant' && cursor !== null && Number.isSafeInteger(eventId) && eventId > cursor;
  }
  function unreadOverview() {
    const count = unreadTotal(), chats = ids.filter(id => unreadCount(id) > 0).length;
    return count ? `<section class="unread-overview" aria-label="Mensajes nuevos"><span class="unread-overview-icon" aria-hidden="true">${icon('chat')}</span><div><strong>${count} ${count === 1 ? 'mensaje nuevo te espera' : 'mensajes nuevos te esperan'}</strong><p>En ${chats} ${chats === 1 ? 'conversación' : 'conversaciones'}. Abre la que te apetezca primero.</p></div><button class="button" data-chat="${orderedIds()[0]}">Leer los nuevos ${icon('arrow')}</button></section>` : '';
  }
  function renderUnreadChrome() {
    const count = unreadTotal(), menu = document.getElementById('mobile-menu');
    menu.innerHTML = `${icon('menu')}${count ? `<span class="mobile-unread-count">${count > 99 ? '99+' : count}<span class="sr-only"> mensajes nuevos</span></span>` : ''}`;
    menu.setAttribute('aria-label', count ? `Abrir menú, ${count} mensajes nuevos` : 'Abrir menú');
    for (const button of document.querySelectorAll('.nav-item[data-view="conversations"]')) {
      button.querySelector('.unread-badge')?.remove();
      if (count) button.insertAdjacentHTML('beforeend', unreadBadge(count, 'nav-unread'));
    }
  }
  function normalizeUnread(unread) {
    if (!unread || typeof unread.animals !== 'object' || !unread.animals) return unread;
    const animals = {};
    for (const [id, item] of Object.entries(unread.animals)) {
      if (!item || typeof item !== 'object') continue;
      const scopes = Array.isArray(item.scopes) ? item.scopes.map(scope => {
        const acknowledged = readReceipts.get(unreadKey(id, scope.consultation_id)) || 0;
        return acknowledged >= nonnegative(scope.latest_id) && acknowledged > nonnegative(scope.read_id) ? { ...scope, count: 0, read_id: acknowledged } : scope;
      }) : null;
      animals[id] = scopes ? { ...item, scopes, count: scopes.reduce((n, scope) => n + nonnegative(scope.count), 0), has_new: scopes.some(scope => nonnegative(scope.count) > 0) } : item;
    }
    return { ...unread, animals };
  }
  function applyUnread(unread) {
    if (!unread || typeof unread.animals !== 'object' || !unread.animals) return;
    unread = normalizeUnread(unread);
    const changed = JSON.stringify(serverState.unread) !== JSON.stringify(unread);
    serverState.unread = unread;
    if (mode !== 'live' || !changed) return;
    renderFriends(); syncNotifications();
    refreshUnreadViews();
  }
  function refreshUnreadViews() {
    if (view === 'home' || view === 'conversations') main.innerHTML = view === 'home' ? home() : conversations();
    if (view === 'chat') {
      const log = document.getElementById('chat-messages'), html = renderMessages(activeId);
      if (log && log.innerHTML !== html) {
        const top = log.scrollTop, height = log.scrollHeight, atBottom = height - top - log.clientHeight <= 24;
        log.innerHTML = html;
        log.scrollTop = atBottom ? log.scrollHeight : Math.max(0, top + log.scrollHeight - height);
      }
    }
    if (view === 'clinic' || view === 'consultation') experiences?.refreshUnread?.();
  }
  function syncNotifications() {
    Promise.resolve(notifications?.update?.({ portal: account.portal, authenticated: account.authenticated,
      actor: serverState.actor || account.actor, unreadCount: unreadTotal() })).catch(() => {});
  }
  function stopUnreadPolling() { unreadPollVersion++; clearTimeout(unreadPollTimer); }
  function startUnreadPolling() {
    stopUnreadPolling(); const version = unreadPollVersion;
    const run = async () => {
      if (version !== unreadPollVersion || mode !== 'live' || accountLocked()) return;
      if (document.visibilityState !== 'hidden') { try { await refreshServerState(); } catch (_) { /* The last confirmed counters remain visible. */ } }
      if (version === unreadPollVersion && mode === 'live') unreadPollTimer = setTimeout(run, 12000);
    };
    unreadPollTimer = setTimeout(run, 12000);
  }
  async function acknowledgeRead(animal, eventId, consultationId = null) {
    if (mode !== 'live' || !isSandra() || !readingForeground() || !bridge.read
        || !Number.isSafeInteger(eventId) || eventId <= 0) return;
    const key = animal + ':' + (consultationId || ''), epoch = liveEpoch;
    if ((readReceipts.get(key) || 0) >= eventId || readRequests.has(key)) return;
    const record = { epoch, eventId }; readRequests.set(key, record);
    try {
      const result = await bridge.read({ animal, event_id: eventId, consultation_id: consultationId });
      if (epoch === liveEpoch) {
        readReceipts.set(key, Math.max(eventId, readReceipts.get(key) || 0));
        if (result?.unread) applyUnread(result.unread);
        await refreshServerState();
      }
    } catch (_) { /* A later visible render/poll retries this idempotent acknowledgement. */ }
    finally { if (readRequests.get(key) === record) readRequests.delete(key); }
  }
  function acknowledgeChatRead() {
    if (view !== 'chat' || mode !== 'live' || modal.open) return;
    const log = document.getElementById('chat-messages');
    if (!log || log.scrollHeight - log.scrollTop - log.clientHeight > 24 || !readingEndVisible(log)) return;
    // A global polling cursor can include other animals or messages not shown.
    // Only the latest actual assistant message rendered in this chat is read.
    const latest = chatHistory(activeId).filter(m => m.role === 'assistant')
      .map(m => ({ id: m.event_id ?? m.id, consultationId: m.consultation_id || null }))
      .filter(m => Number.isSafeInteger(m.id) && m.id > 0).sort((a, b) => b.id - a.id)[0];
    if (latest) acknowledgeRead(activeId, latest.id, latest.consultationId);
  }
  function acknowledgeVisibleRead() { acknowledgeChatRead(); experiences?.acknowledgeVisible(); }
  const canUseControl = () => canOpenControl() && (mode === 'demo' || adminAuth.unlocked && !adminAuth.requirePassword && !adminAuth.revocationPending && !adminAuth.loading && Date.parse(adminAuth.expiresAt) > Date.now());
  // Preview tools are available only on a local development host, never in Sandra's portal.
  const canExploreDemo = () => !account.portal && ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  const accountLocked = () => !account.checked || account.portal && !account.authenticated;
  function canCommand(id, command) {
    const list = config(id)?.commands;
    return !readOnly() && ready(id) && Array.isArray(list) && list.some(c => String(typeof c === 'object' ? c.command : c).replace(/^\//, '') === command.replace(/^\//, ''));
  }
  function status(id) {
    if (mode === 'demo') return id === 'corte' ? 'Disponible al conectar' : 'Conversación de ejemplo';
    if (id === 'dulcimiel') return 'Próximamente';
    if (mode === 'checking') return 'Abriendo la puerta…';
    if (config(id)?.reason === 'owner_uses_centralita') return 'Disponible desde Centralita';
    if (!ready(id)) return 'Volvemos en un ratito';
    return id === 'castori' || config(id)?.mode === 'manual' ? 'La ventanilla está abierta' : 'Te está esperando';
  }
  function persist() { try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { toast('No hemos podido guardar este recuerdo en tu dispositivo.'); } }
  function toast(message) { const el = document.getElementById('toast'); el.textContent = message; el.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 4800); }
  function portrait(id, avatar = false) {
    if (id === 'corte') return `<span class="${avatar ? 'avatar avatar-symbol' : 'court-portrait'}" aria-hidden="true"><span>⚖</span>${avatar ? '' : '<small>la corte celestial</small>'}</span>`;
    return `<img class="${avatar ? 'avatar' : ''}" src="assets/${id === 'vaca' ? 'vaca-v2' : id}.png" alt="${avatar ? '' : esc(characters[id].name)}" ${avatar ? '' : 'loading="lazy"'}>`;
  }
  const notifications = window.CastoriNotifications?.create({ bridge, toast });
  const experiences = window.CastoriExperiences?.create({ bridge, esc, icon, portrait, formatDate, formatTime, uid,
    mode: () => mode, epoch: () => liveEpoch, ready, readOnly, navigate, toast, showModal, closeModal: () => modal.close(), submitLive,
    refreshState: refreshServerState, acknowledgeRead, readingForeground, readingEndVisible, updateUnread: applyUnread, unreadCount, unreadBadge, isUnreadMessage, unreadBoundary, modalOpen: () => modal.open,
    wishes: () => mode === 'demo' ? state.wishes.map(w => ({ ...w, name: w.text })) : (serverState.wishes || []),
    demoWish: (action, wish) => { if (mode !== 'demo') return; if (action === 'add') state.wishes.push(wish); else if (action === 'remove') state.wishes = state.wishes.filter(w => w.id !== wish.id); else { const w = state.wishes.find(w => w.id === wish.id); if (w) w.favorite = !w.favorite; } persist(); }
  });
  function accountChrome() {
    document.body.dataset.access = accountLocked() ? 'locked' : 'open';
    document.getElementById('account-gate').hidden = !accountLocked();
    const logout = document.getElementById('account-logout'); logout.hidden = !(account.portal && account.authenticated); logout.disabled = account.loading;
    document.getElementById('profile-name').innerHTML = account.portal && account.authenticated ? `${esc(account.username)}<small>Tu rincón en la Casa Celestial</small>` : 'El rincón de Patita<small>Hecho con muchísimo cariño</small>';
  }
  function readInvitationFragment() {
    account.ownerInvite = location.hash.startsWith('#owner-invite/');
    if (!account.ownerInvite && !location.hash.startsWith('#invite/')) return;
    try { account.code = decodeURIComponent(location.hash.slice(account.ownerInvite ? 14 : 8)).slice(0, 512); } catch (_) { account.code = ''; }
    account.screen = 'register';
    history.replaceState(null, '', (location.pathname || '/castori/') + (location.search || ''));
  }
  function renderAccountGate() {
    accountChrome();
    const checking = !account.checked, registering = account.screen === 'register';
    const body = checking ? `<div class="account-wait" role="status">${icon('key')}<h2>${account.error ? 'La puerta necesita un momento.' : 'Estamos preparando tu llegada.'}</h2><p>${esc(account.error || 'Comprobando tu llave a la Casa Celestial…')}</p>${account.error ? '<button class="button" data-account-retry>Volver a intentarlo</button>' : ''}</div>` : `<div class="account-tabs" aria-label="Cómo quieres entrar"><button data-account-screen="login" aria-pressed="${!registering}" class="${registering ? '' : 'active'}">Ya tengo mi llave</button><button data-account-screen="register" aria-pressed="${registering}" class="${registering ? 'active' : ''}">Tengo una invitación</button></div><form id="account-form" class="account-form">${registering ? `<label>Código de invitación<input name="code" id="account-code" value="${esc(account.code)}" maxlength="512" autocomplete="off" spellcheck="false" autocapitalize="none" required placeholder="La llave que Castori ha preparado para ti"></label>` : ''}<label>${registering ? 'Tu nombre de usuario' : 'Nombre de usuario'}<input id="account-username" name="username" value="${esc(account.username)}" autocomplete="username" autocapitalize="none" spellcheck="false" minlength="3" maxlength="32" required placeholder="Entre 3 y 32 letras, números, puntos o guiones"></label><label>${registering ? 'Elige tu contraseña' : 'Contraseña'}<span class="account-password"><input id="account-password" name="password" type="password" autocomplete="${registering ? 'new-password' : 'current-password'}" maxlength="128" required placeholder="${registering ? 'La contraseña que quieras usar' : 'Tu llave secreta'}"><button type="button" data-account-show-password aria-label="Mostrar contraseña">Mostrar</button></span></label>${registering ? '<p class="account-field-note">No necesitas correo. Elige la contraseña que prefieras.</p>' : ''}<div id="account-error" class="account-error" role="alert">${esc(account.error)}</div><button class="button account-submit" type="submit" ${account.loading ? 'disabled' : ''}>${account.loading ? 'Abriendo la puerta…' : registering ? 'Crear mi llave y entrar' : 'Entrar en mi rincón'} ${icon('arrow')}</button></form><button class="text-button account-help-button" data-account-help>¿Necesitas una nueva llave?</button>${account.help ? '<p class="account-help">Pídele a Castori una nueva invitación. Si ya tienes cuenta, utiliza el mismo nombre de usuario y elige una contraseña nueva.</p>' : ''}`;
    document.getElementById('account-gate').innerHTML = `<div class="account-layout"><aside class="account-illustration"><img src="assets/casa-celestial-v2.png" alt="Los amigos de la Casa Celestial esperan junto a su cálida oficina en el árbol"><div class="account-art-copy"><span class="eyebrow">SIEMPRE HAY UNA SILLA PARA TI</span><h2>Las cosas bonitas<br>empiezan por <em>entrar.</em></h2><p>Un cuento, un abrazo y todos tus amigos,<br>al otro lado de esta pequeña puerta.</p></div><div class="account-art-footer">${icon('heart')} Pasa. Estás en casa.</div></aside><div class="account-card"><a class="account-brand" href="#" aria-label="Casa Celestial"><span class="brand-seal">c<span>✦</span></span><span>la casa celestial<small>UN RINCÓN HECHO DE CARIÑO</small></span></a><div class="account-key" aria-hidden="true">${icon('key')}</div><h1>Tu llave a la<br><em>Casa Celestial.</em></h1><p class="account-intro">Tu pequeño universo tiene una puerta<br>que se abre solo para ti.</p>${body}<div class="account-footnote">${icon('star')} Historias, magia y mucho cariño.</div></div></div>`;
    if (!checking) document.getElementById('account-form').addEventListener('submit', event => { event.preventDefault(); submitAccount(); });
  }
  async function bootstrapAccount() {
    const version = ++accountVersion; account.loading = true; account.error = ''; account.checked = false; renderAccountGate();
    try {
      const session = await bridge.accountSession(); if (version !== accountVersion) return;
      if (!session || typeof session.portal !== 'boolean' || session.portal && typeof session.authenticated !== 'boolean') throw new Error('No se pudo comprobar tu acceso.');
      account.checked = true; account.actor = session.actor || null; account.portal = session.portal; account.authenticated = session.portal && session.authenticated; account.username = typeof session.username === 'string' ? session.username : ''; account.loading = false;
      if (account.portal) readInvitationFragment();
      accountChrome();
      if (accountLocked()) renderAccountGate(); else { document.getElementById('account-gate').innerHTML = ''; account.code = ''; fromHash(); connect(); }
    } catch (_) { if (version !== accountVersion) return; account.loading = false; account.error = 'No hemos podido comprobar tu acceso. Vuelve a intentarlo en un momento.'; renderAccountGate(); }
  }
  function clearAccountContent(keepNotifications = false) {
    connectVersion++; stopPolling(); clearLiveState(keepNotifications); sending.clear(); callbackBusy.clear(); serverState = { characters: [], wishes: [] }; actorKey = undefined;
    main.innerHTML = ''; document.getElementById('friend-nav').innerHTML = ''; document.getElementById('connection-banner').innerHTML = ''; document.getElementById('modal-content').innerHTML = ''; closeMenu();
  }
  function expireAccountSession() {
    if (!account.portal || !account.authenticated) return;
    accountVersion++; account.authenticated = false; account.loading = false; account.screen = 'login'; account.code = ''; account.error = 'Tu sesión ha terminado. Usa tu llave para volver a entrar.'; mode = 'offline'; clearAccountContent(); renderAccountGate();
  }
  async function submitAccount() {
    if (!account.portal || account.authenticated || account.loading) return;
    const username = document.getElementById('account-username').value.trim(), passwordInput = document.getElementById('account-password'), registering = account.screen === 'register';
    const body = { username, password: passwordInput.value }; if (registering) body.code = document.getElementById('account-code').value.trim();
    const version = ++accountVersion; account.loading = true; account.username = username; account.error = ''; account.code = registering ? body.code : account.code; passwordInput.value = ''; renderAccountGate();
    try {
      const result = await (registering ? bridge.accountRegister(body) : bridge.accountLogin(body));
      if (version !== accountVersion) return; if (result?.authenticated !== true || typeof result.username !== 'string') throw new Error('No se pudo confirmar el acceso.');
      account.authenticated = true; account.actor = result.actor || null; account.ownerInvite = false; account.username = result.username; account.code = ''; account.loading = false; account.error = ''; account.help = false; clearAccountContent(); accountChrome(); document.getElementById('account-gate').innerHTML = ''; view = 'home'; navigate('home'); connect();
    } catch (error) { if (version !== accountVersion) return; account.loading = false; account.error = error.uncertain && registering ? 'No pudimos confirmar la creación de tu llave. Prueba a entrar con el usuario y la contraseña que elegiste antes de activar otra invitación.' : error.message || 'No hemos podido abrir tu rincón. Vuelve a intentarlo.'; renderAccountGate(); }
    finally { body.password = ''; if ('code' in body) body.code = ''; }
  }
  async function logoutAccount() {
    if (!account.portal || account.loading) return;
    let cleanup; try { cleanup = notifications?.beforeLogout?.(); } catch (error) { cleanup = Promise.reject(error); }
    const version = ++accountVersion; account.loading = true; account.authenticated = false; account.code = ''; account.error = ''; account.screen = 'login'; mode = 'offline'; clearAccountContent(true); renderAccountGate();
    try { try { await cleanup; } catch (_) { /* Push cleanup must never keep the account signed in. */ } await bridge.accountLogout(); if (version !== accountVersion) return; account.username = ''; }
    catch (error) { if (version !== accountVersion) return; account.error = 'Tu rincón se ha cerrado aquí, pero no pudimos confirmar el cierre de tu sesión. Vuelve a pulsar «Cerrar sesión» antes de dejar este dispositivo.'; }
    finally { notifications?.reset?.(); if (version === accountVersion) { account.loading = false; renderAccountGate(); if (account.error) document.getElementById('account-error').insertAdjacentHTML('beforeend', '<button class="text-button" data-account-logout>Reintentar cerrar sesión</button>'); } }
  }
  function renderConnection() {
    const banner = document.getElementById('connection-banner'); let heading, copy, buttons;
    if (mode === 'live') { heading = 'La Casa Celestial te da la bienvenida'; copy = 'Tus amigos, tus historias y un lugar guardado para ti.'; buttons = !canExploreDemo() ? '' : '<button class="text-button" data-mode="demo">Explorar boceto</button>'; }
    else if (mode === 'demo') { heading = 'Estás explorando el boceto'; copy = 'Vista local de prueba. Ninguna de estas acciones sale del boceto.'; buttons = '<button class="text-button" data-mode="live">Volver a la Casa Celestial</button>'; }
    else if (mode === 'checking') { heading = 'Abriendo la puerta de la Casa Celestial…'; copy = 'Estamos preparando tu rincón. Un momentito, Patita.'; buttons = ''; }
    else { heading = 'La puerta necesita un momentito'; copy = connectionError || 'Ahora no podemos abrir tu rincón. Vuelve a intentarlo en un ratito.'; buttons = (connectionStatus === 401 && !account.portal ? '<a class="text-button" href="/signin-with-chatgpt?return_to=/" target="_top">Iniciar sesión</a>' : '<button class="text-button" data-mode="live">Volver a llamar</button>') + (!canExploreDemo() ? '' : '<button class="text-button" data-mode="demo">Explorar boceto</button>'); }
    banner.className = 'connection-banner ' + mode;
    banner.innerHTML = `<span class="connection-mark" aria-hidden="true">${mode === 'live' ? '✦' : '✧'}</span><div><strong>${esc(heading)}</strong><p>${esc(copy)}</p></div><div class="connection-actions">${buttons}</div>`;
    document.getElementById('about-demo').textContent = mode === 'demo' ? 'Boceto interactivo' : 'Sobre este rincón'; document.body.dataset.mode = mode;
    const controlNav = document.getElementById('control-nav'); controlNav.hidden = !canOpenControl(); controlNav.querySelector('span').textContent = mode === 'demo' ? 'Vista de Miguel' : 'Despacho del Castor';
  }
  function renderFriends() {
    const friends = document.getElementById('friend-nav'), html = orderedIds().map(id => `<button class="friend-link ${unreadCount(id) ? 'has-unread' : ''} ${['chat', 'clinic', 'consultation', 'vaca'].includes(view) && activeId === id ? 'active' : ''}" data-chat="${id}">${portrait(id, true)}<span class="friend-name">${esc(characters[id].name)}<small>${esc(unreadCount(id) ? 'Hay mensajes por leer' : status(id))}</small></span>${unreadCount(id) ? unreadBadge(unreadCount(id)) : `<span class="online-dot ${ready(id) && mode === 'live' ? '' : 'offline'}" aria-hidden="true"></span>`}</button>`).join('');
    if (friends.innerHTML !== html) friends.innerHTML = html;
    renderUnreadChrome();
  }
  function title(eyebrow, heading, text) { return `<div class="page-title"><div class="eyebrow">${icon('star')}${esc(eyebrow)}</div><h1>${esc(heading)}</h1><p>${esc(text)}</p></div>`; }
  function card(id) { return `<button class="character-card ${unreadCount(id) ? 'has-unread' : ''}" data-chat="${id}"><div class="portrait-wrap">${portrait(id)}${unreadBadge(unreadCount(id), 'card-unread')}</div><h3>${esc(characters[id].name)}</h3><p>${esc(details[id].short)}</p><span class="card-bottom">${esc(ready(id) ? (id === 'salchicher' ? 'Visitar el consultorio' : id === 'vaca' ? 'Charlar con la Vaca' : 'Entrar a charlar') : status(id))} ${icon('arrow')}</span></button>`; }
  function home() {
    return `${unreadOverview()}<section class="hero" aria-labelledby="welcome-title"><img class="hero-art" src="assets/casa-celestial-v2.png" alt="Castori, Mimosuga y la Vaca Mágica en una oficina iluminada dentro de un árbol"><div class="hero-content"><div class="eyebrow">${icon('star')} UN LUGAR HECHO DE CARIÑO</div><h1 id="welcome-title">Qué bien que estés<br>aquí, <em>Patita.</em></h1><p>Al otro lado hay una historia, un abrazo<br>y alguien con ganas de escucharte.</p><div class="hero-buttons"><button class="button" data-chat="mimosuga">¿Charlamos un ratito? ${icon('arrow')}</button><button class="text-button" id="discover-friends">Conocer a mis amigos</button></div></div><div class="hero-caption">${icon('heart')} Pasa. Estás en casa.</div></section><section id="our-friends"><div class="section-heading"><div><h2>¿Con quién te apetece hablar?</h2><p>Tu pequeño universo, con todas sus historias.</p></div><span class="aside-note">Siempre hay una silla para ti.</span></div><div class="character-grid">${orderedIds().map(card).join('')}</div></section><div class="below-home"><button class="story-feature" data-story="${stories[0].id}"><span class="mini-book">${icon('book')}</span><span><span class="eyebrow">UN CUENTO PARA TI</span><h3>${esc(stories[0].title)}</h3><p>Una historia de bienvenida, guardada para ti.</p></span>${icon('arrow')}</button><div class="daily-note"><span>✧</span><div><span class="eyebrow">UNA COSITA PARA RECORDAR</span><blockquote>Lo bonito también está<br>en los días normales.</blockquote></div></div></div>`;
  }
  function demoHistory(id) {
    if (id === 'corte') return [];
    if (!Array.isArray(state.chats[id])) state.chats[id] = [];
    if (state.chats[id].some(m => !m || typeof m.text !== 'string' || !['user', 'assistant'].includes(m.role))) state.chats[id] = state.chats[id].filter(m => m && typeof m.text === 'string' && ['user', 'assistant'].includes(m.role));
    if (!state.chats[id].length) state.chats[id].push({ id: `greeting-${id}`, role: 'assistant', text: characters[id].greeting, time: Date.now() });
    return state.chats[id];
  }
  const messageKey = message => String(message.event_id ?? message.id);
  function connectedHistory(id) {
    const current = new Map((liveChats[id] || []).map(message => [messageKey(message), message]));
    const combined = (archives[id]?.items || []).map(message => {
      const key = messageKey(message), latest = current.get(key); current.delete(key); return latest || message;
    });
    // Backend page order is authoritative for legacy messages with no timestamp.
    // Numeric event IDs let newer feed pages fit around archived events without text matching.
    for (const message of current.values()) {
      const position = combined.findIndex(existing => /^\d+$/.test(messageKey(existing)) && Number(messageKey(existing)) > Number(messageKey(message)));
      if (position < 0) combined.push(message); else combined.splice(position, 0, message);
    }
    return combined;
  }
  function chatHistory(id) { return mode === 'demo' ? demoHistory(id) : mode === 'live' ? connectedHistory(id) : []; }
  function conversations() {
    return title('Siempre cerquita', 'Una conversación, un pequeño refugio.', mode === 'demo' ? 'Conversaciones de ejemplo guardadas en este navegador.' : 'Abre una conversación para recibir sus mensajes y botones.') + unreadOverview() + orderedIds().map(id => { const last = chatHistory(id).at(-1); const text = last ? last.text : status(id); return `<button class="list-card ${unreadCount(id) ? 'has-unread' : ''}" data-chat="${id}">${portrait(id, true)}<span><h2>${esc(characters[id].name)} ${unreadBadge(unreadCount(id))}</h2><p>${esc(text.length > 110 ? text.slice(0, 110) + '…' : text)}</p></span>${icon('arrow')}</button>`; }).join('');
  }
  function messageButtons(message) {
    if (mode !== 'live' || !Array.isArray(message.buttons)) return '';
    return `<div class="message-buttons">${message.buttons.filter(Array.isArray).map(row => `<div>${row.filter(b => b && typeof b.text === 'string' && typeof b.data === 'string').map(b => `<button class="message-choice" data-callback-event="${esc(message.id)}" data-callback="${esc(b.data)}" ${readOnly() || deskChatVisible() || callbackBusy.has(message.id + ':' + b.data) || !ready(activeId) ? 'disabled' : ''}>${esc(b.text)}</button>`).join('')}</div>`).join('')}</div>`;
  }
  function formatTime(value) { if (value == null || value === '') return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('es-ES', { hour: '2-digit', minute: '2-digit' }).format(date); }
  function formatDate(value) { if (value == null || value === '') return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'long', year: 'numeric' }).format(date); }
  function historyControl(id) {
    if (mode !== 'live' || !ready(id) || id === 'salchicher') return '';
    const page = archives[id]; const session = id === 'salchicher' ? '<small>Solo la consulta activa, hasta 48 horas · Sin archivo permanente</small>' : '';
    let content;
    if (!page || page.loading && !page.items.length) content = '<span role="status">Abriendo los mensajes anteriores…</span>';
    else if (page.error) content = `<span role="status">${esc(page.error)}</span><button class="text-button" data-history="${id}">Reintentar</button>`;
    else if (page.hasMore) content = `<button class="history-button" data-history="${id}" ${page.loading ? 'disabled' : ''}>${page.loading ? 'Abriendo mensajes…' : 'Ver mensajes anteriores'}</button>`;
    else if (!page.available) content = `<span>${page.items.length ? 'Estos son los mensajes recuperados. El archivo anterior no está disponible.' : 'El historial anterior no está disponible para esta conversación.'}</span>`;
    else content = `<span>${page.items.length ? 'Has llegado al comienzo de los mensajes disponibles.' : id === 'salchicher' ? 'No hay mensajes anteriores en esta consulta.' : 'No hay mensajes anteriores guardados.'}</span>`;
    return `<div class="history-control">${content}${session}</div>`;
  }
  function renderMessages(id) {
    const messages = chatHistory(id).filter(m => id !== 'salchicher' || !m.consultation_id && m.role === 'assistant'); const label = mode === 'demo' ? 'CONVERSACIÓN DE DEMOSTRACIÓN' : (readOnly() ? 'CONVERSACIÓN DE PATITA CON ' : 'TU CONVERSACIÓN CON ') + characters[id].name.toUpperCase(); let empty = '';
    let previousDate = '', firstUnread = true;
    if (!messages.length) {
      const text = config(id)?.reason === 'owner_uses_centralita' && mode !== 'demo' ? 'Este personaje se atiende desde tu Centralita. La conversación de Patita permanece separada de tu sesión de administrador.' : !ready(id) ? (id === 'dulcimiel' ? 'Dulcimiel todavía está preparando su rincón. Su conversación estará disponible próximamente.' : mode === 'checking' ? 'Abriendo la puerta…' : 'Ahora no podemos abrir esta conversación. Vuelve a llamar en un ratito.') : readOnly() ? 'Los mensajes de Patita y de este amigo aparecerán aquí. Puedes escribir como el animal desde el Despacho del Castor.' : id === 'salchicher' ? 'El consultorio de cuento guarda tus preguntas y las recetas de mimos de Salchicher.' : id === 'castori' ? 'Deja tu mensaje en la oficina. Castori la leerá en cuanto llegue su turno.' : id === 'corte' ? 'Presenta una acusación de cuento. Los siguientes pasos aparecerán aquí.' : 'Escribe cuando quieras. Los mensajes de esta conversación aparecerán aquí.';
      empty = `<div class="chat-empty">${icon(id === 'corte' ? 'star' : 'chat')}<p>${esc(text)}</p></div>`;
    }
    return historyControl(id) + `<div class="chat-date">UN RATITO PARA TI · ${esc(label)}</div>` + empty + messages.map(m => {
      const assistant = m.role !== 'user', unread = isUnreadMessage(id, m, m.consultation_id || null);
      const divider = unread && firstUnread ? '<div class="unread-divider" role="separator"><span>Mensajes nuevos desde aquí</span></div>' : ''; if (unread) firstUnread = false;
      const saved = state.memories.some(x => x.messageId === m.id);
      const date = formatDate(m.time), separator = mode === 'live' && date && date !== previousDate ? `<div class="message-date">${esc(date)}</div>` : ''; previousDate = date;
      return separator + divider + `<div class="message-row ${assistant ? '' : 'user'} ${unread ? 'message-unread' : ''}">${assistant ? portrait(id, true) : ''}<div class="message-content"><div class="message">${esc(m.text)}</div>${messageButtons(m)}<div class="message-meta">${assistant ? esc(characters[id].name) : readOnly() ? 'Patita' : 'Tú'}${formatTime(m.time) ? ' · ' + formatTime(m.time) : ''}${mode === 'demo' && assistant ? `<button class="${saved ? 'saved' : ''}" data-save-message="${esc(m.id)}" aria-label="${saved ? 'Quitar de' : 'Guardar en'} mis recuerdos del boceto" aria-pressed="${saved}">${icon('heart')}</button>` : ''}</div></div></div>`;
    }).join('') + (mode === 'demo' && pending.has(id) ? `<div class="message-row">${portrait(id, true)}<div class="message"><div class="typing" role="status" aria-label="Preparando una respuesta de ejemplo"><span></span><span></span><span></span></div></div></div>` : '');
  }
  function chatActions(id) {
    if (readOnly()) return '';
    if (mode === 'demo') return characters[id].suggestions.map(s => `<button class="suggestion" data-suggestion="${esc(s)}">${esc(s)}</button>`).join('');
    const whispers = id === 'vaca' ? ['¿Me susurras una profecía?', '¿Qué dice tu campanilla?'].map(s => `<button class="suggestion" data-suggestion="${esc(s)}" ${ready(id) ? '' : 'disabled'}>${esc(s)}</button>`).join('') : '';
    return whispers + actions[id].map(a => `<button class="suggestion" data-command="${a.command}" ${a.compose ? 'data-compose="true"' : ''} ${canCommand(id, a.command) ? '' : 'disabled'}>${esc(a.label)}</button>`).join('');
  }
  function deliveryNote(id) { const note = deliveryNotes[id]; return note && mode === 'live' ? `<span>${esc(note.text)}</span>${note.requestId && note.check ? `<button class="text-button" data-check-request="${esc(note.requestId)}">Comprobar envío</button>` : ''}` : ''; }
  function chat(id) {
    const c = characters[id], disabled = !ready(id) || readOnly();
    const intro = id === 'vaca' ? `<section class="vaca-chat-intro"><span class="vaca-chat-spark" aria-hidden="true">✧</span><div><div class="eyebrow">EL RINCÓN DE LOS SECRETOS A MEDIAS</div><h2>Un muuu, una pista.<br><em>Y tú, intentando adivinar.</em></h2><p>Aquí llegan sus cartas, sus profecías y esos susurros que hacen cosquillas de ilusión. Puedes contestarle, preguntar y seguirle el juego.</p></div><button class="button secondary" data-view="wishes">${icon('star')} Mi cuaderno de deseos</button></section>` : '';
    const note = readOnly() ? 'Cuaderno de Patita · Solo lectura. Puedes escribir como un animal desde el Despacho del Castor.' : mode === 'demo' ? 'Respuestas de ejemplo · Esta conversación se guarda solo en este navegador.' : id === 'salchicher' ? 'El cuaderno de los patos está abierto. Vamos pasito a pasito.' : id === 'castori' ? 'Tu carta espera su turno en la mesa de Castori.' : 'Un ratito para hablar, sin ninguna prisa.';
    return intro + `<div class="chat-layout"><section class="chat-panel" aria-label="Conversación con ${esc(c.name)}"><header class="chat-header">${portrait(id, true)}<div><h1>${esc(c.name)}</h1><p>${esc(status(id))}</p></div><button class="icon-button" id="chat-info" aria-label="Acerca de esta conversación">${icon('star')}</button></header><div class="chat-messages" id="chat-messages" role="log" aria-label="Mensajes" aria-live="polite" aria-relevant="additions text">${renderMessages(id)}</div><div class="chat-suggestions">${chatActions(id)}</div><div class="delivery-status" id="delivery-status" role="status">${deliveryNote(id)}</div><div class="composer-wrap"><form class="composer" id="chat-form"><textarea id="chat-input" rows="1" maxlength="4000" aria-label="Escribe a ${esc(c.name)}" placeholder="${readOnly() ? 'Vista de Patita · solo lectura' : disabled ? esc(id === 'dulcimiel' ? 'Próximamente…' : 'Un momentito…') : 'Cuéntame, Patita…'}" ${disabled ? 'disabled' : ''} required></textarea><button class="send-button" aria-label="Enviar mensaje" ${disabled || pending.has(id) || sending.has(id) ? 'disabled' : ''}>${icon('send')}</button></form><p class="composer-note">${esc(note)}</p>${readOnly() ? `<button class="text-button" data-desk-animal="${id}">Abrir en el Despacho del Castor →</button>` : ''}</div></section><aside class="companion-panel"><div class="companion-portrait">${portrait(id)}</div><div class="eyebrow" style="justify-content:center">TU COMPAÑÍA DE HOY</div><h2>${esc(c.name)}</h2><p>${esc(details[id].description)}</p><blockquote class="companion-quote">«${esc(details[id].quote)}»</blockquote><button class="button secondary" data-view="${id === 'vaca' ? 'wishes' : 'library'}">${icon(id === 'vaca' ? 'star' : 'book')}${id === 'vaca' ? 'Mi cuaderno de ilusiones' : 'Visitar la biblioteca'}</button><button class="text-button" data-view="conversations">Visitar a otro amigo</button></aside></div>`;
  }
  function library() {
    const samples = `<div class="library-grid">${stories.map((s, i) => `<button class="book-card" data-story="${s.id}"><div class="book-art"><span class="mini-book">${icon(i === 0 ? 'heart' : i === 1 ? 'star' : 'moon')}</span></div><div class="book-info"><span class="eyebrow">CUENTO DE BIENVENIDA</span><h2>${esc(s.title)}</h2><p>Un pequeño cuento · 2 minutos de calma</p><span class="text-button">Abrir el cuento →</span></div></button>`).join('')}</div>`;
    const heading = title('Historias con un lugar para ti', 'La biblioteca de las cosas bonitas.', mode === 'demo' ? 'Tres cuentos de muestra para explorar este rincón.' : 'Vuelve a los cuentos que Mimosuga ya ha compartido contigo.');
    if (mode === 'demo') return heading + samples;
    const connected = mode === 'live' ? `<div class="library-live"><div><h2>Un cuento nuevo de Mimosuga</h2><p>Cada historia entregada tiene aquí su pequeño lugar, para volver a leerla entera.</p></div><button class="button" data-chat="mimosuga">Hablar con Mimosuga ${icon('arrow')}</button></div><section id="story-shelf" aria-label="Tus cuentos de Mimosuga">${renderStoryShelf()}</section>` : `<div class="empty-state">${icon('book')}<h2>${mode === 'checking' ? 'Abriendo tu biblioteca…' : 'Tus cuentos te esperan.'}</h2><p>No podemos abrir tu estantería ahora mismo. Vuelve a intentarlo en un ratito.</p>${mode === 'checking' ? '' : '<button class="button" data-mode="live">Volver a llamar</button>'}</div>`;
    return heading + connected + `<details class="sample-library"><summary>La repisa de bienvenida <span>Tres historias para empezar</span></summary><p>Tres cuentos que siempre te esperan junto a la puerta, además de las historias que Mimosuga ha compartido contigo.</p>${samples}</details>`;
  }
  function renderStoryShelf() {
    const page = storyShelf;
    const cards = page.items.map(story => `<button class="delivered-story" data-live-story="${esc(story.id)}"><span class="story-spine" aria-hidden="true">${icon('book')}</span><span class="delivered-story-copy"><span class="eyebrow">${esc(story.narrator || 'Mimosuga')}</span><h2>${esc(story.title)}</h2><span class="story-date">${esc(formatDate(story.delivered_at || story.created_at) || 'Fecha no disponible')}</span>${story.excerpt ? `<p>${esc(story.excerpt)}</p>` : ''}<span class="text-button">Volver a leer el cuento ${icon('arrow')}</span></span></button>`).join('');
    let status = '';
    if (page.error) status = `<div class="archive-notice error" role="status"><h3>No hemos podido abrir la biblioteca.</h3><p>${esc(page.error)}</p><button class="button secondary" data-load-stories>Reintentar</button></div>`;
    else if (page.loading || !page.loaded) status = '<div class="archive-notice" role="status"><span class="library-spark" aria-hidden="true">✧</span><p>Buscando tus cuentos en la estantería…</p></div>';
    else if (!page.available) status = '<div class="archive-notice" role="status"><h3>El archivo de cuentos aún no está disponible.</h3><p>No podemos comprobar tu biblioteca en este momento.</p><button class="button secondary" data-load-stories>Volver a comprobar</button></div>';
    else if (!page.items.length) status = '<div class="archive-notice"><span class="library-spark" aria-hidden="true">✧</span><h3>El primer cuento tendrá un lugar aquí.</h3><p>Todavía no hay cuentos entregados en tu biblioteca. Puedes pedirle uno a Mimosuga.</p><button class="button secondary" data-chat="mimosuga">Visitar a Mimosuga</button></div>';
    else if (page.hasMore) status = '<div class="archive-pagination"><button class="button secondary" data-load-stories>Ver más cuentos</button></div>';
    else status = '<p class="archive-end">Estos son todos los cuentos disponibles en tu biblioteca.</p>';
    return `<div class="delivered-stories">${cards}</div>` + status;
  }
  function refreshLibrary() { if (mode === 'live' && view === 'library') document.getElementById('story-shelf').innerHTML = renderStoryShelf(); }
  function cancelPage(page) { if (!page) return; page.version++; page.controller?.abort(); page.controller = null; page.loading = false; }
  function cancelStory() { storyVersion++; storyController?.abort(); storyController = null; }
  function cancelArchiveReads() { Object.values(archives).forEach(cancelPage); cancelPage(storyShelf); cancelStory(); }
  function clearHistory(id) { cancelPage(archives[id]); delete archives[id]; if (id === 'vaca') experiences?.clearLetters(); }
  function archiveAccessError(error) {
    if (error.status !== 401 && error.status !== 403) return false;
    clearLiveState(); mode = 'offline'; connectionError = error.message; connectionStatus = error.status; navigate(view, activeId, false); return true;
  }
  async function loadHistory(id) {
    if (mode !== 'live' || !ready(id) || id === 'salchicher') return;
    const page = archives[id] ||= newPage(); if (page.loading || page.loaded && !page.hasMore && !page.error) return;
    const epoch = liveEpoch, version = ++page.version, first = !page.loaded;
    page.controller = new AbortController(); page.loading = true; page.error = ''; if (chatVisible(id)) refreshChat();
    try {
      const data = await bridge.history(id, first ? null : page.nextCursor, page.controller.signal);
      if (epoch !== liveEpoch || version !== page.version || mode !== 'live') return;
      if (!Array.isArray(data?.messages)) throw new Error('No se pudieron recuperar los mensajes anteriores.');
      const incoming = data.messages.filter(m => m && m.animal === id && m.id != null && ['user', 'assistant'].includes(m.role) && typeof m.text === 'string');
      const existing = new Map(page.items.map(m => [messageKey(m), m]));
      const added = [];
      for (const message of incoming) { const key = messageKey(message); if (!existing.has(key)) { existing.set(key, message); added.push(message); } }
      page.items = added.concat(page.items); page.loaded = true; page.available = data.archive_available !== false;
      page.hasMore = Boolean(data.has_more && data.next_cursor != null); page.nextCursor = data.next_cursor ?? null;
      page.loading = false; page.controller = null;
      if (chatVisible(id)) refreshChat(first, !first);
    } catch (error) {
      if (epoch !== liveEpoch || version !== page.version || error.cancelled) return;
      page.loading = false; page.controller = null; if (archiveAccessError(error)) return;
      page.error = error.message || 'No se pudieron recuperar los mensajes anteriores.';
      if (chatVisible(id)) refreshChat();
    }
  }
  async function loadStories(restart = false) {
    if (mode !== 'live') return;
    const page = storyShelf; if (page.loading) return;
    const epoch = liveEpoch, version = ++page.version, first = restart || !page.loaded || !page.available || Boolean(page.error && page.retryFirst);
    page.retryFirst = first;
    page.controller = new AbortController(); page.loading = true; page.error = ''; refreshLibrary();
    try {
      const data = await bridge.stories(first ? null : page.nextCursor, page.controller.signal);
      if (epoch !== liveEpoch || version !== page.version || mode !== 'live') return;
      if (!Array.isArray(data?.stories)) throw new Error('No se pudieron recuperar tus cuentos.');
      const byId = new Map((first ? [] : page.items).map(s => [String(s.id), s]));
      for (const story of data.stories) if (story && story.id != null && typeof story.title === 'string' && story.delivered_at) byId.set(String(story.id), story);
      page.items = [...byId.values()]; page.loaded = true; page.available = data.archive_available !== false;
      page.hasMore = Boolean(data.has_more && data.next_cursor != null); page.nextCursor = data.next_cursor ?? null;
    } catch (error) {
      if (epoch !== liveEpoch || version !== page.version || error.cancelled) return;
      if (archiveAccessError(error)) return;
      page.error = error.message || 'No se pudieron recuperar tus cuentos.';
    } finally { if (epoch === liveEpoch && version === page.version) { page.loading = false; page.controller = null; refreshLibrary(); } }
  }
  const adminHelp = {
    start: ['', 'Ayuda completa de la Centralita'], status: ['', 'Estado general de los bots'],
    castori: ['mensaje', 'Enviar a Sandra como Oficina Castori'], mimosuga: ['mensaje', 'Enviar a Sandra como Mimosuga'], salchicher: ['mensaje', 'Enviar a Sandra como Salchicher'], vaca: ['mensaje', 'Enviar a Sandra como la Vaca'], corte: ['mensaje', 'Enviar a Sandra como la Corte'],
    historial: ['animal [cantidad]', 'Consultar el historial de un animal'], programar: ['animal lunes|DD/MM/AAAA HH:MM mensaje', 'Crear una programación'], programados: ['', 'Consultar las programaciones'], cancelar: ['ID', 'Cancelar una programación'], pausar_programas: ['', 'Pausar programaciones y visitas'], reanudar_programas: ['', 'Reanudar programaciones y visitas'],
    mimosuga_auto: ['on|off|auto|revision', 'Elegir cómo responde Mimosuga'], salchicher_auto: ['on|off', 'Activar o pausar a Salchicher'], vaca_auto: ['on|off|status', 'Activar o pausar la conversación de la Vaca'], mimosuga_pendientes: ['[ID]', 'Abrir borradores con sus botones de revisión'],
    admin_ultimos: ['', 'Consultar los últimos cuentos'], admin_ver: ['ID', 'Leer un cuento completo'], admin_aprobar: ['ID', 'Aprobar un cuento'], admin_descartar: ['ID', 'Descartar un cuento'], admin_canon: ['ID', 'Incorporar un cuento al canon'], admin_lore: ['', 'Consultar el lore'], admin_memoria_cuentos: ['', 'Consultar la memoria de cuentos'], admin_cuento_prueba: ['mimosuga', 'Generar una prueba privada, sin entrega a Sandra'],
    vaca_ayuda: ['', 'Ayuda privada de la Vaca'], vaca_deseos: ['', 'Abrir el cuaderno de deseos de Sandra'], vaca_visita: ['DD/MM/AAAA HH:MM | regalos', 'Preparar una visita privada'], vaca_visitas: ['[ID]', 'Revisar las visitas'], vaca_texto: ['ID pista1|pista2|manana | texto', 'Editar el texto de una visita'], vaca_hora: ['ID evento DD/MM/AAAA HH:MM', 'Editar la hora de una pista'], vaca_fecha: ['ID DD/MM/AAAA HH:MM', 'Cambiar la fecha de entrega'], vaca_activar: ['ID', 'Activar los envíos revisados de una visita'], vaca_cancelar: ['ID', 'Cancelar una visita'], vaca_pausa: ['on|off', 'Pausar o reanudar visitas'],
    acusar: ['hechos', 'Abrir un caso en la Corte'], alegar: ['texto', 'Presentar una alegación'], caso_estado: ['', 'Consultar el caso activo']
  };
  function demoControlData() {
    return { available: true, actor: 'owner', commands: Object.keys(adminHelp), database_available: true, admin_identity_matches: true, timezone: 'Europe/Madrid', animals: ids.filter(id => id !== 'dulcimiel').map(id => ({ id, name: characters[id].name, available: true, linked: true })),
      automation: { schedules_paused: false, mimosuga_enabled: true, mimosuga_mode: 'review', salchicher_enabled: true, vaca_enabled: true, vaca_visits_paused: false }, counts: { stories_total: 12, stories_pending: 2, stories_canon: 4, auto_reply_pending: 1, schedules_active: 1, visits_active: 1, court_cases_active: 0 },
      schedules: [{ id: 'ejemplo-1', animal: 'mimosuga', text: 'Un abrazo de abuela para empezar la semana.', kind: 'weekly', day: 0, time: '09:00', sent: false }],
      stories: [{ id: 'ejemplo-cuento', title: 'El paraguas de las nubes pequeñas', narrator: 'Mimosuga', status: 'pending', created_at: '2026-10-20T16:00:00Z' }],
      drafts: [{ id: 'ejemplo-borrador', animal: 'mimosuga', incoming_text: 'Hoy me apetece una historia de lluvia.', proposed_text: 'Ven, Patita. La abuela tiene una taza calentita y un cuento que empieza con tres gotas.', status: 'pending', created_at: '2026-10-20T17:00:00Z' }],
      visits: [{ id: 'ejemplo-visita', status: 'draft', gifts: 'Un cuaderno y una tarde de merienda · ejemplo ficticio', delivery_at: '2026-12-24T08:00:00Z', events: [{ id: 'pista1', at: '2026-12-21T17:00:00Z', text: 'Hay una sorpresa de papel esperando su momento.', status: 'pending' }] }],
      wishes: [{ id: 'ejemplo-deseo', name: 'Un cuaderno color lavanda', details: 'Deseo ficticio de la vista de Miguel', favorite: true }], court: null, errors: [] };
  }
  const controlData = () => mode === 'demo' ? demoControlData() : canUseControl() ? admin.data : null;
  const controlEvents = () => mode === 'demo' ? demoAdminEvents : canUseControl() ? admin.events : [];
  function adminCommandAllowed(text) {
    if (!canUseControl()) return false;
    const command = String(text).trim().split(/\s/)[0].replace(/^\//, '').toLowerCase(), data = controlData();
    return Boolean(data?.available && Array.isArray(data.commands) && data.commands.includes(command) && !(command.startsWith('admin_') && (data.admin_identity_matches === false || data.editorial_admin?.available === false)));
  }
  function adminButton(label, command, strong = false, confirmed = false) { return `<button class="${strong ? 'button' : 'admin-action-button'}" data-admin-command="${esc(command)}" ${confirmed ? 'data-admin-confirmed="true"' : ''} ${adminCommandAllowed(command) && !(mode === 'live' && (admin.busy || admin.check)) ? '' : 'disabled'}>${esc(label)}</button>`; }
  const adminEmpty = text => `<p class="admin-empty">${esc(text)}</p>`;
  function adminDate(value) { if (!value) return 'Sin fecha disponible'; const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Sin fecha disponible' : new Intl.DateTimeFormat('es-ES', { timeZone: controlData()?.timezone || 'Europe/Madrid', dateStyle: 'long', timeStyle: 'short' }).format(date); }
  const adminStatus = value => ({ pending: 'Pendiente', approved: 'Aprobado', rejected: 'Descartado', canon: 'Canon', draft: 'Borrador', active: 'Activa', cancelled: 'Cancelada', sent: 'Enviado', done: 'Completado', open: 'Abierto', review: 'Con revisión', auto: 'Automático' }[value] || value || 'Sin estado');
  function renderAdminLock() {
    const portal = account.portal && isOwner(), setup = !portal && adminAuth.checked && !adminAuth.configured;
    const waiting = !adminAuth.checked || adminAuth.revocationPending;
    const form = waiting ? `<div class="admin-lock-wait" role="status"><p>${adminAuth.loading ? 'Cerrando la puerta antes de comprobar tu llave…' : 'Comprueba el cierre del escritorio para volver a entrar.'}</p>${adminAuth.loading || adminAuth.revocationPending ? '' : '<button class="button" data-admin-auth-refresh>Comprobar acceso</button>'}</div>` : `<form id="admin-auth-form" class="admin-lock-form"><label>${portal ? 'La misma contraseña de tu cuenta' : setup ? 'Elige tu contraseña' : 'Contraseña del Despacho'}<input id="admin-auth-password" name="password" type="password" autocomplete="${setup ? 'new-password' : 'current-password'}" maxlength="128" required placeholder="Tu llave secreta" ${adminAuth.loading ? 'disabled' : ''}></label>${setup ? '<label>Repite la contraseña<input id="admin-auth-confirm" name="confirmation" type="password" autocomplete="new-password" maxlength="128" required placeholder="La misma llave, una vez más"></label><p class="admin-lock-hint">Elige la contraseña que prefieras. Guárdala en tu gestor de contraseñas.</p>' : ''}<button class="button" type="submit" ${adminAuth.loading ? 'disabled' : ''}>${adminAuth.loading ? 'Comprobando tu llave…' : setup ? 'Guardar mi contraseña y entrar' : 'Abrir el Despacho del Castor'} ${icon('arrow')}</button></form>`;
    return `<section class="admin-lock" aria-labelledby="admin-lock-title"><div class="admin-lock-art" aria-hidden="true"><span class="admin-lock-orbit">✧</span><div class="admin-lock-seal">${icon('key')}</div><span class="admin-lock-signature">despacho del castor</span></div><div class="admin-lock-content"><span class="eyebrow">EL ESCRITORIO PRIVADO DE MIGUEL</span><h1 id="admin-lock-title">La llave de<br><em>tu Despacho.</em></h1><p class="admin-lock-intro">${portal ? 'Vuelve a escribir la contraseña con la que entras en la Casa Celestial para abrir tu mesa de trabajo.' : setup ? 'Elige una contraseña para cuidar las historias, los mensajes y las sorpresas que preparas para Sandra.' : 'Un pequeño secreto para entrar donde se preparan las cosas bonitas.'}</p>${adminAuth.error ? `<p class="account-error" role="alert">${esc(adminAuth.error)}</p>` : ''}${adminAuth.revocationPending && !adminAuth.loading ? '<button class="button secondary admin-lock-retry" data-admin-lock>Reintentar cierre</button>' : ''}${form}<p class="admin-lock-footnote">${icon('key')} ${portal ? 'Usa la contraseña de tu cuenta. El Despacho se cierra al salir y, como máximo, a los 30 minutos. Tu sesión en la Casa permanece abierta.' : 'Tu acceso de ChatGPT y esta contraseña protegen el escritorio. Se cierra automáticamente a los 30 minutos.'}</p></div></section>`;
  }
  function refreshAdminGate() {
    if (view !== 'control' || !canOpenControl()) return;
    main.innerHTML = control(); bindControl();
  }
  function clearAdminAuth() {
    adminAuth.version++; adminAuth.controller?.abort(); clearTimeout(adminAuth.timer);
    Object.assign(adminAuth, { portalPrepared: false, checked: false, configured: false, unlocked: false, expiresAt: null, loading: false, error: '', controller: null, timer: null, requirePassword: false, revocationPending: false });
  }
  function closeAdminGate(message = '') {
    adminAuth.version++; adminAuth.controller?.abort(); clearTimeout(adminAuth.timer);
    Object.assign(adminAuth, { unlocked: false, expiresAt: null, loading: false, error: message, controller: null, timer: null, requirePassword: true });
    if (view === 'control') stopPolling(); clearAdminState(); refreshAdminGate();
  }
  function adminAccessError(error) {
    if (error.status !== 423 && error.code !== 'admin_locked') return false;
    closeAdminGate('Tu Centralita se ha cerrado. Introduce tu contraseña para continuar.'); return true;
  }
  function applyAdminAuth(data, verified = false) {
    if (typeof data?.configured !== 'boolean' || typeof data.unlocked !== 'boolean') throw new Error('No se pudo comprobar la llave de tu Centralita.');
    const expires = Date.parse(data.expires_at);
    if (data.unlocked && (!data.configured || !Number.isFinite(expires) || expires <= Date.now())) throw new Error('La sesión de tu Centralita ha caducado. Vuelve a introducir tu contraseña.');
    if (account.portal && (data.reauthenticate !== true || data.configured !== true)) throw new Error('No se pudo comprobar el acceso al Despacho.');
    const unlocked = data.unlocked && !adminAuth.requirePassword && (!account.portal || verified);
    Object.assign(adminAuth, { checked: true, configured: data.configured, unlocked, expiresAt: unlocked ? data.expires_at : null });
    clearTimeout(adminAuth.timer);
    if (unlocked) {
      const version = adminAuth.version;
      adminAuth.timer = setTimeout(() => { if (version !== adminAuth.version) return; closeAdminGate('Han pasado 30 minutos. Tu escritorio vuelve a estar cerrado.'); }, Math.min(expires - Date.now(), 2147483647));
    } else clearAdminState();
  }
  function openAdminDesk() {
    refreshAdminGate();
    if (view === 'control' && canUseControl() && mode === 'live') { loadAdminState(); startAdminPolling(); }
  }
  async function loadAdminAuth() {
    if (!canOpenControl() || mode !== 'live' || adminAuth.loading) return;
    if (account.portal && (!adminAuth.portalPrepared || adminAuth.revocationPending)) return lockPortalDesk();
    const epoch = liveEpoch, version = ++adminAuth.version; adminAuth.loading = true; adminAuth.error = ''; adminAuth.controller = new AbortController(); refreshAdminGate();
    try {
      const data = await bridge.adminAuth(adminAuth.controller.signal);
      if (epoch !== liveEpoch || version !== adminAuth.version || !canOpenControl() || mode !== 'live') return;
      applyAdminAuth(data);
    } catch (error) {
      if (epoch !== liveEpoch || version !== adminAuth.version || error.cancelled) return;
      if (account.portal && error.code === 'sign_in_required') { expireAccountSession(); return; }
      if (account.portal) adminAuth.requirePassword = true;
      adminAuth.unlocked = false; adminAuth.expiresAt = null; clearAdminState(); adminAuth.error = error.message || 'No se pudo comprobar el acceso.';
    } finally { if (epoch === liveEpoch && version === adminAuth.version) { adminAuth.loading = false; adminAuth.controller = null; openAdminDesk(); } }
  }
  async function submitAdminAuth() {
    if (!canOpenControl() || mode !== 'live' || adminAuth.loading || adminAuth.revocationPending || !adminAuth.checked || canUseControl()) return;
    const input = document.getElementById('admin-auth-password'), confirmation = document.getElementById('admin-auth-confirm');
    const password = input?.value || '', setup = !account.portal && !adminAuth.configured;
    if (!password.length || password.length > 128) { adminAuth.error = 'Escribe una contraseña de hasta 128 caracteres.'; refreshAdminGate(); return; }
    if (setup && password !== confirmation?.value) { adminAuth.error = 'Las dos contraseñas deben ser iguales.'; refreshAdminGate(); return; }
    if (input) input.value = ''; if (confirmation) confirmation.value = '';
    const epoch = liveEpoch, version = ++adminAuth.version; adminAuth.loading = true; adminAuth.error = ''; adminAuth.controller = new AbortController(); refreshAdminGate();
    try {
      const body = { action: setup ? 'setup' : 'unlock', password };
      const data = await (account.portal ? queuePortalAuth(body, epoch) : bridge.adminAuthAction(body, adminAuth.controller.signal));
      if (epoch !== liveEpoch || version !== adminAuth.version || !canOpenControl() || mode !== 'live') return;
      adminAuth.requirePassword = false; adminAuth.revocationPending = false; applyAdminAuth(data, true);
      if (!adminAuth.unlocked) throw new Error('No se pudo abrir la Centralita. Vuelve a comprobar tu llave.');
    } catch (error) {
      if (epoch !== liveEpoch || version !== adminAuth.version || error.cancelled) return;
      if (account.portal && error.code === 'sign_in_required') { expireAccountSession(); return; }
      if (account.portal) adminAuth.requirePassword = true;
      adminAuth.unlocked = false; adminAuth.expiresAt = null; clearAdminState();
      if (error.code === 'admin_already_configured') { adminAuth.checked = true; adminAuth.configured = true; }
      if (error.code === 'admin_setup_required') { adminAuth.checked = true; adminAuth.configured = false; }
      adminAuth.error = ['invalid_admin_password', 'invalid_credentials'].includes(error.code) ? 'La contraseña no coincide. Prueba de nuevo.' : error.uncertain ? 'No pudimos confirmar la apertura. Comprueba el acceso antes de volver a intentarlo.' : error.message;
      if (error.uncertain) { adminAuth.checked = false; if (account.portal) { adminAuth.portalPrepared = false; adminAuth.revocationPending = true; } }
    } finally { if (epoch === liveEpoch && version === adminAuth.version) { adminAuth.loading = false; adminAuth.controller = null; openAdminDesk(); } }
  }
  function queuePortalAuth(body, epoch) {
    const operation = portalAuthQueue.catch(() => {}).then(() => {
      if (epoch !== liveEpoch || !account.portal || !isOwner()) throw Object.assign(new Error('La sesión ha cambiado.'), { cancelled: true });
      return bridge.adminAuthAction(body);
    });
    portalAuthQueue = operation.catch(() => {});
    return operation;
  }
  async function lockPortalDesk() {
    if (!account.portal || !isOwner() || mode !== 'live') return;
    closeAdminGate(); const epoch = liveEpoch, version = adminAuth.version;
    Object.assign(adminAuth, { portalPrepared: false, checked: false, configured: true, loading: true, revocationPending: true }); refreshAdminGate();
    try {
      const data = await queuePortalAuth({ action: 'lock' }, epoch);
      if (epoch !== liveEpoch || version !== adminAuth.version) return;
      if (data?.unlocked !== false || data?.configured !== true || data?.reauthenticate !== true) throw new Error('No se pudo confirmar el cierre.');
      Object.assign(adminAuth, { portalPrepared: true, checked: true, configured: true, revocationPending: false });
    } catch (error) {
      if (epoch !== liveEpoch || version !== adminAuth.version) return;
      if (error.code === 'sign_in_required') { expireAccountSession(); return; }
      adminAuth.error = 'El escritorio está oculto, pero no pudimos confirmar su cierre en el servidor. Reintenta el cierre para volver a entrar.';
    } finally { if (epoch === liveEpoch && version === adminAuth.version) { adminAuth.loading = false; refreshAdminGate(); } }
  }
  async function lockAdmin() {
    if (account.portal && isOwner()) { if (adminAuth.revocationPending) return lockPortalDesk(); const closing = lockPortalDesk(); navigate('home'); return closing; }
    if (!canOpenControl() || mode !== 'live') return;
    closeAdminGate(); const epoch = liveEpoch, version = adminAuth.version;
    adminAuth.loading = true; adminAuth.revocationPending = true; refreshAdminGate();
    try {
      const data = await bridge.adminAuthAction({ action: 'lock' });
      if (epoch !== liveEpoch || version !== adminAuth.version) return;
      if (data?.unlocked !== false) throw new Error('No se pudo confirmar el cierre.');
      adminAuth.revocationPending = false;
      if (typeof data.configured === 'boolean') { adminAuth.checked = true; adminAuth.configured = data.configured; }
    } catch (_) {
      if (epoch !== liveEpoch || version !== adminAuth.version) return;
      adminAuth.error = 'El escritorio está oculto, pero no pudimos confirmar el cierre en el servidor. Vuelve a intentar cerrarlo antes de dejar este dispositivo.';
    } finally { if (epoch === liveEpoch && version === adminAuth.version) { adminAuth.loading = false; refreshAdminGate(); } }
  }
  function control() {
    if (!canOpenControl()) return title('Un rincón privado', 'Esta mesa está reservada.', mode === 'checking' ? 'Castori está comprobando tu llave.' : 'Castori guarda aquí sus papeles de oficina.') + `<div class="empty-state">${icon('star')}<p>Las conversaciones de Patita siguen en su propio rincón.</p><button class="button" data-view="home">Volver a mi rincón</button></div>`;
    if (!canUseControl()) return renderAdminLock();
    const tabs = [['overview', 'Un vistazo'], ['chats', 'Conversaciones'], ['send', 'Mensajes y horarios'], ['stories', 'Cuentos y borradores'], ['vaca', 'La Vaca Mágica'], ['court', 'Corte y memoria'], ['access', 'Las llaves de la Casa']];
    return `<section class="control-hero"><div><div class="eyebrow">${icon('star')}${mode === 'demo' ? 'VISTA DE MIGUEL · DATOS FICTICIOS' : 'EL ESCRITORIO PRIVADO DE MIGUEL'}</div><h1>Detrás de cada poquito<br>de magia, <em>estás tú.</em></h1><p>Cuida las historias, prepara las sorpresas y acompaña a cada animal desde un solo lugar.</p></div><div class="control-seal" aria-hidden="true"><span>✦</span><small>despacho<br>del castor</small></div></section><div class="control-topline"><span>${mode === 'demo' ? 'Demostración local · Ninguna acción se envía a Telegram ni a Sandra.' : 'Los mismos servicios de Telegram · Solo tú puedes abrir este escritorio.'}</span><div class="control-topline-actions"><button class="text-button" data-admin-refresh>Actualizar estado ${icon('arrow')}</button>${mode === 'live' ? '<button class="button secondary admin-lock-button" data-admin-lock>Salir del Despacho</button>' : ''}</div></div><div id="admin-summary">${renderAdminSummary()}</div><nav class="control-tabs" aria-label="Secciones del Despacho del Castor">${tabs.map(([id, label]) => `<button data-admin-tab="${id}" class="${adminTab === id ? 'active' : ''}" aria-pressed="${adminTab === id}">${label}</button>`).join('')}</nav><div id="admin-panel">${renderAdminPanel()}</div><section class="admin-console" aria-label="Consola del Despacho del Castor"><div class="section-heading"><div><span class="eyebrow">EL CUADERNO DE MANDO</span><h2>El cuaderno de mando del Castor.</h2><p>Las respuestas y sus botones aparecen aquí. También puedes usar cualquier comando disponible.</p></div>${adminButton('Ayuda de Telegram', '/start')}</div><div id="admin-feed" class="admin-feed" role="log" aria-live="polite">${renderAdminEvents()}</div><div id="admin-delivery" class="admin-delivery" role="status">${renderAdminDelivery()}</div><form id="admin-console-form" class="admin-console-form"><label class="sr-only" for="admin-command-input">Comando del Despacho del Castor</label><input id="admin-command-input" name="command" placeholder="/status, /historial mimosuga 10…" maxlength="4000" autocomplete="off" required><button class="button" type="submit" ${mode === 'live' && admin.busy ? 'disabled' : ''}>Ejecutar ${icon('arrow')}</button></form><details class="admin-command-help"><summary>Ver todos los comandos disponibles</summary><div id="admin-command-list">${renderAdminHelp()}</div></details></section>`;
  }
  function renderAdminSummary() {
    const data = controlData();
    if (mode === 'live' && admin.error) return `<div class="archive-notice error" role="status"><h3>No se pudo actualizar el Despacho.</h3><p>${esc(admin.error)}</p><button class="button secondary" data-admin-refresh>Reintentar</button></div>`;
    if (!data) return '<div class="archive-notice" role="status"><p>Abriendo el escritorio de Miguel…</p></div>';
    const counts = data.counts || {}, metrics = [['stories_pending', 'Cuentos por revisar', 'stories'], ['auto_reply_pending', 'Borradores de Mimosuga', 'stories'], ['schedules_active', 'Mensajes programados', 'send'], ['visits_active', 'Visitas preparadas', 'vaca']];
    return `<div class="control-metrics">${metrics.map(([key, label, tab]) => `<button data-admin-tab="${tab}"><strong>${Number.isFinite(counts[key]) ? counts[key] : '—'}</strong><span>${label}</span>${icon('arrow')}</button>`).join('')}</div>${data.admin_identity_matches === false || data.editorial_admin?.available === false ? '<p class="admin-notice">La revisión editorial corresponde a otro administrador de Telegram. Sus acciones permanecen desactivadas en esta sesión.</p>' : ''}${data.errors?.length ? '<p class="admin-notice">Algunos apartados no pudieron actualizarse. Puedes volver a comprobar el estado.</p>' : ''}`;
  }
  function adminAnimalOptions(allowVaca = true) { return (controlData()?.animals || []).filter(animal => allowVaca || animal.id !== 'vaca').map(animal => `<option value="${esc(animal.id)}" ${!animal.available ? 'disabled' : ''}>${esc(animal.name || characters[animal.id]?.name || animal.id)}${animal.available ? '' : ' · no disponible'}</option>`).join(''); }
  function adminField(label, name, type = 'text', extra = '') { return `<label>${esc(label)}<input name="${name}" type="${type}" ${extra}></label>`; }
  function adminArea(label, name, placeholder = '') { return `<label class="admin-field-wide">${esc(label)}<textarea name="${name}" rows="3" maxlength="${name === 'gifts' ? 2000 : 3500}" placeholder="${esc(placeholder)}" required></textarea></label>`; }
  function adminForm(kind, heading, body, button, command, note = '') { return `<section class="admin-card"><h2>${esc(heading)}</h2>${note ? `<p class="admin-card-note">${esc(note)}</p>` : ''}<form data-admin-form="${kind}" class="admin-form">${body}<div class="admin-form-footer"><button class="button" type="submit" ${adminCommandAllowed(command) && !(mode === 'live' && (admin.busy || admin.check)) ? '' : 'disabled'}>${esc(button)}</button></div></form></section>`; }
  const deskConsultations = { items: [], selected: null, detail: null, loaded: false, loading: false, error: '', version: 0, controller: null };
  function clearDeskConsultations() { deskConsultations.version++; deskConsultations.controller?.abort(); Object.assign(deskConsultations, { items: [], selected: null, detail: null, loaded: false, loading: false, error: '', controller: null }); }
  function renderDeskConsultations() {
    const box = deskConsultations, c = box.detail;
    const choices = box.items.map(item => `<button class="desk-consultation ${item.id === box.selected ? 'active' : ''}" data-desk-consultation="${esc(item.id)}" aria-pressed="${item.id === box.selected}"><strong>${esc(item.title || 'Consulta con Salchicher')}</strong><small>${esc(formatDate(typeof item.created_at === 'number' && item.created_at < 1e12 ? item.created_at * 1000 : item.created_at))} · ${item.status === 'active' ? 'Abierta' : 'Cerrada'}</small></button>`).join('');
    const messages = c && c.id === box.selected ? (c.messages || []).filter(m => ['user', 'assistant'].includes(m.role) && typeof m.content === 'string').map(m => `<article class="consultation-message ${m.role}"><div class="consultation-speaker">${m.role === 'user' ? 'Sandra' : 'Doctor Salchicher'}<time>${esc(formatTime(typeof m.created_at === 'number' && m.created_at < 1e12 ? m.created_at * 1000 : m.created_at))}</time></div><p>${esc(m.content)}</p></article>`).join('') : '';
    return `<p class="desk-shared-note">El cuaderno de Patita: preguntas, pequeñas historias y recetas de mimos.</p><div class="desk-consultation-list">${choices}</div>${box.error ? `<p role="status">${esc(box.error)}</p><button class="text-button" data-desk-consultations>Volver a comprobar</button>` : box.loading ? '<p role="status">Abriendo el cuaderno de cuidados…</p>' : !box.items.length ? '<p class="admin-empty">Todavía no hay consultas guardadas.</p>' : ''}${messages}${chatHistory('salchicher').some(m => !m.consultation_id && m.role === 'assistant') ? `<details class="desk-other-messages"><summary>Otros mensajes de Salchicher</summary>${renderMessages('salchicher')}</details>` : ''}`;
  }
  function renderDeskChat() {
    const id = deskAnimal, name = characters[id].name, schedules = (controlData()?.schedules || []).filter(item => item.animal === id), scheduleAllowed = ['castori', 'mimosuga', 'salchicher', 'corte'].includes(id);
    const switcher = ids.filter(key => key !== 'dulcimiel').map(key => `<button class="desk-animal ${key === id ? 'active' : ''}" data-desk-animal="${key}" aria-pressed="${key === id}">${portrait(key, true)}<span>${esc(characters[key].name)}</span></button>`).join('');
    return `<div class="desk-animal-list" aria-label="Elegir conversación">${switcher}</div><div class="desk-workspace"><section class="chat-panel desk-chat"><header class="chat-header">${portrait(id, true)}<div><h2>${esc(name)}</h2><p>La conversación de Sandra · Tú escribes como ${esc(name)}</p></div></header><div id="desk-messages" class="chat-messages desk-messages" role="log" aria-label="Conversación compartida de ${esc(name)}" aria-live="polite">${id === 'salchicher' ? renderDeskConsultations() : renderMessages(id)}</div><div id="desk-delivery" class="admin-delivery" role="status">${renderAdminDelivery()}</div>${adminForm('desk-send-' + id, 'Escribir como ' + name, adminArea('Mensaje para Sandra', 'text', 'Escribe con la voz de ' + name + '…'), 'Revisar mensaje', '/' + id, 'Sandra recibirá el mensaje de este animal. Verás una confirmación antes de enviarlo.')}</section><aside class="desk-planner">${scheduleAllowed ? adminForm('desk-schedule-' + id, 'Preparar un mensaje para después', `<label>Día semanal<select name="day">${['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'].map(day => `<option>${day}</option>`).join('')}</select></label>${adminField('O fecha puntual', 'date', 'date')}${adminField('Hora de Madrid', 'time', 'time', 'required')}${adminArea('Mensaje de ' + name, 'text')}`, 'Programar mensaje', '/programar', 'Una fecha concreta se envía una vez. Sin fecha, se repite cada semana.') : '<section class="admin-card"><h2>Las visitas de la Vaca</h2><p>Prepara sus pistas y horarios en el apartado de la Vaca Mágica.</p><button class="button secondary" data-admin-tab="vaca">Abrir sus visitas</button></section>'}<section class="admin-card"><h2>Lo que espera su momento</h2>${schedules.length ? schedules.map(item => `<article class="admin-record"><div><p>${esc(item.text)}</p><small>${esc(item.time)} · ${esc(item.kind === 'weekly' ? ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][item.day] || 'Cada semana' : item.date || 'Una vez')}</small></div>${adminButton('Cancelar', '/cancelar ' + item.id)}</article>`).join('') : adminEmpty('No hay mensajes programados para este animal.')}<button class="text-button" data-admin-tab="send">Ver todas las programaciones →</button>${id === 'mimosuga' ? '<button class="text-button" data-admin-tab="stories">Cuentos y lista de borradores de Mimosuga →</button>' : ''}</section></aside></div>`;
  }
  function openDeskChat(id) {
    if (!canOpenControl() || !ids.includes(id) || id === 'dulcimiel') return;
    rememberAdminForms(); stopPolling(); deskAnimal = id; adminTab = 'chats';
    if (view !== 'control') navigate('control'); else { selectAdminTab('chats'); }
  }
  function startDeskChat() {
    if (!deskChatVisible()) return;
    refreshDeskChat(true);
    if (mode !== 'live') return;
    stopPolling(); startPolling(deskAnimal);
    if (deskAnimal === 'salchicher') loadDeskConsultations(); else loadHistory(deskAnimal);
  }
  function refreshDeskChat(forceScroll = false, prepended = false) {
    if (!deskChatVisible()) return;
    const log = document.getElementById('desk-messages'); if (!log) return;
    const bottom = log.scrollHeight - log.scrollTop - log.clientHeight < 100, top = log.scrollTop, height = log.scrollHeight;
    log.innerHTML = deskAnimal === 'salchicher' ? renderDeskConsultations() : renderMessages(deskAnimal);
    log.scrollTop = prepended ? top + log.scrollHeight - height : forceScroll || bottom ? log.scrollHeight : top;
  }
  async function loadDeskConsultations() {
    if (!deskChatVisible() || deskAnimal !== 'salchicher' || mode !== 'live' || deskConsultations.loading) return;
    const box = deskConsultations, epoch = liveEpoch, version = ++box.version;
    box.loading = true; box.error = ''; box.controller = new AbortController(); refreshDeskChat();
    try {
      const data = await bridge.consultations(box.controller.signal);
      if (epoch !== liveEpoch || version !== box.version || !canUseControl()) return;
      if (!Array.isArray(data?.consultations)) throw new Error('No se pudo abrir el cuaderno de cuidados.');
      box.items = data.consultations; box.loaded = true;
      if (!box.items.some(c => c.id === box.selected)) { box.selected = data.active_id || box.items[0]?.id || null; box.detail = null; }
      if (box.selected) { const result = await bridge.consultation(box.selected, box.controller.signal); if (epoch !== liveEpoch || version !== box.version || !canUseControl()) return; box.detail = result.consultation || result; }
    } catch (error) { if (epoch !== liveEpoch || version !== box.version || error.cancelled) return; if (archiveAccessError(error)) return; box.error = error.message; }
    finally { if (epoch === liveEpoch && version === box.version) { box.loading = false; box.controller = null; refreshDeskChat(); } }
  }
  async function loadDeskConsultation(id) {
    if (!deskChatVisible() || deskAnimal !== 'salchicher' || !deskConsultations.items.some(c => c.id === id)) return;
    deskConsultations.version++; deskConsultations.controller?.abort(); deskConsultations.loading = false; deskConsultations.selected = id; deskConsultations.detail = null; await loadDeskConsultations();
  }
  function clearSubmittedDeskDraft(text) {
    const drafts = adminFormDrafts[mode]; if (!drafts) return;
    for (const [kind, values] of Object.entries(drafts)) if (kind.startsWith('desk-') && buildAdminCommand(kind, values) === text) { const form = document.querySelector(`[data-admin-form="${kind}"]`); if (form && buildAdminCommand(kind, Object.fromEntries(new FormData(form))) !== text) { drafts[kind] = Object.fromEntries(new FormData(form)); continue; } delete drafts[kind]; form?.reset(); }
  }
  function renderAdminPanel() {
    if (adminTab === 'access') return renderInvitation() + renderOwnerInvitation();
    if (adminTab === 'chats') return renderDeskChat();
    const data = controlData(); if (!data) return '';
    const auto = data.automation || {}, schedules = data.schedules || [], stories = data.stories || [], drafts = data.drafts || [], visits = data.visits || [];
    if (adminTab === 'overview') return `<div class="admin-grid"><section class="admin-card"><div class="admin-card-heading"><h2>La casa está despierta</h2>${adminButton('Ver estado completo', '/status')}</div><div class="admin-bot-list">${(data.animals || []).map(animal => `<div>${characters[animal.id] ? portrait(animal.id, true) : icon('star')}<span><strong>${esc(animal.name || animal.id)}</strong><small>${animal.available ? animal.linked ? 'Bot disponible · chat vinculado' : 'Bot disponible · falta vincular chat' : 'Bot no disponible'}</small></span><i class="online-dot ${animal.available ? '' : 'offline'}" aria-hidden="true"></i></div>`).join('')}</div><p class="admin-card-note">${data.database_available ? 'Archivo disponible' : 'El archivo no está disponible'} · Horario ${esc(data.timezone || 'Europe/Madrid')}</p></section><section class="admin-card"><h2>El ritmo de cada día</h2><p class="admin-card-note">Estos controles usan los mismos ajustes que tu Centralita de Telegram.</p><div class="admin-setting"><div><strong>Mimosuga</strong><small>${auto.mimosuga_enabled ? 'Activa · ' + adminStatus(auto.mimosuga_mode) : 'En pausa'}</small></div><div>${adminButton('Con revisión', '/mimosuga_auto revision')}${adminButton('Automática', '/mimosuga_auto auto')}${adminButton(auto.mimosuga_enabled ? 'Pausar' : 'Activar', '/mimosuga_auto ' + (auto.mimosuga_enabled ? 'off' : 'on'))}</div></div><div class="admin-setting"><div><strong>Doctor Salchicher</strong><small>${auto.salchicher_enabled ? 'Activo' : 'En pausa'} · Consultas compartidas entre Sandra y Miguel</small></div>${adminButton(auto.salchicher_enabled ? 'Pausar' : 'Activar', '/salchicher_auto ' + (auto.salchicher_enabled ? 'off' : 'on'))}</div><div class="admin-setting"><div><strong>La Vaca Mágica</strong><small>Conversación ${auto.vaca_enabled ? 'activa' : 'en pausa'}</small></div>${adminButton(auto.vaca_enabled ? 'Pausar conversación' : 'Activar conversación', '/vaca_auto ' + (auto.vaca_enabled ? 'off' : 'on'))}</div><div class="admin-setting"><div><strong>Programaciones y visitas</strong><small>${auto.schedules_paused ? 'Pausadas' : 'En marcha'}</small></div>${adminButton(auto.schedules_paused ? 'Reanudar todo' : 'Pausar todo', auto.schedules_paused ? '/reanudar_programas' : '/pausar_programas')}</div></section></div>`;
    if (adminTab === 'send') return `<div class="admin-grid">${adminForm('send', 'Un mensaje con su voz', `<label>Enviar como<select name="animal">${adminAnimalOptions()}</select></label>${adminArea('Tu mensaje', 'text', 'Escribe lo que quieres que Sandra reciba…')}<div class="admin-send-preview admin-field-wide" data-send-preview>Vista previa: este mensaje llegará a Sandra como el animal seleccionado.</div>`, 'Enviar a Sandra', '/castori', 'Revisa el animal y el texto antes de enviarlo. Este envío llega a Sandra.')}${adminForm('schedule', 'Una pequeña alegría a su hora', `<label>Animal<select name="animal">${adminAnimalOptions(false)}</select></label><label>Día semanal<select name="day">${['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'].map(day => `<option>${day}</option>`).join('')}</select></label>${adminField('O fecha puntual (sustituye al día)', 'date', 'date')}${adminField('Hora de Madrid', 'time', 'time', 'required')}${adminArea('Mensaje programado', 'text')}`, 'Crear programación', '/programar', 'Sin fecha puntual, se repite cada semana. Las visitas de la Vaca tienen su propio apartado.')}</div><section class="admin-card admin-wide"><div class="admin-card-heading"><h2>Mensajes que esperan su momento</h2><div>${adminButton('Ver todos', '/programados')}${adminButton(auto.schedules_paused ? 'Reanudar' : 'Pausar', auto.schedules_paused ? '/reanudar_programas' : '/pausar_programas')}</div></div>${schedules.length ? schedules.map(item => `<article class="admin-record"><div><span class="eyebrow">${esc(characters[item.animal]?.name || item.animal)} · ${esc(item.id)}</span><p>${esc(item.text)}</p><small>${esc(item.kind === 'weekly' ? ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][item.day] || 'Cada semana' : item.date || 'Una vez')} · ${esc(item.time)}${item.next_at ? ' · Próximo: ' + esc(adminDate(item.next_at)) : ''}${item.sent ? ' · Enviado' : item.sending ? ' · En proceso' : ''}</small></div>${adminButton('Cancelar', '/cancelar ' + item.id)}</article>`).join('') : adminEmpty('No hay programaciones en esta vista.')}${data.truncated?.schedules ? '<p class="admin-card-note">Esta vista muestra las primeras programaciones. «Ver todos» abre el listado completo en la consola.</p>' : ''}</section>`;
    if (adminTab === 'stories') return `<section class="admin-card admin-wide"><div class="admin-card-heading"><div><h2>Los cuentos, antes de echar a volar</h2><p class="admin-card-note">Lee, revisa y decide cuáles forman parte de vuestra historia.</p></div>${adminButton('Últimos cuentos', '/admin_ultimos')}</div>${stories.length ? stories.map(item => `<article class="admin-record"><div><span class="eyebrow">${esc(adminStatus(item.status))} · ${esc(item.id)}</span><h3>${esc(item.title || 'Cuento sin título')}</h3><small>${esc(item.narrator || 'Mimosuga')} · ${esc(adminDate(item.created_at))}</small></div><div class="admin-record-actions">${adminButton('Leer', '/admin_ver ' + item.id)}${adminButton('Aprobar', '/admin_aprobar ' + item.id)}${adminButton('Hacer canon', '/admin_canon ' + item.id)}${adminButton('Descartar', '/admin_descartar ' + item.id)}</div></article>`).join('') : adminEmpty('No hay cuentos para mostrar en esta vista.')}</section><section class="admin-card admin-wide"><div class="admin-card-heading"><div><h2>El lápiz de Mimosuga</h2><p class="admin-card-note">Abre una revisión para recibir los botones reales de enviar o descartar en la consola.</p></div>${adminButton('Revisar pendientes', '/mimosuga_pendientes')}</div>${drafts.length ? drafts.map(item => `<article class="admin-draft"><div><span class="eyebrow">BORRADOR · ${esc(item.id)}</span><small>${esc(adminDate(item.created_at))}</small></div><p><strong>Mensaje recibido</strong>${esc(item.incoming_text)}</p><blockquote>${esc(item.proposed_text)}</blockquote>${adminButton('Abrir revisión', '/mimosuga_pendientes ' + item.id)}</article>`).join('') : adminEmpty('Mimosuga no tiene borradores pendientes en esta vista.')}</section>`;
    if (adminTab === 'vaca') return `<div class="admin-grid"><section class="admin-card"><div class="admin-card-heading"><h2>El cuaderno secreto de ilusiones</h2>${adminButton('Ver todos', '/vaca_deseos')}</div>${(data.wishes || []).length ? data.wishes.map(wish => `<div class="admin-wish"><span>${wish.favorite ? '★' : '✧'}</span><div><strong>${esc(wish.name)}</strong><p>${esc(wish.details || '')}</p><small>${esc(wish.id)}</small></div></div>`).join('') : adminEmpty('No hay deseos para mostrar en esta vista.')}<p class="admin-card-note">Este cuaderno es privado. Apuntar una ilusión no promete un regalo.</p></section>${adminForm('visit', 'Preparar una visita de diciembre', `${adminField('Fecha de entrega', 'date', 'date', 'required')}${adminField('Hora de Madrid', 'time', 'time', 'required')}${adminArea('Regalos que prepararás', 'gifts', 'Los regalos físicos los preparas tú…')}`, 'Crear borrador privado', '/vaca_visita', 'Primero se prepara el borrador. Revisa sus pistas, textos y fechas antes de activarlo.')}</div><section class="admin-card admin-wide"><div class="admin-card-heading"><div><h2>Las visitas, con todo su cuidado</h2><p class="admin-card-note">Al activar una visita autorizas sus mensajes a Sandra. El saludo presupone que has colocado los regalos.</p></div><div>${adminButton('Ver todas', '/vaca_visitas')}${adminButton(auto.vaca_visits_paused ? 'Reanudar visitas' : 'Pausar visitas', '/vaca_pausa ' + (auto.vaca_visits_paused ? 'off' : 'on'))}</div></div>${visits.length ? visits.map(visit => `<article class="admin-visit"><div class="admin-card-heading"><div><span class="eyebrow">${esc(adminStatus(visit.status))} · ${esc(visit.id)}</span><h3>${esc(adminDate(visit.delivery_at))}</h3></div><div>${adminButton('Ver detalle', '/vaca_visitas ' + visit.id)}${adminButton('Cancelar visita', '/vaca_cancelar ' + visit.id)}</div></div><p>${esc(visit.gifts)}</p><div class="admin-visit-events">${(visit.events || []).map(event => `<div><strong>${esc({ pista1: 'Primera pista', pista2: 'Segunda pista', manana: 'Saludo de la mañana' }[event.id] || event.id)}</strong><small>${esc(adminDate(event.at))} · ${esc(adminStatus(event.status))}</small><p>${esc(event.text)}</p></div>`).join('')}</div>${adminButton('Activar esta visita para Sandra', '/vaca_activar ' + visit.id, true, true)}</article>`).join('') : adminEmpty('No hay visitas preparadas en esta vista.')}</section><details class="admin-edit-visits"><summary>Editar una visita, sus textos o sus horas</summary><p>Cualquier cambio devuelve la visita a borrador. Revisa y vuelve a activarla cuando esté lista.</p><div class="admin-grid">${adminForm('visit-text', 'Cambiar una pista', `${adminField('ID de visita', 'id', 'text', 'required')}<label>Momento<select name="event"><option value="pista1">Primera pista</option><option value="pista2">Segunda pista</option><option value="manana">Saludo de la mañana</option></select></label>${adminArea('Nuevo texto', 'text')}`, 'Guardar texto del borrador', '/vaca_texto')}${adminForm('visit-time', 'Cambiar la hora de una pista', `${adminField('ID de visita', 'id', 'text', 'required')}<label>Momento<select name="event"><option value="pista1">Primera pista</option><option value="pista2">Segunda pista</option><option value="manana">Saludo de la mañana</option></select></label>${adminField('Nueva fecha', 'date', 'date', 'required')}${adminField('Nueva hora de Madrid', 'time', 'time', 'required')}`, 'Guardar fecha de la pista', '/vaca_hora')}${adminForm('visit-date', 'Mover la fecha de entrega', `${adminField('ID de visita', 'id', 'text', 'required')}${adminField('Nueva fecha', 'date', 'date', 'required')}${adminField('Nueva hora de Madrid', 'time', 'time', 'required')}`, 'Cambiar entrega del borrador', '/vaca_fecha')}</div></details>`;
    return `<div class="admin-grid">${adminForm('accuse', 'Un pequeño asunto para la Corte', adminArea('¿Qué ha ocurrido?', 'text', 'Cuenta los hechos del caso…'), 'Presentar acusación', '/acusar', 'La Corte tramita el caso con el mismo procedimiento de Telegram.')}${adminForm('plead', 'Tu versión también cuenta', adminArea('Alegación', 'text'), 'Presentar alegación', '/alegar')}</div><section class="admin-card admin-wide"><div class="admin-card-heading"><h2>El caso sobre la mesa</h2>${adminButton('Consultar estado', '/caso_estado')}</div>${data.court ? `<p><strong>${esc(adminStatus(data.court.status))}</strong> · ${esc(data.court.id)}</p><p>${esc(data.court.accusation)}</p>${data.court.verdict ? `<blockquote>${esc(data.court.verdict)}</blockquote>` : ''}${data.court.sentence_text ? `<p>${esc(data.court.sentence_text)}</p>` : ''}` : adminEmpty('No hay un caso activo para mostrar.')}</section><section class="admin-card admin-wide"><h2>La memoria de vuestro universo</h2><p class="admin-card-note">Consulta el lore, la memoria de historias o prepara un cuento de prueba privado. La prueba no se entrega a Sandra.</p><div class="admin-record-actions">${adminButton('Abrir lore', '/admin_lore')}${adminButton('Memoria de cuentos', '/admin_memoria_cuentos')}${adminButton('Crear cuento de prueba', '/admin_cuento_prueba mimosuga')}</div></section>`;
  }
  function renderAdminHelp() { const data = controlData(); return (data?.commands || []).map(command => { const [args, description] = adminHelp[command] || ['', 'Comando disponible en tu Centralita']; return `<button data-admin-compose="/${esc(command)}${args ? ' ' : ''}" ${adminCommandAllowed('/' + command) ? '' : 'disabled'}><code>/${esc(command)}${args ? ' ' + esc(args) : ''}</code><span>${esc(description)}</span></button>`; }).join(''); }
  function renderAdminEvents() {
    const events = controlEvents(); if (!events.length) return '<div class="admin-feed-empty">✧<p>Aquí aparecerán las respuestas del Despacho y sus botones.</p></div>';
    return events.map(event => `<article class="admin-event ${event.role === 'user' ? 'user' : ''}"><div class="admin-event-meta">${event.role === 'user' ? 'Miguel' : 'Despacho del Castor'}${event.time ? ' · ' + esc(formatTime(event.time)) : ''}${mode === 'demo' ? ' · Demostración' : ''}</div><div class="admin-event-text">${esc(event.text)}</div>${Array.isArray(event.buttons) ? `<div class="message-buttons">${event.buttons.filter(Array.isArray).map(row => `<div>${row.filter(button => typeof button?.text === 'string' && typeof button.data === 'string').map(button => `<button class="message-choice" data-admin-event="${esc(event.id)}" data-admin-callback="${esc(button.data)}" ${mode === 'live' && admin.busy || !canUseControl() || mode === 'live' && /^(adminstory|adminteststory):/.test(button.data) && (admin.data?.admin_identity_matches === false || admin.data?.editorial_admin?.available === false) ? 'disabled' : ''}>${esc(button.text)}</button>`).join('')}</div>`).join('')}</div>` : ''}</article>`).join('');
  }
  function renderAdminDelivery() {
    if (mode === 'demo') return 'Vista de prueba · Ninguna acción sale de este navegador.';
    const animalPreview = admin.preview?.match(/^\/(castori|mimosuga|salchicher|vaca|corte)\s+([\s\S]+)/);
    if (admin.preview) return `<div class="admin-confirm-preview"><strong>${animalPreview ? 'Para Sandra · ' + esc(characters[animalPreview[1]].name) : 'Revisa esta acción antes de enviarla'}</strong><pre>${esc(animalPreview ? animalPreview[2] : admin.preview)}</pre><button class="button" data-admin-confirm>${/^\/vaca_activar\b/.test(admin.preview) ? 'Activar la visita para Sandra' : 'Enviar a Sandra'}</button><button class="text-button" data-admin-cancel-preview>Volver a editar</button></div>`;
    return `${esc(admin.note || '')}${admin.check && admin.requestId ? `<button class="text-button" data-admin-receipt="${esc(admin.requestId)}">Comprobar envío</button>` : ''}`;
  }
  function adminTruncation() {
    const truncated = controlData()?.truncated || {}, labels = { schedules: 'programaciones', stories: 'cuentos', drafts: 'borradores', visits: 'visitas', wishes: 'deseos' };
    const keys = { send: ['schedules'], stories: ['stories', 'drafts'], vaca: ['visits', 'wishes'] }[adminTab] || [];
    const limited = keys.filter(key => truncated[key]).map(key => labels[key]);
    return limited.length ? `<p class="admin-notice">Esta vista muestra una selección de ${esc(limited.join(' y '))}. Usa sus botones de listado o la consola para consultar otros elementos por ID.</p>` : '';
  }
  function rememberAdminForms() {
    const drafts = adminFormDrafts[mode]; if (!drafts) return;
    document.querySelectorAll('[data-admin-form]').forEach(form => { drafts[form.dataset.adminForm] = Object.fromEntries(new FormData(form)); });
  }
  function restoreAdminForms() {
    const drafts = adminFormDrafts[mode]; if (!drafts) return;
    document.querySelectorAll('[data-admin-form]').forEach(form => { for (const [name, value] of Object.entries(drafts[form.dataset.adminForm] || {})) { const field = form.elements.namedItem(name); if (field) field.value = value; } });
  }
  function refreshControl() {
    if (view !== 'control' || !canUseControl()) return;
    const previousLog = deskChatVisible() ? document.getElementById('desk-messages') : null, deskScroll = previousLog ? { top: previousLog.scrollTop, bottom: previousLog.scrollHeight - previousLog.scrollTop - previousLog.clientHeight < 100 } : null;
    rememberAdminForms(); const focused = document.activeElement, focusForm = focused?.closest?.('[data-admin-form]')?.dataset.adminForm, focusName = focused?.name, selection = focused?.selectionStart;
    document.getElementById('admin-summary').innerHTML = renderAdminSummary(); document.getElementById('admin-panel').innerHTML = renderAdminPanel() + adminTruncation(); document.getElementById('admin-command-list').innerHTML = renderAdminHelp(); restoreAdminForms(); bindAdminForms(); refreshAdminFeed();
    if (deskScroll && deskChatVisible()) { const log = document.getElementById('desk-messages'); if (log) log.scrollTop = deskScroll.bottom ? log.scrollHeight : deskScroll.top; }
    if (focusForm && focusName) { const field = document.querySelector(`[data-admin-form="${focusForm}"]`)?.elements?.namedItem(focusName); if (field) { field.focus({ preventScroll: true }); if (typeof selection === 'number' && field.type !== 'date' && field.type !== 'time') { try { field.setSelectionRange(selection, selection); } catch (_) {} } } }
  }
  function refreshAdminFeed() {
    if (view !== 'control' || !canUseControl()) return;
    const feed = document.getElementById('admin-feed'), bottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 100, position = feed.scrollTop;
    feed.innerHTML = renderAdminEvents(); feed.scrollTop = bottom ? feed.scrollHeight : position;
    document.getElementById('admin-delivery').innerHTML = renderAdminDelivery(); if (deskChatVisible()) document.getElementById('desk-delivery').innerHTML = renderAdminDelivery();
    document.querySelectorAll('[data-admin-command], [data-admin-form] button[type="submit"], #admin-console-form button').forEach(button => { button.disabled = mode === 'live' && (admin.busy || admin.check) || Boolean(button.dataset.adminCommand && !adminCommandAllowed(button.dataset.adminCommand)); });
  }
  function selectAdminTab(tab) { if (!canUseControl() || !['overview', 'chats', 'send', 'stories', 'vaca', 'court', 'access'].includes(tab)) return; if (tab !== 'access') clearInvitationSecret(); adminTab = tab; document.querySelectorAll('[data-admin-tab]').forEach(button => { const selected = button.dataset.adminTab === tab; button.classList.toggle('active', selected); button.setAttribute('aria-pressed', String(selected)); }); refreshControl(); stopPolling(); if (tab === 'chats') startDeskChat(); if (tab === 'access') { loadInvitation(); loadOwnerInvitation(); } }
  function stopAdminReads() { adminVersion++; clearTimeout(adminTimer); adminController?.abort(); adminPollController?.abort(); adminController = null; adminPollController = null; admin.loading = false; }
  function clearAdminState() { stopAdminReads(); clearDeskConsultations(); ownerInvitation.data = null; ownerInvitation.error = ''; ownerInvitation.uncertain = false; clearInvitationSecret(); invitation.data = null; invitation.error = ''; invitation.uncertain = false; adminRequests.clear(); adminFormDrafts.live = {}; Object.assign(admin, { data: null, events: [], cursor: '0', loading: false, error: '', busy: false, note: '', requestId: null, check: false, preview: null }); }
  async function loadAdminState() {
    if (mode !== 'live' || !canUseControl() || admin.loading) return;
    const epoch = liveEpoch, version = adminVersion; admin.loading = true; admin.error = ''; adminController = new AbortController();
    try { const data = await bridge.adminState(adminController.signal); if (epoch !== liveEpoch || version !== adminVersion || mode !== 'live' || !canUseControl()) return; if (!data || data.actor !== 'owner') throw new Error('Esta sesión no tiene acceso a la Centralita.'); admin.data = data; }
    catch (error) { if (epoch !== liveEpoch || version !== adminVersion || error.cancelled) return; if (adminAccessError(error)) return; admin.error = error.message; if (error.status === 401 || error.status === 403) { clearLiveState(); mode = 'offline'; connectionError = error.message; connectionStatus = error.status; navigate('control', null, false); return; } }
    finally { if (epoch === liveEpoch && version === adminVersion) { admin.loading = false; adminController = null; refreshControl(); } }
  }
  function mergeAdminEvents(payload) {
    if (!payload || !Array.isArray(payload.events)) return;
    const byId = new Map((payload.reset ? [] : admin.events).map(event => [String(event.id), event]));
    for (const event of payload.events) if (event && Number.isFinite(Number(event.id)) && ['user', 'assistant'].includes(event.role) && typeof event.text === 'string') byId.set(String(event.id), event);
    admin.events = [...byId.values()].sort((a, b) => Number(a.id) - Number(b.id)).slice(-200);
    // Admin cursors include a boot identity. They are opaque and must not be coerced to numbers.
    if (typeof payload.cursor === 'string' || payload.cursor === 0) admin.cursor = String(payload.cursor);
    refreshAdminFeed();
  }
  function startAdminPolling() {
    if (mode !== 'live' || !canUseControl()) return;
    const version = adminVersion, epoch = liveEpoch;
    const run = async () => {
      if (version !== adminVersion || epoch !== liveEpoch || mode !== 'live' || !canUseControl()) return;
      adminPollController = new AbortController();
      try { const payload = await bridge.adminEvents(admin.cursor, adminPollController.signal); if (version !== adminVersion || epoch !== liveEpoch || mode !== 'live' || !canUseControl()) return; mergeAdminEvents(payload); }
      catch (error) { if (version !== adminVersion || epoch !== liveEpoch || error.cancelled) return; if (adminAccessError(error)) return; if (error.status === 401 || error.status === 403) { clearLiveState(); mode = 'offline'; connectionError = error.message; connectionStatus = error.status; navigate('control', null, false); return; } admin.note = 'No se están recibiendo respuestas del Despacho. Volveremos a comprobar la conexión.'; refreshAdminFeed(); }
      finally { if (version === adminVersion && epoch === liveEpoch && mode === 'live' && canUseControl()) adminTimer = setTimeout(run, 3000); }
    }; run();
  }
  const toCommandDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? value.split('-').reverse().join('/') : String(value || '').trim();
  function buildAdminCommand(kind, values) {
    const text = String(values.text || '').trim(), date = toCommandDate(values.date), time = String(values.time || '').trim(), id = String(values.id || '').trim();
    if (kind.startsWith('desk-send-')) return '/' + kind.slice(10) + ' ' + text;
    if (kind.startsWith('desk-schedule-')) return `/programar ${kind.slice(14)} ${date || values.day} ${time} ${text}`;
    if (kind === 'send') return '/' + values.animal + ' ' + text;
    if (kind === 'schedule') return `/programar ${values.animal} ${date || values.day} ${time} ${text}`;
    if (kind === 'visit') return `/vaca_visita ${date} ${time} | ${String(values.gifts || '').trim()}`;
    if (kind === 'visit-text') return `/vaca_texto ${id} ${values.event} | ${text}`;
    if (kind === 'visit-time') return `/vaca_hora ${id} ${values.event} ${date} ${time}`;
    if (kind === 'visit-date') return `/vaca_fecha ${id} ${date} ${time}`;
    if (kind === 'accuse') return '/acusar ' + text;
    if (kind === 'plead') return '/alegar ' + text;
    return '';
  }
  function bindAdminForms() {
    document.querySelectorAll('[data-admin-form]').forEach(form => {
      form.addEventListener('submit', async event => { event.preventDefault(); rememberAdminForms(); const kind = form.dataset.adminForm, formMode = mode, text = buildAdminCommand(kind, Object.fromEntries(new FormData(form))); const accepted = await submitAdmin(text, null, kind === 'send'); if (accepted && mode === formMode) { delete adminFormDrafts[formMode]?.[kind]; const current = document.querySelector(`[data-admin-form="${kind}"]`); if (current && buildAdminCommand(kind, Object.fromEntries(new FormData(current))) === text) current.reset(); } });
      if (form.dataset.adminForm === 'send') { const updatePreview = () => { const values = Object.fromEntries(new FormData(form)); form.querySelector('[data-send-preview]').textContent = `Para Sandra · ${characters[values.animal]?.name || values.animal}\n\n${values.text || 'Aquí verás el mensaje antes de enviarlo.'}`; }; form.addEventListener('input', updatePreview); updatePreview(); }
    });
  }
  function bindControl() { if (!canUseControl()) { document.getElementById('admin-auth-form')?.addEventListener('submit', event => { event.preventDefault(); submitAdminAuth(); }); return; } bindAdminForms(); if (adminTab === 'chats') startDeskChat(); if (adminTab === 'access') { loadInvitation(); loadOwnerInvitation(); } document.getElementById('admin-console-form').addEventListener('submit', async event => { event.preventDefault(); const input = document.getElementById('admin-command-input'), text = input.value.trim(); if (await submitAdmin(text)) input.value = ''; }); }
  function clearInvitationSecret() { clearOwnerInvitationSecret(); invitation.version++; invitation.controller?.abort(); invitation.controller = null; invitation.loading = false; invitation.secret = null; }
  function invitationData() { return mode === 'demo' ? { has_account: false, active: false, expires_at: null, reset: false, portal_url: 'https://ejemplo.invalid/castori/' } : invitation.data; }
  function renderInvitation() {
    const data = invitationData(), secret = invitation.secret;
    const disabled = invitation.loading ? 'disabled' : '';
    return `<section class="invitation-card"><div class="invitation-emblem" aria-hidden="true">${icon('key')}</div><div class="eyebrow">UNA PUERTA SOLO PARA ELLA</div><h2>La llave de Sandra.</h2><p class="invitation-intro">Prepara una invitación para que pueda elegir su usuario y su contraseña. Sin correo, con todos sus amigos al otro lado.</p>${mode === 'demo' ? '<p class="admin-notice">Vista de prueba · Las llaves de ejemplo no abren ninguna cuenta real.</p>' : ''}${invitation.error ? `<p class="account-error" role="alert">${esc(invitation.error)}</p>` : ''}${!data ? `<p class="admin-card-note" role="status">${invitation.loading ? 'Comprobando su llave…' : 'Consulta el estado de su acceso.'}</p><button class="button secondary" data-invitation-refresh ${disabled}>Comprobar acceso</button>` : `<div class="invitation-status"><span class="online-dot ${data.has_account ? '' : 'offline'}"></span><div><strong>${data.has_account ? 'Sandra ya tiene su cuenta' : 'Su rincón espera su primera llave'}</strong><p>${data.active ? `${data.reset ? 'Invitación para renovar su contraseña' : 'Invitación pendiente de activar'}${data.expires_at ? ' · hasta ' + esc(adminDate(data.expires_at)) : ''}` : data.has_account ? 'Puede entrar con el usuario y la contraseña que eligió.' : 'Crea una invitación y comparte el enlace con ella.'}</p></div></div>${secret ? `<div class="invitation-secret"><span class="eyebrow">${mode === 'demo' ? 'LLAVE FICTICIA DEL BOCETO' : 'GUARDA ESTA LLAVE AHORA'}</span><h3>Una invitación hecha para ella.</h3><p>El código se muestra ahora y no vuelve a aparecer al salir de este apartado. No se ha enviado automáticamente.</p><label>Enlace de invitación<input id="invitation-link" value="${esc(secret.invite_url || '')}" readonly></label><div class="invitation-copy"><button class="button secondary" data-invitation-copy="link">Copiar enlace ${icon('key')}</button></div><label>Código<input id="invitation-code" value="${esc(secret.code || '')}" readonly></label><button class="text-button" data-invitation-copy="code">Copiar código</button>${secret.expires_at ? `<small>Válida hasta ${esc(adminDate(secret.expires_at))}</small>` : ''}<button class="text-button invitation-dismiss" data-invitation-dismiss>Ya lo he guardado · Ocultar la llave</button></div>` : ''}<div class="invitation-actions">${!data.has_account ? `<button class="button" data-invitation-action="create" ${disabled}>${data.active ? 'Crear una nueva invitación' : 'Preparar su invitación'} ${icon('key')}</button>` : `<button class="button secondary" data-invitation-action="reset" ${disabled}>Preparar llave de recuperación</button>`}${data.active ? `<button class="text-button" data-invitation-action="revoke" ${disabled}>Revocar invitación pendiente</button>` : ''}<button class="text-button" data-invitation-refresh ${disabled}>Actualizar estado</button></div>${data.has_account ? '<p class="invitation-note">La llave de recuperación permite elegir una contraseña nueva con el mismo usuario. Al completar el cambio se cerrarán sus sesiones anteriores.</p>' : data.active ? '<p class="invitation-note">Crear otra invitación invalida la anterior.</p>' : ''}${data.portal_url ? `<div class="invitation-address"><span>Su puerta de entrada</span><p>${esc(data.portal_url)}</p></div>` : ''}`}</section>`;
  }
  function refreshInvitation() { if (view === 'control' && adminTab === 'access' && canUseControl()) document.getElementById('admin-panel').innerHTML = renderInvitation() + renderOwnerInvitation(); }
  async function loadInvitation() {
    if (!canUseControl() || invitation.loading) return;
    if (mode === 'demo') { refreshInvitation(); return; }
    const epoch = liveEpoch, version = ++invitation.version; invitation.loading = true; invitation.error = ''; invitation.controller = new AbortController(); refreshInvitation();
    try { const data = await bridge.invitation(invitation.controller.signal); if (epoch !== liveEpoch || version !== invitation.version || !canUseControl() || mode !== 'live') return; if (typeof data?.has_account !== 'boolean' || typeof data.active !== 'boolean') throw new Error('No se pudo comprobar la invitación.'); invitation.data = data; invitation.uncertain = false; }
    catch (error) { if (epoch !== liveEpoch || version !== invitation.version || error.cancelled) return; if (adminAccessError(error) || archiveAccessError(error)) return; invitation.error = error.message; }
    finally { if (epoch === liveEpoch && version === invitation.version) { invitation.loading = false; invitation.controller = null; refreshInvitation(); } }
  }
  async function changeInvitation(action) {
    if (!canUseControl() || invitation.loading || invitation.uncertain || !['create', 'reset', 'revoke'].includes(action)) return;
    const data = invitationData(); if (!data || action === 'create' && data.has_account || action === 'reset' && !data.has_account) return;
    if (mode === 'demo') { invitation.secret = action === 'revoke' ? null : { code: 'EJEMPLO-LLAVE-CELESTIAL', invite_url: 'https://ejemplo.invalid/castori/#invite/EJEMPLO-LLAVE-CELESTIAL', expires_at: '2026-12-31T22:59:00Z' }; refreshInvitation(); return; }
    const epoch = liveEpoch, version = ++invitation.version; invitation.secret = null; invitation.loading = true; invitation.error = ''; refreshInvitation();
    try {
      const result = await bridge.invitationAction(action); if (epoch !== liveEpoch || version !== invitation.version || mode !== 'live' || !canUseControl()) return;
      if (action !== 'revoke') { if (typeof result?.code !== 'string' || typeof result.invite_url !== 'string') throw new Error('No se pudo recuperar la nueva llave. Comprueba el estado antes de crear otra.'); invitation.secret = { code: result.code, invite_url: result.invite_url, expires_at: result.expires_at, reset: result.reset }; invitation.data = { ...data, active: true, expires_at: result.expires_at, reset: result.reset }; }
      else { invitation.data = typeof result?.has_account === 'boolean' ? result : { ...data, active: false, expires_at: null }; }
      invitation.uncertain = false;
    } catch (error) { if (epoch !== liveEpoch || version !== invitation.version) return; if (adminAccessError(error) || archiveAccessError(error)) return; invitation.uncertain = Boolean(error.uncertain); invitation.error = error.uncertain ? 'No pudimos confirmar el cambio. Actualiza el estado antes de crear otra invitación; no repetiremos la acción automáticamente.' : error.message; }
    finally { if (epoch === liveEpoch && version === invitation.version) { invitation.loading = false; refreshInvitation(); } }
  }
  async function copyInvitation(kind) {
    if (!canUseControl() || !invitation.secret) return;
    const field = document.getElementById(kind === 'code' ? 'invitation-code' : 'invitation-link');
    try { if (!window.navigator?.clipboard?.writeText) throw new Error(); await window.navigator.clipboard.writeText(field.value); toast(kind === 'code' ? 'Código copiado.' : 'Enlace copiado.'); }
    catch (_) { field.focus(); field.select(); toast('Seleccionado para que puedas copiarlo.'); }
  }
  function clearOwnerInvitationSecret() { ownerInvitation.version++; ownerInvitation.controller?.abort(); ownerInvitation.controller = null; ownerInvitation.loading = false; ownerInvitation.secret = null; }
  function ownerInvitationData() { return mode === 'demo' ? { has_account: false, active: false, expires_at: null, reset: false, portal_url: 'https://ejemplo.invalid/castori/' } : ownerInvitation.data; }
  function renderOwnerInvitation() {
    const data = ownerInvitationData(), secret = ownerInvitation.secret;
    const disabled = ownerInvitation.loading ? 'disabled' : '';
    return `<section class="invitation-card"><div class="invitation-emblem" aria-hidden="true">${icon('key')}</div><div class="eyebrow">TU MISMA LLAVE, TAMBIÉN EN EL DESPACHO</div><h2>Mi acceso a la Casa.</h2><p class="invitation-intro">Prepara tu acceso de Miguel a oficinacastori.es. Entrarás en la misma casa que Sandra y tu usuario podrá abrir el Despacho del Castor.</p>${mode === 'demo' ? '<p class="admin-notice">Vista de prueba · Las llaves de ejemplo no abren ninguna cuenta real.</p>' : ''}${ownerInvitation.error ? `<p class="account-error" role="alert">${esc(ownerInvitation.error)}</p>` : ''}${!data ? `<p class="admin-card-note" role="status">${ownerInvitation.loading ? 'Comprobando su llave…' : 'Consulta el estado de su acceso.'}</p><button class="button secondary" data-owner-invitation-refresh ${disabled}>Comprobar acceso</button>` : `<div class="invitation-status"><span class="online-dot ${data.has_account ? '' : 'offline'}"></span><div><strong>${data.has_account ? 'Miguel ya tiene su cuenta' : 'Su rincón espera su primera llave'}</strong><p>${data.active ? `${data.reset ? 'Invitación para renovar su contraseña' : 'Invitación pendiente de activar'}${data.expires_at ? ' · hasta ' + esc(adminDate(data.expires_at)) : ''}` : data.has_account ? 'Puede entrar con el usuario y la contraseña que eligió.' : 'Crea una invitación y abre el enlace para elegir tu usuario.'}</p></div></div>${secret ? `<div class="invitation-secret"><span class="eyebrow">${mode === 'demo' ? 'LLAVE FICTICIA DEL BOCETO' : 'GUARDA ESTA LLAVE AHORA'}</span><h3>Una invitación para tu usuario de Miguel.</h3><p>El código se muestra ahora y no vuelve a aparecer al salir de este apartado. No se ha enviado automáticamente.</p><label>Enlace de invitación<input id="owner-invitation-link" value="${esc(secret.invite_url || '')}" readonly></label><div class="invitation-copy"><button class="button secondary" data-owner-invitation-copy="link">Copiar enlace ${icon('key')}</button></div><label>Código<input id="owner-invitation-code" value="${esc(secret.code || '')}" readonly></label><button class="text-button" data-owner-invitation-copy="code">Copiar código</button>${secret.expires_at ? `<small>Válida hasta ${esc(adminDate(secret.expires_at))}</small>` : ''}<button class="text-button invitation-dismiss" data-owner-invitation-dismiss>Ya lo he guardado · Ocultar la llave</button></div>` : ''}<div class="invitation-actions">${!data.has_account ? `<button class="button" data-owner-invitation-action="create" ${disabled}>${data.active ? 'Crear una nueva invitación' : 'Preparar su invitación'} ${icon('key')}</button>` : `<button class="button secondary" data-owner-invitation-action="reset" ${disabled}>Preparar llave de recuperación</button>`}${data.active ? `<button class="text-button" data-owner-invitation-action="revoke" ${disabled}>Revocar invitación pendiente</button>` : ''}<button class="text-button" data-owner-invitation-refresh ${disabled}>Actualizar estado</button></div>${data.has_account ? '<p class="invitation-note">La llave de recuperación permite elegir una contraseña nueva con el mismo usuario. Al completar el cambio se cerrarán sus sesiones anteriores.</p>' : data.active ? '<p class="invitation-note">Crear otra invitación invalida la anterior.</p>' : ''}${data.portal_url ? `<div class="invitation-address"><span>Su puerta de entrada</span><p>${esc(data.portal_url)}</p></div>` : ''}`}</section>`;
  }
  function refreshOwnerInvitation() { refreshInvitation(); }
  async function loadOwnerInvitation() {
    if (!canUseControl() || ownerInvitation.loading) return;
    if (mode === 'demo') { refreshOwnerInvitation(); return; }
    const epoch = liveEpoch, version = ++ownerInvitation.version; ownerInvitation.loading = true; ownerInvitation.error = ''; ownerInvitation.controller = new AbortController(); refreshOwnerInvitation();
    try { const data = await bridge.ownerInvitation(ownerInvitation.controller.signal); if (epoch !== liveEpoch || version !== ownerInvitation.version || !canUseControl() || mode !== 'live') return; if (typeof data?.has_account !== 'boolean' || typeof data.active !== 'boolean') throw new Error('No se pudo comprobar la invitación.'); ownerInvitation.data = data; ownerInvitation.uncertain = false; }
    catch (error) { if (epoch !== liveEpoch || version !== ownerInvitation.version || error.cancelled) return; if (adminAccessError(error) || archiveAccessError(error)) return; ownerInvitation.error = error.message; }
    finally { if (epoch === liveEpoch && version === ownerInvitation.version) { ownerInvitation.loading = false; ownerInvitation.controller = null; refreshOwnerInvitation(); } }
  }
  async function changeOwnerInvitation(action) {
    if (!canUseControl() || ownerInvitation.loading || ownerInvitation.uncertain || !['create', 'reset', 'revoke'].includes(action)) return;
    const data = ownerInvitationData(); if (!data || action === 'create' && data.has_account || action === 'reset' && !data.has_account) return;
    if (mode === 'demo') { ownerInvitation.secret = action === 'revoke' ? null : { code: 'EJEMPLO-LLAVE-CELESTIAL', invite_url: 'https://ejemplo.invalid/castori/#owner-invite/EJEMPLO-LLAVE-CELESTIAL', expires_at: '2026-12-31T22:59:00Z' }; refreshOwnerInvitation(); return; }
    const epoch = liveEpoch, version = ++ownerInvitation.version; ownerInvitation.secret = null; ownerInvitation.loading = true; ownerInvitation.error = ''; refreshOwnerInvitation();
    try {
      const result = await bridge.ownerInvitationAction(action); if (epoch !== liveEpoch || version !== ownerInvitation.version || mode !== 'live' || !canUseControl()) return;
      if (action !== 'revoke') { if (typeof result?.code !== 'string' || typeof result.invite_url !== 'string') throw new Error('No se pudo recuperar la nueva llave. Comprueba el estado antes de crear otra.'); ownerInvitation.secret = { code: result.code, invite_url: result.invite_url, expires_at: result.expires_at, reset: result.reset }; ownerInvitation.data = { ...data, active: true, expires_at: result.expires_at, reset: result.reset }; }
      else { ownerInvitation.data = typeof result?.has_account === 'boolean' ? result : { ...data, active: false, expires_at: null }; }
      ownerInvitation.uncertain = false;
    } catch (error) { if (epoch !== liveEpoch || version !== ownerInvitation.version) return; if (adminAccessError(error) || archiveAccessError(error)) return; ownerInvitation.uncertain = Boolean(error.uncertain); ownerInvitation.error = error.uncertain ? 'No pudimos confirmar el cambio. Actualiza el estado antes de crear otra invitación; no repetiremos la acción automáticamente.' : error.message; }
    finally { if (epoch === liveEpoch && version === ownerInvitation.version) { ownerInvitation.loading = false; refreshOwnerInvitation(); } }
  }
  async function copyOwnerInvitation(kind) {
    if (!canUseControl() || !ownerInvitation.secret) return;
    const field = document.getElementById(kind === 'code' ? 'owner-invitation-code' : 'owner-invitation-link');
    try { if (!window.navigator?.clipboard?.writeText) throw new Error(); await window.navigator.clipboard.writeText(field.value); toast(kind === 'code' ? 'Código copiado.' : 'Enlace copiado.'); }
    catch (_) { field.focus(); field.select(); toast('Seleccionado para que puedas copiarlo.'); }
  }
  function demoAdminAction(text, callback) {
    const time = new Date().toISOString(); demoAdminEvents.push({ id: ++demoAdminSequence, role: 'user', text: callback ? 'Opción ficticia: ' + callback.data : text, time });
    const review = /^\/mimosuga_pendientes\b/.test(text);
    demoAdminEvents.push({ id: ++demoAdminSequence, role: 'assistant', time, text: review ? 'Vista de prueba · Borrador ficticio de Mimosuga:\n\nVen, Patita. Hoy el bosque tiene una historia pequeñita para ti.' : 'Vista de prueba · Acción simulada. No se ha enviado nada a Telegram ni a Sandra.\n\n' + (callback ? 'La opción de ejemplo quedó registrada.' : 'Comando: ' + text), buttons: review ? [[{ text: 'Enviar a Sandra · prueba', data: 'demo:send' }, { text: 'Descartar · prueba', data: 'demo:reject' }]] : [] });
    if (callback) { const original = demoAdminEvents.find(event => event.id === callback.eventId); if (original) original.buttons = []; } refreshAdminFeed();
  }
  async function submitAdmin(text, callback, confirmed = false) {
    text = String(text || '').trim(); if (!canUseControl() || !callback && (!text || !adminCommandAllowed(text))) { toast('Este comando no está disponible para esta sesión.'); return false; }
    if (mode === 'demo') { demoAdminAction(text, callback); return true; }
    if (admin.busy || admin.check) return false;
    if (!callback && !confirmed && /^\/(castori|mimosuga|salchicher|vaca|corte|vaca_activar)\s/.test(text)) { admin.preview = text; refreshAdminFeed(); document.getElementById('admin-delivery').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); return false; }
    if (callback) { if (/^(adminstory|adminteststory):/.test(callback.data) && (admin.data?.admin_identity_matches === false || admin.data?.editorial_admin?.available === false)) return false; const event = admin.events.find(item => Number(item.id) === Number(callback.eventId)); if (!event?.buttons?.some(row => Array.isArray(row) && row.some(button => button.data === callback.data))) return false; }
    const requestId = uid(), record = { id: requestId, text, epoch: liveEpoch, authVersion: adminAuth.version }; adminRequests.set(requestId, record);
    Object.assign(admin, { busy: true, note: 'Enviando al Despacho…', requestId, check: false, preview: null }); refreshAdminFeed();
    try {
      const result = callback ? await bridge.adminCallback({ event_id: callback.eventId, data: callback.data, request_id: requestId }) : await bridge.adminAction({ text, request_id: requestId });
      if (record.epoch !== liveEpoch || record.authVersion !== adminAuth.version || mode !== 'live' || !canUseControl()) return false;
      applyAdminReceipt(record, result.status); if (result.status === 'pending') setTimeout(() => checkAdminReceipt(requestId), 700); return true;
    } catch (error) { if (record.epoch !== liveEpoch || record.authVersion !== adminAuth.version || mode !== 'live' || !canUseControl()) return false; if (adminAccessError(error)) return false; if (error.status === 401 || error.status === 403) { clearLiveState(); mode = 'offline'; connectionError = error.message; connectionStatus = error.status; navigate('control', null, false); return false; } admin.busy = false; admin.note = error.message; admin.check = Boolean(error.uncertain); refreshAdminFeed(); return false; }
  }
  function applyAdminReceipt(record, status) {
    if (status === 'processed' || status === 'pending') clearSubmittedDeskDraft(record.text);
    admin.busy = status === 'pending'; admin.requestId = record.id; admin.check = status === 'uncertain' || status === 'pending';
    admin.note = status === 'pending' ? 'Acción recibida. Esperando confirmación…' : status === 'uncertain' ? 'No se pudo confirmar esta acción. No se enviará otra vez automáticamente. Comprueba su estado antes de repetirla.' : status === 'rejected' ? 'Este botón ya no está disponible. Abre de nuevo la revisión para usar sus opciones actuales.' : 'Acción procesada. La respuesta aparecerá en el cuaderno de mando.';
    refreshAdminFeed(); if (status === 'processed') loadAdminState();
  }
  async function checkAdminReceipt(requestId, attempt = 0) {
    const record = adminRequests.get(requestId); if (!record || record.epoch !== liveEpoch || record.authVersion !== adminAuth.version || mode !== 'live' || !canUseControl()) return;
    try { const result = await bridge.receipt(requestId); if (!adminRequests.has(requestId) || record.epoch !== liveEpoch || record.authVersion !== adminAuth.version || mode !== 'live' || !canUseControl()) return; applyAdminReceipt(record, result.status); if (result.status === 'pending') { if (attempt < 20) setTimeout(() => checkAdminReceipt(requestId, attempt + 1), 1500); else { admin.busy = false; admin.note = 'La acción sigue pendiente de confirmación. Puedes comprobar su estado.'; refreshAdminFeed(); } } }
    catch (error) { if (record.epoch !== liveEpoch || record.authVersion !== adminAuth.version || mode !== 'live' || !canUseControl()) return; if (adminAccessError(error)) return; if (error.status === 401 || error.status === 403) { clearLiveState(); mode = 'offline'; connectionError = error.message; connectionStatus = error.status; navigate('control', null, false); return; } admin.busy = false; admin.note = error.message; admin.check = true; refreshAdminFeed(); }
  }
  function memories() {
    const items = mode === 'demo' ? state.memories : state.memories.filter(m => m.type === 'story');
    return title('Tu cajita de cosas bonitas', 'Hay palabras que apetece guardar.', 'Aquí guardas tus cuentos de bienvenida favoritos. Tus conversaciones te esperan junto a cada amigo.') + (items.length ? items.map(m => `<article class="memory-card"><div class="eyebrow">${icon(m.type === 'story' ? 'book' : 'heart')}${esc(m.author)}</div><blockquote>${esc(m.text)}</blockquote><div class="memory-meta"><span>${m.type === 'story' ? 'Cuento de bienvenida' : 'Recuerdo del boceto'}</span>${m.type === 'story' ? `<button class="text-button" data-story="${esc(m.storyId)}">Volver a leer</button>` : ''}<button class="icon-button" data-remove-memory="${esc(m.id)}" aria-label="Quitar recuerdo">${icon('trash')}</button></div></article>`).join('') : `<div class="empty-state">${icon('heart')}<h2>Un huequito para lo que importa.</h2><p>Guarda un cuento de bienvenida de la biblioteca y podrás volver a él desde aquí.</p><button class="button" data-view="library">Abrir la biblioteca ${icon('arrow')}</button></div>`);
  }
  function wishRows() {
    const items = mode === 'demo' ? state.wishes : mode === 'live' && Array.isArray(serverState.wishes) ? serverState.wishes : [];
    if (!items.length) return `<div class="empty-state">${icon('star')}<h2>${mode === 'live' ? 'Tu cuaderno está listo.' : 'El primer deseo lo pones tú.'}</h2><p>${mode === 'live' ? 'Añade una ilusión o consulta la lista en la conversación con la Vaca.' : mode === 'demo' ? 'Los deseos de este boceto se quedan en este navegador.' : 'No podemos abrir tu cuaderno ahora mismo. Vuelve a llamar en un ratito.'}</p></div>`;
    return items.filter(w => w && typeof w.id !== 'undefined').map(w => { const name = mode === 'demo' ? w.text : w.name; return `<div class="wish-row"><span class="wish-star">${w.favorite ? '★' : '✧'}</span><span>${esc(name)}${w.details ? `<small>${esc(w.details)}</small>` : ''}${mode === 'live' ? `<small>${esc(w.id)}</small>` : ''}</span>${mode === 'live' ? `<button class="icon-button" data-wish-command="/favorito" data-wish-id="${esc(w.id)}" aria-label="${w.favorite ? 'Quitar favorito' : 'Marcar favorito'}" ${canCommand('vaca', '/favorito') ? '' : 'disabled'}>${icon('star')}</button>` : ''}<button class="icon-button" ${mode === 'demo' ? `data-remove-wish="${esc(w.id)}"` : `data-wish-command="/quitar" data-wish-id="${esc(w.id)}"`} aria-label="Quitar deseo: ${esc(name)}" ${mode !== 'demo' && !canCommand('vaca', '/quitar') ? 'disabled' : ''}>${icon('trash')}</button></div>`; }).join('');
  }
  function wishes() {
    const enabled = mode === 'demo' || canCommand('vaca', '/pedir');
    return title('El cuaderno de la Vaca Mágica', 'Las cosas que te hacen ilusión.', mode === 'demo' ? 'Un cuaderno de ejemplo, guardado solo en este navegador.' : 'Tus deseos se gestionan con el mismo cuaderno de la Vaca Mágica.') + `<div class="wish-board"><div><form class="wish-form" id="wish-form"><input id="wish-input" aria-label="Nuevo deseo" placeholder="Me haría ilusión…" maxlength="240" ${enabled ? '' : 'disabled'} required><button class="button" type="submit" ${enabled ? '' : 'disabled'}>${icon('plus')} Apuntar ilusión</button></form>${mode !== 'demo' ? `<button class="text-button wish-chat-link" data-open-wishlist ${canCommand('vaca', '/lista') ? '' : 'disabled'}>Ver la lista en la conversación →</button>` : ''}<div id="wish-list">${wishRows()}</div></div><aside class="wish-aside"><img src="assets/vaca-v2.png" alt="La Vaca Mágica"><p>«Patita, tengo una página<br>muuuuy especial para ti.»</p><small>Apuntar un deseo no promete un regalo. Lo bonito empieza por imaginarlo.</small><button class="text-button" data-chat="vaca" style="margin-top:20px">Contárselo a la Vaca →</button></aside></div>`;
  }
  function stopPolling() { pollVersion++; clearTimeout(pollTimer); if (pollController) pollController.abort(); pollController = null; }
  function navigate(next, id, updateHash = true, direct = false) {
    if (accountLocked()) return;
    if (experiences && next === 'chat' && id === 'salchicher') next = 'clinic';
    if (experiences && next === 'wishes') next = 'vaca';
    const experienceId = next === 'consultation' ? (id && !ids.includes(id) ? id : experiences?.selectedId()) : null;
    if (next !== view || (id && id !== activeId && id !== experiences?.selectedId())) unreadBoundaries.clear();
    initialChatScroll = next === 'chat' ? activeId : null;
    experiences?.leave();
    if (view === 'control' && next !== 'control') { clearInvitationSecret(); if (account.portal && isOwner() && mode === 'live' && !(adminAuth.loading && adminAuth.revocationPending)) lockPortalDesk(); }
    if (next === 'control' && view !== 'control' && account.portal && isOwner()) { adminAuth.portalPrepared = false; adminAuth.requirePassword = true; adminAuth.unlocked = false; adminAuth.checked = false; }
    stopPolling(); stopAdminReads(); cancelArchiveReads(); if (modal.open) modal.close(); if (next === 'chat' && !ids.includes(id)) next = 'home'; view = next; if (id && ids.includes(id)) activeId = id;
    if (next === 'clinic' || next === 'consultation') activeId = 'salchicher'; else if (next === 'vaca') activeId = 'vaca';
    if (next === 'chat') { initialChatScroll = activeId; unreadBoundary(activeId); }
    const views = { home, conversations, library, memories, wishes, control }; main.innerHTML = experiences && ['clinic', 'consultation', 'vaca'].includes(next) ? experiences.render(next, experienceId) : next === 'chat' ? chat(activeId) : (views[next] || home)();
    const labels = { home: 'Mi rincón', conversations: 'Conversaciones', library: 'La biblioteca', memories: 'Mis recuerdos', wishes: 'Cuaderno de ilusiones', control: 'Despacho del Castor', clinic: 'El consultorio de Salchicher', consultation: 'Mi consulta', vaca: 'El establo de las ilusiones' };
    document.getElementById('breadcrumb-current').textContent = next === 'chat' ? characters[activeId].name : labels[next] || 'Mi rincón';
    document.querySelectorAll('.nav-item').forEach(b => { const active = b.dataset.view === next || (next === 'chat' && b.dataset.view === 'conversations'); b.classList.toggle('active', active); if (active) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); b.querySelector('.nav-dot')?.remove(); if (active) b.insertAdjacentHTML('beforeend', '<span class="nav-dot"></span>'); });
    renderFriends(); renderConnection(); syncNotifications(); closeMenu();
    const nextHash = next === 'consultation' ? '#consultation/' + encodeURIComponent(experienceId || '') : next === 'chat' ? `#${activeId === 'vaca' ? 'carta' : 'chat'}/${activeId}` : `#${next === 'home' ? 'inicio' : next}`; if (updateHash && location.hash !== nextHash) history.pushState(null, '', nextHash);
    window.scrollTo(0, 0); if (next === 'chat') { scrollChat(); bindComposer(); }
    if (next === 'wishes') document.getElementById('wish-form').addEventListener('submit', addWish);
    main.focus({ preventScroll: true });
    if (mode === 'live' && next === 'chat' && ready(activeId)) { startPolling(activeId); if (!archives[activeId]?.loaded) loadHistory(activeId); }
    if (mode === 'live' && next === 'wishes') startPolling('vaca');
    if (mode === 'live' && next === 'library') loadStories(true);
    if (next === 'control' && canOpenControl()) { bindControl(); if (mode === 'live') { if (canUseControl()) { loadAdminState(); startAdminPolling(); } else loadAdminAuth(); } }
    if (['clinic', 'consultation', 'vaca'].includes(next)) experiences?.enter(next);
    acknowledgeChatRead();
  }
  function scrollChat() {
    const log = document.getElementById('chat-messages'); if (!log) return;
    if (initialChatScroll === activeId) {
      const divider = log.querySelector('.unread-divider');
      if (divider && Number.isFinite(divider.offsetTop)) {
        log.scrollTop = Math.max(0, divider.offsetTop - 12);
        if (archives[activeId]?.loaded) initialChatScroll = null;
        return;
      }
    }
    log.scrollTop = log.scrollHeight;
  }
  function refreshChat(forceScroll = false, prepended = false) {
    if (deskChatVisible()) { refreshDeskChat(forceScroll, prepended); return; }
    if (view !== 'chat') return;
    const log = document.getElementById('chat-messages'), nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 100, oldScroll = log.scrollTop, oldHeight = log.scrollHeight;
    log.innerHTML = renderMessages(activeId); document.querySelector('.send-button').disabled = readOnly() || !ready(activeId) || (mode === 'demo' ? pending.has(activeId) : sending.has(activeId));
    document.getElementById('delivery-status').innerHTML = deliveryNote(activeId); if (prepended) log.scrollTop = oldScroll + log.scrollHeight - oldHeight; else if (forceScroll || nearBottom) scrollChat(); else log.scrollTop = oldScroll;
    acknowledgeChatRead();
  }
  function mergeEvents(id, payload) {
    // Concurrent post-send and regular polls must never restore an older revision.
    if (Number.isFinite(Number(payload.cursor)) && Number(payload.cursor) < (cursors[id] || 0)) return;
    if (payload.reset) clearHistory(id);
    if (payload.unread) applyUnread(payload.unread);
    let changed = !liveChats[id] || Boolean(payload.reset);
    const byId = new Map((payload.reset ? [] : liveChats[id] || []).map(m => [String(m.id), m]));
    for (const event of payload.events || []) {
      if (!event || event.animal !== id || event.id == null || !['user', 'assistant'].includes(event.role) || typeof event.text !== 'string') continue;
      changed = true;
      byId.set(String(event.id), event); for (const key of callbackBusy) if (key.startsWith(event.id + ':')) callbackBusy.delete(key);
      if (event.role === 'assistant') delete deliveryNotes[id];
    }
    liveChats[id] = Array.from(byId.values()).sort((a, b) => Number(a.id) - Number(b.id));
    if (Number.isFinite(Number(payload.cursor))) cursors[id] = Number(payload.cursor);
    if (changed && chatVisible(id) && mode === 'live') refreshChat();
    if (payload.reset && chatVisible(id) && mode === 'live') loadHistory(id);
    if (view === 'chat' && activeId === id) acknowledgeChatRead();
  }
  async function refreshServerState(signal) {
    const stateEpoch = liveEpoch, version = ++stateReadVersion;
    const data = await bridge.state(signal); if (stateEpoch !== liveEpoch || version !== stateReadVersion) return data; if (!data || !Array.isArray(data.characters)) throw new Error('La puerta necesita un momentito. Vuelve a intentarlo en un ratito.');
    const nextActor = JSON.stringify(data.actor);
    const actorChanged = actorKey !== undefined && actorKey !== nextActor;
    if (actorChanged) clearLiveState();
    const unread = normalizeUnread(data.unread), unreadChanged = JSON.stringify(serverState.unread) !== JSON.stringify(unread);
    actorKey = nextActor; serverState = { ...data, unread };
    if (actorChanged && mode === 'live') { navigate(view, activeId, false); return data; }
    if (mode === 'live') {
      renderFriends(); syncNotifications();
      if (unreadChanged) refreshUnreadViews();
      if (view === 'wishes') document.getElementById('wish-list').innerHTML = wishRows();
      if (view === 'vaca') experiences?.refreshWishes();
      if (view === 'chat') {
        document.querySelectorAll('[data-command]').forEach(b => { b.disabled = !canCommand(activeId, b.dataset.command); });
        document.getElementById('chat-input').disabled = readOnly() || !ready(activeId);
      }
    }
    return data;
  }
  function clearLiveState(keepNotifications = false) {
    stopUnreadPolling(); if (!keepNotifications) notifications?.reset?.();
    readReceipts.clear(); readRequests.clear(); unreadBoundaries.clear(); initialChatScroll = null;
    experiences?.clear();
    liveEpoch++; cancelArchiveReads(); if (modal.open) modal.close(); document.getElementById('modal-content').innerHTML = '';
    clearAdminAuth(); clearAdminState();
    for (const data of [liveChats, cursors, deliveryNotes]) for (const key of Object.keys(data)) delete data[key];
    for (const key of Object.keys(archives)) delete archives[key]; storyShelf = newPage();
    requests.clear(); callbackBusy.clear();
  }
  function startPolling(id) {
    const version = pollVersion;
    const run = async () => {
      if (version !== pollVersion || mode !== 'live') return; pollController = new AbortController();
      try {
        const payload = await bridge.events(id, cursors[id] || 0, pollController.signal);
        if (version !== pollVersion || mode !== 'live') return; mergeEvents(id, payload);
        if (deskChatVisible() && id === 'salchicher') await loadDeskConsultations();
        if (view === 'wishes') await refreshServerState(pollController.signal);
        if (connectionError) { connectionError = ''; renderConnection(); }
      } catch (error) {
        if (!error.cancelled && version === pollVersion && mode === 'live') {
          if (error.status === 401 || error.status === 403) { clearLiveState(); mode = 'offline'; connectionError = error.message; connectionStatus = error.status; navigate(view, activeId, false); return; }
          deliveryNotes[id] = { text: 'Ahora no llegan las cartas. Volveremos a mirar el buzón en un momento.' }; connectionError = error.message;
          if (chatVisible(id)) refreshChat();
          const banner = document.getElementById('connection-banner'); banner.classList.add('degraded'); banner.querySelector('p').textContent = 'El camino se ha quedado en silencio. Tus cartas nuevas aparecerán cuando podamos abrir el buzón.';
        }
      } finally { if (version === pollVersion && mode === 'live') pollTimer = setTimeout(run, 3000); }
    }; run();
  }
  async function connect() {
    if (accountLocked()) return;
    clearInvitationSecret();
    const version = ++connectVersion; mode = 'checking'; connectionError = ''; connectionStatus = 0; navigate(view, activeId, false);
    try { await refreshServerState(); if (version !== connectVersion) return; mode = 'live'; }
    catch (error) { if (version !== connectVersion) return; mode = 'offline'; connectionStatus = error.status || 0; connectionError = error.message === 'La puerta necesita un momentito. Vuelve a intentarlo en un ratito.' ? 'Ahora no podemos abrir tu rincón. Vuelve a llamar en un ratito.' : error.message; }
    navigate(view, activeId, false); if (mode === 'live') startUnreadPolling();
  }
  function exploreDemo() {
    if (!canExploreDemo() || accountLocked()) return;
    clearInvitationSecret();
    connectVersion++; stopPolling(); clearLiveState(); mode = 'demo';
    for (const id of ids) { const messages = state.chats[id]; if (id !== 'corte' && Array.isArray(messages) && messages.at(-1)?.role === 'user' && !pending.has(id)) { const last = messages.at(-1); messages.push({ id: uid(), role: 'assistant', text: reply(id, last.text, messages.slice(0, -1)), time: Date.now() }); } }
    navigate(view, activeId, false);
  }
  function receiptNote(record, status) {
    if (status === 'uncertain') return { text: 'No se pudo confirmar este envío. No se enviará otra vez automáticamente.', requestId: record.id, check: true };
    if (status === 'rejected') return { text: 'Este botón ya no está disponible. Usa las opciones del mensaje más reciente.' };
    return { text: record.animal === 'castori' ? 'Tu carta espera su turno en la mesa de Castori.' : 'Tu mensaje ha llegado. La respuesta aparecerá aquí.' };
  }
  async function checkReceipt(requestId, attempt = 0) {
    const record = requests.get(requestId); if (!record) return;
    try {
      const result = await bridge.receipt(requestId);
      if (!requests.has(requestId) || record.epoch !== liveEpoch) return;
      if (result.status === 'pending') {
        if (attempt < 20) { setTimeout(() => checkReceipt(requestId, attempt + 1), 1500); return; }
        deliveryNotes[record.animal] = { text: 'El envío sigue pendiente de confirmación.', requestId, check: true };
      } else {
        deliveryNotes[record.animal] = receiptNote(record, result.status);
        if (result.status === 'processed' && record.forget) { clearHistory(record.animal); liveChats[record.animal] = []; cursors[record.animal] = 0; }
        if (result.status === 'rejected' && record.callback) callbackBusy.delete(record.callback.eventId + ':' + record.callback.data);
        if (result.status === 'processed') { try { await refreshServerState(); } catch (_) { /* Polling reports disconnections. */ } }
      }
      if (mode === 'live' && view === 'chat' && activeId === record.animal) refreshChat();
    } catch (error) { deliveryNotes[record.animal] = { text: error.message, requestId, check: true }; if (mode === 'live' && view === 'chat' && activeId === record.animal) refreshChat(); }
  }
  async function submitLive(animal, text, callback) {
    if (readOnly()) return false;
    if (mode !== 'live' || !ready(animal) || sending.has(animal)) return false;
    const requestId = uid(), record = { id: requestId, animal, forget: text === '/olvidar', callback, epoch: liveEpoch }; requests.set(requestId, record); sending.add(animal);
    deliveryNotes[animal] = { text: 'Enviando…' }; if (view === 'chat' && activeId === animal) refreshChat();
    try {
      const result = callback ? await bridge.callback({ animal, event_id: callback.eventId, data: callback.data, request_id: requestId }) : await bridge.message({ animal, text, request_id: requestId });
      if (record.epoch !== liveEpoch) return false;
      deliveryNotes[animal] = result.status === 'pending' ? { text: 'Mensaje recibido. Esperando confirmación…', requestId, check: true } : receiptNote(record, result.status);
      if (result.status === 'pending') setTimeout(() => checkReceipt(requestId), 700);
      else if (result.status === 'processed') { if (text === '/olvidar') { clearHistory(animal); liveChats[animal] = []; cursors[animal] = 0; } refreshServerState().catch(() => {}); }
      if (mode === 'live') { try { const events = await bridge.events(animal, cursors[animal] || 0); if (record.epoch === liveEpoch) mergeEvents(animal, events); } catch (_) { /* Regular polling recovers. */ } }
      return true;
    } catch (error) { deliveryNotes[animal] = { text: error.message, requestId, check: Boolean(error.uncertain) }; if (callback) callbackBusy.delete(callback.eventId + ':' + callback.data); toast(error.message); return false; }
    finally { sending.delete(animal); if (mode === 'live' && view === 'chat' && activeId === animal) refreshChat(); }
  }
  async function sendMessage(text) {
    if (readOnly()) return;
    text = text.trim(); const id = activeId; if (!text || !ready(id)) return; const input = document.getElementById('chat-input');
    if (view === 'chat' && window.CastoriBearAlarm?.matches(id, text) &&
        window.CastoriBearAlarm.play({ onFinish: () => toast('Oso espantado. Puedes continuar, Patita. 🐮') })) {
      if (input) { input.value = ''; input.style.height = 'auto'; }
      return;
    }
    if (mode === 'live') { const accepted = await submitLive(id, text.slice(0, 4000)); if (accepted && input?.isConnected && input.value.trim() === text) { input.value = ''; input.style.height = 'auto'; } return; }
    if (mode !== 'demo' || pending.has(id)) return; if (input) { input.value = ''; input.style.height = 'auto'; }
    const history = demoHistory(id); history.push({ id: uid(), role: 'user', text: text.slice(0, 1500), time: Date.now() }); pending.add(id); persist(); refreshChat(true);
    setTimeout(() => { let response; try { response = reply(id, text, history.slice(0, -1)); } catch (_) { response = 'Patita, se me ha enredado una frase. ¿Probamos otra vez?'; } history.push({ id: uid(), role: 'assistant', text: response, time: Date.now() }); pending.delete(id); persist(); if (mode === 'demo' && chatVisible(id)) refreshChat(true); }, 700 + Math.random() * 550);
  }
  function bindComposer() {
    document.getElementById('chat-form').addEventListener('submit', e => { e.preventDefault(); sendMessage(document.getElementById('chat-input').value); });
    const input = document.getElementById('chat-input'); input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(input.value); } }); input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 130)}px`; });
  }
  async function addWish(e) {
    e.preventDefault(); const input = document.getElementById('wish-input'), text = input.value.trim(); if (!text) return;
    if (mode === 'live') { const accepted = await submitLive('vaca', '/pedir ' + text); if (accepted && input.isConnected) { input.value = ''; toast('Petición enviada a la Vaca. El cuaderno se actualizará cuando quede confirmada.'); } return; }
    if (mode !== 'demo') return; state.wishes.push({ id: uid(), text: text.slice(0, 250) }); persist(); navigate('wishes'); toast('Ilusión guardada en el cuaderno del boceto.');
  }
  function showModal(html) { document.getElementById('modal-content').innerHTML = html; if (!modal.open) modal.showModal(); }
  async function openLiveStory(id) {
    if (mode !== 'live') return;
    cancelStory(); const epoch = liveEpoch, version = storyVersion; storyController = new AbortController();
    showModal(`<div class="eyebrow">${icon('book')} TU BIBLIOTECA DE MIMOSUGA</div><h2 id="modal-title">Abriendo el cuento…</h2><p role="status">Un momento, estamos buscando sus páginas.</p>`);
    try {
      const result = await bridge.story(id, storyController.signal);
      if (epoch !== liveEpoch || version !== storyVersion || mode !== 'live' || !modal.open) return;
      const story = result?.story;
      if (!story || String(story.id) !== String(id) || typeof story.text !== 'string' || !story.delivered_at) throw new Error('Este cuento no está disponible en tu biblioteca.');
      showModal(`<div class="eyebrow">${icon('book')}${esc(story.narrator || 'Mimosuga')}</div><h2 id="modal-title">${esc(story.title)}</h2><p class="story-delivered-date">${esc(formatDate(story.delivered_at || story.created_at) || 'Fecha no disponible')}</p><div class="story-text">${esc(story.text)}</div><div class="story-signature">Un cuento para volver a encontrarnos.</div>`);
    } catch (error) {
      if (epoch !== liveEpoch || version !== storyVersion || error.cancelled || !modal.open) return;
      if (archiveAccessError(error)) return;
      showModal(`<div class="eyebrow">${icon('book')} TU BIBLIOTECA</div><h2 id="modal-title">No hemos podido abrir el cuento.</h2><p role="status">${esc(error.message)}</p><button class="button secondary" data-live-story="${esc(id)}">Reintentar</button>`);
    } finally { if (version === storyVersion) storyController = null; }
  }
  function openStory(id) { const s = stories.find(x => x.id === id); if (!s) return; cancelStory(); const saved = state.memories.some(x => x.storyId === id); showModal(`<div class="eyebrow">${icon('book')}CUENTO DE BIENVENIDA</div><h2 id="modal-title">${esc(s.title)}</h2><div class="story-text">${esc(s.body)}</div><div class="story-signature">Con cariño, desde la Castora Celestial.</div><button class="button secondary" data-save-story="${esc(s.id)}">${icon(saved ? 'check' : 'heart')}${saved ? 'Guardado en mis recuerdos' : 'Guardar este cuento de bienvenida'}</button>`); }
  function about() { cancelStory(); showModal(`<div class="eyebrow">${icon('star')} TU PEQUEÑO UNIVERSO</div><h2 id="modal-title">Siempre hay una silla para ti.</h2><p>Castori guarda tus cartas en su oficina, Mimosuga tiene historias entre los pliegues del chal y la Vaca Mágica escucha los deseos de tu cuaderno. Dulcimiel está preparando un rincón muy dulce para su llegada.</p><p>En la biblioteca puedes volver a los cuentos que Mimosuga ha compartido contigo. En la repisa de bienvenida hay otras tres historias, por si te apetece empezar por una de ellas.</p><p>Salchicher te espera en su consultorio de cuento, con preguntas de patos, cuidados de plumas y recetas de mimos del Oso. Tú eliges si guardas cada visita en tu cuaderno. Las guardadas se cierran tras 30 días sin actividad y siguen disponibles para releer; las temporales se borran tras 48 horas sin actividad o al cerrarlas. Puedes borrar cualquier visita desde su ficha.</p><p>Tus conversaciones y tus cuentos te esperan al volver a entrar. Los favoritos de la repisa de bienvenida se guardan solo en este dispositivo.</p><button class="button" id="close-about">Volver a mi rincón ${icon('heart')}</button>`); }
  function toggleMemory(messageId) {
    if (mode !== 'demo') return; const existing = state.memories.findIndex(x => x.messageId === messageId);
    if (existing >= 0) state.memories.splice(existing, 1); else { const m = demoHistory(activeId).find(x => x.id === messageId); if (!m) return; state.memories.push({ id: uid(), type: 'message', messageId, author: characters[activeId].name, text: m.text }); }
    persist(); refreshChat(); toast(existing >= 0 ? 'Recuerdo quitado.' : 'Guardado como recuerdo del boceto.');
  }
  function closeMenu() { document.getElementById('sidebar').classList.remove('open'); document.getElementById('mobile-shade').classList.remove('open'); document.getElementById('mobile-menu').setAttribute('aria-expanded', 'false'); }
  function applyTheme() {
    const moon = appearance.light === 'moon';
    document.body.classList.toggle('moon', moon);
    document.body.dataset.palette = appearance.palette;
    const b = document.getElementById('theme-toggle');
    b.setAttribute('aria-pressed', String(moon)); b.setAttribute('aria-label', moon ? 'Activar luz de día' : 'Activar luz de luna'); b.title = moon ? 'Luz de día' : 'Luz de luna';
    const palette = palettes[appearance.palette], toggle = document.getElementById('palette-toggle');
    toggle?.setAttribute('aria-label', 'Elegir los colores de mi rincón. Ahora: ' + palette.name);
    if (toggle) toggle.title = 'Colores · ' + palette.name;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', palette[appearance.light]);
  }
  function saveAppearance() {
    try { localStorage.setItem(appearanceKey, JSON.stringify(appearance)); }
    catch (_) { toast('Tus colores están puestos, pero este dispositivo no ha podido recordarlos.'); }
  }
  function openAppearance() {
    cancelStory();
    showModal(`<div class="appearance-picker"><div class="eyebrow">${icon('star')} A TU GUSTO, PATITA</div><h2 id="modal-title">¿De qué color es<br>tu rincón?</h2><p>Un poquito de rosa, una tarde de cacao o un paseo por el bosque. Elige lo que te haga sonreír.</p><div class="palette-options" role="group" aria-label="Colores de tu rincón">${Object.entries(palettes).map(([id, palette]) => `<button type="button" id="palette-option-${id}" class="palette-option" data-palette-choice="${id}" aria-pressed="${appearance.palette === id}"><span class="palette-preview" data-preview="${id}" aria-hidden="true"><span></span><span></span><span></span></span><span class="palette-name">${palette.name}</span><span class="palette-description">${palette.description}</span><span class="palette-selected">${appearance.palette === id ? 'Tu elección' : 'Elegir estos colores'}</span></button>`).join('')}</div><p class="appearance-note">Los colores cambian al elegirlos y se guardan en este dispositivo. También puedes combinarlos con la luz de luna.</p><button type="button" class="button" id="close-appearance">Así me gusta ${icon('heart')}</button></div>`);
  }
  function choosePalette(id) {
    if (typeof id !== 'string' || !Object.hasOwn(palettes, id)) return;
    appearance.palette = id; applyTheme(); saveAppearance(); openAppearance();
    document.getElementById('palette-option-' + id)?.focus();
  }
  document.addEventListener('click', async e => {
    const b = e.target.closest('button, a'); if (!b || b.disabled) return;
    if (b.id === 'palette-toggle') openAppearance();
    else if (b.dataset.paletteChoice) choosePalette(b.dataset.paletteChoice);
    else if (b.id === 'close-appearance') modal.close();
    else if (b.hasAttribute('data-account-retry')) bootstrapAccount();
    else if (b.dataset.accountScreen) { if (account.loading) return; account.screen = b.dataset.accountScreen === 'register' ? 'register' : 'login'; account.error = ''; renderAccountGate(); }
    else if (b.hasAttribute('data-account-help')) { account.help = !account.help; renderAccountGate(); }
    else if (b.hasAttribute('data-account-show-password')) { const input = document.getElementById('account-password'), visible = input.type === 'password'; input.type = visible ? 'text' : 'password'; b.textContent = visible ? 'Ocultar' : 'Mostrar'; b.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña'); }
    else if (b.hasAttribute('data-account-logout') || b.id === 'account-logout') logoutAccount();
    else if (accountLocked()) return;
    else if (experiences && await experiences.handle(b)) return;
    else if (b.hasAttribute('data-admin-auth-refresh')) loadAdminAuth();
    else if (b.hasAttribute('data-admin-lock')) lockAdmin();
    else if (b.dataset.deskAnimal) openDeskChat(b.dataset.deskAnimal);
    else if (b.dataset.deskConsultation) loadDeskConsultation(b.dataset.deskConsultation);
    else if (b.hasAttribute('data-desk-consultations')) loadDeskConsultations();
    else if (b.hasAttribute('data-owner-invitation-refresh')) loadOwnerInvitation();
    else if (b.dataset.ownerInvitationAction) changeOwnerInvitation(b.dataset.ownerInvitationAction);
    else if (b.dataset.ownerInvitationCopy) copyOwnerInvitation(b.dataset.ownerInvitationCopy);
    else if (b.hasAttribute('data-owner-invitation-dismiss')) { clearOwnerInvitationSecret(); refreshInvitation(); }
    else if (b.hasAttribute('data-invitation-refresh')) loadInvitation();
    else if (b.dataset.invitationAction) changeInvitation(b.dataset.invitationAction);
    else if (b.dataset.invitationCopy) copyInvitation(b.dataset.invitationCopy);
    else if (b.hasAttribute('data-invitation-dismiss')) { clearInvitationSecret(); refreshInvitation(); }
    else if (b.dataset.mode) { if (b.dataset.mode === 'demo') exploreDemo(); else connect(); }
    else if (b.dataset.adminTab) selectAdminTab(b.dataset.adminTab);
    else if (b.hasAttribute('data-admin-refresh')) { if (mode === 'demo') refreshControl(); else loadAdminState(); }
    else if (b.dataset.adminCommand) { await submitAdmin(b.dataset.adminCommand, null, b.dataset.adminConfirmed === 'true'); document.getElementById('admin-feed')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
    else if (b.dataset.adminCompose) { const input = document.getElementById('admin-command-input'); input.value = b.dataset.adminCompose; input.focus(); }
    else if (b.dataset.adminEvent) await submitAdmin('', { eventId: Number(b.dataset.adminEvent), data: b.dataset.adminCallback });
    else if (b.dataset.adminReceipt) checkAdminReceipt(b.dataset.adminReceipt);
    else if (b.hasAttribute('data-admin-confirm')) { const text = admin.preview; if (text) await submitAdmin(text, null, true); }
    else if (b.hasAttribute('data-admin-cancel-preview')) { admin.preview = null; refreshAdminFeed(); document.getElementById('admin-command-input').focus(); }
    else if (b.dataset.chat) navigate('chat', b.dataset.chat);
    else if (b.dataset.view) navigate(b.dataset.view);
    else if (b.dataset.history) loadHistory(b.dataset.history);
    else if (b.hasAttribute('data-load-stories')) loadStories();
    else if (b.dataset.liveStory) openLiveStory(b.dataset.liveStory);
    else if (b.dataset.story) openStory(b.dataset.story);
    else if (b.dataset.suggestion) sendMessage(b.dataset.suggestion);
    else if (b.dataset.command) { if (!canCommand(activeId, b.dataset.command)) return; if (b.dataset.compose) { const input = document.getElementById('chat-input'); input.value = b.dataset.command + ' '; input.focus(); } else sendMessage(b.dataset.command); }
    else if (b.dataset.callbackEvent) { const eventId = Number(b.dataset.callbackEvent), key = eventId + ':' + b.dataset.callback; if (readOnly() || callbackBusy.has(key) || mode !== 'live' || sending.has(activeId)) return; callbackBusy.add(key); refreshChat(); await submitLive(activeId, '', { eventId, data: b.dataset.callback }); }
    else if (b.dataset.checkRequest) checkReceipt(b.dataset.checkRequest);
    else if (b.dataset.wishCommand) await submitLive('vaca', b.dataset.wishCommand + ' ' + b.dataset.wishId);
    else if (b.hasAttribute('data-open-wishlist')) { navigate('chat', 'vaca'); sendMessage('/lista'); }
    else if (b.dataset.saveMessage) toggleMemory(b.dataset.saveMessage);
    else if (b.dataset.saveStory) { const s = stories.find(x => x.id === b.dataset.saveStory); if (!s) return; if (!state.memories.some(x => x.storyId === s.id)) { state.memories.push({ id: uid(), type: 'story', storyId: s.id, author: s.eyebrow, text: s.title }); persist(); } b.innerHTML = icon('check') + 'Guardado en mis recuerdos'; toast('Cuento de bienvenida guardado.'); }
    else if (b.dataset.removeMemory) { state.memories = state.memories.filter(x => x.id !== b.dataset.removeMemory); persist(); navigate('memories'); }
    else if (b.dataset.removeWish && mode === 'demo') { state.wishes = state.wishes.filter(x => x.id !== b.dataset.removeWish); persist(); navigate('wishes'); }
    else if (b.id === 'discover-friends') document.getElementById('our-friends').scrollIntoView({ behavior: 'smooth', block: 'start' });
    else if (['about-demo', 'profile', 'chat-info'].includes(b.id)) about();
    else if (b.id === 'close-about') modal.close();
  });
  document.getElementById('theme-toggle').addEventListener('click', () => { appearance.light = appearance.light === 'moon' ? 'day' : 'moon'; applyTheme(); saveAppearance(); });
  document.getElementById('modal-close').addEventListener('click', () => modal.close());
  modal.addEventListener('close', cancelStory);
  modal.addEventListener('close', acknowledgeVisibleRead);
  document.addEventListener('visibilitychange', () => { acknowledgeVisibleRead(); if (document.visibilityState === 'visible' && mode === 'live') refreshServerState().catch(() => {}); });
  window.addEventListener('focus', acknowledgeVisibleRead);
  window.addEventListener('resize', acknowledgeVisibleRead);
  window.visualViewport?.addEventListener('resize', acknowledgeVisibleRead);
  window.visualViewport?.addEventListener('scroll', acknowledgeVisibleRead);
  document.addEventListener('scroll', acknowledgeVisibleRead, true);
  modal.addEventListener('click', e => { if (e.target === modal) { const r = modal.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) modal.close(); } });
  document.getElementById('mobile-menu').setAttribute('aria-expanded', 'false');
  document.getElementById('mobile-menu').addEventListener('click', () => { const open = document.getElementById('sidebar').classList.toggle('open'); document.getElementById('mobile-shade').classList.toggle('open', open); document.getElementById('mobile-menu').setAttribute('aria-expanded', String(open)); });
  document.getElementById('mobile-shade').addEventListener('click', closeMenu);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });
  function fromHash() { if (accountLocked()) return; const path = location.hash.slice(1).split('/'); if (path[0] === 'consultation' && path[1]) { let id; try { id = decodeURIComponent(path[1]); } catch (_) { navigate('clinic', null, false); return; } navigate('consultation', id, false); } else if (path[0] === 'carta' && path[1] === 'vaca') navigate('chat', 'vaca', false, true); else if (path[0] === 'chat' && ids.includes(path[1])) navigate('chat', path[1], false); else navigate(['conversations', 'library', 'memories', 'wishes', 'control', 'clinic', 'vaca'].includes(path[0]) ? path[0] : 'home', null, false); }
  window.addEventListener('hashchange', fromHash); window.addEventListener('pageshow', event => { if (mode === 'live') { startUnreadPolling(); acknowledgeVisibleRead(); } if (event.persisted && account.portal && isOwner() && view === 'control') { adminAuth.portalPrepared = false; loadAdminAuth(); } }); window.addEventListener('pagehide', () => { if (account.portal && isOwner() && view === 'control') lockPortalDesk(); stopUnreadPolling(); stopPolling(); stopAdminReads(); cancelArchiveReads(); clearInvitationSecret(); }); bridge.onUnauthorized?.(expireAccountSession); applyTheme(); bootstrapAccount();
}());

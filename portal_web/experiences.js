(function () {
  'use strict';
  window.CastoriExperiences = { create(ctx) {
    const { bridge, esc, icon, portrait } = ctx;
    const dateValue = value => typeof value === 'number' && value > 0 && value < 1e12 ? value * 1000 : value;
    const formatDate = value => ctx.formatDate(dateValue(value));
    const formatTime = value => ctx.formatTime(dateValue(value));
    let route = '', selectedId = '', generation = 0, controller, timer, busy = false;
    let consultations = [], activeId = null, detail = null, loaded = false, error = '', note = '', receipt = null;
    let demoConsultations = [], letters = [], lettersCursor = null, lettersMore = false, lettersLoading = false, lettersError = '';
    let wishFilter = 'all', wishSearch = '', urgentNoticeId = null, lettersVersion = 0;
    const isDemo = () => ctx.mode() === 'demo';
    const enabled = animal => isDemo() || ctx.mode() === 'live' && ctx.ready(animal);
    const stamp = () => new Date().toISOString();
    const current = () => isDemo() ? demoConsultations : consultations;
    const active = () => current().find(c => c.status === 'active');
    const tag = c => c.status === 'recovered' ? 'Me encuentro bien' : c.status === 'inactive' ? c.closure_reason === 'urgent_help' ? 'Consulta cerrada' : 'Cerrada por inactividad' : 'En curso';
    const pendingSend = () => Boolean(receipt?.pending && receipt.consultation === selectedId);
    function mergeConsultation(c, removeId) {
      consultations = consultations.filter(x => x.id !== (c?.id || removeId));
      if (c) consultations.unshift(c);
      activeId = consultations.find(x => x.status === 'active')?.id || null;
    }
    const safeUrl = value => { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : ''; } catch (_) { return ''; } };
    const demoNote = () => isDemo() ? '<p class="experience-demo">✧ Boceto de ejemplo · Las consultas de esta vista duran solo esta sesión.</p>' : '';
    const unavailable = animal => enabled(animal) ? '' : '<p class="experience-notice">Este rincón estará disponible al conectar los bots. Puedes recorrer su diseño desde «Explorar boceto».</p>';
    function clinicRows() {
      if (error) return `<div class="experience-notice" role="status">${esc(error)} <button class="text-button" data-clinic-refresh>Volver a comprobar</button></div>`;
      if (!isDemo() && !loaded && enabled('salchicher')) return '<p class="experience-empty" role="status">Abriendo tu cuaderno de cuidados…</p>';
      const rows = current().filter(c => c.status !== 'active');
      if (!rows.length) return '<div class="experience-empty"><span>✧</span><h3>Tu cuaderno empieza contigo.</h3><p>Las consultas que elijas guardar encontrarán aquí su lugar.<br>Podrás volver a leerlas, a tu ritmo.</p></div>';
      return rows.map(c => `<article class="consultation-row"><span class="consultation-mark">${icon('heart')}</span><div><span class="consultation-date">${esc(formatDate(c.created_at))}</span><h3>${esc(c.title || 'Un ratito de cuidados')}</h3><span class="consultation-status ${esc(c.status)}">${esc(tag(c))}</span></div><button class="text-button" data-consultation-open="${esc(c.id)}">Abrir cuaderno ${icon('arrow')}</button></article>`).join('');
    }
    function clinic() {
      const open = active();
      return `<section class="experience-hero clinic-hero"><div class="experience-hero-copy"><div class="eyebrow">${icon('heart')} EL CONSULTORIO DEL DOCTOR SALCHICHER</div><h1>Aquí se viene<br>a que te <em>cuiden.</em></h1><p>Deja las prisas en la puerta, Patita.<br>Hay un sillón, unas orejitas atentas y tiempo para ti.</p><div class="experience-hero-actions"><button class="button" ${open ? `data-consultation-open="${esc(open.id)}"` : 'data-consultation-new'} ${enabled('salchicher') ? '' : 'disabled'}>${icon(open ? 'book' : 'plus')}${open ? 'Continuar mi consulta' : 'Iniciar consulta'}</button><button class="text-button" data-clinic-history>Mi cuaderno de cuidados ↓</button></div><span class="experience-private">${icon('key')} Un espacio privado, a tu ritmo</span></div><div class="experience-hero-art">${portrait('salchicher')}<div class="doctor-sign">Doctor Salchicher<small>CUIDADOS PEQUEÑOS · CARIÑO ENORME</small></div><span class="hero-spark first">✧</span><span class="hero-spark second">✦</span></div></section>${demoNote()}${unavailable('salchicher')}<div class="care-path"><div><span>01</span><h3>Me cuentas.</h3><p>Abres una consulta cuando necesitas un poquito de cuidado.</p></div><div><span>02</span><h3>Te acompaño.</h3><p>Preguntas con calma, pequeños cuidados y mimos del Oso.</p></div><div><span>03</span><h3>Volvemos a sonreír.</h3><p>Cuando te encuentres bien, puedes cerrar esa consulta.</p></div></div><section class="clinic-lower" id="clinic-history"><div class="clinic-notebook"><div class="experience-section-heading"><div><div class="eyebrow">TUS PEQUEÑAS HISTORIAS DE CUIDADO</div><h2>El cuaderno de Patita.</h2></div><span>✧</span></div><div id="clinic-records">${clinicRows()}</div></div><aside class="care-paper"><span class="paper-pin">✦</span><h3>Tu intimidad<br>también se cuida.</h3><p>Tú eliges si guardas cada consulta. Puedes releerla y borrarla cuando quieras.</p><p>Las consultas guardadas se cierran tras 30 días sin actividad. Eso no significa que te hayas curado.</p><small>Salchicher acompaña con cuidados generales. No emite diagnósticos médicos.</small></aside></section>`;
    }
    function summaryCard(c) {
      const summary = Array.isArray(c.care_summary) ? c.care_summary.filter(x => typeof x === 'string') : [];
      return `<aside class="consultation-summary"><div class="summary-doctor">${portrait('salchicher', true)}<span>De mi cuaderno<br><strong>al tuyo.</strong></span></div><div class="eyebrow">LO QUE HEMOS HABLADO</div><h2>Un poquito<br>de cuidado.</h2>${summary.length ? `<ul>${summary.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p>Los cuidados que Salchicher proponga durante esta consulta aparecerán aquí, para tenerlos cerquita.</p>'}<div class="summary-meta"><span>Comenzó</span><strong>${esc(formatDate(c.created_at))}</strong><span>Tu elección</span><strong>${c.retained ? 'Guardar en mi cuaderno' : 'Consulta temporal · 48 h sin actividad'}</strong>${c.status !== 'active' ? `<span>Cierre</span><strong>${c.status === 'recovered' ? 'Has indicado que te encuentras bien' : c.closure_reason === 'urgent_help' ? 'Cerrada para buscar atención sanitaria' : 'Sin actividad durante 30 días'}</strong>` : ''}</div><p class="consultation-boundary">Un resumen de cuidados y compañía, sin diagnóstico médico.</p><button class="text-button danger" data-consultation-delete="${esc(c.id)}">${icon('trash')} Borrar esta consulta</button></aside>`;
    }
    function transcript(c) {
      const messages = Array.isArray(c.messages) ? c.messages : [];
      return messages.filter(m => ['user', 'assistant'].includes(m.role) && typeof m.content === 'string').map(m => `<article class="consultation-message ${m.role}"><div class="consultation-speaker">${m.role === 'assistant' ? 'Doctor Salchicher' : 'Tú'}<time>${esc(formatTime(m.created_at))}</time></div><p>${esc(m.content)}</p></article>`).join('') || '<div class="consultation-welcome"><span>✧</span><h3>Ya puedes pasar, Patita.</h3><p>Salchicher se ajusta las gafitas.<br>Cuéntale qué te trae hoy por aquí.</p></div>';
    }
    function consultation() {
      const c = detail && detail.id === selectedId ? detail : isDemo() ? demoConsultations.find(x => x.id === selectedId) : null;
      if (urgentNoticeId === selectedId && (!c || c.status === 'active')) return `<button class="text-button experience-back" data-view="clinic">← Volver al consultorio</button><section class="care-paper" role="alert"><div class="eyebrow">DOCTOR SALCHICHER · CONSULTA CERRADA</div><h2>Patita, busca ayuda ahora.</h2><p>Esto necesita ayuda sanitaria inmediata. Si te cuesta respirar, tienes dolor en el pecho, te desmayas, notas confusión repentina o una reacción alérgica fuerte, llama al 112 ahora y pide ayuda a alguien cercano.</p><p>No esperes otra respuesta de este chat ni conduzcas tú. Salchicher no puede valorar una urgencia por aquí.</p><small>${c?.retained ? 'Tu consulta guardada seguirá en el cuaderno.' : 'La consulta temporal se ha cerrado y eliminado. Este aviso no guarda tus síntomas.'}</small></section>`;
      if (!c) return `<button class="text-button experience-back" data-view="clinic">← Volver al consultorio</button><div class="experience-empty"><h2>${error ? 'No hemos podido abrir el cuaderno.' : 'Preparando tu sillón…'}</h2><p role="status">${esc(error || 'Buscando esta consulta en tu espacio privado.')}</p>${error ? '<button class="button secondary" data-clinic-refresh>Volver a comprobar</button>' : ''}</div>`;
      const ongoing = c.status === 'active';
      return `<div class="consultation-topline"><button class="text-button" data-view="clinic">← El consultorio</button><span class="consultation-status ${esc(c.status)}">${esc(tag(c))}</span></div>${demoNote()}<div class="consultation-heading"><div class="eyebrow">UN RATITO CONTIGO</div><h1>${esc(c.title || 'Tu consulta con Salchicher.')}</h1><p>${ongoing ? 'Sin prisas, Patita. Vamos pasito a pasito.' : 'Un cuaderno cerrado que puedes volver a leer.'}</p></div><div class="consultation-layout"><section class="consultation-room" aria-label="Consulta con Salchicher"><div class="consultation-room-label">${icon('heart')} ${ongoing ? 'LAS OREJITAS ESTÁN ESCUCHANDO' : 'UNA PÁGINA DE TU HISTORIA'}</div><div class="consultation-transcript" id="consultation-transcript" role="log" aria-label="Conversación de esta consulta" aria-live="polite">${transcript(c)}</div><div id="consultation-note" class="consultation-note" role="status">${esc(note)}</div>${ongoing ? `<form id="consultation-form" class="consultation-composer"><label class="sr-only" for="consultation-input">Cuéntale a Salchicher</label><textarea id="consultation-input" maxlength="4000" rows="2" placeholder="Me pasa que…" required></textarea><button class="send-button" aria-label="Enviar a Salchicher" ${busy || pendingSend() ? 'disabled' : ''}>${icon('send')}</button></form><div class="consultation-footer"><span>${c.retained ? 'Esta consulta se guardará en tu cuaderno.' : 'Esta consulta temporal se borra tras 48 h sin actividad.'}</span><button class="button secondary" data-consultation-close="${esc(c.id)}" ${busy ? 'disabled' : ''}>${icon('check')} Ya me encuentro bien</button></div>` : `<div class="consultation-closed"><p>${c.status === 'inactive' ? (c.closure_reason === 'urgent_help' ? 'Salchicher ha cerrado esta consulta para que busques atención sanitaria. No es un alta médica.' : 'Se cerró por falta de actividad; no es una confirmación de recuperación.') : 'Cerraste esta consulta al indicar que te encontrabas bien.'}</p><button class="button secondary" data-consultation-new ${enabled('salchicher') && !active() ? '' : 'disabled'}>Empezar otra consulta ${icon('plus')}</button></div>`}</section><div id="consultation-summary">${summaryCard(c)}</div></div>`;
    }
    function wishes() {
      const all = ctx.wishes();
      return all.filter(w => (wishFilter !== 'favorites' || w.favorite) && `${w.name} ${w.details || ''}`.toLocaleLowerCase('es').includes(wishSearch.toLocaleLowerCase('es')));
    }
    function wishCards() {
      const rows = wishes();
      if (!rows.length) return `<div class="experience-empty wish-empty"><span>✧</span><h3>${wishSearch || wishFilter === 'favorites' ? 'Aquí todavía no hay estrellas.' : '¿Qué te haría ilusión?'}</h3><p>${wishSearch ? 'Prueba con otras palabras.' : 'Un libro, una excursión, una tontería preciosa…<br>Este cuaderno tiene sitio para todo.'}</p></div>`;
      return rows.map((w, i) => { const link = safeUrl(w.url); return `<article class="wish-card tone-${i % 3}"><div class="wish-card-top"><span>ILUSIÓN ${String(i + 1).padStart(2, '0')}</span><button class="icon-button wish-favorite ${w.favorite ? 'selected' : ''}" data-vaca-favorite="${esc(w.id)}" aria-label="${w.favorite ? 'Quitar de favoritas' : 'Marcar como favorita'}: ${esc(w.name)}" aria-pressed="${Boolean(w.favorite)}" ${enabled('vaca') ? '' : 'disabled'}>${w.favorite ? '★' : '☆'}</button></div><h3>${esc(w.name)}</h3>${w.details ? `<p>${esc(w.details)}</p>` : '<p class="wish-card-flower" aria-hidden="true">ꕤ</p>'}<div class="wish-card-bottom">${link ? `<a class="text-button" href="${esc(link)}" target="_blank" rel="noopener noreferrer">Ver el detalle ↗</a>` : '<span>Guardado con ilusión</span>'}<button class="icon-button" data-vaca-remove="${esc(w.id)}" aria-label="Quitar deseo: ${esc(w.name)}" ${enabled('vaca') ? '' : 'disabled'}>${icon('trash')}</button></div></article>`; }).join('');
    }
    function letterCards() {
      if (lettersError) return `<p class="experience-notice" role="status">${esc(lettersError)} <button class="text-button" data-vaca-letters>Volver a abrir el buzón</button></p>`;
      const list = isDemo() ? [{ id: 'demo-letter', text: 'Patita, he abierto mi cuaderno por tu página favorita: la que todavía está por escribir. ¿Qué cosa pequeña te haría muuucha ilusión?', created_at: null }] : letters;
      if (!list.length) return `<div class="experience-empty"><span>✉</span><h3>${lettersLoading ? 'Abriendo el buzón…' : 'Un buzón para las cosas bonitas.'}</h3><p>${lettersLoading ? 'Buscando las cartas que ya te han llegado.' : 'Aquí aparecerán los mensajes que la Vaca ya te haya enviado.'}</p>${lettersMore ? '<button class="text-button" data-vaca-more>Buscar en mensajes anteriores</button>' : ''}</div>`;
      return `<div class="vaca-letters">${list.map(m => `<button class="vaca-letter" data-vaca-letter-id="${esc(m.id)}"><span class="letter-seal">✦</span><span class="letter-date">${isDemo() ? 'CARTA DE EJEMPLO' : esc(formatDate(m.created_at || m.time))}</span><h3>De la Vaca,<br>con muuuucho cariño.</h3><p>${esc(String(m.text).slice(0, 170))}${m.text.length > 170 ? '…' : ''}</p><span class="text-button">Abrir carta ${icon('arrow')}</span></button>`).join('')}</div>${!isDemo() && lettersMore ? `<button class="text-button" data-vaca-more ${lettersLoading ? 'disabled' : ''}>${lettersLoading ? 'Buscando más cartas…' : 'Leer mensajes anteriores'}</button>` : ''}`;
    }
    function vaca() {
      return `<section class="experience-hero vaca-hero"><div class="experience-hero-copy"><div class="eyebrow">${icon('star')} EL ESTABLO DE LAS ILUSIONES</div><h1>Las cosas bonitas<br>empiezan con un<br><em>«me haría ilusión».</em></h1><p>La Vaca Mágica guarda tus deseos<br>entre lazos, estrellas y páginas de cuento.</p><div class="experience-hero-actions"><button class="button" data-vaca-new ${enabled('vaca') ? '' : 'disabled'}>${icon('plus')} Apuntar una ilusión</button><button class="text-button" data-vaca-chat>Escribir a la Vaca ${icon('arrow')}</button></div></div><div class="experience-hero-art">${portrait('vaca')}<span class="vaca-art-label">se aceptan deseos<br><em>de todos los tamaños</em></span><span class="hero-spark first">✧</span></div></section>${isDemo() ? '<p class="experience-demo">✧ Estás recorriendo el cuaderno de ejemplo. Nada se envía a los bots.</p>' : ''}${unavailable('vaca')}<section class="vaca-notebook"><div class="experience-section-heading"><div><div class="eyebrow">AQUÍ LAS ILUSIONES TIENEN SITIO</div><h2>Mi cuaderno de deseos.</h2></div><span id="wish-count">${ctx.wishes().length} ${ctx.wishes().length === 1 ? 'ilusión' : 'ilusiones'}</span></div><div class="wish-toolbar"><div class="experience-tabs" aria-label="Filtrar deseos"><button data-vaca-filter="all" aria-pressed="${wishFilter === 'all'}" class="${wishFilter === 'all' ? 'active' : ''}">Todos mis deseos</button><button data-vaca-filter="favorites" aria-pressed="${wishFilter === 'favorites'}" class="${wishFilter === 'favorites' ? 'active' : ''}">★ Mis favoritas</button></div><label class="wish-search"><span class="sr-only">Buscar en mis deseos</span><input id="vaca-search" type="search" value="${esc(wishSearch)}" placeholder="Buscar una ilusión…"></label></div><div class="wish-card-grid" id="vaca-wishes">${wishCards()}</div><p class="vaca-promise">✧ Apuntar un deseo no promete un regalo. Aquí también se viene a imaginar.</p></section><section class="vaca-mailbox"><div class="experience-section-heading"><div><div class="eyebrow">SOBRES QUE YA HAN LLEGADO</div><h2>El buzón de la Vaca.</h2></div><button class="text-button" data-vaca-letters ${enabled('vaca') ? '' : 'disabled'}>Abrir el buzón ${icon('arrow')}</button></div><div id="vaca-letter-list">${letterCards()}</div></section>`;
    }
    function refreshClinic() {
      if (route !== 'clinic') return;
      document.getElementById('main').innerHTML = clinic();
    }
    function refreshDetail(force = false) {
      if (route !== 'consultation') return;
      const c = detail;
      const log = document.getElementById('consultation-transcript');
      if (!log || force) { document.getElementById('main').innerHTML = consultation(); bindDetail(); return; }
      if (!c || c.id !== selectedId) return;
      const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 100;
      const html = transcript(c); if (log.innerHTML !== html) log.innerHTML = html;
      if (nearBottom) log.scrollTop = log.scrollHeight;
      document.getElementById('consultation-summary').innerHTML = summaryCard(c);
      const notice = document.getElementById('consultation-note'); if (notice) notice.textContent = note;
      const sendButton = document.querySelector('#consultation-form button'); if (sendButton) sendButton.disabled = busy || pendingSend();
      const closeButton = document.querySelector('[data-consultation-close]'); if (closeButton) closeButton.disabled = busy;
    }
    function refreshWishes() {
      if (route !== 'vaca') return;
      document.getElementById('vaca-wishes').innerHTML = wishCards();
      document.getElementById('wish-count').textContent = `${ctx.wishes().length} ${ctx.wishes().length === 1 ? 'ilusión' : 'ilusiones'}`;
    }
    async function loadConsultations() {
      if (isDemo() || !enabled('salchicher')) return;
      const version = generation, epoch = ctx.epoch();
      try {
        const data = await bridge.consultations(controller?.signal);
        if (version !== generation || epoch !== ctx.epoch()) return;
        if (!Array.isArray(data.consultations)) throw new Error('No hemos podido abrir tu cuaderno de cuidados.');
        consultations = data.consultations; activeId = data.active_id; loaded = true; error = ''; refreshClinic();
      } catch (err) { if (version !== generation || epoch !== ctx.epoch() || err.cancelled) return; error = err.status === 404 ? 'El nuevo consultorio está preparado, pero todavía no está activado en el servidor.' : err.message; refreshClinic(); }
    }
    async function loadDetail() {
      if (isDemo()) { detail = demoConsultations.find(c => c.id === selectedId) || null; refreshDetail(); return; }
      if (!enabled('salchicher')) return;
      const version = generation, epoch = ctx.epoch(), id = selectedId;
      try {
        const data = await bridge.consultation(id, controller?.signal);
        if (version !== generation || epoch !== ctx.epoch() || id !== selectedId) return;
        if (!data.consultation || data.consultation.id !== id) throw new Error('No se encuentra esta consulta.');
        const changedStatus = detail?.status !== data.consultation.status;
        detail = data.consultation; mergeConsultation(detail); error = ''; refreshDetail(changedStatus);
      } catch (err) { if (version !== generation || epoch !== ctx.epoch() || err.cancelled) return; error = err.message; if (err.status === 404) { detail = null; refreshDetail(true); } else { note = err.message; refreshDetail(); } }
    }
    async function loadLetters(more = false) {
      if (isDemo() || !enabled('vaca') || lettersLoading) return;
      const version = generation, epoch = ctx.epoch(), letterRequestVersion = lettersVersion; lettersLoading = true; lettersError = '';
      try {
        const data = await bridge.history('vaca', more ? lettersCursor : null, controller?.signal);
        if (version !== generation || epoch !== ctx.epoch() || letterRequestVersion !== lettersVersion) return;
        const received = (data.messages || []).filter(m => m.role === 'assistant' && typeof m.text === 'string');
        const byId = new Map((more ? letters : []).map(m => [String(m.id), m])); received.forEach(m => byId.set(String(m.id), m));
        letters = [...byId.values()].sort((a, b) => new Date(dateValue(b.created_at || b.time || 0)) - new Date(dateValue(a.created_at || a.time || 0)));
        lettersCursor = data.next_cursor; lettersMore = Boolean(data.has_more);
      } catch (err) { if (version === generation && epoch === ctx.epoch() && letterRequestVersion === lettersVersion && !err.cancelled) lettersError = err.message; }
      finally { if (version === generation && letterRequestVersion === lettersVersion) { lettersLoading = false; if (route === 'vaca') document.getElementById('vaca-letter-list').innerHTML = letterCards(); } }
    }
    function newConsultation() {
      const open = active(); if (open) { ctx.navigate('consultation', open.id); return; }
      if (!enabled('salchicher') || busy) return;
      ctx.showModal(`<div class="eyebrow">${icon('heart')} PASA, PATITA</div><h2 id="modal-title">Te estaba guardando<br>el mejor sillón.</h2><p>Salchicher te hará unas preguntas y te acompañará con cuidados generales. Es un personaje con IA, no un médico, y no emitirá un diagnóstico.</p><div class="consultation-consent"><p>Esta consulta es privada. Tus mensajes se procesan con IA de OpenAI y no se comparten con el Oso, los cuentos ni el lore.</p><label><input type="checkbox" id="consultation-retain"><span><strong>Guardar esta consulta en mi cuaderno</strong><small>Podré releerla y borrarla cuando quiera. Se cerrará tras 30 días sin actividad, pero seguirá en mi historial.</small></span></label><p class="consent-temporary">Si no la guardas, se eliminará tras 48 horas sin actividad. ${isDemo() ? 'En este boceto, todas las consultas son de ejemplo y duran solo esta sesión.' : ''}</p></div><button class="button" data-consultation-start>Entendido, iniciar consulta ${icon('arrow')}</button><p class="experience-modal-note" id="experience-modal-note" role="status"></p>`);
    }
    async function act(action, id) {
      if (busy || !enabled('salchicher')) return;
      const epoch = ctx.epoch(), version = generation; busy = true;
      const keep = Boolean(document.getElementById('consultation-retain')?.checked);
      const button = document.querySelector('[data-consultation-start], [data-consultation-confirm]'); if (button) button.disabled = true;
      try {
        let result;
        if (isDemo()) {
          if (action === 'start') {
            if (active()) throw new Error('Ya tienes una consulta abierta.');
            const c = { id: ctx.uid(), status: 'active', retained: keep, created_at: stamp(), updated_at: stamp(), title: 'Un ratito de cuidados', care_summary: [], messages: [{ role: 'assistant', content: 'Pasa, Patita. Me ajusto las gafitas y dejo mi cuaderno abierto. ¿Qué te trae hoy por aquí?', created_at: stamp() }] };
            demoConsultations.unshift(c); result = { consultation: c };
          } else {
            const c = demoConsultations.find(c => c.id === id); if (!c) throw new Error('No se encuentra esta consulta.');
            if (action === 'delete') { demoConsultations = demoConsultations.filter(c => c.id !== id); result = { deleted: true }; }
            else { c.status = 'recovered'; c.closed_at = stamp(); if (!c.retained) demoConsultations = demoConsultations.filter(x => x.id !== id); result = { consultation: c.retained ? c : null }; }
          }
        } else result = await bridge.consultationAction(action === 'start' ? { action, retain_history: keep } : { action, consultation_id: id });
        if (epoch !== ctx.epoch() || version !== generation) return;
        if (!isDemo()) mergeConsultation(result.consultation || null, id);
        ctx.closeModal(); note = ''; receipt = null; busy = false;
        if (result.consultation) { detail = result.consultation; selectedId = detail.id; ctx.navigate('consultation', detail.id); }
        else { detail = null; ctx.navigate('clinic'); }
        ctx.toast(action === 'delete' ? 'Consulta borrada de tu cuaderno.' : action === 'close' ? 'Consulta cerrada. Qué alegría que te encuentres mejor, Patita.' : 'El sillón está preparado para ti.');
      } catch (err) {
        if (epoch !== ctx.epoch() || version !== generation) return;
        const target = document.getElementById('experience-modal-note');
        if (target) target.textContent = err.uncertain ? 'No hemos podido confirmar el cambio. Cierra esta ventana y comprueba tu cuaderno antes de repetirlo.' : err.message;
        if (err.code === 'consultation_active') loadConsultations();
      } finally { if (epoch === ctx.epoch()) { busy = false; refreshDetail(); } if (button?.isConnected) button.disabled = false; }
    }
    function confirmAction(action, id) {
      if (busy) return;
      ctx.showModal(`<div class="eyebrow">${icon(action === 'delete' ? 'book' : 'heart')} TU CUADERNO, A TU MANERA</div><h2 id="modal-title">${action === 'delete' ? '¿Borramos esta consulta?' : '¿Ya te encuentras bien, Patita?'}</h2><p>${action === 'delete' ? 'Se eliminará su conversación y su resumen del consultorio. Las copias que ya existan en Telegram se gestionan desde Telegram.' : 'Quedará anotado que tú has indicado que te encuentras bien. Si elegiste guardarla, podrás volver a leerla en tu cuaderno; si era temporal, se borrará al cerrar.'}</p><button class="button" data-consultation-confirm="${action}" data-consultation-id="${esc(id)}">${action === 'delete' ? 'Sí, borrar esta consulta' : 'Sí, cerrar mi consulta'}</button><p id="experience-modal-note" class="experience-modal-note" role="status"></p>`);
    }
    function bindDetail() {
      const form = document.getElementById('consultation-form'); if (!form) return;
      form.addEventListener('submit', event => { event.preventDefault(); send(); });
    }
    async function send() {
      const input = document.getElementById('consultation-input'), text = input?.value.trim();
      if (!text || busy || pendingSend() || detail?.status !== 'active' || !enabled('salchicher')) return;
      const epoch = ctx.epoch(), version = generation, id = selectedId; busy = true;
      const button = document.querySelector('#consultation-form button'); if (button) button.disabled = true;
      note = 'Acercando tu nota al doctor…'; refreshDetail();
      try {
        if (isDemo()) {
          const c = demoConsultations.find(c => c.id === id);
          c.messages.push({ role: 'user', content: text, created_at: stamp() });
          c.messages.push({ role: 'assistant', content: window.CastoriDialogue.reply('salchicher', text, []), created_at: stamp() });
          c.updated_at = stamp(); detail = c; note = 'Respuesta de ejemplo. Esta consulta no se envía a los bots.';
        } else {
          const requestId = ctx.uid(); receipt = { id: requestId, consultation: id, pending: true, text };
          const result = await bridge.consultationMessage({ consultation_id: id, text, request_id: requestId });
          if (version !== generation || epoch !== ctx.epoch()) return;
          receipt.pending = result.status === 'pending'; note = result.status === 'rejected' ? 'La consulta ya no admite este mensaje.' : 'Salchicher ha recibido tu nota. Su respuesta aparecerá aquí.';
          if (result.notice === 'urgent_help') { urgentNoticeId = id; refreshDetail(true); }
        }
        if (version !== generation || epoch !== ctx.epoch()) return;
        if (input?.isConnected && input.value.trim() === text) input.value = ''; refreshDetail(); if (!isDemo()) await loadDetail();
      } catch (err) {
        if (version !== generation || epoch !== ctx.epoch()) return;
        note = err.uncertain ? 'No se pudo confirmar el envío. Estamos comprobándolo; no repitas el mensaje todavía.' : err.message;
        if (!err.uncertain) receipt = null;
        refreshDetail();
      } finally { if (epoch === ctx.epoch()) { busy = false; refreshDetail(); } if (button?.isConnected) button.disabled = pendingSend(); }
    }
    function wishForm() {
      if (!enabled('vaca')) return;
      ctx.showModal(`<div class="eyebrow">${icon('star')} UNA PÁGINA PARA UNA ILUSIÓN</div><h2 id="modal-title">Me haría ilusión…</h2><p>Grande, pequeña o de esas que dan un poquito de risa. Cuéntaselo a la Vaca.</p><form id="vaca-wish-form" class="vaca-wish-form"><label>Tu deseo<input id="vaca-wish-name" maxlength="240" required placeholder="Un libro para leer bajo la manta…"></label><label>Un enlace, si lo tienes <small>opcional</small><input id="vaca-wish-url" type="url" maxlength="1200" placeholder="https://…"></label><button class="button" type="submit">${icon('plus')} Guardar mi ilusión</button><p class="experience-modal-note" id="vaca-wish-note" role="status"></p></form>`);
      document.getElementById('vaca-wish-form').addEventListener('submit', async event => {
        event.preventDefault(); const name = document.getElementById('vaca-wish-name').value.trim(), raw = document.getElementById('vaca-wish-url').value.trim();
        if (!name || raw && !safeUrl(raw)) { document.getElementById('vaca-wish-note').textContent = 'Utiliza un enlace que empiece por https:// o http://.'; return; }
        const button = event.currentTarget.querySelector('button'); button.disabled = true;
        const epoch = ctx.epoch();
        if (isDemo()) { ctx.demoWish('add', { id: ctx.uid(), text: name, url: raw, favorite: false }); ctx.closeModal(); refreshWishes(); ctx.toast('Ilusión guardada en el cuaderno del boceto.'); return; }
        const accepted = await ctx.submitLive('vaca', '/pedir ' + name + (raw ? ' ' + raw : ''));
        if (epoch !== ctx.epoch()) return;
        if (accepted) { ctx.closeModal(); ctx.toast('La Vaca ha recibido tu deseo. Aparecerá cuando quede guardado.'); }
        else if (button.isConnected) { button.disabled = false; document.getElementById('vaca-wish-note').textContent = 'No se pudo confirmar el envío. Comprueba la conversación antes de repetirlo.'; }
      });
    }
    async function wishAction(action, id) {
      if (!enabled('vaca')) return;
      if (isDemo()) { ctx.demoWish(action, { id }); refreshWishes(); return; }
      await ctx.submitLive('vaca', (action === 'favorite' ? '/favorito ' : '/quitar ') + id);
    }
    function showLetter(id) {
      const m = isDemo() ? { text: 'Patita, he abierto mi cuaderno por tu página favorita: la que todavía está por escribir. ¿Qué cosa pequeña te haría muuucha ilusión?' } : letters.find(x => String(x.id) === id);
      if (!m) return;
      ctx.showModal(`<div class="eyebrow">${icon('star')} ${isDemo() ? 'CARTA DE EJEMPLO' : 'DEL BUZÓN DE LA VACA'}</div><h2 id="modal-title">Para Patita,<br>con muuuucho cariño.</h2><p class="story-delivered-date">${esc(formatDate(m.created_at || m.time))}</p><div class="story-text">${esc(m.text)}</div><div class="story-signature">La Vaca Mágica.</div><button class="button secondary" data-vaca-chat>Contestar a la Vaca ${icon('arrow')}</button>`);
    }
    async function handle(button) {
      const b = button.dataset;
      if (button.hasAttribute('data-consultation-new')) newConsultation();
      else if (b.consultationOpen) ctx.navigate('consultation', b.consultationOpen);
      else if (button.hasAttribute('data-consultation-start')) await act('start');
      else if (b.consultationClose) confirmAction('close', b.consultationClose);
      else if (b.consultationDelete) confirmAction('delete', b.consultationDelete);
      else if (b.consultationConfirm) await act(b.consultationConfirm, b.consultationId);
      else if (button.hasAttribute('data-clinic-refresh')) { if (route === 'consultation') await loadDetail(); else await loadConsultations(); }
      else if (button.hasAttribute('data-clinic-history')) document.getElementById('clinic-history')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      else if (button.hasAttribute('data-vaca-new')) wishForm();
      else if (button.hasAttribute('data-vaca-chat')) ctx.navigate('chat', 'vaca', true, true);
      else if (b.vacaFilter) { wishFilter = b.vacaFilter === 'favorites' ? 'favorites' : 'all'; document.querySelectorAll('[data-vaca-filter]').forEach(x => { const selected = x.dataset.vacaFilter === wishFilter; x.classList.toggle('active', selected); x.setAttribute('aria-pressed', selected); }); refreshWishes(); }
      else if (b.vacaFavorite) await wishAction('favorite', b.vacaFavorite);
      else if (b.vacaRemove) await wishAction('remove', b.vacaRemove);
      else if (button.hasAttribute('data-vaca-letters')) await loadLetters();
      else if (button.hasAttribute('data-vaca-more')) await loadLetters(true);
      else if (b.vacaLetterId) showLetter(b.vacaLetterId);
      else return false;
      return true;
    }
    function clearLetters() { lettersVersion++; lettersLoading = false; letters = []; lettersCursor = null; lettersMore = false; lettersError = ''; if (route === 'vaca') { const list = document.getElementById('vaca-letter-list'); if (list) list.innerHTML = letterCards(); } }
    function leave() { generation++; clearTimeout(timer); controller?.abort(); controller = null; if (route === 'vaca') clearLetters(); route = ''; lettersLoading = false; }
    function clear() { leave(); consultations = []; demoConsultations = []; activeId = null; detail = null; loaded = false; error = ''; note = ''; receipt = null; urgentNoticeId = null; clearLetters(); busy = false; selectedId = ''; }
    function render(next, id) { route = next; if (next === 'consultation') selectedId = id || selectedId; return next === 'clinic' ? clinic() : next === 'consultation' ? consultation() : vaca(); }
    function enter(next) {
      route = next; controller = new AbortController(); const version = generation;
      if (next === 'clinic') loadConsultations();
      if (next === 'consultation') { bindDetail(); loadDetail(); }
      if (next === 'vaca') { document.getElementById('vaca-search').addEventListener('input', event => { wishSearch = event.target.value.slice(0, 160); refreshWishes(); }); loadLetters(); }
      if (ctx.mode() !== 'live') return;
      const poll = async () => {
        if (version !== generation) return;
        try {
          if (route === 'consultation') {
            if (receipt?.pending && receipt.consultation === selectedId) {
              try {
                const data = await bridge.receipt(receipt.id); if (version !== generation) return;
                if (data.notice === 'urgent_help') { urgentNoticeId = selectedId; refreshDetail(true); }
                if (data.status !== 'pending') {
                  receipt.pending = false; note = data.status === 'processed' ? 'Salchicher ha recibido tu nota. Su respuesta aparecerá aquí.' : 'No se pudo confirmar el envío. No lo repetiremos automáticamente.';
                  const input = document.getElementById('consultation-input'); if (data.status === 'processed' && input?.value.trim() === receipt.text) input.value = '';
                }
              } catch (err) { if (version !== generation) return; if (err.code === 'request_not_found') { receipt.pending = false; note = 'No se ha registrado ese envío. Puedes comprobar la conversación y volver a enviarlo.'; } }
            }
            await loadDetail();
          } else if (route === 'vaca') await ctx.refreshState(controller.signal);
        } catch (_) { /* Each view retains its last confirmed data; no fake fallback. */ }
        if (version === generation) timer = setTimeout(poll, route === 'consultation' ? 3000 : 7000);
      };
      if (next !== 'clinic') timer = setTimeout(poll, 3000);
    }
    return { render, enter, leave, clear, clearLetters, handle, refreshWishes, selectedId: () => selectedId };
  } };
}());

(function (root) {
  'use strict';

  const doc = root.document;
  const START = Date.parse('2026-11-05T00:00:00+01:00');
  const VISIT_START = Date.parse('2026-11-13T00:00:00+01:00');
  const END = Date.parse('2026-11-14T00:00:00+01:00');
  const SEEN_KEY = 'castori.vaca-arrival.2026-11.v1';
  const SOUND_KEY = 'castori.vaca-arrival.sound.v1';
  const DURATION = 26000;
  const clock = () => root.performance?.now() ?? Date.now();
  const news = [
    { title: 'La Vaca ha abandonado la Castora Celestial.', text: 'Mimosuga confirma: falta una vaca y sobra purpurina.', aside: '«¡MUUU! No me he escapado. He salido sin avisar.»' },
    { title: 'Autopista astral abierta', text: 'Peaje pagado con tres campanillas. Tráfico de renos desviado. Destino: Casa Tosico.', aside: '«¡Muuu! El peaje se ha quedado con mi lazo. ¡Era de regalo!»' },
    { title: '¡Llegada inminente!', text: 'Despejad balcones. Sujetad macetas. Dejad un poquito de sitio para lo imposible.', aside: '«¡Patita, haz sitio! Lo del lazo en el cuerno estaba planeado. MUUU.»' }
  ];
  const acts = [
    { label: '00 · PROTOCOLO DE LLEGADA', title: '¡ALERTA VACUNA!', text: 'La Vaca ha tocado el botón que ponía NO TOCAR.', aside: '«Muuu… ¿y si lo vuelvo a tocar?»' },
    { label: '01 · DESPEGUE CONFIRMADO', title: '¡LA VACA HA SALIDO!', text: 'Ha abandonado la Castora Celestial. Mimosuga confirma: falta una vaca y sobra purpurina.', aside: '«No me he escapado. La puerta estaba MUUUY abierta.»' },
    { label: '02 · HIPERESPACIO', title: '¡AUTOPISTA ASTRAL ABIERTA!', text: 'Peaje pagado con tres campanillas. Tráfico de renos desviado. Destino: Casa Tosico.', aside: '«¡Muuu! El peaje se ha quedado con mi lazo. ¡Era de regalo!»' },
    { label: '03 · APROXIMACIÓN A CASA TOSICO', title: '¡DESPEJAD LOS BALCONES!', text: 'La llegada es inminente. Sujetad macetas. Dejad sitio para lo imposible.', aside: '«¡Patita, haz sitio! Lo del lazo en el cuerno estaba planeado. MUUU.»' }
  ];
  const arrivalNews = [
    { title: '¡La Vaca ha venido!', text: '13 de noviembre. Casa Tosico confirma la visita nocturna más MUUUy esperada.', aside: '«Patita, esta noche he estado aquí. Lo del sigilo lo dejamos para otro año.»' },
    { title: 'Autopista astral: trayecto completado', text: 'De la Castora Celestial a Casa Tosico. Tres campanillas de peaje y una entrada triunfal.', aside: '«He llegado con todas las pezuñas. El lazo ha viajado por su cuenta.»' },
    { title: 'Hoy se celebra. El radar descansa.', text: 'Las predicciones vuelven mañana. Hoy la noticia es que la Vaca ya ha pasado por aquí.', aside: '«¡MUUU! Mira bien a tu alrededor, Patita. Yo solo digo eso.»' }
  ];
  const arrivalActs = [
    { label: '00 · ÚLTIMA HORA', title: '¡MUUU! ¡HE ESTADO AQUÍ!', text: 'Patita, esto ya no es una predicción. La Vaca ha venido a Casa Tosico.', aside: '«¿Entrar discretamente? No me sonaba esa parte del plan.»' },
    { label: '01 · ASÍ EMPEZÓ TODO', title: '¡UNA VACA A LA FUGA!', text: 'Salí de la Castora Celestial con una misión MUUUY importante. Y sin pedir permiso al botón rojo.', aside: '«Mimosuga, si preguntan… yo ya estaba de camino.»' },
    { label: '02 · TRAYECTO COMPLETADO', title: '¡PEAJE PAGADO. MISIÓN CUMPLIDA!', text: 'Crucé la autopista astral y llegué a Casa Tosico. El lazo sobrevivió. Más o menos.', aside: '«Tres campanillas. Ni una más. El regateo fue espectacular.»' },
    { label: '03 · 13 DE NOVIEMBRE · VISITA CONFIRMADA', title: '¡LA VACA HA VENIDO!', text: 'Hoy no hay porcentajes: hay una visita que celebrar. El radar vuelve mañana.', aside: '«Mira bien a tu alrededor, Patita. ¡MUUU!»' }
  ];
  let active = null, soundMuted = false, soundPreferenceRead = false;
  const seenInMemory = new Set();
  const now = () => root.CastoriChristmas?.now() ?? Date.now();
  const phase = (time = now()) => time < VISIT_START ? 'before' : 'arrival';
  const seenKey = visitPhase => visitPhase === 'arrival' ? 'castori.vaca-visit.2026-11-13.v1' : SEEN_KEY;
  const available = (time = now()) => time >= START && time < END;
  const accessible = (time = now()) => doc?.body?.dataset.access === 'open' && doc.visibilityState !== 'hidden' && available(time);

  function seen(visitPhase = phase()) {
    const key = seenKey(visitPhase);
    try { if (root.localStorage.getItem(key) === '1') seenInMemory.add(key); } catch (_) { /* Memory keeps replay working in private browsing. */ }
    return seenInMemory.has(key);
  }
  function remember(visitPhase) {
    const key = seenKey(visitPhase);
    seenInMemory.add(key);
    try { root.localStorage.setItem(key, '1'); } catch (_) { /* Reading the message never depends on storage. */ }
    for (const button of doc.querySelectorAll('[data-vaca-arrival-play]')) {
      const title = button.querySelector('.vaca-arrival-button-copy > strong');
      const badge = button.querySelector('.vaca-arrival-new');
      if (title) title.textContent = visitPhase === 'arrival' ? '¡MUUU! ¡La Vaca ha venido!' : 'Repetir mensaje';
      if (badge) { badge.textContent = 'REPLAY'; badge.setAttribute('aria-label', 'Mensaje visto'); }
    }
  }
  function preferences(media) {
    let value = {};
    try { value = root.CastoriChristmas?.preferences?.() || {}; } catch (_) { /* Effects are optional. */ }
    return {
      // christmas-paused also describes a temporarily hidden document. Only the
      // explicit preference may skip a newly opened, visible performance.
      motionPaused: value.motionPaused === true,
      reducedMotion: value.reducedMotion === true || media?.matches === true
    };
  }
  function readSoundPreference() {
    if (soundPreferenceRead) return;
    soundPreferenceRead = true;
    try {
      const saved = root.localStorage.getItem(SOUND_KEY);
      if (saved === 'muted' || saved === 'on') soundMuted = saved === 'muted';
    } catch (_) { /* Keep the user's choice in memory when storage is unavailable. */ }
  }
  function saveSoundPreference(muted) {
    soundMuted = muted;
    try { root.localStorage.setItem(SOUND_KEY, muted ? 'muted' : 'on'); } catch (_) { /* Still applies to this visit. */ }
  }
  function cardContent(visitPhase) {
    const replay = seen(visitPhase);
    const arrived = visitPhase === 'arrival';
    return `<button type="button" class="vaca-arrival-trigger" data-vaca-arrival-play aria-haspopup="dialog" aria-controls="vaca-arrival">
        <span class="vaca-arrival-beacon" aria-hidden="true">✦</span>
        <span class="vaca-arrival-button-copy"><small>${arrived ? 'ÚLTIMA HORA · 13 DE NOVIEMBRE' : 'ESTAFETA ASTRAL · CASA TOSICO'}</small><strong>${arrived ? '¡MUUU! ¡La Vaca ha venido!' : replay ? 'Repetir mensaje' : 'Tienes un mensaje de la Vaca'}</strong><span>${arrived ? '«Esta noche he estado aquí, Patita.» Abre el parte de la visita.' : 'La Castora Celestial acaba de emitir un comunicado.'}</span></span>
        <span class="vaca-arrival-new" aria-label="${replay ? 'Mensaje visto' : 'Un mensaje nuevo'}">${replay ? 'REPLAY' : '1'}</span>
        <span class="vaca-arrival-button-arrow" aria-hidden="true">↗</span>
      </button>`;
  }
  function render() {
    const time = now(), visitPhase = phase(time);
    if (!available(time)) return '';
    return `<section class="vaca-arrival-card${visitPhase === 'arrival' ? ' vaca-visit-card' : ''}" data-vaca-arrival data-vaca-arrival-phase="${visitPhase}" aria-label="Un comunicado de la Vaca">${cardContent(visitPhase)}</section>`;
  }
  function refresh() {
    const time = now(), visitPhase = phase(time);
    if (active && (!accessible(time) || active.phase !== visitPhase)) finish(active, 'expired');
    const card = doc?.querySelector('[data-vaca-arrival]');
    if (!card) return;
    if (!available(time)) { card.remove(); return; }
    if (card.getAttribute('data-vaca-arrival-phase') !== visitPhase) {
      card.innerHTML = cardContent(visitPhase);
      card.setAttribute('data-vaca-arrival-phase', visitPhase);
      card.classList.toggle('vaca-visit-card', visitPhase === 'arrival');
    }
  }
  function scene(visitPhase) {
    const arrived = visitPhase === 'arrival';
    const script = arrived ? arrivalActs : acts;
    const bulletin = arrived ? arrivalNews : news;
    const colors = ['#ffe16a', '#ff648e', '#6cf2df', '#b393ff', '#fff8d8'];
    const speedlines = Array.from({ length: 36 }, (_, i) => `<i style="--angle:${i * 10}deg;--delay:${(-i * .07).toFixed(2)}s"></i>`).join('');
    const fireworks = Array.from({ length: 3 }, (_, burst) => `<div class="arrival-burst" style="--x:${[20, 78, 52][burst]}%;--y:${[28, 30, 13][burst]}%;--burst-delay:${burst * .7}s">${Array.from({ length: 24 }, (_, i) => `<i style="--angle:${i * 15}deg;--distance:${115 + i % 5 * 16}px;--delay:${(burst * .7 + i % 3 * .035).toFixed(2)}s;--color:${colors[(i + burst) % colors.length]}"></i>`).join('')}</div>`).join('');
    const confetti = Array.from({ length: 100 }, (_, i) => `<i${i % 7 === 0 ? ' class="is-star"' : ''} style="--x:${(i * 37.7 % 100).toFixed(1)}%;--drift:${i % 2 ? 40 + i % 73 : -40 - i % 73}px;--delay:${(i % 17 * .09).toFixed(2)}s;--duration:${(3.8 + i % 9 * .43).toFixed(2)}s;--color:${colors[i % colors.length]}">${i % 7 === 0 ? '✦' : ''}</i>`).join('');
    const ribbon = arrived ? 'LA VACA HA VENIDO · VISITA CONFIRMADA · CASA TOSICO · MUUUY IMPORTANTE · ' : 'VACA EN RUTA · PRIORIDAD ABSOLUTA · DESTINO CASA TOSICO · ATENCIÓN A LOS BALCONES · ';
    return `<div class="arrival-film" aria-hidden="true">
        <div class="arrival-shot arrival-shot-departure"><picture><source media="(max-width:700px)" srcset="assets/vaca-arrival-departure-mobile.webp"><img src="assets/vaca-arrival-departure.webp" alt="" loading="eager" decoding="async" fetchpriority="high" width="1536" height="1024"></picture></div>
        <div class="arrival-shot arrival-shot-highway"><picture><source media="(max-width:700px)" srcset="assets/vaca-arrival-highway-mobile.webp"><img src="assets/vaca-arrival-highway.webp" alt="" loading="eager" decoding="async" width="1536" height="1024"></picture></div>
        <div class="arrival-shot arrival-shot-arrival"><picture><source media="(max-width:700px)" srcset="assets/vaca-arrival-arrival-mobile.webp"><img src="assets/vaca-arrival-arrival.webp" alt="" loading="eager" decoding="async" width="1536" height="1024"></picture></div>
      </div>
      <div class="arrival-speedlines" aria-hidden="true">${speedlines}</div><div class="arrival-fireworks" aria-hidden="true">${fireworks}</div><div class="arrival-confetti" aria-hidden="true">${confetti}</div><div class="arrival-siren" aria-hidden="true"><i></i><i></i></div>
      <div class="arrival-emergency-ribbon" aria-hidden="true"><span>${ribbon}</span><span>${ribbon}</span></div>
      <div class="arrival-theatre">
        <div class="arrival-toolbar"><span>✦ COMUNICADO DE LA CASTORA CELESTIAL</span><button type="button" class="vaca-arrival-close" aria-label="Cerrar el mensaje de la Vaca">Cerrar <span aria-hidden="true">×</span></button></div>
        <div class="arrival-live"><i aria-hidden="true"></i> ${arrived ? 'VISITA CONFIRMADA' : 'EN DIRECTO'}</div>
        <div class="arrival-alert-type" aria-hidden="true">MUUUY URGENTE</div>
        <div class="arrival-stamp" aria-hidden="true"><strong>${arrived ? 'MISIÓN CUMPLIDA' : 'VACA EN RUTA'}</strong><span>MISIÓN CASA TOSICO</span></div>
        <div class="arrival-caption" aria-live="polite" aria-atomic="true"><p class="arrival-act-label">${script[0].label}</p><h2 id="vaca-arrival-title">${script[0].title}</h2><p id="vaca-arrival-description">${script[0].text}</p><p class="vaca-arrival-aside arrival-aside">${script[0].aside}</p></div>
        <div class="arrival-route"><span>CASTORA CELESTIAL</span><i class="arrival-route-flight" aria-hidden="true">✦ ➜</i><span>CASA TOSICO</span></div>
        <ol class="vaca-arrival-summary" hidden aria-label="El comunicado completo">${bulletin.map(item => `<li><strong>${item.title}</strong><span>${item.text}</span><small>${item.aside}</small></li>`).join('')}</ol>
        <div class="arrival-progress" aria-label="Actos de la llegada"><span class="is-active" aria-current="step">00 · ALERTA</span><span>01 · DESPEGUE</span><span>02 · HIPERESPACIO</span><span>03 · LLEGADA</span></div>
        <div class="arrival-controls"><button type="button" class="vaca-arrival-mute" aria-pressed="true">Sonido: sí</button><button type="button" class="vaca-arrival-skip">Leer el mensaje completo</button><button type="button" class="vaca-arrival-close-final" hidden>${arrived ? '¡Recibido, Vaca! Voy a mirar.' : 'Entendido. Despejo el balcón.'}</button></div>
        <p class="arrival-footer">Servicio de mensajería mágica · No se admiten devoluciones de purpurina.</p>
      </div>`;
  }
  function clearTimers(run) { for (const timer of run.timers) clearTimeout(timer); run.timers.clear(); }
  function stopAudio(run) {
    run.soundGeneration++;
    const stop = run.stopSound; run.stopSound = null;
    try { stop?.(); } catch (_) { /* Optional sound cannot keep the scene open. */ }
  }
  function updateSoundButton(run) {
    const button = run.dialog.querySelector('.vaca-arrival-mute');
    const playing = !soundMuted && !run.soundBlocked && !run.soundEnded && !run.audioUnavailable;
    button.textContent = run.soundEnded ? 'Sonido finalizado' : run.audioUnavailable ? 'Sonido no disponible' : soundMuted ? 'Sonido: no' : run.soundBlocked ? 'Activar sonido' : 'Sonido: sí';
    button.disabled = run.soundEnded || run.audioUnavailable;
    button.setAttribute('aria-pressed', String(playing));
    button.setAttribute('aria-label', playing ? 'Silenciar sonido' : button.disabled ? button.textContent : 'Activar sonido');
  }
  function sound(run) {
    const engine = root.CastoriVacaArrivalAudio;
    if (typeof engine?.play !== 'function') { run.audioUnavailable = true; updateSoundButton(run); return; }
    stopAudio(run);
    const generation = run.soundGeneration;
    run.soundBlocked = false;
    const blocked = () => {
      if (active !== run || run.done || run.soundEnded || generation !== run.soundGeneration || soundMuted) return;
      run.soundBlocked = true; stopAudio(run); updateSoundButton(run);
    };
    try {
      // The engine creates/resumes audio synchronously inside this trusted click.
      const cleanup = engine.play({ duration: DURATION, offset: Math.max(0, clock() - run.startedAt), onBlocked: blocked,
        isAllowed: () => active === run && !run.done && !run.soundEnded && generation === run.soundGeneration && accessible() && !soundMuted });
      if (typeof cleanup !== 'function') { blocked(); return; }
      if (generation !== run.soundGeneration) { cleanup(); return; }
      run.stopSound = cleanup;
      if (cleanup.available === false) blocked();
    } catch (_) { blocked(); }
    updateSoundButton(run);
  }
  function toggleSound(run, event) {
    if (event?.isTrusted !== true || active !== run || run.done || run.soundEnded || !accessible()) return;
    if (soundMuted || run.soundBlocked) { saveSoundPreference(false); sound(run); }
    else { saveSoundPreference(true); stopAudio(run); updateSoundButton(run); }
  }
  function changeStage(run, index) {
    run.dialog.setAttribute('data-stage', String(index));
    const item = run.script[index];
    run.dialog.querySelector('.arrival-act-label').textContent = item.label;
    run.dialog.querySelector('#vaca-arrival-title').textContent = item.title;
    run.dialog.querySelector('#vaca-arrival-description').textContent = item.text;
    run.dialog.querySelector('.vaca-arrival-aside').textContent = item.aside;
    run.dialog.querySelectorAll('.arrival-progress > span').forEach((node, position) => {
      node.classList.toggle('is-active', position <= index);
      if (position === index) node.setAttribute('aria-current', 'step'); else node.removeAttribute('aria-current');
    });
  }
  function complete(run, { keepSound = false } = {}) {
    if (active !== run || run.done) return;
    if (!keepSound) {
      clearTimeout(run.soundTimer); run.soundTimer = null;
      run.soundEnded = true; stopAudio(run); updateSoundButton(run);
    }
    if (run.complete) return;
    run.complete = true; clearTimers(run); changeStage(run, 3);
    run.dialog.classList.add('is-complete');
    run.dialog.querySelector('.vaca-arrival-summary').hidden = false;
    run.dialog.querySelector('.vaca-arrival-skip').hidden = true;
    run.dialog.querySelector('.vaca-arrival-close-final').hidden = false;
  }
  function finish(run, reason) {
    if (run.done) return;
    run.done = true; clearTimers(run); stopAudio(run);
    clearTimeout(run.soundTimer); run.soundTimer = null;
    doc.removeEventListener('visibilitychange', run.onVisibility);
    doc.removeEventListener('castori:seasonchange', run.onSeason);
    root.removeEventListener('pagehide', run.onPageHide);
    run.media?.removeEventListener?.('change', run.onMotion);
    if (run.dialog.open) run.dialog.close();
    run.dialog.remove(); doc.body.style.overflow = run.previousOverflow;
    if (active === run) active = null;
    if (reason !== 'hidden' && doc.visibilityState !== 'hidden') {
      const target = run.trigger?.isConnected ? run.trigger : doc.querySelector('[data-vaca-arrival-play]') || run.previousFocus;
      if (target?.isConnected) target.focus({ preventScroll: true });
    }
  }
  function play({ event, trigger } = {}) {
    const time = now(), visitPhase = phase(time);
    if (active || event?.isTrusted !== true || !accessible(time)) return false;
    const dialog = doc.createElement('dialog');
    dialog.id = 'vaca-arrival'; dialog.setAttribute('data-stage', '0');
    dialog.setAttribute('aria-labelledby', 'vaca-arrival-title'); dialog.setAttribute('aria-describedby', 'vaca-arrival-description');
    dialog.innerHTML = scene(visitPhase);
    const media = root.matchMedia?.('(prefers-reduced-motion: reduce)');
    readSoundPreference();
    const settings = preferences(media), still = settings.reducedMotion || settings.motionPaused;
    if (still) dialog.classList.add('is-still');
    const run = { dialog, media, trigger, phase: visitPhase, script: visitPhase === 'arrival' ? arrivalActs : acts, previousFocus: doc.activeElement, previousOverflow: doc.body.style.overflow,
      timers: new Set(), startedAt: clock(), soundTimer: null, stopSound: null, soundGeneration: 0,
      soundBlocked: false, soundEnded: false, audioUnavailable: false, done: false, complete: false };
    run.onVisibility = () => { if (doc.visibilityState === 'hidden') finish(run, 'hidden'); };
    run.onPageHide = () => finish(run, 'hidden');
    run.onSeason = () => { if (!accessible()) finish(run, 'expired'); };
    run.onMotion = () => { if (preferences(media).reducedMotion) { dialog.classList.add('is-still'); complete(run, { keepSound: true }); } };
    dialog.addEventListener('cancel', e => { e.preventDefault(); finish(run, 'dismissed'); });
    dialog.addEventListener('close', () => finish(run, 'dismissed'));
    dialog.querySelector('.vaca-arrival-close').addEventListener('click', () => finish(run, 'dismissed'));
    dialog.querySelector('.vaca-arrival-close-final').addEventListener('click', () => finish(run, 'dismissed'));
    dialog.querySelector('.vaca-arrival-skip').addEventListener('click', () => {
      complete(run); dialog.querySelector('.vaca-arrival-close-final').focus({ preventScroll: true });
    });
    dialog.querySelector('.vaca-arrival-mute').addEventListener('click', event => toggleSound(run, event));
    doc.body.appendChild(dialog);
    try { dialog.showModal(); } catch (_) { dialog.remove(); return false; }
    active = run; doc.body.style.overflow = 'hidden';
    doc.addEventListener('visibilitychange', run.onVisibility);
    doc.addEventListener('castori:seasonchange', run.onSeason);
    root.addEventListener('pagehide', run.onPageHide);
    media?.addEventListener?.('change', run.onMotion);
    remember(visitPhase); // Act zero is already readable: interruptions still leave a replay button.
    if (!soundMuted) sound(run);
    updateSoundButton(run);
    run.soundTimer = setTimeout(() => {
      run.soundTimer = null;
      if (!accessible()) finish(run, 'hidden'); else complete(run);
    }, Math.max(0, DURATION - (clock() - run.startedAt)));
    if (still) complete(run, { keepSound: true });
    else {
      for (const [delay, index] of [[3000, 1], [9000, 2], [17000, 3]]) {
        const timer = setTimeout(() => {
          run.timers.delete(timer);
          if (active !== run || run.done || run.complete) return;
          if (!accessible()) { finish(run, 'hidden'); return; }
          changeStage(run, index);
        }, delay);
        run.timers.add(timer);
      }
    }
    return true;
  }
  root.CastoriVacaArrival = { render, refresh, play, stop: () => { if (active) finish(active, 'dismissed'); } };
})(typeof window === 'undefined' ? globalThis : window);

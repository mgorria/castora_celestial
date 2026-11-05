(function (root) {
  'use strict';

  const doc = root.document;
  const START = Date.parse('2026-11-05T00:00:00+01:00');
  const END = Date.parse('2027-01-11T00:00:00+01:00');
  const SEEN_KEY = 'castori.vaca-arrival.2026-11.v1';
  const DURATION = 26000;
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
  let active = null, seenInMemory = false;
  const now = () => root.CastoriChristmas?.now() ?? Date.now();
  const available = () => now() >= START && now() < END;
  const accessible = () => doc?.body?.dataset.access === 'open' && doc.visibilityState !== 'hidden' && available();

  function seen() {
    try { seenInMemory ||= root.localStorage.getItem(SEEN_KEY) === '1'; } catch (_) { /* Memory keeps replay working in private browsing. */ }
    return seenInMemory;
  }
  function remember() {
    seenInMemory = true;
    try { root.localStorage.setItem(SEEN_KEY, '1'); } catch (_) { /* Reading the message never depends on storage. */ }
    for (const button of doc.querySelectorAll('[data-vaca-arrival-play]')) {
      const title = button.querySelector('.vaca-arrival-button-copy > strong');
      const badge = button.querySelector('.vaca-arrival-new');
      if (title) title.textContent = 'Repetir mensaje';
      if (badge) { badge.textContent = 'REPLAY'; badge.setAttribute('aria-label', 'Mensaje visto'); }
    }
  }
  function preferences(media) {
    let value = {};
    try { value = root.CastoriChristmas?.preferences?.() || {}; } catch (_) { /* Effects are optional. */ }
    return {
      soundMuted: value.soundMuted === true,
      // christmas-paused also describes a temporarily hidden document. Only the
      // explicit preference may skip a newly opened, visible performance.
      motionPaused: value.motionPaused === true,
      reducedMotion: value.reducedMotion === true || media?.matches === true
    };
  }
  function render() {
    if (!available()) return '';
    const replay = seen();
    return `<section class="vaca-arrival-card" data-vaca-arrival aria-label="Un comunicado de la Vaca">
      <button type="button" class="vaca-arrival-trigger" data-vaca-arrival-play aria-haspopup="dialog" aria-controls="vaca-arrival">
        <span class="vaca-arrival-beacon" aria-hidden="true">✦</span>
        <span class="vaca-arrival-button-copy"><small>ESTAFETA ASTRAL · CASA TOSICO</small><strong>${replay ? 'Repetir mensaje' : 'Tienes un mensaje de la Vaca'}</strong><span>La Castora Celestial acaba de emitir un comunicado.</span></span>
        <span class="vaca-arrival-new" aria-label="${replay ? 'Mensaje visto' : 'Un mensaje nuevo'}">${replay ? 'REPLAY' : '1'}</span>
        <span class="vaca-arrival-button-arrow" aria-hidden="true">↗</span>
      </button>
    </section>`;
  }
  function scene() {
    const colors = ['#ffe16a', '#ff648e', '#6cf2df', '#b393ff', '#fff8d8'];
    const speedlines = Array.from({ length: 36 }, (_, i) => `<i style="--angle:${i * 10}deg;--delay:${(-i * .07).toFixed(2)}s"></i>`).join('');
    const fireworks = Array.from({ length: 3 }, (_, burst) => `<div class="arrival-burst" style="--x:${[20, 78, 52][burst]}%;--y:${[28, 30, 13][burst]}%;--burst-delay:${burst * .7}s">${Array.from({ length: 24 }, (_, i) => `<i style="--angle:${i * 15}deg;--distance:${115 + i % 5 * 16}px;--delay:${(burst * .7 + i % 3 * .035).toFixed(2)}s;--color:${colors[(i + burst) % colors.length]}"></i>`).join('')}</div>`).join('');
    const confetti = Array.from({ length: 100 }, (_, i) => `<i${i % 7 === 0 ? ' class="is-star"' : ''} style="--x:${(i * 37.7 % 100).toFixed(1)}%;--drift:${i % 2 ? 40 + i % 73 : -40 - i % 73}px;--delay:${(i % 17 * .09).toFixed(2)}s;--duration:${(3.8 + i % 9 * .43).toFixed(2)}s;--color:${colors[i % colors.length]}">${i % 7 === 0 ? '✦' : ''}</i>`).join('');
    const ribbon = 'VACA EN RUTA · PRIORIDAD ABSOLUTA · DESTINO CASA TOSICO · ATENCIÓN A LOS BALCONES · ';
    return `<div class="arrival-film" aria-hidden="true">
        <div class="arrival-shot arrival-shot-departure"><picture><source media="(max-width:700px)" srcset="assets/vaca-arrival-departure-mobile.webp"><img src="assets/vaca-arrival-departure.webp" alt="" loading="eager" decoding="async" fetchpriority="high" width="1536" height="1024"></picture></div>
        <div class="arrival-shot arrival-shot-highway"><picture><source media="(max-width:700px)" srcset="assets/vaca-arrival-highway-mobile.webp"><img src="assets/vaca-arrival-highway.webp" alt="" loading="eager" decoding="async" width="1536" height="1024"></picture></div>
        <div class="arrival-shot arrival-shot-arrival"><picture><source media="(max-width:700px)" srcset="assets/vaca-arrival-arrival-mobile.webp"><img src="assets/vaca-arrival-arrival.webp" alt="" loading="eager" decoding="async" width="1536" height="1024"></picture></div>
      </div>
      <div class="arrival-speedlines" aria-hidden="true">${speedlines}</div><div class="arrival-fireworks" aria-hidden="true">${fireworks}</div><div class="arrival-confetti" aria-hidden="true">${confetti}</div><div class="arrival-siren" aria-hidden="true"><i></i><i></i></div>
      <div class="arrival-emergency-ribbon" aria-hidden="true"><span>${ribbon}</span><span>${ribbon}</span></div>
      <div class="arrival-theatre">
        <div class="arrival-toolbar"><span>✦ COMUNICADO DE LA CASTORA CELESTIAL</span><button type="button" class="vaca-arrival-close" aria-label="Cerrar el mensaje de la Vaca">Cerrar <span aria-hidden="true">×</span></button></div>
        <div class="arrival-live"><i aria-hidden="true"></i> EN DIRECTO</div>
        <div class="arrival-alert-type" aria-hidden="true">MUUUY URGENTE</div>
        <div class="arrival-stamp" aria-hidden="true"><strong>VACA EN RUTA</strong><span>MISIÓN CASA TOSICO</span></div>
        <div class="arrival-caption" aria-live="polite" aria-atomic="true"><p class="arrival-act-label">${acts[0].label}</p><h2 id="vaca-arrival-title">${acts[0].title}</h2><p id="vaca-arrival-description">${acts[0].text}</p><p class="vaca-arrival-aside arrival-aside">${acts[0].aside}</p></div>
        <div class="arrival-route"><span>CASTORA CELESTIAL</span><i class="arrival-route-flight" aria-hidden="true">✦ ➜</i><span>CASA TOSICO</span></div>
        <ol class="vaca-arrival-summary" hidden aria-label="El comunicado completo">${news.map(item => `<li><strong>${item.title}</strong><span>${item.text}</span><small>${item.aside}</small></li>`).join('')}</ol>
        <div class="arrival-progress" aria-label="Actos de la llegada"><span class="is-active" aria-current="step">00 · ALERTA</span><span>01 · DESPEGUE</span><span>02 · HIPERESPACIO</span><span>03 · LLEGADA</span></div>
        <div class="arrival-controls"><button type="button" class="vaca-arrival-mute" aria-pressed="false">Silenciar</button><button type="button" class="vaca-arrival-skip">Leer el mensaje completo</button><button type="button" class="vaca-arrival-close-final" hidden>Entendido. Despejo el balcón.</button></div>
        <p class="arrival-footer">Servicio de mensajería mágica · No se admiten devoluciones de purpurina.</p>
      </div>`;
  }
  function clearTimers(run) { for (const timer of run.timers) clearTimeout(timer); run.timers.clear(); }
  function stopAudio(run) {
    run.soundStopped = true;
    const stop = run.stopSound; run.stopSound = null;
    try { stop?.(); } catch (_) { /* Optional sound cannot keep the scene open. */ }
  }
  function muteButton(run, text) {
    const button = run.dialog.querySelector('.vaca-arrival-mute');
    button.textContent = text; button.disabled = true; button.setAttribute('aria-pressed', 'true');
  }
  function sound(run) {
    const engine = root.CastoriVacaArrivalAudio;
    if (typeof engine?.play !== 'function') return false;
    try {
      // The engine creates/resumes audio synchronously inside this trusted click.
      const cleanup = engine.play({ duration: DURATION,
        isAllowed: () => active === run && !run.done && !run.complete && !run.soundStopped && accessible() && !preferences(run.media).soundMuted });
      if (typeof cleanup !== 'function') return false;
      run.stopSound = cleanup;
      if (cleanup.available === false) { stopAudio(run); return false; }
      return true;
    } catch (_) { stopAudio(run); return false; }
  }
  function changeStage(run, index) {
    run.dialog.setAttribute('data-stage', String(index));
    const item = acts[index];
    run.dialog.querySelector('.arrival-act-label').textContent = item.label;
    run.dialog.querySelector('#vaca-arrival-title').textContent = item.title;
    run.dialog.querySelector('#vaca-arrival-description').textContent = item.text;
    run.dialog.querySelector('.vaca-arrival-aside').textContent = item.aside;
    run.dialog.querySelectorAll('.arrival-progress > span').forEach((node, position) => {
      node.classList.toggle('is-active', position <= index);
      if (position === index) node.setAttribute('aria-current', 'step'); else node.removeAttribute('aria-current');
    });
  }
  function complete(run) {
    if (active !== run || run.done || run.complete) return;
    run.complete = true; clearTimers(run); stopAudio(run); changeStage(run, 3);
    run.dialog.classList.add('is-complete');
    run.dialog.querySelector('.vaca-arrival-summary').hidden = false;
    run.dialog.querySelector('.vaca-arrival-skip').hidden = true;
    run.dialog.querySelector('.vaca-arrival-close-final').hidden = false;
    if (!run.dialog.querySelector('.vaca-arrival-mute').disabled) muteButton(run, 'Sonido finalizado');
  }
  function finish(run, reason) {
    if (run.done) return;
    run.done = true; clearTimers(run); stopAudio(run);
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
    if (active || event?.isTrusted !== true || !accessible()) return false;
    const dialog = doc.createElement('dialog');
    dialog.id = 'vaca-arrival'; dialog.setAttribute('data-stage', '0');
    dialog.setAttribute('aria-labelledby', 'vaca-arrival-title'); dialog.setAttribute('aria-describedby', 'vaca-arrival-description');
    dialog.innerHTML = scene();
    const media = root.matchMedia?.('(prefers-reduced-motion: reduce)');
    const settings = preferences(media), still = settings.reducedMotion || settings.motionPaused;
    if (still) dialog.classList.add('is-still');
    const run = { dialog, media, trigger, previousFocus: doc.activeElement, previousOverflow: doc.body.style.overflow,
      timers: new Set(), stopSound: null, soundStopped: false, done: false, complete: false };
    run.onVisibility = () => { if (doc.visibilityState === 'hidden') finish(run, 'hidden'); };
    run.onPageHide = () => finish(run, 'hidden');
    run.onSeason = () => { if (!accessible()) finish(run, 'expired'); };
    run.onMotion = () => { if (preferences(media).reducedMotion) { dialog.classList.add('is-still'); complete(run); } };
    dialog.addEventListener('cancel', e => { e.preventDefault(); finish(run, 'dismissed'); });
    dialog.addEventListener('close', () => finish(run, 'dismissed'));
    dialog.querySelector('.vaca-arrival-close').addEventListener('click', () => finish(run, 'dismissed'));
    dialog.querySelector('.vaca-arrival-close-final').addEventListener('click', () => finish(run, 'dismissed'));
    dialog.querySelector('.vaca-arrival-skip').addEventListener('click', () => {
      complete(run); dialog.querySelector('.vaca-arrival-close-final').focus({ preventScroll: true });
    });
    dialog.querySelector('.vaca-arrival-mute').addEventListener('click', () => { stopAudio(run); muteButton(run, 'Sonido silenciado'); });
    doc.body.appendChild(dialog);
    try { dialog.showModal(); } catch (_) { dialog.remove(); return false; }
    active = run; doc.body.style.overflow = 'hidden';
    doc.addEventListener('visibilitychange', run.onVisibility);
    doc.addEventListener('castori:seasonchange', run.onSeason);
    root.addEventListener('pagehide', run.onPageHide);
    media?.addEventListener?.('change', run.onMotion);
    remember(); // Act zero is already readable: interruptions still leave a replay button.
    if (still) { complete(run); muteButton(run, 'Escena sin sonido'); }
    else {
      if (settings.soundMuted) muteButton(run, 'Sonido desactivado');
      else if (!sound(run)) muteButton(run, 'Sin sonido');
      for (const [delay, index] of [[3000, 1], [9000, 2], [17000, 3], [DURATION, 4]]) {
        const timer = setTimeout(() => {
          run.timers.delete(timer);
          if (active !== run || run.done || run.complete) return;
          if (!accessible()) { finish(run, 'hidden'); return; }
          if (index === 4) complete(run); else changeStage(run, index);
        }, delay);
        run.timers.add(timer);
      }
    }
    return true;
  }
  root.CastoriVacaArrival = { render, play, stop: () => { if (active) finish(active, 'dismissed'); } };
})(typeof window === 'undefined' ? globalThis : window);

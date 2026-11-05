(function (root) {
  'use strict';

  const doc = root.document;
  const START = Date.parse('2026-11-05T00:00:00+01:00');
  const END = Date.parse('2027-01-11T00:00:00+01:00');
  const SEEN_KEY = 'castori.vaca-arrival.2026-11.v1';
  const DURATION = 18000;
  const news = [
    { title: 'La Vaca ha abandonado la Castora Celestial.', text: 'Mimosuga confirma: falta una vaca y sobra purpurina.', aside: 'Comunicado urgente para Casa Tosico.' },
    { title: 'Autopista astral abierta', text: 'Peaje pagado con tres campanillas. Tráfico de renos desviado. Destino: Casa Tosico.', aside: 'Velocidad autorizada: completamente absurda.' },
    { title: '¡Llegada inminente!', text: 'Despejad balcones. Sujetad macetas. Dejad un poquito de sitio para lo imposible.', aside: 'Patita: los animales mágicos hemos hablado.' }
  ];
  let active = null, seenInMemory = false;
  const now = () => root.CastoriChristmas?.now() ?? Date.now();
  const available = () => now() >= START && now() < END;
  const elapsed = run => (root.performance?.now() ?? Date.now()) - run.started;
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
      motionPaused: value.motionPaused === true || doc.body.classList.contains('christmas-paused'),
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
    const colors = ['#ffe3a0', '#f7a2bb', '#a9e4e0', '#c6b6ff', '#ffffff'];
    const particles = Array.from({ length: 80 }, (_, i) => `<span style="--x:${(i * 37.7 % 100).toFixed(1)}%;--y:${(i * 23.3 % 100).toFixed(1)}%;--delay:${(-i * .17).toFixed(2)}s;--duration:${(3.8 + i % 7 * .51).toFixed(2)}s;--drift:${i % 2 ? 26 + i % 47 : -26 - i % 47}px;--color:${colors[i % colors.length]}">${i % 4 === 0 ? '✦' : '·'}</span>`).join('');
    const lights = Array.from({ length: 20 }, (_, i) => `<i style="--color:${colors[i % colors.length]};--delay:${(-i * .21).toFixed(2)}s"></i>`).join('');
    return `<div class="vaca-arrival-cosmos" aria-hidden="true"></div><div class="vaca-arrival-particles" aria-hidden="true">${particles}</div><div class="vaca-arrival-lights" aria-hidden="true">${lights}</div>
      <div class="vaca-arrival-stage">
        <div class="vaca-arrival-toolbar"><span>✦ COMUNICADO DE LA CASTORA CELESTIAL</span><button type="button" class="vaca-arrival-close" aria-label="Cerrar el mensaje de la Vaca">Cerrar <span aria-hidden="true">×</span></button></div>
        <div class="vaca-arrival-layout">
          <div class="vaca-arrival-visual" aria-hidden="true"><div class="vaca-arrival-rings"><i></i><i></i><i></i></div><div class="vaca-arrival-orbit"><span>✦</span><span>✧</span><span>✦</span></div><img class="vaca-arrival-portrait" src="assets/vaca-v2.png" alt="" width="600" height="600"><span class="vaca-arrival-seal">LA VACA MÁGICA<br>EN MISIÓN ASTRAL</span></div>
          <div class="vaca-arrival-copy"><p class="vaca-arrival-kicker">ATENCIÓN, CASA TOSICO</p><div class="vaca-arrival-message" aria-live="polite" aria-atomic="true"><h2 id="vaca-arrival-title">${news[0].title}</h2><p id="vaca-arrival-description">${news[0].text}</p><p class="vaca-arrival-aside">${news[0].aside}</p></div>
            <div class="vaca-arrival-route"><span><small>ORIGEN</small>Castora Celestial</span><i aria-hidden="true">✦ → ✦</i><span><small>DESTINO</small>Casa Tosico</span></div>
            <ol class="vaca-arrival-summary" hidden aria-label="El comunicado completo">${news.map(item => `<li><strong>${item.title}</strong><span>${item.text}</span><small>${item.aside}</small></li>`).join('')}</ol>
          </div>
        </div>
        <div class="vaca-arrival-progress" aria-hidden="true"><span class="is-active">01 · DESPEGUE</span><span>02 · EN RUTA</span><span>03 · LLEGADA INMINENTE</span></div>
        <div class="vaca-arrival-actions"><button type="button" class="vaca-arrival-mute" aria-pressed="false">Silenciar</button><button type="button" class="vaca-arrival-skip">Leer el mensaje completo</button><button type="button" class="vaca-arrival-close-final" hidden>Entendido. Despejo el balcón.</button></div>
        <p class="vaca-arrival-footer">Servicio de mensajería mágica · No se admiten devoluciones de purpurina.</p>
      </div>`;
  }
  function clearTimers(run) { for (const timer of run.timers) clearTimeout(timer); run.timers.clear(); }
  function stopAudio(run) {
    run.soundStopped = true;
    for (const node of run.audioNodes) {
      try { node.stop?.(); } catch (_) { /* A scheduled voice may already have ended. */ }
      try { node.disconnect(); } catch (_) { /* Audio is optional. */ }
    }
    run.audioNodes.length = 0;
    const context = run.audio; run.audio = null;
    if (context && context.state !== 'closed') { try { context.close()?.catch(() => {}); } catch (_) { /* Audio is optional. */ } }
  }
  function muteButton(run, text) {
    const button = run.dialog.querySelector('.vaca-arrival-mute');
    button.textContent = text; button.disabled = true; button.setAttribute('aria-pressed', 'true');
  }
  function sound(run) {
    const Audio = root.AudioContext || root.webkitAudioContext;
    if (!Audio) return false;
    try {
      // Create/resume in the original trusted click, before any asynchronous work.
      const context = run.audio = new Audio();
      const resumed = context.resume?.();
      const schedule = () => {
        if (active !== run || run.done || run.complete || run.soundStopped || !accessible() || context.state !== 'running') return;
        if (preferences(run.media).soundMuted) { stopAudio(run); muteButton(run, 'Sonido desactivado'); return; }
        const passed = elapsed(run) / 1000, left = DURATION / 1000 - passed;
        if (left <= 0) { stopAudio(run); return; }
        const base = context.currentTime;
        const master = context.createGain(); run.audioNodes.push(master);
        master.gain.setValueAtTime(.1, base); master.gain.setValueAtTime(0, base + left);
        master.connect(context.destination);
        function tone(frequency, at, duration, volume = .13, type = 'sine', sweep = false) {
          if (at < passed || at >= DURATION / 1000) return;
          const start = base + at - passed, end = Math.min(start + duration, base + left);
          const oscillator = context.createOscillator(), envelope = context.createGain();
          run.audioNodes.push(oscillator, envelope);
          oscillator.type = type; oscillator.frequency.setValueAtTime(frequency, start);
          if (sweep) {
            oscillator.frequency.linearRampToValueAtTime(frequency * 1.4, start + (end - start) / 2);
            oscillator.frequency.linearRampToValueAtTime(frequency, end);
          }
          envelope.gain.setValueAtTime(.0001, start);
          envelope.gain.exponentialRampToValueAtTime(volume, start + Math.min(.035, (end - start) / 4));
          envelope.gain.exponentialRampToValueAtTime(.0001, end);
          oscillator.connect(envelope); envelope.connect(master);
          oscillator.start(start); oscillator.stop(end);
        }
        // A soft storybook siren, then bells, rising arpeggios and a small major-key fanfare.
        [0, 1.4, 2.8].forEach(at => tone(240, at, 1.3, .09, 'sine', true));
        [0.25, .8, 1.35, 3.5, 4, 4.5].forEach((at, i) => {
          tone([1046.5, 1318.5, 1568][i % 3], at, .6, .1);
          tone([1046.5, 1318.5, 1568][i % 3] * 2.76, at, .32, .025);
        });
        [523.25, 659.25, 784, 1046.5, 784, 659.25, 523.25, 784, 1046.5].forEach((hz, i) => tone(hz, 5.1 + i * .42, .5));
        [10.2, 11.1, 12.3, 14.3, 16.1].forEach((at, i) => {
          [523.25, 659.25, 784].forEach(hz => tone(hz * (i % 2 ? 1 : 2), at, i === 4 ? 1.5 : .65, .055, 'triangle'));
          tone(2093, at + .16, .5, .07);
        });
      };
      const failed = () => { stopAudio(run); if (active === run && !run.done) muteButton(run, 'Sin sonido'); };
      const ready = () => { try { schedule(); } catch (_) { failed(); } };
      if (context.state === 'running') ready();
      else if (resumed?.then) resumed.then(ready, failed);
      else failed();
      // Some implementations return a promise even when already running.
      if (context.state === 'running') resumed?.catch(failed);
      return true;
    } catch (_) { stopAudio(run); return false; }
  }
  function changeStage(run, index) {
    run.dialog.setAttribute('data-stage', String(index));
    const item = news[index];
    run.dialog.querySelector('#vaca-arrival-title').textContent = item.title;
    run.dialog.querySelector('#vaca-arrival-description').textContent = item.text;
    run.dialog.querySelector('.vaca-arrival-aside').textContent = item.aside;
    run.dialog.querySelectorAll('.vaca-arrival-progress > span').forEach((node, position) => node.classList.toggle('is-active', position <= index));
  }
  function complete(run) {
    if (active !== run || run.done || run.complete) return;
    run.complete = true; clearTimers(run); stopAudio(run); changeStage(run, 2);
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
      timers: new Set(), audioNodes: [], audio: null, soundStopped: false, done: false, complete: false,
      started: root.performance?.now() ?? Date.now() };
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
      for (const [delay, index] of [[5000, 1], [10000, 2], [DURATION, 3]]) {
        const timer = setTimeout(() => {
          run.timers.delete(timer);
          if (active !== run || run.done || run.complete) return;
          if (!accessible()) { finish(run, 'hidden'); return; }
          if (index === 3) complete(run); else changeStage(run, index);
        }, delay);
        run.timers.add(timer);
      }
    }
    return true;
  }
  root.CastoriVacaArrival = { render, play, stop: () => { if (active) finish(active, 'dismissed'); } };
})(typeof window === 'undefined' ? globalThis : window);

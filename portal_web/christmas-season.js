(function (root) {
  'use strict';

  const START = Date.parse('2026-11-01T00:00:00+01:00');
  // January 10 is included; the usual house returns at midnight on January 11.
  const END = Date.parse('2027-01-11T00:00:00+01:00');
  const STORAGE_KEY = 'castori.christmas.effects.v1';
  const doc = root.document;
  const period = time => time < START ? 'before' : time < END ? 'active' : 'after';
  let initialized = false, active = false, decorations, controls, snow;
  let boundaryTimer, snowTimer, snowCleanup, audioTimer, audioContext, soundGeneration = 0;
  let soundMuted = false, motionPaused = false, lastSound = -Infinity;
  let media, previewTime = null, previewStarted = 0;
  const originals = new WeakMap();
  const now = () => previewTime === null ? Date.now() : previewTime + Date.now() - previewStarted;

  // Local QA can travel through the date boundaries. Production ignores this parameter.
  function readPreview() {
    if (!['localhost', '127.0.0.1', '[::1]'].includes(root.location?.hostname)) return;
    const value = new URLSearchParams(root.location.search).get('christmas-preview');
    if (!value) return;
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) { previewTime = parsed; previewStarted = Date.now(); }
  }
  function readPreferences() {
    try {
      const value = JSON.parse(root.localStorage.getItem(STORAGE_KEY));
      soundMuted = value?.soundMuted === true;
      motionPaused = value?.motionPaused === true;
    } catch (_) { /* Preferences are optional; no account data is involved. */ }
  }
  function savePreferences() {
    try { root.localStorage.setItem(STORAGE_KEY, JSON.stringify({ soundMuted, motionPaused })); } catch (_) { /* Still works for this visit. */ }
  }
  function isVisible() { return doc.visibilityState !== 'hidden'; }
  function effectsAllowed() { return active && isVisible() && doc.body.dataset.access === 'open'; }
  function motionAllowed() { return effectsAllowed() && !motionPaused && !media?.matches; }

  function buildDecorations() {
    if (decorations) return;
    decorations = doc.createElement('div');
    decorations.id = 'christmas-decorations';
    decorations.setAttribute('aria-hidden', 'true');
    const colors = ['#f26b65', '#f5ce6a', '#65d3a2', '#7ab8f5', '#e5a0df'];
    decorations.innerHTML = `<div class="christmas-lights">${Array.from({ length: 32 }, (_, i) => `<span class="christmas-bulb" style="--bulb-color:${colors[i % colors.length]};--bulb-delay:-${(i % 7) * .63}s"></span>`).join('')}</div><div class="christmas-snow"></div>`;
    doc.body.append(decorations);
    snow = decorations.querySelector('.christmas-snow');
    controls = doc.createElement('section');
    controls.id = 'christmas-controls';
    controls.setAttribute('aria-label', 'El ambiente navideño de Casa Tosico');
    controls.innerHTML = `<div class="christmas-controls-title"><span aria-hidden="true">✧</span><div><strong>El cascabeleo está en casa</strong><small>Luces, historias y un poquito de magia.</small></div></div><div class="christmas-control-buttons"><button type="button" data-christmas-sound></button><button type="button" data-christmas-motion></button></div>`;
    doc.getElementById('connection-banner').after(controls);
    if (previewTime !== null) {
      const note = doc.createElement('small');
      note.id = 'christmas-preview-note';
      note.textContent = 'Vista previa local de Navidad · la fecha de la web publicada no cambia';
      controls.prepend(note);
    }
    updateControls();
  }
  function updateControls() {
    if (!controls) return;
    controls.hidden = !active || doc.body.dataset.access !== 'open';
    const soundButton = controls.querySelector('[data-christmas-sound]');
    soundButton.textContent = soundMuted ? 'Cascabeles: no' : 'Cascabeles: sí';
    soundButton.setAttribute('aria-label', soundMuted ? 'Activar cascabeles' : 'Silenciar cascabeles');
    soundButton.setAttribute('aria-pressed', String(!soundMuted));
    soundButton.title = 'Suenan al visitar a un amigo, abrir un cuento o volver a Mi rincón.';
    const motionButton = controls.querySelector('[data-christmas-motion]');
    motionButton.textContent = media?.matches ? 'Movimiento reducido' : motionPaused ? 'Reanudar luces y nieve' : 'Pausar luces y nieve';
    motionButton.setAttribute('aria-pressed', String(motionPaused || !!media?.matches));
    motionButton.disabled = !!media?.matches;
    doc.body.classList.toggle('christmas-paused', !motionAllowed());
  }
  function stopSnow() {
    clearTimeout(snowTimer); clearTimeout(snowCleanup);
    snowTimer = snowCleanup = null;
    snow?.replaceChildren();
  }
  function snowBurst() {
    snowTimer = null;
    if (!motionAllowed() || !snow) return;
    // Sparse, short showers, with a quiet interval between them.
    snow.innerHTML = Array.from({ length: 14 }, (_, i) => {
      const x = Math.round(Math.random() * 98);
      const size = 9 + Math.round(Math.random() * 11);
      const duration = 7 + Math.random() * 3;
      const drift = Math.round(Math.random() * 100 - 50);
      return `<span class="christmas-flake" style="--flake-x:${x}vw;--flake-size:${size}px;--flake-duration:${duration.toFixed(2)}s;--flake-delay:${(i * .16).toFixed(2)}s;--flake-drift:${drift}px">${i % 3 === 0 ? '❄' : '•'}</span>`;
    }).join('');
    snowCleanup = setTimeout(() => { snow?.replaceChildren(); snowCleanup = null; }, 13000);
    snowTimer = setTimeout(snowBurst, 32000 + Math.random() * 14000);
  }
  function syncEffects() {
    updateControls();
    if (decorations) decorations.hidden = !effectsAllowed();
    if (!motionAllowed()) stopSnow();
    else if (snowTimer == null) snowTimer = setTimeout(snowBurst, 2400);
    if (!effectsAllowed()) stopAudio();
  }

  function remember(node) {
    if (!originals.has(node)) originals.set(node, { html: node.innerHTML, src: node.getAttribute('src'), alt: node.getAttribute('alt') });
    return originals.get(node);
  }
  function dressHouse() {
    const changes = [
      ['#welcome-title', 'La Navidad está<br>en casa, <em>Patita.</em>'],
      ['.hero-content .eyebrow', '✧ CASA TOSICO · EDICIÓN NAVIDAD'],
      ['.hero-content > p', 'Enciende la ilusión, acércate al árbol<br>y quédate un ratito con nosotros.'],
      ['.hero-caption', '✧ Aquí vive el espíritu navideño.']
    ];
    for (const [selector, html] of changes) {
      const node = doc.querySelector(selector);
      if (!node) continue;
      if (active) { remember(node); if (node.innerHTML !== html) node.innerHTML = html; }
      else if (originals.has(node)) { node.innerHTML = originals.get(node).html; originals.delete(node); }
    }
    const art = doc.querySelector('.hero-art');
    if (!art) return;
    if (active) {
      remember(art);
      if (art.getAttribute('src') !== 'assets/casa-celestial-navidad.png') art.setAttribute('src', 'assets/casa-celestial-navidad.png');
      art.setAttribute('alt', 'Castori, Mimosuga y la Vaca celebran la Navidad en su casa del árbol, entre guirnaldas, regalos y luces de colores.');
    } else if (originals.has(art)) {
      const original = originals.get(art);
      art.setAttribute('src', original.src); art.setAttribute('alt', original.alt);
      originals.delete(art);
    }
  }

  function stopAudio() {
    soundGeneration++;
    clearTimeout(audioTimer); audioTimer = null;
    const context = audioContext; audioContext = null;
    if (context && context.state !== 'closed') { try { context.close().catch(() => {}); } catch (_) { /* Optional audio. */ } }
  }
  function jingle() {
    if (!effectsAllowed() || soundMuted || period(now()) !== 'active' || Date.now() - lastSound < 1100) return;
    const Audio = root.AudioContext || root.webkitAudioContext;
    if (!Audio) return;
    lastSound = Date.now();
    stopAudio();
    const generation = soundGeneration;
    try {
      const context = audioContext = new Audio();
      const play = () => {
        if (generation !== soundGeneration || !effectsAllowed() || soundMuted || context.state !== 'running') return;
        const master = context.createGain();
        master.gain.value = .15; master.connect(context.destination);
        // Short inharmonic overtones make a soft cluster of sleigh bells.
        [0, .1, .22].forEach((offset, strike) => {
          [1, 2.76, 4.07].forEach((partial, index) => {
            const start = context.currentTime + offset;
            const oscillator = context.createOscillator(), envelope = context.createGain();
            oscillator.type = 'sine'; oscillator.frequency.value = [1397, 1568, 2093][strike] * partial;
            envelope.gain.setValueAtTime(.0001, start);
            envelope.gain.exponentialRampToValueAtTime(.21 / (index + 1), start + .006);
            envelope.gain.exponentialRampToValueAtTime(.0001, start + .52);
            oscillator.connect(envelope); envelope.connect(master);
            oscillator.start(start); oscillator.stop(start + .55);
          });
        });
        audioTimer = setTimeout(stopAudio, 1000);
      };
      // Created/resumed only inside a real click, as required by mobile browsers.
      if (context.state === 'suspended') context.resume().then(play).catch(stopAudio); else play();
    } catch (_) { stopAudio(); }
  }
  function handleClick(event) {
    const button = event.target.closest?.('button, a');
    if (!button || button.disabled || !event.isTrusted || !effectsAllowed()) return;
    if (button.hasAttribute('data-christmas-sound')) {
      soundMuted = !soundMuted; savePreferences(); updateControls();
      if (soundMuted) stopAudio(); else jingle();
    } else if (button.hasAttribute('data-christmas-motion')) {
      motionPaused = !motionPaused; savePreferences(); syncEffects();
    } else if (button.matches('[data-chat]:not([data-chat="salchicher"]), [data-story], [data-view="home"]')) jingle();
  }
  function refresh() {
    if (!initialized) return;
    clearTimeout(boundaryTimer); boundaryTimer = null;
    const time = now(), next = period(time) === 'active', changed = next !== active;
    active = next;
    doc.body.classList.toggle('christmas-season', active);
    if (active) buildDecorations();
    else {
      stopSnow(); stopAudio();
      decorations?.remove(); controls?.remove();
      decorations = controls = snow = null;
      doc.body.classList.remove('christmas-paused');
    }
    dressHouse();
    if (active) syncEffects();
    if (changed) doc.dispatchEvent(new root.CustomEvent('castori:seasonchange', { detail: { active } }));
    const boundary = time < START ? START : time < END ? END : null;
    if (boundary !== null && isVisible()) boundaryTimer = setTimeout(refresh, Math.max(1, Math.min(60000, boundary - time)));
  }
  function suspend() { clearTimeout(boundaryTimer); boundaryTimer = null; stopSnow(); stopAudio(); }
  function init() {
    if (initialized || !doc) return;
    initialized = true;
    readPreview(); readPreferences();
    media = root.matchMedia?.('(prefers-reduced-motion: reduce)');
    media?.addEventListener?.('change', syncEffects);
    doc.addEventListener('visibilitychange', refresh);
    doc.addEventListener('click', handleClick, true);
    root.addEventListener('pageshow', refresh);
    root.addEventListener('pagehide', suspend);
    refresh();
  }
  root.CastoriChristmas = { START, END, period, now, init, refresh, isActive: () => active };
})(typeof window === 'undefined' ? globalThis : window);

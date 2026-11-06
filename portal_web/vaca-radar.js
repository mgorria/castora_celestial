(function (root) {
  'use strict';

  const PHASE_MS = 8000;
  const phases = [
    { title: 'Señal de pezuñas localizada', activity: 'Demasiado MUUU para ir de incógnito.', heading: 'Casa Tosico… con unos cuantos rodeos.', quote: '«Estoy dando una vuelta. Una muuuuy normal.»' },
    { title: 'Desvío sospechoso', activity: 'Posibles escaparates en la salida 7.', heading: 'Ha puesto el intermitente de purpurina.', quote: '«Solo voy a mirar. ¡No me sigáis!»' },
    { title: 'Parada bajo investigación', activity: 'Niega llevar bolsas. No nos deja comprobarlo.', heading: 'Casa Tosico sigue en el mapa.', quote: '«Eso no es una bolsa. Es una nube con asas.»' },
    { title: '¡Pezuñas a la fuga!', activity: 'Una vuelta de más. Y otra. Muuu sospechoso.', heading: 'Recalculando la coartada.', quote: '«El camino recto estaba demasiado recto.»' },
    { title: 'De vuelta a su órbita', activity: 'La campanilla intenta guardar el secreto.', heading: 'Casa Tosico, entre ceja y pezuña.', quote: '«Yo no he comprado nada. MUUU.»' }
  ];
  let mounted = null;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const safeChance = value => Math.max(0, Math.min(100, Number(value) || 0));
  const orbitName = chance => chance < 30 ? 'Órbita exterior' : chance < 50 ? 'Desvío astral' : chance < 70 ? 'Rumbo a Tosico' : 'Órbita de aproximación';
  const routeIcon = chance => `<svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><ellipse cx="20" cy="21" rx="16" ry="10" stroke="currentColor" opacity=".35"/><ellipse cx="20" cy="21" rx="10" ry="6" stroke="currentColor" stroke-dasharray="2 3"/><path d="m16 21 4-4 4 4v6h-8Z" stroke="currentColor" stroke-linejoin="round"/><circle cx="${chance < 50 ? '5' : '29'}" cy="${chance < 50 ? '17' : '18'}" r="3" fill="currentColor"/></svg>`;

  function render(days) {
    if (!Array.isArray(days) || !days.length) return '';
    const today = days[0], chance = safeChance(today.chance);
    const stars = Array.from({ length: 36 }, (_, i) => `<i style="--sx:${4 + (i * 37 % 92)}%;--sy:${5 + (i * 29 % 88)}%;--sd:${i % 7 * -.63}s;--ss:${i % 4 === 0 ? 3 : 2}px"></i>`).join('');
    return `<div class="vaca-forecast-heading"><div><p class="vaca-forecast-kicker">AUTOPISTA ASTRAL · CASA TOSICO</p><h3 id="vaca-forecast-title">Radar de pezuñas</h3><p class="vaca-forecast-intro">Una vaca suelta. Demasiados desvíos. Muuu pocas explicaciones.</p></div><span class="vaca-radar-seal" aria-hidden="true">SEÑAL<br><b>MUUU</b><span>LOCALIZADA</span></span></div>
      <div class="vaca-radar-console">
        <div class="vaca-radar-stage" data-radar-stage data-chance="${chance}" role="img" aria-label="La Vaca Mágica recorre ${escape(orbitName(chance).toLowerCase())} alrededor de Casa Tosico, con desvíos y posibles paradas. Una escena de cuento.">
          <div class="vaca-radar-nebula" aria-hidden="true"></div><div class="vaca-radar-stars" aria-hidden="true">${stars}</div>
          <svg class="vaca-radar-map" viewBox="0 0 600 460" fill="none" aria-hidden="true">
            <defs><radialGradient id="vaca-radar-home-glow"><stop stop-color="#ffd9b3" stop-opacity=".22"/><stop offset="1" stop-color="#ff9ed4" stop-opacity="0"/></radialGradient><linearGradient id="vaca-radar-trail" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e39fd8"/><stop offset="1" stop-color="#ffe6ad"/></linearGradient></defs>
            <ellipse cx="300" cy="240" rx="237" ry="170" fill="url(#vaca-radar-home-glow)"/>
            <path class="vaca-radar-grid" d="M300 48V427M45 240H555M96 94 503 387M98 386 506 91"/>
            <g class="vaca-radar-road"><ellipse cx="300" cy="240" rx="218" ry="148"/><ellipse cx="300" cy="240" rx="166" ry="113"/><ellipse cx="300" cy="240" rx="112" ry="76"/></g>
            <g class="vaca-radar-road-dashes"><ellipse cx="300" cy="240" rx="218" ry="148"/><ellipse cx="300" cy="240" rx="166" ry="113"/><ellipse cx="300" cy="240" rx="112" ry="76"/></g>
            <path class="vaca-radar-detour" d="M447 337C545 321 543 183 500 112C445 35 330 63 265 83M500 112 533 240 470 360 122 317"/>
            <g class="vaca-radar-sweep"><path d="M300 240 528 225A229 155 0 0 0 468 135Z" fill="#e59dc9" fill-opacity=".08"/><path d="M300 240 528 225" stroke="#ffd9ac" stroke-opacity=".42"/></g>
            <g class="vaca-radar-beacons"><circle cx="82" cy="240" r="3"/><circle cx="300" cy="92" r="3"/><circle cx="518" cy="240" r="3"/><circle cx="300" cy="388" r="3"/></g>
            <polyline class="vaca-radar-tail-glow" data-radar-tail-glow points=""/><polyline class="vaca-radar-tail" data-radar-tail points=""/>
          </svg>
          <span class="vaca-radar-orbit-label" aria-hidden="true">RUTA NO HOMOLOGADA<br>POR NINGÚN RENO</span>
          <div class="vaca-radar-shop" aria-hidden="true"><svg viewBox="0 0 36 40" fill="none"><path d="M8 13h20l3 22H5L8 13Z" stroke="currentColor" stroke-width="1.5"/><path d="M13 15V9a5 5 0 0 1 10 0v6M15 24l3-3 3 3-3 3-3-3Z" stroke="currentColor" stroke-width="1.5"/></svg><span>SALIDA 7<small>¿Solo mirando?</small></span><i></i></div>
          <div class="vaca-radar-home" aria-hidden="true"><div class="vaca-radar-home-ring"></div><img src="assets/casa-celestial-v2.png" alt="" loading="lazy" width="110" height="110"><span>CASA TOSICO<small>El centro del lío</small></span></div>
          <div class="vaca-radar-cow" data-radar-cow style="--cow-x:22%;--cow-y:35%;--cow-tilt:-9deg" aria-hidden="true"><span class="vaca-radar-cow-ping"></span><div class="vaca-radar-cow-portrait"><img src="assets/vaca-v2.png" alt="" draggable="false" loading="lazy" width="84" height="84"></div><span class="vaca-radar-cow-call">MUUU<span>↗</span></span><span class="vaca-radar-cow-sparks">✦ · ✧</span></div>
          <div class="vaca-radar-map-caption" aria-hidden="true"><span class="vaca-radar-live-dot"></span><span data-radar-running>Señal de cuento · en movimiento</span></div>
        </div>
        <div class="vaca-radar-report"><div class="vaca-radar-today"><div><span>POSIBLE VISITA HOY</span><strong>${escape(today.chance)}<small>%</small></strong></div><p>La probabilidad de visita.<br>El lío está garantizado.</p></div><div class="vaca-radar-phase"><span class="vaca-radar-report-kicker">ÚLTIMA TRAVESURA DETECTADA</span><h4 data-radar-phase>${phases[0].title}</h4><p class="vaca-radar-quote" data-radar-quote>${phases[0].quote}</p></div><dl class="vaca-radar-telemetry"><div><dt>Posición</dt><dd data-radar-distance>${escape(orbitName(chance))}</dd></div><div><dt>Sospechas</dt><dd data-radar-activity>${phases[0].activity}</dd></div><div><dt>Rumbo declarado</dt><dd data-radar-heading>${phases[0].heading}</dd></div></dl><div class="vaca-radar-actions"><button type="button" data-radar-follow>Seguir la señal <span aria-hidden="true">↗</span></button><button type="button" data-radar-pause aria-pressed="false">Pausar radar</button></div></div>
      </div>
      <div class="vaca-radar-week-heading"><h4>Las próximas órbitas</h4><p class="vaca-forecast-range">${escape(today.dateLabel)} — ${escape(days[days.length - 1].dateLabel)}</p></div>
      <ol class="vaca-forecast-days">${days.map((day, index) => `<li class="vaca-forecast-day" data-outlook="${escape(day.outlook)}"${index === 0 ? ' aria-current="date"' : ''}><p class="vaca-forecast-weekday">${escape(day.weekday)}</p><time class="vaca-forecast-date" datetime="${escape(day.iso)}">${escape(day.dateLabel)}</time><span class="vaca-forecast-icon">${routeIcon(safeChance(day.chance))}</span><strong class="vaca-forecast-chance" aria-label="${escape(day.chance)}% de probabilidad de visita">${escape(day.chance)}<small>%</small></strong><span class="vaca-forecast-signal">${escape(day.signal)}</span></li>`).join('')}</ol>
      <p class="vaca-forecast-note">Seguimiento mágico orientativo. La Vaca se reserva el derecho a aparecer por sorpresa.</p>`;
  }

  function orbit(run, angle) { return { x: 300 + Math.cos(angle) * run.radius, y: 240 + Math.sin(angle) * run.radius * .68 }; }
  function smooth(value) { return value * value * (3 - 2 * value); }
  function blend(a, b, t) { return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }; }
  function curve(a, b, c, d, t) {
    const s = 1 - t;
    return { x: s * s * s * a.x + 3 * s * s * t * b.x + 3 * s * t * t * c.x + t * t * t * d.x,
      y: s * s * s * a.y + 3 * s * s * t * b.y + 3 * s * t * t * c.y + t * t * t * d.y };
  }
  function position(run, phase, progress) {
    const t = smooth(progress), shop = { x: 500, y: 112 };
    if (phase === 0) return orbit(run, -2.6 + 3.4 * progress);
    if (phase === 1) return curve(orbit(run, .8), { x: 550, y: 383 }, { x: 564, y: 190 }, shop, t);
    if (phase === 2) return shop;
    if (phase === 3) {
      const points = [shop, { x: 529, y: 234 }, { x: 430, y: 365 }, { x: 254, y: 349 }, orbit(run, 2.6)];
      const part = Math.min(3, Math.floor(progress * 4));
      return blend(points[part], points[part + 1], smooth(progress * 4 - part));
    }
    return orbit(run, 2.6 + (Math.PI * 2 - 5.2) * t);
  }

  function paint(run, force = false) {
    const phase = Math.floor(run.elapsed / PHASE_MS) % phases.length;
    const progress = (run.elapsed % PHASE_MS) / PHASE_MS;
    const point = position(run, phase, progress);
    run.cow.style.setProperty('--cow-x', (point.x / 6).toFixed(3) + '%');
    run.cow.style.setProperty('--cow-y', (point.y / 4.6).toFixed(3) + '%');
    const tilt = run.paused ? -5 : phase === 2 ? Math.sin(run.elapsed / 420) * 5 : Math.sin(run.elapsed / 260) * 9;
    run.cow.style.setProperty('--cow-tilt', tilt.toFixed(2) + 'deg');
    if (force || run.elapsed - run.lastTrail >= 65) {
      if (!run.paused) run.points.push(point);
      if (run.points.length > 26) run.points.shift();
      const path = run.points.map(p => p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
      run.tail?.setAttribute('points', path); run.tailGlow?.setAttribute('points', path);
      run.lastTrail = run.elapsed;
    }
    if (phase !== run.phase || force) {
      run.phase = phase; run.node.dataset.radarPhase = String(phase);
      run.title.textContent = phases[phase].title;
      run.quote.textContent = phases[phase].quote;
      run.activity.textContent = phases[phase].activity;
      run.heading.textContent = phases[phase].heading;
      run.distance.textContent = phase === 2 ? 'Salida 7 · parada sospechosa' : phase === 1 || phase === 3 ? 'Fuera de su órbita habitual' : orbitName(run.chance);
    }
  }

  function cancelFrame(run) {
    if (run.frame !== null) root.cancelAnimationFrame(run.frame);
    run.frame = null; run.lastFrame = null;
  }
  function blocked(run) {
    const doc = run.node.ownerDocument, body = doc.body;
    const preferences = root.CastoriChristmas?.preferences?.() || {};
    return run.localPaused || !run.inViewport || preferences.motionPaused || preferences.reducedMotion || run.media?.matches ||
      body?.classList.contains('christmas-paused') || body?.dataset.christmasMotion === 'off' ||
      body?.dataset.access !== 'open' || doc.visibilityState === 'hidden';
  }
  function frame(run, time) {
    run.frame = null;
    if (mounted !== run) return;
    if (!run.node.isConnected) { unmount(); return; }
    if (blocked(run)) { refresh(); return; }
    if (run.lastFrame !== null) run.elapsed += Math.min(80, Math.max(0, time - run.lastFrame));
    run.lastFrame = time;
    paint(run);
    run.frame = root.requestAnimationFrame(time => frame(run, time));
  }
  function refresh() {
    const run = mounted;
    if (!run) return;
    if (!run.node.isConnected) { unmount(); return; }
    run.paused = !!blocked(run);
    run.node.classList.toggle('radar-is-paused', run.paused);
    run.node.dataset.radarPaused = String(run.paused);
    const preferences = root.CastoriChristmas?.preferences?.() || {};
    const reduced = !!(preferences.reducedMotion || run.media?.matches);
    const globalPause = !!(preferences.motionPaused || run.node.ownerDocument.body?.classList.contains('christmas-paused') || run.node.ownerDocument.body?.dataset.christmasMotion === 'off');
    run.pause.disabled = reduced || globalPause;
    run.pause.textContent = reduced ? 'Mínimo movimiento' : globalPause ? 'Movimiento en pausa' : run.localPaused ? 'Reanudar radar' : 'Pausar radar';
    run.pause.setAttribute('aria-pressed', String(run.paused));
    run.running.textContent = run.paused ? 'Señal en pausa · puedes seguir las pistas' : 'Señal de cuento · en movimiento';
    if (run.paused) cancelFrame(run);
    else if (run.frame === null && typeof root.requestAnimationFrame === 'function') run.frame = root.requestAnimationFrame(time => frame(run, time));
  }
  function unmount() {
    const run = mounted;
    if (!run) return;
    mounted = null; cancelFrame(run);
    run.node.removeEventListener('click', run.click);
    run.node.ownerDocument.removeEventListener('visibilitychange', refresh);
    run.node.ownerDocument.removeEventListener('castori:seasonchange', refresh);
    run.media?.removeEventListener?.('change', refresh);
    run.observer?.disconnect(); run.intersection?.disconnect();
  }
  function mount(node) {
    unmount();
    if (!node?.isConnected) return;
    const stage = node.querySelector('[data-radar-stage]');
    if (!stage) return;
    const run = {
      node, chance: safeChance(stage.dataset.chance), radius: 0, elapsed: 0, phase: -1,
      frame: null, lastFrame: null, lastTrail: -100, points: [], localPaused: false, paused: true, inViewport: true,
      cow: node.querySelector('[data-radar-cow]'), tail: node.querySelector('[data-radar-tail]'),
      tailGlow: node.querySelector('[data-radar-tail-glow]'), title: node.querySelector('[data-radar-phase]'),
      quote: node.querySelector('[data-radar-quote]'), distance: node.querySelector('[data-radar-distance]'),
      activity: node.querySelector('[data-radar-activity]'), heading: node.querySelector('[data-radar-heading]'),
      pause: node.querySelector('[data-radar-pause]'), running: node.querySelector('[data-radar-running]'),
      media: root.matchMedia?.('(prefers-reduced-motion: reduce)'), observer: null, intersection: null, click: null
    };
    if (![run.cow, run.title, run.quote, run.distance, run.activity, run.heading, run.pause, run.running].every(Boolean)) return;
    run.radius = 218 - run.chance * 1.06;
    run.click = event => {
      const button = event.target.closest?.('[data-radar-pause], [data-radar-follow]');
      if (!button || !node.contains(button) || button.disabled) return;
      if (button.hasAttribute('data-radar-pause')) run.localPaused = !run.localPaused;
      else { run.elapsed = (Math.floor(run.elapsed / PHASE_MS) + 1) * PHASE_MS; run.points = []; run.lastTrail = -100; paint(run, true); }
      refresh();
    };
    mounted = run;
    node.addEventListener('click', run.click);
    node.ownerDocument.addEventListener('visibilitychange', refresh);
    node.ownerDocument.addEventListener('castori:seasonchange', refresh);
    run.media?.addEventListener?.('change', refresh);
    if (root.MutationObserver && node.ownerDocument.body) {
      run.observer = new root.MutationObserver(refresh);
      run.observer.observe(node.ownerDocument.body, { attributes: true, attributeFilter: ['class', 'data-access', 'data-christmas-motion'] });
    }
    if (root.IntersectionObserver) {
      run.intersection = new root.IntersectionObserver(entries => {
        if (mounted !== run) return;
        const entry = entries.find(item => item.target === node);
        if (entry) { run.inViewport = entry.isIntersecting; refresh(); }
      }, { rootMargin: '100px' });
      run.intersection.observe(node);
    }
    refresh(); paint(run, true);
  }

  root.CastoriVacaRadar = { render, mount, refresh, unmount };
})(typeof window === 'undefined' ? globalThis : window);

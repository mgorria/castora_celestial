(function (root) {
  'use strict';

  const stations = [
    { id: 'market', name: 'Mercadillo', short: 'Tiendas', subtitle: '¿Solo mirando?', x: 480, y: 110, dock: { x: 430, y: 146 }, action: 'browse', prop: 'bag', call: '¿BOLSAS?',
      title: 'Una parada muuu sospechosa', activity: 'Posibles bolsas escondidas bajo la capa.', heading: 'Dice que solo ha entrado a mirar.', quote: '«Eso no es una bolsa. Es una nube con asas.»', log: 'Mercadillo: la capa parece tener más bultos.' },
    { id: 'fuel', name: 'Gasolinera astral', short: 'Brillo', subtitle: 'Purpurina al depósito', x: 505, y: 310, dock: { x: 450, y: 284 }, action: 'refuel', prop: 'glitter', call: '¡BRILLO!',
      title: 'Repostando purpurina', activity: 'El depósito brilla. Las pezuñas, todavía más.', heading: 'Pide gasolina de estrellas sin mirar el precio.', quote: '«¡Lleno, por favor! Y un chorrito en los cuernos.»', log: 'Gasolinera: fuga de purpurina junto al surtidor.' },
    { id: 'cookies', name: 'Merienda clandestina', short: 'Galletas', subtitle: 'Aquí no falta ninguna', x: 300, y: 380, dock: { x: 220, y: 355 }, action: 'nibble', prop: 'cookie', call: 'ÑAM… MUU',
      title: 'La pausa de las migas', activity: 'Bajada inexplicable del nivel de galletas.', heading: 'La investigación requiere otra degustación.', quote: '«No estoy comiendo. Estoy haciendo inventario.»', log: 'Merienda: aparecen migas en el hocico.' },
    { id: 'post', name: 'Correo astral', short: 'Correo', subtitle: 'Sobres con coartada', x: 95, y: 315, dock: { x: 149, y: 286 }, action: 'post', prop: 'letter', call: 'SHHH…',
      title: 'Un sobre que no hemos visto', activity: 'Sello torcido. Destinatario ilegible. Muuu raro.', heading: 'Casa Tosico sigue entre sus planes secretos.', quote: '«¿Una carta? No. Un rectángulo con secretos.»', log: 'Correo: una pezuña tapa el nombre del sobre.' },
    { id: 'lookout', name: 'Mirador de balcones', short: 'Mirador', subtitle: '¿Qué estará buscando?', x: 105, y: 115, dock: { x: 158, y: 150 }, action: 'look', prop: 'binoculars', call: '¡AJÁ!',
      title: 'Vigilancia de vaca curiosa', activity: 'Prismáticos al revés. Disimulo mejorable.', heading: 'Busca Casa Tosico entre las nubes del mapa.', quote: '«Muuu… todo está lejísimos. Ah. Eran al revés.»', log: 'Mirador: gira los prismáticos y se hace la distraída.' }
  ];
  const phases = [{ duration: 6000, action: 'travel', stop: 'orbit', title: 'Señal de pezuñas localizada', activity: 'Demasiado MUUU para ir de incógnito.', heading: 'Casa Tosico… con cinco desvíos tentadores.', quote: '«Estoy dando una vuelta. Una muuuuy normal.»', call: 'MUUU', log: 'Señal localizada: la Vaca ha vuelto a escaparse.' }];
  for (const station of stations) {
    phases.push({ duration: 5000, action: 'travel', stop: station.id, title: 'Otro desvío perfectamente sospechoso', activity: `Su campanilla apunta hacia ${station.name.toLowerCase()}.`, heading: 'El camino recto le parecía demasiado recto.', quote: '«¡Un momentito! He visto una cosa. MUUU.»', call: '¡POR AQUÍ!', log: `Intermitente de purpurina: rumbo a ${station.name.toLowerCase()}.` });
    phases.push({ duration: 6000, ...station, stop: station.id });
  }
  phases.push({ duration: 5000, action: 'travel', stop: 'orbit', title: 'De vuelta, como si nada', activity: 'Posibles bolsas. Posibles migas. Cero explicaciones.', heading: 'Casa Tosico, entre ceja y pezuña.', quote: '«Yo no me he desviado. Se ha movido la carretera.»', call: 'MUUU', log: 'Regresa a su órbita fingiendo absoluta normalidad.' });
  let cycleDuration = 0;
  for (const phase of phases) { phase.start = cycleDuration; cycleDuration += phase.duration; }
  let mounted = null;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const safeChance = value => Math.max(0, Math.min(100, Number(value) || 0));
  const orbitName = chance => chance < 30 ? 'Órbita exterior' : chance < 50 ? 'Desvío astral' : chance < 70 ? 'Rumbo a Tosico' : 'Órbita de aproximación';
  const routeIcon = chance => `<svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><ellipse cx="20" cy="21" rx="16" ry="10" stroke="currentColor" opacity=".35"/><ellipse cx="20" cy="21" rx="10" ry="6" stroke="currentColor" stroke-dasharray="2 3"/><path d="m16 21 4-4 4 4v6h-8Z" stroke="currentColor" stroke-linejoin="round"/><circle cx="${chance < 50 ? '5' : '29'}" cy="${chance < 50 ? '17' : '18'}" r="3" fill="currentColor"/></svg>`;

  function render(days) {
    if (!Array.isArray(days) || !days.length) return '';
    const today = days[0], chance = safeChance(today.chance);
    const stars = Array.from({ length: 36 }, (_, i) => `<i style="--sx:${4 + (i * 37 % 92)}%;--sy:${5 + (i * 29 % 88)}%;--sd:${i % 7 * -.63}s;--ss:${i % 4 === 0 ? 3 : 2}px"></i>`).join('');
    const sprite = id => `<svg viewBox="0 0 120 100" aria-hidden="true"><use href="assets/vaca-radar-stations.svg#${id}" width="120" height="100"></use></svg>`;
    const stationMap = stations.map((station, index) => `<div class="vaca-radar-station" data-station="${station.id}" style="--station-x:${station.x / 6}%;--station-y:${station.y / 4.6}%;--station-index:${index}" aria-hidden="true"><i class="vaca-radar-station-halo"></i><div class="vaca-radar-station-art">${sprite(station.id)}</div><span class="vaca-radar-station-name">${station.name}<small>${station.subtitle}</small></span></div>`).join('');
    const stationRail = `<div class="vaca-radar-station-rail" role="group" aria-label="Seguir las cinco paradas de la Vaca">${stations.map(station => `<button type="button" data-radar-station="${station.id}" aria-label="Seguir a la Vaca: ${station.name}" aria-pressed="false">${sprite(station.id)}<span>${station.short}</span><i aria-hidden="true"></i></button>`).join('')}</div>`;
    const props = stations.map(station => `<span class="vaca-radar-cow-prop" data-prop="${station.action}">${sprite(station.prop)}</span>`).join('');
    const lights = Array.from({ length: 12 }, (_, i) => `<i style="--light-i:${i}"></i>`).join('');
    return `<div class="vaca-forecast-heading"><div><p class="vaca-forecast-kicker">AUTOPISTA ASTRAL · CASA TOSICO</p><h3 id="vaca-forecast-title">Radar de pezuñas</h3><p class="vaca-forecast-intro">Cinco paradas. Una vaca fugada. Muuu pocas explicaciones.</p></div><span class="vaca-radar-seal" aria-hidden="true">SEÑAL<br><b>MUUU</b><span>LOCALIZADA</span></span></div>
      <div class="vaca-radar-console">
        <div class="vaca-radar-map-panel"><div class="vaca-radar-stage" data-radar-stage data-chance="${chance}" role="img" aria-label="Mapa de cuento de la Vaca Mágica alrededor de Casa Tosico. Posición: ${escape(orbitName(chance))}. Paradas posibles: mercadillo, gasolinera de purpurina, merienda, correo astral y mirador.">
          <div class="vaca-radar-nebula" aria-hidden="true"></div><div class="vaca-radar-stars" aria-hidden="true">${stars}</div>
          <div class="vaca-radar-comet" aria-hidden="true"></div><div class="vaca-radar-moon" aria-hidden="true"></div><div class="vaca-radar-christmas-lights" aria-hidden="true">${lights}</div>
          <svg class="vaca-radar-map" viewBox="0 0 600 460" fill="none" aria-hidden="true">
            <defs><radialGradient id="vaca-radar-home-glow"><stop stop-color="#ffd9b3" stop-opacity=".22"/><stop offset="1" stop-color="#ff9ed4" stop-opacity="0"/></radialGradient><linearGradient id="vaca-radar-trail" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e39fd8"/><stop offset="1" stop-color="#ffe6ad"/></linearGradient></defs>
            <ellipse cx="300" cy="240" rx="237" ry="170" fill="url(#vaca-radar-home-glow)"/>
            <path class="vaca-radar-grid" d="M300 48V427M45 240H555M96 94 503 387M98 386 506 91"/>
            <g class="vaca-radar-road"><ellipse cx="300" cy="240" rx="218" ry="148"/><ellipse cx="300" cy="240" rx="166" ry="113"/><ellipse cx="300" cy="240" rx="112" ry="76"/></g>
            <g class="vaca-radar-road-dashes"><ellipse cx="300" cy="240" rx="218" ry="148"/><ellipse cx="300" cy="240" rx="166" ry="113"/><ellipse cx="300" cy="240" rx="112" ry="76"/></g>
            <path class="vaca-radar-detour" d="M337 93C380 65 428 80 430 146C540 170 550 235 450 284C440 360 370 380 220 355C225 385 152 365 149 286C55 260 60 175 158 150C190 65 120 130 113 168"/>
            <path class="vaca-radar-station-links" d="M430 146 480 110M450 284 505 310M220 355 300 380M149 286 95 315M158 150 105 115"/>
            <g class="vaca-radar-sweep"><path d="M300 240 528 225A229 155 0 0 0 468 135Z" fill="#e59dc9" fill-opacity=".08"/><path d="M300 240 528 225" stroke="#ffd9ac" stroke-opacity=".42"/></g>
            <g class="vaca-radar-beacons"><circle cx="82" cy="240" r="3"/><circle cx="300" cy="92" r="3"/><circle cx="518" cy="240" r="3"/><circle cx="300" cy="388" r="3"/></g>
            <polyline class="vaca-radar-tail-glow" data-radar-tail-glow points=""/><polyline class="vaca-radar-tail" data-radar-tail points=""/>
          </svg>
          <span class="vaca-radar-orbit-label" aria-hidden="true">RUTA NO HOMOLOGADA<br>POR NINGÚN RENO</span>${stationMap}
          <div class="vaca-radar-home" aria-hidden="true"><div class="vaca-radar-home-ring"></div><img src="assets/casa-celestial-v2.png" alt="" loading="lazy" width="110" height="110"><span>CASA TOSICO<small>El centro del lío</small></span></div>
          <div class="vaca-radar-cow" data-radar-cow style="--cow-x:22%;--cow-y:35%;--cow-tilt:-9deg" aria-hidden="true"><span class="vaca-radar-cow-ping"></span><div class="vaca-radar-cow-portrait"><img src="assets/vaca-v2.png" alt="" draggable="false" loading="lazy" width="84" height="84"></div><span class="vaca-radar-cow-call"><span data-radar-call>MUUU</span><span>↗</span></span>${props}<span class="vaca-radar-cow-sparks">✦ · ✧</span><span class="vaca-radar-action-particles">${Array.from({ length: 8 }, (_, i) => `<i style="--particle-i:${i}"></i>`).join('')}</span></div>
        </div><div class="vaca-radar-map-caption" aria-hidden="true"><span class="vaca-radar-live-dot"></span><span data-radar-running>Señal de cuento · en movimiento</span></div>${stationRail}<div class="vaca-radar-route-meta"><span>VUELTA MUUUY POCO DIRECTA</span><span>5 paradas · 0 explicaciones</span></div><div class="vaca-radar-route-progress" data-radar-progress-track role="progressbar" aria-label="Recorrido de las travesuras" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><span data-radar-progress></span></div></div>
        <div class="vaca-radar-report"><div class="vaca-radar-today"><div><span>POSIBLE VISITA HOY</span><strong>${escape(today.chance)}<small>%</small></strong></div><p>La probabilidad de visita.<br>El lío está garantizado.</p></div><div class="vaca-radar-phase"><span class="vaca-radar-report-kicker">ÚLTIMA TRAVESURA DETECTADA</span><h4 data-radar-phase>${phases[0].title}</h4><p class="vaca-radar-quote" data-radar-quote>${phases[0].quote}</p></div><dl class="vaca-radar-telemetry"><div><dt>Posición</dt><dd data-radar-distance>${escape(orbitName(chance))}</dd></div><div><dt>Sospechas</dt><dd data-radar-activity>${phases[0].activity}</dd></div><div><dt>Rumbo declarado</dt><dd data-radar-heading>${phases[0].heading}</dd></div></dl><div class="vaca-radar-actions"><button type="button" data-radar-follow>Seguir la señal <span aria-hidden="true">↗</span></button><button type="button" data-radar-pause aria-pressed="false">Pausar radar</button></div><div class="vaca-radar-logbook"><span class="vaca-radar-report-kicker">RASTRO DE TRAVESURAS</span><ol class="vaca-radar-log" data-radar-log aria-live="off"><li><i aria-hidden="true">✦</i><span>${phases[0].log}</span></li></ol></div><span class="vaca-radar-announcement" data-radar-announcement role="status" aria-live="polite"></span></div>
      </div>
      <div class="vaca-radar-week-heading"><h4>Las próximas órbitas</h4><p class="vaca-forecast-range">${escape(today.dateLabel)} — ${escape(days[days.length - 1].dateLabel)}</p></div>
      <ol class="vaca-forecast-days">${days.map((day, index) => `<li class="vaca-forecast-day" data-outlook="${escape(day.outlook)}"${index === 0 ? ' aria-current="date"' : ''}><p class="vaca-forecast-weekday">${escape(day.weekday)}</p><time class="vaca-forecast-date" datetime="${escape(day.iso)}">${escape(day.dateLabel)}</time><span class="vaca-forecast-icon">${routeIcon(safeChance(day.chance))}</span><strong class="vaca-forecast-chance" aria-label="${escape(day.chance)}% de probabilidad de visita">${escape(day.chance)}<small>%</small></strong><span class="vaca-forecast-signal">${escape(day.signal)}</span></li>`).join('')}</ol>
      <p class="vaca-forecast-note">Seguimiento mágico orientativo. La Vaca se reserva el derecho a aparecer por sorpresa.</p>`;
  }

  function orbit(run, angle) { return { x: 300 + Math.cos(angle) * run.radius, y: 240 + Math.sin(angle) * run.radius * .68 }; }
  function smooth(value) { return value * value * (3 - 2 * value); }
  function curve(a, b, c, d, t) {
    const s = 1 - t;
    return { x: s * s * s * a.x + 3 * s * s * t * b.x + 3 * s * t * t * c.x + t * t * t * d.x,
      y: s * s * s * a.y + 3 * s * s * t * b.y + 3 * s * t * t * c.y + t * t * t * d.y };
  }
  function position(run, phase, progress) {
    const t = smooth(progress);
    if (phase === 0) return orbit(run, -2.6 + 1.2 * progress);
    if (phase % 2 === 0) return stations[phase / 2 - 1].dock;
    const legs = [
      [orbit(run, -1.4), { x: 380, y: 65 }, { x: 428, y: 80 }, stations[0].dock],
      [stations[0].dock, { x: 540, y: 170 }, { x: 550, y: 235 }, stations[1].dock],
      [stations[1].dock, { x: 440, y: 360 }, { x: 370, y: 380 }, stations[2].dock],
      [stations[2].dock, { x: 225, y: 385 }, { x: 152, y: 365 }, stations[3].dock],
      [stations[3].dock, { x: 55, y: 260 }, { x: 60, y: 175 }, stations[4].dock],
      [stations[4].dock, { x: 190, y: 65 }, { x: 120, y: 130 }, orbit(run, -2.6)]
    ];
    return curve(...legs[(phase - 1) / 2], t);
  }
  function phaseAt(elapsed) {
    const cycleTime = (elapsed % cycleDuration + cycleDuration) % cycleDuration;
    const index = phases.findIndex(phase => cycleTime < phase.start + phase.duration);
    return { index, progress: (cycleTime - phases[index].start) / phases[index].duration, cycleTime };
  }

  function paint(run, force = false) {
    const state = phaseAt(run.elapsed), phase = state.index, progress = state.progress;
    const current = phases[phase];
    const point = position(run, phase, progress);
    run.cow.style.setProperty('--cow-x', (point.x / 6).toFixed(3) + '%');
    run.cow.style.setProperty('--cow-y', (point.y / 4.6).toFixed(3) + '%');
    const tilt = run.paused ? -5 : current.action === 'travel' ? Math.sin(run.elapsed / 260) * 9 : Math.sin(run.elapsed / 420) * 5;
    run.cow.style.setProperty('--cow-tilt', tilt.toFixed(2) + 'deg');
    run.node.style.setProperty('--route-progress', (state.cycleTime / cycleDuration * 100).toFixed(2) + '%');
    const percent = Math.round(state.cycleTime / cycleDuration * 100);
    if (percent !== run.lastPercent) { run.progressTrack?.setAttribute('aria-valuenow', String(percent)); run.lastPercent = percent; }
    if (force || run.elapsed - run.lastTrail >= 65) {
      if (!run.paused) run.points.push(point);
      if (run.points.length > 26) run.points.shift();
      const path = run.points.map(p => p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
      run.tail?.setAttribute('points', path); run.tailGlow?.setAttribute('points', path);
      run.lastTrail = run.elapsed;
    }
    const changed = phase !== run.phase;
    if (changed || force) {
      run.phase = phase; run.node.dataset.radarPhase = String(phase);
      run.node.dataset.radarAction = current.action; run.node.dataset.radarStop = current.stop;
      run.title.textContent = current.title; run.quote.textContent = current.quote;
      run.activity.textContent = current.activity; run.heading.textContent = current.heading;
      if (run.call) run.call.textContent = current.call;
      const station = stations.find(item => item.id === current.stop);
      run.distance.textContent = current.stop === 'orbit' ? orbitName(run.chance) : current.action === 'travel' ? `Desvío hacia ${station.name.toLowerCase()}` : station.name;
      for (const button of run.stationButtons) button.setAttribute('aria-pressed', String(button.getAttribute('data-radar-station') === current.stop));
      if (changed) {
        run.logEntries.unshift(current.log); run.logEntries = run.logEntries.slice(0, 3);
        if (run.log) run.log.innerHTML = run.logEntries.map(entry => `<li><i aria-hidden="true">✦</i><span>${escape(entry)}</span></li>`).join('');
      }
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
      frame: null, lastFrame: null, lastTrail: -100, lastPercent: -1, points: [], logEntries: [], localPaused: false, paused: true, inViewport: true,
      cow: node.querySelector('[data-radar-cow]'), tail: node.querySelector('[data-radar-tail]'),
      tailGlow: node.querySelector('[data-radar-tail-glow]'), title: node.querySelector('[data-radar-phase]'),
      quote: node.querySelector('[data-radar-quote]'), distance: node.querySelector('[data-radar-distance]'),
      activity: node.querySelector('[data-radar-activity]'), heading: node.querySelector('[data-radar-heading]'),
      pause: node.querySelector('[data-radar-pause]'), running: node.querySelector('[data-radar-running]'),
      call: node.querySelector('[data-radar-call]'), log: node.querySelector('[data-radar-log]'),
      progressTrack: node.querySelector('[data-radar-progress-track]'), announcement: node.querySelector('[data-radar-announcement]'),
      stationButtons: Array.from(node.querySelectorAll('[data-radar-station]')),
      media: root.matchMedia?.('(prefers-reduced-motion: reduce)'), observer: null, intersection: null, click: null
    };
    if (![run.cow, run.title, run.quote, run.distance, run.activity, run.heading, run.pause, run.running].every(Boolean)) return;
    run.radius = 218 - run.chance * 1.06;
    run.click = event => {
      const button = event.target.closest?.('[data-radar-pause], [data-radar-follow], [data-radar-station]');
      if (!button || !node.contains(button) || button.disabled) return;
      if (button.hasAttribute('data-radar-pause')) run.localPaused = !run.localPaused;
      else {
        const selected = button.getAttribute('data-radar-station');
        const next = selected === null ? (phaseAt(run.elapsed).index + 1) % phases.length : phases.findIndex(phase => phase.stop === selected && phase.action !== 'travel');
        if (next < 0) return;
        run.elapsed = phases[next].start; run.points = []; run.lastTrail = -100; run.lastFrame = null;
        paint(run, true);
        if (run.announcement) run.announcement.textContent = `${phases[next].title}. ${phases[next].activity}`;
      }
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

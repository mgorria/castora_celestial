(function (root) {
  'use strict';

  const calendar = root.CastoriChristmas;
  // The decoration review closes at midnight on 1 December in Madrid.
  const DEADLINE = Date.parse('2026-12-01T00:00:00+01:00');
  const END = calendar?.END ?? Date.parse('2027-01-11T00:00:00+01:00');
  const currentTime = () => calendar?.now() ?? Date.now();
  const units = [['days', 'días'], ['hours', 'horas'], ['minutes', 'minutos'], ['seconds', 'segundos']];
  const madridDate = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit' });
  const shortDate = new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', day: 'numeric', month: 'short' });
  const weekday = new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', weekday: 'short' });
  // Storytelling forecasts: stable per date, with the possible surprise windows
  // suggested by Miguel. These are magical signals, not measured probabilities.
  const visitSignals = {
    '2026-11-02': 18, '2026-11-03': 23, '2026-11-04': 31, '2026-11-05': 43,
    '2026-11-06': 8, '2026-11-07': 12, '2026-11-08': 10,
    '2026-11-09': 18, '2026-11-10': 26, '2026-11-11': 58, '2026-11-12': 67,
    '2026-11-13': 76, '2026-11-14': 82, '2026-11-15': 20,
    '2026-11-16': 16, '2026-11-17': 22, '2026-11-18': 28,
    '2026-11-19': 66, '2026-11-20': 74, '2026-11-21': 88, '2026-11-22': 92
  };
  const orbits = [
    { limit: 30, outlook: 'quiet', signal: 'Órbita exterior' },
    { limit: 50, outlook: 'whisper', signal: 'Desvío astral' },
    { limit: 70, outlook: 'near', signal: 'Rumbo a Tosico' },
    { limit: 101, outlook: 'bright', signal: 'Órbita de aproximación' }
  ];
  let section = null, timer = null;

  function dayKey(now) {
    const parts = Object.fromEntries(madridDate.formatToParts(new Date(now)).map(part => [part.type, part.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  }
  function forecast(now = currentTime()) {
    // UTC here represents a civil date, so moving one day also works across
    // month/year and daylight-saving boundaries without skipping a day.
    const firstDay = Date.parse(dayKey(now) + 'T00:00:00Z');
    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(firstDay + index * 86400000), iso = date.toISOString().slice(0, 10);
      const dayNumber = Math.floor(date.getTime() / 86400000);
      const weekend = [0, 6].includes(date.getUTCDay());
      const chance = visitSignals[iso] ?? (22 + (dayNumber * 17 % 33 + 33) % 33 + (weekend ? 10 : 0));
      const orbit = orbits.find(item => chance < item.limit);
      return { iso, weekday: index === 0 ? 'Hoy' : weekday.format(date).replace('.', ''), dateLabel: shortDate.format(date).replace('.', ''), chance, signal: orbit.signal, outlook: orbit.outlook };
    });
  }
  function forecastBody(days) {
    return root.CastoriVacaRadar.render(days);
  }
  function renderForecast(now) {
    const days = forecast(now);
    return `<section class="vaca-forecast" data-vaca-forecast data-forecast-day="${days[0].iso}" aria-labelledby="vaca-forecast-title">${forecastBody(days)}</section>`;
  }
  function remaining(now = currentTime()) {
    const total = Math.max(0, Math.ceil((DEADLINE - now) / 1000));
    return { closed: now >= DEADLINE, days: Math.floor(total / 86400), hours: Math.floor(total / 3600) % 24, minutes: Math.floor(total / 60) % 60, seconds: total % 60 };
  }
  const pad = value => String(value).padStart(2, '0');
  const heading = closed => closed ? 'La Vaca prepara su veredicto' : 'La Vaca está puntuando la decoración navideña';
  const copy = closed => closed
    ? 'El plazo para modificar la decoración ha terminado. La última palabra la tiene la Vaca.'
    : 'La casa ya está decorada y cada detalle cuenta. Aún tienes tiempo para hacer modificaciones.';

  function render(now = currentTime()) {
    if (now >= END) return '';
    const value = remaining(now);
    return `<section class="decoration-review${value.closed ? ' decoration-review-closed' : ''}" data-decoration-review aria-labelledby="decoration-review-title">
      <svg class="decoration-review-sprig" viewBox="0 0 180 130" fill="none" aria-hidden="true"><g stroke="currentColor" stroke-linecap="round"><path d="M180 8C131 23 89 56 22 113" stroke-width="2"/><path d="m145 21-32-9m30 10-11 32m-12-18-34-8m33 9-9 33m-15-20-34-6m33 8-7 34m-15-19-32-5m30 7-4 32m-15-18-26-2m25 4-3 25"/></g><g fill="#d87c76"><circle cx="96" cy="46" r="4"/><circle cx="105" cy="48" r="3"/><circle cx="99" cy="55" r="3.5"/></g></svg>
      <div class="decoration-review-main">
        <div class="decoration-review-intro">
          <div class="decoration-review-juror" aria-hidden="true">
            <span class="decoration-review-thought"><span>?</span><span>?</span><span>?</span></span>
            <img class="decoration-review-portrait" src="assets/vaca-v2.png" alt="" width="88" height="104">
          </div>
          <div class="decoration-review-copy"><p class="decoration-review-kicker">EL JURADO DE CASA TOSICO</p><h2 id="decoration-review-title">${heading(value.closed)}</h2><p data-decoration-review-copy>${copy(value.closed)}</p></div>
        </div>
        <div class="decoration-review-rating">
          <div class="decoration-review-rating-heading"><span>Termómetro navideño</span><strong aria-label="Puntuación pendiente">— <small>/ 10</small></strong></div>
          <div class="decoration-review-thermometer" aria-hidden="true"><span class="decoration-review-mercury"></span><span class="decoration-review-bulb"></span></div>
          <p class="decoration-review-rating-note"><span class="decoration-review-deliberation">Deliberando<span class="decoration-review-thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span></span><span>Puntuación pendiente de la Vaca</span></p>
          ${root.CastoriDecorationComments?.render() || ''}
        </div>
      </div>
      <div class="decoration-review-deadline"><p class="decoration-review-date">CIERRE DE LA EVALUACIÓN<time datetime="2026-12-01T00:00:00+01:00">1 de diciembre</time></p>
        <div class="decoration-review-clock" role="timer" aria-live="off" aria-label="Tiempo para modificar la decoración antes del 1 de diciembre"${value.closed ? ' hidden' : ''}>${units.map(([key, label]) => `<div class="decoration-review-unit"><span data-decoration-review-unit="${key}">${pad(value[key])}</span><span class="decoration-review-label">${label}</span></div>`).join('')}</div>
        <p class="decoration-review-verdict"${value.closed ? '' : ' hidden'}>Evaluación cerrada.<br>Esperando el veredicto de la Vaca.</p>
      </div>
      ${renderForecast(now)}
      <span class="decoration-review-announcement" role="status" aria-live="polite"></span>
    </section>`;
  }

  function pause() { if (timer !== null) clearTimeout(timer); timer = null; }
  function unmount() {
    pause();
    root.CastoriDecorationComments?.unmount();
    root.CastoriVacaRadar?.unmount();
    if (section) {
      section.ownerDocument.removeEventListener('visibilitychange', refresh);
      section.ownerDocument.removeEventListener('castori:seasonchange', refresh);
    }
    section = null;
  }
  function refresh() {
    pause();
    if (!section?.isConnected) { unmount(); return; }
    const now = currentTime();
    if (now >= END) { section.hidden = true; unmount(); return; }
    const weather = section.querySelector('[data-vaca-forecast]');
    const today = dayKey(now);
    if (weather.getAttribute('data-forecast-day') !== today) {
      root.CastoriVacaRadar?.unmount();
      weather.innerHTML = forecastBody(forecast(now));
      weather.setAttribute('data-forecast-day', today);
      root.CastoriVacaRadar?.mount(weather);
    }
    root.CastoriVacaRadar?.refresh();
    const value = remaining(now);
    const wasClosed = section.classList.contains('decoration-review-closed');
    section.classList.toggle('decoration-review-closed', value.closed);
    section.querySelector('.decoration-review-clock').hidden = value.closed;
    section.querySelector('.decoration-review-verdict').hidden = !value.closed;
    if (wasClosed !== value.closed) {
      section.querySelector('#decoration-review-title').textContent = heading(value.closed);
      section.querySelector('[data-decoration-review-copy]').textContent = copy(value.closed);
      section.querySelector('.decoration-review-announcement').textContent = value.closed ? 'Evaluación cerrada. Esperando el veredicto de la Vaca.' : '';
    }
    for (const [key] of units) {
      const node = section.querySelector(`[data-decoration-review-unit="${key}"]`);
      const text = pad(value[key]);
      if (node.textContent !== text) node.textContent = text;
    }
    if (section.ownerDocument.visibilityState !== 'hidden') timer = setTimeout(refresh, value.closed ? 60000 : Math.min(1000, DEADLINE - now));
  }
  function mount(node) {
    unmount();
    section = node;
    if (!section) return;
    root.CastoriDecorationComments?.mount(section.querySelector('[data-decoration-comments]'));
    section.ownerDocument.addEventListener('visibilitychange', refresh);
    section.ownerDocument.addEventListener('castori:seasonchange', refresh);
    root.CastoriVacaRadar?.mount(section.querySelector('[data-vaca-forecast]'));
    refresh();
  }
  root.CastoriDecorationReview = { render, mount, unmount, remaining, forecast };
})(typeof window === 'undefined' ? globalThis : window);

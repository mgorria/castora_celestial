(function (root) {
  'use strict';

  const calendar = root.CastoriChristmas;
  // The decoration review closes at midnight on 1 December in Madrid.
  const DEADLINE = Date.parse('2026-12-01T00:00:00+01:00');
  const END = calendar?.END ?? Date.parse('2027-01-11T00:00:00+01:00');
  const currentTime = () => calendar?.now() ?? Date.now();
  const units = [['days', 'días'], ['hours', 'horas'], ['minutes', 'minutos'], ['seconds', 'segundos']];
  let section = null, timer = null;

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
          <img class="decoration-review-portrait" src="assets/vaca-v2.png" alt="" width="88" height="88">
          <div class="decoration-review-copy"><p class="decoration-review-kicker">EL JURADO DE CASA TOSICO</p><h2 id="decoration-review-title">${heading(value.closed)}</h2><p data-decoration-review-copy>${copy(value.closed)}</p></div>
        </div>
        <div class="decoration-review-rating">
          <div class="decoration-review-rating-heading"><span>Termómetro navideño</span><strong aria-label="Puntuación pendiente">— <small>/ 10</small></strong></div>
          <div class="decoration-review-thermometer" aria-hidden="true"><span class="decoration-review-mercury"></span><i></i><i></i><i></i></div>
          <p class="decoration-review-rating-note">Puntuación pendiente de la Vaca</p>
        </div>
      </div>
      <div class="decoration-review-deadline"><p class="decoration-review-date">CIERRE DE LA EVALUACIÓN<time datetime="2026-12-01T00:00:00+01:00">1 de diciembre</time></p>
        <div class="decoration-review-clock" role="timer" aria-live="off" aria-label="Tiempo para modificar la decoración antes del 1 de diciembre"${value.closed ? ' hidden' : ''}>${units.map(([key, label]) => `<div class="decoration-review-unit"><span data-decoration-review-unit="${key}">${pad(value[key])}</span><span class="decoration-review-label">${label}</span></div>`).join('')}</div>
        <p class="decoration-review-verdict"${value.closed ? '' : ' hidden'}>Evaluación cerrada.<br>Esperando el veredicto de la Vaca.</p>
      </div>
      <span class="decoration-review-announcement" role="status" aria-live="polite"></span>
    </section>`;
  }

  function pause() { if (timer !== null) clearTimeout(timer); timer = null; }
  function unmount() {
    pause();
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
    if (!value.closed && section.ownerDocument.visibilityState !== 'hidden') timer = setTimeout(refresh, Math.min(1000, DEADLINE - now));
  }
  function mount(node) {
    unmount();
    section = node;
    if (!section) return;
    section.ownerDocument.addEventListener('visibilitychange', refresh);
    section.ownerDocument.addEventListener('castori:seasonchange', refresh);
    refresh();
  }
  root.CastoriDecorationReview = { render, mount, unmount, remaining };
})(typeof window === 'undefined' ? globalThis : window);

(function (root) {
  'use strict';

  // Casa Tosico opens Christmas on 1 November 2026, at midnight in Madrid.
  // An explicit offset keeps every visitor counting down to the same instant.
  const calendar = root.CastoriChristmas;
  const TARGET = calendar?.START ?? Date.parse('2026-11-01T00:00:00+01:00');
  const END = calendar?.END ?? Date.parse('2027-01-11T00:00:00+01:00');
  const currentTime = () => calendar?.now() ?? Date.now();
  const units = [['days', 'días'], ['hours', 'horas'], ['minutes', 'minutos'], ['seconds', 'segundos']];
  let section = null, timer = null;

  function remaining(now = currentTime()) {
    const total = Math.max(0, Math.ceil((TARGET - now) / 1000));
    return { arrived: now >= TARGET, days: Math.floor(total / 86400), hours: Math.floor(total / 3600) % 24, minutes: Math.floor(total / 60) % 60, seconds: total % 60 };
  }
  const pad = value => String(value).padStart(2, '0');
  const heading = arrived => arrived ? '¡Ya llegó el cascabeleo!' : 'Se acerca el cascabeleo';
  const copy = arrived => arrived
    ? 'El espíritu navideño ya está en Casa Tosico. Es hora de sacar los adornos y llenar la casa de Navidad.'
    : 'Nuestro espíritu navideño está despertando. El 1 de noviembre sacamos los adornos y llenamos la casa de Navidad.';

  function render(now = currentTime()) {
    if (now >= END) return '';
    const value = remaining(now);
    return `<section class="cascabeleo${value.arrived ? ' cascabeleo-arrived' : ''}" data-cascabeleo aria-labelledby="cascabeleo-title">
      <svg class="cascabeleo-sprig" viewBox="0 0 180 130" fill="none" aria-hidden="true"><g stroke="currentColor" stroke-linecap="round"><path d="M180 8C131 23 89 56 22 113" stroke-width="2"/><path d="m145 21-32-9m30 10-11 32m-12-18-34-8m33 9-9 33m-15-20-34-6m33 8-7 34m-15-19-32-5m30 7-4 32m-15-18-26-2m25 4-3 25"/><path d="M173 14c-10 35-3 68 7 94m-11-68-16-13m17 15 10-10m-11 23-17-11m18 14 10-10m-7 26-15-10m17 15 5-6"/></g><g fill="#c56b68"><circle cx="96" cy="46" r="4"/><circle cx="105" cy="48" r="3"/><circle cx="99" cy="55" r="3.5"/></g></svg>
      <div class="cascabeleo-emblem" aria-hidden="true"><svg viewBox="0 0 96 108" fill="none"><path d="M48 24C26 3 13 14 22 24c6 7 18 5 26 0Zm0 0C67 2 83 12 75 23c-5 7-17 6-27 1Z" fill="#b95757" stroke="#e9aca1" stroke-width="1.5"/><path d="m47 25-12 20 13-5 6-15 12 18-1-15" fill="#b95757"/><g stroke="#f4dca2" stroke-width="1.8"><path d="m40 31-7 16m22-16 7 24"/><circle cx="29" cy="66" r="21" fill="#bd9853"/><path d="M12 66c10 5 24 6 36-1M29 70v14"/><circle cx="29" cy="82" r="3" fill="#294b3d"/><path d="m15 55 6-4m15 1 5 4"/><circle cx="65" cy="74" r="22" fill="#dfbf76"/><path d="M46 73c11 6 26 7 39 0M65 78v15"/><circle cx="65" cy="90" r="3" fill="#294b3d"/><path d="m51 63 6-4m16 1 5 5"/></g><path d="m78 38 2-6 2 6 6 2-6 2-2 6-2-6-6-2ZM13 89l1-4 2 4 4 1-4 2-2 4-1-4-4-2Z" fill="#f4dca2"/></svg></div>
      <div class="cascabeleo-copy"><p class="cascabeleo-kicker">CASA TOSICO <span aria-hidden="true">✦</span> <time datetime="2026-11-01">1 DE NOVIEMBRE</time></p><h2 id="cascabeleo-title">${heading(value.arrived)}</h2><p data-cascabeleo-copy>${copy(value.arrived)}</p></div>
      <div class="cascabeleo-clock" role="timer" aria-live="off" aria-label="Cuenta atrás para el cascabeleo"${value.arrived ? ' hidden' : ''}>${units.map(([key, label]) => `<div class="cascabeleo-unit"><span data-cascabeleo-unit="${key}">${pad(value[key])}</span><span class="cascabeleo-label">${label}</span></div>`).join('')}</div>
      <p class="cascabeleo-welcome"${value.arrived ? '' : ' hidden'}><span aria-hidden="true">✧</span>La Navidad<br>empieza en casa</p>
      <span class="cascabeleo-announcement" role="status" aria-live="polite"></span>
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
    if (currentTime() >= END) { section.hidden = true; unmount(); return; }
    const value = remaining();
    const wasArrived = section.classList.contains('cascabeleo-arrived');
    section.classList.toggle('cascabeleo-arrived', value.arrived);
    section.querySelector('.cascabeleo-clock').hidden = value.arrived;
    section.querySelector('.cascabeleo-welcome').hidden = !value.arrived;
    if (wasArrived !== value.arrived) {
      section.querySelector('#cascabeleo-title').textContent = heading(value.arrived);
      section.querySelector('[data-cascabeleo-copy]').textContent = copy(value.arrived);
      section.querySelector('.cascabeleo-announcement').textContent = value.arrived ? heading(true) : '';
    }
    for (const [key] of units) {
      const node = section.querySelector(`[data-cascabeleo-unit="${key}"]`);
      const text = pad(value[key]);
      if (node.textContent !== text) node.textContent = text;
    }
    if (!value.arrived && section.ownerDocument.visibilityState !== 'hidden') timer = setTimeout(refresh, 1000);
  }
  function mount(node) {
    unmount();
    section = node;
    if (!section) return;
    section.ownerDocument.addEventListener('visibilitychange', refresh);
    section.ownerDocument.addEventListener('castori:seasonchange', refresh);
    refresh();
  }
  root.CastoriCascabeleo = { render, mount, unmount, remaining };
})(typeof window === 'undefined' ? globalThis : window);

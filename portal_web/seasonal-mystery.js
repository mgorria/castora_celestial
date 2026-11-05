(function (root) {
  'use strict';
  const doc = root.document;
  const numerals = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII'];
  const escape = value => String(value).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const date = value => new Intl.DateTimeFormat('es-ES', { timeZone: 'Europe/Madrid', day: 'numeric', month: 'long' }).format(new Date(value));
  const tick = () => root.performance?.now() ?? Date.now();
  let section, snapshot, selected, timer, controller, generation = 0, fetchedAt = -Infinity, painted = '';

  function content() {
    if (!snapshot) return '<p class="mystery-loading" role="status">La Vaca está deslizando un sobre bajo la puerta…</p>';
    const entry = snapshot.entries.find(item => item.id === selected) || snapshot.entries.at(-1);
    if (!entry) return '';
    const index = snapshot.entries.indexOf(entry);
    return `<div class="mystery-heading"><div><p class="mystery-kicker">CORRESPONDENCIA RESERVADA · CASA TOSICO</p><h2 id="mystery-title">El gabinete de los siete sellos</h2><p class="mystery-intro">La Vaca ha escondido algo y se le escapa un MUUU cada vez que preguntas. Ha dejado siete sobres. Dice que no son pistas. Miente fatal.</p></div><span class="mystery-emblem" aria-hidden="true">✧<small>VII</small></span></div>
      <div class="mystery-body"><article class="mystery-letter" aria-labelledby="mystery-clue-title"><p class="mystery-letter-number">SOBRE ${numerals[index]} <span>·</span> ${escape(date(entry.release_at))}</p><h3 id="mystery-clue-title">${escape(entry.title)}</h3><div class="mystery-lines">${entry.lines.map(line => `<p>${escape(line) || '&nbsp;'}</p>`).join('')}</div><details class="mystery-hint"><summary>Mirar el reverso del sobre</summary><p>${escape(entry.hint)}</p></details></article>
      <aside class="mystery-dossier" aria-label="Los siete sobres"><p class="mystery-dossier-label">EL ARCHIVO DE LA VACA</p><div class="mystery-seals">${numerals.map((roman, i) => {
        const item = snapshot.entries[i];
        return item ? `<button type="button" data-mystery-id="${escape(item.id)}" aria-label="Leer sobre ${i + 1}" aria-pressed="${item.id === entry.id}"><span>${roman}</span><small>abierto</small></button>` : `<button type="button" disabled aria-label="Sobre ${i + 1}, todavía sellado"><span>${roman}</span><small>sellado</small></button>`;
      }).join('')}</div><p class="mystery-next">${snapshot.next_unlock_at ? `El siguiente sello cederá el <strong>${escape(date(snapshot.next_unlock_at))}</strong>.` : snapshot.closed ? 'Los siete sellos están abiertos. La última respuesta vive fuera de esta página.' : `El <strong>${escape(date(snapshot.finale_at))}</strong>, la última respuesta vivirá fuera de esta página.`}</p><p class="mystery-footnote">Conserva lo que encuentres.<br>Ninguna palabra ha llegado por casualidad.</p></aside></div>`;
  }
  function render() {
    return `<section class="seasonal-mystery" data-seasonal-mystery aria-label="El gabinete de los siete sellos"${snapshot?.visible === false ? ' hidden' : ''}><div data-mystery-content>${content()}</div><span class="mystery-announcement" role="status" aria-live="polite"></span></section>`;
  }
  function paint() {
    if (!section) return;
    section.hidden = snapshot?.visible === false || snapshot?.entries.length === 0;
    const key = JSON.stringify([snapshot?.entries, snapshot?.closed, snapshot?.next_unlock_at, selected]);
    if (key === painted) return;
    section.querySelector('[data-mystery-content]').innerHTML = content();
    painted = key;
  }
  function pause() { clearTimeout(timer); timer = null; }
  function schedule() {
    pause();
    if (!section || doc.visibilityState === 'hidden' || doc.body.dataset.access !== 'open') return;
    const next = snapshot?.next_unlock_at || (!snapshot?.closed && snapshot?.finale_at);
    const until = next ? Date.parse(next) - Date.parse(snapshot.server_now) - (tick() - fetchedAt) : 60000;
    timer = setTimeout(refresh, Math.max(1000, Math.min(60000, until)));
  }
  async function refresh() {
    pause();
    if (!section?.isConnected) { unmount(); return; }
    if (doc.visibilityState === 'hidden' || doc.body.dataset.access !== 'open') return;
    controller?.abort();
    controller = new AbortController();
    const version = ++generation;
    try {
      const value = await root.CastoriBridge.seasonalMystery(controller.signal);
      if (version !== generation || !section?.isConnected) return;
      if (!Array.isArray(value.entries) || !Number.isFinite(Date.parse(value.server_now))) throw new Error('Invalid mystery response');
      const previous = snapshot?.entries.at(-1)?.id;
      snapshot = value;
      fetchedAt = tick();
      const latest = snapshot.entries.at(-1)?.id;
      if (!selected || selected === previous) selected = latest;
      paint();
      if (previous && latest !== previous) section.querySelector('.mystery-announcement').textContent = 'La Vaca ha abierto un nuevo sobre.';
    } catch (error) {
      if (version !== generation || error.cancelled || error.name === 'AbortError' || !section?.isConnected) return;
      if (!snapshot) section.querySelector('[data-mystery-content]').innerHTML = '<div class="mystery-loading"><p>El sobre está de camino. No se ha perdido ninguna pista.</p><button type="button" data-mystery-retry>Volver a mirar el buzón</button></div>';
    } finally { if (version === generation) { controller = null; schedule(); } }
  }
  function onVisibility() {
    if (doc.visibilityState === 'hidden') { pause(); generation++; controller?.abort(); controller = null; }
    else refresh();
  }
  function onClick(event) {
    const button = event.target.closest?.('[data-mystery-id], [data-mystery-retry]');
    if (!button || !section?.contains(button)) return;
    if (button.hasAttribute('data-mystery-retry')) { refresh(); return; }
    const id = button.getAttribute('data-mystery-id');
    if (!snapshot?.entries.some(item => item.id === id)) return;
    selected = id;
    paint();
    section.querySelector(`[data-mystery-id="${id}"]`)?.focus({ preventScroll: true });
  }
  function unmount(clear = false) {
    pause(); generation++; controller?.abort(); controller = null;
    section?.removeEventListener('click', onClick);
    doc.removeEventListener('visibilitychange', onVisibility);
    root.removeEventListener?.('pageshow', refresh);
    section = null; painted = '';
    if (clear) { snapshot = null; selected = null; fetchedAt = -Infinity; }
  }
  function mount(node) {
    unmount(); section = node;
    if (!section) return;
    section.addEventListener('click', onClick);
    doc.addEventListener('visibilitychange', onVisibility);
    root.addEventListener('pageshow', refresh);
    paint();
    if (snapshot && tick() - fetchedAt < 60000) schedule(); else refresh();
  }
  root.CastoriMystery = { render, mount, unmount };
})(typeof window === 'undefined' ? globalThis : window);

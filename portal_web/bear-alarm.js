(function () {
  'use strict';

  const trigger = '.aqui manda el oso';
  const duration = 10000;
  const usedKey = 'castori-bear-alarm-used-v1';
  let active = null;

  function startSound() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return null;
    let context;
    try {
      context = new AudioContext();
      // Called in the original Send gesture, before any asynchronous work.
      const resumed = context.resume();
      resumed?.catch(() => {});
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = 'triangle';
      oscillator.connect(gain);
      gain.connect(context.destination);
      const now = context.currentTime;
      gain.gain.setValueAtTime(0, now);
      for (let i = 0; i < 20; i++) {
        const time = now + i * 0.5;
        oscillator.frequency.setValueAtTime(480, time);
        oscillator.frequency.linearRampToValueAtTime(920, time + 0.23);
        oscillator.frequency.linearRampToValueAtTime(480, time + 0.46);
        gain.gain.setValueAtTime(0, time);
        gain.gain.linearRampToValueAtTime(0.035, time + 0.03);
        gain.gain.setValueAtTime(0.035, time + 0.39);
        gain.gain.linearRampToValueAtTime(0, time + 0.48);
      }
      oscillator.start(now);
      // Audio has its own deadline, even if browser timers are throttled.
      oscillator.stop(now + duration / 1000);
      let closed = false;
      return () => {
        if (closed) return;
        closed = true;
        try { gain.gain.cancelScheduledValues(context.currentTime); gain.gain.setValueAtTime(0, context.currentTime); } catch (_) {}
        try { oscillator.stop(); oscillator.disconnect(); gain.disconnect(); } catch (_) {}
        try { context.close().catch(() => {}); } catch (_) {}
      };
    } catch (_) {
      try { context?.close().catch(() => {}); } catch (_) {}
      return null;
    }
  }

  function play(options = {}) {
    if (active || document.visibilityState === 'hidden') return false;
    let storage;
    try {
      storage = window.localStorage;
      // A permanent marker keeps the secret phrase harmless after the first show.
      if (!storage || storage.getItem(usedKey) !== null) return false;
    } catch (_) { return false; }
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    const deadline = performance.now() + duration;
    const dialog = document.createElement('dialog');
    dialog.id = 'bear-alarm';
    dialog.setAttribute('aria-labelledby', 'bear-alarm-title');
    dialog.setAttribute('aria-describedby', 'bear-alarm-description');
    dialog.innerHTML = `
      <div class="bear-alarm-embers" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></div>
      <div class="bear-alarm-flames" aria-hidden="true">${Array.from({ length: 11 }, (_, i) => `<i class="bear-flame bear-flame-${i}"></i>`).join('')}</div>
      <div class="bear-alarm-content">
        <div class="bear-alarm-warning"><span aria-hidden="true">!</span> PROTECCIÓN DE PATITA ACTIVADA</div>
        <div class="bear-alarm-cow" aria-hidden="true"><img src="assets/vaca-v2.png" alt=""><span class="bear-alarm-anger">╬</span><span class="bear-alarm-muuu">¡MUUU!</span></div>
        <p class="bear-alarm-eyebrow">LA VACA MÁGICA NO DA PERMISO</p>
        <h2 id="bear-alarm-title">¡OSO<br>DETECTADO!</h2>
        <p class="bear-alarm-order">¡Suelta el móvil, Miguel!</p>
        <p id="bear-alarm-description">Aquí manda <strong>Patita.</strong><br>Devuélvele el móvil a Sandra.</p>
        <div class="bear-alarm-countdown" aria-hidden="true"><span class="bear-alarm-count">10</span><span>segundos para<br>espantar al oso</span></div>
        <p class="bear-alarm-sr">Alerta de broma. Se cierra automáticamente en diez segundos.</p>
        <div class="bear-alarm-actions"><button type="button" class="bear-alarm-mute" aria-pressed="false">Silenciar alarma</button><button type="button" class="bear-alarm-close">Soy Patita · cerrar</button></div>
      </div>`;
    let timeout;
    let interval;
    let sound;
    let done = false;
    function finish(reason) {
      if (done) return;
      done = true;
      clearTimeout(timeout);
      clearInterval(interval);
      document.removeEventListener('visibilitychange', visibilityChanged);
      window.removeEventListener('pagehide', pageHidden);
      sound?.();
      if (dialog.open) dialog.close();
      dialog.remove();
      document.body.style.overflow = previousOverflow;
      active = null;
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
      if (typeof options.onFinish === 'function') options.onFinish(reason);
    }
    function visibilityChanged() { if (document.visibilityState === 'hidden') finish('hidden'); }
    function pageHidden() { finish('hidden'); }
    function updateCountdown() {
      const remaining = deadline - performance.now();
      if (remaining <= 0) { finish('complete'); return; }
      dialog.querySelector('.bear-alarm-count').textContent = String(Math.ceil(remaining / 1000));
    }
    dialog.addEventListener('cancel', event => { event.preventDefault(); finish('dismissed'); });
    dialog.addEventListener('close', () => finish('dismissed'));
    dialog.querySelector('.bear-alarm-close').addEventListener('click', () => finish('dismissed'));
    const mute = dialog.querySelector('.bear-alarm-mute');
    mute.addEventListener('click', () => {
      sound?.();
      sound = null;
      mute.textContent = 'Alarma silenciada';
      mute.setAttribute('aria-pressed', 'true');
      mute.disabled = true;
    });
    document.body.appendChild(dialog);
    try { dialog.showModal(); } catch (_) { dialog.remove(); return false; }
    try {
      // Persist before starting sound or timers; fail closed if storage is blocked.
      storage.setItem(usedKey, '1');
      if (storage.getItem(usedKey) !== '1') throw new Error('Alarm marker was not saved');
    } catch (_) {
      dialog.remove();
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
      return false;
    }
    document.body.style.overflow = 'hidden';
    active = { finish };
    sound = startSound();
    if (!sound) { mute.textContent = 'Alarma sin sonido'; mute.disabled = true; }
    document.addEventListener('visibilitychange', visibilityChanged);
    window.addEventListener('pagehide', pageHidden);
    timeout = setTimeout(() => finish('complete'), Math.max(0, deadline - performance.now()));
    interval = setInterval(updateCountdown, 100);
    return true;
  }

  window.CastoriBearAlarm = {
    matches: (animal, text) => animal === 'vaca' && text === trigger,
    play,
    stop: () => active?.finish('dismissed')
  };
}());

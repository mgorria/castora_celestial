(function (root) {
  'use strict';

  const SCORE_LENGTH = 26000;
  const clock = () => root.performance?.now() ?? Date.now();

  // The caller owns the trusted gesture. Loading this file never opens an audio context.
  function play({ duration = SCORE_LENGTH, isAllowed = () => true } = {}) {
    const length = Math.min(SCORE_LENGTH, Number.isFinite(duration) ? Math.max(0, duration) : SCORE_LENGTH);
    const started = clock(), nodes = new Set(), sources = new Set();
    let context, master, timer, finished = false, scheduled = false, noiseBuffer;
    const allowed = () => { try { return isAllowed() === true; } catch (_) { return false; } };
    const left = () => Math.max(0, length - (clock() - started));
    const track = node => { nodes.add(node); return node; };
    const disconnect = node => { try { node.disconnect(); } catch (_) { /* Optional browser audio. */ } nodes.delete(node); };

    function stop() {
      if (finished) return;
      finished = true;
      clearTimeout(timer); timer = null;
      if (master && context) {
        try { master.gain.cancelScheduledValues?.(context.currentTime); master.gain.setValueAtTime(0, context.currentTime); } catch (_) { /* Closing also silences the graph. */ }
      }
      for (const source of [...sources]) { source.onended = null; try { source.stop(); } catch (_) { /* Already ended. */ } }
      sources.clear();
      for (const node of [...nodes]) disconnect(node);
      if (context && context.state !== 'closed') { try { context.close()?.catch(() => {}); } catch (_) { /* The graph is already disconnected. */ } }
    }
    stop.available = false;
    Object.defineProperty(stop, 'active', { get: () => !finished && !!context });
    if (!length || !allowed()) { stop(); return stop; }
    const Audio = root.AudioContext || root.webkitAudioContext;
    if (!Audio) { stop(); return stop; }

    function watchdog() {
      if (finished) return;
      if (!left() || !allowed() || context.state === 'closed') { stop(); return; }
      timer = setTimeout(watchdog, Math.min(250, left()));
    }

    function score() {
      if (finished || scheduled) return;
      if (!allowed() || !left() || context.state !== 'running') { stop(); return; }
      scheduled = true;
      const passed = (clock() - started) / 1000;
      const base = context.currentTime, deadline = base + left() / 1000;
      master = track(context.createGain());
      master.gain.setValueAtTime(.46, base);
      master.gain.setValueAtTime(.46, Math.max(base, deadline - .08));
      master.gain.linearRampToValueAtTime(0, deadline);
      // This native deadline remains effective when a background tab stalls JS timers.
      master.gain.setValueAtTime(0, deadline);
      let output = master;
      if (context.createDynamicsCompressor) {
        const limiter = track(context.createDynamicsCompressor());
        limiter.threshold.setValueAtTime(-8, base);
        limiter.knee.setValueAtTime(4, base);
        limiter.ratio.setValueAtTime(16, base);
        limiter.attack.setValueAtTime(.002, base);
        limiter.release.setValueAtTime(.12, base);
        output.connect(limiter); output = limiter;
      }
      if (context.createWaveShaper) {
        const ceiling = track(context.createWaveShaper());
        const curve = new Float32Array(1025);
        for (let i = 0; i < curve.length; i++) curve[i] = .9 * Math.tanh((i * 2 / (curve.length - 1) - 1) / .9);
        ceiling.curve = curve; ceiling.oversample = '2x';
        output.connect(ceiling); output = ceiling;
      }
      output.connect(context.destination);

      function windowFor(at, duration) {
        if (at >= length / 1000 || at + duration <= passed) return null;
        const begin = base + Math.max(0, at - passed);
        const end = Math.min(deadline, base + at + duration - passed);
        if (end - begin < .005) return null;
        return { begin, end, progress: Math.max(0, passed - at) / duration };
      }
      function sourceChain(source, chain, start, end) {
        sources.add(source);
        source.onended = () => { sources.delete(source); for (const node of chain) disconnect(node); };
        source.start(start); source.stop(end);
      }
      function envelope(node, begin, end, volume, swell = false) {
        const span = end - begin;
        node.gain.setValueAtTime(.0001, begin);
        node.gain.exponentialRampToValueAtTime(Math.max(.0002, volume), begin + Math.min(swell ? span * .78 : .012, span * .8));
        node.gain.exponentialRampToValueAtTime(.0001, end);
      }
      function tone(frequency, at, duration, volume, type = 'sine', target = frequency) {
        const span = windowFor(at, duration); if (!span) return;
        const source = track(context.createOscillator()), gain = track(context.createGain());
        source.type = type;
        source.frequency.setValueAtTime(frequency + (target - frequency) * span.progress, span.begin);
        source.frequency.exponentialRampToValueAtTime(Math.max(20, target), span.end);
        envelope(gain, span.begin, span.end, volume);
        source.connect(gain); gain.connect(master);
        sourceChain(source, [source, gain], span.begin, span.end);
      }
      function noise(at, duration, volume, from = 1500, to = from, swell = false) {
        if (!context.createBuffer || !context.createBufferSource) return;
        const span = windowFor(at, duration); if (!span) return;
        if (!noiseBuffer) {
          noiseBuffer = context.createBuffer(1, Math.ceil(context.sampleRate * 2), context.sampleRate);
          const data = noiseBuffer.getChannelData(0);
          let seed = 173;
          for (let i = 0; i < data.length; i++) { seed = (Math.imul(seed, 1664525) + 1013904223) | 0; data[i] = (seed >>> 0) / 2147483648 - 1; }
        }
        const source = track(context.createBufferSource()), gain = track(context.createGain());
        const chain = [source, gain];
        source.buffer = noiseBuffer; source.loop = true;
        let output = source;
        if (context.createBiquadFilter) {
          const filter = track(context.createBiquadFilter()); chain.push(filter);
          filter.type = swell ? 'bandpass' : 'highpass';
          filter.frequency.setValueAtTime(from + (to - from) * span.progress, span.begin);
          filter.frequency.exponentialRampToValueAtTime(to, span.end);
          filter.Q.setValueAtTime(swell ? .7 : .45, span.begin);
          source.connect(filter); output = filter;
        }
        envelope(gain, span.begin, span.end, volume, swell);
        output.connect(gain); gain.connect(master);
        sourceChain(source, chain, span.begin, span.end);
      }
      function bell(frequency, at, duration = .75, volume = .24) {
        // Inharmonic, independently decaying partials make a struck metal bell.
        [[1, .65, 1], [2.01, .26, .62], [2.71, .16, .42], [4.06, .08, .25]].forEach(([ratio, level, decay]) => {
          tone(frequency * ratio, at, duration * decay, volume * level);
        });
      }
      function kick(at, volume = .52) { tone(155, at, .24, volume, 'sine', 43); tone(63, at + .01, .18, volume * .25, 'triangle', 38); }
      function snare(at, volume = .3) { noise(at, .11, volume, 1100); tone(185, at, .085, volume * .4, 'triangle', 120); }
      function brass(frequency, at, duration, volume = .25) {
        tone(frequency, at, duration, volume, 'triangle');
        tone(frequency * 1.003, at, duration * .92, volume * .36, 'sawtooth');
        tone(frequency * 2, at, duration * .76, volume * .22, 'triangle');
      }

      // 0–3 s: a theatrical two-tone alarm, with a comic descending bass stomp.
      kick(0, .7);
      for (let i = 0; i < 6; i++) {
        const hz = i % 2 ? 987.77 : 659.25;
        tone(hz * .91, i * .48, .42, .29, 'square', hz * 1.045);
        tone(hz / 2, i * .48, .38, .14, 'triangle', hz / 2 * .93);
      }
      [0.15, 1.1, 2.05].forEach((at, i) => bell([1568, 2093, 2637][i], at, .7, .32));

      // 3–9 s: marching percussion becomes a snare roll; the bells lift off.
      [3, 4.5, 6, 7.5, 8.65].forEach(at => kick(at));
      for (let i = 0; i < 12; i++) snare(3.25 + i * .25, .22 + i * .009);
      for (let i = 0; i < 24; i++) snare(6 + i * .12, .28 + i * .005);
      [1046.5, 1318.51, 1568, 2093, 1568, 2093, 2637, 3136, 2093, 2637].forEach((hz, i) => bell(hz, 3.1 + i * .55, .85, .32));
      [3, 5, 7].forEach((at, i) => brass([130.81, 164.81, 196][i], at, 1.35, .19));
      noise(7.7, 1.3, .45, 350, 6200, true);

      // 9–17 s: a sweeping wind tunnel, sparkling ascending/descending arpeggios.
      noise(9, 7.85, .55, 180, 6500, true);
      noise(10.5, 3.8, .2, 5500, 300, true);
      const orbit = [523.25, 659.25, 784, 1046.5, 1318.51, 1046.5, 784, 659.25];
      for (let i = 0; i < 64; i++) {
        const hz = orbit[i % orbit.length];
        tone(hz, 9 + i * .12, .19, .21, 'triangle');
        tone(hz * 2.005, 9 + i * .12, .12, .07);
      }
      [9, 11, 13, 15, 16.3].forEach((at, i) => bell([2093, 2637, 3136][i % 3], at, .9, .3));

      // 17–26 s: a major-key arrival fanfare with a dense sleigh-bell procession.
      const fanfare = [[523.25, 0, .24], [523.25, .3, .24], [784, .6, .48], [1046.5, 1.2, .65], [1318.51, 2, .48], [1174.66, 2.6, .48], [1046.5, 3.2, .65], [784, 4, .48], [880, 4.6, .48], [698.46, 5.2, .48], [784, 5.8, .65], [1046.5, 6.6, .9]];
      fanfare.forEach(([hz, at, duration]) => brass(hz, 17 + at, duration, .29));
      [[17, [261.63, 329.63, 392]], [19, [349.23, 440, 523.25]], [21, [392, 493.88, 587.33]], [23, [261.63, 329.63, 392]], [25, [261.63, 329.63, 392, 523.25]]].forEach(([at, chord]) => chord.forEach(hz => brass(hz, at, at === 25 ? .98 : .85, .19)));
      for (let i = 0; i < 8; i++) { kick(17 + i, .44); snare(17.5 + i, .3); }
      for (let i = 0; i < 39; i++) { bell([1568, 2093, 2637][i % 3], 17 + i * .22, .5, .23); noise(17 + i * .22, .065, .13, 6500); }
      noise(24.9, 1.08, .65, 2200, 8500);
      [0, .18, .36, .54].forEach((at, i) => bell([2093, 2637, 3136, 4186][i], 25.15 + at, .75, .32));
    }

    try {
      context = new Audio();
      stop.available = true;
      // Both operations happen synchronously inside the original click handler.
      const resumed = context.resume?.();
      const ready = () => { if (finished) return; try { score(); } catch (_) { stop(); } };
      if (context.state === 'running') ready();
      if (resumed?.then) resumed.then(ready, stop);
      else if (context.state !== 'running') stop();
      if (!finished) watchdog();
    } catch (_) { stop.available = false; stop(); }
    return stop;
  }

  root.CastoriVacaArrivalAudio = Object.freeze({ play });
})(typeof window === 'undefined' ? globalThis : window);

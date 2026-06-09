/* ══════════════════════════════════════════════════════════════════
   AETERNUS NEXUS — AVATAR ENGINE v2 (performance-optimised)
   Public API on window.NX:
     NX.init(canvas)         — start render loop
     NX.setState(name)       — morph state (idle/listening/thinking/
                               speaking/executing/alert)
     NX.state                — current state name
     NX.pulse(strength)      — shockwave + energy burst
     NX.setGaze(x,y)         — target gaze in [-1..1]
     NX.setHover(bool)       — pointer over core
     NX.setSpeakLevel(level) — TTS amplitude [0..1]
   Tweaks: window.__avatarTweaks {energy,glow,density,tracking}
══════════════════════════════════════════════════════════════════ */
(function () {
  const NX = (window.NX = window.NX || {});

  /* ── colour helpers ───────────────────────────────────────────── */
  function hslRGB(h, s, l) {
    h = (((h % 360) + 360) % 360) / 360;
    let r, g, b;
    if (s === 0) { r = g = b = l; }
    else {
      const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
      const hk = x => {
        if (x < 0) x += 1; if (x > 1) x -= 1;
        if (x < 1/6) return p + (q-p)*6*x;
        if (x < 1/2) return q;
        if (x < 2/3) return p + (q-p)*(2/3-x)*6;
        return p;
      };
      r = hk(h+1/3); g = hk(h); b = hk(h-1/3);
    }
    return [Math.round(r*255), Math.round(g*255), Math.round(b*255)];
  }
  function paletteFrom(h, s) {
    return {
      hot:    hslRGB(h, Math.min(1,s*0.55), 0.88),
      bri:    hslRGB(h, s, 0.60),
      mid:    hslRGB(h, s, 0.46),
      deep:   hslRGB(h, s*0.95, 0.33),
      dark:   hslRGB(h, s*0.90, 0.19),
      shadow: hslRGB(h, s*0.80, 0.09),
    };
  }
  const lerp = (a, b, f) => a + (b-a)*f;
  const lerpHue = (a, b, f) => { const d = ((b-a+540)%360)-180; return a+d*f; };

  /* ── state table ──────────────────────────────────────────────── */
  const STATES = {
    idle:      { hue: 43,  sat: 0.88, scanSp: .0060, ringMul: .70, rayInt: .70, coreBri: .85, pulseRate: 1.3, pulseAmp: .030, partMul: .60, jitter: .00 },
    listening: { hue: 174, sat: 0.80, scanSp: .0045, ringMul: .55, rayInt: .62, coreBri: .82, pulseRate: 1.8, pulseAmp: .050, partMul: .75, jitter: .00 },
    thinking:  { hue: 276, sat: 0.74, scanSp: .0130, ringMul: 1.65,rayInt:1.12, coreBri:1.00, pulseRate: 2.6, pulseAmp: .038, partMul:1.45, jitter: .14 },
    speaking:  { hue: 48,  sat: 0.96, scanSp: .0085, ringMul: .95, rayInt:1.00, coreBri:1.15, pulseRate: 2.0, pulseAmp: .045, partMul:1.00, jitter: .04 },
    executing: { hue: 150, sat: 0.72, scanSp: .0220, ringMul:1.25, rayInt:1.05, coreBri:1.02, pulseRate: 2.2, pulseAmp: .035, partMul:1.15, jitter: .05 },
    alert:     { hue: 2,   sat: 0.86, scanSp: .0170, ringMul:1.45, rayInt:1.35, coreBri:1.22, pulseRate: 5.2, pulseAmp: .090, partMul:1.35, jitter: .50 },
  };

  /* ── ring definitions (8 rings — trimmed from 13 for perf) ───── */
  const RINGS = [
    { r: 1.30, ys: .44, sp: -.040, a: .20, w: 0.8, tk: 12, gl: 0 },
    { r: 1.18, ys: .30, sp:  .060, a: .28, w: 1.0, tk: 10, gl: 0, bright: true },
    { r: 1.06, ys: .50, sp: -.078, a: .42, w: 1.4, tk:  9, gl: 0, bright: true },
    { r: .980, ys: .072,sp: -.028, a: .90, w: 3.0, tk:  8, dt: 6, gl: 6, bright: true, prime: true },
    { r: .910, ys: .44, sp:  .058, a: .70, w: 2.0, tk:  8, dt: 5, gl: 0, bright: true },
    { r: .840, ys: .32, sp: -.076, a: .55, w: 1.5, tk:  8, gl: 0 },
    { r: .770, ys: .58, sp:  .092, a: .48, w: 1.2, tk:  6, gl: 0 },
    { r: .700, ys: .24, sp: -.112, a: .42, w: 1.0, tk:  6, gl: 0 },
  ];
  RINGS.forEach((r, i) => { r._keep = (i*0.137+0.05)%1; });

  /* ── live params ──────────────────────────────────────────────── */
  const CUR = { hue:43, sat:.88, scanSp:.006, ringMul:.7, rayInt:.7, coreBri:.85, pulseRate:1.3, pulseAmp:.03, partMul:.6, jitter:0 };
  let PAL = paletteFrom(CUR.hue, CUR.sat);

  function tw() {
    const t = window.__avatarTweaks || {};
    // perf-lite: halve glow weight in lite mode
    const lite = !!(t.perfLite || window.__avatarPerfLite);
    return {
      energy:   t.energy   != null ? t.energy   : 1.4,
      glow:     lite ? 0 : (t.glow != null ? t.glow : 1.0),
      density:  t.density  != null ? t.density  : 0.55,
      tracking: t.tracking != null ? t.tracking : true,
    };
  }
  function C(shade, a) { const c = PAL[shade]; return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }

  /* ── engine state ─────────────────────────────────────────────── */
  let canvas, ctx, dpr, S, cx, cy, R, RB;
  let t = 0, scanA = 0, raf = 0, useInterval = false, loopStarted = false;
  let stars = [], shocks = [];
  let gazeTX = 0, gazeTY = 0, gazeX = 0, gazeY = 0;
  let hover = 0, hoverT = 0, pulseBoost = 0;
  NX.speakLevel = 0; NX.state = 'idle';
  let target = STATES.idle;
  let _lastFrame = 0;
  // Halo offscreen cache
  let _haloCanvas = null, _haloHue = -999, _haloR = -1;

  function listenLevel() { return .5 + .5*(.6*Math.sin(t*3.1)+.4*Math.sin(t*7.3+1.2)); }

  /* ── resize ───────────────────────────────────────────────────── */
  function resize() {
    const raw = NX._containerSize || Math.min(window.innerWidth, window.innerHeight, 520);
    S = Math.max(180, Math.min(raw, 520));
    RB = S * 0.430;          // eye fills ~86% of canvas diameter
    cx = S/2; cy = S/2;
    // Large canvas + high DPR = huge backing store: cap DPR at 1.5 when S > 400px
    const rawDpr = window.devicePixelRatio || 1;
    dpr = S > 400 ? Math.min(rawDpr, 1.5) : Math.min(rawDpr, 2);
    canvas.style.width  = S+'px';
    canvas.style.height = S+'px';
    canvas.width  = Math.round(S*dpr);
    canvas.height = Math.round(S*dpr);
    ctx = canvas.getContext('2d');
    _haloR = -1; // force halo regen at new size
  }

  /* ── setup ────────────────────────────────────────────────────── */
  function setup() {
    resize();
    stars = Array.from({ length: 32 }, () => ({
      x: Math.random()*S, y: Math.random()*S,
      r: Math.random()*.9+.2, o: Math.random()*.18+.03,
      ph: Math.random()*Math.PI*2, sp: Math.random()*.4+.15,
    }));
  }

  function ringVisible(ring, density) {
    if (ring.prime || ring.bright) return true;
    return ring._keep < density;
  }

  /* ── ring arc — shadowBlur capped at 6, only on prime ring ───── */
  function ringArc(ring, rr, alphaMult) {
    const a = ring.a * alphaMult;
    if (a < .008) return;
    const prime = ring.prime, bright = ring.bright;
    const col = prime ? C('hot', a) : bright ? C('bri', a) : C('mid', a);
    ctx.beginPath(); ctx.arc(0, 0, rr, 0, Math.PI*2);
    ctx.strokeStyle = col; ctx.lineWidth = ring.w;
    if (prime) {
      // One subtle glow pass only on the prime ring — shadowBlur capped at 6
      ctx.shadowBlur = 6; ctx.shadowColor = C('bri', .8);
    }
    ctx.stroke(); ctx.shadowBlur = 0;

    if (ring.tk) {
      const maj = Math.max(1, Math.round(ring.tk/6));
      for (let i = 0; i < ring.tk; i++) {
        const ang = i/ring.tk*Math.PI*2, big = i%maj===0, tl = rr*(big?.045:.018);
        ctx.beginPath();
        ctx.moveTo(Math.cos(ang)*rr, Math.sin(ang)*rr);
        ctx.lineTo(Math.cos(ang)*(rr+tl), Math.sin(ang)*(rr+tl));
        ctx.strokeStyle = C('mid', a*(big?.65:.25)); ctx.lineWidth = big?.8:.35; ctx.stroke();
      }
    }
    if (ring.dt) {
      for (let i = 0; i < ring.dt; i++) {
        const ang = i/ring.dt*Math.PI*2;
        ctx.beginPath(); ctx.arc(Math.cos(ang)*rr, Math.sin(ang)*rr, prime?3.5:2.2, 0, Math.PI*2);
        ctx.fillStyle = prime ? C('hot', 1) : C('bri', Math.min(1, a*1.4));
        ctx.fill();
      }
    }
  }

  function drawRings(front, density) {
    RINGS.forEach(ring => {
      if (!ringVisible(ring, density)) return;
      ctx.save(); ctx.translate(cx, cy);
      ctx.beginPath();
      front ? ctx.rect(-S*3, 0, S*6, S*3) : ctx.rect(-S*3, -S*3, S*6, S*3);
      ctx.clip();
      ctx.scale(1, ring.ys); ctx.rotate(t*ring.sp*CUR.ringMul);
      ringArc(ring, ring.r*R, front ? 1.0 : .45);
      ctx.restore();
    });
  }

  /* ── iris ─────────────────────────────────────────────────────── */
  function drawIris(ex, ey) {
    ctx.save();
    ctx.beginPath(); ctx.arc(ex, ey, R*.97, 0, Math.PI*2); ctx.clip();

    const ig = ctx.createRadialGradient(ex, ey, 0, ex, ey, R*.97);
    ig.addColorStop(0,   'rgba(2,1,0,1)');
    ig.addColorStop(.12, C('shadow', .99));
    ig.addColorStop(.28, C('dark', .96));
    ig.addColorStop(.50, C('deep', .94));
    ig.addColorStop(.72, C('dark', .96));
    ig.addColorStop(1,   'rgba(2,1,0,1)');
    ctx.beginPath(); ctx.arc(ex, ey, R*.97, 0, Math.PI*2);
    ctx.fillStyle = ig; ctx.fill();

    // 40 fibers (was 64) — no per-fiber createLinearGradient, use flat colour
    const numFib = 40;
    for (let i = 0; i < numFib; i++) {
      const ang = (i/numFib)*Math.PI*2 + t*.003;
      const ir = R*.12, or = R*(.55+Math.sin(i*2.17+1.3)*.06+Math.cos(i*3.7+.5)*.03);
      const al = .012 + Math.abs(Math.sin(i*.89+.4))*.013;
      ctx.beginPath();
      ctx.moveTo(ex+Math.cos(ang)*ir, ey+Math.sin(ang)*ir);
      ctx.lineTo(ex+Math.cos(ang)*or, ey+Math.sin(ang)*or);
      ctx.strokeStyle = C('deep', al); ctx.lineWidth = .45; ctx.stroke();
    }

    // 12 concentric iris rings (was 18)
    for (let i = 0; i < 12; i++) {
      const frac = .14+(i/12)*.78, al = .022+(i%4===0?.022:.006)+Math.abs(Math.sin(i*.75))*.008;
      ctx.beginPath(); ctx.arc(ex, ey, R*frac, 0, Math.PI*2);
      ctx.strokeStyle = C('deep', al); ctx.lineWidth = i%4===0?.65:.28; ctx.stroke();
    }

    // Pupil
    const pg = ctx.createRadialGradient(ex, ey, 0, ex, ey, R*.18);
    pg.addColorStop(0,   'rgba(0,0,0,1)');
    pg.addColorStop(.70, 'rgba(1,0,0,.97)');
    pg.addColorStop(1,   'rgba(4,2,0,.5)');
    ctx.beginPath(); ctx.arc(ex, ey, R*.18, 0, Math.PI*2);
    ctx.fillStyle = pg; ctx.fill();
    ctx.restore();
  }

  /* ── scan beam — no shadowBlur ────────────────────────────────── */
  function drawScan(ex, ey) {
    ctx.save();
    ctx.beginPath(); ctx.arc(ex, ey, R*.94, 0, Math.PI*2); ctx.clip();
    const sw = Math.PI*.18;
    for (let i = 8; i >= 0; i--) {
      const a0 = scanA - sw*(i/8), a1 = a0 - sw/8;
      ctx.beginPath(); ctx.moveTo(ex, ey); ctx.arc(ex, ey, R*.88, a1, a0); ctx.closePath();
      ctx.fillStyle = C('deep', .016*(1-i/8)); ctx.fill();
    }
    ctx.beginPath();
    ctx.moveTo(ex, ey);
    ctx.lineTo(ex+Math.cos(scanA)*R*.88, ey+Math.sin(scanA)*R*.88);
    ctx.strokeStyle = C('bri', .30); ctx.lineWidth = 1.2; ctx.stroke();
    ctx.restore();
  }

  function tri(s, off) { const e = s+(off||0); ctx.beginPath(); ctx.moveTo(0,-e); ctx.lineTo(e*.866,e*.5); ctx.lineTo(-e*.866,e*.5); ctx.closePath(); }

  /* ── shockwaves ───────────────────────────────────────────────── */
  function drawShocks() {
    for (let i = shocks.length-1; i >= 0; i--) {
      const s = shocks[i], age = t-s.t0, life = .9;
      if (age > life) { shocks.splice(i,1); continue; }
      const f = age/life, rr = R*(1+f*1.6), a = (1-f)*.4*s.str;
      ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI*2);
      ctx.strokeStyle = C('bri', a); ctx.lineWidth = 2*(1-f)+.3; ctx.stroke();
    }
  }

  /* ── main frame ───────────────────────────────────────────────── */
  function frame() {
    if (NX._paused) { if (!useInterval) raf = requestAnimationFrame(frame); return; }
    const _now = performance.now();
    // 30fps cap at idle (no gaze movement)
    if (NX.state === 'idle' && Math.abs(gazeTX) < .02 && Math.abs(gazeTY) < .02 && _now-_lastFrame < 33) {
      if (!useInterval) raf = requestAnimationFrame(frame); return;
    }
    _lastFrame = _now;
    NX._f = (NX._f||0)+1;
    loopStarted = true;
    try {
      const k = .06;
      CUR.hue      = lerpHue(CUR.hue,      target.hue,      k);
      CUR.sat      = lerp(CUR.sat,          target.sat,      k);
      CUR.scanSp   = lerp(CUR.scanSp,       target.scanSp,   k);
      CUR.ringMul  = lerp(CUR.ringMul,      target.ringMul,  k);
      CUR.rayInt   = lerp(CUR.rayInt,       target.rayInt,   k);
      CUR.coreBri  = lerp(CUR.coreBri,      target.coreBri,  k);
      CUR.pulseRate= lerp(CUR.pulseRate,    target.pulseRate, k);
      CUR.pulseAmp = lerp(CUR.pulseAmp,     target.pulseAmp, k);
      CUR.partMul  = lerp(CUR.partMul,      target.partMul,  k);
      CUR.jitter   = lerp(CUR.jitter,       target.jitter,   k);
      PAL = paletteFrom(CUR.hue, CUR.sat);

      const T = tw();
      const energy = T.energy, density = T.density;

      gazeX = lerp(gazeX, T.tracking ? gazeTX : 0, .08);
      gazeY = lerp(gazeY, T.tracking ? gazeTY : 0, .08);
      hoverT = lerp(hoverT, hover, .08);
      pulseBoost = lerp(pulseBoost, 0, .05);

      t += .0068; scanA += CUR.scanSp;

      let breath = 1 + CUR.pulseAmp*Math.sin(t*CUR.pulseRate);
      let coreBoost = CUR.coreBri*(1+hoverT*.10) + pulseBoost*.4;
      if (NX.state === 'speaking') { breath += NX.speakLevel*.05; coreBoost += NX.speakLevel*.28; }
      if (NX.state === 'listening') { const ll = listenLevel(); breath += ll*.025; coreBoost += ll*.10; }
      coreBoost += pulseBoost*.3;
      R = RB * breath;

      const jit = CUR.jitter;
      const jx = jit ? (Math.random()-.5)*jit*5 : 0;
      const jy = jit ? (Math.random()-.5)*jit*5 : 0;
      cx = S/2+jx; cy = S/2+jy;

      const maxG = R * .07;
      const ex = cx + gazeX*maxG, ey = cy + gazeY*maxG;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, S, S);

      /* 1. stars (32, static alpha scale) */
      stars.forEach(s => {
        const o = s.o*(.5+Math.sin(t*s.sp+s.ph)*.35);
        ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI*2);
        ctx.fillStyle = `rgba(185,205,235,${o})`; ctx.fill();
      });

      /* 2. atmosphere halo — offscreen, max size 3.2R, cached until hue/R changes */
      const _hR = Math.round(R);
      if (Math.abs(CUR.hue-_haloHue) > 2 || _hR !== _haloR) {
        const sz = Math.round(R*2.6)*2;  // tight ambient glow only
        if (!_haloCanvas) _haloCanvas = document.createElement('canvas');
        _haloCanvas.width = _haloCanvas.height = sz;
        const hc = _haloCanvas.getContext('2d');
        const hx = sz/2, hy = sz/2;
        // One outer halo (was 3)
        const hg = hc.createRadialGradient(hx, hy, R*.3, hx, hy, sz/2);
        hg.addColorStop(0,   C('mid', .38));
        hg.addColorStop(.30, C('deep', .18));
        hg.addColorStop(.60, C('dark', .07));
        hg.addColorStop(1,   'transparent');
        hc.beginPath(); hc.arc(hx, hy, sz/2, 0, Math.PI*2);
        hc.fillStyle = hg; hc.fill();
        _haloHue = CUR.hue; _haloR = _hR;
      }
      ctx.globalAlpha = energy*.75;
      ctx.drawImage(_haloCanvas, cx-_haloCanvas.width/2, cy-_haloCanvas.height/2,
                    _haloCanvas.width, _haloCanvas.height);
      ctx.globalAlpha = 1;

      /* 3. back rings */
      drawRings(false, density);

      /* 4. sphere body */
      const sg = ctx.createRadialGradient(cx-R*.18, cy-R*.16, R*.02, cx, cy, R);
      sg.addColorStop(0,   C('dark', .50));
      sg.addColorStop(.12, 'rgba(8,5,2,.95)');
      sg.addColorStop(.30, 'rgba(4,6,18,.98)');
      sg.addColorStop(.60, 'rgba(2,3,10,1)');
      sg.addColorStop(1,   'rgba(1,1,3,1)');
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI*2);
      ctx.fillStyle = sg; ctx.fill();

      /* 5. iris */
      drawIris(ex, ey);

      /* 6. scan */
      drawScan(ex, ey);

      /* 7. core glow — 2 passes (was 2, keep) — no shadowBlur */
      let g = ctx.createRadialGradient(ex, ey, 0, ex, ey, R*.75*Math.min(1.25,coreBoost));
      g.addColorStop(0,   'rgba(255,255,235,1)');
      g.addColorStop(.06, C('hot', 1));
      g.addColorStop(.16, C('bri', .90));
      g.addColorStop(.32, C('mid', .75));
      g.addColorStop(.52, C('deep', .38));
      g.addColorStop(.75, C('dark', .14));
      g.addColorStop(1,   'transparent');
      ctx.beginPath(); ctx.arc(ex, ey, R*.75, 0, Math.PI*2); ctx.fillStyle = g; ctx.fill();
      g = ctx.createRadialGradient(ex, ey, 0, ex, ey, R*.18);
      g.addColorStop(0,   'rgba(255,255,255,1)');
      g.addColorStop(.20, 'rgba(255,255,235,.90)');
      g.addColorStop(.50, C('hot', .50));
      g.addColorStop(1,   'transparent');
      ctx.beginPath(); ctx.arc(ex, ey, R*.18, 0, Math.PI*2); ctx.fillStyle = g; ctx.fill();

      /* 8. energy rays — 10 (was 16), no per-ray createLinearGradient */
      const rays = 10;
      for (let i = 0; i < rays; i++) {
        const a = i/rays*Math.PI*2 + t*.040;
        const ln = R*(.28+Math.sin(t*1.38+i*.68)*.045)*(0.7+CUR.rayInt*.45);
        const al = (.22+Math.sin(t*1.12+i*.48)*.09)*CUR.rayInt*energy;
        ctx.beginPath();
        ctx.moveTo(ex, ey);
        ctx.lineTo(ex+Math.cos(a)*ln, ey+Math.sin(a)*ln);
        ctx.strokeStyle = C('bri', al); ctx.lineWidth = .7; ctx.stroke();
      }

      /* 9. corneal highlights — no shadowBlur */
      ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI*2); ctx.clip();
      const hx = cx-gazeX*maxG*.4, hy = cy-gazeY*maxG*.4;
      const hl = ctx.createRadialGradient(hx-R*.36, hy-R*.33, 0, hx-R*.36, hy-R*.33, R*.36);
      hl.addColorStop(0,   'rgba(255,248,225,.48)');
      hl.addColorStop(.25, 'rgba(248,232,180,.24)');
      hl.addColorStop(1,   'transparent');
      ctx.fillStyle = hl; ctx.fillRect(cx-R, cy-R, R*2, R*2);
      ctx.restore();

      /* 10. rim — shadowBlur capped at 8 */
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI*2);
      ctx.strokeStyle = C('mid', .85); ctx.lineWidth = 2.0;
      ctx.shadowBlur = 8; ctx.shadowColor = C('bri', .70); ctx.stroke(); ctx.shadowBlur = 0;

      /* 11. aperture rings (no shadowBlur) */
      [.945, .900].forEach((f, i) => {
        ctx.save(); ctx.translate(cx, cy); ctx.scale(1, .97-i*.018);
        ctx.beginPath(); ctx.arc(0, 0, R*f, 0, Math.PI*2);
        ctx.strokeStyle = C('deep', .07+i*.018); ctx.lineWidth = .6+i*.15; ctx.stroke();
        ctx.restore();
      });

      /* 12. front rings */
      drawRings(true, density);

      /* 13. shockwaves */
      drawShocks();

      /* 14. triangle — 3 strokes (was 6), no shadowBlur */
      const ts = R*.220, pu = (1+Math.sin(t*1.85)*.024)*(1+pulseBoost*.12);
      ctx.save(); ctx.translate(ex, ey); ctx.scale(pu, pu);
      // fill
      tri(ts);
      const tf = ctx.createLinearGradient(0, -ts, 0, ts*.55);
      tf.addColorStop(0, C('hot', .20)); tf.addColorStop(.5, C('bri', .10)); tf.addColorStop(1, C('mid', .03));
      ctx.fillStyle = tf; ctx.fill();
      // outer stroke
      tri(ts); ctx.strokeStyle = C('bri', .22); ctx.lineWidth = 8; ctx.stroke();
      // sharp rim
      tri(ts); ctx.strokeStyle = C('hot', .88); ctx.lineWidth = 1.8; ctx.stroke();
      // inner dot
      ctx.beginPath(); ctx.arc(0, 0, R*.020, 0, Math.PI*2);
      ctx.fillStyle = 'rgba(255,252,230,.95)'; ctx.fill();
      ctx.restore();

    } catch(err) { window.__nxErr = (err&&err.stack)||String(err); }
    if (!useInterval) raf = requestAnimationFrame(frame);
  }

  /* ── public API ───────────────────────────────────────────────── */
  NX.setState = function(name) {
    if (!STATES[name]) return;
    NX.state = name; target = Object.assign({}, STATES[name]);
    if (name === 'idle') {
      const a = (window.__avatarTweaks||{}).accentIdle;
      if (a) { target.hue = a.hue; target.sat = a.sat; }
    }
    window.dispatchEvent(new CustomEvent('nx-state', { detail: name }));
  };
  NX.pulse = function(str) {
    str = str||1; pulseBoost = Math.min(1.2, pulseBoost+0.7*str);
    shocks.push({ t0: t, str });
  };
  NX.setGaze  = function(x, y) { gazeTX = x==null?0:Math.max(-1,Math.min(1,x)); gazeTY = y==null?0:Math.max(-1,Math.min(1,y)); };
  NX.setHover = function(b) { hover = b?1:0; };
  NX.setSpeakLevel = function(l) { NX.speakLevel = Math.max(0,Math.min(1,Number(l)||0)); };

  function startLoop() {
    loopStarted = false; useInterval = false;
    raf = requestAnimationFrame(function probe(){ loopStarted = true; raf = requestAnimationFrame(frame); });
    setTimeout(function(){ if (!loopStarted) { cancelAnimationFrame(raf); useInterval = true; raf = setInterval(frame,16); } }, 200);
  }
  NX.init = function(cv) {
    canvas = cv; setup();
    let timer;
    window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(resize, 150); });
    startLoop();
  };
})();

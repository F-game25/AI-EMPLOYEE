/* ══════════════════════════════════════════════════════════════════
   AETERNUS NEXUS — INTERACTIVE AVATAR ENGINE
   Cognitive-eye renderer, fully state + parameter driven.
   Public API on window.NX:
     NX.init(canvas)        — start render loop
     NX.setState(name)      — morph to a state (idle/listening/thinking/
                              speaking/executing/alert)
     NX.state               — current state name
     NX.pulse(strength)     — emit a shockwave + energy burst (click)
     NX.setGaze(x,y)        — target gaze in [-1..1] (mouse), null=center
     NX.setHover(bool)      — pointer over the core
     NX.speakLevel          — read-only 0..1 (drives subtitle sync glow)
   Tweaks read live from window.__avatarTweaks.
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
      const hk = (x) => {
        if (x < 0) x += 1; if (x > 1) x -= 1;
        if (x < 1 / 6) return p + (q - p) * 6 * x;
        if (x < 1 / 2) return q;
        if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6;
        return p;
      };
      r = hk(h + 1 / 3); g = hk(h); b = hk(h - 1 / 3);
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
  }
  function paletteFrom(h, s) {
    return {
      hot:    hslRGB(h, Math.min(1, s * 0.55), 0.88),
      bri:    hslRGB(h, s, 0.60),
      mid:    hslRGB(h, s, 0.46),
      deep:   hslRGB(h, s * 0.95, 0.33),
      dark:   hslRGB(h, s * 0.90, 0.19),
      shadow: hslRGB(h, s * 0.80, 0.09),
    };
  }
  const lerp = (a, b, f) => a + (b - a) * f;
  const lerpHue = (a, b, f) => { let d = ((b - a + 540) % 360) - 180; return a + d * f; };

  /* ── state table ──────────────────────────────────────────────── */
  const STATES = {
    idle:      { hue: 43,  sat: 0.88, scanSp: 0.0060, ringMul: 0.70, rayInt: 0.70, coreBri: 0.85, pulseRate: 1.3, pulseAmp: 0.030, partMul: 0.60, jitter: 0.00 },
    listening: { hue: 174, sat: 0.80, scanSp: 0.0045, ringMul: 0.55, rayInt: 0.62, coreBri: 0.82, pulseRate: 1.8, pulseAmp: 0.050, partMul: 0.75, jitter: 0.00 },
    thinking:  { hue: 276, sat: 0.74, scanSp: 0.0130, ringMul: 1.65, rayInt: 1.12, coreBri: 1.00, pulseRate: 2.6, pulseAmp: 0.038, partMul: 1.45, jitter: 0.14 },
    speaking:  { hue: 48,  sat: 0.96, scanSp: 0.0085, ringMul: 0.95, rayInt: 1.00, coreBri: 1.15, pulseRate: 2.0, pulseAmp: 0.045, partMul: 1.00, jitter: 0.04 },
    executing: { hue: 150, sat: 0.72, scanSp: 0.0220, ringMul: 1.25, rayInt: 1.05, coreBri: 1.02, pulseRate: 2.2, pulseAmp: 0.035, partMul: 1.15, jitter: 0.05 },
    alert:     { hue: 2,   sat: 0.86, scanSp: 0.0170, ringMul: 1.45, rayInt: 1.35, coreBri: 1.22, pulseRate: 5.2, pulseAmp: 0.090, partMul: 1.35, jitter: 0.50 },
  };

  /* ── ring definitions ─────────────────────────────────────────── */
  const RINGS = [
    { r: 2.05, ys: .38, sp:  .008, a: .16, w: .8,  tk: 36, dt: 18, gl: 5 },
    { r: 1.90, ys: .62, sp: -.014, a: .20, w: .9,  tk: 32, dt: 16, gl: 6 },
    { r: 1.76, ys: .28, sp:  .022, a: .26, w: 1.0, tk: 28, dt: 14, gl: 8 },
    { r: 1.63, ys: .52, sp: -.032, a: .32, w: 1.1, tk: 26, dt: 14, gl: 9 },
    { r: 1.51, ys: .22, sp:  .042, a: .38, w: 1.3, tk: 22, dt: 12, gl: 11 },
    { r: 1.40, ys: .68, sp: -.054, a: .44, w: 1.4, tk: 20, dt: 12, gl: 13 },
    { r: 1.30, ys: .36, sp:  .068, a: .52, w: 1.6, tk: 18, dt: 10, gl: 15, bright: true },
    { r: 1.21, ys: .50, sp: -.082, a: .62, w: 1.9, tk: 16, dt: 10, gl: 19, bright: true },
    { r: 1.12, ys: .24, sp:  .095, a: .74, w: 2.3, tk: 16, dt: 9,  gl: 26, bright: true },
    { r: 1.02, ys: .072,sp: -.028, a: 1.0, w: 3.6, tk: 14, dt: 8,  gl: 42, bright: true, prime: true },
    { r: .942, ys: .44, sp:  .058, a: .82, w: 2.6, tk: 12, dt: 8,  gl: 28, bright: true },
    { r: .870, ys: .32, sp: -.076, a: .70, w: 2.1, tk: 12, dt: 7,  gl: 20 },
    { r: .802, ys: .58, sp:  .092, a: .62, w: 1.8, tk: 10, dt: 6,  gl: 16 },
    { r: .738, ys: .24, sp: -.112, a: .57, w: 1.6, tk: 10, dt: 6,  gl: 13 },
    { r: .676, ys: .46, sp:  .132, a: .52, w: 1.4, tk: 8,  dt: 5,  gl: 10 },
    { r: .616, ys: .36, sp: -.155, a: .49, w: 1.3, tk: 8,           gl: 9 },
    { r: .558, ys: .62, sp:  .175, a: .46, w: 1.2, tk: 8,           gl: 8 },
    { r: .502, ys: .28, sp: -.195, a: .44, w: 1.1,                  gl: 7 },
    { r: .448, ys: .48, sp:  .215, a: .42, w: 1.0,                  gl: 6 },
  ];
  RINGS.forEach((r, i) => { r._keep = ((i * 0.137 + 0.05) % 1); });

  /* ── live, interpolated parameters ────────────────────────────── */
  const CUR = { hue: 43, sat: 0.88, scanSp: .006, ringMul: .7, rayInt: .7, coreBri: .85, pulseRate: 1.3, pulseAmp: .03, partMul: .6, jitter: 0 };
  let PAL = paletteFrom(CUR.hue, CUR.sat);

  function tw() {
    const t = window.__avatarTweaks || {};
    return {
      energy: t.energy != null ? t.energy : 1,
      glow: t.glow != null ? t.glow : 1,
      density: t.density != null ? t.density : 1,
      tracking: t.tracking != null ? t.tracking : true,
    };
  }
  function C(shade, a) { const c = PAL[shade]; return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }

  /* ── engine state ─────────────────────────────────────────────── */
  let canvas, ctx, dpr, S, cx, cy, R, RB;
  let t = 0, scanA = 0, raf = 0, useInterval = false, loopStarted = false;
  let stars = [], oParticles = [], shocks = [];
  let gazeTX = 0, gazeTY = 0, gazeX = 0, gazeY = 0;
  let hover = 0, hoverT = 0;
  let pulseBoost = 0;
  NX.speakLevel = 0;
  NX.state = 'idle';
  let target = STATES.idle;

  /* synthetic envelopes */
  function listenLevel() { return 0.5 + 0.5 * (0.6 * Math.sin(t * 3.1) + 0.4 * Math.sin(t * 7.3 + 1.2)); }

  /* ── resize (geometry only — no particle regen) ──────────────── */
  function resize() {
    const sz = NX._containerSize || Math.max(320, Math.min(window.innerWidth, window.innerHeight));
    S = sz; RB = S * 0.300;
    cx = S / 2; cy = S / 2;
    dpr = window.devicePixelRatio || 1;
    canvas.style.width  = S + 'px'; canvas.style.height = S + 'px';
    canvas.width  = Math.round(S * dpr); canvas.height = Math.round(S * dpr);
    ctx = canvas.getContext('2d');
  }

  /* ── setup (full init — particles + geometry) ─────────────────── */
  function setup() {
    resize();
    stars = Array.from({ length: 300 }, () => ({
      x: Math.random() * S, y: Math.random() * S, r: Math.random() * 1.3 + .2,
      o: Math.random() * .24 + .04, ph: Math.random() * Math.PI * 2, sp: Math.random() * .5 + .2,
    }));
    oParticles = Array.from({ length: 90 }, () => {
      const ri = Math.floor(Math.random() * RINGS.length);
      return { ring: RINGS[ri], angle: Math.random() * Math.PI * 2, sp: RINGS[ri].sp * (2.5 + Math.random() * 3.5), o: .5 + Math.random() * .5, sz: 1.6 + Math.random() * 3.4, ph: Math.random() * Math.PI * 2 };
    });
  }

  function ringVisible(ring, density) {
    if (ring.prime || ring.bright) return true;
    return ring._keep < density;
  }

  /* ── ring arc ─────────────────────────────────────────────────── */
  function ringArc(ring, rr, alphaMult, glowMul) {
    const a = ring.a * alphaMult;
    if (a < .006) return;
    const prime = ring.prime, bright = ring.bright;
    const col = prime ? C('hot', a) : bright ? C('bri', a) : C('mid', a);
    if (prime) {
      [[rr, ring.gl * 4, a * .28], [rr, ring.gl * 2.2, a * .62], [rr, ring.gl, a * .95]].forEach(([r, bl, oa]) => {
        ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2);
        ctx.strokeStyle = C('bri', oa); ctx.lineWidth = ring.w * 1.15;
        ctx.shadowBlur = bl * glowMul; ctx.shadowColor = C('bri', .95); ctx.stroke(); ctx.shadowBlur = 0;
      });
    } else {
      ctx.beginPath(); ctx.arc(0, 0, rr, 0, Math.PI * 2);
      ctx.strokeStyle = col; ctx.lineWidth = ring.w;
      if (ring.gl) { ctx.shadowBlur = ring.gl * glowMul; ctx.shadowColor = bright ? C('mid', a * .85) : C('deep', a * .75); }
      ctx.stroke(); ctx.shadowBlur = 0;
    }
    if (ring.tk) {
      const maj = Math.max(1, Math.round(ring.tk / 8));
      for (let i = 0; i < ring.tk; i++) {
        const ang = i / ring.tk * Math.PI * 2, big = i % maj === 0, tl = rr * (big ? .050 : .022);
        ctx.beginPath(); ctx.moveTo(Math.cos(ang) * rr, Math.sin(ang) * rr); ctx.lineTo(Math.cos(ang) * (rr + tl), Math.sin(ang) * (rr + tl));
        ctx.strokeStyle = C('mid', a * (big ? .72 : .32)); ctx.lineWidth = big ? .95 : .44; ctx.stroke();
      }
    }
    if (ring.dt) {
      for (let i = 0; i < ring.dt; i++) {
        const ang = i / ring.dt * Math.PI * 2, ds = prime ? 4.2 : bright ? 3.2 : 2.4;
        ctx.beginPath(); ctx.arc(Math.cos(ang) * rr, Math.sin(ang) * rr, ds, 0, Math.PI * 2);
        ctx.fillStyle = prime ? C('hot', 1) : C('bri', Math.min(1, a * 1.5));
        if (ring.gl > 8) { ctx.shadowBlur = (prime ? 14 : 8) * glowMul; ctx.shadowColor = C('bri', .92); }
        ctx.fill(); ctx.shadowBlur = 0;
      }
    }
  }
  function drawRings(front, density, glowMul) {
    RINGS.forEach(ring => {
      if (!ringVisible(ring, density)) return;
      ctx.save(); ctx.translate(cx, cy);
      ctx.beginPath();
      front ? ctx.rect(-S * 3, 0, S * 6, S * 3) : ctx.rect(-S * 3, -S * 3, S * 6, S * 3);
      ctx.clip();
      ctx.scale(1, ring.ys); ctx.rotate(t * ring.sp * CUR.ringMul);
      ringArc(ring, ring.r * R, front ? 1.0 : .55, glowMul);
      ctx.restore();
    });
  }

  /* ── iris ─────────────────────────────────────────────────────── */
  function drawIris(ex, ey) {
    ctx.save();
    ctx.beginPath(); ctx.arc(ex, ey, R * .97, 0, Math.PI * 2); ctx.clip();
    const ig = ctx.createRadialGradient(ex, ey, 0, ex, ey, R * .97);
    ig.addColorStop(0, 'rgba(2,1,0,1)'); ig.addColorStop(.11, 'rgba(4,2,0,1)');
    ig.addColorStop(.21, C('shadow', .99)); ig.addColorStop(.32, C('dark', .97));
    ig.addColorStop(.46, C('deep', .95)); ig.addColorStop(.58, C('deep', .93));
    ig.addColorStop(.68, C('dark', .95)); ig.addColorStop(.79, C('shadow', .97));
    ig.addColorStop(.89, 'rgba(6,4,2,.99)'); ig.addColorStop(1, 'rgba(2,1,0,1)');
    ctx.beginPath(); ctx.arc(ex, ey, R * .97, 0, Math.PI * 2); ctx.fillStyle = ig; ctx.fill();

    const numFib = 96;
    for (let i = 0; i < numFib; i++) {
      const ang = (i / numFib) * Math.PI * 2 + t * 0.003;
      const ir = R * .13, or = R * (.58 + Math.sin(i * 2.17 + 1.3) * .07 + Math.cos(i * 3.7 + .5) * .04);
      const al = .015 + Math.abs(Math.sin(i * .89 + .4)) * .016;
      const lg = ctx.createLinearGradient(ex + Math.cos(ang) * ir, ey + Math.sin(ang) * ir, ex + Math.cos(ang) * or, ey + Math.sin(ang) * or);
      lg.addColorStop(0, 'transparent'); lg.addColorStop(.20, C('deep', al)); lg.addColorStop(.58, C('dark', al * .65)); lg.addColorStop(1, 'transparent');
      ctx.beginPath(); ctx.moveTo(ex + Math.cos(ang) * ir, ey + Math.sin(ang) * ir); ctx.lineTo(ex + Math.cos(ang) * or, ey + Math.sin(ang) * or);
      ctx.strokeStyle = lg; ctx.lineWidth = .52; ctx.stroke();
    }
    for (let i = 0; i < 32; i++) {
      const frac = .12 + (i / 32) * .82, al = .035 + (i % 4 === 0 ? .035 : .010) + Math.abs(Math.sin(i * .75)) * .018;
      ctx.beginPath(); ctx.arc(ex, ey, R * frac, 0, Math.PI * 2);
      ctx.strokeStyle = i < 9 ? C('dark', al) : C('deep', al); ctx.lineWidth = i % 5 === 0 ? .9 : .4; ctx.stroke();
    }
    for (let i = 0; i < 12; i++) {
      const ang = (i / 12) * Math.PI * 2 + .8, fr = .35 + Math.sin(i * 1.9) * .13, cr = R * (.020 + Math.abs(Math.sin(i * 3.3)) * .014);
      ctx.beginPath(); ctx.arc(ex + Math.cos(ang) * R * fr, ey + Math.sin(ang) * R * fr, cr, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(8,3,0,.22)'; ctx.fill();
    }
    ctx.beginPath();
    for (let i = 0; i < 64; i++) {
      const ang = i / 64 * Math.PI * 2, fr = R * (.225 + Math.sin(i * 3.1 + .7) * .008 + Math.cos(i * 5.3) * .004);
      i === 0 ? ctx.moveTo(ex + Math.cos(ang) * fr, ey + Math.sin(ang) * fr) : ctx.lineTo(ex + Math.cos(ang) * fr, ey + Math.sin(ang) * fr);
    }
    ctx.closePath(); ctx.strokeStyle = C('deep', .14); ctx.lineWidth = 1.8; ctx.stroke();

    const pg = ctx.createRadialGradient(ex, ey, 0, ex, ey, R * .18);
    pg.addColorStop(0, 'rgba(0,0,0,1)'); pg.addColorStop(.72, 'rgba(1,0,0,.97)'); pg.addColorStop(1, 'rgba(4,2,0,.5)');
    ctx.beginPath(); ctx.arc(ex, ey, R * .18, 0, Math.PI * 2); ctx.fillStyle = pg; ctx.fill();
    ctx.restore();
  }

  /* ── scan beam ────────────────────────────────────────────────── */
  function drawScan(ex, ey, glowMul) {
    ctx.save();
    ctx.beginPath(); ctx.arc(ex, ey, R * .94, 0, Math.PI * 2); ctx.clip();
    const sw = Math.PI * .20;
    for (let i = 12; i >= 0; i--) {
      const a0 = scanA - sw * (i / 12), a1 = a0 - sw / 12;
      ctx.beginPath(); ctx.moveTo(ex, ey); ctx.arc(ex, ey, R * .88, a1, a0); ctx.closePath();
      ctx.fillStyle = C('deep', .020 * (1 - i / 12)); ctx.fill();
    }
    ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex + Math.cos(scanA) * R * .90, ey + Math.sin(scanA) * R * .90);
    ctx.strokeStyle = C('bri', .35); ctx.lineWidth = 1.5; ctx.shadowBlur = 10 * glowMul; ctx.shadowColor = C('bri', .65); ctx.stroke(); ctx.shadowBlur = 0;
    ctx.beginPath(); ctx.arc(ex + Math.cos(scanA) * R * .88, ey + Math.sin(scanA) * R * .88, 3, 0, Math.PI * 2);
    ctx.fillStyle = C('hot', .6); ctx.shadowBlur = 8 * glowMul; ctx.shadowColor = C('bri', .8); ctx.fill(); ctx.shadowBlur = 0;
    ctx.restore();
  }

  function tri(s, off) { const e = s + (off || 0); ctx.beginPath(); ctx.moveTo(0, -e); ctx.lineTo(e * .866, e * .5); ctx.lineTo(-e * .866, e * .5); ctx.closePath(); }

  /* ── orbit particles ──────────────────────────────────────────── */
  function drawOrbitParticles(glowMul) {
    const pm = CUR.partMul;
    oParticles.forEach(p => {
      p.angle += p.sp * .012 * (0.4 + pm);
      const rr = p.ring.r * R, ys = p.ring.ys;
      const twk = Math.sin(t * 2.1 + p.ph) * .5 + .5, alpha = p.o * (.35 + twk * .65) * Math.min(1.2, pm + .2);
      for (let i = 5; i >= 0; i--) {
        const ta = p.angle - i * .09, tx = cx + Math.cos(ta) * rr, ty = cy + Math.sin(ta) * rr * ys;
        const to = alpha * (1 - i * .16), ts2 = p.sz * (1 - i * .15);
        if (to < .02 || ts2 < .3) continue;
        ctx.beginPath(); ctx.arc(tx, ty, ts2, 0, Math.PI * 2); ctx.fillStyle = C('bri', to * .55);
        if (i === 0) { ctx.shadowBlur = 9 * glowMul; ctx.shadowColor = C('bri', .85); }
        ctx.fill(); ctx.shadowBlur = 0;
      }
    });
  }

  function sparkle(x, y, sz, o, rot, glowMul) {
    if (o < .02) return;
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.globalAlpha = o;
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, sz * 5.5);
    g.addColorStop(0, C('bri', .55)); g.addColorStop(.45, C('mid', .18)); g.addColorStop(1, 'transparent');
    ctx.beginPath(); ctx.arc(0, 0, sz * 5.5, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    ctx.shadowBlur = sz * 4 * glowMul; ctx.shadowColor = C('bri', .95); ctx.fillStyle = C('hot', .98);
    ctx.beginPath();
    for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2, r = i % 2 === 0 ? sz : sz * .30; i === 0 ? ctx.moveTo(Math.cos(a) * r, Math.sin(a) * r) : ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r); }
    ctx.closePath(); ctx.fill(); ctx.shadowBlur = 0; ctx.restore();
  }

  /* ── shockwaves (click bursts) ────────────────────────────────── */
  function drawShocks(glowMul) {
    for (let i = shocks.length - 1; i >= 0; i--) {
      const s = shocks[i], age = t - s.t0, life = 0.9;
      if (age > life) { shocks.splice(i, 1); continue; }
      const f = age / life, rr = R * (1 + f * 1.8), a = (1 - f) * 0.5 * s.str;
      ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI * 2);
      ctx.strokeStyle = C('bri', a); ctx.lineWidth = (2.4 * (1 - f) + .4);
      ctx.shadowBlur = 16 * glowMul; ctx.shadowColor = C('bri', a); ctx.stroke(); ctx.shadowBlur = 0;
    }
  }

  /* ── main frame ───────────────────────────────────────────────── */
  function frame() {
   if (NX._paused) { if (!useInterval) raf = requestAnimationFrame(frame); return; }
   NX._f = (NX._f || 0) + 1;
   loopStarted = true;
   try {
    /* smooth parameter morph */
    const k = 0.06;
    CUR.hue = lerpHue(CUR.hue, target.hue, k);
    CUR.sat = lerp(CUR.sat, target.sat, k);
    CUR.scanSp = lerp(CUR.scanSp, target.scanSp, k);
    CUR.ringMul = lerp(CUR.ringMul, target.ringMul, k);
    CUR.rayInt = lerp(CUR.rayInt, target.rayInt, k);
    CUR.coreBri = lerp(CUR.coreBri, target.coreBri, k);
    CUR.pulseRate = lerp(CUR.pulseRate, target.pulseRate, k);
    CUR.pulseAmp = lerp(CUR.pulseAmp, target.pulseAmp, k);
    CUR.partMul = lerp(CUR.partMul, target.partMul, k);
    CUR.jitter = lerp(CUR.jitter, target.jitter, k);
    PAL = paletteFrom(CUR.hue, CUR.sat);

    const T = tw();
    const energy = T.energy, glowMul = T.glow, density = T.density;

    /* gaze morph */
    gazeX = lerp(gazeX, T.tracking ? gazeTX : 0, 0.08);
    gazeY = lerp(gazeY, T.tracking ? gazeTY : 0, 0.08);
    hoverT = lerp(hoverT, hover, 0.08);
    pulseBoost = lerp(pulseBoost, 0, 0.05);

    t += .0068; scanA += CUR.scanSp;

    /* breathing + state-specific modulation */
    let breath = 1 + CUR.pulseAmp * Math.sin(t * CUR.pulseRate);
    let coreBoost = CUR.coreBri * (1 + hoverT * 0.12) + pulseBoost * 0.5;
    if (NX.state === 'speaking') { breath += NX.speakLevel * 0.06; coreBoost += NX.speakLevel * 0.35; }
    if (NX.state === 'listening') { const ll = listenLevel(); breath += ll * 0.03; coreBoost += ll * 0.12; }
    coreBoost += pulseBoost * 0.4;
    R = RB * breath;

    /* jitter */
    const jit = CUR.jitter, jx = jit ? (Math.random() - .5) * jit * 6 : 0, jy = jit ? (Math.random() - .5) * jit * 6 : 0;
    cx = S / 2 + jx; cy = S / 2 + jy;

    /* gaze applied centre for "looking" group */
    const maxG = R * 0.13;
    const ex = cx + gazeX * maxG, ey = cy + gazeY * maxG;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, S, S);

    /* 1. stars */
    stars.forEach(s => { const o = s.o * (.5 + Math.sin(t * s.sp + s.ph) * .38); ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fillStyle = `rgba(185,205,235,${o})`; ctx.fill(); });

    /* 2. atmosphere halos */
    let g;
    g = ctx.createRadialGradient(cx, cy, R * .4, cx, cy, R * 4.0);
    g.addColorStop(0, C('deep', .34 * energy)); g.addColorStop(.15, C('deep', .22 * energy)); g.addColorStop(.40, C('dark', .10)); g.addColorStop(.68, C('shadow', .04)); g.addColorStop(1, 'transparent');
    ctx.beginPath(); ctx.arc(cx, cy, R * 4.0, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    g = ctx.createRadialGradient(cx, cy, R * .22, cx, cy, R * 2.6);
    g.addColorStop(0, C('mid', .54 * energy)); g.addColorStop(.20, C('mid', .36 * energy)); g.addColorStop(.50, C('deep', .15)); g.addColorStop(.78, C('dark', .05)); g.addColorStop(1, 'transparent');
    ctx.beginPath(); ctx.arc(cx, cy, R * 2.6, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    g = ctx.createRadialGradient(cx, cy, R * .06, cx, cy, R * 1.52);
    g.addColorStop(0, C('bri', .60 * energy)); g.addColorStop(.22, C('mid', .44 * energy)); g.addColorStop(.54, C('deep', .18)); g.addColorStop(1, 'transparent');
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.52, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();

    /* 3. back rings */
    drawRings(false, density, glowMul);

    /* 4. sphere body */
    const sg = ctx.createRadialGradient(cx - R * .18, cy - R * .16, R * .02, cx, cy, R);
    sg.addColorStop(0, C('dark', .55)); sg.addColorStop(.10, 'rgba(8,5,2,.96)'); sg.addColorStop(.28, 'rgba(4,6,18,.98)'); sg.addColorStop(.58, 'rgba(2,3,10,1)'); sg.addColorStop(1, 'rgba(1,1,3,1)');
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fillStyle = sg; ctx.fill();

    /* 5. iris */
    drawIris(ex, ey);

    /* 6. scan */
    drawScan(ex, ey, glowMul);

    /* 7. core glow */
    g = ctx.createRadialGradient(ex, ey, 0, ex, ey, R * .80 * Math.min(1.3, coreBoost));
    g.addColorStop(0, 'rgba(255,255,235,1)'); g.addColorStop(.05, C('hot', 1)); g.addColorStop(.14, C('bri', .98)); g.addColorStop(.28, C('mid', .88)); g.addColorStop(.48, C('deep', .50)); g.addColorStop(.70, C('dark', .20)); g.addColorStop(.88, C('shadow', .07)); g.addColorStop(1, 'transparent');
    ctx.beginPath(); ctx.arc(ex, ey, R * .80, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    g = ctx.createRadialGradient(ex, ey, 0, ex, ey, R * .20);
    g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(.18, 'rgba(255,255,235,.95)'); g.addColorStop(.46, C('hot', .60)); g.addColorStop(.80, C('mid', .22)); g.addColorStop(1, 'transparent');
    ctx.beginPath(); ctx.arc(ex, ey, R * .20, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();

    /* 8. energy rays */
    const rays = 24;
    for (let i = 0; i < rays; i++) {
      const a = i / rays * Math.PI * 2 + t * .042;
      const ln = R * (.32 + Math.sin(t * 1.38 + i * .68) * .055) * (0.7 + CUR.rayInt * 0.5);
      const al = (.28 + Math.sin(t * 1.12 + i * .48) * .12) * CUR.rayInt * energy;
      const lg = ctx.createLinearGradient(ex, ey, ex + Math.cos(a) * ln, ey + Math.sin(a) * ln);
      lg.addColorStop(0, C('bri', al)); lg.addColorStop(.40, C('mid', al * .38)); lg.addColorStop(1, 'transparent');
      ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex + Math.cos(a) * ln, ey + Math.sin(a) * ln);
      ctx.strokeStyle = lg; ctx.lineWidth = .9; ctx.stroke();
    }

    /* 9. corneal highlights (move opposite to gaze for glass feel) */
    ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();
    const hx = cx - gazeX * maxG * 0.5, hy = cy - gazeY * maxG * 0.5;
    const hl = ctx.createRadialGradient(hx - R * .38, hy - R * .35, 0, hx - R * .38, hy - R * .35, R * .40);
    hl.addColorStop(0, 'rgba(255,248,225,.55)'); hl.addColorStop(.22, 'rgba(248,232,180,.30)'); hl.addColorStop(.55, 'rgba(220,190,110,.11)'); hl.addColorStop(1, 'transparent');
    ctx.fillStyle = hl; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
    const hl2 = ctx.createRadialGradient(hx + R * .30, hy - R * .38, 0, hx + R * .30, hy - R * .38, R * .15);
    hl2.addColorStop(0, 'rgba(255,255,245,.26)'); hl2.addColorStop(.5, 'rgba(240,225,170,.11)'); hl2.addColorStop(1, 'transparent');
    ctx.fillStyle = hl2; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
    const rf = ctx.createRadialGradient(cx, cy, R * .84, cx, cy, R * .98);
    rf.addColorStop(0, 'transparent'); rf.addColorStop(.6, C('mid', .06)); rf.addColorStop(1, C('bri', .18));
    ctx.beginPath(); ctx.arc(cx, cy, R * .98, 0, Math.PI * 2); ctx.fillStyle = rf; ctx.fill();
    ctx.restore();

    /* 10. rim glow */
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.strokeStyle = C('mid', .90); ctx.lineWidth = 2.4; ctx.shadowBlur = 48 * glowMul; ctx.shadowColor = C('deep', .80); ctx.stroke(); ctx.shadowBlur = 0;

    /* 11. aperture rings */
    [.945, .910, .880].forEach((f, i) => { ctx.save(); ctx.translate(cx, cy); ctx.scale(1, .97 - i * .014); ctx.beginPath(); ctx.arc(0, 0, R * f, 0, Math.PI * 2); ctx.strokeStyle = C('deep', .10 + i * .025); ctx.lineWidth = .8 + i * .2; ctx.stroke(); ctx.restore(); });

    /* 12. front rings */
    drawRings(true, density, glowMul);

    /* 13. orbit particles */
    drawOrbitParticles(glowMul);

    /* 14. sparkle field */
    stars.slice(0, 65).forEach((s, i) => {
      const oa = s.ph + t * s.sp * .3, od = R * (1.04 + (i / 65) * .98), oys = .28 + .40 * (i / 65);
      const sx = cx + Math.cos(oa) * od, sy = cy + Math.sin(oa) * od * oys;
      sparkle(sx, sy, s.r * 2.6, s.o * (.3 + (.5 + Math.sin(t * 2.2 + s.ph) * .5) * .7) * energy, t * .32 + s.ph, glowMul);
    });

    /* 15. shockwaves */
    drawShocks(glowMul);

    /* 16. triangle emblem */
    const ts = R * .240, pu = (1 + Math.sin(t * 1.85) * .028) * (1 + pulseBoost * 0.15);
    ctx.save(); ctx.translate(ex, ey); ctx.scale(pu, pu);
    tri(ts, ts * .12); ctx.strokeStyle = C('bri', .14); ctx.lineWidth = 16; ctx.shadowBlur = 82 * glowMul; ctx.shadowColor = C('bri', .68); ctx.stroke(); ctx.shadowBlur = 0;
    tri(ts, ts * .04); ctx.strokeStyle = C('bri', .30); ctx.lineWidth = 9; ctx.shadowBlur = 44 * glowMul; ctx.shadowColor = C('bri', .84); ctx.stroke(); ctx.shadowBlur = 0;
    tri(ts); const tf = ctx.createLinearGradient(0, -ts, 0, ts * .55); tf.addColorStop(0, C('hot', .24)); tf.addColorStop(.42, C('bri', .12)); tf.addColorStop(1, C('mid', .04)); ctx.fillStyle = tf; ctx.fill();
    tri(ts); ctx.strokeStyle = C('hot', 1); ctx.lineWidth = 2.4; ctx.shadowBlur = 26 * glowMul; ctx.shadowColor = C('bri', .98); ctx.stroke(); ctx.shadowBlur = 0;
    tri(ts * .58); ctx.strokeStyle = C('bri', .74); ctx.lineWidth = 1.3; ctx.shadowBlur = 14 * glowMul; ctx.shadowColor = C('bri', .80); ctx.stroke(); ctx.shadowBlur = 0;
    tri(ts * .30); ctx.strokeStyle = C('hot', .54); ctx.lineWidth = .9; ctx.shadowBlur = 9 * glowMul; ctx.shadowColor = C('bri', .70); ctx.stroke(); ctx.shadowBlur = 0;
    ctx.beginPath(); ctx.arc(0, 0, R * .022, 0, Math.PI * 2); ctx.fillStyle = 'rgba(255,252,230,.97)'; ctx.shadowBlur = 20 * glowMul; ctx.shadowColor = C('hot', .98); ctx.fill(); ctx.shadowBlur = 0;
    ctx.restore();

   } catch(err){ window.__nxErr = (err && err.stack) || String(err); console.error('NX frame error', err); }
    if (!useInterval) raf = requestAnimationFrame(frame);
  }

  /* ── public API ───────────────────────────────────────────────── */
  NX.setState = function (name) {
    if (!STATES[name]) return;
    NX.state = name;
    target = Object.assign({}, STATES[name]);
    if (name === 'idle') {
      const a = (window.__avatarTweaks || {}).accentIdle;
      if (a) { target.hue = a.hue; target.sat = a.sat; }
    }
    window.dispatchEvent(new CustomEvent('nx-state', { detail: name }));
  };
  NX.pulse = function (str) { str = str || 1; pulseBoost = Math.min(1.4, pulseBoost + 0.8 * str); shocks.push({ t0: t, str: str }); };
  NX.setGaze = function (x, y) { gazeTX = x == null ? 0 : Math.max(-1, Math.min(1, x)); gazeTY = y == null ? 0 : Math.max(-1, Math.min(1, y)); };
  NX.setHover = function (b) { hover = b ? 1 : 0; };

  function startLoop() {
    loopStarted = false; useInterval = false;
    raf = requestAnimationFrame(function probe(){ loopStarted = true; raf = requestAnimationFrame(frame); });
    setTimeout(function(){ if (!loopStarted) { cancelAnimationFrame(raf); useInterval = true; raf = setInterval(frame, 16); } }, 200);
  }
  NX.init = function (cv) {
    canvas = cv; setup();
    let timer;
    window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(resize, 150); });
    startLoop();
  };
})();

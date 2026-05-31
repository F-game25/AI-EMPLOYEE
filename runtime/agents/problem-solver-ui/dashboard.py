"""Embedded HTML dashboard for the AI Employee problem-solver-ui server.

Extracted from server.py to keep that file manageable.
Do not edit directly — the HTML/JS is generated from the frontend build.
"""
INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AI Employee Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@300;400;500;600;700&family=Orbitron:wght@400;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root{
      --gold:#F5C400;
      --gold2:#FFCC00;
      --gold-dim:rgba(245,196,0,0.15);
      --gold-glow:rgba(245,196,0,0.35);
      --gold-border:rgba(245,196,0,0.4);
      --bg:#050508;
      --bg2:#08080d;
      --bg3:#0c0c14;
      --bg-deep:#080810;
      --panel:rgba(10,10,18,0.95);
      --panel2:rgba(14,14,24,0.92);
      --surface:rgba(10,10,18,0.95);
      --surface2:rgba(14,14,24,0.92);
      --border:rgba(245,196,0,0.12);
      --primary:#F5C400;
      --primary-dark:#B8960C;
      --primary-light:#FFDD55;
      --accent:#FFCC00;
      --accent2:#FFE566;
      --gold-light:#FFDD55;
      --gold-dark:#B8960C;
      --text:#e8e0c8;
      --text-secondary:#7a7060;
      --text-dim:#7a7060;
      --text-muted:#3a3428;
      --success:#00ff88;
      --danger:#ff3344;
      --warning:#f59e0b;
      --cyan:#00d4ff;
      --radius:4px;
      --radius-sm:2px;
      --shadow:0 8px 40px rgba(0,0,0,.98);
      --glow-primary:0 0 20px rgba(245,196,0,0.3);
      --glow-gold:0 0 20px rgba(245,196,0,0.4);
      --glow-success:0 0 20px rgba(0,255,136,0.3);
      --glow-danger:0 0 20px rgba(255,51,68,0.3);
      --sidebar-w:56px;
      --mono:'Share Tech Mono','JetBrains Mono',monospace;
      --ui:'Rajdhani',sans-serif;
      --display:'Orbitron',sans-serif;
      --sans:'Rajdhani','Inter',sans-serif;
    }
    *{box-sizing:border-box;margin:0;padding:0}
    html{scroll-behavior:smooth}
    html,body{background:var(--bg);color:var(--text);overflow-x:hidden;}
    body{font-family:var(--ui);min-height:100vh;line-height:1.6;}
    /* Animated background blobs */
    body::before,body::after{
      content:'';position:fixed;border-radius:50%;pointer-events:none;z-index:0;filter:blur(80px);
    }
    body::before{
      width:900px;height:700px;top:-200px;left:-200px;
      background:radial-gradient(circle,rgba(212,175,55,.08) 0%,transparent 65%);
      animation:blobDrift 18s ease-in-out infinite alternate;
    }
    body::after{
      width:700px;height:600px;bottom:-100px;right:-100px;
      background:radial-gradient(circle,rgba(212,175,55,.05) 0%,transparent 65%);
      animation:blobDrift2 22s ease-in-out infinite alternate;
    }
    @keyframes blobDrift{0%{transform:translate(0,0) scale(1)}50%{transform:translate(80px,50px) scale(1.1)}100%{transform:translate(-40px,80px) scale(0.95)}}
    @keyframes blobDrift2{0%{transform:translate(0,0) scale(1)}50%{transform:translate(-60px,-40px) scale(1.08)}100%{transform:translate(50px,-80px) scale(0.92)}}

    /* ── Scrollbars ── */
    ::-webkit-scrollbar{width:5px;height:5px}
    ::-webkit-scrollbar-track{background:transparent}
    ::-webkit-scrollbar-thumb{background:rgba(148,163,184,.15);border-radius:10px}
    ::-webkit-scrollbar-thumb:hover{background:rgba(212,175,55,.35)}

    /* ── Layout ── */
    .app{display:flex;flex-direction:column;min-height:100vh;position:relative;z-index:1}

    /* ── Keyframe animations ── */
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
    @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
    @keyframes slideInLeft{from{opacity:0;transform:translateX(-20px)}to{opacity:1;transform:none}}
    @keyframes slideInRight{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:none}}
    @keyframes slideInUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
    @keyframes pulseRing{0%{transform:scale(1);opacity:.8}70%{transform:scale(2);opacity:0}100%{transform:scale(2);opacity:0}}
    @keyframes gradientShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
    @keyframes shimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}
    @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
    @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
    @keyframes countUp{from{opacity:0;transform:scale(.8) translateY(6px)}to{opacity:1;transform:none}}
    @keyframes glowPulse{0%,100%{box-shadow:0 0 20px rgba(212,175,55,.15),0 0 0 rgba(212,175,55,.05)}50%{box-shadow:0 0 40px rgba(212,175,55,.25),0 0 80px rgba(212,175,55,.08)}}
    @keyframes borderGlow{0%,100%{border-color:rgba(212,175,55,.2)}50%{border-color:rgba(212,175,55,.5)}}
    @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}

    /* ── Header ── */
    header{
      background:linear-gradient(100deg,rgba(6,12,28,0.98) 0%,rgba(10,18,42,0.98) 60%,rgba(8,15,35,0.98) 100%);
      backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
      padding:14px 32px;display:flex;align-items:center;justify-content:space-between;
      border-bottom:1px solid rgba(212,175,55,.2);
      position:sticky;top:0;z-index:200;
      animation:glowPulse 8s ease infinite;
    }
    .header-left{display:flex;align-items:center;gap:14px}
    .logo{
      width:42px;height:42px;
      background:linear-gradient(135deg,#B8960C,#D4AF37);
      border-radius:12px;display:flex;align-items:center;justify-content:center;
      font-size:1.3em;border:1px solid rgba(212,175,55,.3);
      animation:float 5s ease-in-out infinite;
      box-shadow:0 0 20px rgba(212,175,55,.5),inset 0 1px 0 rgba(255,255,255,.15);
    }
    .header-title h1{
      font-size:1.18em;font-weight:700;letter-spacing:-.03em;
      background:linear-gradient(135deg,#fff 30%,var(--gold-light) 100%);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
    }
    .header-title .sub{color:rgba(148,163,184,.75);font-size:.78em;margin-top:1px;letter-spacing:.01em}
    .header-right{display:flex;align-items:center;gap:10px}
    .status-pill{display:flex;align-items:center;gap:7px;
      background:rgba(255,255,255,.05);
      border:1px solid rgba(255,255,255,.1);border-radius:20px;
      padding:5px 13px;font-size:.78em;color:rgba(240,244,255,.8);
      backdrop-filter:blur(8px);transition:all .3s}
    .status-pill:hover{background:rgba(255,255,255,.09);border-color:rgba(212,175,55,.3)}
    .status-dot{width:7px;height:7px;border-radius:50%;background:var(--success);
      box-shadow:0 0 9px var(--success);animation:blink 2.5s infinite;flex-shrink:0}
    .hdr-ctrl{display:flex;align-items:center;gap:8px}
    .hdr-btn{display:inline-flex;align-items:center;gap:5px;padding:6px 15px;border:none;
      border-radius:20px;cursor:pointer;font-size:.775em;font-weight:600;
      transition:all .2s;font-family:inherit;white-space:nowrap;position:relative;overflow:hidden;
      letter-spacing:.01em}
    .hdr-btn-start{background:rgba(212,175,55,.15);color:var(--gold);border:1px solid rgba(212,175,55,.35)}
    .hdr-btn-start:hover{background:rgba(212,175,55,.28);box-shadow:0 0 18px rgba(212,175,55,.35);transform:translateY(-1px)}
    .hdr-btn-stop{background:rgba(244,63,94,.12);color:#fb7185;border:1px solid rgba(244,63,94,.28)}
    .hdr-btn-stop:hover{background:rgba(244,63,94,.25);box-shadow:0 0 18px rgba(244,63,94,.35);transform:translateY(-1px)}
    .hdr-btn:disabled{opacity:.4;cursor:not-allowed;transform:none!important;box-shadow:none!important}

    /* ── Navigation (grouped two-tier bar) ── */
    .nav-wrapper{position:relative;display:flex;flex-direction:column;align-items:stretch}
    .nav-scroll-btn{display:none} /* hidden — no more horizontal scroll */
    /* Primary group nav */
    nav#main-nav{
      background:rgba(8,8,12,0.97);
      border-bottom:1px solid rgba(212,175,55,.18);
      padding:0 20px;display:flex;gap:2px;overflow-x:auto;
      box-shadow:0 4px 24px rgba(0,0,0,.7),0 1px 0 rgba(212,175,55,.08);
      backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
      scrollbar-width:none;position:relative;
    }
    nav#main-nav::after{
      content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(212,175,55,.3),rgba(212,175,55,.5),rgba(212,175,55,.3),transparent);
    }
    nav#main-nav::-webkit-scrollbar{display:none}
    /* Group buttons */
    .nav-group-btn{
      background:none;border:none;color:rgba(180,180,180,.6);
      padding:14px 18px 12px;cursor:pointer;font-size:.8em;font-weight:600;
      border-bottom:2px solid transparent;transition:all .25s cubic-bezier(.4,0,.2,1);
      white-space:nowrap;display:flex;align-items:center;gap:6px;
      font-family:inherit;position:relative;letter-spacing:.05em;text-transform:uppercase;
    }
    .nav-group-btn .nav-arrow{font-size:.65em;opacity:.5;transition:transform .25s,opacity .25s;margin-left:2px}
    .nav-group-btn:hover{color:rgba(212,175,55,.9);background:rgba(212,175,55,.04)}
    .nav-group-btn.active{
      color:var(--gold);border-bottom-color:var(--gold);
      background:rgba(212,175,55,.07);
      text-shadow:0 0 14px rgba(212,175,55,.5);
    }
    .nav-group-btn.active .nav-arrow{transform:rotate(180deg);opacity:.8}
    .nav-group-btn.active::after{
      content:'';position:absolute;bottom:-1px;left:20%;right:20%;height:2px;
      background:linear-gradient(90deg,transparent,var(--gold),transparent);
      filter:blur(1.5px);box-shadow:0 0 10px var(--gold);
    }
    /* Labs group special styling */
    .nav-group-btn.labs-group{
      color:var(--gold);border:1px solid rgba(212,175,55,.3)!important;
      border-bottom-color:transparent!important;
      text-shadow:0 0 12px rgba(212,175,55,.5);
      box-shadow:0 0 14px rgba(212,175,55,.15);
      margin:5px 4px;border-radius:6px;padding:9px 14px 7px;
      background:rgba(212,175,55,.05);
    }
    .nav-group-btn.labs-group:hover{background:rgba(212,175,55,.1)!important;box-shadow:0 0 20px rgba(212,175,55,.3)!important}
    .nav-group-btn.labs-group.active{
      background:rgba(212,175,55,.12)!important;border-color:rgba(212,175,55,.6)!important;
      box-shadow:0 0 20px rgba(212,175,55,.35),inset 0 0 20px rgba(212,175,55,.05)!important;
    }
    /* Sub-nav bar */
    .sub-nav{
      background:rgba(6,6,10,0.96);
      border-bottom:1px solid rgba(255,255,255,.06);
      padding:0 24px;display:none;gap:0;overflow-x:auto;
      animation:slideInDown .2s ease;
      scrollbar-width:none;
    }
    .sub-nav::-webkit-scrollbar{display:none}
    .sub-nav.active{display:flex}
    @keyframes slideInDown{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
    .sub-nav button{
      background:none;border:none;color:rgba(160,160,160,.6);
      padding:9px 14px;cursor:pointer;font-size:.775em;font-weight:500;
      border-bottom:2px solid transparent;transition:all .2s;
      white-space:nowrap;display:flex;align-items:center;gap:5px;
      font-family:inherit;position:relative;letter-spacing:.01em;
    }
    .sub-nav button:hover{color:rgba(212,175,55,.85);background:rgba(212,175,55,.04)}
    .sub-nav button:active{transform:scale(.96);transition:transform .1s}
    .sub-nav button.active{
      color:var(--gold);border-bottom-color:rgba(212,175,55,.7);
      background:rgba(212,175,55,.06);font-weight:600;
    }
    .sub-nav button.active::after{
      content:'';position:absolute;bottom:0;left:10%;right:10%;height:2px;
      background:linear-gradient(90deg,transparent,rgba(212,175,55,.8),transparent);
      filter:blur(1px);
    }
    @keyframes navBtnActivate{
      0%{transform:scale(.95)}50%{transform:scale(1.03)}100%{transform:scale(1)}
    }
    .sub-nav button.active{animation:navBtnActivate .25s cubic-bezier(.4,0,.2,1)}
    /* Legacy hidden scroll buttons */
    .nav-scroll-btn.hidden{display:none}

    /* ── Boot/Loading overlay ── */
    #boot-overlay{
      position:fixed;inset:0;z-index:9999;
      background:#000;
      display:flex;flex-direction:column;align-items:center;justify-content:center;
      font-family:var(--mono);
      overflow:hidden;
    }
    #boot-overlay.fade-out{animation:bootFadeOut 1s cubic-bezier(.4,0,.2,1) forwards}
    @keyframes bootFadeOut{
      0%{opacity:1;filter:none}
      60%{opacity:1;filter:brightness(1.2) saturate(1.5)}
      100%{opacity:0;filter:brightness(2) blur(8px);pointer-events:none}
    }
    .boot-scanline{
      position:absolute;inset:0;pointer-events:none;
      background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.18) 2px,rgba(0,0,0,.18) 4px);
      z-index:2;animation:scanMove 6s linear infinite;
    }
    @keyframes scanMove{0%{background-position:0 0}100%{background-position:0 200px}}
    .boot-glow-h{
      position:absolute;height:1px;width:100%;
      background:linear-gradient(90deg,transparent 0%,rgba(245,196,0,.05) 20%,rgba(245,196,0,.9) 50%,rgba(245,196,0,.05) 80%,transparent 100%);
      box-shadow:0 0 20px 4px rgba(245,196,0,.3);
      animation:bootScanH 2.8s ease-in-out infinite;
      z-index:3;
    }
    @keyframes bootScanH{0%{top:-2px;opacity:0}8%{opacity:1}92%{opacity:.7}100%{top:100%;opacity:0}}
    /* CRT vignette */
    #boot-overlay::before{
      content:'';position:absolute;inset:0;z-index:1;pointer-events:none;
      background:radial-gradient(ellipse at center,transparent 55%,rgba(0,0,0,.85) 100%);
    }
    /* Chromatic aberration line effect */
    #boot-overlay::after{
      content:'';position:absolute;inset:0;z-index:2;pointer-events:none;
      background:repeating-linear-gradient(0deg,transparent,transparent 1px,rgba(245,196,0,.012) 1px,rgba(245,196,0,.012) 2px);
      animation:crtFlicker 0.15s steps(1) infinite;
    }
    @keyframes crtFlicker{0%,100%{opacity:1}50%{opacity:.97}}
    .boot-corner{
      position:absolute;width:100px;height:100px;
      border:1.5px solid rgba(245,196,0,.4);
    }
    .boot-corner.tl{top:24px;left:24px;border-right:none;border-bottom:none;animation:cornerGlow 1.8s ease-in-out infinite alternate}
    .boot-corner.tr{top:24px;right:24px;border-left:none;border-bottom:none;animation:cornerGlow 1.8s ease-in-out .45s infinite alternate}
    .boot-corner.bl{bottom:24px;left:24px;border-right:none;border-top:none;animation:cornerGlow 1.8s ease-in-out .9s infinite alternate}
    .boot-corner.br{bottom:24px;right:24px;border-left:none;border-top:none;animation:cornerGlow 1.8s ease-in-out 1.35s infinite alternate}
    .boot-corner::before,.boot-corner::after{
      content:'';position:absolute;width:6px;height:1.5px;background:var(--gold);
    }
    .boot-corner.tl::before{top:-1.5px;right:-1px}
    .boot-corner.tl::after{bottom:-1px;left:-1.5px;width:1.5px;height:6px}
    @keyframes cornerGlow{0%{border-color:rgba(245,196,0,.15)}100%{border-color:rgba(245,196,0,1);box-shadow:0 0 18px rgba(245,196,0,.6),inset 0 0 8px rgba(245,196,0,.1)}}
    /* Glitch logo */
    .boot-logo{
      font-family:var(--mono);
      font-size:3em;font-weight:700;letter-spacing:.25em;text-transform:uppercase;
      color:var(--gold);
      text-shadow:0 0 20px rgba(245,196,0,.9),0 0 50px rgba(245,196,0,.5),0 0 100px rgba(245,196,0,.2);
      margin-bottom:6px;opacity:0;position:relative;z-index:5;
      animation:bootLogoReveal .7s cubic-bezier(.23,1,.32,1) .4s forwards;
    }
    @keyframes bootLogoReveal{
      0%{opacity:0;transform:scaleX(0.1) translateY(6px);letter-spacing:.02em;filter:blur(10px)}
      60%{filter:blur(2px)}
      100%{opacity:1;transform:none;letter-spacing:.25em;filter:none}
    }
    .boot-logo::before{
      content:attr(data-text);position:absolute;left:0;top:0;width:100%;height:100%;
      color:rgba(255,80,80,.7);text-shadow:none;clip-path:inset(30% 0 30% 0);
      transform:translateX(-2px);
      animation:glitchR 4s steps(1) 1.5s infinite;
    }
    .boot-logo::after{
      content:attr(data-text);position:absolute;left:0;top:0;width:100%;height:100%;
      color:rgba(80,80,255,.7);text-shadow:none;clip-path:inset(60% 0 10% 0);
      transform:translateX(2px);
      animation:glitchB 4s steps(1) 1.8s infinite;
    }
    @keyframes glitchR{0%,88%,92%,100%{opacity:0}89%{opacity:1;clip-path:inset(20% 0 40% 0);transform:translateX(-3px)}91%{clip-path:inset(55% 0 5% 0);transform:translateX(2px)}}
    @keyframes glitchB{0%,88%,92%,100%{opacity:0}89%{opacity:1;clip-path:inset(60% 0 15% 0);transform:translateX(3px)}91%{clip-path:inset(10% 0 65% 0);transform:translateX(-2px)}}
    .boot-sub{
      font-family:var(--mono);
      font-size:.68em;letter-spacing:.55em;color:rgba(245,196,0,.55);
      text-transform:uppercase;margin-bottom:36px;z-index:5;position:relative;
      opacity:0;animation:fadeIn .5s ease .95s forwards;
    }
    .boot-terminal{
      width:min(620px,92vw);height:220px;overflow:hidden;
      border:1px solid rgba(245,196,0,.18);border-radius:4px;
      background:rgba(0,0,0,.9);padding:14px 18px;
      font-size:.69em;line-height:1.8;color:rgba(245,196,0,.7);
      position:relative;z-index:5;
      box-shadow:0 0 28px rgba(245,196,0,.1),inset 0 0 40px rgba(0,0,0,.6);
    }
    .boot-terminal::before{
      content:'SYSTEM LOG';position:absolute;top:0;left:0;right:0;
      background:rgba(245,196,0,.07);border-bottom:1px solid rgba(245,196,0,.12);
      padding:3px 12px;font-size:.85em;letter-spacing:.15em;color:rgba(245,196,0,.45);
    }
    .boot-terminal-inner{padding-top:22px;height:100%;overflow:hidden}
    .boot-terminal-line{display:block;opacity:0;animation:termLine .12s ease forwards;white-space:pre;font-family:var(--mono)}
    .boot-terminal-line.cmd{color:rgba(245,196,0,.9)}
    .boot-terminal-line.ok{color:rgba(34,197,94,.85)}
    .boot-terminal-line.warn{color:rgba(251,146,60,.85)}
    .boot-terminal-line.dim{color:rgba(245,196,0,.3)}
    @keyframes termLine{to{opacity:1}}
    .boot-bar-wrap{margin-top:24px;width:min(380px,82vw);z-index:5;position:relative}
    .boot-bar-label{display:flex;justify-content:space-between;font-size:.67em;color:rgba(245,196,0,.5);margin-bottom:7px;letter-spacing:.08em;font-family:var(--mono)}
    .boot-bar-track{height:2px;background:rgba(245,196,0,.08);border-radius:0;overflow:visible;position:relative}
    .boot-bar-track::after{content:'';position:absolute;inset:-1px -1px;border:1px solid rgba(245,196,0,.12)}
    .boot-bar-fill{
      height:100%;width:0%;
      background:linear-gradient(90deg,#7A6000,#F5C400,#FFE566,#F5C400);
      background-size:200% 100%;
      box-shadow:0 0 8px 2px rgba(245,196,0,.6),0 0 24px rgba(245,196,0,.3);
      transition:width .1s linear;
      animation:barShimmer 1.5s linear infinite;
      position:relative;
    }
    .boot-bar-fill::after{
      content:'';position:absolute;right:0;top:-3px;bottom:-3px;width:3px;
      background:#fff;box-shadow:0 0 8px 4px rgba(245,196,0,.9);
      animation:barPulse .4s ease-in-out infinite alternate;
    }
    @keyframes barShimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
    @keyframes barPulse{0%{opacity:.6}100%{opacity:1}}
    /* Login screen phase */
    #boot-login{
      display:none;flex-direction:column;align-items:center;justify-content:center;
      z-index:5;position:relative;
    }
    #boot-login.visible{display:flex;animation:fadeIn .6s ease forwards}
    .boot-login-box{
      border:1px solid rgba(245,196,0,.4);border-radius:6px;
      padding:36px 48px;text-align:center;
      background:rgba(0,0,0,.7);
      box-shadow:0 0 40px rgba(245,196,0,.12),0 0 1px rgba(245,196,0,.6),inset 0 0 40px rgba(0,0,0,.8);
      backdrop-filter:blur(16px);
    }
    .boot-login-welcome{
      font-family:var(--mono);font-size:1.05em;font-weight:700;
      color:var(--gold);letter-spacing:.18em;
      text-shadow:0 0 20px rgba(245,196,0,.8);
      margin-bottom:6px;
    }
    .boot-login-sub{font-size:.7em;color:rgba(245,196,0,.45);letter-spacing:.35em;text-transform:uppercase;margin-bottom:22px}
    .boot-login-cursor{
      display:inline-block;width:10px;height:1.2em;background:var(--gold);
      vertical-align:text-bottom;margin-left:3px;
      box-shadow:0 0 10px rgba(245,196,0,.8);
      animation:blink .9s step-end infinite;
    }

    /* ── Scanline overlay on main UI ── */
    .scanlines{
      position:fixed;inset:0;z-index:998;pointer-events:none;
      background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.04) 2px,rgba(0,0,0,.04) 3px);
    }
    /* ── Particle canvas ── */
    #particles-canvas{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.45}

    /* ── Glitch animation (used on logo/title) ── */
    @keyframes glitch1{
      0%,90%,100%{clip-path:none;transform:none}
      92%{clip-path:inset(20% 0 30% 0);transform:translateX(-3px)}
      94%{clip-path:inset(60% 0 10% 0);transform:translateX(3px)}
      96%{clip-path:inset(40% 0 50% 0);transform:translateX(-2px)}
    }
    .glitch{animation:glitch1 5s infinite}

    /* ── Cyberpunk chat terminal container ── */
    #tab-chat .chat-terminal-wrap{
      display:flex;flex-direction:column;height:calc(100vh - 120px);
      background:rgba(4,4,6,0.99);
      border:1px solid rgba(245,196,0,.28);
      border-radius:4px;overflow:hidden;position:relative;
      box-shadow:0 0 40px rgba(245,196,0,.06),0 0 1px rgba(245,196,0,.5),inset 0 0 80px rgba(0,0,0,.8);
    }
    /* Corner HUD decorations */
    #tab-chat .chat-terminal-wrap::before{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent 0%,rgba(245,196,0,.6) 20%,rgba(245,196,0,.9) 50%,rgba(245,196,0,.6) 80%,transparent 100%);
      box-shadow:0 0 12px rgba(245,196,0,.4);
      z-index:5;
    }
    #tab-chat .chat-terminal-wrap::after{
      content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(245,196,0,.4),transparent);
      z-index:5;
    }
    /* Chat header HUD bar */
    .chat-hud-bar{
      display:flex;align-items:center;justify-content:space-between;
      padding:10px 18px;
      border-bottom:1px solid rgba(245,196,0,.12);
      background:rgba(6,6,10,0.98);
      flex-shrink:0;position:relative;z-index:2;
    }
    .chat-hud-bar::after{
      content:'';position:absolute;bottom:-1px;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(245,196,0,.25),transparent);
    }
    .chat-hud-title{
      font-family:var(--mono);font-size:.75em;font-weight:700;
      color:var(--gold);letter-spacing:.18em;text-transform:uppercase;
      text-shadow:0 0 10px rgba(245,196,0,.5);
      display:flex;align-items:center;gap:10px;
    }
    .chat-hud-title::before{content:'[ ';opacity:.5}
    .chat-hud-title::after{content:' ]';opacity:.5}
    .chat-hud-dot{
      width:7px;height:7px;border-radius:50%;
      background:var(--gold);
      box-shadow:0 0 8px rgba(245,196,0,.8);
      animation:blink 2s step-end infinite;
      flex-shrink:0;
    }
    .chat-hud-stats{
      display:flex;align-items:center;gap:14px;
      font-family:var(--mono);font-size:.67em;color:rgba(245,196,0,.45);
      letter-spacing:.06em;
    }
    .chat-hud-stat{display:flex;align-items:center;gap:5px}
    .chat-hud-stat-label{color:rgba(245,196,0,.3);text-transform:uppercase}
    .chat-hud-stat-val{color:rgba(245,196,0,.7)}
    /* Chat log area */
    #chat-log{
      flex:1;overflow-y:auto;padding:20px 22px;
      display:flex;flex-direction:column;gap:0;
      background:
        radial-gradient(ellipse at 20% 30%,rgba(245,196,0,.025) 0%,transparent 55%),
        radial-gradient(ellipse at 80% 70%,rgba(245,196,0,.02) 0%,transparent 55%),
        rgba(4,4,6,0.99);
      position:relative;
    }
    /* Grid background pattern */
    #chat-log::before{
      content:'';position:absolute;inset:0;pointer-events:none;z-index:0;
      background-image:
        linear-gradient(rgba(245,196,0,.025) 1px,transparent 1px),
        linear-gradient(90deg,rgba(245,196,0,.025) 1px,transparent 1px);
      background-size:40px 40px;
    }
    #chat-log > *{position:relative;z-index:1}
    /* Terminal-style input bar */
    .chat-cmd-bar{
      padding:12px 18px;
      border-top:1px solid rgba(245,196,0,.15);
      background:rgba(4,4,6,0.99);
      flex-shrink:0;position:relative;z-index:2;
    }
    .chat-cmd-row{
      display:flex;align-items:flex-end;gap:0;
      border:1px solid rgba(245,196,0,.35);
      background:rgba(2,2,4,0.98);
      position:relative;
      box-shadow:0 0 20px rgba(245,196,0,.08),0 0 1px rgba(245,196,0,.4);
    }
    .chat-cmd-row:focus-within{
      border-color:rgba(245,196,0,.7);
      box-shadow:0 0 24px rgba(245,196,0,.18),0 0 1px rgba(245,196,0,.8),inset 0 0 20px rgba(245,196,0,.03);
    }
    .chat-cmd-prompt{
      padding:11px 12px 11px 14px;
      font-family:var(--mono);font-size:.88em;
      color:rgba(245,196,0,.8);
      white-space:nowrap;flex-shrink:0;
      text-shadow:0 0 8px rgba(245,196,0,.5);
      border-right:1px solid rgba(245,196,0,.15);
      background:rgba(245,196,0,.03);
      user-select:none;
    }
    #chat-input{
      flex:1;
      background:transparent;border:none;outline:none;
      color:var(--text);padding:11px 14px;
      font-family:var(--mono);font-size:.9em;line-height:1.5;
      resize:none;caret-color:var(--gold);
      letter-spacing:.02em;
    }
    #chat-input::placeholder{color:rgba(245,196,0,.2);font-style:normal}
    .chat-send-btn{
      flex-shrink:0;padding:0 18px;
      background:rgba(245,196,0,.08);border:none;border-left:1px solid rgba(245,196,0,.2);
      color:var(--gold);font-family:var(--mono);font-size:.8em;font-weight:700;
      cursor:pointer;height:100%;min-height:44px;
      letter-spacing:.12em;text-transform:uppercase;
      transition:all .2s;
      text-shadow:0 0 8px rgba(245,196,0,.4);
    }
    .chat-send-btn:hover{
      background:rgba(245,196,0,.18);
      box-shadow:0 0 20px rgba(245,196,0,.15),inset 0 0 10px rgba(245,196,0,.05);
      color:#fff;
    }
    .chat-send-btn:active{background:rgba(245,196,0,.25)}
    .chat-cmd-hint{
      font-family:var(--mono);font-size:.63em;color:rgba(245,196,0,.25);
      margin-top:7px;letter-spacing:.06em;
      display:flex;align-items:center;justify-content:space-between;
    }
    .chat-cmd-hint-left{display:flex;align-items:center;gap:12px}
    /* Empty state */
    #chat-log .empty{
      text-align:center;margin:auto;
      font-family:var(--mono);font-size:.8em;
      color:rgba(245,196,0,.25);letter-spacing:.1em;
    }
    #chat-log .empty .icon{font-size:2em;margin-bottom:12px;filter:drop-shadow(0 0 8px rgba(245,196,0,.3))}
    /* Header system clock */
    .hdr-clock{
      font-family:var(--mono);font-size:.72em;
      color:rgba(245,196,0,.6);letter-spacing:.1em;
      padding:4px 10px;
      border:1px solid rgba(245,196,0,.15);
      border-radius:3px;
      background:rgba(245,196,0,.04);
      text-shadow:0 0 8px rgba(245,196,0,.3);
    }
    /* Enhanced header */
    header{
      background:linear-gradient(100deg,rgba(4,4,8,0.99) 0%,rgba(8,8,14,0.99) 60%,rgba(4,4,8,0.99) 100%) !important;
      border-bottom:1px solid rgba(245,196,0,.2) !important;
    }
    header::after{
      background:linear-gradient(90deg,transparent,rgba(245,196,0,.7),rgba(255,220,0,.9),rgba(245,196,0,.7),transparent) !important;
      box-shadow:0 0 16px rgba(245,196,0,.4) !important;
    }
    /* Logo enhanced */
    .logo{
      background:linear-gradient(135deg,rgba(245,196,0,.12),rgba(245,196,0,.06)) !important;
      border:1px solid rgba(245,196,0,.4) !important;
      border-radius:4px !important;
      box-shadow:0 0 16px rgba(245,196,0,.25),inset 0 0 12px rgba(245,196,0,.06) !important;
    }
    /* Enhanced nav */
    nav#main-nav{
      background:rgba(4,4,6,0.99) !important;
      border-bottom:1px solid rgba(245,196,0,.15) !important;
    }
    .nav-group-btn.active{
      text-shadow:0 0 16px rgba(245,196,0,.7) !important;
    }
    .nav-group-btn.active::after{
      background:linear-gradient(90deg,transparent,var(--gold),transparent) !important;
      box-shadow:0 0 12px rgba(245,196,0,.5) !important;
    }
    /* Chat model select dropdown dark */
    .chat-model-select-wrap select{
      background:rgba(4,4,6,.98);
      border:1px solid rgba(245,196,0,.2);
      border-radius:3px;
      color:rgba(245,196,0,.9);
      font-family:var(--mono);font-size:.8em;
      padding:5px 10px;outline:none;cursor:pointer;
    }
    .chat-model-select-wrap select:focus{border-color:rgba(245,196,0,.5)}
    /* Markdown code blocks in chat */
    .chat-msg pre,.chat-msg code{
      font-family:var(--mono);
      background:rgba(0,0,0,.6);
      border:1px solid rgba(245,196,0,.12);
      color:rgba(245,196,0,.85);
    }
    .chat-msg pre{padding:10px 14px;margin:8px 0;border-radius:2px;overflow-x:auto;
      border-left:2px solid rgba(245,196,0,.4)}
    .chat-msg code{padding:1px 5px;border-radius:2px;font-size:.9em}

    /* ── Enhanced tab content transitions ── */
    .tab-content{display:none;width:100%;box-sizing:border-box}
    .tab-content.active{
      display:block;width:100%;
      animation:tabReveal .4s cubic-bezier(.4,0,.2,1);
    }
    .tab-content.tab-leaving{
      display:block;width:100%;pointer-events:none;
      animation:tabLeave .2s cubic-bezier(.4,0,.2,1) forwards;
    }
    @keyframes tabReveal{
      0%{opacity:0;transform:translateY(14px) scale(.993)}
      60%{opacity:1;transform:translateY(-2px) scale(1.001)}
      100%{opacity:1;transform:none}
    }
    @keyframes tabLeave{
      0%{opacity:1;transform:none}
      100%{opacity:0;transform:translateY(-8px) scale(.996)}
    }

    /* ── Gold glow line under header ── */
    header::after{
      content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(212,175,55,.6),rgba(255,215,0,.8),rgba(212,175,55,.6),transparent);
      box-shadow:0 0 12px rgba(212,175,55,.4);
    }

    /* ── Main content ── */
    main{flex:1;padding:24px 28px;max-width:100%;margin:0 auto;width:100%;position:relative;z-index:1;box-sizing:border-box}
    @media(min-width:1921px){main{padding:28px 3vw}}
    @media(max-width:768px){main{padding:12px 10px}}

    /* ── Tab panels ── */

    /* ── Tab page headers ── */
    .page-header{
      display:flex;align-items:center;gap:16px;
      padding:20px 24px;margin-bottom:20px;
      background:var(--surface2);
      border:1px solid var(--border);
      border-radius:var(--radius);
      border-left-width:3px;
      position:relative;overflow:hidden;
    }
    .page-header::before{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent);
    }
    .page-header-icon{font-size:1.8rem;line-height:1;flex-shrink:0}
    .page-header-title{font-size:1.1em;font-weight:700;color:var(--text);letter-spacing:-.01em;margin-bottom:3px}
    .page-header-desc{font-size:.8em;color:var(--text-secondary);line-height:1.4}
    .page-header-badge{margin-left:auto;font-size:.7em;font-weight:700;padding:5px 12px;border-radius:20px;letter-spacing:.06em;text-transform:uppercase;border:1px solid currentColor;opacity:.85;flex-shrink:0}

    /* ── Cards ── */
    .card{
      background:var(--surface);
      border:1px solid var(--border);
      border-radius:var(--radius);padding:22px;margin-bottom:16px;
      transition:border-color .3s,box-shadow .35s,transform .3s;
      backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
      position:relative;overflow:hidden;
    }
    .card::before{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(255,255,255,.12),transparent);
    }
    .card:hover{border-color:rgba(255,255,255,.12);box-shadow:0 8px 32px rgba(0,0,0,.5),0 0 0 1px rgba(255,255,255,.04);transform:translateY(-1px)}
    .card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}
    .card-title{font-size:.92em;font-weight:600;color:var(--text);display:flex;align-items:center;gap:8px;letter-spacing:.005em}
    .card-title .icon{color:var(--primary-light)}
    .section-title{font-size:.76em;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px}

    /* ── Grid layouts ── */
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
    .grid-stat{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px;margin-bottom:16px}
    @media(max-width:1100px){.grid3{grid-template-columns:repeat(2,1fr)}}
    @media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr}}
    @media(min-width:1921px){.grid2{grid-template-columns:1fr 1fr}.grid3{grid-template-columns:repeat(3,1fr)}.grid-stat{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}}

    /* ── Stat cards ── */
    .stat-card{
      background:var(--surface2);
      border:1px solid var(--border);border-radius:var(--radius);
      padding:20px 18px;display:flex;align-items:center;gap:14px;
      transition:all .3s ease;cursor:default;position:relative;overflow:hidden;
      backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
    }
    .stat-card::before{
      content:'';position:absolute;inset:0;
      background:linear-gradient(135deg,rgba(255,255,255,.03) 0%,transparent 60%);
      pointer-events:none;
    }
    .stat-card::after{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,var(--stat-top,rgba(255,255,255,.1)),transparent);
    }
    .stat-card:hover{transform:translateY(-3px);box-shadow:0 10px 32px rgba(0,0,0,.4),0 0 0 1px rgba(212,175,55,.12);border-color:rgba(212,175,55,.25)}
    .stat-card:hover::before{opacity:1}
    .stat-icon{
      width:48px;height:48px;border-radius:14px;display:flex;align-items:center;
      justify-content:center;font-size:1.3em;flex-shrink:0;transition:transform .3s,box-shadow .3s;
      position:relative;overflow:hidden;
    }
    .stat-icon::before{content:'';position:absolute;inset:0;border-radius:inherit;
      background:linear-gradient(135deg,rgba(255,255,255,.12) 0%,transparent 50%)}
    .stat-card:hover .stat-icon{transform:scale(1.1) rotate(-5deg);box-shadow:0 0 16px var(--stat-glow,rgba(212,175,55,.4))}
    .stat-icon.green{background:linear-gradient(135deg,rgba(16,185,129,.2),rgba(52,211,153,.08));color:#34d399;--stat-glow:rgba(16,185,129,.45)}
    .stat-icon.blue{background:linear-gradient(135deg,rgba(59,130,246,.2),rgba(96,165,250,.08));color:#60a5fa;--stat-glow:rgba(59,130,246,.45)}
    .stat-icon.cyan{background:linear-gradient(135deg,rgba(212,175,55,.15),rgba(212,175,55,.05));color:var(--accent2);--stat-glow:rgba(212,175,55,.35)}
    .stat-icon.yellow{background:linear-gradient(135deg,rgba(245,158,11,.2),rgba(251,191,36,.08));color:#fbbf24;--stat-glow:rgba(245,158,11,.45)}
    .stat-icon.red{background:linear-gradient(135deg,rgba(239,68,68,.2),rgba(239,68,68,.08));color:#f87171;--stat-glow:rgba(239,68,68,.45)}
    .stat-body .val{font-size:1.8em;font-weight:800;color:var(--text);
      animation:countUp .5s ease;letter-spacing:-.04em;line-height:1}
    .stat-body .lbl{font-size:.75em;color:var(--text-muted);margin-top:6px;letter-spacing:.03em;text-transform:uppercase;font-weight:500}

    /* ── Overview hero stat cards ── */
    .ov-hero-card{
      background:var(--surface2);
      border:1px solid rgba(212,175,55,.18);
      border-radius:10px;
      padding:18px 20px;
      position:relative;overflow:hidden;
      transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;
    }
    .ov-hero-card::before{
      content:'';position:absolute;inset:0;
      background:linear-gradient(135deg,rgba(212,175,55,.04),transparent);
      pointer-events:none;
    }
    .ov-hero-card:hover{transform:translateY(-2px);border-color:rgba(212,175,55,.45);box-shadow:0 8px 32px rgba(0,0,0,.5),0 0 24px rgba(212,175,55,.1)}

    /* ── System control hero ── */
    .sys-control{
      background:linear-gradient(135deg,rgba(212,175,55,.08) 0%,rgba(212,175,55,.04) 50%,rgba(212,175,55,.02) 100%);
      border:1px solid rgba(212,175,55,.25);border-radius:var(--radius);
      padding:26px 30px;margin-bottom:16px;
      display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;
      position:relative;overflow:hidden;
      backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
      animation:borderGlow 8s ease infinite;
    }
    .sys-control::before{
      content:'';position:absolute;top:-80%;right:-5%;width:400px;height:400px;
      background:radial-gradient(circle,rgba(212,175,55,.08) 0%,transparent 65%);
      pointer-events:none;animation:float 10s ease-in-out infinite;
    }
    .sys-control::after{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(212,175,55,.4),transparent);
    }
    .sys-control-left{display:flex;align-items:center;gap:20px}
    .sys-status-ring{position:relative;width:60px;height:60px;flex-shrink:0}
    .sys-status-ring .ring-bg{
      width:60px;height:60px;border-radius:50%;
      border:2px solid rgba(212,175,55,.3);
      display:flex;align-items:center;justify-content:center;
      font-size:1.65em;
      background:linear-gradient(135deg,rgba(212,175,55,.15),rgba(212,175,55,.05));
      box-shadow:0 0 20px rgba(212,175,55,.3);
    }
    .sys-status-ring .ring-pulse{
      position:absolute;inset:-4px;border-radius:50%;
      border:2px solid var(--success);
      animation:pulseRing 2.8s ease-out infinite;
    }
    .sys-status-ring.offline .ring-pulse{border-color:var(--danger)}
    .sys-control-info h2{font-size:1.1em;font-weight:700;color:var(--text);margin-bottom:4px;letter-spacing:-.02em}
    .sys-control-info p{font-size:.83em;color:var(--text-secondary);line-height:1.5}
    .sys-control-right{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
    .btn-hero{
      display:inline-flex;align-items:center;gap:9px;padding:12px 26px;border:none;
      border-radius:11px;cursor:pointer;font-size:.9em;font-weight:600;
      transition:all .22s cubic-bezier(.4,0,.2,1);font-family:inherit;white-space:nowrap;
      position:relative;overflow:hidden;letter-spacing:.01em;
    }
    .btn-hero::before{
      content:'';position:absolute;inset:0;border-radius:inherit;
      background:linear-gradient(135deg,rgba(255,255,255,.12) 0%,transparent 50%);
      opacity:0;transition:opacity .22s;
    }
    .btn-hero:hover::before{opacity:1}
    .btn-hero::after{
      content:'';position:absolute;top:50%;left:50%;width:0;height:0;
      background:rgba(255,255,255,.18);border-radius:50%;
      transform:translate(-50%,-50%);transition:width .45s ease,height .45s ease,opacity .45s ease;
      opacity:0;
    }
    .btn-hero:active::after{width:350px;height:350px;opacity:0}
    .btn-hero-start{
      background:linear-gradient(135deg,#047857,#059669,#10b981);
      color:#fff;box-shadow:0 4px 18px rgba(16,185,129,.35),inset 0 1px 0 rgba(255,255,255,.15);
    }
    .btn-hero-start:hover{
      box-shadow:0 8px 28px rgba(16,185,129,.55),inset 0 1px 0 rgba(255,255,255,.2);
      transform:translateY(-2px);
    }
    .btn-hero-stop{
      background:linear-gradient(135deg,#9f1239,#be123c,#f43f5e);
      color:#fff;box-shadow:0 4px 18px rgba(244,63,94,.3),inset 0 1px 0 rgba(255,255,255,.12);
    }
    .btn-hero-stop:hover{
      box-shadow:0 8px 28px rgba(244,63,94,.5),inset 0 1px 0 rgba(255,255,255,.18);
      transform:translateY(-2px);
    }
    .btn-hero:disabled{opacity:.4;cursor:not-allowed;transform:none!important;box-shadow:none!important}
    .btn-hero .btn-icon{font-size:1em}

    /* ── Bot health progress bar ── */
    .health-bar-wrap{margin:10px 0 4px;position:relative}
    .health-bar-track{height:5px;background:rgba(255,255,255,.06);border-radius:10px;overflow:hidden}
    .health-bar-fill{
      height:100%;border-radius:10px;
      background:linear-gradient(90deg,#059669,#34d399);
      transition:width .9s cubic-bezier(.4,0,.2,1);
      box-shadow:0 0 10px rgba(16,185,129,.5);
      width:0%;
    }
    .health-bar-fill.warn{background:linear-gradient(90deg,#d97706,#fbbf24)}
    .health-bar-fill.danger{background:linear-gradient(90deg,#be123c,#fb7185)}
    .health-label{display:flex;justify-content:space-between;font-size:.73em;color:var(--text-muted);margin-top:4px}

    /* ── Bot rows ── */
    .bot-row{
      display:flex;align-items:center;gap:10px;padding:10px 10px;
      border-bottom:1px solid rgba(148,163,184,.06);border-radius:8px;
      transition:background .2s;animation:slideInLeft .3s ease both;
    }
    .bot-row:last-child{border-bottom:none}
    .bot-row:hover{background:rgba(212,175,55,.04)}
    .dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;transition:all .4s;position:relative}
    .dot.on{background:var(--success);box-shadow:0 0 8px rgba(16,185,129,.6)}
    .dot.on::after{
      content:'';position:absolute;inset:-3px;border-radius:50%;
      border:1.5px solid rgba(16,185,129,.4);
      animation:pulseRing 2.5s ease-out infinite;
    }
    .dot.off{background:#374151}
    .dot.unknown{background:var(--warning)}
    .bot-name{flex:1;font-size:.875em;color:var(--text)}

    /* ── Badges ── */
    .badge{display:inline-flex;align-items:center;padding:2px 9px;border-radius:20px;
      font-size:.75em;font-weight:600;letter-spacing:.01em}
    .badge.running,.badge.approved{background:rgba(16,185,129,.12);color:var(--success);border:1px solid rgba(16,185,129,.25)}
    .badge.stopped,.badge.rejected{background:rgba(239,68,68,.12);color:var(--danger);border:1px solid rgba(239,68,68,.25)}
    .badge.pending{background:rgba(245,158,11,.12);color:var(--warning);border:1px solid rgba(245,158,11,.25)}
    .badge.enabled{background:rgba(212,175,55,.12);color:var(--primary);border:1px solid rgba(212,175,55,.25)}
    .badge.disabled{background:rgba(100,116,139,.12);color:var(--text-muted);border:1px solid rgba(100,116,139,.25)}

    /* ── Buttons ── */
    .btn{
      display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border:none;
      border-radius:var(--radius-sm);cursor:pointer;font-size:.855em;font-weight:500;
      transition:all .2s cubic-bezier(.4,0,.2,1);font-family:inherit;text-decoration:none;
      white-space:nowrap;position:relative;overflow:hidden;letter-spacing:.01em;
    }
    .btn::after{
      content:'';position:absolute;top:50%;left:50%;width:0;height:0;
      background:rgba(255,255,255,.14);border-radius:50%;
      transform:translate(-50%,-50%);transition:width .4s ease,height .4s ease,opacity .4s ease;
      opacity:0;
    }
    .btn:active::after{width:250px;height:250px;opacity:0}
    .btn-primary{
      background:linear-gradient(135deg,var(--primary-dark),var(--primary));
      color:#000;font-weight:600;box-shadow:0 2px 12px rgba(212,175,55,.35);
    }
    .btn-primary:hover{transform:translateY(-1px);box-shadow:0 5px 20px rgba(212,175,55,.55),0 0 0 1px rgba(212,175,55,.2);filter:brightness(1.08)}
    .btn-danger{background:rgba(244,63,94,.12);color:#fb7185;border:1px solid rgba(244,63,94,.22)}
    .btn-danger:hover{background:rgba(244,63,94,.22);box-shadow:0 3px 12px rgba(244,63,94,.28);border-color:rgba(244,63,94,.4)}
    .btn-success{background:rgba(212,175,55,.12);color:var(--gold);border:1px solid rgba(212,175,55,.25)}
    .btn-success:hover{background:rgba(212,175,55,.24);box-shadow:0 3px 12px rgba(212,175,55,.25);border-color:rgba(212,175,55,.45)}
    .btn-ghost{background:rgba(255,255,255,.04);color:var(--text-secondary);border:1px solid rgba(148,163,184,.12)}
    .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text);border-color:rgba(212,175,55,.3)}
    .btn-sm{padding:5px 12px;font-size:.78em}
    .btn:disabled{opacity:.4;cursor:not-allowed;transform:none!important;box-shadow:none!important}

    /* ── Form controls ── */
    .form-group{margin-bottom:14px}
    label{display:block;font-size:.8em;font-weight:500;color:var(--text-secondary);margin-bottom:5px;letter-spacing:.02em}
    input,textarea,select{
      width:100%;
      background:rgba(10,10,18,0.85);
      border:1px solid rgba(148,163,184,.12);
      color:var(--text);border-radius:var(--radius-sm);padding:9px 13px;
      font-size:.875em;font-family:inherit;transition:border-color .2s,box-shadow .2s,background .2s;outline:none;
      backdrop-filter:blur(4px);
    }
    input:focus,textarea:focus,select:focus{
      border-color:rgba(212,175,55,.6);
      box-shadow:0 0 0 3px rgba(212,175,55,.12),0 0 16px rgba(212,175,55,.1);
      background:rgba(10,10,22,0.95);
    }
    input:hover:not(:focus),select:hover:not(:focus){border-color:rgba(212,175,55,.3)}
    textarea{resize:vertical;min-height:80px}
    select option{background:#08080d;color:var(--text)}

    /* ── Toggle (enhanced) ── */
    .toggle{position:relative;display:inline-block;width:44px;height:25px;flex-shrink:0}
    .toggle input{opacity:0;width:0;height:0}
    .slider{
      position:absolute;cursor:pointer;inset:0;
      background:rgba(148,163,184,.15);border-radius:25px;
      transition:.35s cubic-bezier(.4,0,.2,1);
      border:1px solid rgba(148,163,184,.1);
    }
    .slider:before{
      content:"";position:absolute;width:19px;height:19px;left:3px;top:2px;
      background:#475569;border-radius:50%;
      transition:.35s cubic-bezier(.4,0,.2,1);
      box-shadow:0 1px 4px rgba(0,0,0,.5);
    }
    input:checked+.slider{background:linear-gradient(135deg,var(--primary-dark),var(--primary));box-shadow:0 0 14px rgba(212,175,55,.5)}
    input:checked+.slider:before{transform:translateX(19px);background:#fff;box-shadow:0 1px 5px rgba(0,0,0,.4)}

    /* ── Code / pre ── */
    pre{
      background:rgba(4,8,18,.7);border:1px solid rgba(148,163,184,.1);border-radius:var(--radius-sm);
      padding:16px;overflow:auto;font-size:.8em;max-height:280px;
      white-space:pre-wrap;word-break:break-word;color:var(--text-secondary);
      font-family:'JetBrains Mono','Fira Code','Consolas',monospace;
      backdrop-filter:blur(4px);
    }
    code{background:rgba(212,175,55,.12);color:var(--primary-light);
      padding:1px 7px;border-radius:5px;font-size:.875em;font-family:monospace}

    /* ── Chat ── */
    #chat-log{
      max-height:calc(100vh - 280px);overflow-y:auto;padding:16px;
      border:1px solid rgba(148,163,184,.09);
      border-radius:16px;
      background:linear-gradient(180deg,rgba(4,8,20,.95),rgba(7,12,28,.98));
      margin-bottom:14px;
      backdrop-filter:blur(8px);
    }
    /* ── Cyberpunk Chat Messages ── */
    .chat-msg{
      padding:0;border-radius:0;margin-bottom:14px;max-width:88%;
      word-break:break-word;animation:msgReveal .28s cubic-bezier(.23,1,.32,1);
      position:relative;
    }
    @keyframes msgReveal{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
    .chat-msg-inner{
      padding:12px 16px;position:relative;
    }
    .chat-msg.user{
      margin-left:auto;
    }
    .chat-msg.user .chat-msg-inner{
      background:rgba(8,8,10,0.96);
      border:1px solid rgba(245,196,0,.5);
      border-right-width:3px;
      color:var(--text);
      font-size:.91em;line-height:1.7;
      box-shadow:0 0 20px rgba(245,196,0,.12),0 0 1px rgba(245,196,0,.6),inset 0 0 30px rgba(245,196,0,.03);
      clip-path:polygon(0 0,100% 0,100% calc(100% - 10px),calc(100% - 10px) 100%,0 100%);
    }
    .chat-msg.user .chat-msg-inner::before{
      content:'';position:absolute;left:0;top:0;bottom:0;width:2px;
      background:linear-gradient(180deg,transparent,rgba(245,196,0,.7),transparent);
    }
    .chat-msg.bot .chat-msg-inner,.chat-msg.agent .chat-msg-inner{
      background:rgba(5,5,8,0.97);
      border:1px solid rgba(245,196,0,.2);
      border-left-width:2px;
      color:var(--text);
      font-size:.91em;line-height:1.7;
      box-shadow:0 0 14px rgba(245,196,0,.06),inset 0 0 30px rgba(0,0,0,.4);
      clip-path:polygon(0 0,100% 0,100% 100%,10px 100%,0 calc(100% - 10px));
    }
    .chat-msg.bot .chat-msg-inner::before,.chat-msg.agent .chat-msg-inner::before{
      content:'';position:absolute;right:0;top:0;bottom:0;width:1px;
      background:linear-gradient(180deg,transparent,rgba(245,196,0,.3),transparent);
    }
    /* Terminal corner accent */
    .chat-msg.user .chat-msg-inner::after{
      content:'';position:absolute;bottom:0;right:0;
      width:10px;height:10px;
      border-right:2px solid rgba(245,196,0,.7);
      border-bottom:2px solid rgba(245,196,0,.7);
    }
    .chat-msg-header{
      display:flex;align-items:center;gap:8px;
      font-size:.68em;margin-bottom:8px;
      font-family:var(--mono);letter-spacing:.08em;
      color:rgba(245,196,0,.6);
    }
    .chat-msg.user .chat-msg-header{color:rgba(245,196,0,.8)}
    .chat-msg-avatar{
      width:20px;height:20px;border-radius:2px;
      display:inline-flex;align-items:center;justify-content:center;
      background:rgba(245,196,0,.08);
      border:1px solid rgba(245,196,0,.25);
      font-size:.85em;
    }
    .chat-msg-source{
      font-weight:600;letter-spacing:.08em;text-transform:uppercase;font-size:.9em;
    }
    .chat-msg-source::before{content:'// ';opacity:.45}
    .chat-msg-prompt{color:rgba(245,196,0,.35);font-size:.9em;margin-right:4px}
    .chat-model-row{display:flex;gap:10px;align-items:center;margin-bottom:10px}
    .chat-model-row select{max-width:240px}
    .chat-msg .ts{
      font-size:.65em;opacity:.45;margin-top:8px;
      font-family:var(--mono);letter-spacing:.06em;
      color:rgba(245,196,0,.4);
    }
    .chat-input-row{display:flex;gap:8px;align-items:flex-end}
    /* Typing indicator */
    .chat-typing-indicator{
      display:inline-flex;align-items:center;gap:4px;
      padding:10px 16px;font-family:var(--mono);font-size:.78em;
      color:rgba(245,196,0,.6);letter-spacing:.12em;
    }
    .chat-typing-indicator span{
      display:inline-block;width:6px;height:6px;
      background:var(--gold);border-radius:50%;
      box-shadow:0 0 6px rgba(245,196,0,.6);
      animation:typingDot .9s ease-in-out infinite;
    }
    .chat-typing-indicator span:nth-child(2){animation-delay:.15s}
    .chat-typing-indicator span:nth-child(3){animation-delay:.3s}
    @keyframes typingDot{0%,80%,100%{transform:scale(.6);opacity:.3}40%{transform:scale(1);opacity:1}}

    /* ── Live Office ── */
    .office-wrap{position:relative;overflow:hidden;border:1px solid var(--border);border-radius:16px;min-height:420px;
      background:
        linear-gradient(180deg,rgba(35,199,255,.08),rgba(9,17,31,.9) 38%),
        repeating-linear-gradient(90deg,rgba(255,255,255,.02) 0 2px,transparent 2px 120px),
        linear-gradient(0deg,#0a1220,#0a1424)}
    .office-floor{position:absolute;left:0;right:0;bottom:0;height:48%;background:linear-gradient(180deg,#121b2b,#0a0f17);
      border-top:1px solid rgba(255,255,255,.08)}
    .office-window{position:absolute;top:24px;width:160px;height:90px;border-radius:10px;border:1px solid rgba(159,232,255,.35);
      background:linear-gradient(180deg,rgba(35,199,255,.28),rgba(35,199,255,.06));box-shadow:0 0 22px rgba(35,199,255,.18)}
    .office-window::after{content:'';position:absolute;left:50%;top:0;bottom:0;width:1px;background:rgba(159,232,255,.35)}
    .office-plant{position:absolute;bottom:104px;width:22px;height:36px;background:#143027;border-radius:6px 6px 3px 3px;border:1px solid rgba(65,217,147,.3)}
    .office-plant::before{content:'';position:absolute;left:-5px;top:-22px;width:32px;height:24px;border-radius:50%;background:radial-gradient(circle,#3fdc94,#1f7f56)}
    .office-desk{position:absolute;bottom:120px;width:175px;height:15px;
      background:linear-gradient(135deg,#1a1208,#2a1e08);border-radius:9px;
      box-shadow:0 4px 12px rgba(0,0,0,.4)}
    .office-desk::after{content:'';position:absolute;left:12px;top:-18px;width:36px;height:18px;
      border-radius:5px 5px 3px 3px;background:linear-gradient(135deg,#2e1e06,#1e1004)}
    .office-agent{position:absolute;bottom:88px;width:42px;height:42px;border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      background:radial-gradient(circle at 30% 30%,#ffe8a0,#D4AF37);
      border:2px solid rgba(212,175,55,.4);cursor:pointer;
      animation:officeWalk linear infinite;
      will-change:transform;
      box-shadow:0 0 20px rgba(212,175,55,.4),0 4px 12px rgba(0,0,0,.4)}
    .office-agent.warning{box-shadow:0 0 24px rgba(244,63,94,.7);border-color:rgba(244,63,94,.9)}
    .office-agent:hover{transform:scale(1.15)!important;z-index:10}
    .office-agent .agent-emoji{font-size:18px}
    .office-agent .agent-tag{
      position:absolute;top:-24px;left:50%;transform:translateX(-50%);
      font-size:.62em;white-space:nowrap;max-width:110px;overflow:hidden;text-overflow:ellipsis;
      background:rgba(4,8,20,.92);
      padding:2px 8px;border-radius:999px;
      border:1px solid rgba(212,175,55,.25);
      box-shadow:0 0 8px rgba(212,175,55,.15);
    }
    @keyframes officeWalk{
      0%{translate:0}25%{translate:32px 0}75%{translate:-16px 0}100%{translate:0}
    }
    .office-modal{position:fixed;inset:0;background:rgba(2,4,12,.8);display:none;align-items:center;justify-content:center;z-index:4000;backdrop-filter:blur(6px)}
    .office-modal.open{display:flex;animation:fadeIn .2s ease}
    .office-modal-card{
      width:min(540px,92vw);
      background:rgba(10,10,18,0.97);
      border:1px solid rgba(212,175,55,.2);border-radius:18px;padding:22px;
      box-shadow:0 24px 64px rgba(0,0,0,.6),0 0 0 1px rgba(212,175,55,.08);
      backdrop-filter:blur(20px);
    }
    #office-modal-action{overflow-wrap:anywhere;word-break:break-word}
    .office-progress{height:8px;border-radius:999px;background:rgba(255,255,255,.06);overflow:hidden;border:1px solid rgba(148,163,184,.08)}
    .office-progress > div{height:100%;background:linear-gradient(90deg,var(--accent),var(--primary-light));width:0;transition:width .5s cubic-bezier(.4,0,.2,1)}

    /* ── Improvements ── */
    .improv-row{
      border:1px solid rgba(148,163,184,.1);border-radius:var(--radius);
      padding:16px;margin-bottom:10px;
      background:rgba(10,10,18,0.85);
      transition:border-color .25s,transform .2s,box-shadow .25s;
      backdrop-filter:blur(8px);
    }
    .improv-row:hover{border-color:rgba(212,175,55,.35);transform:translateX(4px);box-shadow:0 0 20px rgba(212,175,55,.1),-4px 0 0 rgba(212,175,55,.4)}
    .improv-row h4{color:var(--text);font-size:.9em;margin-bottom:5px;font-weight:600}
    .improv-row p{font-size:.83em;color:var(--text-secondary);margin-bottom:8px;line-height:1.55}

    /* ── Scheduler ── */
    .sched-row{
      border:1px solid rgba(148,163,184,.1);border-radius:var(--radius);
      padding:13px 16px;margin-bottom:10px;
      background:rgba(10,10,18,0.85);
      display:flex;align-items:flex-start;gap:12px;
      transition:border-color .25s,box-shadow .25s;
      backdrop-filter:blur(6px);
    }
    .sched-row:hover{border-color:rgba(212,175,55,.3);box-shadow:0 4px 16px rgba(0,0,0,.3),0 0 0 1px rgba(212,175,55,.08)}
    .sched-info{flex:1}
    .sched-info h4{color:var(--text);font-size:.875em;margin-bottom:3px;display:flex;align-items:center;gap:8px;font-weight:600}
    .sched-info p{font-size:.8em;color:var(--text-muted)}

    /* ── Skills ── */
    .skill-card{
      border:1px solid rgba(148,163,184,.1);border-radius:var(--radius);
      padding:13px;margin-bottom:8px;cursor:pointer;
      transition:all .22s;
      background:rgba(10,10,18,0.85);
      backdrop-filter:blur(6px);
    }
    .skill-card:hover{border-color:rgba(212,175,55,.4);background:rgba(212,175,55,.06);
      transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.4),0 0 0 1px rgba(212,175,55,.1)}
    .skill-card.selected{border-color:rgba(52,211,153,.5);background:rgba(16,185,129,.08);
      box-shadow:0 0 16px rgba(16,185,129,.18)}
    .skill-card h5{color:var(--text);font-size:.875em;margin-bottom:4px;font-weight:600}
    .skill-card p{font-size:.8em;color:var(--text-muted);margin:0;line-height:1.45}
    .skill-card .tags{margin-top:7px;display:flex;flex-wrap:wrap;gap:4px}
    .tag{background:rgba(212,175,55,.12);color:var(--gold-light);border-radius:5px;
      padding:2px 8px;font-size:.72em;font-weight:500;letter-spacing:.01em;border:1px solid rgba(212,175,55,.2)}
    .cat-pill{display:inline-block;padding:4px 12px;border-radius:20px;font-size:.8em;
      cursor:pointer;border:1px solid var(--border);color:var(--text-secondary);
      margin:2px;transition:all .2s;font-weight:500}
    .cat-pill:hover{border-color:var(--primary);color:var(--primary)}
    .cat-pill.active{background:var(--primary);color:#080808;border-color:var(--primary);
      box-shadow:0 2px 10px rgba(212,175,55,.35);}
    .skill-grid{max-height:500px;overflow-y:auto;padding-right:4px}
    .agent-card{
      border:1px solid rgba(148,163,184,.1);border-radius:var(--radius);
      padding:15px;margin-bottom:8px;
      background:rgba(10,10,18,0.85);transition:all .22s;
      backdrop-filter:blur(6px);
    }
    .agent-card:hover{border-color:rgba(212,175,55,.35);transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.3),0 0 0 1px rgba(212,175,55,.1)}
    .agent-card h4{color:var(--text);margin-bottom:5px;font-size:.9em;font-weight:600}
    .agent-card p{font-size:.82em;color:var(--text-muted);line-height:1.45}
    #skill-search{margin-bottom:12px}

    /* ── Toast ── */
    #toast{
      position:fixed;bottom:24px;right:24px;min-width:260px;padding:14px 20px;
      border-radius:13px;color:#fff;opacity:0;
      transition:opacity .3s cubic-bezier(.4,0,.2,1),transform .3s cubic-bezier(.4,0,.2,1);
      pointer-events:none;z-index:9999;
      font-size:.855em;font-weight:500;
      box-shadow:0 16px 48px rgba(0,0,0,.6),0 4px 16px rgba(0,0,0,.4);
      transform:translateY(16px) scale(.96);
      display:flex;align-items:center;gap:10px;
      backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
    }
    #toast.show{opacity:1;transform:translateY(0) scale(1)}
    #toast.success{background:rgba(16,67,30,.9);border:1px solid rgba(52,211,153,.25);border-left:3px solid #34d399}
    #toast.error{background:rgba(67,10,20,.9);border:1px solid rgba(244,63,94,.25);border-left:3px solid #f43f5e}
    #toast.info{background:rgba(10,10,22,.95);border:1px solid rgba(212,175,55,.25);border-left:3px solid var(--gold)}

    /* ── Empty states ── */
    .empty{text-align:center;padding:40px 16px;color:var(--text-muted)}
    .empty .icon{font-size:2.8em;margin-bottom:12px;opacity:.3;display:block}
    .empty p{font-size:.875em;line-height:1.5}

    /* ── Spinner ── */
    .spinner{display:inline-block;animation:spin .7s linear infinite}

    /* ── Divider ── */
    hr{border:none;border-top:1px solid rgba(148,163,184,.08);margin:18px 0}

    /* ── Quick actions bar ── */
    .actions-bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}

    /* ── Cmd reference ── */
    .cmd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:8px}
    .cmd-item{
      background:rgba(10,10,18,0.85);border:1px solid rgba(148,163,184,.1);border-radius:var(--radius);
      padding:11px 14px;transition:all .2s;cursor:pointer;backdrop-filter:blur(6px);
    }
    .cmd-item:hover{border-color:rgba(212,175,55,.3);background:rgba(212,175,55,.06);transform:translateY(-1px)}
    .cmd-item code{display:block;margin-bottom:4px;font-size:.8em;color:var(--primary-light)}
    .cmd-item span{font-size:.77em;color:var(--text-muted)}

    /* ── Badges ── */
    .badge{display:inline-flex;align-items:center;padding:2px 9px;border-radius:20px;
      font-size:.74em;font-weight:600;letter-spacing:.02em}
    .badge.running,.badge.approved{background:rgba(16,185,129,.12);color:#34d399;border:1px solid rgba(52,211,153,.2)}
    .badge.stopped,.badge.rejected{background:rgba(244,63,94,.12);color:#fb7185;border:1px solid rgba(244,63,94,.2)}
    .badge.pending{background:rgba(245,158,11,.12);color:#fbbf24;border:1px solid rgba(245,158,11,.2)}
    .badge.enabled{background:rgba(212,175,55,.12);color:var(--primary-light);border:1px solid rgba(212,175,55,.2)}
    .badge.disabled{background:rgba(100,116,139,.08);color:var(--text-muted);border:1px solid rgba(100,116,139,.15)}

    /* ── Dots ── */
    .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;transition:all .4s;position:relative}
    .dot.on{background:#34d399;box-shadow:0 0 9px rgba(52,211,153,.7)}
    .dot.on::after{
      content:'';position:absolute;inset:-3px;border-radius:50%;
      border:1.5px solid rgba(52,211,153,.4);
      animation:pulseRing 2.8s ease-out infinite;
    }
    .dot.off{background:rgba(100,116,139,.4)}
    .dot.unknown{background:var(--warning)}
    .bot-name{flex:1;font-size:.855em;color:var(--text);font-weight:500}

    /* ── Staggered animation delays for bot rows ── */
    .bot-row:nth-child(1){animation-delay:.02s}.bot-row:nth-child(2){animation-delay:.04s}
    .bot-row:nth-child(3){animation-delay:.06s}.bot-row:nth-child(4){animation-delay:.08s}
    .bot-row:nth-child(5){animation-delay:.1s}.bot-row:nth-child(6){animation-delay:.12s}
    .bot-row:nth-child(7){animation-delay:.14s}.bot-row:nth-child(8){animation-delay:.16s}
    .bot-row:nth-child(9){animation-delay:.18s}.bot-row:nth-child(n+10){animation-delay:.2s}

    /* ── Live Office enhanced ── */
    .office-wrap{
      position:relative;overflow:hidden;
      border:1px solid rgba(148,163,184,.1);border-radius:18px;min-height:440px;
      background:
        linear-gradient(180deg,rgba(79,70,229,.12) 0%,rgba(9,15,30,.95) 35%),
        repeating-linear-gradient(90deg,rgba(255,255,255,.018) 0 1px,transparent 1px 100px),
        repeating-linear-gradient(0deg,rgba(255,255,255,.012) 0 1px,transparent 1px 80px),
        linear-gradient(180deg,#080f1e,#070c18);
      backdrop-filter:blur(4px);
    }
    .office-floor{
      position:absolute;left:0;right:0;bottom:0;height:46%;
      background:linear-gradient(180deg,#0e1928,#08111c);
      border-top:1px solid rgba(212,175,55,.12);
    }
    .office-floor::before{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(212,175,55,.35),transparent);
    }
    .office-window{
      position:absolute;top:20px;width:150px;height:88px;border-radius:10px;
      border:1px solid rgba(212,175,55,.2);
      background:linear-gradient(180deg,rgba(212,175,55,.1),rgba(212,175,55,.03));
      box-shadow:0 0 20px rgba(212,175,55,.08),inset 0 1px 0 rgba(255,255,255,.08);
    }
    .office-window::after{content:'';position:absolute;left:50%;top:0;bottom:0;width:1px;background:rgba(212,175,55,.2)}
    .office-window::before{content:'';position:absolute;top:50%;left:0;right:0;height:1px;background:rgba(212,175,55,.15)}
    .office-plant{position:absolute;bottom:106px;width:18px;height:32px;background:linear-gradient(180deg,#0f2e1c,#0b2016);border-radius:5px 5px 2px 2px;border:1px solid rgba(52,211,153,.2)}
    .office-plant::before{content:'';position:absolute;left:-8px;top:-28px;width:34px;height:30px;border-radius:50% 50% 0 50%;background:radial-gradient(circle at 40% 40%,#34d399,#059669);box-shadow:0 0 14px rgba(52,211,153,.3)}
    .health-check-item{display:flex;align-items:center;gap:6px;padding:8px 10px;border-radius:6px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05)}
    .health-check-item .hc-dot{font-size:.65em;color:var(--text-muted)}
    .health-check-item.ok .hc-dot{color:var(--success)}
    .health-check-item.ok .hc-dot::after{content:' ✓'}
    .health-check-item.warn .hc-dot{color:var(--warning)}
    .health-check-item.warn .hc-dot::after{content:' ⚠'}
    .health-check-item.err .hc-dot{color:var(--danger)}
    .health-check-item.err .hc-dot::after{content:' ✕'}
    .health-check-item .hc-val{margin-left:auto;font-weight:600;font-size:.88em}
    .health-check-item.ok .hc-val{color:var(--success)}
    .health-check-item.warn .hc-val{color:var(--warning)}
    .health-check-item.err .hc-val{color:var(--danger)}
    .wf-metrics-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
    .wf-metric{padding:8px 10px;border-radius:6px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.05)}
    .wf-metric .k{font-size:.68em;color:var(--text-muted);letter-spacing:.02em}
    .wf-metric .v{font-size:.95em;font-family:var(--mono);font-weight:700;color:var(--gold)}
    /* System Resources card */
    .sysres-metric{background:rgba(0,0,0,.3);border:1px solid rgba(212,175,55,.14);border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:7px;transition:border-color .3s,box-shadow .3s}
    .sysres-metric:hover{border-color:rgba(212,175,55,.35);box-shadow:0 0 16px rgba(212,175,55,.07)}
    .sysres-metric-header{display:flex;justify-content:space-between;align-items:center;gap:8px}
    .sysres-metric-label{font-size:.68em;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:rgba(148,163,184,.6)}
    .sysres-metric-value{font-size:1.18em;font-weight:700;font-family:var(--mono);color:var(--gold);letter-spacing:.03em}
    .sysres-metric-sub{font-size:.69em;color:rgba(148,163,184,.5);letter-spacing:.02em}
    .sysres-temp-badge{display:inline-flex;align-items:center;gap:3px;font-size:.72em;font-family:var(--mono);padding:1px 6px;border-radius:4px;border:1px solid currentColor;opacity:.85}
    .sysres-section-divider{grid-column:1/-1;height:1px;background:linear-gradient(90deg,transparent,rgba(212,175,55,.15),transparent);margin:2px 0}
    .sysres-bar-track{height:3px;background:rgba(255,255,255,.06);border-radius:100px;overflow:hidden;margin-top:3px}
    .sysres-bar-fill{height:100%;border-radius:100px;transition:width .9s cubic-bezier(.4,0,.2,1),background .5s}
    .sysres-bar-fill.ok{background:linear-gradient(90deg,#16a34a,#4ade80)}
    .sysres-bar-fill.warn{background:linear-gradient(90deg,#d97706,#fbbf24)}
    .sysres-bar-fill.hot{background:linear-gradient(90deg,#dc2626,#f87171)}
    .sysres-na{font-size:.75em;color:var(--text-dim);font-style:italic}
    .office-desk-item{position:absolute;width:80px;height:44px;background:linear-gradient(180deg,rgba(212,175,55,.18),rgba(212,175,55,.06));border:1px solid rgba(212,175,55,.25);border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.3)}
    .robot-agent{position:absolute;cursor:pointer;transition:transform .3s;animation:robotWalk 3s ease-in-out infinite}
    .robot-agent:hover{transform:scale(1.2)!important;z-index:100}
    .robot-body{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.3em;border:2px solid var(--gold);box-shadow:0 0 16px rgba(212,175,55,.5),0 0 32px rgba(212,175,55,.15);background:var(--surface2)}
    .robot-body.busy{border-color:var(--success);box-shadow:0 0 16px rgba(34,197,94,.6),0 0 32px rgba(34,197,94,.2);animation:robotBusy .8s ease-in-out infinite}
    .robot-body.alert{border-color:#ef4444;box-shadow:0 0 20px rgba(239,68,68,.8),0 0 40px rgba(239,68,68,.3);animation:robotAlert .6s ease-in-out infinite}
    .robot-alert-badge{position:absolute;top:-6px;right:-6px;width:16px;height:16px;background:#ef4444;border-radius:50%;border:2px solid var(--surface2);display:flex;align-items:center;justify-content:center;font-size:.55em;animation:blink .6s infinite;z-index:10}
    .robot-name{font-size:.6em;color:var(--gold-light);text-align:center;margin-top:3px;white-space:nowrap;max-width:70px;overflow:hidden;text-overflow:ellipsis;font-weight:600}
    .robot-name.alert{color:#f87171}
    .robot-status-dot{width:8px;height:8px;border-radius:50%;margin:2px auto;background:var(--text-muted)}
    .robot-status-dot.running{background:var(--success);box-shadow:0 0 8px var(--success);animation:blink 1.5s infinite}
    .robot-status-dot.busy{background:var(--gold);box-shadow:0 0 8px var(--gold);animation:blink .8s infinite}
    .robot-status-dot.alert{background:#ef4444;box-shadow:0 0 8px #ef4444;animation:blink .5s infinite}
    @keyframes robotWalk{0%,100%{transform:translateY(0) rotate(-1deg)}25%{transform:translateY(-5px) rotate(1.5deg)}50%{transform:translateY(-2px) rotate(0deg)}75%{transform:translateY(-6px) rotate(-1.5deg)}}
    @keyframes robotBusy{0%,100%{box-shadow:0 0 8px rgba(34,197,94,.4),0 4px 12px rgba(0,0,0,.3)}50%{box-shadow:0 0 24px rgba(34,197,94,.9),0 4px 20px rgba(34,197,94,.3)}}
    @keyframes robotAlert{0%,100%{box-shadow:0 0 8px rgba(239,68,68,.5),0 4px 12px rgba(0,0,0,.3)}50%{box-shadow:0 0 28px rgba(239,68,68,1),0 4px 20px rgba(239,68,68,.4)}}
    @keyframes robotWalk2{0%,100%{transform:translateY(0) rotate(1deg)}25%{transform:translateY(-3px) rotate(-1deg)}50%{transform:translateY(-5px) rotate(0deg)}75%{transform:translateY(-2px) rotate(1deg)}}

    /* ── Agent picker grid (Task tab) ── */
    .agent-pick-item{
      display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;
      border:1px solid rgba(148,163,184,.1);cursor:pointer;
      background:rgba(10,10,18,0.75);transition:all .2s;font-size:.82em;
    }
    .agent-pick-item:hover{border-color:rgba(212,175,55,.3);background:rgba(212,175,55,.06)}
    .agent-pick-item.selected{border-color:rgba(212,175,55,.5);background:rgba(212,175,55,.1);box-shadow:0 0 12px rgba(212,175,55,.12)}
    .agent-pick-item .pick-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
    .agent-pick-item .pick-dot.on{background:var(--success);box-shadow:0 0 6px var(--success)}
    .agent-pick-item .pick-dot.off{background:rgba(100,116,139,.4)}

    /* ══ APP STATE MACHINE ══ */
    .app{opacity:0;pointer-events:none;transition:opacity .6s ease}
    body.state-dashboard .app{opacity:1;pointer-events:auto}

    /* ══ SCREEN TRANSITIONS (glitch + fade-scale) ══ */
    @keyframes screenGlitch{
      0%{clip-path:inset(0 0 100% 0);transform:skewX(-2deg) scale(1.01)}
      20%{clip-path:inset(0 0 70% 0);transform:skewX(1deg)}
      40%{clip-path:inset(30% 0 40% 0);transform:skewX(-1deg) scale(.99)}
      60%{clip-path:inset(0 0 20% 0);transform:skewX(.5deg)}
      80%{clip-path:inset(0 0 5% 0);transform:skewX(0)}
      100%{clip-path:inset(0 0 0 0);transform:none}
    }
    @keyframes fadeScale{from{opacity:0;transform:scale(.97) translateY(6px)}to{opacity:1;transform:none}}
    .glitch-in{animation:screenGlitch .45s steps(4,end) forwards,fadeScale .55s ease forwards}

    /* ══ LOGIN SCREEN ══ */
    #login-screen{
      display:none;position:fixed;inset:0;z-index:9000;
      background:radial-gradient(ellipse at 60% 40%,rgba(212,175,55,.06) 0%,transparent 70%),
                 radial-gradient(ellipse at 20% 80%,rgba(212,175,55,.04) 0%,transparent 60%),
                 #050505;
      align-items:center;justify-content:center;flex-direction:column;
      font-family:'Space Grotesk',monospace;
    }
    #login-screen.visible{display:flex}
    #login-screen.leaving{animation:bootFadeOut .5s ease forwards}
    .login-box{
      width:min(420px,92vw);
      border:1px solid rgba(212,175,55,.3);
      border-radius:6px;
      background:rgba(8,8,8,.97);
      box-shadow:0 0 60px rgba(212,175,55,.12),0 0 120px rgba(212,175,55,.04),inset 0 1px 0 rgba(212,175,55,.1);
      padding:40px 36px 36px;
      animation:fadeScale .6s ease both;
    }
    .login-corner{position:absolute;width:16px;height:16px;border-color:rgba(212,175,55,.6);border-style:solid}
    .login-corner.tl{top:-1px;left:-1px;border-width:2px 0 0 2px;border-radius:4px 0 0 0}
    .login-corner.tr{top:-1px;right:-1px;border-width:2px 2px 0 0;border-radius:0 4px 0 0}
    .login-corner.bl{bottom:-1px;left:-1px;border-width:0 0 2px 2px;border-radius:0 0 0 4px}
    .login-corner.br{bottom:-1px;right:-1px;border-width:0 2px 2px 0;border-radius:0 0 4px 0}
    .login-logo{
      font-size:1.6em;font-weight:700;letter-spacing:.2em;text-transform:uppercase;
      color:#F5C400;text-shadow:0 0 20px rgba(245,196,0,.5),0 0 40px rgba(245,196,0,.2);
      text-align:center;margin-bottom:4px;
    }
    .login-sub{text-align:center;color:rgba(212,175,55,.45);font-size:.7em;letter-spacing:.15em;text-transform:uppercase;margin-bottom:32px}
    .login-label{display:block;font-size:.7em;letter-spacing:.12em;text-transform:uppercase;color:rgba(212,175,55,.5);margin-bottom:6px;margin-top:20px}
    .login-input{
      width:100%;background:rgba(255,255,255,.03);border:1px solid rgba(212,175,55,.25);border-radius:4px;
      color:#e5e5e5;font-family:monospace;font-size:.9em;padding:10px 14px;box-sizing:border-box;outline:none;
      transition:border-color .2s,box-shadow .2s;
    }
    .login-input:focus{border-color:rgba(212,175,55,.6);box-shadow:0 0 12px rgba(212,175,55,.15)}
    .login-btn{
      width:100%;margin-top:28px;padding:12px;background:linear-gradient(90deg,#B8960C,#D4AF37,#B8960C);
      background-size:200% auto;border:none;border-radius:4px;color:#050505;font-weight:700;font-size:.85em;
      letter-spacing:.12em;text-transform:uppercase;cursor:pointer;
      box-shadow:0 0 24px rgba(212,175,55,.3);transition:background-position .4s,box-shadow .3s,transform .15s;
    }
    .login-btn:hover{background-position:right center;box-shadow:0 0 40px rgba(212,175,55,.5);transform:translateY(-1px)}
    .login-btn:active{transform:translateY(0)}
    .login-status{text-align:center;font-size:.72em;margin-top:16px;color:rgba(212,175,55,.45);font-family:monospace;min-height:18px}
    #login-cursor{display:inline-block;animation:blink .7s infinite}
    .login-scanline{position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.03) 2px,rgba(0,0,0,.03) 4px);border-radius:6px}

    /* ══ OFFLINE SCREEN ══ */
    #offline-screen{
      display:none;position:fixed;inset:0;z-index:9100;background:#050505;
      align-items:center;justify-content:center;flex-direction:column;font-family:monospace;
    }
    #offline-screen.visible{display:flex}
    .offline-box{
      border:1px solid rgba(239,68,68,.4);border-radius:6px;background:rgba(8,0,0,.98);
      padding:40px 48px;max-width:500px;width:90%;text-align:center;
      box-shadow:0 0 60px rgba(239,68,68,.15);animation:fadeScale .5s ease both;
    }
    .offline-title{font-size:1.4em;color:#ef4444;letter-spacing:.15em;text-shadow:0 0 20px rgba(239,68,68,.6);margin-bottom:8px}
    .offline-msg{color:rgba(239,68,68,.7);font-size:.8em;line-height:1.6;margin:16px 0}
    .offline-retry{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.4);border-radius:4px;color:#ef4444;padding:10px 28px;cursor:pointer;font-family:monospace;font-size:.85em;letter-spacing:.1em;margin-top:8px;transition:background .2s,box-shadow .2s}
    .offline-retry:hover{background:rgba(239,68,68,.25);box-shadow:0 0 16px rgba(239,68,68,.3)}

    /* ══ CYBER DASHBOARD PANEL ══ */
    #cyber-panel{display:grid;grid-template-columns:1fr 1.5fr 1fr;gap:14px;height:520px;margin-bottom:20px}
    @media(max-width:1100px){#cyber-panel{grid-template-columns:1fr;height:auto}}
    .cyber-col{
      border:1px solid rgba(212,175,55,.25);border-radius:10px;
      background:linear-gradient(135deg,rgba(10,8,5,.98),rgba(18,14,7,.95));
      box-shadow:0 0 30px rgba(212,175,55,.06),inset 0 0 40px rgba(212,175,55,.02);
      display:flex;flex-direction:column;overflow:hidden;
      transition:box-shadow .3s ease,border-color .3s ease;
    }
    .cyber-col:hover{border-color:rgba(212,175,55,.4);box-shadow:0 0 40px rgba(212,175,55,.1),inset 0 0 40px rgba(212,175,55,.03)}
    .cyber-col-header{
      padding:10px 14px;border-bottom:1px solid rgba(212,175,55,.15);
      font-size:.72em;letter-spacing:.12em;text-transform:uppercase;color:rgba(212,175,55,.6);
      display:flex;align-items:center;gap:8px;flex-shrink:0;
      background:rgba(212,175,55,.03);
    }
    .cyber-col-header .hdr-dot{width:6px;height:6px;border-radius:50%;background:#D4AF37;box-shadow:0 0 6px #D4AF37;animation:blink 1.4s infinite}
    /* ─ Doctor Panel ─ */
    #doctor-panel{background:var(--surface2);border:1px solid rgba(212,175,55,.22);border-radius:var(--radius);padding:16px;margin-bottom:18px}
    #doctor-panel .dp-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
    #doctor-panel .dp-title{font-size:.82em;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);font-family:var(--mono);display:flex;align-items:center;gap:8px}
    #doctor-panel .dp-title .hdr-dot{width:6px;height:6px;border-radius:50%;background:#D4AF37;box-shadow:0 0 6px #D4AF37;animation:blink 1.4s infinite;flex-shrink:0}
    .dp-item{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-radius:8px;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.06);margin-bottom:8px;transition:border-color .2s}
    .dp-item:last-child{margin-bottom:0}
    .dp-item.dp-ok{border-left:3px solid var(--success,#10b981)}
    .dp-item.dp-warn{border-left:3px solid #f59e0b}
    .dp-item.dp-error{border-left:3px solid var(--danger,#ef4444)}
    .dp-item.dp-approved{opacity:.55}
    .dp-item.dp-rejected{opacity:.45;text-decoration:line-through}
    .dp-icon{font-size:1.1em;flex-shrink:0;margin-top:1px}
    .dp-body{flex:1;min-width:0}
    .dp-item-title{font-size:.82em;font-weight:600;color:var(--text);margin-bottom:2px}
    .dp-item-desc{font-size:.74em;color:var(--text-muted);line-height:1.45}
    .dp-actions{display:flex;gap:5px;margin-top:6px;flex-wrap:wrap}
    .dp-btn{font-size:.7em;padding:3px 9px;border-radius:5px;border:1px solid;cursor:pointer;font-family:var(--mono);font-weight:600;letter-spacing:.04em;transition:all .15s;background:transparent}
    .dp-btn-approve{color:#10b981;border-color:rgba(16,185,129,.4)}
    .dp-btn-approve:hover{background:rgba(16,185,129,.15);border-color:#10b981}
    .dp-btn-reject{color:#f87171;border-color:rgba(239,68,68,.4)}
    .dp-btn-reject:hover{background:rgba(239,68,68,.12);border-color:#ef4444}
    .dp-empty{font-size:.8em;color:var(--text-muted);text-align:center;padding:14px 0}
    /* ─ Heartbeat col ─ */
    #heartbeat-log{flex:1;overflow-y:auto;padding:10px 12px;font-family:monospace;font-size:.72em;line-height:1.7}
    #heartbeat-log::-webkit-scrollbar{width:3px}
    #heartbeat-log::-webkit-scrollbar-thumb{background:rgba(212,175,55,.2)}
    .hb-line{color:rgba(180,180,180,.75);animation:fadeIn .2s ease both}
    .hb-line .hb-tag{color:#D4AF37}
    .hb-line .hb-orch{color:#F5C400;text-shadow:0 0 8px rgba(245,196,0,.4)}
    .hb-line .hb-ts{color:rgba(212,175,55,.3);margin-right:6px}
    /* ─ Chat col ─ */
    #cyber-chat-messages{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
    #cyber-chat-messages::-webkit-scrollbar{width:3px}
    #cyber-chat-messages::-webkit-scrollbar-thumb{background:rgba(212,175,55,.2)}
    .msg-bubble{max-width:82%;padding:9px 13px;border-radius:8px;font-size:.82em;line-height:1.5;word-break:break-word}
    .msg-user{align-self:flex-end;background:rgba(212,175,55,.12);border:1px solid rgba(212,175,55,.25);color:#e5e5e5}
    .msg-ai{align-self:flex-start;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);color:#ccc}
    .msg-ai .msg-sender{font-size:.7em;color:rgba(212,175,55,.5);margin-bottom:3px;font-family:monospace;letter-spacing:.05em}
    .msg-typing{color:rgba(212,175,55,.5);font-family:monospace;font-size:.8em;padding:6px 12px}
    .chat-input-row{padding:10px;border-top:1px solid rgba(212,175,55,.12);display:flex;gap:8px;flex-shrink:0}
    #cyber-chat-input{
      flex:1;background:rgba(255,255,255,.03);border:1px solid rgba(212,175,55,.2);border-radius:4px;
      color:#e5e5e5;font-family:monospace;font-size:.82em;padding:8px 12px;outline:none;
      transition:border-color .2s;
    }
    #cyber-chat-input:focus{border-color:rgba(212,175,55,.5)}
    #cyber-chat-send{
      background:rgba(212,175,55,.15);border:1px solid rgba(212,175,55,.3);border-radius:4px;
      color:#D4AF37;padding:8px 16px;cursor:pointer;font-family:monospace;font-size:.8em;
      transition:background .2s,box-shadow .2s;
    }
    #cyber-chat-send:hover{background:rgba(212,175,55,.25);box-shadow:0 0 12px rgba(212,175,55,.2)}
    /* ─ Stats col ─ */
    #stats-col{flex:1;overflow-y:auto;padding:12px}
    .stat-ring-wrap{display:flex;flex-direction:column;align-items:center;padding:14px 0 10px;border-bottom:1px solid rgba(212,175,55,.08);margin-bottom:12px}
    .stat-ring-svg{width:90px;height:90px}
    .stat-ring-label{font-size:.68em;letter-spacing:.1em;text-transform:uppercase;color:rgba(212,175,55,.45);margin-top:6px}
    .stat-ring-val{font-size:.9em;color:#D4AF37;font-family:monospace;margin-top:2px}
    .stat-item{display:flex;justify-content:space-between;align-items:center;padding:7px 4px;border-bottom:1px solid rgba(255,255,255,.04);font-size:.78em}
    .stat-item .si-label{color:rgba(180,180,180,.6)}
    .stat-item .si-val{color:#D4AF37;font-family:monospace;font-size:.9em}
    .stat-item .si-bar{height:3px;background:rgba(212,175,55,.12);border-radius:3px;margin-top:4px;overflow:hidden}
    .stat-item .si-bar-fill{height:100%;background:linear-gradient(90deg,#B8960C,#D4AF37);border-radius:3px;transition:width 1s ease}
    .topbar-time{font-family:monospace;font-size:.8em;color:rgba(212,175,55,.6);letter-spacing:.08em}

    /* ======== CYBERPUNK REFERENCE CSS ======== */

    /* ── SCANLINES ── */
    body::after{
      content:'';position:fixed;inset:0;pointer-events:none;z-index:9999;
      background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.03) 2px,rgba(0,0,0,0.03) 4px);
    }

    /* ── BOOT SCREEN ── */
    #boot{
      position:fixed;inset:0;background:#000;z-index:10000;
      display:flex;flex-direction:column;align-items:center;justify-content:center;
      font-family:var(--mono);
    }
    #boot-log{
      position:absolute;top:0;left:0;right:0;
      font-size:11px;color:rgba(245,196,0,0.5);
      padding:20px;line-height:1.8;overflow:hidden;height:100%;
    }
    #boot-center{
      position:relative;z-index:2;text-align:center;
      opacity:0;transform:scale(0.8);
      transition:opacity 0.8s ease, transform 0.8s ease;
    }
    #boot-center.show{opacity:1;transform:scale(1)}
    .boot-box{
      border:1px solid var(--gold-border);
      padding:40px 80px;
      position:relative;
      background:rgba(0,0,0,0.8);
    }
    .boot-box::before,.boot-box::after{
      content:'';position:absolute;width:20px;height:20px;border-color:var(--gold);border-style:solid;
    }
    .boot-box::before{top:-1px;left:-1px;border-width:2px 0 0 2px}
    .boot-box::after{bottom:-1px;right:-1px;border-width:0 2px 2px 0}
    .boot-logo{
      font-family:var(--display);font-size:2.8em;font-weight:900;
      color:var(--gold);letter-spacing:.2em;
      text-shadow:0 0 40px var(--gold-glow),0 0 80px rgba(245,196,0,0.15);
    }
    .boot-sub{
      font-family:var(--ui);font-size:.9em;color:var(--text-dim);
      letter-spacing:.4em;margin-top:8px;text-transform:uppercase;
    }
    .boot-status{
      margin-top:24px;font-size:.75em;color:var(--gold);
      letter-spacing:.1em;
    }
    .boot-bar{
      width:100%;height:2px;background:rgba(245,196,0,0.1);
      margin-top:12px;position:relative;overflow:hidden;
    }
    .boot-bar-fill{
      height:100%;width:0%;background:var(--gold);
      box-shadow:0 0 12px var(--gold-glow);
      transition:width 0.05s linear;
    }

    /* ── LOGIN PANEL (cyberpunk reference, used in #login) ── */
    #login{
      position:fixed;inset:0;background:var(--bg);z-index:9999;
      display:none;align-items:center;justify-content:center;
      font-family:var(--ui);flex-direction:column;gap:24px;
    }
    .login-panel{
      border:1px solid var(--gold-border);
      padding:48px 56px;min-width:420px;
      background:var(--panel);
      position:relative;
      animation:panelIn 0.5s ease;
    }
    @keyframes panelIn{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}
    .login-panel::before{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,var(--gold),transparent);
    }
    .login-welcome{
      font-family:var(--display);font-size:1.1em;color:var(--gold);
      letter-spacing:.15em;margin-bottom:4px;
    }
    .login-name{font-size:1.8em;font-weight:700;color:var(--text);margin-bottom:32px}
    .login-field{
      width:100%;background:rgba(245,196,0,0.04);
      border:1px solid var(--gold-border);
      color:var(--text);padding:12px 16px;
      font-family:var(--mono);font-size:.9em;
      outline:none;margin-bottom:12px;display:block;
      transition:border-color .2s,box-shadow .2s;
    }
    .login-field:focus{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold-glow),inset 0 0 20px rgba(245,196,0,0.03)}

    /* ── VIRTUAL KEYBOARD ── */
    .vkb{
      position:fixed;bottom:0;left:50%;transform:translateX(-50%) translateY(100%);
      background:rgba(5,5,10,0.97);border-top:1px solid var(--gold-border);
      padding:16px 20px;z-index:9998;width:700px;
      transition:transform .4s cubic-bezier(.4,0,.2,1);
    }
    .vkb.show{transform:translateX(-50%) translateY(0)}
    .vkb-row{display:flex;gap:4px;justify-content:center;margin-bottom:4px}
    .vkb-key{
      padding:8px 12px;min-width:36px;
      background:rgba(245,196,0,0.05);border:1px solid rgba(245,196,0,0.2);
      color:var(--gold);font-family:var(--mono);font-size:.78em;
      cursor:pointer;text-align:center;
      transition:background .1s,box-shadow .1s;
      user-select:none;
    }
    .vkb-key:hover{background:rgba(245,196,0,0.12);box-shadow:0 0 8px rgba(245,196,0,0.2)}
    .vkb-key:active{background:rgba(245,196,0,0.2)}
    .vkb-key.wide{min-width:80px}.vkb-key.wider{min-width:200px}

    /* ── TOPBAR (for indicators in header) ── */
    .tb-indicator{display:flex;align-items:center;gap:5px;font-family:var(--mono);font-size:.7em;color:var(--text-dim)}
    .tb-dot{width:6px;height:6px;border-radius:50%;background:var(--success);box-shadow:0 0 6px var(--success);animation:cpBlink 2s infinite}
    @keyframes cpBlink{0%,100%{opacity:1}50%{opacity:.3}}
    .tb-clock{font-family:var(--display);font-size:.8em;color:var(--gold);letter-spacing:.1em}

    /* ── SIDEBAR (inside chat tab) ── */
    .sidebar{
      width:56px;background:rgba(5,5,8,0.98);
      border-right:1px solid rgba(245,196,0,0.1);
      display:flex;flex-direction:column;align-items:center;
      padding:16px 0;gap:6px;flex-shrink:0;
    }
    .sb-icon{
      width:40px;height:40px;display:flex;align-items:center;justify-content:center;
      cursor:pointer;position:relative;
      color:var(--text-dim);font-size:16px;
      transition:color .2s;border:1px solid transparent;
      font-family:var(--mono);
    }
    .sb-icon:hover{color:var(--gold);border-color:rgba(245,196,0,0.2);background:rgba(245,196,0,0.04)}
    .sb-icon.active{color:var(--gold);border-color:rgba(245,196,0,0.3);background:rgba(245,196,0,0.07)}
    .sb-icon.active::before{
      content:'';position:absolute;left:-1px;top:25%;bottom:25%;width:2px;
      background:var(--gold);box-shadow:0 0 8px var(--gold-glow);
    }
    .sb-divider{width:24px;height:1px;background:rgba(245,196,0,0.1);margin:4px 0}

    /* ── CHAT PANEL ── */
    .chat-panel{flex:1;display:flex;flex-direction:column;overflow:hidden;position:relative}

    /* ── CHAT HEADER ── */
    .chat-header{
      padding:14px 24px;
      border-bottom:1px solid rgba(245,196,0,0.1);
      background:rgba(8,8,14,0.95);
      display:flex;align-items:center;justify-content:space-between;
      flex-shrink:0;
    }
    .ch-left{display:flex;align-items:center;gap:14px}
    .ch-icon{
      width:38px;height:38px;border:1px solid var(--gold-border);
      display:flex;align-items:center;justify-content:center;
      font-family:var(--display);font-size:.8em;color:var(--gold);
      position:relative;
      background:rgba(245,196,0,0.04);
    }
    .ch-icon::before,.ch-icon::after{
      content:'';position:absolute;width:8px;height:8px;
      border-color:var(--gold);border-style:solid;
    }
    .ch-icon::before{top:-1px;left:-1px;border-width:1px 0 0 1px}
    .ch-icon::after{bottom:-1px;right:-1px;border-width:0 1px 1px 0}
    .ch-title{font-family:var(--display);font-size:.88em;font-weight:700;color:var(--text);letter-spacing:.08em}
    .ch-sub{font-family:var(--mono);font-size:.68em;color:var(--text-dim);margin-top:2px}
    .ch-right{display:flex;align-items:center;gap:10px}
    .ch-badge{
      font-family:var(--mono);font-size:.7em;padding:4px 10px;
      border:1px solid rgba(245,196,0,0.25);color:var(--gold);
      background:rgba(245,196,0,0.06);
    }
    .ch-ctrl{
      font-family:var(--mono);font-size:.7em;padding:4px 10px;
      border:1px solid rgba(245,196,0,0.2);color:var(--text-dim);
      background:transparent;cursor:pointer;
      transition:all .15s;
    }
    .ch-ctrl:hover{color:var(--gold);border-color:rgba(245,196,0,0.4);background:rgba(245,196,0,0.05)}

    /* ── MODEL SELECT ── */
    .model-select{
      background:rgba(245,196,0,0.04);border:1px solid rgba(245,196,0,0.2);
      color:var(--gold);font-family:var(--mono);font-size:.72em;
      padding:4px 8px;outline:none;cursor:pointer;
    }
    .model-select option{background:#08080d;color:var(--text)}

    /* ── CHAT LOG (override for new chat tab) ── */
    #tab-chat #chat-log{
      flex:1;overflow-y:auto;padding:24px;
      display:flex;flex-direction:column;gap:16px;
      background:unset;
      scrollbar-width:thin;scrollbar-color:rgba(245,196,0,0.2) transparent;
    }
    #tab-chat #chat-log::-webkit-scrollbar{width:3px}
    #tab-chat #chat-log::-webkit-scrollbar-track{background:transparent}
    #tab-chat #chat-log::-webkit-scrollbar-thumb{background:rgba(245,196,0,0.2);border-radius:2px}
    #tab-chat #chat-log::before{display:none}

    /* ── MESSAGES ── */
    .msg-wrap{display:flex;flex-direction:column;animation:msgIn .25s ease}
    @keyframes msgIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
    .msg-wrap.user{align-items:flex-end}
    .msg-wrap.agent{align-items:flex-start}

    .msg-meta{
      font-family:var(--mono);font-size:.65em;color:var(--text-dim);
      margin-bottom:5px;display:flex;align-items:center;gap:8px;
    }
    .msg-wrap.user .msg-meta{flex-direction:row-reverse}

    .msg-avatar{
      width:20px;height:20px;border:1px solid var(--gold-border);
      display:flex;align-items:center;justify-content:center;
      font-size:10px;color:var(--gold);background:rgba(245,196,0,0.06);
    }
    .msg-source{color:var(--gold);letter-spacing:.05em}
    .msg-ts{color:var(--text-muted)}

    .msg-wrap.user .msg-bubble{
      background:rgba(245,196,0,0.07);
      border:1px solid rgba(245,196,0,0.3);
      border-radius:2px 2px 2px 12px;
      color:var(--text);
    }
    .msg-wrap.user .msg-bubble::before{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(245,196,0,0.5),transparent);
    }
    .msg-wrap.user .msg-bubble::after{
      content:'';position:absolute;right:-1px;top:10px;
      width:3px;height:60%;max-height:40px;
      background:var(--gold);box-shadow:0 0 8px var(--gold-glow);
    }

    .msg-wrap.agent .msg-bubble{
      background:rgba(10,10,20,0.9);
      border:1px solid rgba(245,196,0,0.15);
      border-radius:2px 12px 12px 2px;
      color:var(--text);
    }
    .msg-wrap.agent .msg-bubble::before{
      content:'';position:absolute;left:-1px;top:10px;
      width:3px;height:60%;max-height:40px;
      background:rgba(245,196,0,0.4);
    }

    .msg-bubble strong{color:var(--gold);font-weight:600}
    .msg-bubble em{color:rgba(245,196,0,0.7);font-style:italic}
    .msg-bubble code{
      font-family:var(--mono);font-size:.85em;
      background:rgba(245,196,0,0.08);border:1px solid rgba(245,196,0,0.15);
      padding:1px 6px;color:var(--gold);
    }

    /* THINKING bubble */
    .msg-thinking{
      display:flex;align-items:center;gap:10px;
      font-family:var(--mono);font-size:.78em;color:var(--text-dim);
      padding:10px 16px;border:1px solid rgba(245,196,0,0.12);
      background:rgba(8,8,14,0.8);border-radius:2px;
      max-width:220px;
    }
    .think-dots{display:flex;gap:4px}
    .think-dot{
      width:5px;height:5px;border-radius:50%;
      background:var(--gold);opacity:.3;
      animation:thinkPulse 1.2s ease infinite;
    }
    .think-dot:nth-child(2){animation-delay:.2s}
    .think-dot:nth-child(3){animation-delay:.4s}
    @keyframes thinkPulse{0%,100%{opacity:.3;transform:scale(1)}50%{opacity:1;transform:scale(1.3)}}

    /* ── INPUT BAR ── */
    .input-bar{
      padding:16px 24px;
      border-top:1px solid rgba(245,196,0,0.1);
      background:rgba(5,5,10,0.98);
      flex-shrink:0;position:relative;
    }
    .input-bar::before{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(245,196,0,0.25),transparent);
    }
    .input-wrap{display:flex;gap:10px;align-items:flex-end;}
    .input-prefix{
      font-family:var(--mono);font-size:.9em;color:var(--gold);
      padding-bottom:11px;opacity:.7;flex-shrink:0;
    }
    .input-field{
      flex:1;background:rgba(245,196,0,0.03);
      border:1px solid rgba(245,196,0,0.25);
      color:var(--text);padding:10px 14px;
      font-family:var(--mono);font-size:.88em;line-height:1.5;
      outline:none;resize:none;
      transition:border-color .2s,box-shadow .2s;
      caret-color:var(--gold);
    }
    .input-field:focus{
      border-color:rgba(245,196,0,0.6);
      box-shadow:0 0 0 1px rgba(245,196,0,0.15),inset 0 0 30px rgba(245,196,0,0.02);
    }
    .input-field::placeholder{color:var(--text-muted)}
    .send-btn{
      padding:10px 22px;
      background:linear-gradient(135deg,#8a6e00,#c9a200,#F5C400);
      border:none;color:#000;
      font-family:var(--display);font-size:.72em;font-weight:700;
      letter-spacing:.12em;cursor:pointer;
      transition:opacity .15s,box-shadow .15s;
      flex-shrink:0;align-self:stretch;
      position:relative;overflow:hidden;
    }
    .send-btn:hover{opacity:.9;box-shadow:0 0 20px rgba(245,196,0,0.4)}
    .send-btn::before{
      content:'';position:absolute;top:0;left:-100%;width:100%;height:100%;
      background:linear-gradient(90deg,transparent,rgba(255,255,255,.15),transparent);
      transition:left .4s;
    }
    .send-btn:hover::before{left:100%}
    .input-hint{
      font-family:var(--mono);font-size:.65em;color:var(--text-muted);
      margin-top:7px;display:flex;justify-content:space-between;align-items:center;
    }
    .input-hint span{color:rgba(245,196,0,0.5)}

    /* ── RIGHT PANEL ── */
    .right-panel{
      width:260px;border-left:1px solid rgba(245,196,0,0.1);
      background:rgba(5,5,10,0.96);
      display:flex;flex-direction:column;flex-shrink:0;
      overflow:hidden;
    }
    .rp-section{padding:16px;border-bottom:1px solid rgba(245,196,0,0.08);}
    .rp-title{
      font-family:var(--display);font-size:.65em;color:var(--gold);
      letter-spacing:.2em;text-transform:uppercase;margin-bottom:12px;
      display:flex;align-items:center;gap:6px;
    }
    .rp-title::before{content:'//';color:rgba(245,196,0,0.4);font-family:var(--mono)}

    .agent-item{
      display:flex;align-items:center;gap:8px;padding:5px 0;
      font-family:var(--mono);font-size:.72em;color:var(--text-dim);
      border-bottom:1px solid rgba(245,196,0,0.04);
    }
    .agent-dot{width:5px;height:5px;border-radius:50%;flex-shrink:0}
    .agent-dot.on{background:var(--success);box-shadow:0 0 5px var(--success)}
    .agent-dot.off{background:rgba(255,255,255,0.1)}
    .agent-name{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .agent-status{font-size:.9em;opacity:.6}

    .mini-term{
      flex:1;overflow-y:auto;padding:12px;
      font-family:var(--mono);font-size:.68em;line-height:1.9;
      color:rgba(245,196,0,0.5);
      scrollbar-width:none;
    }
    .mini-term::-webkit-scrollbar{display:none}
    .mini-term .term-line{display:block}
    .mini-term .term-line.ok{color:rgba(0,255,136,.5)}
    .mini-term .term-line.warn{color:rgba(245,196,0,.7)}
    .mini-term .term-line.err{color:rgba(255,51,68,.6)}

    /* ── EMPTY STATE ── */
    .chat-empty{
      flex:1;display:flex;flex-direction:column;align-items:center;
      justify-content:center;color:var(--text-muted);
      font-family:var(--mono);font-size:.82em;text-align:center;gap:12px;
    }
    .chat-empty .ce-symbol{
      font-family:var(--display);font-size:2.5em;color:rgba(245,196,0,0.1);
      letter-spacing:.2em;
    }
    .chat-empty .ce-text{color:rgba(245,196,0,0.2);letter-spacing:.1em}

    /* ── GRID BG inside chat panel ── */
    .chat-panel::before{
      content:'';position:absolute;inset:0;pointer-events:none;
      background-image:
        linear-gradient(rgba(245,196,0,0.015) 1px,transparent 1px),
        linear-gradient(90deg,rgba(245,196,0,0.015) 1px,transparent 1px);
      background-size:50px 50px;
    }

    @keyframes glitch{
      0%{clip-path:inset(80% 0 0 0);transform:translate(-3px,0)}
      10%{clip-path:inset(10% 0 85% 0);transform:translate(3px,0)}
      20%{clip-path:inset(40% 0 43% 0);transform:translate(-2px,0)}
      30%{clip-path:inset(92% 0 1% 0);transform:translate(2px,0)}
      40%{clip-path:inset(20% 0 60% 0);transform:translate(-1px,0)}
      50%{clip-path:inset(0 0 0 0);transform:none}
      100%{clip-path:inset(0 0 0 0);transform:none}
    }

    /* ── JS-generated dynamic card hover (replaces inline onmouseenter) ── */
    .js-card-hover{transition:all .25s}
    .js-card-hover:hover{transform:translateY(-3px);border-color:rgba(212,175,55,.5)!important;box-shadow:0 12px 40px rgba(0,0,0,.6),0 0 0 1px rgba(212,175,55,.1)}
    .js-card-row-hover{transition:all .2s}
    .js-card-row-hover:hover{border-color:rgba(212,175,55,.3)!important}
    .js-item-hover{transition:background .15s;cursor:default}
    .js-item-hover:hover{background:rgba(212,175,55,.04)!important}
    .js-agent-card{transition:all .25s}
    .js-agent-card:hover{transform:translateY(-3px);border-color:rgba(212,175,55,.3)!important;box-shadow:0 8px 32px rgba(0,0,0,.5),0 0 0 1px rgba(212,175,55,.08)}
    .btn-approve{padding:8px 16px;background:linear-gradient(135deg,#064e3b,#065f46);color:#34d399;border:2px solid rgba(52,211,153,.4);border-radius:8px;cursor:pointer;font-weight:700;font-size:.84em;font-family:inherit;transition:all .2s;white-space:nowrap}
    .btn-approve:hover{background:linear-gradient(135deg,#065f46,#047857);box-shadow:0 0 16px rgba(52,211,153,.4)}
    .btn-reject{padding:8px 16px;background:linear-gradient(135deg,#450a0a,#7f1d1d);color:#f87171;border:2px solid rgba(248,113,113,.4);border-radius:8px;cursor:pointer;font-weight:700;font-size:.84em;font-family:inherit;transition:all .2s;white-space:nowrap}
    .btn-reject:hover{background:linear-gradient(135deg,#7f1d1d,#991b1b);box-shadow:0 0 16px rgba(248,113,113,.4)}
    .btn-approve-sm{padding:6px 16px;background:linear-gradient(135deg,#14532d,#15803d);border:1px solid rgba(74,222,128,.3);border-radius:7px;color:#4ade80;font-weight:700;font-size:.78em;cursor:pointer;font-family:inherit;transition:all .2s}
    .btn-approve-sm:hover{box-shadow:0 0 12px rgba(74,222,128,.25)}
    .btn-reject-sm{padding:6px 16px;background:linear-gradient(135deg,#450a0a,#7f1d1d);border:1px solid rgba(239,68,68,.3);border-radius:7px;color:#f87171;font-weight:700;font-size:.78em;cursor:pointer;font-family:inherit;transition:all .2s}
    .btn-reject-sm:hover{box-shadow:0 0 12px rgba(239,68,68,.2)}
    .btn-rollback{padding:4px 12px;background:rgba(127,29,29,.6);border:1px solid rgba(239,68,68,.3);border-radius:6px;color:#f87171;font-size:.75em;font-weight:700;cursor:pointer;font-family:inherit;transition:all .2s}
    .btn-rollback:hover{background:rgba(127,29,29,.9)}
    .btn-deploy{width:100%;padding:12px;background:linear-gradient(135deg,var(--primary-dark),var(--primary));border:none;border-radius:9px;color:#000;font-weight:700;font-size:.88em;cursor:pointer;transition:all .2s;letter-spacing:.02em;font-family:inherit}
    .btn-deploy:hover{box-shadow:0 6px 24px rgba(212,175,55,.5);filter:brightness(1.08)}
    .btn-cmd-run{flex-shrink:0;padding:3px 10px;font-size:.72em;background:rgba(212,175,55,.1);border:1px solid rgba(212,175,55,.3);color:var(--gold);border-radius:5px;cursor:pointer;font-family:inherit;transition:all .15s}
    .btn-cmd-run:hover{background:rgba(212,175,55,.2)}
    .btn-cmd-copy{flex-shrink:0;padding:3px 8px;font-size:.7em;background:transparent;border:1px solid rgba(148,163,184,.12);color:var(--text-muted);border-radius:5px;cursor:pointer;font-family:inherit;transition:all .15s}
    .btn-cmd-copy:hover{border-color:rgba(212,175,55,.3);color:var(--gold)}
    .cmd-code{cursor:pointer;min-width:160px;max-width:220px;background:rgba(10,15,30,.9);padding:4px 9px;border-radius:5px;font-size:.8em;color:var(--gold-light);border:1px solid rgba(212,175,55,.18);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:border-color .15s}
    .cmd-code:hover{border-color:rgba(212,175,55,.5)}
    .btn-assign-task{width:100%;font-size:.78em;border:1px solid rgba(212,175,55,.3);color:var(--gold);padding:6px;border-radius:6px;transition:all .2s;background:transparent;cursor:pointer;font-family:inherit}
    .btn-assign-task:hover{background:rgba(212,175,55,.1);border-color:rgba(212,175,55,.6)}
    .color-swatch{width:34px;height:34px;border-radius:50%;border:2px solid rgba(255,255,255,.3);cursor:pointer;transition:transform .15s}
    .color-swatch:hover{transform:scale(1.15)}

    @media(max-width:900px){.right-panel{display:none}}

    /* ═══════════════════════════════════════════════════════
       DESIGN SYSTEM — UTILITY CLASSES  (Pass 2 additions)
       These replace scattered inline styles for consistency.
       ═══════════════════════════════════════════════════════ */

    /* ── Preset / power-preset cards ── */
    .preset-card{
      padding:14px 16px;
      background:linear-gradient(135deg,rgba(212,175,55,.1),rgba(212,175,55,.05));
      border:1px solid rgba(212,175,55,.28);
      border-radius:12px;
      color:var(--gold);
      text-align:left;cursor:pointer;font-family:inherit;
      transition:border-color .2s,background .2s,box-shadow .2s;
      display:flex;flex-direction:column;gap:4px;
    }
    .preset-card:hover{
      border-color:rgba(212,175,55,.55);
      background:linear-gradient(135deg,rgba(212,175,55,.18),rgba(212,175,55,.09));
      box-shadow:0 4px 18px rgba(212,175,55,.18);
    }
    .preset-card .pc-icon{font-size:1.3em}
    .preset-card .pc-name{font-weight:700;font-size:.9em}
    .preset-card .pc-desc{font-size:.74em;color:var(--text-muted)}

    /* ── Full-width form fields (replaces repeated inline styles) ── */
    .field-full{
      width:100%;background:var(--surface2);
      border:1px solid var(--border);border-radius:var(--radius-sm);
      color:var(--text);padding:8px;font-family:inherit;
    }
    textarea.field-full{resize:vertical}

    /* ── Gold outline button (Tier-2 important action) ── */
    .btn-gold{
      background:transparent;
      color:var(--gold);
      border:1px solid rgba(212,175,55,.45);
      border-radius:var(--radius-sm);
      padding:9px 20px;font-weight:700;font-size:.84em;
      cursor:pointer;font-family:inherit;
      transition:all .2s;
    }
    .btn-gold:hover{
      background:rgba(212,175,55,.12);
      border-color:var(--gold);
      box-shadow:0 4px 18px rgba(212,175,55,.3);
      transform:translateY(-1px);
    }

    /* ── Send-to-swarm/primary action button ── */
    .btn-swarm{
      padding:9px 20px;
      background:linear-gradient(135deg,var(--primary-dark),var(--primary));
      border:none;border-radius:10px;
      color:#000;font-weight:800;font-size:.84em;
      cursor:pointer;font-family:inherit;
      transition:all .2s;
      box-shadow:0 4px 14px rgba(212,175,55,.25);
    }
    .btn-swarm:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(212,175,55,.4)}

    /* ── Card with gold-tinted accent border ── */
    .card-gold{border:1px solid rgba(212,175,55,.25)!important}
    .card-ai{
      border:1px solid rgba(212,175,55,.2)!important;
      background:linear-gradient(135deg,rgba(212,175,55,.03),var(--surface2))!important;
    }
    /* ── Card with subtle accent border variants ── */
    .card-accent{border:1px solid rgba(212,175,55,.3)!important}

  </style>
</head>
<body>

<!-- ══ BOOT OVERLAY (used by runBootSequence / hideBoot) ══ -->
<div id="boot-overlay">
  <div class="boot-scanline"></div>
  <div class="boot-glow-h"></div>
  <div class="boot-corner tl"></div>
  <div class="boot-corner tr"></div>
  <div class="boot-corner bl"></div>
  <div class="boot-corner br"></div>
  <div class="boot-logo" data-text="AI EMPLOYEE">AI EMPLOYEE</div>
  <div class="boot-sub">Autonomous Workforce Interface · v4.0</div>
  <!-- Terminal output area -->
  <div class="boot-terminal">
    <div class="boot-terminal-inner" id="boot-terminal"></div>
  </div>
  <!-- Progress bar -->
  <div class="boot-bar-wrap">
    <div class="boot-bar-label">
      <span id="boot-stage-label">INITIALIZING</span>
      <span id="boot-pct">0%</span>
    </div>
    <div class="boot-bar-track">
      <div class="boot-bar-fill" id="boot-bar"></div>
    </div>
  </div>
  <!-- Login phase shown after boot completes -->
  <div id="boot-login">
    <div class="boot-login-box">
      <div class="boot-login-welcome">SYSTEM READY<span class="boot-login-cursor"></span></div>
      <div class="boot-login-sub">Redirecting to authentication…</div>
    </div>
  </div>
</div>

<!-- ══ LOGIN SCREEN ══ -->
<div id="login">
  <div class="login-panel">
    <div class="login-corner tl"></div>
    <div class="login-corner tr"></div>
    <div class="login-corner bl"></div>
    <div class="login-corner br"></div>
    <div class="login-welcome">WELCOME BACK</div>
    <div class="login-name" id="login-name">OPERATOR</div>
    <input class="login-field" type="text" id="login-user" placeholder="IDENTIFIER" value="admin" autocomplete="off"/>
    <input class="login-field" type="password" id="login-pass" placeholder="ACCESS CODE" value="••••••••"/>
    <button class="login-btn" onclick="doLogin()">AUTHENTICATE  ›</button>
  </div>
  <div class="vkb" id="vkb">
    <div class="vkb-row">
      <div class="vkb-key" onclick="vkType('1')">1</div><div class="vkb-key" onclick="vkType('2')">2</div>
      <div class="vkb-key" onclick="vkType('3')">3</div><div class="vkb-key" onclick="vkType('4')">4</div>
      <div class="vkb-key" onclick="vkType('5')">5</div><div class="vkb-key" onclick="vkType('6')">6</div>
      <div class="vkb-key" onclick="vkType('7')">7</div><div class="vkb-key" onclick="vkType('8')">8</div>
      <div class="vkb-key" onclick="vkType('9')">9</div><div class="vkb-key" onclick="vkType('0')">0</div>
      <div class="vkb-key wide" onclick="vkBackspace()">⌫ DEL</div>
    </div>
    <div class="vkb-row">
      <div class="vkb-key" onclick="vkType('q')">Q</div><div class="vkb-key" onclick="vkType('w')">W</div>
      <div class="vkb-key" onclick="vkType('e')">E</div><div class="vkb-key" onclick="vkType('r')">R</div>
      <div class="vkb-key" onclick="vkType('t')">T</div><div class="vkb-key" onclick="vkType('y')">Y</div>
      <div class="vkb-key" onclick="vkType('u')">U</div><div class="vkb-key" onclick="vkType('i')">I</div>
      <div class="vkb-key" onclick="vkType('o')">O</div><div class="vkb-key" onclick="vkType('p')">P</div>
    </div>
    <div class="vkb-row">
      <div class="vkb-key" onclick="vkType('a')">A</div><div class="vkb-key" onclick="vkType('s')">S</div>
      <div class="vkb-key" onclick="vkType('d')">D</div><div class="vkb-key" onclick="vkType('f')">F</div>
      <div class="vkb-key" onclick="vkType('g')">G</div><div class="vkb-key" onclick="vkType('h')">H</div>
      <div class="vkb-key" onclick="vkType('j')">J</div><div class="vkb-key" onclick="vkType('k')">K</div>
      <div class="vkb-key" onclick="vkType('l')">L</div>
      <div class="vkb-key wide" onclick="doLogin()">ENTER ↵</div>
    </div>
    <div class="vkb-row">
      <div class="vkb-key" onclick="vkType('z')">Z</div><div class="vkb-key" onclick="vkType('x')">X</div>
      <div class="vkb-key" onclick="vkType('c')">C</div><div class="vkb-key" onclick="vkType('v')">V</div>
      <div class="vkb-key" onclick="vkType('b')">B</div><div class="vkb-key" onclick="vkType('n')">N</div>
      <div class="vkb-key" onclick="vkType('m')">M</div>
      <div class="vkb-key wider" onclick="vkType(' ')">SPACE</div>
    </div>
  </div>
</div>

<!-- ── Offline Screen ── -->
<div id="offline-screen">
  <div class="offline-box">
    <div class="offline-title">⚠ SYSTEM OFFLINE</div>
    <pre class="offline-msg" id="offline-msg">> Backend unreachable
> GET /health → connection refused
> Check that the AI Employee server is running
> on http://localhost:3000</pre>
    <button class="offline-retry" onclick="retryBoot()">↺ RETRY CONNECTION</button>
  </div>
</div>

<!-- ── Login Screen ── -->
<div id="login-screen">
  <div class="login-box" style="position:relative">
    <div class="login-corner tl"></div>
    <div class="login-corner tr"></div>
    <div class="login-corner bl"></div>
    <div class="login-corner br"></div>
    <div class="login-scanline"></div>
    <div class="login-logo">AI EMPLOYEE</div>
    <div class="login-sub">Autonomous Intelligence Platform · v4.0</div>
    <label class="login-label" for="login-user">Operator ID</label>
    <input class="login-input" id="login-user" type="text" placeholder="enter operator id" autocomplete="off" spellcheck="false"/>
    <label class="login-label" for="login-pass">Access Code</label>
    <input class="login-input" id="login-pass" type="password" placeholder="••••••••" autocomplete="off"/>
    <button class="login-btn" id="login-btn" onclick="submitLogin()">AUTHENTICATE <span id="login-cursor">_</span></button>
    <div class="login-status" id="login-status"></div>
  </div>
</div>

<!-- ── Scanline overlay ── -->
<div class="scanlines"></div>
<!-- ── Particle canvas ── -->
<canvas id="particles-canvas"></canvas>

<div class="app">

<!-- ── Header ── -->
<header>
  <div class="header-left">
    <div class="logo glitch">🤖</div>
    <div class="header-title">
      <h1>AI Employee</h1>
      <div class="sub" id="header-sub">Loading…</div>
    </div>
  </div>
  <div class="header-right">
    <div class="topbar-time" id="topbar-time"></div>
    <div class="tb-indicator"><span class="tb-dot"></span>SYSTEM ONLINE</div>
    <div class="tb-indicator" id="tb-agent-count">0 AGENTS</div>
    <div class="hdr-ctrl">
      <button class="hdr-btn hdr-btn-start" id="hdr-start-btn" onclick="startAll()" title="Start all agents">▶ Start</button>
      <button class="hdr-btn hdr-btn-stop" id="hdr-stop-btn" onclick="stopAll()" title="Stop all agents">■ Stop</button>
    </div>
    <div class="hdr-clock" id="hdr-clock">00:00:00</div>
    <span class="tb-clock" id="tb-clock" style="display:none">00:00:00</span>
    <div class="status-pill"><div class="status-dot"></div><span id="header-status">Running</span></div>
  </div>
</header>

<!-- ── Navigation (grouped two-tier) ── -->
<div class="nav-wrapper">
  <!-- Hidden legacy scroll buttons for JS compatibility -->
  <button class="nav-scroll-btn left hidden" id="nav-scroll-left" style="display:none"></button>
  <!-- Primary group nav -->
  <nav id="main-nav">
    <button class="nav-group-btn active" data-group="overview" onclick="switchGroup('overview',this)">◈ Command Center</button>
    <button class="nav-group-btn" data-group="intelligence" id="nav-btn-chat-group" onclick="switchGroup('intelligence',this)">◈ Intelligence <span class="nav-arrow">▾</span></button>
    <button class="nav-group-btn" data-group="operations" onclick="switchGroup('operations',this)">◈ Operations <span class="nav-arrow">▾</span></button>
    <button class="nav-group-btn" data-group="workforce" onclick="switchGroup('workforce',this)">◈ Workforce <span class="nav-arrow">▾</span></button>
    <button class="nav-group-btn" data-group="growth" onclick="switchGroup('growth',this)">◈ Growth &amp; Revenue <span class="nav-arrow">▾</span></button>
    <button class="nav-group-btn" data-group="governance" onclick="switchGroup('governance',this)">◈ Governance &amp; System <span class="nav-arrow">▾</span></button>
    <button class="nav-group-btn labs-group" data-group="labs" onclick="switchGroup('labs',this)">🧪 Labs <span class="nav-arrow">▾</span></button>
  </nav>
  <button class="nav-scroll-btn right hidden" id="nav-scroll-right" style="display:none"></button>
</div>
<!-- Sub-navigation rows (one per group) -->
<div class="sub-nav active" id="subnav-overview">
  <button class="active" onclick="switchTab('dashboard',this)">◈ Dashboard</button>
</div>
<div class="sub-nav" id="subnav-intelligence">
  <button onclick="switchTab('chat',this)" id="nav-btn-chat">💬 Chat</button>
  <button onclick="switchTab('history',this)">🕐 History</button>
  <button onclick="switchTab('briefing',this)">📰 Briefing</button>
  <button onclick="switchTab('meetings',this)">📅 Meetings</button>
  <button onclick="switchTab('competitors',this)">🔍 Competitors</button>
</div>
<div class="sub-nav" id="subnav-operations">
  <button onclick="switchTab('tasks',this)">🚀 Tasks</button>
  <button onclick="switchTab('scheduler',this)">📅 Scheduler</button>
  <button onclick="switchTab('workflows',this)">⚙️ Workflows</button>
  <button onclick="switchTab('templates',this)">📋 Templates</button>
  <button onclick="switchTab('artifacts',this)">📦 Outputs</button>
</div>
<div class="sub-nav" id="subnav-workforce">
  <button onclick="switchTab('swarm',this)">🐝 Swarm</button>
  <button onclick="switchTab('workers',this)">👷 Agents</button>
  <button onclick="switchTab('live-office',this)">🏢 Live Office</button>
  <button onclick="switchTab('skills',this)">🛠️ Skills</button>
  <button onclick="switchTab('improvements',this)">💡 Improvements</button>
  <button onclick="switchTab('commands',this)">📜 Commands</button>
  <button onclick="switchTab('org',this)">🏢 Org Chart</button>
  <button onclick="switchTab('team',this)">👥 Team</button>
</div>
<div class="sub-nav" id="subnav-growth">
  <button onclick="switchTab('crm',this)">🎯 CRM</button>
  <button onclick="switchTab('email-mkt',this)">📧 Email</button>
  <button onclick="switchTab('social',this)">📱 Social</button>
  <button onclick="switchTab('content-calendar',this)">📅 Content Cal</button>
  <button onclick="switchTab('metrics',this)">📈 ROI &amp; Metrics</button>
  <button onclick="switchTab('budget',this)">💰 Budget</button>
  <button onclick="switchTab('invoicing',this)">💳 Invoicing</button>
  <button onclick="switchTab('financial',this)">💰 Financial</button>
  <button onclick="switchTab('analytics-bi',this)">📊 Analytics</button>
</div>
<div class="sub-nav" id="subnav-governance">
  <button onclick="switchTab('guardrails',this)" id="nav-btn-guardrails">🔒 Guardrails <span id="guardrail-pending-badge" style="display:none;background:#ef4444;color:#fff;border-radius:10px;padding:1px 6px;font-size:.7em;font-weight:700;margin-left:3px;animation:blink 1.5s infinite"></span></button>
  <button onclick="switchTab('memory',this)">🧠 Memory</button>
  <button onclick="switchTab('integrations',this)">🔌 Integrations</button>
  <button onclick="switchTab('options',this)">⚙️ Options</button>
  <button onclick="switchTab('goals',this)">🎯 Goals</button>
  <button onclick="switchTab('tickets',this)">🎫 Tickets</button>
  <button onclick="switchTab('boardroom',this)">🛡️ Boardroom</button>
  <button onclick="switchTab('companies',this)">🏗️ Companies</button>
  <button onclick="switchTab('export',this)">📤 Export</button>
</div>
<div class="sub-nav" id="subnav-labs">
  <button onclick="switchTab('blacklight',this)" id="nav-blacklight-btn">⚡ BLACKLIGHT</button>
  <button onclick="switchTab('ascend',this)" id="nav-ascend-btn">🔥 ASCEND FORGE</button>
  <button onclick="switchTab('neural-brain',this)" id="nav-neural-brain-btn">🧠 Neural Brain</button>
  <button onclick="switchTab('health',this)">🏥 Health</button>
  <button onclick="switchTab('brand',this)">🎨 Brand</button>
  <button onclick="switchTab('website-builder',this)">🌐 Website</button>
  <button onclick="switchTab('support-desk',this)">🎫 Support</button>
</div>

<main>

<!-- ── Dashboard ── -->
<div id="tab-dashboard" class="tab-content active">

  <!-- ── SYSTEM ONLINE Status Banner ── -->
  <div style="display:flex;align-items:center;gap:12px;padding:8px 16px;background:linear-gradient(90deg,rgba(212,175,55,.06),rgba(212,175,55,.03),rgba(0,0,0,0));border:1px solid rgba(212,175,55,.22);border-radius:8px;margin-bottom:14px;font-family:var(--mono);font-size:.72em;letter-spacing:.08em;overflow:hidden;position:relative" id="ov-system-banner">
    <div style="position:absolute;inset:0;background:linear-gradient(90deg,rgba(212,175,55,.04),transparent);pointer-events:none"></div>
    <div style="width:8px;height:8px;border-radius:50%;background:var(--gold);box-shadow:0 0 8px rgba(212,175,55,.6),0 0 16px rgba(212,175,55,.3);animation:blink 1.2s infinite;flex-shrink:0"></div>
    <span style="color:var(--gold);font-weight:700;text-transform:uppercase">◈ SYSTEM ONLINE</span>
    <div style="width:1px;height:14px;background:rgba(255,255,255,.12)"></div>
    <span style="color:var(--gold);text-transform:uppercase" id="ov-banner-mode">POWER MODE</span>
    <div style="width:1px;height:14px;background:rgba(255,255,255,.12)"></div>
    <span style="color:var(--text-secondary)" id="ov-banner-uptime">Uptime: –</span>
    <div style="flex:1"></div>
    <span style="color:var(--gold);font-weight:700" id="ov-banner-agents">– / – Agents Active</span>
  </div>

  <!-- ── Overview Page Header ── -->
  <div class="page-header" style="border-left-color:var(--gold);background:linear-gradient(135deg,rgba(212,175,55,.08),rgba(212,175,55,.02));border:1px solid rgba(212,175,55,.2);box-shadow:0 0 30px rgba(212,175,55,.06)">
    <div class="page-header-icon" style="color:var(--gold);filter:drop-shadow(0 0 8px rgba(212,175,55,.5))">◈</div>
    <div>
      <div class="page-header-title" style="background:linear-gradient(135deg,#D4AF37,#f5c400);-webkit-background-clip:text;-webkit-text-fill-color:transparent">AI Employee Command Center</div>
      <div class="page-header-desc">Real-time operations hub — monitor all agents, launch tasks, and manage your autonomous AI workforce from one place.</div>
    </div>
    <span class="page-header-badge" style="color:var(--gold);background:rgba(212,175,55,.1);border:1px solid rgba(212,175,55,.3)">Live Operations</span>
  </div>

  <!-- ── Agent Count Hero Cards ── -->
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:18px">
    <div class="ov-hero-card ov-hero-running" role="button" tabindex="0" onclick="showStatDetail('running')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();showStatDetail('running')}" style="cursor:pointer" aria-label="Agents Running – click for details">
      <div style="font-size:.65em;letter-spacing:.12em;text-transform:uppercase;color:rgba(212,175,55,.65);margin-bottom:6px;font-family:var(--mono)">▶ RUNNING</div>
      <div class="val" id="stat-running" style="font-size:2.6em;font-weight:800;color:var(--gold);line-height:1;font-family:var(--display);text-shadow:0 0 18px rgba(212,175,55,.35)">–</div>
      <div style="font-size:.75em;color:var(--text-secondary);margin-top:4px">Agents Active</div>
      <div style="font-size:.68em;color:rgba(212,175,55,.5);margin-top:4px" id="stat-running-sub"></div>
    </div>
    <div class="ov-hero-card ov-hero-total" role="button" tabindex="0" onclick="showStatDetail('total')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();showStatDetail('total')}" style="cursor:pointer" aria-label="Total Agents – click for details">
      <div style="font-size:.65em;letter-spacing:.12em;text-transform:uppercase;color:rgba(212,175,55,.65);margin-bottom:6px;font-family:var(--mono)">◆ TOTAL</div>
      <div class="val" id="stat-total" style="font-size:2.6em;font-weight:800;color:var(--gold);line-height:1;font-family:var(--display);text-shadow:0 0 18px rgba(212,175,55,.35)">–</div>
      <div style="font-size:.75em;color:var(--text-secondary);margin-top:4px">Registered Agents</div>
      <div style="font-size:.68em;color:rgba(212,175,55,.45);margin-top:4px" id="stat-total-sub"></div>
    </div>
    <div class="ov-hero-card ov-hero-offline" aria-label="Offline Agents">
      <div style="font-size:.65em;letter-spacing:.12em;text-transform:uppercase;color:rgba(212,175,55,.65);margin-bottom:6px;font-family:var(--mono)">◌ OFFLINE</div>
      <div class="val" id="stat-offline" style="font-size:2.6em;font-weight:800;color:var(--gold);line-height:1;font-family:var(--display);text-shadow:0 0 18px rgba(212,175,55,.25)">–</div>
      <div style="font-size:.75em;color:var(--text-secondary);margin-top:4px">Agents Stopped</div>
      <div style="font-size:.68em;color:rgba(212,175,55,.45);margin-top:4px" id="stat-offline-sub"></div>
    </div>
    <div class="ov-hero-card ov-hero-gateway" role="button" tabindex="0" onclick="showStatDetail('gateway')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();showStatDetail('gateway')}" style="cursor:pointer" aria-label="Gateway – click for details">
      <div style="font-size:.65em;letter-spacing:.12em;text-transform:uppercase;color:rgba(212,175,55,.65);margin-bottom:6px;font-family:var(--mono)">◉ GATEWAY</div>
      <div class="val" id="stat-gateway" style="font-size:2.6em;font-weight:800;color:var(--gold);line-height:1;font-family:var(--display);text-shadow:0 0 18px rgba(212,175,55,.25)">–</div>
      <div style="font-size:.75em;color:var(--text-secondary);margin-top:4px">API Gateway</div>
      <div style="font-size:.68em;color:rgba(212,175,55,.45);margin-top:4px" id="stat-gateway-sub"></div>
    </div>
    <div class="ov-hero-card ov-hero-uptime" role="button" tabindex="0" onclick="showStatDetail('uptime')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();showStatDetail('uptime')}" style="cursor:pointer" aria-label="Uptime – click for details">
      <div style="font-size:.65em;letter-spacing:.12em;text-transform:uppercase;color:rgba(212,175,55,.65);margin-bottom:6px;font-family:var(--mono)">◎ UPTIME</div>
      <div class="val" id="stat-uptime" style="font-size:2.6em;font-weight:800;color:var(--gold);line-height:1;font-family:var(--display);text-shadow:0 0 18px rgba(212,175,55,.25)">–</div>
      <div style="font-size:.75em;color:var(--text-secondary);margin-top:4px">System Uptime</div>
      <div style="font-size:.68em;color:rgba(212,175,55,.45);margin-top:4px" id="stat-uptime-sub"></div>
    </div>
  </div>

  <!-- Stat detail panel -->
  <div id="stat-detail-panel" style="display:none;background:var(--surface2);border:1px solid var(--gold);border-radius:var(--radius);padding:16px;margin-bottom:16px;animation:fadeIn .2s ease">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <div class="card-title" id="stat-detail-title">Details</div>
      <button class="btn btn-ghost btn-sm" onclick="document.getElementById('stat-detail-panel').style.display='none'">✕</button>
    </div>
    <div id="stat-detail-content" style="font-size:.88em;color:var(--text-secondary)"></div>
  </div>

  <!-- ── Cyber Operations Panel ── -->
  <div id="cyber-panel">
    <!-- Left: AI Heartbeat / System Logs + Doctor Panel (stacked) -->
    <div class="cyber-col" style="display:flex;flex-direction:column;overflow:hidden">
      <!-- Doctor Diagnostics Panel -->
      <div id="doctor-panel">
        <div class="dp-header">
          <div class="dp-title"><span class="hdr-dot"></span>🩺 Diagnostics</div>
          <button class="btn btn-ghost btn-sm" onclick="loadDoctorPanel()" style="font-size:.7em;padding:2px 8px">↻</button>
        </div>
        <div id="doctor-items-list"><div class="dp-empty">Loading…</div></div>
      </div>
      <div class="cyber-col-header" style="flex-shrink:0">
        <span class="hdr-dot"></span>
        AI Heartbeat · System Logs
      </div>
      <div id="heartbeat-log" style="flex:1;min-height:0"></div>
    </div>

    <!-- Center: Main Orchestrator Chat -->
    <div class="cyber-col">
      <div class="cyber-col-header">
        <span class="hdr-dot"></span>
        Main Orchestrator · Chat
      </div>
      <div id="cyber-chat-messages"></div>
      <div class="chat-input-row">
        <input id="cyber-chat-input" type="text" placeholder="Send command to orchestrator…" onkeydown="if(event.key==='Enter')sendCyberChat()" autocomplete="off" spellcheck="false"/>
        <button id="cyber-chat-send" onclick="sendCyberChat()">▶ SEND</button>
      </div>
    </div>

    <!-- Right: System Stats -->
    <div class="cyber-col">
      <div class="cyber-col-header">
        <span class="hdr-dot"></span>
        System Stats
      </div>
      <div id="stats-col">
        <div class="stat-ring-wrap">
          <svg class="stat-ring-svg" viewBox="0 0 90 90">
            <circle cx="45" cy="45" r="36" fill="none" stroke="rgba(212,175,55,.1)" stroke-width="6"/>
            <circle id="cpu-ring-circle" cx="45" cy="45" r="36" fill="none" stroke="#D4AF37" stroke-width="6"
              stroke-dasharray="226" stroke-dashoffset="226" stroke-linecap="round"
              style="transform:rotate(-90deg);transform-origin:center;transition:stroke-dashoffset 1s ease;filter:drop-shadow(0 0 4px #D4AF37)"/>
            <text x="45" y="50" text-anchor="middle" fill="#D4AF37" font-size="14" font-family="monospace" id="cpu-ring-text">0%</text>
          </svg>
          <div class="stat-ring-label">CPU / Load</div>
        </div>
        <div class="stat-item">
          <div>
            <div class="si-label">Agents Running</div>
            <div class="si-bar"><div class="si-bar-fill" id="sb-agents" style="width:0%"></div></div>
          </div>
          <div class="si-val" id="sv-agents">–</div>
        </div>
        <div class="stat-item">
          <div>
            <div class="si-label">Tasks Queued</div>
            <div class="si-bar"><div class="si-bar-fill" id="sb-tasks" style="width:0%"></div></div>
          </div>
          <div class="si-val" id="sv-tasks">–</div>
        </div>
        <div class="stat-item">
          <div>
            <div class="si-label">Memory</div>
            <div class="si-bar"><div class="si-bar-fill" id="sb-mem" style="width:0%"></div></div>
          </div>
          <div class="si-val" id="sv-mem">–</div>
        </div>
        <div class="stat-item">
          <div><div class="si-label">Gateway</div></div>
          <div class="si-val" id="sv-gw" style="color:var(--success)">online</div>
        </div>
        <div class="stat-item">
          <div><div class="si-label">Uptime</div></div>
          <div class="si-val" id="sv-uptime">–</div>
        </div>
        <div class="stat-item">
          <div><div class="si-label">Session</div></div>
          <div class="si-val" id="sv-session" style="font-size:.75em">–</div>
        </div>
      </div>
    </div>
  </div>

  <!-- System Control Hero -->
  <div class="sys-control">
    <div class="sys-control-left">
      <div class="sys-status-ring" id="sys-ring">
        <div class="ring-bg">🤖</div>
        <div class="ring-pulse"></div>
      </div>
      <div class="sys-control-info">
        <h2>AI Employee System</h2>
        <p id="sys-control-sub">Loading system status…</p>
        <div class="health-bar-wrap" style="min-width:200px">
          <div class="health-bar-track"><div class="health-bar-fill" id="health-bar"></div></div>
          <div class="health-label"><span id="health-label-left">Agent Health</span><span id="health-label-right">–</span></div>
        </div>
      </div>
    </div>
    <div class="sys-control-right">
      <button class="btn-hero btn-hero-start" id="hero-start-btn" onclick="startAll()">
        <span class="btn-icon">▶</span> Start All Agents
      </button>
      <button class="btn-hero btn-hero-stop" id="hero-stop-btn" onclick="stopAll()">
        <span class="btn-icon">■</span> Stop All Agents
      </button>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🤖</span> Agent Status</div>
        <button class="btn btn-ghost btn-sm" onclick="loadDashboard()">↻ Refresh</button>
      </div>
      <div id="bot-status-list"><div class="empty"><div class="icon">🔍</div><p>Loading agents…</p></div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">⚡</span> Quick Actions</div>
      </div>
      <div class="actions-bar">
        <button class="btn btn-success" onclick="startAll()">▶ Start All Agents</button>
        <button class="btn btn-danger" onclick="stopAll()">■ Stop All Agents</button>
        <button class="btn btn-primary" onclick="runOnboard()">⚡ Run Onboard</button>
        <button class="btn btn-ghost btn-sm" onclick="openGatewayModal()">📡 AI Gateway</button>
      </div>
      <hr>
      <div class="card-title" style="margin-bottom:10px"><span class="icon" style="color:var(--gold)">◈</span> System Health</div>
      <div id="system-health-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:.84em">
        <div class="health-check-item" id="hc-api"><span class="hc-dot">●</span> API Server <span class="hc-val">–</span></div>
        <div class="health-check-item" id="hc-ollama"><span class="hc-dot">●</span> Ollama LLM <span class="hc-val">–</span></div>
        <div class="health-check-item" id="hc-agents"><span class="hc-dot">●</span> Agents <span class="hc-val">–</span></div>
        <div class="health-check-item" id="hc-db"><span class="hc-dot">●</span> State Store <span class="hc-val">–</span></div>
        <div class="health-check-item" id="hc-gateway"><span class="hc-dot">●</span> Gateway <span class="hc-val">–</span></div>
        <div class="health-check-item" id="hc-memory"><span class="hc-dot">●</span> Memory <span class="hc-val">–</span></div>
        <div class="health-check-item" id="hc-wavefield"><span class="hc-dot">●</span> Wave Field <span class="hc-val">–</span></div>
      </div>
      <div class="wf-metrics-grid" id="wf-metrics-grid">
        <div class="wf-metric"><div class="k">Routed</div><div class="v" id="wf-m-route">0</div></div>
        <div class="wf-metric"><div class="k">Wave Field Routed</div><div class="v" id="wf-m-route-wf">0</div></div>
        <div class="wf-metric"><div class="k">Fallbacks</div><div class="v" id="wf-m-fallbacks">0</div></div>
        <div class="wf-metric"><div class="k">Health Failures</div><div class="v" id="wf-m-health-fail">0</div></div>
        <div class="wf-metric"><div class="k">Shadow Requests</div><div class="v" id="wf-m-shadow">0</div></div>
        <div class="wf-metric"><div class="k">Wave Field Errors</div><div class="v" id="wf-m-errors">0</div></div>
      </div>
      <hr style="margin:12px 0">
      <!-- BLACKLIGHT quick-toggle -->
      <div style="padding:10px 0;border-bottom:1px solid rgba(148,163,184,.08);margin-bottom:6px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:1.1rem">⚡</span>
            <div>
              <div style="font-size:.86em;font-weight:600;color:var(--text)">BLACKLIGHT Mode</div>
              <div style="font-size:.75em;color:var(--text-muted)" id="dash-bl-sublabel">Autonomous agent — idle</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <label class="toggle" title="Toggle BLACKLIGHT on/off">
              <input type="checkbox" id="dash-bl-toggle" onchange="blToggle(this.checked)"/>
              <span class="slider"></span>
            </label>
          </div>
        </div>
        <input id="dash-bl-goal-input" placeholder="Set a goal to activate BLACKLIGHT…"
          aria-label="BLACKLIGHT goal"
          style="width:100%;box-sizing:border-box;font-size:.8em" autocomplete="off"
          oninput="(function(v){var m=document.getElementById('bl-goal-input');if(m&&!m.value)m.value=v;})(this.value)"/>
      </div>
      <!-- Hermes Agent quick-toggle -->
      <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(148,163,184,.08);margin-bottom:10px">
        <div style="display:flex;align-items:center;gap:10px">
          <span style="font-size:1.1rem">🧠</span>
          <div>
            <div style="font-size:.86em;font-weight:600;color:var(--text)">Hermes Agent</div>
            <div style="font-size:.75em;color:var(--text-muted)" id="dash-hermes-sublabel">Reasoning agent — stopped</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <label class="toggle" title="Toggle Hermes Agent on/off">
            <input type="checkbox" id="dash-hermes-toggle" onchange="hermesToggle(this.checked)"/>
            <span class="slider"></span>
          </label>
        </div>
      </div>
      <!-- ASCEND FORGE status widget -->
      <div style="padding:10px 0;border-bottom:1px solid rgba(148,163,184,.08);margin-bottom:6px" id="dash-af-widget">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:1.1rem">🔥</span>
            <div>
              <div style="font-size:.86em;font-weight:600;color:var(--text)">ASCEND FORGE</div>
              <div style="font-size:.75em;color:#f59e0b" id="dash-af-sublabel">Self-improver — idle</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <div id="dash-af-pct-badge" style="font-size:.72em;font-weight:700;color:#fbbf24;padding:2px 7px;border-radius:12px;background:rgba(217,119,6,.15);border:1px solid rgba(217,119,6,.3);display:none">0%</div>
            <button class="btn btn-ghost btn-sm" style="padding:3px 8px;font-size:.72em;border-color:rgba(217,119,6,.3);color:#f59e0b" onclick="switchTab('ascend',null)">Open →</button>
          </div>
        </div>
        <div id="dash-af-progress-wrap" style="display:none">
          <div style="background:rgba(0,0,0,.4);border-radius:100px;height:6px;overflow:hidden;border:1px solid rgba(217,119,6,.15)">
            <div id="dash-af-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#92400e,#d97706,#fbbf24);border-radius:100px;transition:width .4s ease"></div>
          </div>
          <div id="dash-af-task-text" style="font-size:.72em;color:var(--text-muted);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"></div>
        </div>
      </div>
      <div id="system-info" style="display:none"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">💬</span> Quick WhatsApp Commands</div>
      <a href="#" onclick="event.preventDefault();switchTab('commands',null)" style="font-size:.78em;color:var(--gold);text-decoration:none">View all →</a>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:6px">
      <div style="background:rgba(212,175,55,.05);border:1px solid rgba(212,175,55,.15);border-radius:8px;padding:8px 12px;display:flex;align-items:center;gap:10px"><code style="color:var(--gold-light);font-size:.8em;min-width:60px">status</code><span style="font-size:.78em;color:var(--text-muted)">Get current status report</span></div>
      <div style="background:rgba(212,175,55,.05);border:1px solid rgba(212,175,55,.15);border-radius:8px;padding:8px 12px;display:flex;align-items:center;gap:10px"><code style="color:var(--gold-light);font-size:.8em;min-width:60px">workers</code><span style="font-size:.78em;color:var(--text-muted)">List active agents</span></div>
      <div style="background:rgba(212,175,55,.05);border:1px solid rgba(212,175,55,.15);border-radius:8px;padding:8px 12px;display:flex;align-items:center;gap:10px"><code style="color:var(--gold-light);font-size:.8em;min-width:60px">schedule</code><span style="font-size:.78em;color:var(--text-muted)">List scheduled tasks</span></div>
      <div style="background:rgba(212,175,55,.05);border:1px solid rgba(212,175,55,.15);border-radius:8px;padding:8px 12px;display:flex;align-items:center;gap:10px"><code style="color:var(--gold-light);font-size:.8em;min-width:60px">help</code><span style="font-size:.78em;color:var(--text-muted)">Show all commands</span></div>
    </div>
  </div>

  <!-- System Resources card (real hardware metrics) -->
  <div class="card" id="sysres-card" style="border:1px solid rgba(212,175,55,.2);background:linear-gradient(135deg,rgba(212,175,55,.03),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">⬡</span> System Resources</div>
      <div style="display:flex;align-items:center;gap:8px">
        <span id="sysres-updated" style="font-size:.7em;color:var(--text-muted)">Loading…</span>
        <button class="btn btn-ghost btn-sm" onclick="loadSysRes()">↻</button>
      </div>
    </div>
    <div id="sysres-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px">
      <!-- filled by JS -->
      <div class="empty" style="grid-column:1/-1"><div class="icon">⬡</div><p>Loading hardware metrics…</p></div>
    </div>
  </div>

  <!-- CEO Daily Briefing Widget -->
  <div class="card" style="border:1px solid rgba(212,175,55,.25);background:linear-gradient(135deg,rgba(212,175,55,.06),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">📰</span> CEO Daily Briefing</div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" onclick="loadCEOBriefing()">↻ Refresh</button>
        <button class="btn btn-ghost btn-sm" onclick="forceRegenerateBriefing()">⚡ Regenerate</button>
        <button class="btn btn-ghost btn-sm" onclick="switchTab('briefing',document.querySelector('nav button[onclick*=briefing]'))">Full View →</button>
      </div>
    </div>
    <div id="dash-ceo-briefing">
      <div class="empty"><div class="icon">📰</div><p>Loading today's briefing…</p></div>
    </div>
  </div>

  <!-- Live Agent Activity Map -->
  <div class="card card-ai">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">◈</span> Live Agent Activity Map</div>
      <div style="display:flex;align-items:center;gap:8px">
        <span id="dash-agent-map-status" style="font-size:.73em;padding:2px 8px;border-radius:8px;background:rgba(212,175,55,.1);color:var(--gold);border:1px solid rgba(212,175,55,.2)">● Watching</span>
        <button class="btn btn-ghost btn-sm" onclick="loadDashboard()">↻ Refresh</button>
        <button class="btn btn-ghost btn-sm" onclick="switchTab('live-office',null)">🏢 Full Office View →</button>
      </div>
    </div>
    <p style="font-size:.8em;color:var(--text-muted);margin-bottom:12px">Real-time view of all agents and their current task. Click any agent to inspect.</p>
    <div id="dash-agent-map" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px">
      <div class="empty"><div class="icon" style="font-size:1.4em">🤖</div><p style="font-size:.84em">Loading agent map…</p></div>
    </div>
  </div>
</div>

<!-- ── Chat ── -->
<div id="tab-chat" class="tab-content">
  <!-- Chat Panel (reference layout) -->
  <div style="display:flex;height:calc(100vh - 120px)">
    <!-- Chat Main -->
    <div class="chat-panel">
      <!-- Chat Header -->
      <div class="chat-header">
        <div class="ch-left">
          <div class="ch-icon">◈</div>
          <div>
            <div class="ch-title">AI COMMAND CENTER</div>
            <div class="ch-sub">Direct interface → AI workforce</div>
          </div>
        </div>
        <div class="ch-right">
          <select class="model-select" id="chat-model" onchange="updateChatModelBadge()">
            <option value="auto">⚡ AUTO</option>
            <option value="ollama">🦙 OLLAMA</option>
            <option value="gemma">💎 GEMMA</option>
            <option value="nvidia">🔷 NVIDIA NIM</option>
            <option value="openai">◻ OPENAI</option>
            <option value="anthropic">◈ CLAUDE</option>
            <option value="groq">⚡ GROQ</option>
            <option value="external">◉ EXTERNAL</option>
          </select>
          <div class="ch-badge" id="chat-model-badge">AUTO</div>
          <div id="chat-hermes-status" style="display:flex;align-items:center;gap:5px;font-family:var(--mono);font-size:.68em;color:var(--text-dim)">
            <span id="chat-hermes-dot" style="width:5px;height:5px;border-radius:50%;background:#3a3428"></span>
            <span id="chat-hermes-label">HERMES –</span>
          </div>
          <button class="ch-ctrl" onclick="loadChatLog()">⟳ SYNC</button>
          <button class="ch-ctrl" onclick="clearChatDisplay()">⌫ CLR</button>
        </div>
      </div>
      <!-- Chat Log -->
      <div id="chat-log">
        <div class="chat-empty" id="chat-empty">
          <div class="ce-symbol">◈</div>
          <div class="ce-text">AWAITING COMMAND INPUT</div>
          <div style="font-size:.72em;color:rgba(245,196,0,0.15);letter-spacing:.05em">System ready. No active session.</div>
        </div>
      </div>
      <!-- Input Bar -->
      <div class="input-bar">
        <div class="input-wrap">
          <div class="input-prefix">&gt;_</div>
          <textarea id="chat-input" class="input-field" rows="2"
            placeholder="Enter command or idea for AI workforce…"
            onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChat()}"></textarea>
          <button class="send-btn" onclick="sendChat()">SEND</button>
        </div>
        <div class="input-hint">
          <span>ENTER to transmit · SHIFT+ENTER new line</span>
          <span id="chat-agent-indicator">Auto-routing active</span>
        </div>
      </div>
    </div>
    <!-- Right Panel -->
    <div class="right-panel">
      <div class="rp-section">
        <div class="rp-title">Agents</div>
        <div id="agent-status-list">
          <div class="agent-item"><div class="agent-dot off"></div><div class="agent-name" style="color:var(--text-muted)">Loading…</div></div>
        </div>
      </div>
      <div class="rp-section" style="flex:1;display:flex;flex-direction:column;overflow:hidden;padding-bottom:0">
        <div class="rp-title">System Log</div>
        <div class="mini-term" id="mini-term">
          <span class="term-line ok">// SYSTEM BOOT COMPLETE</span>
          <span class="term-line">// INTERFACES ONLINE</span>
          <span class="term-line">// AWAITING INPUT</span>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ── Live Office ── -->
<div id="tab-live-office" class="tab-content">
  <div style="height:calc(100vh - 115px);display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden">
    <!-- Office header -->
    <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 20px;border-bottom:1px solid rgba(245,196,0,.15);background:var(--surface2);flex-shrink:0">
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:32px;height:32px;background:linear-gradient(135deg,#B8960C,#F5C400);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:1em">🏢</div>
        <div>
          <div style="font-weight:700;font-size:.92em">Live Office</div>
          <div id="office-agent-count" style="font-size:.72em;color:var(--text-muted)">Loading agents…</div>
        </div>
      </div>
      <button class="btn btn-ghost btn-sm" onclick="loadLiveOffice()">↻ Refresh</button>
    </div>
    <!-- Office floor -->
    <div style="flex:1;position:relative;overflow:hidden;background:linear-gradient(180deg,#111 0%,#0d0d0d 60%,#0a0a0a 100%)">
      <div style="position:absolute;inset:0;background-image:linear-gradient(rgba(212,175,55,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(212,175,55,.03) 1px,transparent 1px);background-size:60px 60px;pointer-events:none"></div>
      <!-- Zone dividers -->
      <div style="position:absolute;top:0;left:33.3%;bottom:0;width:1px;background:linear-gradient(180deg,transparent,rgba(212,175,55,.08),transparent);pointer-events:none"></div>
      <div style="position:absolute;top:0;left:66.6%;bottom:0;width:1px;background:linear-gradient(180deg,transparent,rgba(212,175,55,.08),transparent);pointer-events:none"></div>
      <div style="position:absolute;bottom:0;left:0;right:0;height:10px;background:linear-gradient(90deg,rgba(212,175,55,.15),rgba(212,175,55,.05),rgba(212,175,55,.15))"></div>
      <div style="position:absolute;top:16px;left:20px;font-size:.68em;color:rgba(212,175,55,.5);letter-spacing:.12em;text-transform:uppercase;font-weight:600;background:rgba(0,0,0,.4);padding:3px 10px;border-radius:20px;border:1px solid rgba(212,175,55,.15)">◈ Command Zone</div>
      <div style="position:absolute;top:16px;left:50%;transform:translateX(-50%);font-size:.68em;color:rgba(212,175,55,.5);letter-spacing:.12em;text-transform:uppercase;font-weight:600;background:rgba(0,0,0,.4);padding:3px 10px;border-radius:20px;border:1px solid rgba(212,175,55,.15);white-space:nowrap">◈ Research Zone</div>
      <div style="position:absolute;top:16px;right:20px;font-size:.68em;color:rgba(212,175,55,.5);letter-spacing:.12em;text-transform:uppercase;font-weight:600;background:rgba(0,0,0,.4);padding:3px 10px;border-radius:20px;border:1px solid rgba(212,175,55,.15)">◈ Sales Zone</div>
      <div class="office-desk-item" style="left:5%;bottom:100px"></div>
      <div class="office-desk-item" style="left:20%;bottom:100px"></div>
      <div class="office-desk-item" style="left:38%;bottom:100px"></div>
      <div class="office-desk-item" style="left:55%;bottom:100px"></div>
      <div class="office-desk-item" style="left:72%;bottom:100px"></div>
      <div class="office-desk-item" style="left:87%;bottom:100px"></div>
      <div id="office-agents" style="position:absolute;inset:0"></div>
    </div>
    <!-- Agent info bar -->
    <div style="height:60px;border-top:1px solid rgba(212,175,55,.12);background:var(--surface2);display:flex;align-items:center;padding:0 20px;gap:10px;overflow-x:auto;flex-shrink:0" id="office-agent-bar">
      <span style="font-size:.78em;color:var(--text-muted);white-space:nowrap">🤖 Click a robot to inspect →</span>
    </div>
  </div>
</div>

<div class="office-modal" id="office-modal">
  <div class="office-modal-card" style="border:1px solid rgba(212,175,55,.25);box-shadow:0 24px 64px rgba(0,0,0,.7),0 0 0 1px rgba(212,175,55,.08),0 0 60px rgba(212,175,55,.08)">
    <div class="card-header" style="margin-bottom:10px">
      <div class="card-title"><span style="color:var(--gold)">🧠</span> <span id="office-modal-title">Agent</span></div>
      <button class="btn btn-ghost btn-sm" onclick="closeOfficeModal()">✕ Close</button>
    </div>
    <div style="font-size:.86em;color:var(--text-secondary);margin-bottom:8px" id="office-modal-status">Status</div>
    <div class="office-progress"><div id="office-modal-progress"></div></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;font-size:.82em;color:var(--text-secondary)">
      <div><strong style="color:var(--text)">Time Busy:</strong> <span id="office-modal-time">-</span></div>
      <div><strong style="color:var(--text)">Last Action:</strong> <span id="office-modal-action">-</span></div>
    </div>
  </div>
</div>

<!-- ── AI Gateway Modal ── -->
<div class="office-modal" id="gateway-modal" onclick="if(event.target===this)closeGatewayModal()">
  <div class="office-modal-card" style="border:1px solid rgba(212,175,55,.3);box-shadow:0 24px 64px rgba(0,0,0,.8),0 0 60px rgba(212,175,55,.1);max-width:520px;width:92%">
    <div class="card-header" style="margin-bottom:14px">
      <div class="card-title"><span style="color:var(--gold)">📡</span> AI Gateway — Local Provider Setup</div>
      <button class="btn btn-ghost btn-sm" onclick="closeGatewayModal()">✕ Close</button>
    </div>
    <p style="font-size:.84em;color:var(--text-muted);margin-bottom:16px;line-height:1.6">
      AI Employee uses local AI models — no paid API required. Choose your preferred local AI backend below.
    </p>
    <!-- Provider cards -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      <div id="gw-card-ollama" onclick="selectGatewayProvider('ollama')" style="border:2px solid rgba(212,175,55,.5);border-radius:12px;padding:16px;cursor:pointer;background:rgba(212,175,55,.06);transition:all .2s">
        <div style="font-size:1.6em;margin-bottom:8px">🦙</div>
        <div style="font-weight:700;font-size:.9em;color:var(--text);margin-bottom:4px">Ollama</div>
        <div style="font-size:.76em;color:var(--text-muted);line-height:1.5">Free, private, runs on CPU/GPU. Best for general use.</div>
        <div id="gw-ollama-status" style="margin-top:8px;font-size:.73em;padding:3px 8px;border-radius:8px;display:inline-block;background:rgba(148,163,184,.1);color:var(--text-muted)">Checking…</div>
      </div>
      <div id="gw-card-nvidia" onclick="selectGatewayProvider('nvidia')" style="border:2px solid rgba(148,163,184,.2);border-radius:12px;padding:16px;cursor:pointer;background:rgba(148,163,184,.03);transition:all .2s">
        <div style="font-size:1.6em;margin-bottom:8px">🔷</div>
        <div style="font-weight:700;font-size:.9em;color:var(--text);margin-bottom:4px">NVIDIA NIM</div>
        <div style="font-size:.76em;color:var(--text-muted);line-height:1.5">Free tier, fast inference. Requires NVIDIA_API_KEY in settings.</div>
        <div id="gw-nvidia-status" style="margin-top:8px;font-size:.73em;padding:3px 8px;border-radius:8px;display:inline-block;background:rgba(148,163,184,.1);color:var(--text-muted)">Checking…</div>
      </div>
    </div>
    <!-- Ollama model picker (shown when Ollama selected) -->
    <div id="gw-ollama-section" style="margin-bottom:14px">
      <div style="font-size:.78em;font-weight:600;color:var(--gold);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Ollama Model</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap" id="gw-model-pills">
        <button class="btn btn-primary btn-sm gw-model-pill" onclick="setOllamaModel('llama3.2',this)">🦙 llama3.2 (default)</button>
        <button class="btn btn-ghost btn-sm gw-model-pill" onclick="setOllamaModel('gemma4',this)">💎 gemma4</button>
        <button class="btn btn-ghost btn-sm gw-model-pill" onclick="setOllamaModel('mistral',this)">🌟 mistral</button>
        <button class="btn btn-ghost btn-sm gw-model-pill" onclick="setOllamaModel('qwen2.5',this)">⚡ qwen2.5</button>
      </div>
      <div id="gw-pull-section" style="margin-top:10px;display:none">
        <div style="font-size:.78em;color:var(--warning);margin-bottom:6px">⚠️ Model not found locally. Pull it now?</div>
        <button class="btn btn-primary btn-sm" id="gw-pull-btn" onclick="pullOllamaModel()">⬇️ Pull Model (ollama pull)</button>
      </div>
    </div>
    <div id="gw-current-provider" style="font-size:.82em;padding:10px 14px;background:rgba(212,175,55,.06);border:1px solid rgba(212,175,55,.2);border-radius:8px;margin-bottom:14px">
      <span style="color:var(--text-muted)">Active provider: </span><span id="gw-provider-label" style="color:var(--gold);font-weight:700">–</span>
    </div>
    <button class="btn btn-primary" onclick="applyGatewayProvider()" style="width:100%;padding:12px">✓ Apply &amp; Save Gateway Settings</button>
    <div id="gw-result" style="margin-top:8px;font-size:.84em;min-height:20px"></div>
  </div>
</div>

<!-- ── Scheduler ── -->
<div id="tab-scheduler" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📅</div>
    <div><div class="page-header-title">Task Scheduler</div><div class="page-header-desc">Schedule recurring and one-time tasks for your agents. View your agenda, create schedules, and manage triggers.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Automation</span>
  </div>
  <div style="display:flex;gap:16px;height:calc(100vh - 175px)">
    <!-- Left: Agenda calendar -->
    <div style="width:320px;display:flex;flex-direction:column;gap:12px;flex-shrink:0">
      <div class="card" style="flex-shrink:0">
        <div class="card-header">
          <div class="card-title"><span style="color:var(--gold)">◈</span> Agenda</div>
          <div style="display:flex;gap:4px">
            <button class="btn btn-ghost btn-sm agenda-view-btn active" onclick="setAgendaView('month',this)">Month</button>
            <button class="btn btn-ghost btn-sm agenda-view-btn" onclick="setAgendaView('week',this)">Week</button>
            <button class="btn btn-ghost btn-sm agenda-view-btn" onclick="setAgendaView('day',this)">Day</button>
          </div>
        </div>
        <div id="agenda-nav" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <button class="btn btn-ghost btn-sm" onclick="agendaNav(-1)">&#8249;</button>
          <span id="agenda-period" style="font-weight:600;font-size:.9em;color:var(--gold)">–</span>
          <button class="btn btn-ghost btn-sm" onclick="agendaNav(1)">&#8250;</button>
        </div>
        <div id="agenda-grid" style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;font-size:.75em"></div>
      </div>
      <div class="card" style="flex:1;overflow-y:auto">
        <div class="card-title" style="margin-bottom:10px"><span style="color:var(--gold)">◈</span> <span id="agenda-day-label">All Tasks</span></div>
        <div id="schedule-list"><div class="empty"><div class="icon">📅</div><p>No tasks yet.</p></div></div>
      </div>
    </div>
    <!-- Right: New task form -->
    <div class="card" style="flex:1;overflow-y:auto">
      <div class="card-header">
        <div class="card-title"><span style="color:var(--gold)">◈</span> Schedule New Task</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="form-group" style="grid-column:1/-1">
          <label>Task Goal / Objective</label>
          <textarea id="sched-goal" rows="3" placeholder="What should this task achieve? e.g. Generate and send weekly performance report to all stakeholders…" class="field-full"></textarea>
        </div>
        <div class="form-group">
          <label>Task ID (unique)</label>
          <input id="sched-id" placeholder="auto-generated from label" oninput="this.dataset.manuallySet='1'"/>
        </div>
        <div class="form-group">
          <label>Label / Title</label>
          <input id="sched-label" placeholder="e.g. Weekly Performance Report" oninput="autoSchedId()"/>
        </div>
        <div class="form-group">
          <label>Priority</label>
          <select id="sched-priority">
            <option value="high">🔴 High</option>
            <option value="medium" selected>🟡 Medium</option>
            <option value="low">🟢 Low</option>
          </select>
        </div>
        <div class="form-group">
          <label>Action</label>
          <select id="sched-action" onchange="toggleSchedBot()">
            <option value="log">Log message</option>
            <option value="start_bot">Start agent</option>
            <option value="stop_bot">Stop agent</option>
            <option value="status_report">Send status report</option>
            <option value="run_task">Run AI task</option>
          </select>
        </div>
        <div class="form-group" id="sched-bot-row" style="display:none">
          <label>Agent name</label>
          <input id="sched-bot" placeholder="e.g. lead-hunter"/>
        </div>
        <div class="form-group">
          <label>Schedule type</label>
          <select id="sched-type" onchange="toggleSchedType()">
            <option value="interval">Every N minutes</option>
            <option value="daily">Daily at time (UTC)</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="once">Once (specific date/time)</option>
          </select>
        </div>
        <div class="form-group" id="sched-interval-row">
          <label>Interval (minutes)</label>
          <input id="sched-interval" type="number" value="60" min="1"/>
        </div>
        <div class="form-group" id="sched-daily-row" style="display:none">
          <label>Run at (HH:MM UTC)</label>
          <input id="sched-daily-time" placeholder="08:00"/>
        </div>
        <div class="form-group" id="sched-once-row" style="display:none">
          <label>Date &amp; Time (UTC)</label>
          <input id="sched-once-dt" type="datetime-local"/>
        </div>
        <div class="form-group" id="sched-weekly-row" style="display:none">
          <label>Day of Week</label>
          <select id="sched-weekly-day">
            <option>Monday</option><option>Tuesday</option><option>Wednesday</option>
            <option>Thursday</option><option>Friday</option><option>Saturday</option><option>Sunday</option>
          </select>
        </div>
        <div class="form-group" style="grid-column:1/-1">
          <label>Notes / Instructions</label>
          <input id="sched-msg" placeholder="Additional instructions or context for this task"/>
        </div>
      </div>
      <button class="btn btn-primary" onclick="addSchedule()" style="width:100%;margin-top:8px">◈ Schedule Task</button>
    </div>
  </div>
</div>

<!-- ── Workers ── -->
<div id="tab-workers" class="tab-content" style="width:100%;box-sizing:border-box">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">👷</div>
    <div><div class="page-header-title">Agent Teams</div><div class="page-header-desc">Bundle agents together with recurring tasks. Agent teams run on a schedule and always perform their assigned role automatically.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Workforce</span>
  </div>

  <!-- ── Quick Presets ── -->
  <div class="card card-ai" style="margin-bottom:18px">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">⚡</span> One-Click Power Presets</div>
      <span style="font-size:.78em;color:var(--text-muted)">Select agents → bundle → send to swarm</span>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Click a preset to instantly configure and launch a coordinated agent bundle. Then click <strong style="color:var(--gold)">Send Bundle to Swarm</strong> to deploy.</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:16px">
      <button onclick="applyAgentPreset('business_automator')" class="preset-card">
        <span class="pc-icon">🏢</span><span class="pc-name">Business Automator</span>
        <span class="pc-desc">Automate ops, admin & scheduling</span>
      </button>
      <button onclick="applyAgentPreset('money_printer')" class="preset-card">
        <span class="pc-icon">💰</span><span class="pc-name">Money Printer</span>
        <span class="pc-desc">Revenue, upsells & monetization</span>
      </button>
      <button onclick="applyAgentPreset('research_team')" class="preset-card">
        <span class="pc-icon">🔬</span><span class="pc-name">Research Team</span>
        <span class="pc-desc">Deep research & competitive intel</span>
      </button>
      <button onclick="applyAgentPreset('lead_gen_swarm')" class="preset-card">
        <span class="pc-icon">🎯</span><span class="pc-name">Lead Generation Swarm</span>
        <span class="pc-desc">Hunt, score & convert leads</span>
      </button>
      <button onclick="applyAgentPreset('content_empire')" class="preset-card">
        <span class="pc-icon">✍️</span><span class="pc-name">Content Empire</span>
        <span class="pc-desc">Content, SEO & brand building</span>
      </button>
      <button onclick="applyAgentPreset('ecom_powerhouse')" class="preset-card">
        <span class="pc-icon">🛒</span><span class="pc-name">E-com Powerhouse</span>
        <span class="pc-desc">Orders, inventory & fulfillment</span>
      </button>
      <button onclick="applyAgentPreset('outreach_machine')" class="preset-card">
        <span class="pc-icon">📣</span><span class="pc-name">Outreach Machine</span>
        <span class="pc-desc">Email, calls & social DMs</span>
      </button>
      <button onclick="applyAgentPreset('analytics_squad')" class="preset-card">
        <span class="pc-icon">📊</span><span class="pc-name">Analytics Squad</span>
        <span class="pc-desc">Reports, KPIs & insights</span>
      </button>
    </div>
    <!-- Bundle builder row -->
    <div style="background:rgba(0,0,0,.3);border:1px solid rgba(212,175,55,.15);border-radius:12px;padding:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:8px">
        <div>
          <div style="font-weight:700;color:var(--gold);font-size:.9em" id="swarm-preset-label">🎯 Select a preset or pick agents below</div>
          <div style="font-size:.78em;color:var(--text-muted)" id="swarm-agent-count-label">0 agents selected</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" onclick="swarmSelectAll()">All</button>
          <button class="btn btn-ghost btn-sm" onclick="swarmClearAll()">None</button>
          <button onclick="sendBundleToSwarm()" id="btn-send-bundle" class="btn-swarm">🚀 Send Bundle to Swarm</button>
        </div>
      </div>
      <div style="margin-bottom:8px">
        <input id="swarm-bundle-task" placeholder="Describe the mission for this bundle (optional)…" style="width:100%;box-sizing:border-box;font-size:.84em" />
      </div>
      <div id="swarm-agent-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:5px;max-height:220px;overflow-y:auto"></div>
      <div id="swarm-bundle-result" style="margin-top:8px;font-size:.84em"></div>
    </div>
  </div>

  <!-- Agent Team Bundles section -->
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">🏭</span> Agent Teams</div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" onclick="loadWorkers()">↻ Refresh</button>
        <button class="btn btn-primary btn-sm" onclick="openCreateWorker()">＋ New Agent Team</button>
      </div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      Bundle agents together with a recurring task. Agent teams run on a schedule and always perform their assigned role.
      <strong style="color:var(--accent)">Ecom Agent Team auto-preset</strong> is included below.
    </p>
    <div id="bundle-list"><div class="empty"><div class="icon">🏭</div><p>No agent teams yet. Click <strong>+ New Agent Team</strong> to create one.</p></div></div>
  </div>

  <!-- Create / Edit Agent Team form (inline, hidden by default) -->
  <div id="worker-form-card" class="card" style="display:none;border:2px solid var(--primary)">
    <div class="card-header">
      <div class="card-title"><span class="icon">✏️</span> <span id="worker-form-title">Create Agent Team</span></div>
      <button class="btn btn-ghost btn-sm" onclick="closeWorkerForm()">✕ Cancel</button>
    </div>
    <div class="grid2" style="gap:12px">
      <div>
        <div class="form-group">
          <label>Agent Team Name</label>
          <input id="wf-name" placeholder="e.g. Ecom Order Processor" />
        </div>
        <div class="form-group">
          <label>Recurring Task / Role Description</label>
          <textarea id="wf-task" rows="3" placeholder="e.g. Monitor new Shopify orders, validate payments, place Printful orders, send customer tracking emails"
            class="field-full"></textarea>
        </div>
        <div class="form-group">
          <label>Schedule</label>
          <select id="wf-schedule" style="width:100%">
            <option value="continuous">Continuous (always on)</option>
            <option value="hourly">Every hour</option>
            <option value="every6h">Every 6 hours</option>
            <option value="daily">Daily (2 AM)</option>
            <option value="3x_daily">3× daily (9 AM / 3 PM / 8 PM)</option>
            <option value="weekly">Weekly</option>
            <option value="manual">Manual trigger only</option>
          </select>
        </div>
        <div class="form-group">
          <label>Description (optional)</label>
          <input id="wf-desc" placeholder="Short description of what this agent team does" />
        </div>
      </div>
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <label style="font-weight:600">Assign Agents <span id="wf-agent-count" style="color:var(--primary)"></span></label>
          <div style="display:flex;gap:6px">
            <button class="btn btn-ghost btn-sm" onclick="wfSelectAll()">All</button>
            <button class="btn btn-ghost btn-sm" onclick="wfClearAll()">None</button>
          </div>
        </div>
        <div id="wf-agent-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:5px;max-height:300px;overflow-y:auto"></div>
      </div>
    </div>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="btn btn-success" onclick="saveWorkerBundle()" style="flex:1" id="wf-save-btn">💾 Save Agent Team</button>
      <button class="btn btn-ghost" onclick="presetEcomWorker()" title="Fill in the full ecom automation preset">🛒 Ecom Preset</button>
    </div>
    <div id="wf-save-result" style="margin-top:8px;font-size:.84em"></div>
    <input type="hidden" id="wf-editing-id" value="" />
  </div>

  <!-- Individual Agents section (raw start/stop controls) -->
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">👷</span> Individual Agents</div>
      <button class="btn btn-ghost btn-sm" onclick="loadWorkers()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      Start or stop individual agents. The problem-solver watchdog auto-restarts enabled agents if they crash.
    </p>
    <div id="worker-list"><div class="empty"><div class="icon">👷</div><p>Loading agents…</p></div></div>
  </div>
</div>

<!-- ── Improvements ── -->
<div id="tab-improvements" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">💡</div>
    <div><div class="page-header-title">AI Improvement Proposals</div><div class="page-header-desc">AI-generated improvement proposals for your system. Review, approve, or escalate to execution. No changes applied automatically.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">AI Insights</span>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">💡</span> Improvement Proposals</div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="loadImprovements()">↻ Refresh</button>
      </div>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:10px">
      AI-generated improvement proposals. Review, approve, or send to the main AI for immediate execution.
      <strong style="color:var(--warning)">No changes are applied automatically.</strong>
    </p>
    <!-- Status filter -->
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px" id="improv-status-pills">
      <button class="btn btn-primary btn-sm improv-pill active" onclick="filterImprovements('all',this)" style="background:linear-gradient(135deg,var(--primary-dark),var(--primary));color:#000;border:none">All</button>
      <button class="btn btn-ghost btn-sm improv-pill" onclick="filterImprovements('pending',this)">⏳ Pending</button>
      <button class="btn btn-ghost btn-sm improv-pill" onclick="filterImprovements('in_progress',this)">🔄 In Progress</button>
      <button class="btn btn-ghost btn-sm improv-pill" onclick="filterImprovements('approved',this)">✅ Approved</button>
      <button class="btn btn-ghost btn-sm improv-pill" onclick="filterImprovements('completed',this)">🏆 Completed</button>
      <button class="btn btn-ghost btn-sm improv-pill" onclick="filterImprovements('rejected',this)">🚫 Rejected</button>
    </div>
    <!-- Priority filter -->
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px" id="improv-priority-pills">
      <span style="font-size:.78em;color:var(--text-muted);align-self:center;font-weight:600">Priority:</span>
      <button class="btn btn-ghost btn-sm improv-pri-pill active" onclick="filterImprovPriority('all',this)">All</button>
      <button class="btn btn-ghost btn-sm improv-pri-pill" onclick="filterImprovPriority('critical',this)" style="border-color:rgba(239,68,68,.4);color:#ef4444">🔴 Critical</button>
      <button class="btn btn-ghost btn-sm improv-pri-pill" onclick="filterImprovPriority('high',this)" style="border-color:rgba(245,158,11,.4);color:#f59e0b">🟠 High</button>
      <button class="btn btn-ghost btn-sm improv-pri-pill" onclick="filterImprovPriority('medium',this)" style="border-color:rgba(234,179,8,.4);color:#eab308">🟡 Medium</button>
      <button class="btn btn-ghost btn-sm improv-pri-pill" onclick="filterImprovPriority('low',this)" style="border-color:rgba(16,185,129,.4);color:#10b981">🟢 Low</button>
    </div>
    <div id="improvement-list"><div class="empty"><div class="icon">💡</div><p>No proposals yet. The discovery agent will add proposals over time.</p></div></div>
  </div>
</div>

<!-- ── Budget ── -->
<div id="tab-budget" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">💰</div>
    <div><div class="page-header-title">Budget & Cost Management</div><div class="page-header-desc">Track monthly AI compute spend per agent. Set hard caps, monitor warnings, and record usage manually.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Cost Control</span>
  </div>
  <div class="grid-stat" style="margin-bottom:16px">
    <div class="stat-card"><div class="stat-icon green">💰</div><div class="stat-body"><div class="val" id="bud-total-spent">–</div><div class="lbl">Total Spent (month)</div></div></div>
    <div class="stat-card"><div class="stat-icon yellow">⚠️</div><div class="stat-body"><div class="val" id="bud-agents-warn">–</div><div class="lbl">Agents at Warning</div></div></div>
    <div class="stat-card"><div class="stat-icon red">🛑</div><div class="stat-body"><div class="val" id="bud-agents-exceeded">–</div><div class="lbl">Agents Exceeded</div></div></div>
    <div class="stat-card"><div class="stat-icon cyan">📊</div><div class="stat-body"><div class="val" id="bud-agents-tracked">–</div><div class="lbl">Agents Tracked</div></div></div>
  </div>
  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">💰</span> Agent Budgets</div>
        <button class="btn btn-ghost btn-sm" onclick="loadBudget()">↻ Refresh</button>
      </div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">Monthly USD budget per agent. 80% = warning, 100% = hard stop.</p>
      <div id="budget-agents-list"><div class="empty"><div class="icon">💰</div><p>Loading budget data…</p></div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">⚙️</span> Set Agent Budget</div></div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Configure the monthly budget cap for any agent.</p>
      <div class="form-group"><label>Agent ID</label><input id="bud-agent-id" placeholder="e.g. ceo, cto, marketing-agent"/></div>
      <div class="form-group"><label>Monthly Budget (USD)</label><input id="bud-amount" type="number" min="0.01" step="0.01" placeholder="e.g. 10.00"/></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="setBudget()">💾 Set Budget</button>
        <button class="btn btn-ghost btn-sm" onclick="resetBudget()">↺ Reset Usage</button>
      </div>
    </div>
  </div>
  <div class="card" style="margin-top:16px">
    <div class="card-header"><div class="card-title"><span class="icon">📈</span> Record Usage Manually</div></div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Manually record token usage (useful for testing or manual reconciliation).</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
      <div class="form-group" style="flex:1;min-width:120px"><label>Agent ID</label><input id="bud-rec-agent" placeholder="agent-id"/></div>
      <div class="form-group" style="flex:1;min-width:120px"><label>Model</label><input id="bud-rec-model" placeholder="gpt-4o" value="gpt-4o"/></div>
      <div class="form-group" style="flex:0 0 90px"><label>Input Tokens</label><input id="bud-rec-in" type="number" min="0" value="0"/></div>
      <div class="form-group" style="flex:0 0 90px"><label>Output Tokens</label><input id="bud-rec-out" type="number" min="0" value="0"/></div>
      <button class="btn btn-primary" style="margin-bottom:18px" onclick="recordBudgetUsage()">📥 Record</button>
    </div>
  </div>
</div>

<!-- ── Org Chart ── -->
<div id="tab-org" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🏢</div>
    <div><div class="page-header-title">Org Chart & Agent Hierarchy</div><div class="page-header-desc">Visual hierarchy of roles and reporting lines. Assign agents to roles for structured delegation and task routing.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Agent Structure</span>
  </div>
  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🏢</span> Org Chart</div>
        <button class="btn btn-ghost btn-sm" onclick="loadOrg()">↻ Refresh</button>
      </div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">Visual hierarchy of roles and reporting lines. Assign agents to roles for delegation.</p>
      <div id="org-chart-tree"><div class="empty"><div class="icon">🏢</div><p>Loading org chart…</p></div></div>
    </div>
    <div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Add / Edit Role</div></div>
        <div class="form-group"><label>Role ID</label><input id="org-role-id" placeholder="e.g. cto"/></div>
        <div class="form-group"><label>Title</label><input id="org-role-title" placeholder="e.g. Chief Technology Officer"/></div>
        <div class="form-group"><label>Description</label><input id="org-role-desc" placeholder="Role responsibilities"/></div>
        <div class="form-group"><label>Reports To (Role ID)</label><input id="org-role-reports" placeholder="e.g. ceo (leave empty for top)"/></div>
        <div class="form-group"><label>Assign Agent ID</label><input id="org-role-agent" placeholder="e.g. engineering-assistant"/></div>
        <button class="btn btn-primary" onclick="upsertOrgRole()">💾 Save Role</button>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-header"><div class="card-title"><span class="icon">🤝</span> Delegate Task</div></div>
        <p style="color:var(--text-muted);font-size:.83em;margin-bottom:12px">Route a task from one role to another through the org chart.</p>
        <div class="form-group"><label>From Role</label><input id="org-del-from" placeholder="ceo"/></div>
        <div class="form-group"><label>To Role</label><input id="org-del-to" placeholder="cto"/></div>
        <div class="form-group"><label>Task</label><input id="org-del-task" placeholder="Build the MVP architecture"/></div>
        <button class="btn btn-primary" onclick="delegateOrgTask()">🚀 Delegate</button>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-header">
          <div class="card-title"><span class="icon">🔌</span> BYOA Adapters</div>
          <button class="btn btn-ghost btn-sm" onclick="loadOrgAdapters()">↻ Refresh</button>
        </div>
        <div id="org-adapters-list" style="font-size:.84em"><div class="empty"><div class="icon">🔌</div><p>No adapters registered.</p></div></div>
        <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
          <div class="form-group" style="flex:1;min-width:110px"><label>Adapter ID</label><input id="org-adp-id" placeholder="my-bot"/></div>
          <div class="form-group" style="flex:2;min-width:160px"><label>Name</label><input id="org-adp-name" placeholder="My Custom Bot"/></div>
          <button class="btn btn-primary" style="margin-bottom:18px" onclick="registerOrgAdapter()">➕ Register</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ── Goals ── -->
<div id="tab-goals" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🎯</div>
    <div><div class="page-header-title">Goals & Company Mission</div><div class="page-header-desc">Set OKR-style goals, define the company mission, and track strategic objectives across your AI team.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Strategic Layer</span>
  </div>
  <div class="card" style="margin-bottom:16px;background:linear-gradient(135deg,rgba(234,88,12,.08),rgba(251,146,60,.04));border-color:rgba(251,146,60,.3)">
    <div class="card-header">
      <div class="card-title"><span class="icon">💬</span> CEO Chat</div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
      Send a direct directive to the top-level CEO agent. Context flows from company mission down through the org chart.
    </p>
    <div id="ceo-chat-log" style="background:var(--bg-deep,#0d1117);border-radius:6px;padding:12px;min-height:80px;max-height:200px;overflow-y:auto;font-size:.83em;margin-bottom:12px;color:#c9d1d9;line-height:1.7">
      <span style="color:#6b7280">CEO is ready. Send a directive below.</span>
    </div>
    <div style="display:flex;gap:8px">
      <input id="ceo-chat-input" placeholder='e.g. "Prioritize the MVP launch this week"' style="flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);padding:8px 12px;font-family:inherit"
        onkeydown="if(event.key==='Enter')sendCEOMessage()"/>
      <button class="btn btn-primary" onclick="sendCEOMessage()" id="ceo-send-btn">📨 Send</button>
    </div>
    <div id="ceo-chat-status" style="font-size:.78em;color:var(--text-muted);margin-top:6px"></div>
  </div>
  <div class="card" style="margin-bottom:16px">
    <div class="card-header">
      <div class="card-title"><span class="icon">🎯</span> Company Mission</div>
      <button class="btn btn-ghost btn-sm" onclick="loadGoals()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
      The company mission is injected into every agent prompt so agents always know <em>what</em> to do and <em>why</em>.
    </p>
    <div id="goals-mission-display" style="background:var(--surface2);border-radius:var(--radius-sm);padding:12px;margin-bottom:14px;font-size:.9em;color:var(--text-secondary);min-height:40px">
      <em style="color:var(--text-muted)">No mission set yet. Set one below.</em>
    </div>
    <div class="form-group"><label>Mission Statement</label><textarea id="goals-mission-input" rows="2" class="field-full" placeholder="e.g. Build the #1 AI note-taking app to $1M MRR"></textarea></div>
    <div class="form-group"><label>Vision (optional)</label><input id="goals-vision-input" placeholder="Long-term company vision"/></div>
    <button class="btn btn-primary" onclick="saveCompanyMission()">💾 Save Mission</button>
  </div>
</div>

<!-- ── Tickets ── -->
<div id="tab-tickets" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🎫</div>
    <div><div class="page-header-title">Tickets & Task Tracker</div><div class="page-header-desc">Track system tickets, feature requests, and AI tasks. Filter by status, assign agents, and monitor progress.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Issue Tracker</span>
  </div>
  <div class="grid-stat" style="margin-bottom:16px">
    <div class="stat-card"><div class="stat-icon blue">🎫</div><div class="stat-body"><div class="val" id="tkt-total">–</div><div class="lbl">Total Tickets</div></div></div>
    <div class="stat-card"><div class="stat-icon yellow">⏳</div><div class="stat-body"><div class="val" id="tkt-open">–</div><div class="lbl">Open</div></div></div>
    <div class="stat-card"><div class="stat-icon cyan">▶️</div><div class="stat-body"><div class="val" id="tkt-inprog">–</div><div class="lbl">In Progress</div></div></div>
    <div class="stat-card"><div class="stat-icon green">✅</div><div class="stat-body"><div class="val" id="tkt-done">–</div><div class="lbl">Done</div></div></div>
  </div>
  <div class="grid2" style="align-items:start">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🎫</span> Tickets</div>
        <div style="display:flex;gap:6px">
          <select id="tkt-filter-status" style="font-size:.8em" onchange="loadTickets()">
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="blocked">Blocked</option>
            <option value="done">Done</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button class="btn btn-ghost btn-sm" onclick="loadTickets()">↻</button>
        </div>
      </div>
      <div id="tickets-list"><div class="empty"><div class="icon">🎫</div><p>No tickets yet.</p></div></div>
    </div>
    <div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Create Ticket</div></div>
        <div class="form-group"><label>Title</label><input id="tkt-new-title" placeholder="Describe the task"/></div>
        <div class="form-group"><label>Description (optional)</label><textarea id="tkt-new-desc" rows="2" class="field-full" placeholder="Details…"></textarea></div>
        <div class="form-group"><label>Priority</label>
          <select id="tkt-new-priority" >
            <option value="high">🔴 High</option>
            <option value="medium" selected>🟡 Medium</option>
            <option value="low">🟢 Low</option>
          </select>
        </div>
        <div class="form-group"><label>Assign Agent (optional)</label><input id="tkt-new-agent" placeholder="e.g. engineering-assistant"/></div>
        <button class="btn btn-primary" onclick="createTicket()">➕ Create Ticket</button>
      </div>
      <div class="card" style="margin-top:14px" id="tkt-detail-card" style="display:none">
        <div class="card-header">
          <div class="card-title"><span class="icon">📋</span> Ticket Detail</div>
          <button class="btn btn-ghost btn-sm" onclick="document.getElementById('tkt-detail-card').style.display='none'">✕</button>
        </div>
        <div id="tkt-detail-body"></div>
        <div class="form-group" style="margin-top:12px"><label>Add Comment</label>
          <div style="display:flex;gap:8px">
            <input id="tkt-comment-input" placeholder="Write a comment…" style="flex:1"/>
            <button class="btn btn-primary" onclick="addTicketComment()">💬 Post</button>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div class="card" style="margin-top:16px">
    <div class="card-header">
      <div class="card-title"><span class="icon">📋</span> Audit Trail</div>
      <button class="btn btn-ghost btn-sm" onclick="loadTicketAudit()">↻ Refresh</button>
    </div>
    <div id="tickets-audit"><div class="empty"><div class="icon">📋</div><p>No audit events yet.</p></div></div>
  </div>
</div>

<!-- ── Boardroom (Governance) ── -->
<div id="tab-boardroom" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🛡️</div>
    <div><div class="page-header-title">Boardroom & Governance</div><div class="page-header-desc">High-level approval workflows, governance decisions, and strategic oversight. Human-in-the-loop for critical actions.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Governance</span>
  </div>
  <div class="grid-stat" style="margin-bottom:16px">
    <div class="stat-card"><div class="stat-icon yellow">⏳</div><div class="stat-body"><div class="val" id="gov-pending">–</div><div class="lbl">Pending Approvals</div></div></div>
    <div class="stat-card"><div class="stat-icon green">✅</div><div class="stat-body"><div class="val" id="gov-approved">–</div><div class="lbl">Approved</div></div></div>
    <div class="stat-card"><div class="stat-icon red">🚫</div><div class="stat-body"><div class="val" id="gov-rejected">–</div><div class="lbl">Rejected</div></div></div>
    <div class="stat-card"><div class="stat-icon cyan">📋</div><div class="stat-body"><div class="val" id="gov-total">–</div><div class="lbl">Total Actions</div></div></div>
  </div>

  <div id="gov-pending-banner" style="display:none;align-items:center;gap:12px;background:linear-gradient(135deg,rgba(239,68,68,.15),rgba(245,158,11,.1));border:1px solid rgba(239,68,68,.5);border-radius:var(--radius);padding:14px 18px;margin-bottom:14px;font-size:.88em;color:#f87171;font-weight:600;animation:blink 1.5s infinite"></div>

  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">⏳</span> Pending Board Approvals</div>
        <button class="btn btn-ghost btn-sm" onclick="loadBoardroom()">↻ Refresh</button>
      </div>
      <div id="gov-pending-list"><div class="empty"><div class="icon">✅</div><p>No pending approvals.</p></div></div>
    </div>
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🤖</span> Agent Controls</div>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">As the board, you can pause, resume, or terminate any agent at any time.</p>
        <div style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap">
          <div class="form-group" style="flex:1;min-width:140px"><label>Agent ID</label><input id="gov-agent-ctrl-id" placeholder="e.g. marketing-agent"/></div>
          <button class="btn btn-warning btn-sm" style="margin-bottom:18px" onclick="govPauseAgent()">⏸ Pause</button>
          <button class="btn btn-success btn-sm" style="margin-bottom:18px" onclick="govResumeAgent()">▶️ Resume</button>
          <button class="btn btn-danger btn-sm" style="margin-bottom:18px" onclick="govTerminateAgent()">⛔ Terminate</button>
        </div>
        <div id="gov-agent-status-display" style="font-size:.83em;color:var(--text-muted)"></div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-header"><div class="card-title"><span class="icon">🧪</span> Submit Test Action</div></div>
        <p style="color:var(--text-muted);font-size:.83em;margin-bottom:10px">Test the approval gate — submit an action on behalf of an agent.</p>
        <div class="form-group"><label>Agent ID</label><input id="gov-test-agent" placeholder="my-agent"/></div>
        <div class="form-group"><label>Action</label><input id="gov-test-action" placeholder="e.g. send_email_blast"/></div>
        <div class="form-group"><label>Description</label><input id="gov-test-desc" placeholder="Send 1000 emails to customer list"/></div>
        <div class="form-group"><label>Risk Level</label>
          <select id="gov-test-risk" >
            <option value="low">🟢 Low (auto-approved)</option>
            <option value="medium" selected>🟡 Medium</option>
            <option value="high">🔴 High</option>
            <option value="critical">🔥 Critical</option>
          </select>
        </div>
        <button class="btn btn-primary" onclick="govTestAction()">🧪 Submit Action</button>
      </div>
    </div>
  </div>
  <div class="card" style="margin-top:16px">
    <div class="card-header">
      <div class="card-title"><span class="icon">📋</span> Governance Audit Trail</div>
      <button class="btn btn-ghost btn-sm" onclick="loadBoardroom()">↻ Refresh</button>
    </div>
    <div id="gov-audit-list"><div class="empty"><div class="icon">📋</div><p>No audit events yet.</p></div></div>
  </div>
</div>

<!-- ── Companies ── -->
<div id="tab-companies" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🏗️</div>
    <div><div class="page-header-title">Multi-Company Manager</div><div class="page-header-desc">One deployment, many companies. Complete data isolation with a single control plane for your entire portfolio.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Portfolio CRM</span>
  </div>
  <div class="card" style="margin-bottom:16px">
    <div class="card-header">
      <div class="card-title"><span class="icon">🏗️</span> Multi-Company Manager</div>
      <button class="btn btn-ghost btn-sm" onclick="loadCompanies()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
      One deployment, many companies. Complete data isolation and one control plane for your portfolio.
    </p>
    <div id="companies-active-banner" style="background:linear-gradient(135deg,rgba(16,185,129,.1),rgba(52,211,153,.05));border:1px solid rgba(52,211,153,.3);border-radius:var(--radius-sm);padding:10px 14px;margin-bottom:12px;font-size:.88em;color:var(--success);display:none"></div>
    <div id="companies-list"><div class="empty"><div class="icon">🏗️</div><p>No companies yet. Create one below.</p></div></div>
  </div>
  <div class="grid2">
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">➕</span> Create Company</div></div>
      <div class="form-group"><label>Company Name</label><input id="co-new-name" placeholder="e.g. Acme AI Inc."/></div>
      <div class="form-group"><label>Mission (optional)</label><input id="co-new-mission" placeholder="Build the #1 AI assistant"/></div>
      <div class="form-group"><label>Description (optional)</label><input id="co-new-desc" placeholder="Brief description"/></div>
      <button class="btn btn-primary" onclick="createCompany()">🏗️ Create Company</button>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">📦</span> Export / Import</div></div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Export a company config (secrets scrubbed) or import a template.</p>
      <div class="form-group"><label>Company ID to Export</label>
        <div style="display:flex;gap:8px">
          <input id="co-export-id" placeholder="company-id" style="flex:1"/>
          <button class="btn btn-ghost" onclick="exportCompany()">📤 Export</button>
        </div>
      </div>
      <div class="form-group"><label>Import Template (JSON)</label>
        <textarea id="co-import-json" rows="4" class="field-full" placeholder='{"company": {"name": "My Company"}, ...}'></textarea>
      </div>
      <button class="btn btn-primary" onclick="importCompany()">📥 Import</button>
    </div>
  </div>
</div>

<!-- ── Outputs (Artifacts + Sessions) ── -->
<div id="tab-artifacts" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📦</div>
    <div><div class="page-header-title">Artifacts & Generated Content</div><div class="page-header-desc">Browse and manage all files, documents, and code generated by your AI agents. Filter, preview, and deploy artifacts.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Output Library</span>
  </div>

  <!-- ── Sub-tab navigation (Artifacts / Sessions) ── -->
  <div style="display:flex;gap:6px;margin-bottom:16px">
    <button class="outputs-tab-btn btn btn-primary btn-sm active" onclick="switchOutputTab('artifacts',this)">📦 Artifacts</button>
    <button class="outputs-tab-btn btn btn-ghost btn-sm" onclick="switchOutputTab('sessions',this)">💾 Sessions</button>
  </div>

  <!-- ── Artifacts panel ── -->
  <div id="outputs-artifacts-panel">
    <div class="grid-stat" style="margin-bottom:16px">
      <div class="stat-card"><div class="stat-icon yellow">📦</div><div class="stat-body"><div class="val" id="art-total">–</div><div class="lbl">Total Artifacts</div></div></div>
      <div class="stat-card"><div class="stat-icon cyan">📝</div><div class="stat-body"><div class="val" id="art-drafts">–</div><div class="lbl">Drafts</div></div></div>
      <div class="stat-card"><div class="stat-icon green">🚀</div><div class="stat-body"><div class="val" id="art-deployed">–</div><div class="lbl">Deployed</div></div></div>
      <div class="stat-card"><div class="stat-icon blue">✅</div><div class="stat-body"><div class="val" id="art-approved">–</div><div class="lbl">Approved</div></div></div>
    </div>
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">📦</span> Artifacts</div>
          <div style="display:flex;gap:6px">
            <select id="art-filter-type" style="font-size:.8em" onchange="loadArtifacts()">
              <option value="">All Types</option>
              <option value="code">Code</option>
              <option value="report">Report</option>
              <option value="campaign">Campaign</option>
              <option value="business_plan">Business Plan</option>
              <option value="config">Config</option>
              <option value="other">Other</option>
            </select>
            <button class="btn btn-ghost btn-sm" onclick="loadArtifacts()">↻</button>
          </div>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:10px">Files, reports, code, and plans produced by agents. Review, approve, and deploy them here.</p>
        <div id="artifacts-list"><div class="empty"><div class="icon">📦</div><p>No artifacts yet. Create a task to generate artifacts.</p></div></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Create Artifact</div></div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">Manually create an artifact from existing content.</p>
        <div class="form-group"><label>Title</label><input id="art-new-title" placeholder="e.g. Marketing Plan Q2"/></div>
        <div class="form-group"><label>Type</label>
          <select id="art-new-type" >
            <option value="report">Report</option>
            <option value="code">Code</option>
            <option value="campaign">Campaign</option>
            <option value="business_plan">Business Plan</option>
            <option value="config">Config</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div class="form-group"><label>Content</label>
          <textarea id="art-new-content" rows="5" class="field-full" placeholder="Artifact content…"></textarea>
        </div>
        <button class="btn btn-primary" onclick="createArtifact()">📦 Create Artifact</button>
      </div>
    </div>
    <div class="card" style="margin-top:16px;display:none" id="art-detail-card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🔍</span> Artifact Detail</div>
        <button class="btn btn-ghost btn-sm" onclick="document.getElementById('art-detail-card').style.display='none'">✕ Close</button>
      </div>
      <div id="art-detail-body"></div>
    </div>
  </div>

  <!-- ── Sessions section (integrated into Outputs) ── -->
  <div id="outputs-sessions-panel" style="margin-top:24px;border-top:1px solid var(--border);padding-top:20px;display:none">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
      <div>
        <h3 style="font-size:1em;font-weight:700;color:var(--text);margin:0 0 2px">💾 AI Sessions</h3>
        <p style="font-size:.8em;color:var(--text-muted);margin:0">Persistent sessions let agents resume exactly where they left off.</p>
      </div>
      <button class="btn btn-ghost btn-sm" onclick="loadSessions()">↻ Refresh</button>
    </div>
    <div class="grid-stat" style="margin-bottom:16px">
      <div class="stat-card"><div class="stat-icon cyan">💾</div><div class="stat-body"><div class="val" id="ses-total">–</div><div class="lbl">Total Sessions</div></div></div>
      <div class="stat-card"><div class="stat-icon green">▶️</div><div class="stat-body"><div class="val" id="ses-active">–</div><div class="lbl">Active</div></div></div>
      <div class="stat-card"><div class="stat-icon yellow">⏸</div><div class="stat-body"><div class="val" id="ses-paused">–</div><div class="lbl">Paused</div></div></div>
      <div class="stat-card"><div class="stat-icon blue">✅</div><div class="stat-body"><div class="val" id="ses-completed">–</div><div class="lbl">Completed</div></div></div>
    </div>
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">💾</span> Persistent Sessions</div>
          <button class="btn btn-ghost btn-sm" onclick="loadSessions()">↻ Refresh</button>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
          Sessions persist across reboots. Agents resume their exact task context rather than starting from scratch.
        </p>
        <div id="sessions-list"><div class="empty"><div class="icon">💾</div><p>No sessions yet. Agents create sessions automatically when tasks start.</p></div></div>
      </div>
      <div>
        <div class="card">
          <div class="card-header"><div class="card-title"><span class="icon">➕</span> Create Session</div></div>
          <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">Manually create a persistent session for an agent with a specific goal and context.</p>
          <div class="form-group"><label>Agent ID</label><input id="ses-new-agent" placeholder="e.g. engineering-assistant"/></div>
          <div class="form-group"><label>Title</label><input id="ses-new-title" placeholder="e.g. MVP feature development"/></div>
          <div class="form-group"><label>Initial Context (JSON)</label>
            <textarea id="ses-new-ctx" rows="3" class="field-full" placeholder='{"goal": "Build login feature", "stack": "React + FastAPI"}'></textarea>
          </div>
          <button class="btn btn-primary" onclick="createSession()">💾 Create Session</button>
        </div>
        <div class="card" style="margin-top:14px" id="ses-detail-card">
          <div class="card-header"><div class="card-title"><span class="icon">📋</span> Session Detail</div></div>
          <div id="ses-detail-body"><div class="empty"><p>Click a session to view details and checkpoints.</p></div></div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ── Finance / Invoicing ── -->
<div id="tab-invoicing" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🧾</div>
    <div><div class="page-header-title">Finance & Invoicing</div><div class="page-header-desc">Create invoices, track expenses, and view your live P&amp;L report.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Finance</span>
  </div>
  <div style="display:flex;gap:6px;margin-bottom:16px">
    <button class="fi-tab-btn btn btn-primary btn-sm active" onclick="switchFinanceTab('invoices',this)">🧾 Invoices</button>
    <button class="fi-tab-btn btn btn-ghost btn-sm" onclick="switchFinanceTab('expenses',this)">💸 Expenses</button>
    <button class="fi-tab-btn btn btn-ghost btn-sm" onclick="switchFinanceTab('pl',this)">📊 P&amp;L</button>
  </div>

  <!-- Invoices -->
  <div id="fi-invoices-panel">
    <div class="grid-stat" style="margin-bottom:16px">
      <div class="stat-card"><div class="stat-icon green">💰</div><div class="stat-body"><div class="val" id="fi-revenue">–</div><div class="lbl">Revenue</div></div></div>
      <div class="stat-card"><div class="stat-icon yellow">⏳</div><div class="stat-body"><div class="val" id="fi-pending">–</div><div class="lbl">Pending</div></div></div>
      <div class="stat-card"><div class="stat-icon blue">🧾</div><div class="stat-body"><div class="val" id="fi-total-inv">–</div><div class="lbl">Invoices</div></div></div>
      <div class="stat-card"><div class="stat-icon red">⚠️</div><div class="stat-body"><div class="val" id="fi-overdue">–</div><div class="lbl">Overdue</div></div></div>
    </div>
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">🧾</span> Invoices</div><button class="btn btn-ghost btn-sm" onclick="loadInvoices()">↻</button></div>
        <div id="fi-invoice-list"><div class="empty"><div class="icon">🧾</div><p>No invoices yet.</p></div></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> New Invoice</div></div>
        <div class="form-group"><label>Client Name</label><input id="fi-client" placeholder="Acme Corp"/></div>
        <div class="form-group"><label>Client Email</label><input id="fi-client-email" placeholder="billing@acme.com"/></div>
        <div class="form-group"><label>Subtotal ($)</label><input id="fi-subtotal" type="number" placeholder="2500"/></div>
        <div class="form-group"><label>Tax Rate (%)</label><input id="fi-tax" type="number" placeholder="10"/></div>
        <div class="form-group"><label>Due Date</label><input id="fi-due" type="date"/></div>
        <div class="form-group"><label>Notes</label><input id="fi-notes" placeholder="Payment terms…"/></div>
        <button class="btn btn-primary" onclick="createInvoice()">🧾 Create Invoice</button>
      </div>
    </div>
  </div>

  <!-- Expenses -->
  <div id="fi-expenses-panel" style="display:none">
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">💸</span> Expenses</div><button class="btn btn-ghost btn-sm" onclick="loadExpenses()">↻</button></div>
        <div id="fi-expense-list"><div class="empty"><div class="icon">💸</div><p>No expenses yet.</p></div></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Log Expense</div></div>
        <div class="form-group"><label>Description</label><input id="fi-exp-desc" placeholder="SaaS subscription…"/></div>
        <div class="form-group"><label>Amount ($)</label><input id="fi-exp-amount" type="number" placeholder="99"/></div>
        <div class="form-group"><label>Category</label>
          <select id="fi-exp-cat" >
            <option value="software">Software</option><option value="marketing">Marketing</option>
            <option value="payroll">Payroll</option><option value="office">Office</option>
            <option value="travel">Travel</option><option value="other">Other</option>
          </select>
        </div>
        <div class="form-group"><label>Date</label><input id="fi-exp-date" type="date"/></div>
        <button class="btn btn-primary" onclick="logExpense()">💸 Log Expense</button>
      </div>
    </div>
  </div>

  <!-- P&L -->
  <div id="fi-pl-panel" style="display:none">
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">📊</span> Profit &amp; Loss Report</div>
        <button class="btn btn-ghost btn-sm" onclick="loadPL()">↻ Refresh</button>
      </div>
      <div id="fi-pl-body"><div class="empty"><p>Click Refresh to generate your P&amp;L report.</p></div></div>
    </div>
  </div>
</div>

<!-- ── Analytics ── -->
<div id="tab-analytics-bi" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📊</div>
    <div><div class="page-header-title">Analytics &amp; Insights</div><div class="page-header-desc">Business intelligence dashboard — unified KPIs, AI recommendations, and trends across all modules.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Intelligence</span>
  </div>
  <div style="display:flex;gap:8px;margin-bottom:16px">
    <button class="btn btn-primary" onclick="loadAnalyticsOverview()">↻ Refresh Overview</button>
    <button class="btn btn-ghost" onclick="loadRecommendations()">💡 Get Recommendations</button>
  </div>
  <div class="grid-stat" id="analytics-stats" style="margin-bottom:16px">
    <div class="stat-card"><div class="stat-icon blue">👥</div><div class="stat-body"><div class="val" id="an-leads">–</div><div class="lbl">Total Leads</div></div></div>
    <div class="stat-card"><div class="stat-icon green">💰</div><div class="stat-body"><div class="val" id="an-revenue">–</div><div class="lbl">Revenue</div></div></div>
    <div class="stat-card"><div class="stat-icon cyan">📧</div><div class="stat-body"><div class="val" id="an-open-rate">–</div><div class="lbl">Email Open Rate</div></div></div>
    <div class="stat-card"><div class="stat-icon pink">📱</div><div class="stat-body"><div class="val" id="an-posts">–</div><div class="lbl">Published Posts</div></div></div>
  </div>
  <div class="grid2" style="align-items:start">
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">💡</span> AI Recommendations</div></div>
      <div id="an-recommendations"><div class="empty"><p>Click "Get Recommendations" to see AI-powered insights.</p></div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">📈</span> Module Breakdown</div></div>
      <div id="an-breakdown"><div class="empty"><p>Click "Refresh Overview" to load data.</p></div></div>
    </div>
  </div>
</div>

<!-- ── Workflow Builder ── -->
<div id="tab-workflows" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">⚙️</div>
    <div><div class="page-header-title">Workflow Builder</div><div class="page-header-desc">No-code automation editor — create trigger → condition → action workflows that run automatically.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Automation</span>
  </div>
  <div class="grid2" style="align-items:start">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">⚙️</span> Workflows</div>
        <button class="btn btn-ghost btn-sm" onclick="loadWorkflows()">↻</button>
      </div>
      <div id="wf-list"><div class="empty"><div class="icon">⚙️</div><p>No workflows yet.</p></div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">➕</span> New Workflow</div></div>
      <div class="form-group"><label>Workflow Name</label><input id="wf-name" placeholder="Welcome new leads"/></div>
      <div class="form-group"><label>Description</label><input id="wf-desc" placeholder="Auto-send welcome email when new lead added"/></div>
      <div class="form-group"><label>Trigger</label>
        <select id="wf-trigger" >
          <option value="manual">Manual</option><option value="new_lead">New Lead Added</option>
          <option value="email_opened">Email Opened</option><option value="deal_stage_change">Deal Stage Change</option>
          <option value="invoice_paid">Invoice Paid</option><option value="schedule">Schedule</option>
          <option value="webhook">Webhook</option>
        </select>
      </div>
      <div class="form-group"><label>Actions (one per line)</label>
        <textarea id="wf-steps" rows="4" class="field-full" placeholder="send_email: Welcome email&#10;wait: 1 day&#10;create_task: Follow up call"></textarea>
      </div>
      <button class="btn btn-primary" onclick="createWorkflow()">⚙️ Create Workflow</button>
    </div>
  </div>
  <div class="card" style="margin-top:16px">
    <div class="card-header"><div class="card-title"><span class="icon">📋</span> Recent Runs</div>
      <button class="btn btn-ghost btn-sm" onclick="loadWorkflowRuns()">↻</button>
    </div>
    <div id="wf-runs-list"><div class="empty"><p>No runs yet.</p></div></div>
  </div>
</div>

<!-- ── Team Management ── -->
<div id="tab-team" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">👥</div>
    <div><div class="page-header-title">Team Management</div><div class="page-header-desc">Invite team members, assign roles, and manage access permissions across your AI Employee workspace.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Multi-User</span>
  </div>
  <div class="grid2" style="align-items:start">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">👥</span> Team Members</div>
        <button class="btn btn-ghost btn-sm" onclick="loadTeamMembers()">↻</button>
      </div>
      <div id="team-members-list"><div class="empty"><div class="icon">👥</div><p>No team members yet. Invite someone below.</p></div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">✉️</span> Invite Member</div></div>
      <div class="form-group"><label>Email Address</label><input id="team-email" placeholder="colleague@company.com"/></div>
      <div class="form-group"><label>Role</label>
        <select id="team-role" >
          <option value="admin">Admin — Full access</option>
          <option value="manager">Manager — Manage agents</option>
          <option value="member" selected>Member — Read &amp; Write</option>
          <option value="viewer">Viewer — Read only</option>
        </select>
      </div>
      <button class="btn btn-primary" onclick="inviteTeamMember()">✉️ Send Invitation</button>
      <div id="team-invite-result" style="margin-top:10px"></div>
    </div>
  </div>
</div>

<!-- ── Customer Support ── -->
<div id="tab-support-desk" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🎧</div>
    <div><div class="page-header-title">Customer Support</div><div class="page-header-desc">24/7 helpdesk with smart ticket routing, AI reply suggestions, and a searchable knowledge base.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Helpdesk</span>
  </div>
  <div style="display:flex;gap:6px;margin-bottom:16px">
    <button class="sup-tab-btn btn btn-primary btn-sm active" onclick="switchSupportTab('tickets',this)">🎫 Tickets</button>
    <button class="sup-tab-btn btn btn-ghost btn-sm" onclick="switchSupportTab('kb',this)">📚 Knowledge Base</button>
  </div>

  <!-- Tickets -->
  <div id="sup-tickets-panel">
    <div class="grid-stat" style="margin-bottom:16px">
      <div class="stat-card"><div class="stat-icon red">🔴</div><div class="stat-body"><div class="val" id="sup-open">–</div><div class="lbl">Open</div></div></div>
      <div class="stat-card"><div class="stat-icon yellow">🟡</div><div class="stat-body"><div class="val" id="sup-progress">–</div><div class="lbl">In Progress</div></div></div>
      <div class="stat-card"><div class="stat-icon green">✅</div><div class="stat-body"><div class="val" id="sup-resolved">–</div><div class="lbl">Resolved</div></div></div>
      <div class="stat-card"><div class="stat-icon blue">📚</div><div class="stat-body"><div class="val" id="sup-kb">–</div><div class="lbl">KB Articles</div></div></div>
    </div>
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">🎫</span> Tickets</div><button class="btn btn-ghost btn-sm" onclick="loadTickets()">↻</button></div>
        <div style="display:flex;gap:6px;margin-bottom:10px">
          <select id="sup-f-status" style="font-size:.8em" onchange="loadTickets()">
            <option value="">All</option><option value="open">Open</option><option value="in_progress">In Progress</option><option value="resolved">Resolved</option>
          </select>
        </div>
        <div id="sup-ticket-list"><div class="empty"><div class="icon">🎫</div><p>No tickets yet.</p></div></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> New Ticket</div></div>
        <div class="form-group"><label>Subject</label><input id="sup-subject" placeholder="Issue with billing…"/></div>
        <div class="form-group"><label>Customer Email</label><input id="sup-cust-email" placeholder="customer@example.com"/></div>
        <div class="form-group"><label>Customer Name</label><input id="sup-cust-name" placeholder="Jane Doe"/></div>
        <div class="form-group"><label>Priority</label>
          <select id="sup-priority" >
            <option value="low">Low</option><option value="medium" selected>Medium</option>
            <option value="high">High</option><option value="urgent">Urgent</option>
          </select>
        </div>
        <div class="form-group"><label>Category</label>
          <select id="sup-cat" >
            <option value="general">General</option><option value="billing">Billing</option>
            <option value="technical">Technical</option><option value="feature_request">Feature Request</option><option value="bug">Bug</option>
          </select>
        </div>
        <div class="form-group"><label>Description</label>
          <textarea id="sup-desc" rows="3" class="field-full" placeholder="Describe the issue…"></textarea>
        </div>
        <button class="btn btn-primary" onclick="createTicket()">🎫 Submit Ticket</button>
      </div>
    </div>
  </div>

  <!-- Knowledge Base -->
  <div id="sup-kb-panel" style="display:none">
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">📚</span> KB Articles</div><button class="btn btn-ghost btn-sm" onclick="loadKBArticles()">↻</button></div>
        <div id="sup-kb-list"><div class="empty"><div class="icon">📚</div><p>No articles yet.</p></div></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> New Article</div></div>
        <div class="form-group"><label>Title</label><input id="kb-title" placeholder="How to reset your password"/></div>
        <div class="form-group"><label>Category</label>
          <select id="kb-cat" >
            <option value="general">General</option><option value="billing">Billing</option>
            <option value="technical">Technical</option><option value="feature_request">Features</option>
          </select>
        </div>
        <div class="form-group"><label>Content</label>
          <textarea id="kb-content" rows="6" class="field-full" placeholder="Write the article content…"></textarea>
        </div>
        <button class="btn btn-primary" onclick="createKBArticle()">📚 Save Article</button>
      </div>
    </div>
  </div>
</div>

<!-- ── Website Builder ── -->
<div id="tab-website-builder" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🌐</div>
    <div><div class="page-header-title">Website Builder</div><div class="page-header-desc">Generate complete landing page HTML from a business description using AI. Edit and export instantly.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">AI Builder</span>
  </div>
  <div class="grid2" style="align-items:start">
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">🌐</span> Generated Pages</div><button class="btn btn-ghost btn-sm" onclick="loadPages()">↻</button></div>
      <div id="wb-pages-list"><div class="empty"><div class="icon">🌐</div><p>No pages yet. Generate one →</p></div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">✨</span> Generate Page</div></div>
      <div class="form-group"><label>Business Name</label><input id="wb-biz" placeholder="Acme SaaS"/></div>
      <div class="form-group"><label>Industry</label><input id="wb-industry" placeholder="B2B Software"/></div>
      <div class="form-group"><label>Page Type</label>
        <select id="wb-type" >
          <option value="landing">Landing Page</option><option value="sales">Sales Page</option>
          <option value="portfolio">Portfolio</option><option value="product">Product Page</option>
          <option value="coming_soon">Coming Soon</option>
        </select>
      </div>
      <div class="form-group"><label>Description</label>
        <textarea id="wb-desc" rows="3" class="field-full" placeholder="We help B2B companies automate their sales process…"></textarea>
      </div>
      <button class="btn btn-primary" onclick="generateWebPage()">🌐 Generate Page</button>
    </div>
  </div>
</div>

<!-- ── Personal Brand ── -->
<div id="tab-brand" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">✨</div>
    <div><div class="page-header-title">Personal Brand Agent</div><div class="page-header-desc">Build your thought leadership — AI content generation, topic ideas, and brand voice consistency.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Brand</span>
  </div>
  <div style="display:flex;gap:6px;margin-bottom:16px">
    <button class="br-tab-btn btn btn-primary btn-sm active" onclick="switchBrandTab('generate',this)">✍️ Generate</button>
    <button class="br-tab-btn btn btn-ghost btn-sm" onclick="switchBrandTab('profile',this)">👤 Profile</button>
    <button class="br-tab-btn btn btn-ghost btn-sm" onclick="switchBrandTab('library',this)">📁 Library</button>
  </div>

  <div id="br-generate-panel">
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">💡</span> Topic Ideas</div>
          <button class="btn btn-ghost btn-sm" onclick="suggestBrandTopics()">✨ AI Suggest</button>
        </div>
        <div id="br-topics-list"><div class="empty"><p>Click "AI Suggest" to get 10 topic ideas based on your profile.</p></div></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="icon">✍️</span> Generate Content</div></div>
        <div class="form-group"><label>Topic</label><input id="br-topic" placeholder="Why AI is transforming sales…"/></div>
        <div class="form-group"><label>Content Type</label>
          <select id="br-type" >
            <option value="linkedin_post">LinkedIn Post</option><option value="twitter_thread">Twitter/X Thread</option>
            <option value="newsletter">Newsletter Section</option><option value="blog_intro">Blog Intro</option>
          </select>
        </div>
        <button class="btn btn-primary" onclick="generateBrandContent()">✨ Generate</button>
        <div id="br-generated" style="margin-top:12px;white-space:pre-wrap;font-size:.85em;color:var(--text-muted)"></div>
      </div>
    </div>
  </div>

  <div id="br-profile-panel" style="display:none">
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">👤</span> Brand Profile</div></div>
      <div class="grid2">
        <div>
          <div class="form-group"><label>Your Name</label><input id="br-p-name" placeholder="Jane Smith"/></div>
          <div class="form-group"><label>Title / Role</label><input id="br-p-title" placeholder="CEO & Founder"/></div>
          <div class="form-group"><label>Industry</label><input id="br-p-industry" placeholder="B2B SaaS"/></div>
        </div>
        <div>
          <div class="form-group"><label>Target Audience</label><input id="br-p-audience" placeholder="Sales leaders at mid-market companies"/></div>
          <div class="form-group"><label>Tone</label>
            <select id="br-p-tone" >
              <option value="professional">Professional</option><option value="casual">Casual</option>
              <option value="inspirational">Inspirational</option><option value="educational">Educational</option>
            </select>
          </div>
        </div>
      </div>
      <button class="btn btn-primary" onclick="saveBrandProfile()">💾 Save Profile</button>
    </div>
  </div>

  <div id="br-library-panel" style="display:none">
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">📁</span> Content Library</div><button class="btn btn-ghost btn-sm" onclick="loadBrandContent()">↻</button></div>
      <div id="br-content-list"><div class="empty"><div class="icon">📁</div><p>No content saved yet.</p></div></div>
    </div>
  </div>
</div>

<!-- ── Health Check ── -->
<div id="tab-health" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">❤️</div>
    <div><div class="page-header-title">Business Health Check</div><div class="page-header-desc">One-click audit of your entire business — graded A to D with issues identified and fixes recommended.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Audit</span>
  </div>
  <div style="display:flex;gap:10px;margin-bottom:16px">
    <button class="btn btn-primary" onclick="runHealthCheck()">❤️ Run Health Check</button>
    <button class="btn btn-ghost" onclick="loadHealthHistory()">📅 History</button>
  </div>
  <div id="hc-report-card" class="card" style="display:none">
    <div class="card-header">
      <div class="card-title"><span class="icon">❤️</span> Health Report</div>
      <span id="hc-grade" style="font-size:2em;font-weight:900;color:var(--gold)"></span>
    </div>
    <div id="hc-report-body"></div>
  </div>
  <div id="hc-latest-msg" class="card">
    <div class="card-header"><div class="card-title"><span class="icon">💡</span> Business Health</div></div>
    <div class="empty"><div class="icon">❤️</div><p>Click "Run Health Check" to audit your business across all modules.</p></div>
  </div>
  <div id="hc-history" style="margin-top:16px"></div>
</div>

<!-- ── Export & Backup ── -->
<div id="tab-export" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">💾</div>
    <div><div class="page-header-title">Export &amp; Backup</div><div class="page-header-desc">Export any module as JSON or CSV, create full ZIP backups of all your AI Employee data.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Data</span>
  </div>
  <div style="display:flex;gap:10px;margin-bottom:16px">
    <button class="btn btn-primary" onclick="createBackup()">🗜️ Create Full Backup</button>
    <button class="btn btn-ghost" onclick="loadExportModules()">↻ Refresh</button>
  </div>
  <div class="grid2" style="align-items:start">
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">📦</span> Export Modules</div></div>
      <p style="font-size:.84em;color:var(--text-muted);margin-bottom:12px">Click a module to export all its data as JSON.</p>
      <div id="export-modules-list"><div class="empty"><p>Loading modules…</p></div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title"><span class="icon">🗜️</span> Backups</div>
        <button class="btn btn-ghost btn-sm" onclick="loadBackupsList()">↻</button>
      </div>
      <div id="export-backups-list"><div class="empty"><div class="icon">🗜️</div><p>No backups yet. Create one to get started.</p></div></div>
    </div>
  </div>
</div>

<!-- ── Skills ── -->
<div id="tab-skills" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🛠️</div>
    <div><div class="page-header-title">Skills Library</div><div class="page-header-desc">Manage capabilities your agents can learn and use. Train skills, assign them to agents, and build new ones.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Agent Capabilities</span>
  </div>
  <div class="grid2" style="align-items:start">
    <div class="card" style="min-height:600px;display:flex;flex-direction:column">
      <div class="card-header">
        <div class="card-title"><span class="icon">🛠️</span> Skills Library <span id="skill-total-badge" style="font-size:.8em;color:var(--text-muted)"></span></div>
        <button class="btn btn-gold btn-sm" onclick="toggleNewSkillForm()" id="new-skill-btn">＋ New Skill</button>
      </div>
      <input id="skill-search" placeholder="🔍 Search skills by name, category, or tag…" oninput="filterSkills()" />
      <div id="category-pills" style="margin:10px 0"></div>
      <div id="skill-grid" class="skill-grid" style="flex:1;overflow-y:auto"><div class="empty"><div class="icon">🛠️</div><p>Loading skills…</p></div></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- New Skill Form (hidden by default) -->
      <div id="new-skill-form-card" class="card" style="display:none;border:2px solid rgba(212,175,55,.4);background:linear-gradient(135deg,rgba(212,175,55,.04),var(--surface2))">
        <div class="card-header">
          <div class="card-title"><span style="color:var(--gold)">◈</span> Create New Skill</div>
          <button class="btn btn-ghost btn-sm" onclick="toggleNewSkillForm()">✕ Cancel</button>
        </div>
        <div class="form-group"><label>Skill Name</label><input id="new-skill-name" placeholder="e.g. Cold Email Copywriting"/></div>
        <div class="form-group"><label>Category</label>
          <select id="new-skill-category">
            <option>Content &amp; Writing</option><option>Lead Generation &amp; Sales</option>
            <option>Research &amp; Analysis</option><option>Social Media</option>
            <option>Customer Support</option><option>Marketing &amp; SEO</option>
            <option>Development &amp; Technical</option><option>Data Analysis</option>
            <option>Trading &amp; Finance</option><option>E-commerce &amp; Product</option>
            <option>Automation &amp; Productivity</option>
          </select>
        </div>
        <div class="form-group"><label>Description</label><textarea id="new-skill-desc" rows="3" placeholder="Describe what this skill does and when to use it…" class="field-full"></textarea></div>
        <div class="form-group"><label>Tags (comma-separated)</label><input id="new-skill-tags" placeholder="e.g. email, sales, conversion"/></div>
        <div class="form-group"><label>How it works (steps, one per line)</label><textarea id="new-skill-steps" rows="3" placeholder="Step 1: Analyze the target audience&#10;Step 2: Draft personalized subject line&#10;Step 3: Write compelling body copy" class="field-full"></textarea></div>
        <button class="btn btn-gold" onclick="saveNewSkill()" style="width:100%">◈ Save Skill to Library</button>
        <div id="new-skill-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
      <!-- Create Custom Agent -->
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🤖</span> Create Custom Agent</div>
        </div>
        <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">Select skills from the library on the left, name your agent, then click Create.</p>
        <div class="form-group"><label>Agent Name</label><input id="agent-name-input" placeholder="e.g. My Content Writer"/></div>
        <div class="form-group"><label>Description (optional)</label><input id="agent-desc-input" placeholder="What this agent does"/></div>
        <div class="form-group">
          <label>Selected Skills <span id="selected-count" style="color:var(--primary)">(0)</span></label>
          <div id="selected-skills-list" style="font-size:.82em;color:var(--text-muted);min-height:24px">No skills selected. Click cards on the left.</div>
        </div>
        <button class="btn btn-gold" onclick="createAgent()" style="width:100%;padding:9px">➕ Create Agent</button>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">👥</span> Custom Agents</div>
          <button class="btn btn-ghost btn-sm" onclick="loadAgents()">↻ Refresh</button>
        </div>
        <div id="agents-list"><div class="empty"><div class="icon">👥</div><p>No agents yet.</p></div></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Tasks ── -->
<div id="tab-tasks" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🚀</div>
    <div><div class="page-header-title">Task Runner</div><div class="page-header-desc">Build and launch tasks for your AI workforce. Describe any goal — agents are auto-selected, you control the final launch.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Task Builder</span>
  </div>

  <!-- Task Builder -->
  <div class="grid2" style="align-items:start">
    <!-- Left: build a task -->
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🚀</span> Build a Task</div>
          <span id="task-step-badge" style="font-size:.78em;background:var(--primary);color:#fff;padding:2px 8px;border-radius:10px">Step 1</span>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Describe any goal — agents will be auto-selected. You can adjust everything before launching.</p>

        <!-- Step 1: description -->
        <div id="task-step1">
          <div class="form-group">
            <label>Task Description</label>
            <textarea id="task-input" rows="4"
              placeholder="e.g. Build a SaaS company for remote team management — create business plan, brand identity, hiring plan, financial model, and go-to-market strategy"
              class="field-full"
              oninput="onTaskInputChange()"></textarea>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary" onclick="runAutoSelect()" style="flex:1" id="btn-autoselect" disabled>🤖 Auto-Select Agents</button>
            <button class="btn btn-ghost btn-sm" onclick="showManualAgentPicker()" title="Manually pick agents">⚙️ Manual</button>
          </div>
          <div id="autoselect-status" style="margin-top:8px;font-size:.82em;color:var(--text-muted)"></div>
        </div>

        <!-- Step 2: agent picker (hidden until auto-select or manual click) -->
        <div id="task-step2" style="display:none;margin-top:16px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <label style="font-weight:600">🤖 Agent Selection <span id="agent-sel-count" style="color:var(--primary);font-weight:700"></span></label>
            <div style="display:flex;gap:6px">
              <button class="btn btn-ghost btn-sm" onclick="selectAllAgents()">All</button>
              <button class="btn btn-ghost btn-sm" onclick="clearAllAgents()">None</button>
              <button class="btn btn-ghost btn-sm" onclick="resetToAutoSelected()">Auto</button>
            </div>
          </div>
          <div id="agent-picker-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:6px;max-height:340px;overflow-y:auto;padding:2px"></div>
        </div>

        <!-- Step 3: mode + submit (hidden until agents selected) -->
        <div id="task-step3" style="display:none;margin-top:16px">
          <div class="form-group">
            <label>Execution Mode</label>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px" id="mode-selector">
              <label id="mode-auto" onclick="setMode('auto')" style="cursor:pointer;border:2px solid var(--primary);border-radius:var(--radius-sm);padding:8px 4px;text-align:center;background:var(--surface2)">
                <div style="font-size:1.2em">🧠</div>
                <div style="font-size:.75em;font-weight:600;margin-top:2px">Auto</div>
                <div style="font-size:.68em;color:var(--text-muted)">Orchestrator decides</div>
              </label>
              <label id="mode-parallel" onclick="setMode('parallel')" style="cursor:pointer;border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 4px;text-align:center;background:var(--surface2)">
                <div style="font-size:1.2em">⚡</div>
                <div style="font-size:.75em;font-weight:600;margin-top:2px">Parallel</div>
                <div style="font-size:.68em;color:var(--text-muted)">All agents at once</div>
              </label>
              <label id="mode-single" onclick="setMode('single')" style="cursor:pointer;border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 4px;text-align:center;background:var(--surface2)">
                <div style="font-size:1.2em">1️⃣</div>
                <div style="font-size:.75em;font-weight:600;margin-top:2px">Single</div>
                <div style="font-size:.68em;color:var(--text-muted)">First selected agent</div>
              </label>
            </div>
          </div>
          <button class="btn btn-success" onclick="submitTask()" style="width:100%;margin-top:4px" id="btn-launch">🚀 Launch Task</button>
          <div id="task-submit-result" style="margin-top:10px;font-size:.88em"></div>
        </div>
      </div>
    </div>

    <!-- Right: active task -->
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📊</span> Active Task</div>
        <button class="btn btn-ghost btn-sm" onclick="loadTasks()">↻ Refresh</button>
      </div>
      <div id="active-task-panel"><div class="empty"><div class="icon">🚀</div><p>No active task.</p></div></div>
    </div>
  </div>

  <!-- Task History -->
  <div class="card" style="margin-top:16px">
    <div class="card-header">
      <div class="card-title"><span class="icon" style="color:var(--gold)">◈</span> Task History</div>
      <button class="btn btn-ghost btn-sm" onclick="loadTasks()">↻ Refresh</button>
    </div>
    <div id="task-history-list"><div class="empty"><p>No completed tasks yet.</p></div></div>
  </div>
  <!-- Task detail modal -->
  <div id="task-detail-modal" role="dialog" aria-modal="true" aria-labelledby="task-detail-heading" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:1000;align-items:center;justify-content:center">
    <div style="background:var(--surface);border:1px solid var(--gold);border-radius:var(--radius);padding:24px;max-width:640px;width:90%;max-height:80vh;overflow-y:auto" tabindex="-1" id="task-detail-dialog">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div class="card-title" id="task-detail-heading">Task Detail</div>
        <button class="btn btn-ghost btn-sm" id="task-detail-close-btn" onclick="closeTaskDetail()" aria-label="Close task detail">✕ Close</button>
      </div>
      <div id="task-detail-content"></div>
    </div>
  </div>
</div>

<!-- ── Swarm ── -->
<div id="tab-swarm" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🐝</div>
    <div><div class="page-header-title">Agent Swarm</div><div class="page-header-desc">All AI agents at a glance — capabilities, status, and current workload. Filter by category or search by skill.</div></div>
    <span class="page-header-badge" style="color:var(--gold)" id="swarm-header-badge">– Agents</span>
  </div>
  <div style="display:flex;gap:16px;flex-wrap:wrap">
    <!-- Left: agent grid -->
    <div style="flex:1;min-width:320px">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🐝</span> Agent Swarm Overview</div>
          <button class="btn btn-ghost btn-sm" onclick="loadSwarm()">↻ Refresh</button>
        </div>
        <p style="color:var(--text-muted);font-size:.85em;margin-bottom:12px">All AI agents — capabilities, status, and current workload.</p>
        <div style="display:flex;gap:10px;margin-bottom:14px;align-items:center">
          <input id="swarm-search" placeholder="🔍 Search agents by name, skill, or capability…"
            style="flex:1;background:var(--surface2);border:1px solid rgba(212,175,55,.2);border-radius:8px;color:var(--text);padding:10px 14px;font-family:inherit;font-size:.88em;outline:none"
            oninput="filterSwarm(null,null)" onfocus="this.style.borderColor='rgba(212,175,55,.5)'" onblur="this.style.borderColor='rgba(212,175,55,.2)'" />
          <button class="btn btn-ghost btn-sm" onclick="loadSwarm()" title="Refresh swarm">↻ Refresh</button>
        </div>
        <div id="swarm-filter-pills" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px">
          <button class="btn btn-primary btn-sm swarm-pill active" onclick="filterSwarm('all',this)" style="background:linear-gradient(135deg,var(--primary-dark),var(--primary));color:#000;border:none">All</button>
          <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('sales',this)">💼 Sales</button>
          <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('marketing',this)">📢 Marketing</button>
          <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('social',this)">📱 Social</button>
          <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('analytics',this)">📊 Analytics</button>
          <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('content',this)">✍️ Content</button>
          <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('ecommerce',this)">🛒 E-commerce</button>
          <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('coordination',this)">🎯 Core</button>
        </div>
        <div id="swarm-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px"><div class="empty"><div class="icon">🐝</div><p>Loading agents…</p></div></div>
      </div>
    </div>
    <!-- Right: collaboration panel -->
    <div style="width:340px;flex-shrink:0;display:flex;flex-direction:column;gap:14px">
      <!-- Active Task Panel -->
      <div class="card" style="border:1px solid rgba(212,175,55,.25);background:linear-gradient(135deg,rgba(212,175,55,.04),var(--surface2))">
        <div class="card-header">
          <div class="card-title"><span style="color:var(--gold)">◈</span> Active Task</div>
          <button class="btn btn-ghost btn-sm" onclick="loadSwarmActivity()">↻</button>
        </div>
        <div id="swarm-active-task">
          <div class="empty"><div class="icon">⚡</div><p style="font-size:.83em">No active task. Launch one from the Tasks tab.</p></div>
        </div>
      </div>
      <!-- Agent Communication Stream -->
      <div class="card" style="flex:1;border:1px solid rgba(212,175,55,.15)">
        <div class="card-header">
          <div class="card-title"><span style="color:var(--gold)">◈</span> Swarm Activity Stream</div>
          <button class="btn btn-ghost btn-sm" onclick="loadSwarmActivity()">↻ Refresh</button>
        </div>
        <p style="color:var(--text-muted);font-size:.8em;margin-bottom:10px">Real-time log of agent actions, completions, and collaborations.</p>
        <div id="swarm-activity-stream" style="max-height:420px;overflow-y:auto;display:flex;flex-direction:column;gap:6px">
          <div class="empty"><div class="icon">📡</div><p style="font-size:.83em">No activity yet. Run a task to see agents collaborate.</p></div>
        </div>
      </div>
      <!-- Swarm Stats -->
      <div class="card" style="border:1px solid rgba(212,175,55,.15)">
        <div class="card-title" style="margin-bottom:10px"><span style="color:var(--gold)">◈</span> Swarm Stats</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div style="text-align:center;padding:10px;background:rgba(212,175,55,.06);border-radius:8px;border:1px solid rgba(212,175,55,.12)">
            <div style="font-size:1.6em;font-weight:800;color:var(--gold)" id="swarm-stat-online">–</div>
            <div style="font-size:.72em;color:var(--text-muted);margin-top:2px">Online</div>
          </div>
          <div style="text-align:center;padding:10px;background:rgba(34,197,94,.06);border-radius:8px;border:1px solid rgba(34,197,94,.12)">
            <div style="font-size:1.6em;font-weight:800;color:var(--success)" id="swarm-stat-total">–</div>
            <div style="font-size:.72em;color:var(--text-muted);margin-top:2px">Total Agents</div>
          </div>
          <div style="text-align:center;padding:10px;background:rgba(212,175,55,.06);border-radius:8px;border:1px solid rgba(212,175,55,.15)">
            <div style="font-size:1.6em;font-weight:800;color:var(--gold)" id="swarm-stat-tasks">–</div>
            <div style="font-size:.72em;color:var(--text-muted);margin-top:2px">Tasks Run</div>
          </div>
          <div style="text-align:center;padding:10px;background:rgba(239,68,68,.06);border-radius:8px;border:1px solid rgba(239,68,68,.12)">
            <div style="font-size:1.6em;font-weight:800;color:#f87171" id="swarm-stat-categories">–</div>
            <div style="font-size:.72em;color:var(--text-muted);margin-top:2px">Categories</div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <!-- ── Live Collaboration Theater ── -->
  <div class="card" style="margin-top:16px;border:1px solid rgba(212,175,55,.2);background:linear-gradient(135deg,rgba(212,175,55,.03),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">◈</span> Live Agent Collaboration Theater</div>
      <div style="display:flex;gap:6px;align-items:center">
        <span id="swarm-theater-status" style="font-size:.75em;color:var(--text-muted)">● Watching</span>
        <button class="btn btn-ghost btn-sm" onclick="swarmTheaterRefresh()">↻ Refresh</button>
      </div>
    </div>
    <p style="color:var(--text-muted);font-size:.8em;margin-bottom:14px">Visual feed of recent cross-agent collaborations — messages, hand-offs and results.</p>
    <div id="swarm-theater" style="min-height:120px;display:flex;flex-direction:column;gap:10px">
      <div class="empty"><div class="icon">🐝</div><p style="font-size:.83em">Load swarm activity to see collaboration messages.</p></div>
    </div>
  </div>
</div>
<style>
@keyframes swarmMsg{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.swarm-msg{animation:swarmMsg .3s ease forwards}
.swarm-msg-bubble{padding:8px 12px;border-radius:12px;font-size:.82em;max-width:80%;line-height:1.4}
.swarm-msg-left .swarm-msg-bubble{background:rgba(212,175,55,.1);border:1px solid rgba(212,175,55,.2);border-bottom-left-radius:3px;color:var(--text)}
.swarm-msg-right .swarm-msg-bubble{background:rgba(212,175,55,.1);border:1px solid rgba(212,175,55,.2);border-bottom-right-radius:3px;color:var(--text);margin-left:auto}
</style>
<div id="tab-commands" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📜</div>
    <div><div class="page-header-title">Command Reference</div><div class="page-header-desc">Full list of WhatsApp and bot commands available across your AI system. Search, filter by category, and copy commands directly.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Commands</span>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon" style="color:var(--gold)">◈</span> Command Reference</div>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:16px">
      <button class="btn btn-primary btn-sm cmd-type-btn active" onclick="switchCmdType('whatsapp',this)" id="cmd-tab-wa" style="background:linear-gradient(135deg,#B8960C,#D4AF37);color:#000;border:none">📱 WhatsApp Commands</button>
      <button class="btn btn-ghost btn-sm cmd-type-btn" onclick="switchCmdType('bot',this)" id="cmd-tab-bot">🤖 Bot Commands</button>
    </div>
    <input id="cmd-search" placeholder="🔍 Search commands…" oninput="filterCommands()" style="width:100%;margin-bottom:14px" />
    <div id="cmd-category-pills" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px"></div>
    <div id="cmd-list"></div>
  </div>
</div>

<!-- ── ROI Metrics ── -->
<div id="tab-metrics" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📈</div>
    <div><div class="page-header-title">ROI & Performance Analytics</div><div class="page-header-desc">Real usage data tracked automatically from all agent activity. Measure tasks, hours saved, cost efficiency, and business impact.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Analytics</span>
  </div>
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
    <div>
      <h2 style="font-size:1.15em;font-weight:800;color:var(--text);letter-spacing:-.02em">ROI &amp; Usage Tracking</h2>
      <p style="font-size:.8em;color:var(--text-muted)">Real usage data — tracked automatically from all agent activity</p>
    </div>
    <div style="display:flex;gap:8px">
      <select id="roi-period" onchange="loadMetrics()" style="font-size:.82em;background:var(--surface2);border:1px solid rgba(212,175,55,.25);border-radius:8px;color:var(--text);padding:6px 12px">
        <option value="all">All Time</option>
        <option value="30d">Last 30 Days</option>
        <option value="7d">Last 7 Days</option>
        <option value="today">Today</option>
      </select>
      <button class="btn btn-ghost btn-sm" onclick="loadMetrics()">↻ Refresh</button>
    </div>
  </div>
  <div class="grid-stat" id="roi-stat-cards">
    <div class="stat-card" style="--stat-top:rgba(212,175,55,.3)">
      <div class="stat-icon" style="background:linear-gradient(135deg,rgba(212,175,55,.2),rgba(212,175,55,.05));color:var(--gold)">✓</div>
      <div class="stat-body"><div class="val" id="m-tasks">–</div><div class="lbl">Tasks Completed</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon" style="background:linear-gradient(135deg,rgba(34,197,94,.2),rgba(34,197,94,.05));color:var(--success)">⏱</div>
      <div class="stat-body"><div class="val" id="m-hours">–</div><div class="lbl">AI Hours Worked</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon" style="background:linear-gradient(135deg,rgba(212,175,55,.2),rgba(212,175,55,.05));color:var(--gold-light)">👤</div>
      <div class="stat-body"><div class="val" id="m-human-saved">–</div><div class="lbl">Human Hours Saved</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon" style="background:linear-gradient(135deg,rgba(34,197,94,.2),rgba(34,197,94,.05));color:var(--success)">€</div>
      <div class="stat-body"><div class="val" id="m-saved">–</div><div class="lbl">Cost Saved (€)</div><div style="font-size:.7em;color:var(--text-muted);margin-top:2px" id="m-saved-trend"></div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon" style="background:linear-gradient(135deg,rgba(212,175,55,.2),rgba(212,175,55,.05));color:var(--gold)">◆</div>
      <div class="stat-body"><div class="val" id="m-agents-used">–</div><div class="lbl">Agents Utilized</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon" style="background:linear-gradient(135deg,rgba(212,175,55,.2),rgba(212,175,55,.05));color:var(--gold)">◎</div>
      <div class="stat-body"><div class="val" id="m-leads">–</div><div class="lbl">Leads Generated</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon" style="background:linear-gradient(135deg,rgba(34,197,94,.2),rgba(34,197,94,.05));color:var(--success)">✉</div>
      <div class="stat-body"><div class="val" id="m-emails">–</div><div class="lbl">Emails Sent</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon" style="background:linear-gradient(135deg,rgba(212,175,55,.2),rgba(212,175,55,.05));color:var(--gold)">◈</div>
      <div class="stat-body"><div class="val" id="m-content">–</div><div class="lbl">Content Created</div></div>
    </div>
  </div>
  <!-- ROI Summary bar -->
  <div class="card" style="border:1px solid rgba(212,175,55,.3);background:linear-gradient(135deg,rgba(212,175,55,.06),rgba(212,175,55,.02))">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">◈</span> ROI Summary</div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:20px" id="roi-summary">
      <div style="text-align:center;padding:16px 10px;background:rgba(212,175,55,.05);border-radius:10px;border:1px solid rgba(212,175,55,.12)">
        <div style="font-size:.7em;color:var(--text-muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Efficiency Rate
          <span title="Efficiency = (human hours saved ÷ total tasks) × 100. Higher means your AI team completes more work per task with less overhead." style="cursor:help;color:var(--gold);margin-left:4px">ⓘ</span>
        </div>
        <div style="font-size:2.4em;font-weight:800;color:var(--gold);letter-spacing:-.03em;line-height:1" id="roi-efficiency">–%</div>
        <div id="roi-efficiency-desc" style="font-size:.72em;color:var(--text-muted);margin-top:6px;line-height:1.4"></div>
      </div>
      <div style="text-align:center;padding:16px 10px;background:rgba(212,175,55,.05);border-radius:10px;border:1px solid rgba(212,175,55,.12)">
        <div style="font-size:.7em;color:var(--text-muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Avg Task Duration</div>
        <div style="font-size:2.4em;font-weight:800;color:var(--gold);letter-spacing:-.03em;line-height:1" id="roi-avg-duration">–</div>
      </div>
      <div style="text-align:center;padding:16px 10px;background:rgba(212,175,55,.05);border-radius:10px;border:1px solid rgba(212,175,55,.12)">
        <div style="font-size:.7em;color:var(--text-muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Most Active Agent</div>
        <div style="font-size:1.2em;font-weight:700;color:var(--text);line-height:1.3;margin-top:6px" id="roi-top-bot">–</div>
      </div>
      <div style="text-align:center;padding:16px 10px;background:rgba(34,197,94,.05);border-radius:10px;border:1px solid rgba(34,197,94,.15)">
        <div style="font-size:.7em;color:var(--text-muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Value Generated</div>
        <div style="font-size:2.4em;font-weight:800;color:var(--success);letter-spacing:-.03em;line-height:1" id="roi-value">€–</div>
      </div>
    </div>
  </div>

  <!-- Value Over Time Chart -->
  <div class="card" style="margin-top:0;border:1px solid rgba(212,175,55,.15)">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">◈</span> Value Generated Over Time</div>
      <span style="font-size:.75em;color:var(--text-muted)">€ per event · cumulative</span>
    </div>
    <div id="roi-chart-container" style="min-height:120px;display:flex;align-items:flex-end;gap:4px;padding:16px 0 0;position:relative">
      <div class="empty" style="width:100%"><div class="icon">📈</div><p style="font-size:.84em">Record events to see value chart.</p></div>
    </div>
    <div id="roi-chart-labels" style="display:flex;gap:4px;margin-top:4px;overflow:hidden"></div>
  </div>

  <!-- Agent Breakdown -->
  <div class="grid2" style="margin-top:0">
    <div class="card" style="border:1px solid rgba(212,175,55,.12)">
      <div class="card-header">
        <div class="card-title"><span style="color:var(--gold)">◈</span> Breakdown by Agent</div>
      </div>
      <div id="roi-agent-breakdown"><div class="empty"><div class="icon">🤖</div><p style="font-size:.84em">No agent data yet.</p></div></div>
    </div>
    <div class="card" style="border:1px solid rgba(212,175,55,.12)">
      <div class="card-header">
        <div class="card-title"><span style="color:var(--gold)">◈</span> Breakdown by Task Type</div>
      </div>
      <div id="roi-type-breakdown"><div class="empty"><div class="icon">📋</div><p style="font-size:.84em">No task type data yet.</p></div></div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">◈</span> Activity Log</div>
        <button class="btn btn-ghost btn-sm" onclick="loadMetrics()">↻ Refresh</button>
      </div>
      <div id="metrics-events"><div class="empty"><div class="icon">📊</div><p>No events recorded yet. Agent activity is tracked automatically.</p></div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">◈</span> Manual Entry</div>
      </div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">Log business outcomes to track ROI for client reporting.</p>
      <div class="form-group">
        <label>Event Type</label>
        <select id="metric-type">
          <option value="task_completed">Task Completed</option>
          <option value="lead_generated">Lead Generated</option>
          <option value="email_sent">Email Sent</option>
          <option value="content_created">Content Created</option>
          <option value="call_booked">Call Booked</option>
          <option value="deal_closed">Deal Closed</option>
          <option value="ticket_resolved">Ticket Resolved</option>
          <option value="custom">Custom</option>
        </select>
      </div>
      <div class="form-group"><label>Agent / Source</label><input id="metric-agent" placeholder="e.g. lead-hunter"/></div>
      <div class="form-group"><label>Value (€, optional)</label><input id="metric-value" type="number" placeholder="e.g. 500" min="0"/></div>
      <div class="form-group"><label>Notes (optional)</label><input id="metric-notes" placeholder="e.g. Closed deal with Acme Corp"/></div>
      <button class="btn btn-success" onclick="recordMetric()">📊 Record Event</button>
    </div>
  </div>
</div>

<!-- ── Templates ── -->
<div id="tab-templates" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📋</div>
    <div><div class="page-header-title">Business Templates</div><div class="page-header-desc">Pre-built plug-and-play templates for common business use-cases. One click to deploy a full AI team.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Templates</span>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">📋</span> Business Templates</div>
      <div style="display:flex;gap:8px;align-items:center">
        <input id="template-search" placeholder="🔍 Search templates…" oninput="filterTemplates()"
          style="background:var(--surface2);border:1px solid rgba(212,175,55,.2);border-radius:8px;color:var(--text);padding:7px 12px;font-family:inherit;font-size:.82em;outline:none;width:200px"
          onfocus="this.style.borderColor='rgba(212,175,55,.5)'" onblur="this.style.borderColor='rgba(212,175,55,.2)'" />
        <button class="btn btn-ghost btn-sm" onclick="loadTemplates()">↻ Refresh</button>
      </div>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:12px">
      Pre-built plug-and-play templates for common business use-cases. One click to deploy a full AI team.
    </p>
    <!-- Category filter -->
    <div id="template-cat-pills" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px">
      <button class="btn btn-primary btn-sm tmpl-pill active" onclick="filterTemplatesCat('',this)" style="background:linear-gradient(135deg,var(--primary-dark),var(--primary));color:#000;border:none">All</button>
      <button class="btn btn-ghost btn-sm tmpl-pill" onclick="filterTemplatesCat('Sales',this)">💼 Sales</button>
      <button class="btn btn-ghost btn-sm tmpl-pill" onclick="filterTemplatesCat('Content',this)">✍️ Content</button>
      <button class="btn btn-ghost btn-sm tmpl-pill" onclick="filterTemplatesCat('Marketing',this)">📢 Marketing</button>
      <button class="btn btn-ghost btn-sm tmpl-pill" onclick="filterTemplatesCat('Support',this)">🎧 Support</button>
      <button class="btn btn-ghost btn-sm tmpl-pill" onclick="filterTemplatesCat('E-commerce',this)">🛒 E-commerce</button>
      <button class="btn btn-ghost btn-sm tmpl-pill" onclick="filterTemplatesCat('HR',this)">👥 HR</button>
      <button class="btn btn-ghost btn-sm tmpl-pill" onclick="filterTemplatesCat('Analytics',this)">📊 Analytics</button>
    </div>
    <div id="templates-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px">
      <div class="empty"><div class="icon">📋</div><p>Loading templates…</p></div>
    </div>
  </div>
</div>

<!-- ── Guardrails ── -->
<div id="tab-guardrails" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🔒</div>
    <div><div class="page-header-title">Guardrails & Safety Controls</div><div class="page-header-desc">Define rules that keep your AI agents operating safely. High-risk actions require manual approval before execution.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Security Layer</span>
  </div>
  <!-- Pending approvals notification banner -->
  <div id="guardrails-notification-banner" style="display:none;align-items:center;gap:12px;background:linear-gradient(135deg,rgba(245,158,11,.15),rgba(239,68,68,.1));border:1px solid rgba(245,158,11,.5);border-radius:var(--radius);padding:14px 18px;margin-bottom:14px;font-size:.88em;color:var(--warning);font-weight:600;animation:blink 1.5s infinite"></div>
  <div class="grid-stat">
    <div class="stat-card">
      <div class="stat-icon yellow">⏳</div>
      <div class="stat-body"><div class="val" id="g-pending">–</div><div class="lbl">Pending Approvals</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon green">✅</div>
      <div class="stat-body"><div class="val" id="g-approved">–</div><div class="lbl">Approved (total)</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon blue">🚫</div>
      <div class="stat-body"><div class="val" id="g-rejected">–</div><div class="lbl">Rejected (total)</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon cyan">📋</div>
      <div class="stat-body"><div class="val" id="g-total">–</div><div class="lbl">All Actions Logged</div></div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">⏳</span> Pending Approvals</div>
        <button class="btn btn-ghost btn-sm" onclick="loadGuardrails()">↻ Refresh</button>
      </div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
        High-risk actions require manual confirmation before execution.
        <strong style="color:var(--warning)">Review carefully before approving.</strong>
      </p>
      <div id="guardrails-pending"><div class="empty"><div class="icon">✅</div><p>No pending approvals. All clear!</p></div></div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📋</span> Action Log</div>
        <button class="btn btn-ghost btn-sm" onclick="loadGuardrails()">↻ Refresh</button>
      </div>
      <div id="guardrails-log"><div class="empty"><div class="icon">📋</div><p>No actions logged yet.</p></div></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">⚙️</span> Guardrail Settings</div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Configure which actions require approval and rate limits per agent.</p>
    <div class="grid2">
      <div>
        <div class="section-title">Actions Requiring Approval</div>
        <div id="guardrail-settings-list" style="font-size:.88em">
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
            <input type="checkbox" id="gr-send-email" checked /> Send bulk emails
          </label>
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
            <input type="checkbox" id="gr-social-post" checked /> Post to social media
          </label>
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
            <input type="checkbox" id="gr-make-purchase" checked /> Make purchases / place orders
          </label>
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
            <input type="checkbox" id="gr-delete-data" checked /> Delete or modify data
          </label>
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0">
            <input type="checkbox" id="gr-api-calls" /> External API calls with side-effects
          </label>
        </div>
      </div>
      <div>
        <div class="section-title">Rate Limits</div>
        <div class="form-group"><label>Max emails / day</label><input id="rl-emails" type="number" value="200" min="1"/></div>
        <div class="form-group"><label>Max social posts / day</label><input id="rl-posts" type="number" value="10" min="1"/></div>
        <div class="form-group"><label>Max API calls / hour</label><input id="rl-api" type="number" value="100" min="1"/></div>
        <button class="btn btn-primary" onclick="saveGuardrailSettings()">💾 Save Settings</button>
      </div>
    </div>
  </div>

  <!-- Custom Guardrails -->
  <div class="card card-ai">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">◈</span> Custom Guardrails</div>
      <button class="btn btn-ghost btn-sm" onclick="loadGuardrails()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Add custom safety rules the AI must follow. These are enforced across all agent actions.</p>
    <div class="grid2" style="gap:16px;align-items:start">
      <div>
        <div style="font-size:.78em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Active Custom Rules</div>
        <div id="custom-guardrails-list"><div class="empty" style="padding:12px"><div class="icon" style="font-size:1.4em">🔒</div><p style="font-size:.84em">No custom rules yet. Add one on the right.</p></div></div>
      </div>
      <div>
        <div style="font-size:.78em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Add New Rule</div>
        <div class="form-group">
          <label>Rule Type</label>
          <select id="gr-custom-type">
            <option value="forbidden_action">Forbidden Action</option>
            <option value="required_approval">Requires Approval</option>
            <option value="content_filter">Content Filter</option>
            <option value="data_restriction">Data Restriction</option>
            <option value="custom">Custom Rule</option>
          </select>
        </div>
        <div class="form-group">
          <label>Rule Description</label>
          <textarea id="gr-custom-rule" rows="3" placeholder="e.g. Never send emails to competitors' domains&#10;e.g. Always require approval before posting on LinkedIn&#10;e.g. Never share customer pricing data externally"
            class="field-full"></textarea>
        </div>
        <div class="form-group">
          <label>Severity</label>
          <select id="gr-custom-severity">
            <option value="critical">🔴 Critical (block immediately)</option>
            <option value="high">🟠 High (require approval)</option>
            <option value="medium" selected>🟡 Medium (log and warn)</option>
            <option value="low">🟢 Low (log only)</option>
          </select>
        </div>
        <button class="btn btn-gold" onclick="addCustomGuardrail()" style="width:100%">🔒 Add Guardrail Rule</button>
        <div id="gr-custom-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
    </div>
  </div>

  <!-- High-Risk Action Review -->
  <div class="card" style="border:1px solid rgba(239,68,68,.3);background:linear-gradient(135deg,rgba(239,68,68,.04),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span style="color:#ef4444">⚠️</span> High-Risk Action Review</div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="loadPendingActions()">↻ Refresh</button>
        <button class="btn btn-ghost btn-sm" style="color:#ef4444;border-color:rgba(239,68,68,.3)" onclick="showSubmitActionForm()">+ Submit Action</button>
      </div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      AI-suggested or system-generated actions that require human approval before execution.
      <strong style="color:#ef4444">Review carefully — these may have real-world effects.</strong>
    </p>
    <div id="pending-actions-list"><div class="empty"><div class="icon">✅</div><p>No pending actions. All clear!</p></div></div>

    <!-- Submit action form (hidden by default) -->
    <div id="submit-action-form" style="display:none;margin-top:16px;border-top:1px solid rgba(239,68,68,.2);padding-top:16px">
      <div style="font-size:.84em;font-weight:600;color:var(--text);margin-bottom:10px">Submit Action for Review</div>
      <div class="form-group"><label>Action Type</label>
        <select id="pa-action-type" >
          <option value="send_email">Send Bulk Email</option>
          <option value="social_post">Social Media Post</option>
          <option value="purchase">Make Purchase</option>
          <option value="delete_data">Delete/Modify Data</option>
          <option value="api_call">External API Call</option>
          <option value="other">Other</option>
        </select>
      </div>
      <div class="form-group"><label>Description *</label><textarea id="pa-description" rows="3" class="field-full" placeholder="Describe exactly what this action will do…"></textarea></div>
      <div class="form-group"><label>Risk Level</label>
        <select id="pa-risk-level" >
          <option value="low">🟢 Low</option>
          <option value="medium" selected>🟡 Medium</option>
          <option value="high">🟠 High</option>
          <option value="critical">🔴 Critical</option>
        </select>
      </div>
      <div class="form-group"><label>Payload (JSON, optional)</label>
        <textarea id="pa-payload" rows="2" class="field-full" placeholder='{"recipients": 150, "subject": "..."}'></textarea>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" onclick="submitPendingAction()" style="flex:1">⚠️ Submit for Review</button>
        <button class="btn btn-ghost" onclick="document.getElementById('submit-action-form').style.display='none'">Cancel</button>
      </div>
      <div id="pa-submit-result" style="margin-top:8px;font-size:.84em"></div>
    </div>
  </div>
</div>

<!-- ── Memory ── -->
<div id="tab-memory" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🧠</div>
    <div><div class="page-header-title">Memory & Knowledge Base</div><div class="page-header-desc">Client contacts, conversation history, and contextual knowledge stored across all AI sessions.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Persistent Memory</span>
  </div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:start">
    <!-- Left: Client Memory with search -->
    <div style="flex:1;min-width:300px">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">👥</span> Client / Contact Memory</div>
          <button class="btn btn-ghost btn-sm" onclick="loadMemory()">↻ Refresh</button>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:10px">The AI remembers your clients across all conversations and tasks.</p>
        <!-- Search and filter bar -->
        <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center">
          <input id="memory-search" placeholder="🔍 Search by name, company, email…" oninput="filterMemoryClients()"
            style="flex:1;background:var(--surface2);border:1px solid rgba(212,175,55,.2);border-radius:8px;color:var(--text);padding:8px 12px;font-family:inherit;font-size:.84em;outline:none"
            onfocus="this.style.borderColor='rgba(212,175,55,.5)'" onblur="this.style.borderColor='rgba(212,175,55,.2)'" />
          <select id="memory-status-filter" onchange="filterMemoryClients()"
            style="background:var(--surface2);border:1px solid rgba(212,175,55,.2);border-radius:8px;color:var(--text);padding:8px 10px;font-size:.82em;outline:none">
            <option value="">All Status</option>
            <option value="prospect">Prospect</option>
            <option value="lead">Lead</option>
            <option value="customer">Customer</option>
            <option value="churned">Churned</option>
          </select>
        </div>
        <div id="memory-clients"><div class="empty"><div class="icon">👥</div><p>No clients remembered yet.</p></div></div>
      </div>
      <!-- Recent Conversations (closed chats) -->
      <div class="card" style="margin-top:14px;border:1px solid rgba(212,175,55,.15)">
        <div class="card-header">
          <div class="card-title"><span style="color:var(--gold)">◈</span> Recent Conversations</div>
          <button class="btn btn-ghost btn-sm" onclick="loadMemoryConversations()">↻ Refresh</button>
        </div>
        <p style="color:var(--text-muted);font-size:.82em;margin-bottom:10px">Closed chat sessions with AI summary and date. Click any to view details.</p>
        <input id="conv-search" placeholder="🔍 Search conversations…" oninput="filterConversations()"
          style="margin-bottom:10px"
          onfocus="this.style.borderColor='rgba(212,175,55,.5)'" onblur="this.style.borderColor='rgba(212,175,55,.2)'" />
        <div id="memory-conversations"><div class="empty"><div class="icon">💬</div><p style="font-size:.84em">No conversations recorded yet. Chat sessions are saved here automatically.</p></div></div>
      </div>
    </div>
    <!-- Right: Add Client + Recent Interactions -->
    <div style="width:320px;flex-shrink:0;display:flex;flex-direction:column;gap:14px">
      <div class="card card-ai">
        <div class="card-header">
          <div class="card-title"><span style="color:var(--gold)">◈</span> Add Client</div>
        </div>
        <div class="form-group"><label>Name</label><input id="mem-name" placeholder="e.g. John Smith"/></div>
        <div class="form-group"><label>Company</label><input id="mem-company" placeholder="e.g. Acme Corp"/></div>
        <div class="form-group"><label>Email</label><input id="mem-email" type="email" placeholder="john@acme.com"/></div>
        <div class="form-group"><label>Phone</label><input id="mem-phone" type="tel" placeholder="+1 555 123 4567"/></div>
        <div class="form-group">
          <label>Last Contact</label>
          <input id="mem-last-contact" type="date" />
        </div>
        <div class="form-group">
          <label>Status</label>
          <select id="mem-status">
            <option value="prospect">Prospect</option>
            <option value="lead">Lead</option>
            <option value="customer">Customer</option>
            <option value="churned">Churned</option>
          </select>
        </div>
        <div class="form-group"><label>Notes</label><textarea id="mem-notes" rows="3" placeholder="Any important context about this client…"></textarea></div>
        <button class="btn btn-gold" onclick="addClient()" style="width:100%">➕ Add Client</button>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">📝</span> Recent Interactions</div>
        </div>
        <div id="memory-recent"><div class="empty"><div class="icon">📝</div><p>No recent interactions.</p></div></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Integrations ── -->
<div id="tab-integrations" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🔌</div>
    <div><div class="page-header-title">Integrations & Connections</div><div class="page-header-desc">Connect your tools and services. The AI uses these integrations to take real actions across your business.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Connected Services</span>
  </div>
  <div class="grid-stat" style="margin-bottom:16px">
    <div class="stat-card"><div class="stat-icon" style="background:linear-gradient(135deg,rgba(167,139,250,.2),rgba(167,139,250,.05));color:#a78bfa">🔌</div><div class="stat-body"><div class="val" id="intg-stat-total">–</div><div class="lbl">Total Services</div></div></div>
    <div class="stat-card"><div class="stat-icon" style="background:linear-gradient(135deg,rgba(34,197,94,.2),rgba(34,197,94,.05));color:var(--success)">✅</div><div class="stat-body"><div class="val" id="intg-stat-connected">–</div><div class="lbl">Connected</div></div></div>
    <div class="stat-card"><div class="stat-icon" style="background:linear-gradient(135deg,rgba(148,163,184,.1),rgba(148,163,184,.05));color:var(--text-muted)">○</div><div class="stat-body"><div class="val" id="intg-stat-pending">–</div><div class="lbl">Not Configured</div></div></div>
    <div class="stat-card"><div class="stat-icon" style="background:linear-gradient(135deg,rgba(212,175,55,.2),rgba(212,175,55,.05));color:var(--gold)">◈</div><div class="stat-body"><div class="val" id="intg-stat-pct">–%</div><div class="lbl">Connected Rate</div></div></div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">🔌</span> Integrations</div>
      <button class="btn btn-ghost btn-sm" onclick="loadIntegrations()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:16px">
      Connect your tools and services. The AI uses these integrations to take real actions across your business. Secret fields are masked — paste a new value to update.
    </p>
    <div id="integrations-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px">
      <div class="empty"><div class="icon">🔌</div><p>Loading integrations…</p></div>
    </div>
  </div>
</div>

<script>
// ── Nav scroll arrows ──
/* ── Group ↔ Tab navigation ── */
const _TAB_TO_GROUP = {
  // Command Center
  dashboard:'overview',
  // Intelligence
  chat:'intelligence', history:'intelligence', briefing:'intelligence',
  meetings:'intelligence', competitors:'intelligence',
  // Operations
  tasks:'operations', scheduler:'operations', workflows:'operations',
  templates:'operations', artifacts:'operations',
  // Workforce
  swarm:'workforce', workers:'workforce', 'live-office':'workforce',
  skills:'workforce', improvements:'workforce', commands:'workforce',
  org:'workforce', team:'workforce',
  // Growth & Revenue
  crm:'growth', 'email-mkt':'growth', 'email-marketing':'growth',
  social:'growth', 'content-calendar':'growth', invoicing:'growth',
  financial:'growth', metrics:'growth', budget:'growth', roi:'growth',
  'analytics-bi':'growth',
  // Governance & System
  guardrails:'governance', memory:'governance', integrations:'governance',
  options:'governance', goals:'governance', tickets:'governance',
  boardroom:'governance', companies:'governance', export:'governance',
  // Labs
  blacklight:'labs', ascend:'labs', 'neural-brain':'labs',
  health:'labs', brand:'labs', 'website-builder':'labs', 'support-desk':'labs',
};

function switchGroup(group, btn) {
  // Update primary nav active state
  document.querySelectorAll('.nav-group-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // Show corresponding sub-nav
  document.querySelectorAll('.sub-nav').forEach(s => s.classList.remove('active'));
  const subNav = document.getElementById('subnav-' + group);
  if (subNav) subNav.classList.add('active');
  // If overview, go directly to dashboard
  if (group === 'overview') {
    switchTab('dashboard', btn);
  } else {
    // Activate the first sub-tab of this group
    const firstBtn = subNav && subNav.querySelector('button');
    if (firstBtn) firstBtn.click();
  }
}

function navScroll(dir) {
  /* legacy — no-op with new grouped nav */
}
function _updateNavArrows() { /* legacy — no-op */ }
document.addEventListener('DOMContentLoaded', function() {
  /* grouped nav needs no scroll arrows */
});

function switchTab(tab, btn) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  const tabEl = document.getElementById('tab-' + tab);
  if (tabEl) tabEl.classList.add('active');
  // Sub-nav active state — find the right button automatically if not provided
  document.querySelectorAll('.sub-nav button').forEach(b => b.classList.remove('active'));
  if (btn && btn.classList && !btn.classList.contains('nav-group-btn')) {
    btn.classList.add('active');
  } else {
    // Auto-find sub-nav button for this tab
    const group = _TAB_TO_GROUP[tab] || 'overview';
    const subNav = document.getElementById('subnav-' + group);
    if (subNav) {
      const safeTab = Object.keys(_TAB_TO_GROUP).includes(tab) ? tab : '';
      const subBtn = safeTab ? subNav.querySelector(`button[onclick*="${safeTab}"]`) : null;
      if (subBtn) subBtn.classList.add('active');
    }
  }
  // Ensure correct group is highlighted
  const group = _TAB_TO_GROUP[tab] || 'overview';
  document.querySelectorAll('.nav-group-btn').forEach(b => b.classList.remove('active'));
  const groupBtn = document.querySelector(`.nav-group-btn[data-group="${group}"]`);
  if (groupBtn) groupBtn.classList.add('active');
  // Ensure correct sub-nav is visible
  document.querySelectorAll('.sub-nav').forEach(s => s.classList.remove('active'));
  const subNav = document.getElementById('subnav-' + group);
  if (subNav) subNav.classList.add('active');
  currentTab = tab;
  if (tab === 'dashboard') { loadDashboard(); if (typeof loadSysRes === 'function') loadSysRes(); loadDoctorPanel(); }
  if (tab === 'chat') loadChatLog();
  if (tab === 'scheduler') loadSchedules();
  if (tab === 'workers') { loadWorkers(); if (!_allAgents.length) loadSwarm().then(renderSwarmAgentGrid); else renderSwarmAgentGrid(); }
  if (tab === 'improvements') loadImprovements();
  if (tab === 'skills') loadSkills();
  if (tab === 'tasks') loadTasks();
  if (tab === 'swarm') { loadSwarm(); swarmTheaterRefresh(); }
  if (tab === 'live-office') loadLiveOffice();
  if (tab === 'commands') loadCommandsTab();
  if (tab === 'metrics') loadMetrics();
  if (tab === 'templates') loadTemplates();
  if (tab === 'guardrails') loadGuardrails();
  if (tab === 'memory') loadMemory();
  if (tab === 'integrations') loadIntegrations();
  if (tab === 'history') loadHistory();
  if (tab === 'options') { loadOptions(); loadUpdaterStatus(); runSecurityCheck(); }
  if (tab === 'blacklight') { blRefresh(); blLoadLogs(); }
  if (tab === 'ascend') { afRefresh(); afLoadPatches(); afLoadChangelog(); }
  if (tab === 'budget') loadBudget();
  if (tab === 'org') { loadOrg(); loadOrgAdapters(); }
  if (tab === 'goals') loadGoals();
  if (tab === 'tickets') { loadTickets(); loadTicketAudit(); }
  if (tab === 'boardroom') loadBoardroom();
  if (tab === 'companies') loadCompanies();
  if (tab === 'artifacts') { loadArtifacts(); loadSessions(); }
}
</script>
<!-- ── History ── -->
<div id="tab-history" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🕐</div>
    <div><div class="page-header-title">Activity History</div><div class="page-header-desc">A persistent, filterable timeline of all agent activities, security checks, and system events from all time.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Full Audit Log</span>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">🕐</span> Activity History</div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn btn-ghost btn-sm" onclick="loadHistory()">↻ Refresh</button>
        <button class="btn btn-ghost btn-sm" onclick="exportHistory()" title="Download history as JSON">⬇️ Export</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--danger)"
                onclick="clearHistory()">🗑️ Clear</button>
      </div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      A persistent log of all agent activities, security checks, settings changes and more. Click <strong style="color:var(--text)">↩ Re-run</strong> on any task to send it to the Tasks tab, or <strong style="color:var(--text)">💬 Send Again</strong> to replay a chat command.
    </p>

    <!-- Filter bar -->
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;align-items:center">
      <input id="history-search" placeholder="🔍 Search…"
             style="flex:1;min-width:160px;max-width:280px;font-size:.84em"
             oninput="filterHistory()"/>
      <select id="history-type-filter" style="font-size:.84em;min-width:160px"
              onchange="filterHistory()">
        <option value="">All event types</option>
        <option value="security_check">🛡️ Security Check</option>
        <option value="security_action_done">✅ Security Action</option>
        <option value="settings_saved">⚙️ Settings Saved</option>
        <option value="guardrail_approved">✅ Guardrail Approved</option>
        <option value="guardrail_rejected">🚫 Guardrail Rejected</option>
        <option value="agent_command">💬 Agent Command</option>
        <option value="task_run">🚀 Task Run</option>
        <option value="worker_triggered">👷 Worker</option>
        <option value="system">ℹ️ System</option>
      </select>
      <select id="history-source-filter" style="font-size:.84em;min-width:140px"
              onchange="filterHistory()">
        <option value="">All sources</option>
        <option value="chat">Chat</option>
        <option value="dashboard">Dashboard</option>
        <option value="guardrails">Guardrails</option>
        <option value="security-checklist">Security</option>
        <option value="system">System</option>
      </select>
      <span id="history-count" style="font-size:.78em;color:var(--text-muted);white-space:nowrap"></span>
    </div>

    <div id="history-timeline">
      <div class="empty"><div class="icon">🕐</div><p>Loading history…</p></div>
    </div>
  </div>
</div>

<!-- ── Options ── -->
<div id="tab-options" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">⚙️</div>
    <div><div class="page-header-title">Settings & Configuration</div><div class="page-header-desc">API keys, agent behavior, security settings, and system preferences. Changes take effect immediately.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">System Config</span>
  </div>
  <div class="grid2">

    <!-- Left column: API Keys -->
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🔑</span> API Keys</div>
          <button class="btn btn-ghost btn-sm" onclick="loadOptions()">↻ Refresh</button>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
          Secret values are masked. Paste a new value to update; leave unchanged to keep existing.
        </p>
        <div id="opt-api-keys"></div>
        <button class="btn btn-primary" style="margin-top:10px;width:100%" onclick="saveSettings('api_keys')">💾 Save API Keys</button>
      </div>
    </div>

    <!-- Right column -->
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">⚙️</span> Preferences</div>
        </div>
        <div id="opt-preferences"></div>
        <button class="btn btn-primary" style="margin-top:10px;width:100%" onclick="saveSettings('preferences')">💾 Save Preferences</button>
      </div>

      <!-- Auto-Update -->
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🔄</span> Auto Update</div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-ghost btn-sm" onclick="checkForUpdates()">🔍 Check Now</button>
            <button class="btn btn-success btn-sm" onclick="triggerUpdate()">⬇ Update Now</button>
          </div>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
          Auto-update runs from GitHub while the system is running. Only changed agents are restarted — the rest stay live.
        </p>
        <div id="opt-updater-status" style="font-size:.84em"></div>
      </div>

      <!-- Security Check -->
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🛡️</span> Security Checklist</div>
          <button class="btn btn-ghost btn-sm" onclick="runSecurityCheck()">↻ Re-run</button>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:4px">
          <strong style="color:var(--text)">Before running in production</strong> — verify all 11 points below.
        </p>
        <ol style="color:var(--text-muted);font-size:.78em;margin:0 0 12px 16px;padding:0;line-height:1.8">
          <li>JWT_SECRET_KEY changed from the default placeholder</li>
          <li>Strong passwords configured</li>
          <li>Application bound to localhost only (or properly secured if networked)</li>
          <li>Rate limiting enabled <code style="font-size:.9em">security.rate_limit_enabled: true</code></li>
          <li>Encryption at rest enabled <code style="font-size:.9em">privacy.encrypt_data_at_rest: true</code></li>
          <li>Telemetry disabled <code style="font-size:.9em">privacy.telemetry_enabled: false</code></li>
          <li>Audit logging enabled <code style="font-size:.9em">logging.audit_enabled: true</code></li>
          <li>Security headers verified <code style="font-size:.9em">curl -I http://127.0.0.1:8787</code></li>
          <li>Dependencies updated <code style="font-size:.9em">pip install -r requirements.txt --upgrade</code></li>
          <li>File permissions secured <code style="font-size:.9em">chmod 600 .env security.local.yml</code></li>
          <li>No secrets committed to version control</li>
        </ol>
        <div id="opt-security-results"><p style="color:var(--text-muted);font-size:.85em">Loading…</p></div>
      </div>

      <!-- Danger Zone -->
      <div class="card" style="border-color:rgba(239,68,68,.35)">
        <div class="card-header">
          <div class="card-title" style="color:var(--danger)"><span class="icon">💣</span> Danger Zone</div>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
          Permanently delete all runtime data — chat logs, metrics, memory, guardrails, improvements.
          Your <code>.env</code> and config files are <strong style="color:var(--text)">not</strong> deleted.
        </p>
        <div class="form-group">
          <label>Type <strong style="color:var(--danger)">DELETE ALL DATA</strong> to confirm</label>
          <input id="nuke-confirm" placeholder="DELETE ALL DATA" style="border-color:rgba(239,68,68,.3)" autocomplete="off"/>
        </div>
        <button class="btn btn-danger" style="width:100%" onclick="nukeData()">🗑️ Delete All Runtime Data</button>
        <div id="nuke-result" style="margin-top:8px;font-size:.82em"></div>
      </div>

      <!-- Delete Complete Installation -->
      <div class="card" style="border-color:rgba(239,68,68,.6);margin-top:0">
        <div class="card-header">
          <div class="card-title" style="color:var(--danger)"><span class="icon">☠️</span> Delete Complete Installation</div>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
          Stops all running agents and <strong style="color:var(--danger)">permanently removes</strong>
          the entire <code>~/.ai-employee</code> installation — all data, config, and code.
          <strong style="color:var(--text)">This cannot be undone.</strong>
        </p>

        <!-- Step 1 -->
        <div id="uninstall-step1">
          <div class="form-group" style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            <input type="checkbox" id="uninstall-check1" style="width:auto;margin:0;cursor:pointer;accent-color:var(--danger)"/>
            <label for="uninstall-check1" style="margin:0;font-size:.86em;cursor:pointer">
              I understand this will <strong style="color:var(--danger)">permanently delete</strong> everything
            </label>
          </div>
          <div class="form-group" style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            <input type="checkbox" id="uninstall-check2" style="width:auto;margin:0;cursor:pointer;accent-color:var(--danger)"/>
            <label for="uninstall-check2" style="margin:0;font-size:.86em;cursor:pointer">
              I have backed up anything I want to keep
            </label>
          </div>
          <button class="btn btn-danger" style="width:100%" onclick="deleteBotStep2()">
            ☠️ Continue to Final Confirmation…
          </button>
        </div>

        <!-- Step 2 (hidden until step 1 passes) -->
        <div id="uninstall-step2" style="display:none;border-top:1px solid rgba(239,68,68,.3);padding-top:14px;margin-top:14px">
          <div class="form-group">
            <label>Type <strong style="color:var(--danger)">UNINSTALL AI EMPLOYEE</strong> to confirm</label>
            <input id="uninstall-confirm" placeholder="UNINSTALL AI EMPLOYEE"
              style="border-color:rgba(239,68,68,.5);background:rgba(239,68,68,.05)"
              autocomplete="off"/>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-ghost btn-sm" style="flex:1" onclick="deleteBotCancel()">↩ Cancel</button>
            <button class="btn btn-danger" style="flex:2" onclick="deleteBotFinal()">
              ☠️ PERMANENTLY DELETE EVERYTHING
            </button>
          </div>
        </div>

        <div id="uninstall-result" style="margin-top:10px;font-size:.82em"></div>
      </div>
    </div>

  </div>

  <!-- ── Theme Customizer ── -->
  <div class="card" style="margin-top:0;border:1px solid rgba(212,175,55,.2);background:linear-gradient(135deg,rgba(212,175,55,.03),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span style="color:var(--gold)">🎨</span> Theme Customizer</div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:16px">Personalize the dashboard appearance. Changes apply instantly without a page reload.</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px">

      <!-- Dark / Light mode -->
      <div>
        <div style="font-size:.78em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">Display Mode</div>
        <div style="display:flex;gap:8px">
          <button id="theme-dark-btn" onclick="setThemeMode('dark')"
            style="flex:1;padding:10px 14px;border-radius:8px;font-size:.84em;font-weight:700;cursor:pointer;font-family:inherit;transition:all .2s;background:linear-gradient(135deg,#0d0d0d,#1a1a1a);color:var(--gold);border:1px solid rgba(212,175,55,.4)">
            🌑 Dark Mode
          </button>
          <button id="theme-light-btn" onclick="setThemeMode('light')"
            style="flex:1;padding:10px 14px;border-radius:8px;font-size:.84em;font-weight:700;cursor:pointer;font-family:inherit;transition:all .2s;background:rgba(255,255,255,.05);color:var(--text-muted);border:1px solid var(--border)">
            ☀️ Light Mode
          </button>
        </div>
      </div>

      <!-- Accent colour -->
      <div>
        <div style="font-size:.78em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">Accent Color</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="theme-accent-btn" onclick="setAccentColor('#D4AF37','#B8960C')" title="Gold (default)"
            class="color-swatch" style="background:#D4AF37"></button>
          <button class="theme-accent-btn" onclick="setAccentColor('#00f0ff','#00c0d0')" title="Cyan"
            class="color-swatch" style="background:#00f0ff"></button>
          <button class="theme-accent-btn" onclick="setAccentColor('#f59e0b','#d97706')" title="Amber"
            class="color-swatch" style="background:#f59e0b"></button>
          <button class="theme-accent-btn" onclick="setAccentColor('#a78bfa','#7c3aed')" title="Purple"
            class="color-swatch" style="background:#a78bfa"></button>
          <button class="theme-accent-btn" onclick="setAccentColor('#34d399','#059669')" title="Emerald"
            class="color-swatch" style="background:#34d399"></button>
          <button class="theme-accent-btn" onclick="setAccentColor('#f87171','#dc2626')" title="Red"
            class="color-swatch" style="background:#f87171"></button>
        </div>
      </div>

      <!-- Font size / density -->
      <div>
        <div style="font-size:.78em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">UI Density</div>
        <div style="display:flex;gap:8px">
          <button onclick="setDensity('compact')" id="density-compact-btn"
            style="flex:1;padding:10px 14px;border-radius:8px;font-size:.82em;font-weight:600;cursor:pointer;font-family:inherit;transition:all .2s;background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)">
            ⊟ Compact
          </button>
          <button onclick="setDensity('normal')" id="density-normal-btn"
            style="flex:1;padding:10px 14px;border-radius:8px;font-size:.82em;font-weight:600;cursor:pointer;font-family:inherit;transition:all .2s;background:rgba(212,175,55,.08);color:var(--gold);border:1px solid rgba(212,175,55,.3)">
            ◻ Normal
          </button>
          <button onclick="setDensity('spacious')" id="density-spacious-btn"
            style="flex:1;padding:10px 14px;border-radius:8px;font-size:.82em;font-weight:600;cursor:pointer;font-family:inherit;transition:all .2s;background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)">
            ⊞ Spacious
          </button>
        </div>
      </div>

    </div>
    <div style="margin-top:14px;font-size:.8em;color:var(--text-muted)" id="theme-save-note">Theme is saved to your browser and persists across sessions.</div>
  </div>
</div>
<div id="tab-blacklight" class="tab-content" style="width:100%;box-sizing:border-box">

  <!-- Header banner -->
  <div style="background:linear-gradient(135deg,#000d1a 0%,#001428 60%,#000a14 100%);border:1px solid #00f0ff;border-radius:14px;padding:24px 28px;margin-bottom:18px;display:flex;align-items:center;gap:18px;position:relative;overflow:hidden;box-shadow:0 0 60px rgba(0,240,255,.15),0 8px 32px rgba(0,0,0,.8)">
    <div style="position:absolute;inset:0;background:radial-gradient(ellipse at 20% 50%,rgba(0,240,255,.12) 0%,transparent 60%);pointer-events:none"></div>
    <div style="position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(0,240,255,.8),transparent)"></div>
    <div style="font-size:2.6rem;line-height:1;animation:blLightning 3s ease-in-out infinite;position:relative;z-index:1">⚡</div>
    <div style="flex:1;position:relative;z-index:1">
      <div style="font-size:1.3rem;font-weight:800;color:#e0f9ff;letter-spacing:.1em;text-shadow:0 0 20px rgba(0,240,255,.7),0 0 40px rgba(0,240,255,.3)">BLACKLIGHT</div>
      <div style="font-size:.83em;color:#00f0ff;margin-top:3px;font-weight:500;opacity:.85">Autonomous money-making agent — runs above Hermes without user input</div>
    </div>
    <div style="display:flex;align-items:center;gap:10px;position:relative;z-index:1">
      <div id="bl-status-dot" style="width:12px;height:12px;border-radius:50%;background:#6b7280;transition:background .4s,box-shadow .4s"></div>
      <span id="bl-status-label" style="font-size:.84em;color:#00f0ff;font-weight:700;letter-spacing:.04em">IDLE</span>
    </div>
  </div>
  <style>
  @keyframes blLightning{0%,90%,100%{opacity:1;filter:drop-shadow(0 0 8px #00f0ff)}5%{opacity:.3;filter:none}10%{opacity:1;filter:drop-shadow(0 0 20px #00f0ff)}15%{opacity:.7}20%{opacity:1;filter:drop-shadow(0 0 12px #00ccff)}}
  .bl-stat-card{background:linear-gradient(135deg,rgba(0,240,255,.06),rgba(0,180,220,.04));border:1px solid rgba(0,240,255,.2);border-radius:var(--radius);padding:16px 18px;display:flex;align-items:center;gap:12px;transition:all .25s}
  .bl-stat-card:hover{border-color:rgba(0,240,255,.5);box-shadow:0 0 20px rgba(0,240,255,.12)}
  @media(prefers-reduced-motion:reduce){[style*="blLightning"],[style*="animation"]{animation:none!important}}
  </style>

  <!-- Control row -->
  <div class="card" style="margin-bottom:18px;border:1px solid rgba(0,240,255,.2);background:linear-gradient(135deg,rgba(0,240,255,.04),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span style="color:#00f0ff">🎯</span> Goal &amp; Control</div>
      <button class="btn btn-ghost btn-sm" onclick="blRefresh()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
      Set a goal, then hit <strong style="color:#00f0ff">Start</strong>. BLACKLIGHT will find opportunities, analyze them with Hermes, generate outreach, and iterate — without waiting for input.
    </p>
    <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
      <div style="flex:1;min-width:220px">
        <label style="font-size:.82em;color:#00f0ff;display:block;margin-bottom:4px;font-weight:600">Goal</label>
        <input id="bl-goal-input" placeholder="e.g. Find local restaurants that need better marketing"
          style="width:100%;box-sizing:border-box;border-color:rgba(0,240,255,.3)" autocomplete="off"/>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding-bottom:2px">
        <label class="toggle" style="width:54px;height:30px" title="Toggle BLACKLIGHT on/off">
          <input type="checkbox" id="bl-toggle" onchange="blToggle(this.checked)"/>
          <span class="slider" style="border-radius:30px"></span>
        </label>
        <span id="bl-toggle-label" style="font-size:.9em;font-weight:700;color:#00f0ff;min-width:52px">OFF</span>
      </div>
    </div>
  </div>

  <!-- Stats row -->
  <div class="grid-stat" style="margin-bottom:18px" id="bl-stat-cards">
    <div class="bl-stat-card">
      <div style="width:40px;height:40px;border-radius:10px;background:rgba(0,240,255,.12);display:flex;align-items:center;justify-content:center;font-size:1.1em">🔄</div>
      <div class="stat-body"><div class="val" id="bl-stat-cycle" style="color:#00f0ff">0</div><div class="lbl">Cycles Run</div></div>
    </div>
    <div class="bl-stat-card">
      <div style="width:40px;height:40px;border-radius:10px;background:rgba(0,240,255,.1);display:flex;align-items:center;justify-content:center;font-size:1.1em">🎯</div>
      <div class="stat-body"><div class="val" id="bl-stat-opps" style="color:#00f0ff">0</div><div class="lbl">Opportunities Found</div></div>
    </div>
    <div class="bl-stat-card">
      <div style="width:40px;height:40px;border-radius:10px;background:rgba(0,240,255,.08);display:flex;align-items:center;justify-content:center;font-size:1.1em">⚡</div>
      <div class="stat-body"><div class="val" id="bl-stat-actions" style="color:#00f0ff">0</div><div class="lbl">Actions Taken</div></div>
    </div>
    <div class="bl-stat-card">
      <div style="width:40px;height:40px;border-radius:10px;background:rgba(0,240,255,.06);display:flex;align-items:center;justify-content:center;font-size:1.1em">🕐</div>
      <div class="stat-body"><div class="val" id="bl-stat-last" style="font-size:.75em;color:#00ccff">—</div><div class="lbl">Last Activity</div></div>
    </div>
  </div>

  <!-- ── BLACKLIGHT Direct Task Composer ── -->
  <div class="card" style="margin-bottom:18px;border:2px solid rgba(0,240,255,.3);background:linear-gradient(135deg,rgba(0,20,40,.9),rgba(0,5,15,.98));box-shadow:0 0 40px rgba(0,240,255,.1)">
    <div class="card-header">
      <div class="card-title"><span style="color:#00f0ff">⚡</span> Direct Task Assignment</div>
      <span style="font-size:.78em;color:#00f0ff;font-weight:600;padding:3px 10px;border-radius:20px;background:rgba(0,240,255,.1);border:1px solid rgba(0,240,255,.3)">INDEPENDENT MODE</span>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      Assign a task directly to BLACKLIGHT — it runs <strong style="color:#00f0ff">independently</strong>, without the main orchestrator. BLACKLIGHT will start immediately and iterate autonomously.
    </p>
    <div style="display:flex;flex-direction:column;gap:10px">
      <textarea id="bl-task-input" rows="3" placeholder="e.g. Find 10 local businesses that need better social media marketing and draft outreach emails&#10;e.g. Identify SaaS companies with weak onboarding and generate improvement proposals&#10;e.g. Scan for e-commerce stores with abandoned cart problems and create solutions"
        style="width:100%;box-sizing:border-box;background:rgba(0,0,0,.7);border:1px solid rgba(0,240,255,.25);border-radius:10px;color:#e0f9ff;padding:12px 16px;font-family:inherit;font-size:.9em;resize:vertical;outline:none;transition:border-color .2s"
        onfocus="this.style.borderColor='rgba(0,240,255,.7)'" onblur="this.style.borderColor='rgba(0,240,255,.25)'"
        onkeydown="if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();blSendTask();}"></textarea>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button onclick="blSendTask()" class="btn btn-swarm">⚡ Launch BLACKLIGHT Task <kbd style="background:rgba(0,0,0,.2);padding:1px 5px;border-radius:4px;font-size:.75em">Ctrl+↵</kbd></button>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(0,240,255,.3);color:#00f0ff" onclick="blFillTask('find local businesses struggling with digital marketing and generate cold outreach sequences')">📣 Lead Outreach</button>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(0,240,255,.3);color:#00f0ff" onclick="blFillTask('identify high-value e-commerce opportunities and generate monetization strategies')">💰 Money Finder</button>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(0,240,255,.3);color:#00f0ff" onclick="blFillTask('research the top 5 competitors in my niche and generate a competitive advantage report')">🔬 Research</button>
      </div>
    </div>
    <!-- Task progress panel -->
    <div id="bl-task-progress-panel" style="margin-top:16px;display:none">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="font-size:.84em;font-weight:700;color:#00f0ff" id="bl-task-status-text">⚡ Launching…</div>
        <div style="font-size:.84em;color:#00ccff;font-weight:700" id="bl-task-pct">0%</div>
      </div>
      <div style="background:rgba(0,0,0,.6);border-radius:100px;height:10px;overflow:hidden;border:1px solid rgba(0,240,255,.15)">
        <div id="bl-task-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#004466,#00a0c0,#00f0ff);border-radius:100px;transition:width .4s ease;box-shadow:0 0 10px rgba(0,240,255,.4)"></div>
      </div>
      <div id="bl-task-result" style="margin-top:8px;font-size:.84em;color:#4ade80;display:none"></div>
    </div>
  </div>

  <!-- Live activity log -->
  <div class="card" style="border:1px solid rgba(0,240,255,.25);background:linear-gradient(135deg,rgba(0,240,255,.04),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span style="color:#00f0ff">📡</span> Live Activity Log</div>
      <button class="btn btn-ghost btn-sm" onclick="blLoadLogs()">↻ Refresh</button>
    </div>
    <div id="bl-log" style="font-family:'JetBrains Mono','Fira Code','Consolas',monospace;font-size:.77em;background:rgba(0,5,12,.95);border:1px solid rgba(0,240,255,.15);border-radius:8px;padding:14px;height:340px;overflow-y:auto;color:#b0f0ff;line-height:1.7;box-shadow:inset 0 0 40px rgba(0,240,255,.05)">
      <span style="color:#4a7080">No activity yet — start BLACKLIGHT to see the live log.</span>
    </div>
  </div>

</div>

<!-- ── ASCEND FORGE ── -->
<div id="tab-ascend" class="tab-content" style="width:100%;box-sizing:border-box">

  <style>
  @keyframes afPulse{0%,100%{box-shadow:0 0 0 0 rgba(217,119,6,.5)}50%{box-shadow:0 0 0 8px rgba(217,119,6,0)}}
  @keyframes forgeFire{0%,100%{filter:drop-shadow(0 0 6px #f59e0b);transform:scale(1)}25%{filter:drop-shadow(0 0 16px #fbbf24);transform:scale(1.05)}50%{filter:drop-shadow(0 0 8px #f97316);transform:scale(.97)}75%{filter:drop-shadow(0 0 20px #f59e0b);transform:scale(1.03)}}
  .af-mode-btn{padding:8px 20px;border-radius:8px;font-size:.82em;font-weight:700;cursor:pointer;transition:all .25s;font-family:inherit;letter-spacing:.05em;text-transform:uppercase}
  .af-mode-btn.active{background:linear-gradient(135deg,#92400e,#b45309,#d97706);color:#fff1c6;border:1px solid #f59e0b;box-shadow:0 0 18px rgba(217,119,6,.5),0 4px 12px rgba(0,0,0,.4)}
  .af-mode-btn:not(.active){background:rgba(217,119,6,.06);color:#d97706;border:1px solid rgba(217,119,6,.25)}
  .af-mode-btn:not(.active):hover{background:rgba(217,119,6,.14);border-color:rgba(217,119,6,.55);color:#f59e0b;transform:translateY(-1px)}
  .af-stat-card{background:linear-gradient(135deg,rgba(120,53,15,.18),rgba(10,5,0,.9));border:1px solid rgba(217,119,6,.22);border-radius:var(--radius);padding:18px 20px;display:flex;align-items:center;gap:14px;transition:all .25s;cursor:default}
  .af-stat-card:hover{border-color:rgba(251,191,36,.45);box-shadow:0 0 24px rgba(217,119,6,.18),0 4px 20px rgba(0,0,0,.4);transform:translateY(-2px)}
  .af-patch-card{border:1px solid rgba(217,119,6,.2);border-radius:10px;padding:14px 16px;margin-bottom:10px;background:linear-gradient(135deg,rgba(120,53,15,.1),rgba(10,5,0,.85));transition:all .2s}
  .af-patch-card:hover{border-color:rgba(251,191,36,.4);box-shadow:0 0 16px rgba(217,119,6,.12)}
  .af-log-card{border:1px solid rgba(30,20,5,.8);border-radius:10px;padding:12px 16px;margin-bottom:8px;background:rgba(10,5,0,.6);transition:all .2s;border-left:3px solid rgba(217,119,6,.3)}
  .af-log-card:hover{background:rgba(20,10,0,.8);border-left-color:#d97706}
  .af-risk-badge{display:inline-block;font-size:.68em;font-weight:800;padding:2px 9px;border-radius:12px;letter-spacing:.06em;text-transform:uppercase}
  @media(prefers-reduced-motion:reduce){.af-mode-btn,.af-stat-card{transition:none}}
  </style>

  <!-- Header banner -->
  <div style="background:linear-gradient(135deg,#0a0802 0%,#1a0e05 50%,#0d0a00 100%);border:1px solid rgba(217,119,6,.55);border-radius:14px;padding:24px 28px;margin-bottom:18px;display:flex;align-items:center;gap:18px;position:relative;overflow:hidden;box-shadow:0 0 60px rgba(217,119,6,.14),0 8px 40px rgba(0,0,0,.7)">
    <div style="position:absolute;inset:0;background:radial-gradient(ellipse at 15% 50%,rgba(217,119,6,.22) 0%,transparent 55%);pointer-events:none"></div>
    <div style="position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(251,191,36,.6),transparent)"></div>
    <div style="font-size:2.8rem;line-height:1;animation:forgeFire 2s ease-in-out infinite;position:relative;z-index:1">🔥</div>
    <div style="flex:1;position:relative;z-index:1">
      <div style="font-size:1.45rem;font-weight:800;color:#fef3c7;letter-spacing:.12em;text-shadow:0 0 28px rgba(251,191,36,.5),0 2px 4px rgba(0,0,0,.8);font-family:var(--display)">ASCEND FORGE</div>
      <div style="font-size:.82em;color:#d97706;margin-top:4px;font-weight:500;letter-spacing:.02em">Top-layer self-improver — continuously improves the system safely</div>
    </div>
    <div style="display:flex;align-items:center;gap:10px;position:relative;z-index:1">
      <div id="af-pulse" style="width:11px;height:11px;border-radius:50%;background:#d97706;animation:afPulse 2s ease-in-out infinite"></div>
      <span id="af-mode-badge" style="font-size:.75em;font-weight:800;padding:4px 14px;border-radius:20px;background:linear-gradient(135deg,#92400e,#b45309,#d97706);color:#fff1c6;letter-spacing:.1em;text-transform:uppercase;box-shadow:0 0 14px rgba(217,119,6,.45)">AUTO</span>
      <button onclick="switchTab('chat',null)" class="btn btn-gold btn-sm">← Overview</button>
    </div>
  </div>

  <!-- ── Ascend Forge Task Composer ── -->
  <div class="card" style="margin-bottom:18px;border:2px solid rgba(251,191,36,.35);background:linear-gradient(135deg,rgba(120,53,15,.18),rgba(10,5,0,.95));box-shadow:0 0 40px rgba(217,119,6,.12)">
    <div class="card-header">
      <div class="card-title"><span style="color:#fbbf24">⚡</span> Direct Task Assignment</div>
      <span style="font-size:.78em;color:#f59e0b;font-weight:600;padding:3px 10px;border-radius:20px;background:rgba(217,119,6,.15);border:1px solid rgba(217,119,6,.3)">INDEPENDENT MODE</span>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      Assign tasks directly to Ascend Forge — it works <strong style="color:#fbbf24">independently</strong>, without going through the main orchestrator. Tasks run in the background immediately.
    </p>
    <div style="display:flex;flex-direction:column;gap:10px">
      <textarea id="af-task-input" rows="3" placeholder="e.g. Optimize all AI prompts for better revenue generation&#10;e.g. Scan for code improvements and apply low-risk patches automatically&#10;e.g. Improve the agent response quality for sales tasks"
        style="width:100%;box-sizing:border-box;background:rgba(0,0,0,.6);border:1px solid rgba(251,191,36,.3);border-radius:10px;color:#fef3c7;padding:12px 16px;font-family:inherit;font-size:.9em;resize:vertical;outline:none;transition:border-color .2s"
        onfocus="this.style.borderColor='rgba(251,191,36,.7)'" onblur="this.style.borderColor='rgba(251,191,36,.3)'"
        onkeydown="if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();afSendTask();}"></textarea>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button onclick="afSendTask()" class="btn btn-swarm">🔥 Send to Ascend Forge <kbd style="background:rgba(0,0,0,.2);padding:1px 5px;border-radius:4px;font-size:.75em">Ctrl+↵</kbd></button>
        <button onclick="afAnalyzeOnly()" class="btn btn-ghost btn-sm" style="border-color:rgba(251,191,36,.45);color:#fbbf24;font-weight:700" title="Analyze the prompt and show a structured plan — without queuing any patches">🗺 Plan Only</button>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(217,119,6,.3);color:#f59e0b" onclick="afFillTask('optimize all AI prompts for higher revenue and better output quality')">💰 Optimize Prompts</button>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(217,119,6,.3);color:#f59e0b" onclick="afFillTask('scan system for improvements and automatically apply all low-risk patches')">🔍 Auto-Improve</button>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(217,119,6,.3);color:#f59e0b" onclick="afFillTask('analyze all agent modules and improve their performance and reliability')">🤖 Boost Agents</button>
      </div>
    </div>
    <!-- Live progress panel -->
    <div id="af-task-progress-panel" style="margin-top:16px;display:none">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="font-size:.84em;font-weight:700;color:#fbbf24" id="af-task-status-text">🔥 Running task…</div>
        <div style="font-size:.84em;color:#f59e0b;font-weight:700" id="af-task-pct">0%</div>
      </div>
      <div style="background:rgba(0,0,0,.5);border-radius:100px;height:10px;overflow:hidden;border:1px solid rgba(217,119,6,.2)">
        <div id="af-task-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#92400e,#d97706,#fbbf24);border-radius:100px;transition:width .4s ease;box-shadow:0 0 10px rgba(251,191,36,.4)"></div>
      </div>
      <div id="af-task-desc" style="margin-top:8px;font-size:.8em;color:var(--text-muted);font-style:italic"></div>
      <div id="af-task-result" style="margin-top:8px;font-size:.84em;color:#4ade80;display:none;white-space:pre-wrap;line-height:1.65"></div>
    </div>
  </div>

  <!-- Mode + controls -->
  <div class="card" style="margin-bottom:18px;border:1px solid rgba(217,119,6,.2);background:linear-gradient(135deg,rgba(120,53,15,.1),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span style="color:#f59e0b">⚙️</span> Mode &amp; Controls</div>
      <button class="btn btn-ghost btn-sm" onclick="afRefresh()">↻ Refresh</button>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px">
      <button class="af-mode-btn" id="af-mode-general" onclick="afSetMode('GENERAL')">🛠 GENERAL</button>
      <button class="af-mode-btn" id="af-mode-money"   onclick="afSetMode('MONEY')">💰 MONEY</button>
      <button class="af-mode-btn active" id="af-mode-auto" onclick="afSetMode('AUTO')">🤖 AUTO</button>
      <div style="margin-left:auto;display:flex;align-items:center;gap:8px">
        <label style="font-size:.82em;color:var(--text-muted)">Auto-approve LOW risk:</label>
        <label class="toggle" style="width:44px;height:24px">
          <input type="checkbox" id="af-auto-approve" onchange="afSetAutoApprove(this.checked)"/>
          <span class="slider" style="border-radius:24px"></span>
        </label>
      </div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button onclick="afScan()" class="btn btn-swarm btn-sm">🔍 Scan System</button>
      <button class="btn btn-ghost btn-sm" style="border-color:rgba(217,119,6,.3);color:#f59e0b" onclick="afShowPending()">📋 Show Pending</button>
      <button class="btn btn-ghost btn-sm" style="border-color:rgba(217,119,6,.3);color:#f59e0b" onclick="afApplyAllLow()">✅ Apply All LOW</button>
      <button class="btn btn-ghost btn-sm" style="color:#ef4444" onclick="afCancelAll()">🗑 Cancel All</button>
    </div>
    <div id="af-current-activity" style="margin-top:12px;font-size:.82em;color:var(--text-muted)">Activity: idle</div>
    <div id="af-current-target"   style="font-size:.82em;color:var(--text-muted)">Target: —</div>
  </div>

  <!-- Stats -->
  <div class="grid-stat" style="margin-bottom:18px">
    <div class="af-stat-card">
      <div style="width:40px;height:40px;border-radius:10px;background:rgba(217,119,6,.2);display:flex;align-items:center;justify-content:center;font-size:1.1em">📋</div>
      <div class="stat-body"><div class="val" id="af-stat-pending" style="color:#f59e0b">0</div><div class="lbl">Pending</div></div>
    </div>
    <div class="af-stat-card">
      <div style="width:40px;height:40px;border-radius:10px;background:rgba(74,222,128,.12);display:flex;align-items:center;justify-content:center;font-size:1.1em">✅</div>
      <div class="stat-body"><div class="val" id="af-stat-approved" style="color:#4ade80">0</div><div class="lbl">Approved</div></div>
    </div>
    <div class="af-stat-card">
      <div style="width:40px;height:40px;border-radius:10px;background:rgba(239,68,68,.12);display:flex;align-items:center;justify-content:center;font-size:1.1em">❌</div>
      <div class="stat-body"><div class="val" id="af-stat-rejected" style="color:#ef4444">0</div><div class="lbl">Rejected</div></div>
    </div>
    <div class="af-stat-card">
      <div style="width:40px;height:40px;border-radius:10px;background:rgba(148,163,184,.08);display:flex;align-items:center;justify-content:center;font-size:1.1em">📚</div>
      <div class="stat-body"><div class="val" id="af-stat-total">0</div><div class="lbl">Total Patches</div></div>
    </div>
  </div>

  <!-- Pending patches -->
  <div class="card" style="margin-bottom:18px;border:1px solid rgba(217,119,6,.22);background:linear-gradient(135deg,rgba(120,53,15,.1),var(--surface))">
    <div class="card-header">
      <div class="card-title"><span style="color:#f59e0b">⏳</span> Pending Patches</div>
      <button class="btn btn-ghost btn-sm" style="border-color:rgba(217,119,6,.3);color:#d97706" onclick="afLoadPatches()">↻ Refresh</button>
    </div>
    <div id="af-patches-list">
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:36px 20px;gap:12px;opacity:.6">
        <div style="font-size:2.2em">📋</div>
        <div style="font-size:.88em;color:var(--text-muted);text-align:center">No pending patches — run a scan to find improvements.</div>
        <button onclick="afScan()" class="btn btn-gold btn-sm" style="margin-top:4px">🔍 Run Scan Now</button>
      </div>
    </div>
  </div>

  <!-- Two-column bottom section -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:0">

    <!-- Activity feed -->
    <div class="card" style="border:1px solid rgba(217,119,6,.2);background:linear-gradient(135deg,rgba(120,53,15,.08),var(--surface2))">
      <div class="card-header">
        <div class="card-title"><span style="color:#f59e0b">📡</span> Activity Feed</div>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(217,119,6,.3);color:#d97706" onclick="afRefresh()">↻ Refresh</button>
      </div>
      <div id="af-activity-log" style="font-family:var(--mono);font-size:.75em;background:rgba(6,3,0,.92);border:1px solid rgba(217,119,6,.18);border-radius:8px;padding:14px;height:240px;overflow-y:auto;color:#fef3c7;line-height:1.75;box-shadow:inset 0 0 40px rgba(120,53,15,.25)">
        <div style="display:flex;align-items:center;gap:8px;color:rgba(107,114,128,.7);padding:4px 0">
          <span style="width:6px;height:6px;border-radius:50%;background:rgba(107,114,128,.4);display:inline-block;flex-shrink:0"></span>
          Waiting for activity…
        </div>
      </div>
    </div>

    <!-- Change history -->
    <div class="card" style="border:1px solid rgba(217,119,6,.2);background:linear-gradient(135deg,rgba(120,53,15,.08),var(--surface2))">
      <div class="card-header">
        <div class="card-title"><span style="color:#f59e0b">🕐</span> Change History</div>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(217,119,6,.3);color:#d97706" onclick="afLoadChangelog()">↻ Refresh</button>
      </div>
      <div id="af-changelog" style="max-height:240px;overflow-y:auto">
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:36px 20px;gap:10px;opacity:.55">
          <div style="font-size:2em">📚</div>
          <div style="font-size:.84em;color:var(--text-muted)">No history yet.</div>
        </div>
      </div>
    </div>

  </div>

</div>

<!-- ── CRM ── -->
<div id="tab-crm" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🎯</div>
    <div><div class="page-header-title">Lead CRM</div><div class="page-header-desc">Manage your sales pipeline from first contact to closed deal. Score leads, track stages, and schedule follow-ups.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Sales Pipeline</span>
  </div>
  <div class="grid-stat" id="crm-pipeline-stats">
    <div class="stat-card"><div class="stat-icon yellow">🆕</div><div class="stat-body"><div class="val" id="crm-stat-new">–</div><div class="lbl">New Leads</div></div></div>
    <div class="stat-card"><div class="stat-icon blue">✅</div><div class="stat-body"><div class="val" id="crm-stat-qualified">–</div><div class="lbl">Qualified</div></div></div>
    <div class="stat-card"><div class="stat-icon cyan">📄</div><div class="stat-body"><div class="val" id="crm-stat-proposal">–</div><div class="lbl">Proposal Sent</div></div></div>
    <div class="stat-card"><div class="stat-icon green">🤝</div><div class="stat-body"><div class="val" id="crm-stat-won">–</div><div class="lbl">Closed Won</div></div></div>
  </div>
  <div class="grid2" style="align-items:start">
    <!-- Pipeline kanban -->
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🎯</span> Pipeline</div>
        <button class="btn btn-ghost btn-sm" onclick="loadCRM()">↻ Refresh</button>
      </div>
      <div id="crm-pipeline-kanban" style="display:flex;flex-direction:column;gap:10px"></div>
    </div>
    <!-- Add lead form + lead list -->
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="card card-accent">
        <div class="card-header">
          <div class="card-title"><span class="icon">➕</span> Add Lead</div>
        </div>
        <div class="form-group"><label>Name *</label><input id="crm-name" placeholder="Contact name"/></div>
        <div class="form-group"><label>Company</label><input id="crm-company" placeholder="Company name"/></div>
        <div class="form-group"><label>Email</label><input id="crm-email" type="email" placeholder="email@example.com"/></div>
        <div class="form-group"><label>Phone</label><input id="crm-phone" placeholder="+1 555-0000"/></div>
        <div class="form-group"><label>Deal Value ($)</label><input id="crm-value" type="number" min="0" placeholder="0"/></div>
        <div class="form-group"><label>Source</label><input id="crm-source" placeholder="LinkedIn, Referral, Website…"/></div>
        <div class="form-group"><label>Notes</label><textarea id="crm-notes" rows="2" class="field-full" placeholder="Initial notes…"></textarea></div>
        <button class="btn btn-primary" onclick="addCRMLead()" style="width:100%">➕ Add Lead</button>
        <div id="crm-add-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">👥</span> All Leads</div>
          <input id="crm-search" placeholder="🔍 Search leads…" oninput="loadCRM()" style="font-size:.8em;padding:4px 8px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);width:140px"/>
        </div>
        <div id="crm-leads-list"><div class="empty"><div class="icon">🎯</div><p>No leads yet. Add your first lead.</p></div></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Email Marketing ── -->
<div id="tab-email-mkt" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📧</div>
    <div><div class="page-header-title">Email Marketing</div><div class="page-header-desc">Create and manage email campaigns, multi-step sequences, and track performance metrics.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Campaigns</span>
  </div>
  <div class="grid-stat">
    <div class="stat-card"><div class="stat-icon blue">📧</div><div class="stat-body"><div class="val" id="em-stat-total">–</div><div class="lbl">Total Campaigns</div></div></div>
    <div class="stat-card"><div class="stat-icon green">✅</div><div class="stat-body"><div class="val" id="em-stat-sent">–</div><div class="lbl">Sent</div></div></div>
    <div class="stat-card"><div class="stat-icon yellow">📝</div><div class="stat-body"><div class="val" id="em-stat-draft">–</div><div class="lbl">Drafts</div></div></div>
    <div class="stat-card"><div class="stat-icon cyan">📊</div><div class="stat-body"><div class="val" id="em-stat-open-rate">–</div><div class="lbl">Avg Open Rate</div></div></div>
  </div>
  <div class="grid2" style="align-items:start">
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Campaign list -->
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">📧</span> Campaigns</div>
          <button class="btn btn-ghost btn-sm" onclick="loadEmailCampaigns()">↻ Refresh</button>
        </div>
        <div id="em-campaigns-list"><div class="empty"><div class="icon">📧</div><p>No campaigns yet.</p></div></div>
      </div>
      <!-- Campaign stats panel -->
      <div class="card" id="em-stats-card" style="display:none">
        <div class="card-header">
          <div class="card-title"><span class="icon">📊</span> Campaign Stats</div>
          <button class="btn btn-ghost btn-sm" onclick="document.getElementById('em-stats-card').style.display='none'">✕</button>
        </div>
        <div id="em-stats-body"></div>
      </div>
      <!-- Deliverability tips -->
      <div class="card card-gold">
        <div class="card-header"><div class="card-title"><span class="icon">🛡️</span> Deliverability Tips</div></div>
        <div id="em-tips-list" style="font-size:.84em"></div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Create campaign form -->
      <div class="card card-gold">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Create Campaign</div></div>
        <div class="form-group"><label>Campaign Name *</label><input id="em-camp-name" placeholder="e.g. Q1 Outreach"/></div>
        <div class="form-group"><label>From Name</label><input id="em-from-name" placeholder="Your Name / Company"/></div>
        <div class="form-group"><label>Subject Line *</label><input id="em-subject" placeholder="Email subject line"/></div>
        <div class="form-group"><label>Email Body *</label><textarea id="em-body" rows="5" class="field-full" placeholder="Email body content…"></textarea></div>
        <button class="btn btn-primary" onclick="createEmailCampaign()" style="width:100%">📧 Create Campaign</button>
        <div id="em-create-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
      <!-- AI Email Writer -->
      <div class="card card-ai">
        <div class="card-header"><div class="card-title"><span style="color:var(--gold)">◈</span> AI Email Writer</div></div>
        <div class="form-group"><label>Campaign Goal</label><input id="em-write-goal" placeholder="e.g. Book a discovery call"/></div>
        <div class="form-group"><label>Tone</label>
          <select id="em-write-tone" >
            <option value="professional">Professional</option>
            <option value="friendly">Friendly</option>
            <option value="urgent">Urgent</option>
            <option value="conversational">Conversational</option>
          </select>
        </div>
        <div class="form-group"><label>Target Audience</label><input id="em-write-audience" placeholder="e.g. SaaS founders"/></div>
        <button class="btn btn-gold" onclick="aiWriteEmail()" style="width:100%">◈ Generate Email</button>
        <div id="em-write-result" style="margin-top:10px;font-size:.84em"></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Meetings ── -->
<div id="tab-meetings" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🗓️</div>
    <div><div class="page-header-title">Meeting Intelligence</div><div class="page-header-desc">Record meetings, AI-summarize transcripts, extract action items, and generate follow-up emails automatically.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Meetings</span>
  </div>
  <div class="grid2" style="align-items:start">
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🗓️</span> Meetings</div>
          <button class="btn btn-ghost btn-sm" onclick="loadMeetings()">↻ Refresh</button>
        </div>
        <div id="meetings-list"><div class="empty"><div class="icon">🗓️</div><p>No meetings recorded yet.</p></div></div>
      </div>
      <!-- Meeting detail -->
      <div class="card" id="meeting-detail-card" style="display:none">
        <div class="card-header">
          <div class="card-title"><span class="icon">📋</span> Meeting Detail</div>
          <button class="btn btn-ghost btn-sm" onclick="document.getElementById('meeting-detail-card').style.display='none'">✕</button>
        </div>
        <div id="meeting-detail-body"></div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="card card-gold">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Add Meeting</div></div>
        <div class="form-group"><label>Title *</label><input id="mtg-title" placeholder="e.g. Q1 Strategy Review"/></div>
        <div class="form-group"><label>Date</label><input id="mtg-date" type="datetime-local"/></div>
        <div class="form-group"><label>Participants (comma-separated)</label><input id="mtg-participants" placeholder="Alice, Bob, Carol"/></div>
        <div class="form-group"><label>Meeting Type</label>
          <select id="mtg-type" >
            <option value="general">General</option>
            <option value="sales">Sales</option>
            <option value="strategy">Strategy</option>
            <option value="1on1">1-on-1</option>
            <option value="review">Review</option>
            <option value="kickoff">Kickoff</option>
          </select>
        </div>
        <div class="form-group"><label>Transcript / Notes</label><textarea id="mtg-transcript" rows="6" class="field-full" placeholder="Paste meeting transcript or notes here…"></textarea></div>
        <button class="btn btn-primary" onclick="addMeeting()" style="width:100%">🗓️ Save Meeting</button>
        <div id="mtg-add-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Social Media Scheduler ── -->
<div id="tab-social" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📱</div>
    <div><div class="page-header-title">Social Media Scheduler</div><div class="page-header-desc">Schedule posts across all platforms, generate AI content, and track your publishing activity.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Social</span>
  </div>
  <div class="grid-stat">
    <div class="stat-card"><div class="stat-icon blue">📅</div><div class="stat-body"><div class="val" id="soc-stat-scheduled">–</div><div class="lbl">Scheduled</div></div></div>
    <div class="stat-card"><div class="stat-icon green">✅</div><div class="stat-body"><div class="val" id="soc-stat-posted">–</div><div class="lbl">Posted</div></div></div>
    <div class="stat-card"><div class="stat-icon yellow">📝</div><div class="stat-body"><div class="val" id="soc-stat-draft">–</div><div class="lbl">Drafts</div></div></div>
    <div class="stat-card"><div class="stat-icon cyan">📊</div><div class="stat-body"><div class="val" id="soc-stat-total">–</div><div class="lbl">Total Posts</div></div></div>
  </div>
  <div class="grid2" style="align-items:start">
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">📅</span> Scheduled Posts</div>
          <div style="display:flex;gap:6px">
            <select id="soc-filter-platform" style="font-size:.8em" onchange="loadSocialPosts()">
              <option value="">All Platforms</option>
              <option value="twitter">Twitter/X</option>
              <option value="instagram">Instagram</option>
              <option value="linkedin">LinkedIn</option>
              <option value="tiktok">TikTok</option>
              <option value="facebook">Facebook</option>
              <option value="youtube">YouTube</option>
            </select>
            <button class="btn btn-ghost btn-sm" onclick="loadSocialPosts()">↻</button>
            <button class="btn btn-ghost btn-sm" onclick="processScheduledPosts()">▶ Auto-Post</button>
          </div>
        </div>
        <div id="social-posts-list"><div class="empty"><div class="icon">📱</div><p>No posts scheduled yet.</p></div></div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Schedule post form -->
      <div class="card card-gold">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Schedule Post</div></div>
        <div class="form-group"><label>Platform *</label>
          <select id="soc-platform" >
            <option value="twitter">Twitter/X</option>
            <option value="instagram">Instagram</option>
            <option value="linkedin">LinkedIn</option>
            <option value="tiktok">TikTok</option>
            <option value="facebook">Facebook</option>
            <option value="youtube">YouTube</option>
          </select>
        </div>
        <div class="form-group"><label>Content *</label><textarea id="soc-content" rows="4" class="field-full" placeholder="Post content…"></textarea></div>
        <div class="form-group"><label>Schedule At *</label><input id="soc-schedule-at" type="datetime-local"/></div>
        <div class="form-group"><label>Campaign (optional)</label><input id="soc-campaign" placeholder="Campaign name"/></div>
        <button class="btn btn-primary" onclick="schedulePost()" style="width:100%">📅 Schedule Post</button>
        <div id="soc-add-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
      <!-- AI Content Generator -->
      <div class="card card-ai">
        <div class="card-header"><div class="card-title"><span style="color:var(--gold)">◈</span> AI Content Generator</div></div>
        <div class="form-group"><label>Topic / Goal</label><input id="soc-gen-topic" placeholder="e.g. Product launch announcement"/></div>
        <div class="form-group"><label>Platform</label>
          <select id="soc-gen-platform" >
            <option value="twitter">Twitter/X</option><option value="instagram">Instagram</option>
            <option value="linkedin">LinkedIn</option><option value="tiktok">TikTok</option>
          </select>
        </div>
        <button class="btn btn-primary" onclick="generateSocialContent()" style="width:100%;background:linear-gradient(135deg,#0d0d0d,#1a1a1a);color:var(--gold);border:1px solid rgba(212,175,55,.4)">◈ Generate Content</button>
        <div id="soc-gen-result" style="margin-top:10px;font-size:.84em"></div>
      </div>
    </div>
  </div>
</div>

<!-- ── CEO Briefing ── -->
<div id="tab-briefing" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">📰</div>
    <div><div class="page-header-title">CEO Daily Briefing</div><div class="page-header-desc">AI-generated executive briefings with key metrics, pipeline status, revenue, and action items for the day.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Executive</span>
  </div>
  <div class="grid2" style="align-items:start">
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Today's briefing -->
      <div class="card" style="border:1px solid rgba(212,175,55,.25);background:linear-gradient(135deg,rgba(212,175,55,.06),var(--surface2))">
        <div class="card-header">
          <div class="card-title"><span class="icon">📰</span> Today's Briefing</div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-ghost btn-sm" onclick="loadFullBriefing()">↻ Refresh</button>
            <button class="btn btn-ghost btn-sm" onclick="forceRegenerateBriefing()">⚡ Regenerate</button>
          </div>
        </div>
        <div id="briefing-today-body"><div class="empty"><div class="icon">📰</div><p>Loading briefing…</p></div></div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Briefing history -->
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🕐</span> Briefing History</div>
          <button class="btn btn-ghost btn-sm" onclick="loadBriefingHistory()">↻ Refresh</button>
        </div>
        <div id="briefing-history-list"><div class="empty"><div class="icon">📰</div><p>No past briefings.</p></div></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Financial Tools ── -->
<div id="tab-financial" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">💳</div>
    <div><div class="page-header-title">Financial Tools</div><div class="page-header-desc">Create and manage invoices, quotes, track expenses, and view your P&amp;L in one place.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Finance</span>
  </div>
  <!-- Sub-tab nav -->
  <div style="display:flex;gap:6px;margin-bottom:16px">
    <button class="fin-tab-btn btn btn-primary btn-sm active" onclick="switchFinTab('invoices',this)">🧾 Invoices</button>
    <button class="fin-tab-btn btn btn-ghost btn-sm" onclick="switchFinTab('quotes',this)">📄 Quotes</button>
    <button class="fin-tab-btn btn btn-ghost btn-sm" onclick="switchFinTab('expenses',this)">💸 Expenses</button>
    <button class="fin-tab-btn btn btn-ghost btn-sm" onclick="switchFinTab('pl',this)">📊 P&amp;L</button>
  </div>

  <!-- Invoices panel -->
  <div id="fin-panel-invoices">
    <div class="grid2" style="align-items:start">
      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="card">
          <div class="card-header">
            <div class="card-title"><span class="icon">🧾</span> Invoices</div>
            <div style="display:flex;gap:6px">
              <select id="inv-filter-status" style="font-size:.8em" onchange="loadInvoices()">
                <option value="">All</option><option value="draft">Draft</option>
                <option value="sent">Sent</option><option value="paid">Paid</option>
                <option value="overdue">Overdue</option>
              </select>
              <button class="btn btn-ghost btn-sm" onclick="loadInvoices()">↻</button>
              <button class="btn btn-ghost btn-sm" onclick="checkOverdueInvoices()">⚠️ Check Overdue</button>
            </div>
          </div>
          <div id="invoices-list"><div class="empty"><div class="icon">🧾</div><p>No invoices yet.</p></div></div>
        </div>
      </div>
      <div class="card" style="border:1px solid rgba(16,185,129,.3)">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Create Invoice</div></div>
        <div class="form-group"><label>Client Name *</label><input id="inv-client" placeholder="Client name"/></div>
        <div class="form-group"><label>Client Email</label><input id="inv-email" type="email" placeholder="client@example.com"/></div>
        <div class="form-group"><label>Items (JSON)</label>
          <textarea id="inv-items" rows="4" class="field-full" placeholder='[{"description":"Service","qty":1,"unit_price":500}]'></textarea>
        </div>
        <div class="form-group"><label>Due Date</label><input id="inv-due" type="date"/></div>
        <div class="form-group"><label>Notes</label><input id="inv-notes" placeholder="Optional notes"/></div>
        <button class="btn btn-primary" onclick="createInvoice()" style="width:100%">🧾 Create Invoice</button>
        <div id="inv-create-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
    </div>
  </div>

  <!-- Quotes panel -->
  <div id="fin-panel-quotes" style="display:none">
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">📄</span> Quotes</div>
          <button class="btn btn-ghost btn-sm" onclick="loadQuotes()">↻ Refresh</button>
        </div>
        <div id="quotes-list"><div class="empty"><div class="icon">📄</div><p>No quotes yet.</p></div></div>
      </div>
      <div class="card" style="border:1px solid rgba(16,185,129,.3)">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Create Quote</div></div>
        <div class="form-group"><label>Client Name *</label><input id="quo-client" placeholder="Client name"/></div>
        <div class="form-group"><label>Client Email</label><input id="quo-email" type="email" placeholder="client@example.com"/></div>
        <div class="form-group"><label>Items (JSON)</label>
          <textarea id="quo-items" rows="4" class="field-full" placeholder='[{"description":"Consulting","qty":10,"unit_price":150}]'></textarea>
        </div>
        <div class="form-group"><label>Valid Until</label><input id="quo-valid" type="date"/></div>
        <button class="btn btn-primary" onclick="createQuote()" style="width:100%">📄 Create Quote</button>
        <div id="quo-create-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
    </div>
  </div>

  <!-- Expenses panel -->
  <div id="fin-panel-expenses" style="display:none">
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">💸</span> Expenses</div>
          <button class="btn btn-ghost btn-sm" onclick="loadExpenses()">↻ Refresh</button>
        </div>
        <div id="expenses-list"><div class="empty"><div class="icon">💸</div><p>No expenses recorded yet.</p></div></div>
      </div>
      <div class="card" style="border:1px solid rgba(16,185,129,.3)">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Add Expense</div></div>
        <div class="form-group"><label>Description *</label><input id="exp-desc" placeholder="e.g. AWS hosting"/></div>
        <div class="form-group"><label>Amount ($) *</label><input id="exp-amount" type="number" step="0.01" min="0" placeholder="0.00"/></div>
        <div class="form-group"><label>Category</label>
          <select id="exp-category" >
            <option value="general">General</option><option value="software">Software/SaaS</option>
            <option value="hosting">Hosting/Infrastructure</option><option value="marketing">Marketing</option>
            <option value="payroll">Payroll</option><option value="office">Office</option>
            <option value="travel">Travel</option><option value="equipment">Equipment</option>
          </select>
        </div>
        <div class="form-group"><label>Date</label><input id="exp-date" type="date"/></div>
        <button class="btn btn-primary" onclick="addExpense()" style="width:100%">💸 Add Expense</button>
        <div id="exp-add-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
    </div>
  </div>

  <!-- P&L panel -->
  <div id="fin-panel-pl" style="display:none">
    <div class="card" style="border:1px solid rgba(16,185,129,.3);background:linear-gradient(135deg,rgba(16,185,129,.05),var(--surface2))">
      <div class="card-header">
        <div class="card-title"><span class="icon">📊</span> Profit &amp; Loss</div>
        <button class="btn btn-ghost btn-sm" onclick="loadPL()">↻ Refresh</button>
      </div>
      <div id="pl-body"><div class="empty"><div class="icon">📊</div><p>Loading P&amp;L data…</p></div></div>
    </div>
  </div>
</div>

<!-- ── Competitors ── -->
<div id="tab-competitors" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🕵️</div>
    <div><div class="page-header-title">Competitor Watch</div><div class="page-header-desc">Track and analyze your competitive landscape. AI-powered SWOT analysis and competitive intelligence alerts.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Intelligence</span>
  </div>
  <div class="grid2" style="align-items:start">
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🕵️</span> Tracked Competitors</div>
          <button class="btn btn-ghost btn-sm" onclick="loadCompetitors()">↻ Refresh</button>
        </div>
        <div id="competitors-list"><div class="empty"><div class="icon">🕵️</div><p>No competitors tracked yet.</p></div></div>
      </div>
      <div class="card" style="border:1px solid rgba(244,63,94,.2)">
        <div class="card-header">
          <div class="card-title"><span class="icon">🚨</span> Alerts</div>
          <button class="btn btn-ghost btn-sm" onclick="loadCompetitorAlerts()">↻ Refresh</button>
        </div>
        <div id="competitor-alerts-list"><div class="empty"><div class="icon">🚨</div><p>No alerts yet.</p></div></div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="card" style="border:1px solid rgba(244,63,94,.3)">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Track Competitor</div></div>
        <div class="form-group"><label>Competitor Name *</label><input id="comp-name" placeholder="Competitor name"/></div>
        <div class="form-group"><label>Website</label><input id="comp-website" placeholder="https://competitor.com"/></div>
        <div class="form-group"><label>Their Pricing</label><input id="comp-pricing" placeholder="e.g. $99/mo freemium"/></div>
        <div class="form-group"><label>Target Market</label><input id="comp-market" placeholder="e.g. SMB SaaS companies"/></div>
        <div class="form-group"><label>Notes</label><textarea id="comp-notes" rows="3" class="field-full" placeholder="Initial observations…"></textarea></div>
        <button class="btn btn-primary" onclick="addCompetitor()" style="width:100%">🕵️ Track Competitor</button>
        <div id="comp-add-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
      <!-- Competitor detail -->
      <div class="card" id="comp-detail-card" style="display:none">
        <div class="card-header">
          <div class="card-title"><span class="icon">🔍</span> Analysis</div>
          <button class="btn btn-ghost btn-sm" onclick="document.getElementById('comp-detail-card').style.display='none'">✕</button>
        </div>
        <div id="comp-detail-body"></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Content Calendar ── -->
<div id="tab-content-calendar" class="tab-content">
  <div class="page-header" style="border-left-color:var(--gold)">
    <div class="page-header-icon">🗃️</div>
    <div><div class="page-header-title">Content Calendar</div><div class="page-header-desc">Plan and track your content across all platforms. AI generates complete 30-day content calendars tailored to your niche.</div></div>
    <span class="page-header-badge" style="color:var(--gold)">Content</span>
  </div>
  <div class="grid-stat">
    <div class="stat-card"><div class="stat-icon blue">📅</div><div class="stat-body"><div class="val" id="cc-stat-total">–</div><div class="lbl">Total Entries</div></div></div>
    <div class="stat-card"><div class="stat-icon yellow">💡</div><div class="stat-body"><div class="val" id="cc-stat-ideas">–</div><div class="lbl">Ideas</div></div></div>
    <div class="stat-card"><div class="stat-icon cyan">📅</div><div class="stat-body"><div class="val" id="cc-stat-scheduled">–</div><div class="lbl">Scheduled</div></div></div>
    <div class="stat-card"><div class="stat-icon green">✅</div><div class="stat-body"><div class="val" id="cc-stat-published">–</div><div class="lbl">Published</div></div></div>
  </div>
  <div class="grid2" style="align-items:start">
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🗃️</span> Content Calendar</div>
          <div style="display:flex;gap:6px">
            <select id="cc-filter-platform" style="font-size:.8em" onchange="loadContentCalendar()">
              <option value="">All Platforms</option>
              <option value="instagram">Instagram</option><option value="twitter">Twitter</option>
              <option value="linkedin">LinkedIn</option><option value="tiktok">TikTok</option>
              <option value="youtube">YouTube</option><option value="blog">Blog</option>
            </select>
            <select id="cc-filter-status" style="font-size:.8em" onchange="loadContentCalendar()">
              <option value="">All Status</option>
              <option value="idea">Idea</option><option value="draft">Draft</option>
              <option value="scheduled">Scheduled</option><option value="published">Published</option>
            </select>
            <button class="btn btn-ghost btn-sm" onclick="loadContentCalendar()">↻</button>
          </div>
        </div>
        <div id="content-calendar-entries"></div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Add entry form -->
      <div class="card" style="border:1px solid rgba(249,115,22,.3)">
        <div class="card-header"><div class="card-title"><span class="icon">➕</span> Add Entry</div></div>
        <div class="form-group"><label>Date *</label><input id="cc-date" type="date"/></div>
        <div class="form-group"><label>Platform *</label>
          <select id="cc-platform" >
            <option value="instagram">Instagram</option><option value="twitter">Twitter/X</option>
            <option value="linkedin">LinkedIn</option><option value="tiktok">TikTok</option>
            <option value="youtube">YouTube</option><option value="blog">Blog</option>
            <option value="email">Email</option>
          </select>
        </div>
        <div class="form-group"><label>Content Type</label>
          <select id="cc-type" >
            <option value="post">Post</option><option value="reel">Reel</option>
            <option value="story">Story</option><option value="article">Article</option>
            <option value="video">Video</option><option value="email">Email</option>
          </select>
        </div>
        <div class="form-group"><label>Title *</label><input id="cc-title" placeholder="Content title"/></div>
        <div class="form-group"><label>Content</label><textarea id="cc-content" rows="3" class="field-full" placeholder="Content text (optional)"></textarea></div>
        <button class="btn btn-primary" onclick="addCalendarEntry()" style="width:100%">➕ Add Entry</button>
        <div id="cc-add-result" style="margin-top:8px;font-size:.84em"></div>
      </div>
      <!-- AI Calendar Generator -->
      <div class="card card-ai">
        <div class="card-header"><div class="card-title"><span style="color:var(--gold)">◈</span> AI Calendar Generator</div></div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">Let AI generate a full 30-day content calendar tailored to your niche.</p>
        <div class="form-group"><label>Your Niche / Business</label><input id="cc-gen-niche" placeholder="e.g. SaaS productivity tools"/></div>
        <div class="form-group"><label>Days to Generate</label>
          <select id="cc-gen-days" >
            <option value="7">7 days</option><option value="14">14 days</option>
            <option value="30" selected>30 days</option>
          </select>
        </div>
        <button class="btn btn-primary" onclick="generateContentCalendar()" style="width:100%;background:linear-gradient(135deg,#0d0d0d,#1a1a1a);color:var(--gold);border:1px solid rgba(212,175,55,.4)">◈ Generate Calendar</button>
        <div id="cc-gen-result" style="margin-top:10px;font-size:.84em"></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Neural Brain ── -->
<div id="tab-neural-brain" class="tab-content" style="width:100%;box-sizing:border-box">

  <!-- Header banner -->
  <div style="background:linear-gradient(135deg,#050812 0%,#0a0d1e 60%,#050a18 100%);border:1px solid rgba(212,175,55,.55);border-radius:14px;padding:24px 28px;margin-bottom:18px;display:flex;align-items:center;gap:18px;position:relative;overflow:hidden;box-shadow:0 0 60px rgba(212,175,55,.12),0 8px 32px rgba(0,0,0,.8)">
    <div style="position:absolute;inset:0;background:radial-gradient(ellipse at 20% 50%,rgba(212,175,55,.14) 0%,transparent 60%);pointer-events:none"></div>
    <div style="position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(212,175,55,.9),transparent)"></div>
    <div style="font-size:2.6rem;line-height:1;animation:brainPulse 3s ease-in-out infinite;position:relative;z-index:1">🧠</div>
    <div style="flex:1;position:relative;z-index:1">
      <div style="font-size:1.3rem;font-weight:800;letter-spacing:.08em;background:linear-gradient(135deg,#fff 30%,var(--gold-light) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;text-shadow:none">NEURAL BRAIN</div>
      <div style="font-size:.83em;color:rgba(212,175,55,.8);margin-top:3px;font-weight:500">Central intelligence core — every agent decision routes through this brain in real time</div>
    </div>
    <div style="display:flex;align-items:center;gap:18px;position:relative;z-index:1;flex-wrap:wrap">
      <div style="display:flex;align-items:center;gap:8px">
        <div id="brain-mode-dot" style="width:10px;height:10px;border-radius:50%;background:#6b7280;transition:background .4s,box-shadow .4s"></div>
        <span id="brain-mode-label" style="font-size:.82em;color:rgba(212,175,55,.8);font-weight:700;letter-spacing:.05em">LOADING</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <div id="brain-bg-dot" style="width:10px;height:10px;border-radius:50%;background:#6b7280;transition:background .4s"></div>
        <span id="brain-bg-label" style="font-size:.82em;color:var(--text-secondary);font-weight:600">BG LOOP</span>
      </div>
    </div>
  </div>
  <style>
  @keyframes brainPulse{0%,100%{filter:drop-shadow(0 0 6px rgba(212,175,55,.5))}50%{filter:drop-shadow(0 0 22px rgba(212,175,55,.9))}}
  .bn-stat-card{background:linear-gradient(135deg,rgba(212,175,55,.06),rgba(212,175,55,.03));border:1px solid rgba(212,175,55,.2);border-radius:var(--radius);padding:16px 18px;display:flex;align-items:center;gap:12px;transition:all .25s;position:relative;overflow:hidden}
  .bn-stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(212,175,55,.3),transparent)}
  .bn-stat-card:hover{border-color:rgba(212,175,55,.5);box-shadow:0 0 20px rgba(212,175,55,.1);transform:translateY(-2px)}
  .bn-stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.1em;flex-shrink:0}
  .bn-btn{display:inline-flex;align-items:center;gap:7px;padding:9px 18px;background:rgba(212,175,55,.08);border:1px solid rgba(212,175,55,.3);border-radius:8px;color:var(--gold);font-size:.82em;font-weight:700;cursor:pointer;font-family:inherit;transition:all .2s;letter-spacing:.03em;white-space:nowrap}
  .bn-btn:hover{background:rgba(212,175,55,.16);border-color:rgba(212,175,55,.6);box-shadow:0 0 16px rgba(212,175,55,.2);transform:translateY(-1px)}
  .bn-btn:active{transform:translateY(0)}
  .bn-btn.danger{background:rgba(239,68,68,.08);border-color:rgba(239,68,68,.3);color:#f87171}
  .bn-btn.danger:hover{background:rgba(239,68,68,.18);border-color:rgba(239,68,68,.6);box-shadow:0 0 16px rgba(239,68,68,.2)}
  .bn-btn.green{background:rgba(16,185,129,.08);border-color:rgba(16,185,129,.3);color:#34d399}
  .bn-btn.green:hover{background:rgba(16,185,129,.18);border-color:rgba(16,185,129,.6);box-shadow:0 0 16px rgba(16,185,129,.2)}
  .bn-chart-bar{display:inline-block;width:5px;border-radius:3px 3px 0 0;background:var(--gold);opacity:.75;transition:height .3s ease,opacity .3s;flex-shrink:0;align-self:flex-end;min-height:2px}
  </style>

  <!-- Stat cards row -->
  <div class="grid-stat" id="brain-stat-grid" style="margin-bottom:18px">
    <div class="bn-stat-card">
      <div class="bn-stat-icon" style="background:rgba(212,175,55,.12)">🎓</div>
      <div class="stat-body"><div class="val" id="bn-learn-steps" style="color:var(--gold)">—</div><div class="lbl">Learn Steps</div></div>
    </div>
    <div class="bn-stat-card">
      <div class="bn-stat-icon" style="background:rgba(99,102,241,.12)">📊</div>
      <div class="stat-body"><div class="val" id="bn-experiences" style="color:#818cf8">—</div><div class="lbl">Experiences</div></div>
    </div>
    <div class="bn-stat-card">
      <div class="bn-stat-icon" style="background:rgba(16,185,129,.12)">🗄️</div>
      <div class="stat-body"><div class="val" id="bn-buffer" style="color:#34d399">—</div><div class="lbl">Buffer Size</div></div>
    </div>
    <div class="bn-stat-card">
      <div class="bn-stat-icon" style="background:rgba(251,191,36,.12)">⭐</div>
      <div class="stat-body"><div class="val" id="bn-avg-reward" style="color:#fbbf24">—</div><div class="lbl">Avg Reward</div></div>
    </div>
    <div class="bn-stat-card">
      <div class="bn-stat-icon" style="background:rgba(244,63,94,.12)">📉</div>
      <div class="stat-body"><div class="val" id="bn-last-loss" style="color:#fb7185">—</div><div class="lbl">Last Loss</div></div>
    </div>
    <div class="bn-stat-card">
      <div class="bn-stat-icon" style="background:rgba(34,211,238,.12)">⚡</div>
      <div class="stat-body"><div class="val" id="bn-lr" style="color:#22d3ee;font-size:1em">—</div><div class="lbl">Learning Rate</div></div>
    </div>
  </div>

  <!-- Charts row -->
  <div class="grid2" style="margin-bottom:18px">

    <!-- Loss chart -->
    <div class="card" style="border:1px solid rgba(212,175,55,.2);background:linear-gradient(135deg,rgba(212,175,55,.04),var(--surface2))">
      <div class="card-header">
        <div class="card-title"><span class="icon">📉</span> Live Loss History</div>
        <span id="bn-loss-latest" style="font-size:.8em;color:var(--text-secondary);font-family:var(--mono)">—</span>
      </div>
      <div id="bn-loss-chart" style="height:90px;display:flex;align-items:flex-end;gap:2px;overflow:hidden;padding:4px 0 0">
        <span style="color:var(--text-secondary);font-size:.8em;align-self:center;width:100%;text-align:center">Waiting for learn steps…</span>
      </div>
    </div>

    <!-- Reward chart -->
    <div class="card" style="border:1px solid rgba(212,175,55,.2);background:linear-gradient(135deg,rgba(212,175,55,.04),var(--surface2))">
      <div class="card-header">
        <div class="card-title"><span class="icon">📈</span> Avg Reward History</div>
        <span id="bn-reward-latest" style="font-size:.8em;color:var(--text-secondary);font-family:var(--mono)">—</span>
      </div>
      <div id="bn-reward-chart" style="height:90px;display:flex;align-items:flex-end;gap:2px;overflow:hidden;padding:4px 0 0">
        <span style="color:var(--text-secondary);font-size:.8em;align-self:center;width:100%;text-align:center">Waiting for experiences…</span>
      </div>
    </div>

  </div>

  <!-- Controls + Model info row -->
  <div class="grid2" style="margin-bottom:18px">

    <!-- Controls card -->
    <div class="card" style="border:1px solid rgba(212,175,55,.25);background:linear-gradient(135deg,rgba(212,175,55,.05),var(--surface2))">
      <div class="card-header">
        <div class="card-title"><span class="icon">🕹️</span> Brain Controls</div>
        <button class="bn-btn" onclick="brainRefresh()" title="Refresh all stats">↻ Refresh</button>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:10px">
        <button class="bn-btn green" onclick="brainLearn()">🎓 Manual Learn</button>
        <button class="bn-btn" onclick="brainForceOffline()">🔌 Force Offline Learn</button>
        <button class="bn-btn" onclick="brainSave()">💾 Save Model</button>
        <button class="bn-btn danger" onclick="brainClear()">🗑️ Clear Buffer</button>
      </div>
      <div id="brain-action-msg" style="margin-top:12px;font-size:.82em;min-height:20px;color:var(--text-secondary)"></div>

      <!-- Auto-poll toggle -->
      <div style="margin-top:16px;display:flex;align-items:center;gap:10px;border-top:1px solid var(--border);padding-top:14px">
        <label class="toggle" style="width:44px;height:24px" title="Auto-refresh brain stats every 5s">
          <input type="checkbox" id="brain-autopoll" onchange="brainToggleAutopoll(this.checked)"/>
          <span class="slider" style="border-radius:24px"></span>
        </label>
        <span style="font-size:.82em;color:var(--text-secondary);font-weight:600">Auto-refresh every 5s</span>
        <span id="brain-poll-indicator" style="display:none;font-size:.75em;color:var(--gold);animation:blink 2s infinite">● LIVE</span>
      </div>
    </div>

    <!-- Model info card -->
    <div class="card" style="border:1px solid rgba(212,175,55,.2);background:linear-gradient(135deg,rgba(212,175,55,.04),var(--surface2))">
      <div class="card-header">
        <div class="card-title"><span class="icon">⚙️</span> Model Configuration</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 16px;font-size:.83em">
        <div><span style="color:var(--text-secondary)">Device</span><br><span id="bn-device" style="color:var(--gold);font-family:var(--mono);font-weight:700">—</span></div>
        <div><span style="color:var(--text-secondary)">Input Size</span><br><span id="bn-input-size" style="color:var(--text);font-family:var(--mono)">—</span></div>
        <div><span style="color:var(--text-secondary)">Output Size</span><br><span id="bn-output-size" style="color:var(--text);font-family:var(--mono)">—</span></div>
        <div><span style="color:var(--text-secondary)">Hidden Layers</span><br><span id="bn-hidden" style="color:var(--text);font-family:var(--mono)">—</span></div>
        <div><span style="color:var(--text-secondary)">Batch Size</span><br><span id="bn-batch" style="color:var(--text);font-family:var(--mono)">—</span></div>
        <div><span style="color:var(--text-secondary)">Update Freq</span><br><span id="bn-update-freq" style="color:var(--text);font-family:var(--mono)">—</span></div>
        <div style="grid-column:span 2"><span style="color:var(--text-secondary)">Model Path</span><br><span id="bn-model-path" style="color:var(--text-secondary);font-family:var(--mono);font-size:.9em;word-break:break-all">—</span></div>
      </div>
    </div>

  </div>

  <!-- Activity log -->
  <div class="card" style="border:1px solid rgba(212,175,55,.2);background:linear-gradient(135deg,rgba(212,175,55,.04),var(--surface2))">
    <div class="card-header">
      <div class="card-title"><span class="icon">📡</span> Brain Activity Log</div>
      <button class="btn btn-ghost btn-sm" onclick="brainLoadLog()">↻ Refresh</button>
    </div>
    <div id="brain-log" style="font-family:var(--mono);font-size:.77em;background:rgba(0,0,0,.7);border:1px solid rgba(212,175,55,.12);border-radius:8px;padding:14px;height:260px;overflow-y:auto;color:rgba(212,175,55,.7);line-height:1.7;box-shadow:inset 0 0 30px rgba(212,175,55,.04)">
      <span style="color:var(--text-secondary)">Loading brain log…</span>
    </div>
  </div>

</div>

</main>

<div id="toast"></div>

<script>
let currentTab = 'dashboard';
const _startTime = Date.now();

/* Tab animation durations — must match CSS */
const TAB_LEAVE_MS = 200;   /* matches tabLeave .2s */
const TAB_ENTER_DELAY_MS = 80; /* stagger: let leave start before enter */

function switchToChatTab() {
  const btn = document.getElementById('nav-btn-chat');
  if (btn) btn.click();
}

// ── Nav scroll arrows ──
function navScroll(dir) {
  const nav = document.getElementById('main-nav');
  nav.scrollBy({left: dir * 220, behavior: 'smooth'});
}
function _updateNavArrows() {
  const nav = document.getElementById('main-nav');
  if (!nav) return;
  const btnL = document.getElementById('nav-scroll-left');
  const btnR = document.getElementById('nav-scroll-right');
  const atStart = nav.scrollLeft <= 4;
  const atEnd = nav.scrollLeft + nav.clientWidth >= nav.scrollWidth - 4;
  btnL.classList.toggle('hidden', atStart);
  btnR.classList.toggle('hidden', atEnd);
}
document.addEventListener('DOMContentLoaded', function() {
  const nav = document.getElementById('main-nav');
  if (nav) {
    nav.addEventListener('scroll', _updateNavArrows, {passive:true});
    _updateNavArrows();
    // Update arrows on window resize
    window.addEventListener('resize', _updateNavArrows, {passive:true});
  }
});

function _switchTabBase(tab, btn) {
  // Animate out current active tab
  const prevTab = document.querySelector('.tab-content.active');
  const isNewTab = prevTab && prevTab.id !== 'tab-' + tab;
  if (isNewTab) {
    prevTab.classList.add('tab-leaving');
    setTimeout(() => { prevTab.classList.remove('active', 'tab-leaving'); }, TAB_LEAVE_MS);
  } else {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  }
  // Animate in new tab (slight delay so leave animation starts first)
  setTimeout(() => {
    const tabEl = document.getElementById('tab-' + tab);
    if (tabEl) tabEl.classList.add('active');
  }, isNewTab ? TAB_ENTER_DELAY_MS : 0);
  // Sync primary group nav button
  const group = _TAB_TO_GROUP[tab] || 'overview';
  document.querySelectorAll('.nav-group-btn').forEach(b => b.classList.remove('active'));
  const groupBtn = document.querySelector('.nav-group-btn[data-group="' + group + '"]');
  if (groupBtn) groupBtn.classList.add('active');
  // Sync sub-nav visibility
  document.querySelectorAll('.sub-nav').forEach(s => s.classList.remove('active'));
  const subNav = document.getElementById('subnav-' + group);
  if (subNav) subNav.classList.add('active');
  // Sync sub-nav active button
  document.querySelectorAll('.sub-nav button').forEach(b => b.classList.remove('active'));
  if (btn && btn.classList && !btn.classList.contains('nav-group-btn')) {
    btn.classList.add('active');
    btn.scrollIntoView({behavior:'smooth',block:'nearest',inline:'nearest'});
  } else {
    // Auto-find the matching sub-nav button when btn is null or a group button
    const safeTab = (tab in _TAB_TO_GROUP) ? CSS.escape(tab) : '';
    const autoBtn = safeTab && subNav ? subNav.querySelector('button[onclick*="' + safeTab + '"]') : null;
    if (autoBtn) autoBtn.classList.add('active');
  }
  currentTab = tab;
  if (tab === 'dashboard') { loadDashboard(); if (typeof loadSysRes === 'function') loadSysRes(); loadDoctorPanel(); }
  if (tab === 'chat') loadChatLog();
  if (tab === 'scheduler') loadSchedules();
  if (tab === 'workers') { loadWorkers(); if (!_allAgents.length) loadSwarm().then(renderSwarmAgentGrid); else renderSwarmAgentGrid(); }
  if (tab === 'improvements') loadImprovements();
  if (tab === 'skills') loadSkills();
  if (tab === 'tasks') loadTasks();
  if (tab === 'swarm') { loadSwarm(); swarmTheaterRefresh(); }
  if (tab === 'live-office') loadLiveOffice();
  if (tab === 'commands') loadCommandsTab();
  if (tab === 'metrics') loadMetrics();
  if (tab === 'templates') loadTemplates();
  if (tab === 'guardrails') loadGuardrails();
  if (tab === 'memory') loadMemory();
  if (tab === 'integrations') loadIntegrations();
  if (tab === 'history') loadHistory();
  if (tab === 'options') { loadOptions(); loadUpdaterStatus(); runSecurityCheck(); }
  if (tab === 'blacklight') { blRefresh(); blLoadLogs(); }
  if (tab === 'ascend') { afRefresh(); afLoadPatches(); afLoadChangelog(); }
  // New Paperclip-parity tabs
  if (tab === 'budget') loadBudget();
  if (tab === 'org') { loadOrg(); loadOrgAdapters(); }
  if (tab === 'goals') loadGoals();
  if (tab === 'tickets') { loadTickets(); loadTicketAudit(); }
  if (tab === 'boardroom') loadBoardroom();
  if (tab === 'companies') loadCompanies();
  if (tab === 'artifacts') { loadArtifacts(); loadSessions(); }
}

function toast(msg, type='success') {
  const icons = {success:'✅', error:'❌', info:'ℹ️'};
  const el = document.getElementById('toast');
  el.innerHTML = `<span style="font-size:1.1em">${icons[type]||'✅'}</span><span>${escHtml(String(msg))}</span>`;
  el.className = '';
  el.classList.add(type, 'show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 3500);
}

async function api(path, opts={}) {
  const fetchOpts = {...opts};
  const headers = new Headers(fetchOpts.headers || {});
  const hasBody = fetchOpts.body !== undefined && fetchOpts.body !== null;

  if (hasBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (hasBody && typeof fetchOpts.body === 'object' && !(fetchOpts.body instanceof FormData)) {
    fetchOpts.body = JSON.stringify(fetchOpts.body);
  }

  // Attach stored JWT token when available
  const storedToken = localStorage.getItem('ai_employee_token');
  if (storedToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${storedToken}`);
  }
  fetchOpts.headers = headers;

  try {
    const r = await fetch(path, fetchOpts);
    let data = {};

    try {
      data = await r.json();
    } catch {
      const text = await r.text();
      data = text ? {message: text} : {};
    }

    if (!data || typeof data !== 'object') {
      data = {value: data};
    }
    if (data.ok === undefined) {
      data.ok = r.ok;
    }
    if (!r.ok && !data.error && !data.detail) {
      data.detail = `Request failed: ${r.status}`;
    }
    // Show login modal when server requires auth and we lack a valid token
    if (r.status === 401 && !path.startsWith('/auth/')) {
      _showAuthModal();
    }
    data.status_code = r.status;
    return data;
  } catch(e) {
    return {ok: false, error: String(e)};
  }
}

// ── Auth helpers ──────────────────────────────────────────────────────────────
function _showAuthModal() {
  let m = document.getElementById('auth-modal');
  if (!m) {
    m = document.createElement('div');
    m.id = 'auth-modal';
    m.setAttribute('role', 'dialog');
    m.setAttribute('aria-modal', 'true');
    m.setAttribute('aria-label', 'Login required');
    m.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9999;display:flex;align-items:center;justify-content:center';
    m.innerHTML = `<div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:32px;max-width:380px;width:90%;box-shadow:var(--shadow)">
      <h2 style="margin-bottom:16px;font-size:1.1em;font-weight:700">🔐 Login Required</h2>
      <p style="font-size:.85em;color:var(--text-secondary);margin-bottom:16px">REQUIRE_AUTH is enabled. Enter your credentials.</p>
      <div style="display:flex;flex-direction:column;gap:10px">
        <input id="auth-user" type="text" placeholder="Username" autocomplete="username"
          style="padding:10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--surface2);color:var(--text);font-family:inherit">
        <input id="auth-pass" type="password" placeholder="Password" autocomplete="current-password"
          style="padding:10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--surface2);color:var(--text);font-family:inherit">
        <div id="auth-err" style="color:var(--danger);font-size:.82em;min-height:1.2em"></div>
        <button onclick="_doLogin()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--primary);color:#000;font-weight:700;border:none;cursor:pointer;font-family:inherit">Login</button>
      </div>
    </div>`;
    document.body.appendChild(m);
  }
  m.style.display = 'flex';
  setTimeout(() => document.getElementById('auth-user')?.focus(), 50);
}

async function _doLogin() {
  const user = document.getElementById('auth-user')?.value.trim();
  const pass = document.getElementById('auth-pass')?.value;
  const errEl = document.getElementById('auth-err');
  if (!user || !pass) { if(errEl) errEl.textContent = 'Enter username and password.'; return; }
  const r = await fetch('/auth/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username: user, password: pass}),
  });
  const data = await r.json().catch(() => ({}));
  if (r.ok && data.access_token) {
    localStorage.setItem('ai_employee_token', data.access_token);
    const m = document.getElementById('auth-modal');
    if (m) m.style.display = 'none';
    toast('Logged in ✓', 'success');
  } else {
    if (errEl) errEl.textContent = data.detail || 'Login failed.';
  }
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// Escape a value for safe embedding inside a JS string literal (single-quoted onclick="…")
function jsEsc(str) {
  return String(str ?? '').replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/"/g,'\\"');
}

// ── Animated count-up helper ─────────────────────────────────────────────────
function animateCount(id, target) {
  const el = document.getElementById(id);
  if (!el) return;
  const prev = parseInt(el.textContent) || 0;
  if (prev === target) return;
  const duration = 500;
  const startTime = performance.now();
  const diff = target - prev;
  const round = diff >= 0 ? Math.ceil : Math.floor;
  function step(now) {
    const elapsed = Math.min(now - startTime, duration);
    const eased = 1 - Math.pow(1 - elapsed / duration, 3);
    el.textContent = round(prev + diff * eased);
    if (elapsed < duration) requestAnimationFrame(step);
    else el.textContent = target;
  }
  requestAnimationFrame(step);
}

// ── Disable / re-enable all start-stop controls during action ────────────────
function normalizeAgents(statusPayload) {
  const raw = statusPayload?.agents || statusPayload?.workers || [];
  return raw.map((entry, idx) => {
    const id = entry?.agent || entry?.name || entry?.bot || entry?.id || `agent-${idx + 1}`;
    const running = entry?.running === true || entry?.status === 'running';
    return { id, running };
  });
}

// ── Disable / re-enable all start-stop controls during action ────────────────
function _setStartStopDisabled(disabled) {
  ['hero-start-btn','hero-stop-btn','hdr-start-btn','hdr-stop-btn'].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.disabled = disabled;
  });
}

function showStatDetail(type) {
  const panel = document.getElementById('stat-detail-panel');
  const title = document.getElementById('stat-detail-title');
  const content = document.getElementById('stat-detail-content');
  if (!panel) return;
  panel.style.display = 'block';
  const details = {
    running: {t:'Running Agents', c:'Agents currently active and processing tasks. Click an agent in the Live Office tab to inspect its workload.'},
    total: {t:'Total System Agents', c:'All registered AI agents in the system. Agents are activated on-demand when tasks matching their specialty arrive.'},
    gateway: {t:'API Gateway', c:'The gateway routes incoming requests to the correct agent. Status shows whether the routing layer is reachable.'},
    uptime: {t:'System Uptime', c:'Time since the dashboard server started. Agents have individual uptime tracked in the Agents tab.'}
  };
  const d = details[type] || {t:'Details', c:'No details available.'};
  title.textContent = d.t;
  content.innerHTML = '<p style="line-height:1.7">' + d.c + '</p>';
  // Move focus to close button for screen reader / keyboard users
  const closeBtn = panel.querySelector('button');
  if (closeBtn) closeBtn.focus();
}

function updateHealthChecks(data, wavefield) {
  const setHC = (id, ok, val) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = 'health-check-item ' + (ok ? 'ok' : 'err');
    el.querySelector('.hc-val').textContent = val;
  };
  setHC('hc-api', true, 'Online');
  setHC('hc-agents', (data.running_agents||0) > 0, (data.running_agents||0) + ' active');
  setHC('hc-ollama', data.ollama_ok, data.ollama_ok ? 'Reachable' : 'Offline');
  setHC('hc-db', true, 'Ready');
  setHC('hc-gateway', data.gateway_ok !== false, data.gateway_ok !== false ? 'Online' : 'Offline');
  setHC('hc-memory', true, 'Ready');
  if (!wavefield || wavefield.error) {
    setHC('hc-wavefield', false, 'Unavailable');
  } else {
    const mode = (wavefield.rollout_mode || 'default').toUpperCase();
    const health = !!wavefield.healthy;
    const enabled = !!wavefield.enabled;
    const label = enabled
      ? (health ? `${mode} · Ready` : `${mode} · Degraded`)
      : `${mode} · Disabled`;
    setHC('hc-wavefield', enabled && health, label);
  }
  const wfMetrics = (wavefield && wavefield.metrics) ? wavefield.metrics : {};
  const setWFMetric = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = String(value ?? 0);
  };
  setWFMetric('wf-m-route', wfMetrics.route_selected);
  setWFMetric('wf-m-route-wf', wfMetrics.route_selected_wavefield);
  setWFMetric('wf-m-fallbacks', wfMetrics.fallbacks);
  setWFMetric('wf-m-health-fail', wfMetrics.healthcheck_failures);
  setWFMetric('wf-m-shadow', wfMetrics.shadow_requests);
  setWFMetric('wf-m-errors', wfMetrics.wavefield_errors);

  // Animate running count in header
  const runEl = document.getElementById('stat-running');
  if (runEl && data.running_agents !== undefined) {
    animateCount('stat-running', data.running_agents);
  }
}

function _isHermesRunning(agents) {
  return agents.some(a => (a.id || a.name || '') === 'hermes-agent' && a.running);
}

function _isHermesRunning(agents) {
  return agents.some(a => (a.id || a.name || '') === 'hermes-agent' && a.running);
}

// ── Doctor Panel ──────────────────────────────────────────────────────────────
async function loadDoctorPanel() {
  const el = document.getElementById('doctor-items-list');
  if (!el) return;
  try {
    const data = await api('/api/doctor/items');
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = '<div class="dp-empty">All checks passed ✅</div>';
      return;
    }
    el.innerHTML = items.map(it => {
      const isOk    = it.status === 'ok';
      const isWarn  = it.status === 'warn';
      const isError = it.status === 'error';
      const icon = isOk ? '✅' : isWarn ? '⚠️' : '❌';
      const cls  = isOk ? 'dp-ok' : isWarn ? 'dp-warn' : 'dp-error';
      const actionCls = it.action === 'approved' ? ' dp-approved' : it.action === 'rejected' ? ' dp-rejected' : '';
      const actionLabel = it.action ? `<span style="font-size:.68em;opacity:.7;font-style:italic">[${it.action}]</span>` : '';
      const descHtml = it.description
        ? `<div class="dp-item-desc">${escHtml(it.description)}</div>` : '';
      const approveDisabled = it.action === 'approved' ? ' disabled style="opacity:.4"' : '';
      const rejectDisabled  = it.action === 'rejected' ? ' disabled style="opacity:.4"' : '';
      const actionsHtml = !isOk ? `
        <div class="dp-actions">
          <button class="dp-btn dp-btn-approve"${approveDisabled} onclick="doctorAction('${escHtml(it.id)}','approved')">✓ Approve</button>
          <button class="dp-btn dp-btn-reject"${rejectDisabled} onclick="doctorAction('${escHtml(it.id)}','rejected')">✕ Reject</button>
          ${it.action ? `<button class="dp-btn" style="color:var(--text-muted);border-color:rgba(255,255,255,.15)" onclick="doctorAction('${escHtml(it.id)}','reset')">↩ Reset</button>` : ''}
        </div>` : '';
      return `<div class="dp-item ${cls}${actionCls}">
        <div class="dp-icon">${icon}</div>
        <div class="dp-body">
          <div class="dp-item-title">${escHtml(it.title)} ${actionLabel}</div>
          ${descHtml}
          ${actionsHtml}
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    el.innerHTML = `<div class="dp-empty" style="color:var(--danger,#f87171)">Failed to load diagnostics</div>`;
  }
}

async function doctorAction(id, action) {
  try {
    await api('/api/doctor/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id, action})});
    loadDoctorPanel();
  } catch(e) {
    console.warn('doctorAction error', e);
  }
}

async function loadDashboard() {
  const d = await api('/api/status');

  // Server unreachable — show fully offline state and stop
  if (!d || d.error || !Array.isArray(d.agents)) {
    animateCount('stat-running', 0);
    animateCount('stat-total', 0);
    animateCount('stat-offline', 0);
    document.getElementById('header-sub').textContent = 'System offline';
    const healthBar = document.getElementById('health-bar');
    const sysRing = document.getElementById('sys-ring');
    const sysControlSub = document.getElementById('sys-control-sub');
    if (healthBar) { healthBar.style.width = '0%'; healthBar.className = 'health-bar-fill danger'; }
    if (document.getElementById('health-label-right')) document.getElementById('health-label-right').textContent = '0%';
    if (document.getElementById('health-label-left')) document.getElementById('health-label-left').textContent = '0 / 0 running';
    if (sysRing) sysRing.classList.add('offline');
    if (sysControlSub) sysControlSub.textContent = 'System offline — server is not reachable';
    const el = document.getElementById('bot-status-list');
    if (el) el.innerHTML = '<div class="empty"><div class="icon">🔴</div><p>System offline — server is not reachable.</p></div>';
    return;
  }

  const agents = normalizeAgents(d);
  const running = agents.filter(a => a.running).length;
  const total = agents.length;
  const offline = total - running;

  // Animate stat numbers
  animateCount('stat-running', running);
  animateCount('stat-total', total);
  animateCount('stat-offline', offline);
  // Update SYSTEM ONLINE banner
  const ovBannerMode = document.getElementById('ov-banner-mode');
  const ovBannerAgents = document.getElementById('ov-banner-agents');
  if (ovBannerMode && d.mode) ovBannerMode.textContent = d.mode.toUpperCase() + ' MODE';
  if (ovBannerAgents) ovBannerAgents.textContent = `${running} / ${total} Agents Active`;
  const modeCapacity = {starter: 3, business: 15, power: 56};
  const capacity = modeCapacity[d.mode] || total;
  const totalSubEl = document.getElementById('stat-total-sub');
  if (totalSubEl && d.mode) totalSubEl.textContent = `${d.mode} mode · ${capacity} max`;
  const offlineSubEl = document.getElementById('stat-offline-sub');
  if (offlineSubEl) offlineSubEl.textContent = total > 0 ? (offline > 0 ? `${Math.round(offline/total*100)}% idle` : 'All running ✓') : '';
  const modeColors = {starter:'#34d399',business:'#D4AF37',power:'#c084fc'};
  const mc = modeColors[d.mode] || 'var(--gold)';
  document.getElementById('header-sub').innerHTML =
    `${running}/${capacity} agents running` +
    (d.mode ? ` <span style="background:${mc}22;color:${mc};border:1px solid ${mc}44;border-radius:8px;padding:1px 8px;font-size:.8em;font-weight:700;margin-left:4px">${escHtml(d.mode).toUpperCase()}</span>` : '');

  // Update system control hero
  const pct = total > 0 ? Math.round((running / total) * 100) : 0;
  const healthBar = document.getElementById('health-bar');
  const sysRing = document.getElementById('sys-ring');
  const sysControlSub = document.getElementById('sys-control-sub');
  const healthLabelRight = document.getElementById('health-label-right');
  const healthLabelLeft = document.getElementById('health-label-left');
  if (healthBar) { healthBar.style.width = pct + '%'; healthBar.className = 'health-bar-fill' + (pct < 40 ? ' danger' : pct < 70 ? ' warn' : ''); }
  if (healthLabelRight) healthLabelRight.textContent = pct + '%';
  if (healthLabelLeft) healthLabelLeft.textContent = running + ' / ' + total + ' running';
  if (pct === 0 && total > 0) {
    if (sysRing) sysRing.classList.add('offline');
    if (sysControlSub) sysControlSub.textContent = 'All agents stopped — click Start All to launch';
  } else if (pct === 100) {
    if (sysRing) sysRing.classList.remove('offline');
    if (sysControlSub) sysControlSub.textContent = 'All systems operational ✓';
  } else if (total === 0) {
    if (sysRing) sysRing.classList.add('offline');
    if (sysControlSub) sysControlSub.textContent = 'No agent state data yet — start agents first';
  } else {
    if (sysRing) sysRing.classList.remove('offline');
    if (sysControlSub) sysControlSub.textContent = `${running} of ${total} agents active`;
  }

  // Uptime
  const secs = Math.floor((Date.now() - _startTime) / 1000);
  const uptimeStr = secs < 60 ? secs + 's' : secs < 3600 ? Math.floor(secs/60) + 'm' : Math.floor(secs/3600) + 'h';
  document.getElementById('stat-uptime').textContent = uptimeStr;
  const ovBannerUptime = document.getElementById('ov-banner-uptime');
  if (ovBannerUptime) ovBannerUptime.textContent = 'Uptime: ' + uptimeStr;

  // Gateway status — use data from /api/status instead of a direct port ping
  const gwOnline = !!(d.gateway_ok || d.gateway_running);
  const gwEl = document.getElementById('stat-gateway');
  if (gwEl) gwEl.textContent = gwOnline ? 'Online' : 'Offline';

  const el = document.getElementById('bot-status-list');
  if (!agents.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🤖</div><p>No agent state data yet. Start the agents first.</p></div>';
  } else {
    const sorted = [...agents].sort((a, b) => (b.running ? 1 : 0) - (a.running ? 1 : 0) || (a.id || '').localeCompare(b.id || ''));
    el.innerHTML = sorted.map(a => {
      const cls = a.running ? 'on' : 'off';
      const lbl = a.running ? 'running' : 'stopped';
      const isActive = (d.active_agents || []).includes(a.id);
      const taskBadge = isActive ? `<span style="font-size:.68em;padding:2px 6px;border-radius:8px;background:rgba(212,175,55,.15);color:var(--gold);border:1px solid rgba(212,175,55,.3);margin-left:4px">◈ on task</span>` : '';
      return `<div class="bot-row">
        <div class="dot ${cls}"></div>
        <span class="bot-name">${escHtml(a.id)}</span>
        ${taskBadge}
        <span class="badge ${lbl}">${lbl}</span>
      </div>`;
    }).join('');
  }

  // Determine gateway and ollama health from /api/status (no direct port pings)
  const gatewayOk = !!(d.gateway_ok || d.gateway_running || gwOnline);
  const wavefield = await api('/api/wavefield/status');
  updateHealthChecks({running_agents: running, ollama_ok: !!d.ollama_ok, gateway_ok: gatewayOk}, wavefield);

  // Refresh doctor diagnostics panel
  loadDoctorPanel();

  // Sync the BLACKLIGHT quick-toggle on the dashboard
  const bl = await api('/api/blacklight/status');
  _blSyncUI(bl.running || false, bl.goal || '');

  // Sync Hermes Agent toggle
  const hermesRunning = _isHermesRunning(agents);
  const hermesToggleEl = document.getElementById('dash-hermes-toggle');
  if (hermesToggleEl) hermesToggleEl.checked = hermesRunning;
  const hermesSub = document.getElementById('dash-hermes-sublabel');
  if (hermesSub) hermesSub.textContent = hermesRunning ? '🧠 Running — ready for tasks' : 'Reasoning agent — stopped';
  _updateChatHermesStatus(hermesRunning);
  // Update live agent map
  _renderDashAgentMap(agents, d);
}

function _renderDashAgentMap(agents, statusData) {
  const el = document.getElementById('dash-agent-map');
  if (!el) return;
  const activeAgents = new Set(statusData?.active_agents || []);
  if (!agents.length) {
    el.innerHTML = '<div class="empty" style="grid-column:1/-1"><div class="icon">🤖</div><p style="font-size:.84em">No agents loaded. Start agents from the button above.</p></div>';
    return;
  }
  const agentEmoji = {
    'task-orchestrator':'🎯','lead-generator':'🎯','lead-hunter':'🎯','offer-agent':'📧',
    'company-builder':'🏢','brand-strategist':'🎨','finance-wizard':'💰','growth-hacker':'📈',
    'social-media-manager':'📱','paid-media-specialist':'📣','qualification-agent':'🔍',
    'follow-up-agent':'🔄','appointment-setter':'📅','ui-designer':'🎨','web-researcher':'🌐',
    'engineering-assistant':'💻','ecom-agent':'🛒','chatbot-builder':'🤖','creator-agency':'✍️',
    'recruiter':'👔','hr-manager':'👔','project-manager':'📋','finance':'💰',
    'newsletter-bot':'📰','faceless-video':'🎬','course-creator':'📚',
  };
  const taskLabels = {
    'task-orchestrator':'Routing tasks','lead-generator':'Finding leads','offer-agent':'Writing outreach',
    'company-builder':'Building strategy','brand-strategist':'Crafting brand','finance-wizard':'Analyzing finances',
    'growth-hacker':'Growing traffic','social-media-manager':'Posting content','paid-media-specialist':'Optimizing ads',
    'web-researcher':'Researching web','engineering-assistant':'Writing code','ecom-agent':'Managing store',
    'follow-up-agent':'Following up leads','project-manager':'Managing tasks',
  };
  el.innerHTML = agents.map(a => {
    const isRunning = a.running;
    const isActive = activeAgents.has(a.id);
    const emoji = agentEmoji[a.id] || '🤖';
    const task = isActive ? (taskLabels[a.id] || 'Working on task') : (isRunning ? 'Ready — standing by' : 'Stopped');
    const dotColor = isActive ? 'var(--gold)' : (isRunning ? 'var(--success)' : 'rgba(148,163,184,.3)');
    const cardBg = isActive ? 'rgba(212,175,55,.07)' : (isRunning ? 'rgba(16,185,129,.04)' : 'transparent');
    const cardBorder = isActive ? 'rgba(212,175,55,.4)' : (isRunning ? 'rgba(16,185,129,.2)' : 'rgba(148,163,184,.12)');
    return `<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;border:1px solid ${cardBorder};background:${cardBg};transition:all .2s;cursor:pointer" title="${a.id}" onclick="switchTab('live-office',document.querySelector('nav button[onclick*=\\'live-office\\']'))">
      <div style="font-size:1.2em;flex-shrink:0">${emoji}</div>
      <div style="min-width:0;flex:1">
        <div style="font-size:.8em;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(a.id)}</div>
        <div style="font-size:.7em;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(task)}</div>
      </div>
      <div style="width:7px;height:7px;border-radius:50%;background:${dotColor};flex-shrink:0;${isActive||isRunning?'box-shadow:0 0 6px '+dotColor:''}"></div>
    </div>`;
  }).join('');
}

async function loadLiveOffice() {
  const container = document.getElementById('office-agents');
  if (!container) return;
  const data = await api('/api/workers');
  if (!data || data.ok === false) {
    container.innerHTML = '<div class="empty" style="padding-top:80px"><div class="icon">⚠️</div><p>Live office unavailable right now.</p></div>';
    return;
  }

  const list = Array.isArray(data.agents) ? data.agents : [];
  const agents = list.filter(a => a && a.running).slice(0, 20);
  const countEl = document.getElementById('office-agent-count');
  if (countEl) countEl.textContent = agents.length + ' agent' + (agents.length !== 1 ? 's' : '') + ' active';
  if (!agents.length) {
    container.innerHTML = `<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px">
    <div style="width:80px;height:80px;border-radius:50%;border:3px solid rgba(212,175,55,.3);display:flex;align-items:center;justify-content:center;font-size:2em;animation:robotWalk 3s ease-in-out infinite">🤖</div>
    <div style="text-align:center">
      <div style="font-size:1em;font-weight:700;color:var(--gold);margin-bottom:6px">No Active Agents</div>
      <div style="font-size:.8em;color:var(--text-muted);max-width:260px;line-height:1.6">Your AI workforce is standing by. Start agents from the Dashboard to see them appear here and work on your tasks.</div>
    </div>
    <button class="btn btn-primary btn-sm" onclick="startAll();setTimeout(loadLiveOffice,3000)" style="background:linear-gradient(135deg,#B8960C,#D4AF37);color:#000;border:none;font-weight:700">▶ Start All Agents</button>
  </div>`;
    return;
  }

  const agentIcons = {
    'task-orchestrator':'🎯','lead-generator':'🎯','lead-hunter':'🎯',
    'brand-strategist':'🎨','finance-wizard':'💰','growth-hacker':'📈',
    'social-media-manager':'📱','content-master':'✍️','email-ninja':'📧',
    'intel-agent':'🔍','company-builder':'🏢','hr-manager':'👔',
    'project-manager':'📋','crypto-trader':'📈','ecom-agent':'🛒',
    'support-bot':'🎧','creative-studio':'🎨','data-analyst':'📊',
    'web-researcher':'🌐','chatbot-builder':'🤖','recruiter':'👔',
  };
  const icons = ['🤖','🦾','🧠','⚙️','🔬','📊','💡','🎯'];
  container.innerHTML = agents.map((agent, idx) => {
    const name = agent.name || agent.id || 'agent';
    const cols = Math.min(agents.length, 6);
    const left = 4 + (idx % cols) * (92 / cols);
    const row = Math.floor(idx / cols);
    const hasAlert = !!agent.alert;
    const isBusy = agent.progress >= 50 || hasAlert;
    const icon = agentIcons[name] || icons[idx % icons.length];
    const animDur = 2.5 + (idx % 4) * 0.7;
    const animName = idx % 2 === 0 ? 'robotWalk' : 'robotWalk2';
    const bodyClass = hasAlert ? 'alert' : (isBusy ? 'busy' : '');
    const dotClass = hasAlert ? 'alert' : (agent.running ? (isBusy ? 'busy' : 'running') : '');
    const alertBadge = hasAlert ? `<div class="robot-alert-badge">⚠</div>` : '';
    return `<div class="robot-agent" role="button" tabindex="0" aria-label="${escHtml(name)} – ${hasAlert ? 'ERROR' : (isBusy ? 'busy' : 'idle')}" style="position:absolute;left:${left}%;bottom:${140 + row * 80}px;animation-name:${animName};animation-duration:${animDur}s" onclick="openOfficeModal('${encodeURIComponent(JSON.stringify(agent))}')" onkeydown="if(event.key==='Enter'||event.key===' ')openOfficeModal('${encodeURIComponent(JSON.stringify(agent))}')">
      ${alertBadge}
      <div class="robot-body ${bodyClass}">${icon}</div>
      <div class="robot-status-dot ${dotClass}"></div>
      <div class="robot-name ${hasAlert ? 'alert' : ''}">${escHtml(name)}</div>
    </div>`;
  }).join('');
}

function openOfficeModal(agentJson) {
  let agent;
  try {
    agent = JSON.parse(decodeURIComponent(agentJson));
  } catch {
    toast('Could not open agent details', 'error');
    return;
  }
  if (!agent || typeof agent !== 'object') return;

  const modal = document.getElementById('office-modal');
  if (!modal) return;
  modal.classList.add('open');
  const titleEl = document.getElementById('office-modal-title');
  const statusEl = document.getElementById('office-modal-status');
  const progressEl = document.getElementById('office-modal-progress');
  const timeEl = document.getElementById('office-modal-time');
  const actionEl = document.getElementById('office-modal-action');
  if (!titleEl || !statusEl || !progressEl || !timeEl || !actionEl) return;

  titleEl.textContent = agent.name || agent.id || 'Agent';
  if (agent.alert) {
    statusEl.innerHTML = '<span style="color:#f87171;font-weight:700">⚠️ ALERT: ' + escHtml(agent.alert_reason || 'Agent error detected') + '</span>';
    statusEl.style.background = 'rgba(239,68,68,.1)';
    statusEl.style.padding = '6px 10px';
    statusEl.style.borderRadius = '6px';
    statusEl.style.border = '1px solid rgba(239,68,68,.3)';
  } else {
    statusEl.textContent = agent.running ? 'Status: Running and processing tasks' : 'Status: Currently stopped';
    statusEl.style.background = '';
    statusEl.style.padding = '';
    statusEl.style.borderRadius = '';
    statusEl.style.border = '';
  }
  const progress = agent.running ? (agent.progress || 15) : 0;
  progressEl.style.width = progress + '%';
  timeEl.textContent = agent.running ? `${agent.elapsed_minutes || 0} min` : '-';
  actionEl.textContent = agent.running
    ? (agent.alert ? `Error: ${agent.alert_reason || 'Unknown error'}` : (agent.last_action || 'Analyzing assigned workload'))
    : 'Waiting for assignment';
}

function closeOfficeModal() {
  document.getElementById('office-modal')?.classList.remove('open');
}

// ── Gateway Modal ────────────────────────────────────────────────────────────
let _gwSelectedProvider = 'ollama';
let _gwSelectedModel = 'llama3.2';

function openGatewayModal() {
  const modal = document.getElementById('gateway-modal');
  if (!modal) return;
  modal.classList.add('open');
  // checkGatewayStatus also loads current provider/model from /api/gateway/status
  checkGatewayStatus();
}

function closeGatewayModal() {
  document.getElementById('gateway-modal')?.classList.remove('open');
}

function selectGatewayProvider(provider) {
  _gwSelectedProvider = provider;
  updateGatewayUI();
}

function setOllamaModel(model, btn) {
  _gwSelectedModel = model;
  document.querySelectorAll('.gw-model-pill').forEach(b => {
    b.classList.remove('active');
    b.style.background = '';
    b.style.color = '';
    b.style.border = '';
  });
  if (btn) {
    btn.classList.add('active');
    btn.style.background = 'linear-gradient(135deg,var(--primary-dark),var(--primary))';
    btn.style.color = '#000';
    btn.style.border = 'none';
  }
}

function updateGatewayUI() {
  const ollamaCard = document.getElementById('gw-card-ollama');
  const nvidiaCard = document.getElementById('gw-card-nvidia');
  const providerLabel = document.getElementById('gw-provider-label');
  const ollamaSection = document.getElementById('gw-ollama-section');
  if (ollamaCard) {
    ollamaCard.style.border = _gwSelectedProvider === 'ollama' ? '2px solid rgba(212,175,55,.7)' : '2px solid rgba(148,163,184,.2)';
    ollamaCard.style.background = _gwSelectedProvider === 'ollama' ? 'rgba(212,175,55,.08)' : 'rgba(148,163,184,.03)';
  }
  if (nvidiaCard) {
    nvidiaCard.style.border = _gwSelectedProvider === 'nvidia' ? '2px solid rgba(56,189,248,.6)' : '2px solid rgba(148,163,184,.2)';
    nvidiaCard.style.background = _gwSelectedProvider === 'nvidia' ? 'rgba(56,189,248,.06)' : 'rgba(148,163,184,.03)';
  }
  if (providerLabel) {
    const labels = {ollama:'🦙 Ollama (local)', nvidia:'🔷 NVIDIA NIM', groq:'⚡ Groq', openai:'🌐 OpenAI', anthropic:'🤖 Claude'};
    providerLabel.textContent = labels[_gwSelectedProvider] || _gwSelectedProvider;
  }
  if (ollamaSection) ollamaSection.style.display = _gwSelectedProvider === 'ollama' ? 'block' : 'none';
}

async function checkGatewayStatus() {
  // Use backend API to check status (avoids hardcoded localhost URL in browser)
  const ollamaStatus = document.getElementById('gw-ollama-status');
  const nvidiaStatus = document.getElementById('gw-nvidia-status');
  try {
    const d = await api('/api/gateway/status');
    if (d.ollama_ok) {
      const models = d.ollama_models || [];
      if (ollamaStatus) {
        ollamaStatus.textContent = '✅ Online — ' + (models.length ? models.slice(0,3).join(', ') : 'no models pulled');
        ollamaStatus.style.background = 'rgba(16,185,129,.15)';
        ollamaStatus.style.color = 'var(--success)';
      }
      // Show pull section if selected model not yet downloaded
      const pullSection = document.getElementById('gw-pull-section');
      const pullBtn = document.getElementById('gw-pull-btn');
      const modelExists = models.some(m => m.startsWith(_gwSelectedModel));
      if (pullSection) pullSection.style.display = modelExists ? 'none' : 'block';
      if (pullBtn) pullBtn.textContent = `⬇️ ollama pull ${_gwSelectedModel}`;
    } else {
      if (ollamaStatus) {
        ollamaStatus.textContent = '⚠️ Offline — install Ollama first';
        ollamaStatus.style.background = 'rgba(239,68,68,.1)';
        ollamaStatus.style.color = '#f87171';
      }
    }
    if (nvidiaStatus) {
      if (d.nvidia_ok) {
        nvidiaStatus.textContent = '✅ Configured';
        nvidiaStatus.style.background = 'rgba(16,185,129,.15)';
        nvidiaStatus.style.color = 'var(--success)';
      } else {
        nvidiaStatus.textContent = 'Add NVIDIA_API_KEY in Settings';
        nvidiaStatus.style.background = 'rgba(148,163,184,.1)';
        nvidiaStatus.style.color = 'var(--text-muted)';
      }
    }
    // Pre-select current provider
    if (d.current_provider) { _gwSelectedProvider = d.current_provider; }
    if (d.current_model) { _gwSelectedModel = d.current_model; }
    updateGatewayUI();
  } catch {
    if (ollamaStatus) { ollamaStatus.textContent = '⚠️ Could not check status'; }
  }
}

async function pullOllamaModel() {
  const btn = document.getElementById('gw-pull-btn');
  if (btn) { btn.textContent = '⏳ Pulling…'; btn.disabled = true; }
  toast(`⬇️ Running: ollama pull ${_gwSelectedModel} — this may take a few minutes`, 'info');
  const r = await api('/api/gateway/pull-model', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({model: _gwSelectedModel})});
  if (r.ok) {
    toast(`✅ Model ${_gwSelectedModel} ready!`, 'success');
    checkGatewayStatus();
  } else {
    toast(r.error || 'Pull failed. Run manually: ollama pull ' + _gwSelectedModel, 'error');
  }
  if (btn) { btn.disabled = false; }
}

async function applyGatewayProvider() {
  const resultEl = document.getElementById('gw-result');
  const payload = {AI_PROVIDER: _gwSelectedProvider};
  if (_gwSelectedProvider === 'ollama') payload.OLLAMA_MODEL = _gwSelectedModel;
  const r = await api('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({updates: payload})});
  if (r.ok) {
    toast(`✅ Gateway set to ${_gwSelectedProvider.toUpperCase()} · model: ${_gwSelectedProvider === 'ollama' ? _gwSelectedModel : 'default'}`, 'success');
    if (resultEl) { resultEl.style.color = 'var(--success)'; resultEl.textContent = '✓ Settings saved. Restart agents for changes to take effect.'; }
    setTimeout(closeGatewayModal, 1800);
  } else {
    toast(r.error || 'Failed to save gateway settings', 'error');
    if (resultEl) { resultEl.style.color = 'var(--danger)'; resultEl.textContent = r.error || 'Save failed'; }
  }
}

async function startAll() {
  _setStartStopDisabled(true);
  const heroBtn = document.getElementById('hero-start-btn');
  if (heroBtn) heroBtn.innerHTML = '<span class="spinner">⟳</span> Starting…';
  try {
    const res = await api('/api/agents/start-all', {method:'POST'});
    const failed = (res.failed || []).length;
    const missing = (res.missing_agents || []).length;
    const skippedGov = (res.skipped_by_governor || []).length;
    const skippedBreaker = (res.skipped_by_breaker || []).length;
    const provisioned = (res.provisioned_from_repo || []).length;
    const dup = (res.already_running || []).length;
    if (res.ok) {
      const parts = [];
      if (dup) parts.push(`${dup} already running`);
      if (provisioned) parts.push(`${provisioned} provisioned`);
      const extra = parts.length ? ` · ${parts.join(' · ')}` : '';
      toast(`▶ Started ${res.started || 0}/${res.configured_count || 0} agents (${res.mode || 'mode'})${extra}`, 'success');
    } else {
      const details = [];
      if (failed) details.push(`${failed} failed`);
      if (missing) details.push(`${missing} missing`);
      if (skippedGov) details.push(`${skippedGov} governor-skipped`);
      if (skippedBreaker) details.push(`${skippedBreaker} breaker-skipped`);
      const suffix = details.length ? ` (${details.join(' · ')})` : '';
      toast(`⚠ Start issue: ${res.error || `started ${res.started || 0}/${res.configured_count || 0}${suffix}`}`, 'error');
    }
    await loadDashboard();
  } finally {
    _setStartStopDisabled(false);
    if (heroBtn) heroBtn.innerHTML = '<span class="btn-icon">▶</span> Start All Agents';
  }
}

async function stopAll() {
  if (!confirm('Stop all running agents?')) return;
  _setStartStopDisabled(true);
  const heroBtn = document.getElementById('hero-stop-btn');
  if (heroBtn) heroBtn.innerHTML = '<span class="spinner">⟳</span> Stopping…';
  try {
    const res = await api('/api/agents/stop-all', {method:'POST'});
    const dur = (res.shutdown && Number.isFinite(res.shutdown.duration_ms)) ? `${res.shutdown.duration_ms}ms` : 'n/a';
    if (res.ok) {
      toast(`■ Stopped ${res.stopped || 0} agents in ${dur}`, 'success');
    } else {
      toast(`⚠ Stop issue: stopped ${res.stopped || 0}, failed: ${(res.failed || []).join(', ') || 'unknown'} (${dur})`, 'error');
    }
    await loadDashboard();
  } finally {
    _setStartStopDisabled(false);
    if (heroBtn) heroBtn.innerHTML = '<span class="btn-icon">■</span> Stop All Agents';
  }
}

async function runOnboard() {
  const btn = document.querySelector('button[onclick="runOnboard()"]');
  if (btn) btn.disabled = true;
  toast('⚡ Running onboarding workflow…', 'info');
  const r = await api('/api/quick-actions/onboard', {method:'POST'});
  if (r.ok) {
    toast('✅ Onboard started. Check Chat, Tasks, and ROI tabs for progress.', 'success');
    loadChatLog();
    loadTasks();
    loadMetrics();
  } else {
    toast(r.detail || r.error || 'Failed to run onboard', 'error');
  }
  if (btn) btn.disabled = false;
}

// ── Chat ────────────────────────────────────────────────────────────────────
function renderMarkdown(str) {
  return str
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,'<em>$1</em>')
    .replace(/`(.+?)`/g,'<code>$1</code>')
    .replace(/^### (.+)$/gm,'<h3>$1</h3>')
    .replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^# (.+)$/gm,'<h1>$1</h1>')
    .replace(/^- (.+)$/gm,'<li>$1</li>')
    .replace(/\n\n/g,'<br><br>')
    .replace(/\n/g,'<br>');
}

async function loadChatLog() {
  try {
    if (typeof _updateChatHermesStatus === 'function') _updateChatHermesStatus();
  } catch(e) {}
  try {
    const r = await fetch('/api/chat');
    if (!r.ok) return;
    const d = await r.json();
    const msgs = d.messages || [];
    const log = document.getElementById('chat-log');
    if (!log) return;
    const empty = document.getElementById('chat-empty');
    if (!msgs.length) { if(empty) empty.style.display='flex'; return; }
    if (empty) empty.style.display = 'none';

    function sourceFrom(m) {
      if (m.type === 'user') return {sym:'\u203a', label:'YOU'};
      const t = String(m.message||'');
      if (t.includes('Agent: finance-wizard')) return {sym:'\u25c6',label:'FINANCE'};
      if (t.includes('Agent: lead-generator')) return {sym:'\u25ce',label:'LEAD-GEN'};
      if (t.includes('Agent: social-guru')) return {sym:'\u25c9',label:'SOCIAL'};
      if (t.includes('Agent:')) return {sym:'\u25c8',label:t.split('Agent:')[1].split('\n')[0].trim().toUpperCase().slice(0,12)};
      return {sym:'\u25c8',label:'AI-SYSTEM'};
    }

    const existingMsgs = log.querySelectorAll('.msg-wrap');
    existingMsgs.forEach(m => m.remove());
    if (empty) empty.style.display = 'none';

    const frag = document.createDocumentFragment();
    msgs.slice(-60).forEach(m => {
      const isUser = m.type === 'user';
      const {sym, label} = sourceFrom(m);
      const text = renderMarkdown(m.message || m.question || '');
      const ts = (m.ts||'').replace('T',' ').slice(0,16);
      const wrap = document.createElement('div');
      wrap.className = 'msg-wrap ' + (isUser ? 'user' : 'agent');
      wrap.innerHTML = `<div class="msg-meta">
          <div class="msg-avatar">${sym}</div>
          <span class="msg-source">${escHtml(label)}</span>
          <span class="msg-ts">${escHtml(ts)}</span>
        </div>
        <div class="msg-bubble">${text}</div>`;
      frag.appendChild(wrap);
    });
    log.appendChild(frag);
    log.scrollTop = log.scrollHeight;
    if (typeof sysLog === 'function') sysLog('// CHAT SYNC OK','ok');
  } catch(e) { if (typeof sysLog === 'function') sysLog('// CHAT SYNC FAIL','err'); }
}

function updateChatModelBadge() {
  const sel = document.getElementById('chat-model');
  const badge = document.getElementById('chat-model-badge');
  const indicator = document.getElementById('chat-agent-indicator');
  if (!sel || !badge) return;
  const labels = {auto:'AUTO',ollama:'OLLAMA',gemma:'GEMMA',nvidia:'NVIDIA NIM',openai:'OPENAI',anthropic:'CLAUDE',groq:'GROQ',external:'EXTERNAL'};
  const hints = {auto:'Auto-routing active',ollama:'Local Ollama',gemma:'Google Gemma',nvidia:'NVIDIA NIM',openai:'OpenAI GPT-4o',anthropic:'Anthropic Claude',groq:'Groq fast inference',external:'External provider'};
  badge.textContent = labels[sel.value] || sel.value.toUpperCase();
  if (indicator) indicator.textContent = hints[sel.value] || 'Auto-routing active';
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  let q = input?.value?.trim();
  if (!q) return;
  const route = document.getElementById('chat-model')?.value || 'auto';

  // Auto-detect rough ideas and expand them silently before sending
  if (_looksLikeIdea(q)) {
    input.value = '';
    const log = document.getElementById('chat-log');
    const empty = document.getElementById('chat-empty');
    if (empty) empty.style.display = 'none';
    // Show the original idea as the user bubble
    if (log) {
      const userWrap = document.createElement('div');
      userWrap.className = 'msg-wrap user';
      userWrap.innerHTML = `<div class="msg-meta">
          <div class="msg-avatar">\u203a</div>
          <span class="msg-source">YOU</span>
          <span class="msg-ts">${new Date().toTimeString().slice(0,8)}</span>
        </div>
        <div class="msg-bubble">${renderMarkdown(q)}</div>`;
      log.appendChild(userWrap);
      log.scrollTop = log.scrollHeight;
    }
    // Show "💡 Expanding idea…" indicator
    const ideaId = 'idea-expand-' + Date.now();
    if (log) {
      const wrap = document.createElement('div');
      wrap.className = 'msg-wrap agent';
      wrap.id = ideaId;
      wrap.innerHTML = `<div class="msg-meta"><div class="msg-avatar">💡</div><span class="msg-source">AI-SYSTEM</span></div>
        <div class="msg-thinking">
          <span style="font-family:var(--mono);font-size:.72em;color:rgba(245,196,0,0.4)">EXPANDING IDEA</span>
          <div class="think-dots"><div class="think-dot"></div><div class="think-dot"></div><div class="think-dot"></div></div>
        </div>`;
      log.appendChild(wrap);
      log.scrollTop = log.scrollHeight;
    }
    if (typeof sysLog === 'function') sysLog('// IDEA: auto-expanding…');
    try {
      const r = await api('/api/idea/convert', {
        method: 'POST',
        body: JSON.stringify({ idea: q })
      });
      if (r && r.ok) {
        q = r.prompt;
        if (typeof sysLog === 'function') sysLog(`// IDEA: expanded via ${r.provider||'AI'}`, 'ok');
      }
    } catch(_) { /* fall through with original q */ }
    document.getElementById(ideaId)?.remove();
    // Now dispatch the (possibly expanded) prompt
    const thinkId2 = 'thinking-' + Date.now();
    if (log) {
      const wrap2 = document.createElement('div');
      wrap2.className = 'msg-wrap agent';
      wrap2.id = thinkId2;
      wrap2.innerHTML = `<div class="msg-meta"><div class="msg-avatar">\u25c8</div><span class="msg-source">AI-SYSTEM</span></div>
        <div class="msg-thinking">
          <span style="font-family:var(--mono);font-size:.72em;color:rgba(245,196,0,0.4)">PROCESSING</span>
          <div class="think-dots"><div class="think-dot"></div><div class="think-dot"></div><div class="think-dot"></div></div>
        </div>`;
      log.appendChild(wrap2);
      log.scrollTop = log.scrollHeight;
    }
    try {
      await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:q,model_route:route})});
      document.getElementById(thinkId2)?.remove();
      if (typeof sysLog === 'function') sysLog('// RESPONSE RECEIVED','ok');
      await loadChatLog();
    } catch(e) {
      document.getElementById(thinkId2)?.remove();
      if (typeof sysLog === 'function') sysLog('// TRANSMIT ERROR','err');
    }
    return;
  }

  input.value = '';
  const log = document.getElementById('chat-log');
  const empty = document.getElementById('chat-empty');
  if (empty) empty.style.display = 'none';

  if (log) {
    const userWrap = document.createElement('div');
    userWrap.className = 'msg-wrap user';
    userWrap.innerHTML = `<div class="msg-meta">
        <div class="msg-avatar">\u203a</div>
        <span class="msg-source">YOU</span>
        <span class="msg-ts">${new Date().toTimeString().slice(0,8)}</span>
      </div>
      <div class="msg-bubble">${renderMarkdown(q)}</div>`;
    log.appendChild(userWrap);
    log.scrollTop = log.scrollHeight;
  }

  if (typeof sysLog === 'function') sysLog(`// CMD: ${q.slice(0,40)}${q.length>40?'\u2026':''}`);

  const thinkId = 'thinking-' + Date.now();
  if (log) {
    const wrap = document.createElement('div');
    wrap.className = 'msg-wrap agent';
    wrap.id = thinkId;
    wrap.innerHTML = `<div class="msg-meta"><div class="msg-avatar">\u25c8</div><span class="msg-source">AI-SYSTEM</span></div>
      <div class="msg-thinking">
        <span style="font-family:var(--mono);font-size:.72em;color:rgba(245,196,0,0.4)">PROCESSING</span>
        <div class="think-dots"><div class="think-dot"></div><div class="think-dot"></div><div class="think-dot"></div></div>
      </div>`;
    log.appendChild(wrap);
    log.scrollTop = log.scrollHeight;
  }

  try {
    await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:q,model_route:route})});
    document.getElementById(thinkId)?.remove();
    if (typeof sysLog === 'function') sysLog('// RESPONSE RECEIVED','ok');
    await loadChatLog();
  } catch(e) {
    document.getElementById(thinkId)?.remove();
    if (typeof sysLog === 'function') sysLog('// TRANSMIT ERROR','err');
  }
}

function clearChatDisplay() {
  const log = document.getElementById('chat-log');
  const empty = document.getElementById('chat-empty');
  if (log) log.querySelectorAll('.msg-wrap').forEach(m => m.remove());
  if (empty) empty.style.display = 'flex';
  if (typeof sysLog === 'function') sysLog('// DISPLAY CLEARED');
}

// ── Scheduler ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const actionEl = document.getElementById('sched-action');
  const typeEl = document.getElementById('sched-type');
  const botRow = document.getElementById('sched-bot-row');
  const intervalRow = document.getElementById('sched-interval-row');
  const dailyRow = document.getElementById('sched-daily-row');

  if (actionEl && botRow) {
    const updateAction = () => {
      botRow.style.display = (actionEl.value === 'start_bot' || actionEl.value === 'stop_bot') ? 'block' : 'none';
    };
    actionEl.addEventListener('change', updateAction);
    updateAction();
  }

  if (typeEl && intervalRow && dailyRow) {
    const updateType = () => {
      intervalRow.style.display = typeEl.value === 'interval' ? 'block' : 'none';
      dailyRow.style.display = typeEl.value === 'daily' ? 'block' : 'none';
    };
    typeEl.addEventListener('change', updateType);
    updateType();
  }

  loadDashboard();
  loadDoctorPanel();
  if (!_allAgents.length) loadSwarm();
  renderAgenda();
});

async function loadSchedules() {
  const data = await api('/api/schedules');
  const tasks = data.tasks || [];
  const el = document.getElementById('schedule-list');
  if (!tasks.length) { el.innerHTML = '<div class="empty"><div class="icon">📅</div><p>No scheduled tasks yet.</p></div>'; return; }
  el.innerHTML = tasks.map(t => {
    const info = t.type==='interval' ? `every ${t.interval_minutes||60}m` : `daily at ${t.run_at_utc||'?'} UTC`;
    const enabled = t.enabled !== false;
    return `<div class="sched-row">
      <div class="sched-info">
        <h4>${t.label||t.id} <span class="badge ${enabled?'enabled':'disabled'}">${enabled?'enabled':'disabled'}</span></h4>
        <p>${t.action} · ${info}</p>
      </div>
      <button class="btn btn-danger btn-sm" onclick="deleteSchedule('${t.id}')">✕</button>
    </div>`;
  }).join('');
}

let _agendaView = 'month';
let _agendaDate = new Date();
function setAgendaView(view, btn) {
  _agendaView = view;
  document.querySelectorAll('.agenda-view-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderAgenda();
}
function agendaNav(dir) {
  if (_agendaView === 'month') _agendaDate.setMonth(_agendaDate.getMonth() + dir);
  else if (_agendaView === 'week') _agendaDate.setDate(_agendaDate.getDate() + dir * 7);
  else _agendaDate.setDate(_agendaDate.getDate() + dir);
  renderAgenda();
}
function renderAgenda() {
  const p = document.getElementById('agenda-period');
  const g = document.getElementById('agenda-grid');
  if (!p || !g) return;
  const d = _agendaDate;
  if (_agendaView === 'month') {
    const today = new Date();
    p.textContent = d.toLocaleDateString('en-US', {month:'long',year:'numeric'});
    const first = new Date(d.getFullYear(), d.getMonth(), 1);
    const last = new Date(d.getFullYear(), d.getMonth()+1, 0);
    const days = ['Su','Mo','Tu','We','Th','Fr','Sa'];
    let html = days.map(dy => '<div style="text-align:center;color:var(--text-muted);padding:4px;font-size:.7em">' + dy + '</div>').join('');
    for (let i = 0; i < first.getDay(); i++) html += '<div></div>';
    for (let i = 1; i <= last.getDate(); i++) {
      const isToday = i === today.getDate() && d.getMonth() === today.getMonth() && d.getFullYear() === today.getFullYear();
      html += '<div onclick="selectAgendaDay(' + i + ')" style="text-align:center;padding:5px 2px;border-radius:4px;cursor:pointer;font-size:.78em;' + (isToday ? 'background:rgba(212,175,55,.2);color:var(--gold);font-weight:700;' : '') + '">' + i + '</div>';
    }
    g.style.display = 'grid';
    g.style.gridTemplateColumns = 'repeat(7,1fr)';
    g.innerHTML = html;
  } else if (_agendaView === 'week') {
    const today = new Date();
    // Show a 7-column week grid with day names + date numbers
    const startOfWeek = new Date(d);
    startOfWeek.setDate(d.getDate() - d.getDay());
    const endOfWeek = new Date(startOfWeek);
    endOfWeek.setDate(startOfWeek.getDate() + 6);
    p.textContent = startOfWeek.toLocaleDateString('en-US',{month:'short',day:'numeric'}) + ' – ' + endOfWeek.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
    const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    let html = '';
    for (let i = 0; i < 7; i++) {
      const day = new Date(startOfWeek);
      day.setDate(startOfWeek.getDate() + i);
      const isToday = day.toDateString() === today.toDateString();
      html += `<div onclick="selectAgendaFull(${JSON.stringify(day.toDateString())})" style="text-align:center;padding:8px 2px;border-radius:6px;cursor:pointer;border:1px solid ${isToday?'rgba(212,175,55,.5)':'transparent'};background:${isToday?'rgba(212,175,55,.12)':'transparent'}">
        <div style="font-size:.68em;color:var(--text-muted);margin-bottom:3px">${days[i]}</div>
        <div style="font-size:.88em;font-weight:${isToday?700:400};color:${isToday?'var(--gold)':'var(--text)'}">${day.getDate()}</div>
      </div>`;
    }
    g.style.display = 'grid';
    g.style.gridTemplateColumns = 'repeat(7,1fr)';
    g.innerHTML = html;
  } else if (_agendaView === 'day') {
    p.textContent = d.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'});
    const hours = [7,8,9,10,11,12,13,14,15,16,17,18,19,20];
    let html = hours.map(h => {
      const label = h < 12 ? h+':00 AM' : h===12 ? '12:00 PM' : (h-12)+':00 PM';
      return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid rgba(148,163,184,.06);font-size:.72em">
        <span style="color:var(--text-muted);min-width:52px">${label}</span>
        <div style="flex:1;height:20px;border-radius:3px;background:transparent"></div>
      </div>`;
    }).join('');
    g.style.display = 'block';
    g.style.gridTemplateColumns = '';
    g.innerHTML = html;
  }
}
function selectAgendaFull(dateStr) {
  const el = document.getElementById('agenda-day-label');
  if (el) { const d = new Date(dateStr); el.textContent = d.toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'}); }
}
function selectAgendaDay(day) {
  const el = document.getElementById('agenda-day-label');
  if (el) el.textContent = _agendaDate.toLocaleDateString('en-US',{month:'short'}) + ' ' + day;
}

function toggleSchedBot() {
  const v = document.getElementById('sched-action').value;
  const el = document.getElementById('sched-bot-row');
  if (el) el.style.display = (v === 'start_bot' || v === 'stop_bot') ? 'block' : 'none';
}

function toggleSchedType() {
  const t = document.getElementById('sched-type').value;
  document.getElementById('sched-interval-row').style.display = t === 'interval' ? '' : 'none';
  document.getElementById('sched-daily-row').style.display = t === 'daily' ? '' : 'none';
  const onceRow = document.getElementById('sched-once-row');
  if (onceRow) onceRow.style.display = t === 'once' ? '' : 'none';
  const weeklyRow = document.getElementById('sched-weekly-row');
  if (weeklyRow) weeklyRow.style.display = t === 'weekly' ? '' : 'none';
}

async function addSchedule() {
  const id = document.getElementById('sched-id').value.trim();
  const label = document.getElementById('sched-label').value.trim();
  const action = document.getElementById('sched-action').value;
  const bot = document.getElementById('sched-bot').value.trim();
  const msg = document.getElementById('sched-msg').value.trim();
  const type = document.getElementById('sched-type').value;
  const interval = parseInt(document.getElementById('sched-interval').value) || 60;
  const dailyTime = document.getElementById('sched-daily-time').value.trim();

  if (!id || !label) { toast('ID and label are required', 'error'); return; }

  const task = {id, label, action, type, enabled: true,
    ...(bot && {bot}), ...(msg && {message: msg}),
    ...(type==='interval' && {interval_minutes: interval}),
    ...(type==='daily' && {run_at_utc: dailyTime||'08:00'}),
  };

  const r = await api('/api/schedules', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(task)});
  if (r.ok) { toast('Task added!'); loadSchedules(); }
  else { toast(r.error||'Error', 'error'); }
}

async function deleteSchedule(id) {
  if (!confirm(`Delete task "${id}"?`)) return;
  const r = await api(`/api/schedules/${id}`, {method:'DELETE'});
  if (r.ok) { toast('Task deleted'); loadSchedules(); }
}

// ── Workers ─────────────────────────────────────────────────────────────────
// ── Bundle management ───────────────────────────────────────────────────────
let _wfSelectedAgents = new Set();
let _workerBundlesById = {};

async function loadWorkers() {
  // Populate swarm agent grid for preset bundles
  if (_allAgents.length) renderSwarmAgentGrid();
  // Load bundles
  const bd = await api('/api/workers/bundles');
  const bundles = (bd && bd.bundles) || [];
  _workerBundlesById = Object.fromEntries(bundles.map(b => [b.id, b]));
  const bundleEl = document.getElementById('bundle-list');
  if (!bundles.length) {
    bundleEl.innerHTML = '<div class="empty"><div class="icon">🏭</div><p>No agent teams yet. Click <strong>+ New Agent Team</strong> to create one.</p></div>';
  } else {
    bundleEl.innerHTML = bundles.map(b => {
      const enabled = b.enabled !== false;
      const statusColor = enabled ? '#10b981' : '#64748b';
      const agents = (b.agents || []).map(a => `<span style="background:rgba(212,175,55,.08);padding:2px 7px;border-radius:4px;font-size:.7em;color:var(--gold-light);border:1px solid rgba(212,175,55,.18)">${escHtml(a)}</span>`).join(' ');
      const schedMap = {continuous:'🔄 Continuous', hourly:'⏰ Hourly', every6h:'⏰ Every 6h', daily:'🌙 Daily 2AM', '3x_daily':'☀️ 3× Daily', weekly:'📅 Weekly', manual:'🖱 Manual'};
      const schedLabel = schedMap[b.schedule] || b.schedule || 'manual';
      const lastRun = b.last_run ? `Last: ${b.last_run.split('T')[0]}` : 'Never run';
      return `<div style="border:1px solid ${enabled ? 'rgba(16,185,129,.2)' : 'var(--border)'};border-radius:var(--radius);padding:16px;margin-bottom:10px;border-left:4px solid ${statusColor};background:var(--surface2);transition:all .2s" class="js-card-row-hover">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
          <div style="flex:1">
            <div style="font-weight:700;font-size:.95em;display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px">
              🏭 ${escHtml(b.name)}
              <span style="font-size:.7em;background:${enabled ? 'rgba(16,185,129,.15)' : 'rgba(100,116,139,.15)'};color:${statusColor};border-radius:4px;padding:2px 7px;border:1px solid ${enabled ? 'rgba(16,185,129,.25)' : 'rgba(100,116,139,.25)'}">${enabled ? 'enabled' : 'disabled'}</span>
              <span style="font-size:.7em;color:var(--text-muted);background:var(--surface);padding:2px 7px;border-radius:4px;border:1px solid var(--border)">${schedLabel}</span>
            </div>
            <div style="font-size:.82em;color:var(--text-secondary);margin-bottom:6px;line-height:1.5">${escHtml((b.task_description||'').slice(0,120))}${(b.task_description||'').length>120?'…':''}</div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px">${agents}</div>
            <div style="font-size:.72em;color:var(--text-muted)">${lastRun}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:5px;min-width:88px">
            <button class="btn btn-primary btn-sm" onclick="runBundle('${escHtml(b.id)}')">▶ Run</button>
            <button class="btn btn-ghost btn-sm" onclick="editBundleById('${escHtml(b.id)}')">✏️ Edit</button>
            <button class="btn btn-ghost btn-sm" onclick="toggleBundle('${escHtml(b.id)}', ${!enabled})">${enabled ? '⏸ Pause' : '▶ Enable'}</button>
            <button class="btn btn-ghost btn-sm" onclick="deleteBundle('${escHtml(b.id)}')" style="color:var(--danger);border-color:rgba(239,68,68,.3)">🗑 Delete</button>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  // Load agent workers
  const wd = await api('/api/workers');
  const agents_list = (wd && wd.agents) || [];
  const el = document.getElementById('worker-list');
  if (!agents_list.length) { el.innerHTML = '<div class="empty"><div class="icon">👷</div><p>No agents found.</p></div>'; return; }
  el.innerHTML = agents_list.map(b => {
    const cls = b.running ? 'on' : 'off';
    const progressColor = b.progress > 70 ? '#34d399' : b.progress > 30 ? '#D4AF37' : '#6b7280';
    const lbl = b.running ? 'running' : 'stopped';
    const startBtn = b.running ? '' : `<button class="btn btn-success btn-sm" onclick="startBot('${b.name}')">▶ Start</button>`;
    const stopBtn = b.running ? `<button class="btn btn-danger btn-sm" onclick="stopBot('${b.name}')">■ Stop</button>` : '';
    return `<div class="sched-row">
      <div class="dot ${cls}" style="margin-top:4px;flex-shrink:0"></div>
      ${b.running && b.progress > 0 ? `<div style="flex:1;max-width:80px;background:rgba(255,255,255,.05);border-radius:4px;height:4px;overflow:hidden;margin:0 8px"><div style="width:${b.progress}%;height:100%;background:${progressColor};transition:width .5s"></div></div>` : ''}
      <div class="sched-info"><h4>${b.name} <span class="badge ${lbl}">${lbl}</span></h4></div>
      <div style="display:flex;gap:6px">${startBtn}${stopBtn}</div>
    </div>`;
  }).join('');
}

async function openCreateWorker(prefill) {
  document.getElementById('wf-editing-id').value = '';
  document.getElementById('wf-name').value = (prefill && prefill.name) || '';
  document.getElementById('wf-task').value = (prefill && prefill.task_description) || '';
  document.getElementById('wf-desc').value = (prefill && prefill.description) || '';
  document.getElementById('wf-schedule').value = (prefill && prefill.schedule) || 'continuous';
  document.getElementById('worker-form-title').textContent = 'Create Agent Team';
  document.getElementById('wf-save-btn').textContent = '💾 Save Agent Team';
  document.getElementById('wf-save-result').textContent = '';
  _wfSelectedAgents = new Set((prefill && prefill.agents) || []);
  if (!_allAgents.length) {
    await loadSwarm();
  }
  renderWfAgentGrid();
  document.getElementById('worker-form-card').style.display = 'block';
  document.getElementById('worker-form-card').scrollIntoView({behavior:'smooth', block:'start'});
}

function editBundle(b) {
  openCreateWorker(b);
  document.getElementById('wf-editing-id').value = b.id;
  document.getElementById('worker-form-title').textContent = 'Edit Agent Team';
  document.getElementById('wf-save-btn').textContent = '💾 Update Agent Team';
}

function editBundleById(id) {
  const bundle = _workerBundlesById[id];
  if (!bundle) {
    toast('Bundle not found', 'error');
    return;
  }
  editBundle(bundle);
}

function closeWorkerForm() {
  document.getElementById('worker-form-card').style.display = 'none';
  _wfSelectedAgents.clear();
}

function renderWfAgentGrid() {
  const grid = document.getElementById('wf-agent-grid');
  if (!_allAgents.length) {
    grid.innerHTML = '<p style="color:var(--text-muted);font-size:.82em">Agents not loaded yet. Open Tasks tab first to load agent list.</p>';
    return;
  }
  grid.innerHTML = _allAgents.map(a => {
    const sel = _wfSelectedAgents.has(a.id);
    const color = _catColors[a.category] || '#64748b';
    return `<div id="wfcard-${a.id}" onclick="toggleWfAgent('${escHtml(a.id)}')"
      style="cursor:pointer;border:2px solid ${sel ? color : 'var(--border)'};border-radius:var(--radius-sm);padding:6px;background:${sel ? 'var(--surface2)' : 'var(--surface)'};transition:all .15s">
      <div style="font-size:.75em;font-weight:600;color:${sel ? color : 'var(--text)'}">${escHtml(a.id)}</div>
      <div style="font-size:.65em;color:var(--text-muted)">${escHtml(a.category||'')}</div>
    </div>`;
  }).join('');
  document.getElementById('wf-agent-count').textContent = `(${_wfSelectedAgents.size} selected)`;
}

function toggleWfAgent(id) {
  if (_wfSelectedAgents.has(id)) _wfSelectedAgents.delete(id);
  else _wfSelectedAgents.add(id);
  const a = _allAgents.find(x => x.id === id);
  const card = document.getElementById('wfcard-' + id);
  if (!card || !a) return;
  const sel = _wfSelectedAgents.has(id);
  const color = _catColors[a.category] || '#64748b';
  card.style.border = `2px solid ${sel ? color : 'var(--border)'}`;
  card.style.background = sel ? 'var(--surface2)' : 'var(--surface)';
  card.querySelector('div').style.color = sel ? color : 'var(--text)';
  document.getElementById('wf-agent-count').textContent = `(${_wfSelectedAgents.size} selected)`;
}

function wfSelectAll() { _allAgents.forEach(a => _wfSelectedAgents.add(a.id)); renderWfAgentGrid(); }
function wfClearAll()  { _wfSelectedAgents.clear(); renderWfAgentGrid(); }

function presetEcomWorker() {
  const preset = {
    name: 'E-commerce Automation Worker',
    description: 'Full 100% automated e-commerce operation — orders, support, inventory, marketing, and reporting.',
    task_description: 'Run the full e-commerce automation pipeline: process new orders via Shopify webhook, handle customer support tickets, sync inventory with supplier, run email marketing campaigns, post to social media, research new products, and generate daily P&L reports.',
    schedule: 'continuous',
    agents: ['order-processor','support-bot','bookkeeper','inventory-sync','email-marketer','social-poster','product-researcher','ecom-dashboard']
  };
  openCreateWorker(preset);
  toast('E-commerce preset loaded! Adjust agents and save.', 'success');
}

async function saveWorkerBundle() {
  const name = document.getElementById('wf-name').value.trim();
  const task_description = document.getElementById('wf-task').value.trim();
  const description = document.getElementById('wf-desc').value.trim();
  const schedule = document.getElementById('wf-schedule').value;
  const agents = [..._wfSelectedAgents];
  const editingId = document.getElementById('wf-editing-id').value.trim();
  const resultEl = document.getElementById('wf-save-result');

  if (!name) { toast('Agent team name is required', 'error'); return; }
  if (!task_description) { toast('Task description is required', 'error'); return; }
  if (!agents.length) { toast('Select at least one agent', 'error'); return; }

  resultEl.textContent = '⏳ Saving…';
  const payload = {name, description, task_description, schedule, agents, enabled: true};

  let r;
  if (editingId) {
    r = await api(`/api/workers/bundles/${editingId}`, {method:'PATCH', body: JSON.stringify(payload)});
  } else {
    r = await api('/api/workers/bundles', {method:'POST', body: JSON.stringify(payload)});
  }

  if (r && r.ok !== false) {
    resultEl.innerHTML = `<span style="color:var(--success)">✅ Agent team ${editingId ? 'updated' : 'created'}!</span>`;
    setTimeout(() => { closeWorkerForm(); loadWorkers(); }, 800);
  } else {
    resultEl.innerHTML = `<span style="color:var(--danger)">❌ Save failed. Check API.</span>`;
  }
}

async function runBundle(id) {
  const r = await api(`/api/workers/bundles/${id}/run`, {method:'POST'});
  if (r && r.ok !== false) toast('Agent team triggered ▶', 'success');
  else toast('Run failed', 'error');
  setTimeout(loadWorkers, 1500);
}

async function toggleBundle(id, enabled) {
  const r = await api(`/api/workers/bundles/${id}`, {method:'PATCH', body: JSON.stringify({enabled})});
  if (r && r.ok !== false) toast(enabled ? 'Agent team enabled ✅' : 'Agent team disabled ⏸', enabled ? 'success' : 'info');
  else toast('Update failed', 'error');
  loadWorkers();
}

async function deleteBundle(id) {
  if (!confirm('Delete this agent team?')) return;
  const r = await api(`/api/workers/bundles/${id}`, {method:'DELETE'});
  if (r && r.ok !== false) { toast('Agent team deleted', 'error'); loadWorkers(); }
  else toast('Delete failed', 'error');
}

async function startBot(name) {
  const r = await api('/api/agents/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot: name})});
  if (r.ok && r.already_running) toast(`${name} is already running`, 'info');
  else if (r.ok) toast(`Starting ${name}…`, 'success');
  else toast(`Failed to start ${name}: ${r.error || 'unknown error'}`, 'error');
  setTimeout(loadWorkers, 1200);
}

async function stopBot(name) {
  if (!confirm(`Stop ${name}?`)) return;
  const r = await api('/api/agents/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot: name})});
  const dur = (r.shutdown && Number.isFinite(r.shutdown.duration_ms)) ? `${r.shutdown.duration_ms}ms` : '';
  if (r.ok) toast(`Stopped ${name}${dur ? ` in ${dur}` : ''}`, 'success');
  else toast(`Failed to fully stop ${name}${dur ? ` (${dur})` : ''}`, 'error');
  setTimeout(loadWorkers, 1200);
}

// ── Improvements ────────────────────────────────────────────────────────────
let _allImprovements = [];
let _improvStatusFilter = 'all';
let _improvPriorityFilter = 'all';

async function loadImprovements() {
  const data = await api('/api/improvements');
  _allImprovements = data.improvements || [];
  renderImprovements();
}

function filterImprovements(status, btn) {
  _improvStatusFilter = status;
  document.querySelectorAll('.improv-pill').forEach(p => {
    p.classList.remove('active');
    p.style.background = '';
    p.style.color = '';
    p.style.border = '';
  });
  if (btn) {
    btn.classList.add('active');
    btn.style.background = 'linear-gradient(135deg,var(--primary-dark),var(--primary))';
    btn.style.color = '#000';
    btn.style.border = 'none';
  }
  renderImprovements();
}

function filterImprovPriority(priority, btn) {
  _improvPriorityFilter = priority;
  document.querySelectorAll('.improv-pri-pill').forEach(p => {
    p.classList.remove('active');
    p.style.background = '';
  });
  if (btn) {
    btn.classList.add('active');
    btn.style.background = 'rgba(212,175,55,.15)';
  }
  renderImprovements();
}

function renderImprovements() {
  const el = document.getElementById('improvement-list');
  let items = _allImprovements;
  if (_improvStatusFilter !== 'all') items = items.filter(i => (i.status || 'pending') === _improvStatusFilter);
  if (_improvPriorityFilter !== 'all') items = items.filter(i => (i.priority || 'medium') === _improvPriorityFilter);

  if (!items.length) {
    el.innerHTML = '<div class="empty"><div class="icon">💡</div><p>No proposals match the current filter. The discovery agent will add proposals over time.</p></div>';
    return;
  }

  const priorityColors = {critical:'#ef4444', high:'#f59e0b', medium:'#eab308', low:'#10b981'};
  const priorityIcons = {critical:'🔴', high:'🟠', medium:'🟡', low:'🟢'};
  const statusColors = {pending:'rgba(245,158,11,.2)', in_progress:'rgba(212,175,55,.18)', approved:'rgba(16,185,129,.2)', completed:'rgba(34,197,94,.2)', rejected:'rgba(239,68,68,.12)'};

  el.innerHTML = items.map(imp => {
    const priority = imp.priority || 'medium';
    const priColor = priorityColors[priority] || '#eab308';
    const priIcon = priorityIcons[priority] || '🟡';
    const statusCol = statusColors[imp.status || 'pending'] || 'var(--surface)';
    return `
    <div class="improv-row" style="cursor:pointer;border-left:3px solid ${priColor}" onclick="toggleImprovDetail('${jsEsc(imp.id)}')">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
        <h4 style="display:flex;align-items:center;gap:8px;flex:1;flex-wrap:wrap">
          <span id="improv-arrow-${escHtml(imp.id)}" style="font-size:.8em;color:var(--text-muted)">▶</span>
          <span style="font-size:.78em;background:rgba(212,175,55,.08);padding:1px 7px;border-radius:4px;border:1px solid rgba(${priColor.replace('#','').match(/../g).map(h=>parseInt(h,16)).join(',')}, .3);color:${priColor};font-weight:600">${priIcon} ${priority}</span>
          ${escHtml(imp.title||imp.id)}
          <span class="badge ${imp.status||'pending'}" style="background:${statusCol}">${imp.status||'pending'}</span>
        </h4>
        ${(imp.status==='pending'||!imp.status) ? `<div style="display:flex;gap:6px;flex-shrink:0" onclick="event.stopPropagation()">
          <button class="btn btn-success btn-sm" onclick="reviewImprovement('${jsEsc(imp.id)}','approved')">✓ Approve</button>
          <button class="btn btn-danger btn-sm" onclick="reviewImprovement('${jsEsc(imp.id)}','rejected')">✕ Reject</button>
        </div>` : ''}
      </div>
      <p style="color:var(--text-muted);font-size:.84em;margin:4px 0">${escHtml((imp.description||'').slice(0,120))}${(imp.description||'').length>120?'…':''}</p>
      <!-- Execute button always visible -->
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px" onclick="event.stopPropagation()">
        <button class="btn btn-primary btn-sm" onclick="sendImprovToAI('${jsEsc(imp.id)}','${jsEsc(imp.title||imp.id)}','${jsEsc(imp.description||'')}')" style="background:linear-gradient(135deg,#B8960C,#D4AF37);color:#000;border:none;font-weight:700;letter-spacing:.02em">🚀 Execute This Improvement</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleImprovDetail('${jsEsc(imp.id)}')" style="font-size:.78em">🔍 Details</button>
      </div>
      <div id="improv-detail-${escHtml(imp.id)}" style="display:none;margin-top:10px;padding:12px;background:var(--surface);border-radius:var(--radius-sm);border:1px solid var(--border)">
        <p style="font-size:.84em;color:var(--text-secondary);line-height:1.6;margin-bottom:10px">${escHtml(imp.description||'No description provided.')}</p>
        ${imp.agent ? `<p style="font-size:.78em;color:var(--primary);margin-bottom:8px">Agent: <strong>${escHtml(imp.agent)}</strong> · Type: ${escHtml(imp.type||'?')} · Effort: ${escHtml(imp.effort||'?')}</p>` : ''}
        ${imp.rationale ? `<p style="font-size:.8em;color:var(--text-muted);margin-bottom:10px"><strong>Rationale:</strong> ${escHtml(imp.rationale)}</p>` : ''}
        <div style="display:flex;gap:6px;flex-wrap:wrap" onclick="event.stopPropagation()">
          <button class="btn btn-primary btn-sm" onclick="sendImprovToAI('${jsEsc(imp.id)}','${jsEsc(imp.title||imp.id)}','${jsEsc(imp.description||'')}')" style="background:linear-gradient(135deg,var(--primary-dark),var(--primary));color:#000;border:none;font-weight:700">🚀 Execute This Improvement</button>
          ${(imp.status==='pending'||!imp.status) ? `<button class="btn btn-success btn-sm" onclick="reviewImprovement('${jsEsc(imp.id)}','approved')">✓ Approve</button>
          <button class="btn btn-danger btn-sm" onclick="reviewImprovement('${jsEsc(imp.id)}','rejected')">✕ Reject</button>` : ''}
          ${imp.status==='approved' ? `<button class="btn btn-primary btn-sm" onclick="reviewImprovement('${jsEsc(imp.id)}','in_progress')">🔄 Mark In Progress</button>` : ''}
          ${imp.status==='in_progress' ? `<button class="btn btn-success btn-sm" onclick="reviewImprovement('${jsEsc(imp.id)}','completed')">🏆 Mark Completed</button>` : ''}
        </div>
      </div>
    </div>`;
  }).join('');
}

function toggleImprovDetail(id) {
  const detail = document.getElementById('improv-detail-' + id);
  const arrow = document.getElementById('improv-arrow-' + id);
  if (!detail) return;
  const open = detail.style.display !== 'none';
  detail.style.display = open ? 'none' : 'block';
  if (arrow) arrow.textContent = open ? '▶' : '▼';
}

async function sendImprovToAI(id, title, description) {
  const msg = `Execute this improvement proposal:\n\nTitle: ${title}\n\nDescription: ${description}\n\nPlease implement this improvement and report back with the result.`;
  // Mark as in_progress
  await api(`/api/improvements/${id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status: 'in_progress'})});
  // Switch to chat tab and send
  switchToChatTab();
  setTimeout(() => {
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = msg;
      toast(`📤 Sending "${title}" to Main AI…`, 'info');
      sendChat();
    }
  }, 200);
}

async function reviewImprovement(id, decision) {
  const r = await api(`/api/improvements/${id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status: decision})});
  if (r.ok) {
    const labels = {approved:'✓ Approved', rejected:'✕ Rejected', in_progress:'🔄 In Progress', completed:'🏆 Completed'};
    const types = {approved:'success', rejected:'error', in_progress:'info', completed:'success'};
    toast(labels[decision] || decision, types[decision] || 'info');
    loadImprovements();
  }
}

// ── Skills ───────────────────────────────────────────────────────────────────
let allSkills = [];
let selectedSkillIds = new Set();
let activeCategory = '';

const CAT_COLORS = {
  'Content & Writing':'#f472b6','Research & Analysis':'#60a5fa',
  'Trading & Finance':'#34d399','Social Media':'#fb923c',
  'Lead Generation & Sales':'#a78bfa','Customer Support':'#fbbf24',
  'Development & Technical':'#22d3ee','Data Analysis':'#4ade80',
  'E-commerce & Product':'#f87171','Marketing & SEO':'#c084fc',
  'Automation & Productivity':'#e2e8f0',
};

async function loadSkills() {
  const data = await api('/api/skills');
  allSkills = data.skills || [];
  document.getElementById('skill-total-badge').textContent = `(${allSkills.length})`;
  renderCategoryPills(data.categories || []);
  renderSkillGrid(allSkills);
  loadAgents();
}

function renderCategoryPills(cats) {
  const el = document.getElementById('category-pills');
  el.innerHTML = `<span class="cat-pill active" onclick="setCat('',this)">All</span>` +
    cats.map(c => `<span class="cat-pill" onclick="setCat('${escHtml(c)}',this)">${c}</span>`).join('');
}

function setCat(cat, btn) {
  activeCategory = cat;
  document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  filterSkills();
}

function filterSkills() {
  const q = (document.getElementById('skill-search').value || '').toLowerCase();
  const filtered = allSkills.filter(s => {
    const catMatch = !activeCategory || s.category === activeCategory;
    const textMatch = !q || s.id.includes(q) || s.name.toLowerCase().includes(q) ||
                      s.description.toLowerCase().includes(q) ||
                      (s.tags||[]).some(t => t.toLowerCase().includes(q));
    return catMatch && textMatch;
  });
  renderSkillGrid(filtered);
}

function renderSkillGrid(skills) {
  const el = document.getElementById('skill-grid');
  if (!skills.length) { el.innerHTML = '<div class="empty"><div class="icon">🔍</div><p>No skills match.</p></div>'; return; }
  el.innerHTML = skills.map(s => {
    const color = CAT_COLORS[s.category] || '#94a3b8';
    const sel = selectedSkillIds.has(s.id);
    const tags = (s.tags||[]).slice(0,4).map(t=>`<span class="tag">${t}</span>`).join('');
    const usageCount = s.usage_count != null ? s.usage_count : 0;
    const createdBy = s.created_by ? `<span style="font-size:.68em;color:var(--text-muted)">by ${escHtml(s.created_by)}</span>` : '';
    return `<div class="skill-card${sel?' selected':''}" onclick="toggleSkill(${JSON.stringify(s.id)},this)">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:6px">
        <h5 style="flex:1">${escHtml(s.name)} <span style="color:${color};font-size:.72em;font-weight:500">${escHtml(s.category)}</span></h5>
        <button onclick="event.stopPropagation();showSkillDetail(${JSON.stringify(s.id)})" title="View details"
          style="background:none;border:1px solid var(--border);border-radius:4px;color:var(--text-muted);font-size:.68em;padding:1px 5px;cursor:pointer;flex-shrink:0">ℹ</button>
      </div>
      <p>${escHtml(s.description.slice(0,110))}${s.description.length>110?'…':''}</p>
      <div class="tags">${tags}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;font-size:.72em;color:var(--text-muted)">
        <span>⚡ Used ${usageCount}×</span>${createdBy}
      </div>
    </div>`;
  }).join('');
}

function showSkillDetail(id) {
  const s = allSkills.find(x => x.id === id);
  if (!s) return;
  const color = CAT_COLORS[s.category] || '#94a3b8';
  const tags = (s.tags||[]).map(t=>`<span class="tag">${escHtml(t)}</span>`).join('');
  const steps = (s.steps||[]).map((step,i)=>`<li style="margin-bottom:6px">${escHtml(step)}</li>`).join('');
  const usageCount = s.usage_count != null ? s.usage_count : 0;
  const createdBy = s.created_by || 'System';
  let html = `<div style="position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:2000;display:flex;align-items:center;justify-content:center" id="skill-detail-overlay" onclick="if(event.target.id==='skill-detail-overlay')closeSkillDetail()">
    <div style="background:var(--surface);border:1px solid var(--gold);border-radius:var(--radius);padding:28px;max-width:560px;width:90%;max-height:80vh;overflow-y:auto">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px">
        <div>
          <div style="font-size:1.1em;font-weight:700;color:var(--text)">${escHtml(s.name)}</div>
          <div style="display:flex;gap:8px;align-items:center;margin-top:4px;flex-wrap:wrap">
            <span style="font-size:.78em;background:${color}22;color:${color};padding:2px 8px;border-radius:4px;border:1px solid ${color}44">${escHtml(s.category)}</span>
            <span style="font-size:.72em;color:var(--text-muted)">⚡ Used ${usageCount}×</span>
            <span style="font-size:.72em;color:var(--text-muted)">👤 by ${escHtml(createdBy)}</span>
          </div>
        </div>
        <button onclick="closeSkillDetail()" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--text-muted);padding:4px 10px;cursor:pointer">✕</button>
      </div>
      <p style="font-size:.88em;color:var(--text-secondary);line-height:1.6;margin-bottom:14px">${escHtml(s.description)}</p>
      ${tags ? `<div style="margin-bottom:14px"><div style="font-size:.72em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">Tags</div><div class="tags">${tags}</div></div>` : ''}
      ${steps ? `<div style="margin-bottom:14px"><div style="font-size:.72em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">How it works</div><ol style="font-size:.83em;color:var(--text-secondary);margin:0 0 0 16px;line-height:1.7">${steps}</ol></div>` : ''}
      ${s.prompt_template ? `<div style="margin-bottom:14px"><div style="font-size:.72em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">Prompt Template</div><pre style="font-size:.75em;background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px;white-space:pre-wrap;word-break:break-word;color:var(--text-secondary)">${escHtml(s.prompt_template.slice(0,400))}${s.prompt_template.length>400?'\n…':''}</pre></div>` : ''}
      <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-success btn-sm" onclick="useSkillNow(${JSON.stringify(s.id)},${JSON.stringify(s.name)});closeSkillDetail()" style="background:linear-gradient(135deg,var(--primary-dark),var(--primary));color:#000;border:none;font-weight:700">⚡ Use This Skill</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleSkillFromModal(${JSON.stringify(s.id)});closeSkillDetail()" id="skill-detail-add-btn">${selectedSkillIds.has(s.id)?'✓ Deselect':'＋ Add to Agent'}</button>
        <button class="btn btn-ghost btn-sm" onclick="closeSkillDetail()">Close</button>
      </div>
    </div>
  </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function closeSkillDetail() {
  const el = document.getElementById('skill-detail-overlay');
  if (el) el.remove();
}

function toggleSkillFromModal(id) {
  if (selectedSkillIds.has(id)) selectedSkillIds.delete(id);
  else selectedSkillIds.add(id);
  updateSelectedPanel();
  filterSkills();
}

function toggleSkill(id, card) {
  if (selectedSkillIds.has(id)) { selectedSkillIds.delete(id); card.classList.remove('selected'); }
  else { selectedSkillIds.add(id); card.classList.add('selected'); }
  updateSelectedPanel();
}

function updateSelectedPanel() {
  const count = selectedSkillIds.size;
  document.getElementById('selected-count').textContent = `(${count})`;
  const el = document.getElementById('selected-skills-list');
  if (!count) { el.textContent = 'No skills selected. Click cards on the left.'; return; }
  el.innerHTML = [...selectedSkillIds].map(id => {
    const s = allSkills.find(x => x.id === id);
    return `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 4px 2px 0;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.8em">
      ${s ? s.name : id}
      <span onclick="selectedSkillIds.delete(${JSON.stringify(id)});updateSelectedPanel();filterSkills();"
        style="cursor:pointer;color:var(--danger);font-weight:bold;margin-left:2px">×</span>
    </span>`;
  }).join('');
}

async function createAgent() {
  const name = document.getElementById('agent-name-input').value.trim();
  const desc = document.getElementById('agent-desc-input').value.trim();
  if (!name) { toast('Agent name is required', 'error'); return; }
  if (!selectedSkillIds.size) { toast('Select at least one skill', 'error'); return; }
  const r = await api('/api/agents/custom', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, description: desc, skills: [...selectedSkillIds]}),
  });
  if (r.ok) {
    toast(`Agent "${name}" created with ${r.skill_count} skills!`);
    document.getElementById('agent-name-input').value = '';
    document.getElementById('agent-desc-input').value = '';
    selectedSkillIds.clear();
    updateSelectedPanel();
    filterSkills();
    loadAgents();
  } else { toast(r.error || 'Error creating agent', 'error'); }
}

async function loadAgents() {
  const data = await api('/api/agents/custom');
  const agents = data.agents || [];
  const el = document.getElementById('agents-list');
  if (!agents.length) { el.innerHTML = '<div class="empty"><div class="icon">👥</div><p>No agents yet. Create one above.</p></div>'; return; }
  el.innerHTML = agents.map(a => `
    <div class="agent-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <h4>${a.name}</h4>
        <button class="btn btn-danger btn-sm" onclick="deleteAgent('${a.id}')">🗑</button>
      </div>
      <p>${a.description || 'No description'}</p>
      <p style="margin-top:6px;color:var(--primary);font-size:.78em">${a.skill_count} skills: ${(a.skills||[]).slice(0,5).join(', ')}${a.skill_count>5?'…':''}</p>
    </div>`).join('');
}

async function deleteAgent(id) {
  if (!confirm('Delete this agent?')) return;
  const r = await api('/api/agents/custom/' + id, {method:'DELETE'});
  if (r.ok) { toast('Agent deleted', 'error'); loadAgents(); }
}

// ── New Skill Form ────────────────────────────────────────────────────────────
function toggleNewSkillForm() {
  const card = document.getElementById('new-skill-form-card');
  const btn = document.getElementById('new-skill-btn');
  if (!card) return;
  const isOpen = card.style.display !== 'none';
  card.style.display = isOpen ? 'none' : 'block';
  if (btn) btn.textContent = isOpen ? '＋ New Skill' : '✕ Cancel';
}

async function saveNewSkill() {
  const name = (document.getElementById('new-skill-name')?.value || '').trim();
  const category = document.getElementById('new-skill-category')?.value || 'Automation & Productivity';
  const description = (document.getElementById('new-skill-desc')?.value || '').trim();
  const tagsRaw = (document.getElementById('new-skill-tags')?.value || '').trim();
  const stepsRaw = (document.getElementById('new-skill-steps')?.value || '').trim();
  const resultEl = document.getElementById('new-skill-result');

  if (!name || !description) {
    if (resultEl) resultEl.innerHTML = '<span style="color:var(--danger)">Name and description are required.</span>';
    return;
  }
  const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
  const steps = stepsRaw ? stepsRaw.split('\n').map(s => s.trim()).filter(Boolean) : [];
  const id = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

  const r = await api('/api/skills', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id, name, category, description, tags, steps, created_by: 'user'})
  });
  if (r.ok) {
    toast(`Skill "${name}" added to library! ✅`, 'success');
    if (resultEl) resultEl.innerHTML = '<span style="color:var(--success)">✅ Skill saved!</span>';
    document.getElementById('new-skill-name').value = '';
    document.getElementById('new-skill-desc').value = '';
    document.getElementById('new-skill-tags').value = '';
    document.getElementById('new-skill-steps').value = '';
    toggleNewSkillForm();
    loadSkills();
  } else {
    const msg = r.detail || r.error || 'Error saving skill';
    if (resultEl) resultEl.innerHTML = `<span style="color:var(--danger)">❌ ${escHtml(msg)}</span>`;
  }
}

function useSkillNow(id, name) {
  // Switch to chat tab and pre-fill the prompt with the skill
  switchToChatTab();
  setTimeout(() => {
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = `Use the "${name}" skill to help me: `;
      input.focus();
      toast(`⚡ "${name}" skill ready to use in chat!`, 'info');
    }
  }, 200);
}


let _allAgents = [];          // full list from /api/agents
let _autoSelectedIds = new Set(); // IDs suggested by auto-select
let _selectedAgentIds = new Set(); // currently selected (user may adjust)
let _taskMode = 'auto';       // 'auto' | 'parallel' | 'single'

// ── Idea auto-detect: heuristic to identify raw ideas vs. commands ─────────────
function _looksLikeIdea(text) {
  const t = text.trim().toLowerCase();
  // Short phrases that sound like intentions or wishes
  const ideaStarters = [
    /^i (want|need|wish|would like|plan|hope|am trying|am looking) to\b/,
    /^i (have an? idea|have a concept|have a vision|have a plan|had an idea)\b/,
    /^help me (build|create|make|start|launch|develop|grow|design)\b/,
    /^(build|create|make|start|launch|develop|design|grow) (a|an|my)\b/,
    /^(how (do i|can i|should i)|what('s| is) the best way to)\b/,
    /^i want\b/,
    /^(let'?s|we should) (build|create|make|start|launch)\b/,
  ];
  if (ideaStarters.some(r => r.test(t))) return true;
  // No period, colon, numbered list, or URL — looks vague/conversational
  const wordCount = t.split(/\s+/).length;
  if (wordCount <= 20 && !/[.:\n]/.test(t) && !/https?:\/\//.test(t) && !/^\d+\./.test(t)) {
    // Extra signal: at least one of these intent words
    if (/\b(build|create|sell|launch|start|grow|develop|design|market|automate|improve)\b/.test(t)) return true;
  }
  return false;
}

// ── Idea Mode (legacy stubs — no-op) ─────────────────────────────────────────
function toggleIdeaMode() {}
function convertIdea() {}
function convertChatIdea() {}

function onTaskInputChange() {
  const v = document.getElementById('task-input').value.trim();
  document.getElementById('btn-autoselect').disabled = !v;
  document.getElementById('autoselect-status').textContent = '';
}

function setMode(m) {
  _taskMode = m;
  ['auto','parallel','single'].forEach(id => {
    const el = document.getElementById('mode-' + id);
    el.style.border = id === m ? '2px solid var(--primary)' : '1px solid var(--border)';
  });
}

async function runAutoSelect() {
  const desc = document.getElementById('task-input').value.trim();
  if (!desc) return;
  const statusEl = document.getElementById('autoselect-status');
  statusEl.textContent = '⏳ Analysing task…';
  document.getElementById('btn-autoselect').disabled = true;

  // Fetch all agents if we don't have them yet
  if (!_allAgents.length) {
    const r = await api('/api/agents');
    if (r.ok) { _allAgents = r.agents || []; }
  }

  const r = await api('/api/task/auto-agents', {method:'POST', body: JSON.stringify({description: desc})});
  if (r.ok) {
    _autoSelectedIds = new Set(r.suggested || []);
    _selectedAgentIds = new Set(_autoSelectedIds);
    statusEl.innerHTML = `<span style="color:var(--success)">✅ ${_autoSelectedIds.size} agent${_autoSelectedIds.size!==1?'s':''} auto-selected</span>`;
    renderAgentPicker();
    document.getElementById('task-step2').style.display = 'block';
    document.getElementById('task-step3').style.display = 'block';
    document.getElementById('task-step-badge').textContent = 'Step 2';
  } else {
    statusEl.innerHTML = '<span style="color:var(--danger)">❌ Auto-select failed — use Manual to pick agents</span>';
    showManualAgentPicker();
  }
  document.getElementById('btn-autoselect').disabled = false;
}

async function showManualAgentPicker() {
  if (!_allAgents.length) {
    const r = await api('/api/agents');
    if (r.ok) { _allAgents = r.agents || []; }
  }
  renderAgentPicker();
  document.getElementById('task-step2').style.display = 'block';
  document.getElementById('task-step3').style.display = 'block';
  document.getElementById('task-step-badge').textContent = 'Step 2';
}

const _catColors = {
  coordination:'#6366f1', sales:'#10b981', content:'#22d3ee', social:'#f59e0b',
  research:'#3b82f6', ecommerce:'#ec4899', analytics:'#8b5cf6', creative:'#ef4444',
  trading:'#f97316', development:'#14b8a6', hr:'#84cc16', finance:'#eab308',
  marketing:'#06b6d4', growth:'#a855f7', management:'#64748b', crypto:'#f59e0b',
  strategy:'#6366f1', support:'#10b981'
};
const _catEmoji = {
  coordination:'🎯', sales:'💼', content:'✍️', social:'📱', research:'🔍',
  ecommerce:'🛒', analytics:'📊', creative:'🎨', trading:'📈', development:'💻',
  hr:'👔', finance:'💰', marketing:'🚀', growth:'📈', management:'📋',
  crypto:'🪙', strategy:'🏢', support:'🎧'
};

function renderAgentPicker() {
  const grid = document.getElementById('agent-picker-grid');
  if (!_allAgents.length) {
    grid.innerHTML = '<p style="color:var(--text-muted);font-size:.84em">No agents loaded. Check /api/agents.</p>';
    return;
  }
  grid.innerHTML = _allAgents.map(a => {
    const selected = _selectedAgentIds.has(a.id);
    const wasAuto = _autoSelectedIds.has(a.id);
    const color = _catColors[a.category] || '#64748b';
    const emoji = _catEmoji[a.category] || '🤖';
    const isRunning = a.running;
    return `<div id="agentcard-${a.id}"
      onclick="toggleAgent('${escHtml(a.id)}')"
      title="${escHtml(a.description||'')}"
      class="agent-pick-item${selected ? ' selected' : ''}"
      style="position:relative;user-select:none;flex-direction:column;align-items:flex-start;gap:4px">
      ${wasAuto ? `<span style="position:absolute;top:4px;right:4px;font-size:.58em;background:rgba(212,175,55,.2);color:var(--gold);border-radius:3px;padding:1px 5px;border:1px solid rgba(212,175,55,.3)">AUTO</span>` : ''}
      <div style="display:flex;align-items:center;gap:6px;width:100%">
        <span style="font-size:1em">${emoji}</span>
        <span class="pick-dot ${isRunning ? 'on' : 'off'}"></span>
        <span style="font-size:.76em;font-weight:600;color:${selected ? 'var(--gold-light)' : 'var(--text)'};line-height:1.2;flex:1">${escHtml(a.id)}</span>
      </div>
      <div style="font-size:.65em;color:${color};margin-left:22px;font-weight:500">${escHtml(a.category||'')}</div>
    </div>`;
  }).join('');
  updateAgentSelCount();
}

function toggleAgent(id) {
  if (_selectedAgentIds.has(id)) _selectedAgentIds.delete(id);
  else _selectedAgentIds.add(id);
  const a = _allAgents.find(x => x.id === id);
  const card = document.getElementById('agentcard-' + id);
  if (!card || !a) return;
  const selected = _selectedAgentIds.has(id);
  const color = _catColors[a.category] || '#64748b';
  card.style.border = `2px solid ${selected ? color : 'var(--border)'}`;
  card.style.background = selected ? 'var(--surface2)' : 'var(--surface)';
  card.querySelector('div:last-child').previousElementSibling.style.color = selected ? color : 'var(--text)';
  updateAgentSelCount();
}

function selectAllAgents() {
  _allAgents.forEach(a => _selectedAgentIds.add(a.id));
  renderAgentPicker();
}
function clearAllAgents() {
  _selectedAgentIds.clear();
  renderAgentPicker();
}
function resetToAutoSelected() {
  _selectedAgentIds = new Set(_autoSelectedIds);
  renderAgentPicker();
}

function updateAgentSelCount() {
  const n = _selectedAgentIds.size;
  document.getElementById('agent-sel-count').textContent = `(${n} selected)`;
}

async function submitTask() {
  const desc = document.getElementById('task-input').value.trim();
  if (!desc) { toast('Please enter a task description', 'error'); return; }
  const resultEl = document.getElementById('task-submit-result');
  resultEl.innerHTML = '⏳ Submitting…';
  const agents = [..._selectedAgentIds];
  const r = await api('/api/task/submit', {method:'POST', body: JSON.stringify({
    description: desc,
    agents: agents,
    mode: _taskMode
  })});
  if (r.ok) {
    resultEl.innerHTML = `<span style="color:var(--success)">✅ Task launched! ID: <code>${escHtml(String(r.task_id||'?'))}</code> | ${agents.length || 'auto'} agent${agents.length!==1?'s':''} | mode: ${escHtml(_taskMode)}</span>`;
    document.getElementById('task-input').value = '';
    _selectedAgentIds.clear();
    _autoSelectedIds.clear();
    document.getElementById('task-step2').style.display = 'none';
    document.getElementById('task-step3').style.display = 'none';
    document.getElementById('task-step-badge').textContent = 'Step 1';
    document.getElementById('autoselect-status').textContent = '';
    setTimeout(loadTasks, 2000);
  } else {
    resultEl.innerHTML = '<span style="color:var(--danger)">❌ Failed to submit. Is task-orchestrator running?</span>';
  }
}

// Task store: indexed by task ID to avoid XSS from inline JSON in onclick attributes
const _taskStore = new Map();

function renderTaskRow(t) {
  const tid = t.id || t.plan_id || ('task_' + _taskStore.size);
  _taskStore.set(tid, t);
  const desc = escHtml((t.description||t.id||'Task').slice(0,60));
  const ts = new Date(t.created_at||t.ts||Date.now()).toLocaleDateString();
  const status = escHtml(t.status||'completed');
  const agent = escHtml(t.agent||'');
  return '<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-radius:8px;background:rgba(255,255,255,.02);border:1px solid rgba(212,175,55,.08);margin-bottom:6px">' +
    '<div><div style="font-weight:600;font-size:.87em;color:var(--text)">' + desc + '</div>' +
    '<div style="font-size:.74em;color:var(--text-muted);margin-top:2px">' + status + ' · ' + agent + ' · ' + ts + '</div></div>' +
    '<button class="btn btn-ghost btn-sm" aria-label="View task details" onclick="openTaskDetail(' + JSON.stringify(tid) + ')" style="border:1px solid rgba(212,175,55,.3);color:var(--gold)">View →</button></div>';
}
let _taskDetailTrigger = null;

async function loadTasks() {
  const r = await api('/api/task/list');
  if (!r.ok) return;
  const plans = r.plans || [];

  const activePanel = document.getElementById('active-task-panel');
  const active = plans.find(p => p.status === 'running' || p.status === 'planning');
  if (active) {
    const subtasks = active.subtasks || [];
    const done = subtasks.filter(s => s.status === 'done').length;
    const pct = subtasks.length ? Math.round(done/subtasks.length*100) : 0;
    const statusEmoji = {running:'⏳',planning:'🧠',done:'✅',failed:'❌'}[active.status]||'?';
    const modeTag = active.mode ? `<span style="font-size:.72em;background:var(--surface2);padding:1px 6px;border-radius:3px;margin-left:6px">${active.mode}</span>` : '';
    activePanel.innerHTML = `
      <div style="margin-bottom:12px">
        <div style="font-weight:600;margin-bottom:4px">${statusEmoji} ${escHtml(active.title||active.id)}${modeTag}</div>
        <div style="font-size:.82em;color:var(--text-muted)">ID: ${active.id} | ${done}/${subtasks.length} subtasks</div>
        <div style="background:var(--border);border-radius:4px;height:6px;margin:8px 0">
          <div style="background:var(--primary);height:100%;width:${pct}%;border-radius:4px;transition:width .3s"></div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${subtasks.map(st => {
          const e = {done:'✅',running:'⏳',pending:'⏸️',failed:'❌',skipped:'⏭️'}[st.status]||'?';
          const agColor = _catColors[(_allAgents.find(a=>a.id===st.agent_id)||{}).category] || '#64748b';
          return `<div style="display:flex;align-items:center;gap:8px;font-size:.84em;padding:4px 6px;border-radius:4px;background:var(--surface)">
            <span>${e}</span>
            <span style="color:${agColor};font-weight:600;min-width:110px;font-size:.9em">${escHtml(st.agent_id||'?')}</span>
            <span style="color:var(--text-secondary);flex:1">${escHtml(st.title||st.subtask_id||'')}</span>
            ${st.status==='pending' ? `<button class="btn btn-ghost btn-sm" style="padding:1px 6px;font-size:.7em" onclick="reassignSubtask('${escHtml(active.id)}','${escHtml(st.subtask_id||'')}')">↩ Reassign</button>` : ''}
          </div>`;
        }).join('')}
      </div>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn btn-ghost btn-sm" style="color:var(--danger)" onclick="cancelTask()">🛑 Cancel</button>
        <button class="btn btn-ghost btn-sm" onclick="loadTasks()">↻ Refresh</button>
      </div>
    `;
    setTimeout(loadTasks, 5000);
  } else {
    activePanel.innerHTML = '<div class="empty"><div class="icon">🚀</div><p>No active task. Build one on the left.</p></div>';
  }

  const histEl = document.getElementById('task-history-list');
  const history = plans.filter(p => !['running','planning'].includes(p.status)).slice(0,10);
  if (!history.length) { histEl.innerHTML = '<div class="empty"><p>No task history yet.</p></div>'; return; }
  histEl.innerHTML = history.map(p => {
    const tid = p.id || (`hist_${Math.random().toString(36).slice(2)}`);
    _taskStore.set(tid, p);
    const e = {done:'✅',failed:'❌',cancelled:'🛑',timed_out:'⏰'}[p.status]||'?';
    const agents = [...new Set((p.subtasks||[]).map(s=>s.agent_id).filter(Boolean))].join(', ');
    const mode = p.mode ? ` · ${p.mode}` : '';
    return `<div style="padding:10px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;cursor:pointer;transition:background .15s" 
      onclick="openTaskDetail(${JSON.stringify(tid)})"
      class="js-item-hover">
      <div>
        <div style="font-weight:500">${e} ${escHtml(p.title||p.id)}</div>
        <div style="font-size:.78em;color:var(--text-muted)">${(p.subtasks||[]).length} subtasks${mode} | Agents: ${escHtml(agents)||'—'} | ${(p.created_at||'').split('T')[0]}</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:.78em;background:var(--surface2);padding:2px 8px;border-radius:4px;color:var(--text-secondary)">${p.status}</span>
        <span style="color:var(--text-muted);font-size:.8em">▶</span>
      </div>
    </div>`;
  }).join('');
}

async function cancelTask() {
  const r = await api('/api/task/cancel', {method:'POST'});
  if (r.ok) { toast('Task cancelled', 'info'); loadTasks(); }
}

async function reassignSubtask(taskId, subtaskId) {
  if (!_allAgents.length) {
    const r = await api('/api/agents');
    if (r.ok) { _allAgents = r.agents || []; }
  }
  const agentId = prompt(
    'Reassign subtask to which agent?\nAvailable: ' +
    _allAgents.map(a=>a.id).join(', ')
  );
  if (!agentId) return;
  const r = await api('/api/task/reassign', {method:'POST', body: JSON.stringify({task_id: taskId, subtask_id: subtaskId, agent_id: agentId.trim()})});
  if (r.ok) { toast('Subtask reassigned ✅', 'success'); loadTasks(); }
  else toast('Reassign failed', 'error');
}

function openTaskDetail(tidOrPlan) {
  // Accept either a task ID string (looks up _taskStore) or a full plan object
  const plan = (typeof tidOrPlan === 'string') ? _taskStore.get(tidOrPlan) : tidOrPlan;
  if (!plan) return;
  const modal = document.getElementById('task-detail-modal');
  const content = document.getElementById('task-detail-content');
  if (!modal || !content) return;
  _taskDetailTrigger = document.activeElement;
  modal.style.display = 'flex';
  const e = {done:'✅',failed:'❌',cancelled:'🛑',timed_out:'⏰',running:'⏳',planning:'🧠'}[plan.status]||'?';
  const subtasks = plan.subtasks || [];
  const subtaskRows = subtasks.map(st => {
    const se = {done:'✅',running:'⏳',pending:'⏸️',failed:'❌',skipped:'⏭️'}[st.status]||'?';
    return `<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:.83em">
      <span>${se}</span>
      <div style="flex:1">
        <div style="font-weight:500;color:var(--text)">${escHtml(st.agent_id||'?')}</div>
        <div style="color:var(--text-secondary)">${escHtml(st.title||st.subtask_id||'')}</div>
        ${st.result ? `<div style="color:var(--text-muted);font-size:.88em;margin-top:2px;white-space:pre-wrap;max-height:80px;overflow:hidden">${escHtml(String(st.result).slice(0,300))}</div>` : ''}
      </div>
      <span style="font-size:.73em;color:var(--text-muted);white-space:nowrap">${st.status}</span>
    </div>`;
  }).join('');
  content.innerHTML = `
    <div style="margin-bottom:12px">
      <div style="font-size:.75em;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em">Goal</div>
      <div style="margin-top:4px">${escHtml(plan.description||plan.goal||plan.title||'N/A')}</div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
      <div><div style="font-size:.75em;color:var(--text-muted)">Status</div><div style="color:var(--gold);font-weight:600">${escHtml(plan.status||'?')}</div></div>
      <div><div style="font-size:.75em;color:var(--text-muted)">Mode</div><div>${escHtml(plan.mode||'auto')}</div></div>
      <div><div style="font-size:.75em;color:var(--text-muted)">ID</div><div style="font-size:.8em;font-family:monospace">${escHtml(plan.id||'?')}</div></div>
      <div><div style="font-size:.75em;color:var(--text-muted)">Created</div><div>${(plan.created_at||'').split('T')[0]||'—'}</div></div>
    </div>
    ${subtasks.length ? `<div style="font-size:.84em;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Subtasks</div>
    <div style="max-height:340px;overflow-y:auto">${subtaskRows}</div>` : ''}
    ${plan.result ? `<div style="margin-top:14px"><div style="font-size:.84em;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Final Output</div><pre style="font-size:.8em;background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px;white-space:pre-wrap;max-height:200px;overflow-y:auto">${escHtml(String(plan.result).slice(0,1500))}</pre></div>` : ''}
  `;
  document.getElementById('task-detail-heading').textContent = (plan.title||plan.id||'Task Detail');
  document.getElementById('task-detail-dialog')?.focus();
}

function closeTaskDetail() {
  const modal = document.getElementById('task-detail-modal');
  if (modal) modal.style.display = 'none';
  if (_taskDetailTrigger && typeof _taskDetailTrigger.focus === 'function') _taskDetailTrigger.focus();
  _taskDetailTrigger = null;
}

// ── Swarm ────────────────────────────────────────────────────────────────────
async function loadSwarm() {
  const r = await api('/api/agents');
  if (!r.ok) return;
  const agents = r.agents || [];
  _allAgents = agents; // cache for task picker
  renderSwarmGrid(agents);
  // Update stats
  const onlineCount = agents.filter(a => a.running).length;
  const cats = new Set(agents.map(a => a.category).filter(Boolean));
  const statOnline = document.getElementById('swarm-stat-online');
  const statTotal = document.getElementById('swarm-stat-total');
  const statCats = document.getElementById('swarm-stat-categories');
  if (statOnline) statOnline.textContent = onlineCount;
  if (statTotal) statTotal.textContent = agents.length;
  if (statCats) statCats.textContent = cats.size;
  // Update header badge with total count
  const headerBadge = document.getElementById('swarm-header-badge');
  if (headerBadge && agents.length > 0) headerBadge.textContent = agents.length + ' Agents';
  // Load activity
  loadSwarmActivity();
}

async function loadSwarmActivity() {
  // Pull recent task history for activity stream
  const r = await api('/api/tasks?limit=20');
  const streamEl = document.getElementById('swarm-activity-stream');
  const activeTaskEl = document.getElementById('swarm-active-task');
  const statTasksEl = document.getElementById('swarm-stat-tasks');

  const tasks = r.plans || r.tasks || r.history || [];
  if (statTasksEl) statTasksEl.textContent = r.total || tasks.length || 0;

  // Active task
  const activeTasks = tasks.filter(t => t.status === 'running' || t.status === 'in_progress');
  if (activeTaskEl) {
    if (!activeTasks.length) {
      activeTaskEl.innerHTML = '<div class="empty"><div class="icon">⚡</div><p style="font-size:.83em">No active task. Launch one from the Tasks tab.</p></div>';
    } else {
      const t = activeTasks[0];
      const agents = (t.agents || t.selected_agents || []).slice(0,5);
      const agentPills = agents.map(a => `<span style="background:rgba(212,175,55,.1);padding:2px 7px;border-radius:4px;font-size:.72em;border:1px solid rgba(212,175,55,.2);color:var(--gold-light)">${escHtml(a)}</span>`).join('');
      activeTaskEl.innerHTML = `<div style="padding:8px">
        <div style="font-size:.9em;font-weight:600;color:var(--text);margin-bottom:4px">${escHtml((t.description||t.goal||'Task').slice(0,80))}${(t.description||t.goal||'').length>80?'…':''}</div>
        <div style="font-size:.72em;color:var(--success);font-weight:600;margin-bottom:8px">● Running</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">${agentPills}</div>
        <div style="height:4px;background:rgba(212,175,55,.1);border-radius:2px;overflow:hidden"><div style="height:100%;width:${Math.min(90,20+Math.random()*60)|0}%;background:linear-gradient(90deg,var(--primary-dark),var(--primary));border-radius:2px;animation:pulse 2s infinite"></div></div>
      </div>`;
    }
  }

  // Activity stream
  if (streamEl) {
    if (!tasks.length) {
      streamEl.innerHTML = '<div class="empty"><div class="icon">📡</div><p style="font-size:.83em">No activity yet. Run a task to see agents collaborate.</p></div>';
      return;
    }
    const statusIcon = {completed:'✅', running:'⚡', failed:'❌', pending:'⏳', cancelled:'🚫'};
    const statusColor = {completed:'var(--success)', running:'var(--gold)', failed:'var(--danger)', pending:'var(--text-muted)', cancelled:'var(--text-muted)'};
    streamEl.innerHTML = tasks.slice(0,20).map(t => {
      const icon = statusIcon[t.status] || '📋';
      const col = statusColor[t.status] || 'var(--text-muted)';
      const agents = (t.agents || t.selected_agents || []).slice(0,3).join(', ');
      const ts = (t.created_at||t.ts||'').replace('T',' ').slice(0,16);
      const dur = t.duration_seconds ? `${Math.round(t.duration_seconds)}s` : '';
      return `<div style="padding:8px 10px;background:var(--surface2);border-radius:8px;border:1px solid var(--border);border-left:3px solid ${col}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px">
          <div style="display:flex;gap:6px;align-items:flex-start;flex:1">
            <span style="margin-top:1px">${icon}</span>
            <div style="flex:1;min-width:0">
              <div style="font-size:.82em;color:var(--text);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml((t.description||t.goal||'Task').slice(0,60))}</div>
              ${agents ? `<div style="font-size:.72em;color:var(--text-muted);margin-top:2px">🤖 ${escHtml(agents)}${(t.agents||[]).length>3?'+more':''}</div>` : ''}
            </div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:.7em;color:${col};font-weight:600">${escHtml(t.status||'?')}</div>
            ${ts ? `<div style="font-size:.68em;color:var(--text-muted)">${ts}</div>` : ''}
            ${dur ? `<div style="font-size:.68em;color:var(--text-muted)">${dur}</div>` : ''}
          </div>
        </div>
      </div>`;
    }).join('');
  }
}

function renderSwarmGrid(agents) {
  const grid = document.getElementById('swarm-grid');
  if (!agents.length) {
    grid.innerHTML = '<div class="empty"><div class="icon">🐝</div><p>No agent data.</p></div>';
    return;
  }
  grid.innerHTML = agents.map(a => {
    const color = _catColors[a.category] || '#64748b';
    const isRunning = a.running;
    const dotColor = isRunning ? '#10b981' : '#4b5563';
    const dotGlow = isRunning ? 'box-shadow:0 0 8px rgba(16,185,129,.7)' : '';
    const cardGlow = isRunning ? 'box-shadow:0 4px 24px rgba(0,0,0,.5),0 0 0 1px rgba(16,185,129,.1)' : '';
    const statusLabel = isRunning ? '<span style="font-size:.7em;color:#34d399;font-weight:600;letter-spacing:.02em">ONLINE</span>' : '<span style="font-size:.7em;color:#4b5563;font-weight:600;letter-spacing:.02em">OFFLINE</span>';
    const skills = (a.skills||[]).slice(0,4).map(s => `<span style="background:rgba(212,175,55,.08);padding:2px 7px;border-radius:4px;font-size:.7em;color:var(--gold-light);border:1px solid rgba(212,175,55,.18)">${escHtml(s)}</span>`).join('');
    const moreSkills = (a.skills||[]).length > 4 ? `<span style="font-size:.7em;color:var(--text-muted);padding:2px 6px">+${(a.skills||[]).length-4} more</span>` : '';
    return `<div data-category="${escHtml(a.category||'')}" style="background:var(--surface2);border:1px solid ${isRunning ? 'rgba(16,185,129,.2)' : 'var(--border)'};border-radius:var(--radius);padding:16px;display:flex;flex-direction:column;transition:all .25s;${cardGlow}" class="js-agent-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
        <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0">
          <div style="width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,${color}22,${color}11);border:1px solid ${color}44;display:flex;align-items:center;justify-content:center;font-size:1.1em;flex-shrink:0">🤖</div>
          <div style="min-width:0">
            <div style="font-weight:700;font-size:.88em;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(a.id)}</div>
            <div style="font-size:.7em;color:${color};font-weight:500;margin-top:1px">${escHtml(a.category||'General')}</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:5px;flex-shrink:0">
          ${statusLabel}
          <span style="width:8px;height:8px;border-radius:50%;background:${dotColor};display:inline-block;${dotGlow}"></span>
        </div>
      </div>
      <div style="font-size:.8em;color:var(--text-secondary);margin-bottom:10px;line-height:1.5;flex:1">${escHtml((a.description||'No description available.').slice(0,100))}${(a.description||'').length>100?'…':''}</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">${skills}${moreSkills}</div>
      <button class="btn btn-ghost btn-sm" onclick="assignTaskToAgent('${escHtml(a.id)}')" class="btn-assign-task">⚡ Assign Task</button>
    </div>`;
  }).join('');
}

async function swarmTheaterRefresh() {
  const el = document.getElementById('swarm-theater');
  if (!el) return;
  const r = await api('/api/tasks?limit=10');
  const tasks = (r.plans || r.tasks || r.history || []).filter(t => (t.agents||t.selected_agents||[]).length > 1);
  if (!tasks.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🐝</div><p style="font-size:.83em">No multi-agent collaborations recorded yet. Run a task with multiple agents to see messages here.</p></div>';
    return;
  }
  const msgs = [];
  const agentEmoji = ['🤖','🧠','⚡','🎯','📊','✍️','💼','📱'];
  tasks.slice(0,6).forEach(t => {
    const agents = (t.agents || t.selected_agents || []);
    if (agents.length < 2) return;
    const ts = (t.created_at||'').replace('T',' ').slice(0,16);
    const a1 = agents[0], a2 = agents[1];
    const e1 = agentEmoji[Math.abs(a1.charCodeAt(0))%agentEmoji.length];
    const e2 = agentEmoji[Math.abs(a2.charCodeAt(0))%agentEmoji.length];
    const goal = (t.description||t.goal||'Task').slice(0,70);
    msgs.push({side:'left', agent:a1, emoji:e1, msg:`📨 Handoff to ${a2}: "${goal}"`, ts});
    if (t.status === 'completed') msgs.push({side:'right', agent:a2, emoji:e2, msg:`✅ Task complete. Result delivered.`, ts});
    else if (t.status === 'running') msgs.push({side:'right', agent:a2, emoji:e2, msg:`⚡ Processing… "${goal.slice(0,40)}${goal.length>40?'…':''}"`, ts});
  });
  if (!msgs.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🐝</div><p style="font-size:.83em">No multi-agent collaborations yet.</p></div>';
    return;
  }
  el.innerHTML = msgs.map((m, i) => `
    <div class="swarm-msg swarm-msg-${m.side}" style="display:flex;gap:8px;align-items:flex-end;${m.side==='right'?'flex-direction:row-reverse':''};animation-delay:${i*0.05}s">
      <div style="width:32px;height:32px;border-radius:50%;background:rgba(212,175,55,.1);border:1px solid rgba(212,175,55,.2);display:flex;align-items:center;justify-content:center;font-size:1em;flex-shrink:0">${m.emoji}</div>
      <div>
        <div style="font-size:.7em;color:var(--text-muted);margin-bottom:2px;${m.side==='right'?'text-align:right':''}">${escHtml(m.agent)} · ${m.ts}</div>
        <div class="swarm-msg-bubble">${escHtml(m.msg)}</div>
      </div>
    </div>`).join('');
}

function filterSwarm(category, btn) {
  if (btn) {
    document.querySelectorAll('.swarm-pill').forEach(p => {
      p.classList.remove('active');
      p.style.background = '';
      p.style.color = '';
      p.style.border = '';
    });
    btn.classList.add('active');
    btn.style.background = 'linear-gradient(135deg,var(--primary-dark),var(--primary))';
    btn.style.color = '#000';
    btn.style.border = 'none';
  }
  const searchVal = (document.getElementById('swarm-search')?.value || '').toLowerCase();
  let filtered = category === 'all' || !category ? _allAgents : _allAgents.filter(a => a.category === category);
  if (searchVal) {
    filtered = filtered.filter(a =>
      (a.id||'').toLowerCase().includes(searchVal) ||
      (a.description||'').toLowerCase().includes(searchVal) ||
      (a.skills||[]).some(s => s.toLowerCase().includes(searchVal)) ||
      (a.category||'').toLowerCase().includes(searchVal)
    );
  }
  renderSwarmGrid(filtered);
}

// ── Commands Tab ─────────────────────────────────────────────────────────────
const COMMAND_GROUPS = [
  {
    cat: '⚙️ System',
    cmds: [
      ['status', 'Get current agent status report'],
      ['workers', 'List all active workers'],
      ['start <agent>', 'Start a specific agent', true],
      ['stop <agent>', 'Stop a specific agent', true],
      ['schedule', 'List all scheduled tasks'],
      ['improvements', 'List pending skill proposals'],
      ['skills', 'Show skills library summary'],
      ['agents', 'List all AI agents'],
      ['switch to <agent>', 'Switch active agent (WhatsApp session)', true],
      ['help', 'Show full command list'],
      ['cmds', 'Show this commands reference'],
    ]
  },
  {
    cat: '🏭 Worker Bundles',
    cmds: [
      ['worker list', 'List all worker bundles'],
      ['worker create <name> agents:<a1,a2> task:<desc>', 'Create a worker bundle'],
      ['worker run <name>', 'Manually trigger a worker'],
      ['worker enable <name>', 'Enable a worker bundle'],
      ['worker disable <name>', 'Pause a worker bundle'],
      ['worker delete <name>', 'Delete a worker bundle'],
      ['worker status <name>', 'Show worker details & last run'],
      ['worker ecom', 'Create full e-commerce automation worker preset'],
    ]
  },
  {
    cat: '🛒 E-commerce Automation',
    cmds: [
      ['ecom metrics', 'Real-time revenue / profit / orders dashboard'],
      ['ecom research <niche>', 'Find top 5 trending product opportunities'],
      ['ecom listing <product>', 'Generate full Shopify listing (title/desc/tags/price)'],
      ['ecom email <type> <product>', 'Email flow: welcome|abandoned_cart|post_purchase|upsell'],
      ['ecom ads <product>', 'Facebook/Google ad copy (headline + body + CTA)'],
      ['ecom trends', 'Current trending products & niches'],
      ['ecom service <issue>', 'Customer service reply template'],
      ['ecom status', 'Listings, emails, and research session count'],
      ['order process <order_id>', 'Process a specific order'],
      ['order status <order_id>', 'Get order fulfillment status'],
      ['inventory check', 'Current stock levels across all products'],
      ['inventory forecast', '7-day demand forecast & reorder recommendations'],
      ['inventory reorder', 'Trigger auto-reorder for low-stock items'],
      ['support ticket <issue>', 'Classify & auto-resolve a support ticket'],
      ['support refund <order_id>', 'Process a refund automatically'],
      ['books daily', 'Daily P&L summary from Stripe'],
      ['books pl', 'Full P&L report (revenue / COGS / ads / profit)'],
      ['books tax', 'Quarterly tax export'],
      ['email campaign <segment>', 'Launch email campaign (new/abandoned/repeat)'],
      ['email abtest <subject1> vs <subject2>', 'Run A/B subject line test'],
      ['social post <product>', 'Generate & schedule viral social post'],
      ['social script <topic>', 'TikTok viral script'],
      ['product scan', 'Daily TikTok/Amazon trending product scan'],
      ['product validate <idea>', 'Demand validation via Google Trends / JungleScout'],
      ['product publish <product>', 'Auto-generate listing and publish to Shopify'],
    ]
  },
  {
    cat: '🚀 Tasks & Orchestration',
    cmds: [
      ['task <description>', 'Submit a multi-agent task'],
      ['task status', 'Show status of active task'],
      ['task list', 'List recent tasks'],
      ['task cancel', 'Cancel active task'],
      ['task agents <a1,a2>', 'Set agents for next task'],
      ['task mode auto|parallel|single', 'Set execution mode'],
      ['task config', 'Show current task configuration'],
      ['assign <agent> <subtask>', 'Manually dispatch a subtask'],
    ]
  },
  {
    cat: '🏢 Company Building',
    cmds: [
      ['company build <idea>', 'Full company launch package'],
      ['company validate <idea>', 'Viability check & SWOT'],
      ['company plan <idea>', 'Business plan only'],
      ['company simulate <scenario>', 'Growth simulation'],
      ['company gtm <idea>', 'Go-to-market strategy'],
      ['company pitch <company>', 'Investor pitch deck'],
      ['company org <company>', 'Org chart design'],
      ['company swot <topic>', 'SWOT analysis'],
    ]
  },
  {
    cat: '🪙 Memecoin & Web3',
    cmds: [
      ['memecoin create <concept>', 'Full token launch package'],
      ['memecoin name <concept>', 'Generate token names'],
      ['memecoin tokenomics <name>', 'Design tokenomics model'],
      ['memecoin whitepaper <name>', 'Draft whitepaper'],
      ['memecoin community <name>', 'Community strategy'],
      ['memecoin viral <name>', 'Viral launch campaign'],
    ]
  },
  {
    cat: '💰 Finance',
    cmds: [
      ['finance model <business>', '3-year financial model'],
      ['finance pl <business>', 'P&L projections'],
      ['finance runway <burn> <cash>', 'Burn rate & runway'],
      ['finance raise <stage> <amount>', 'Fundraising prep'],
      ['finance unit <product> <price>', 'Unit economics (CAC/LTV)'],
      ['finance pricing <product>', 'Pricing strategy'],
      ['finance pitch <company>', 'Investor pitch financials'],
      ['finance valuation <company>', 'Valuation methodology'],
    ]
  },
  {
    cat: '👔 HR & People',
    cmds: [
      ['hr hire <role>', 'Full hiring package'],
      ['hr jd <role>', 'Write job description'],
      ['hr screen <cv-text>', 'AI CV screening & scoring'],
      ['hr interview <role>', 'Interview question pack'],
      ['hr onboard <role>', '90-day onboarding plan'],
      ['hr review <role>', 'Performance review template'],
      ['hr org <company>', 'Org chart design'],
      ['hr culture <company>', 'Culture & values document'],
    ]
  },
  {
    cat: '🎨 Brand',
    cmds: [
      ['brand identity <company>', 'Full brand identity system'],
      ['brand name <industry>', 'Brand name generation (15 options)'],
      ['brand position <company>', 'Brand positioning strategy'],
      ['brand voice <company>', 'Brand voice & tone guide'],
      ['brand messaging <company>', 'Messaging framework'],
      ['brand story <company>', 'Brand story & narrative'],
      ['brand audit <company>', 'Competitive brand audit'],
    ]
  },
  {
    cat: '📈 Growth',
    cmds: [
      ['growth loop <product>', 'Viral growth loop design'],
      ['growth funnel <product>', 'Conversion funnel optimization'],
      ['growth abtests <feature>', 'A/B test framework'],
      ['growth retention <product>', 'Retention strategy'],
      ['growth referral <product>', 'Referral program design'],
      ['growth plg <product>', 'Product-led growth strategy'],
      ['growth experiments <product>', 'ICE-scored experiment backlog'],
    ]
  },
  {
    cat: '📋 Project Management',
    cmds: [
      ['pm start <project>', 'Kick off a project'],
      ['pm breakdown <project>', 'Work breakdown structure'],
      ['pm sprint <goal>', '2-week sprint plan'],
      ['pm roadmap <project>', 'Project roadmap & milestones'],
      ['pm risks <project>', 'Risk register & mitigation'],
      ['pm raci <project>', 'RACI responsibility matrix'],
      ['pm gantt <project>', 'Gantt chart (text-based)'],
      ['pm retro <sprint>', 'Sprint retrospective facilitation'],
    ]
  },
  {
    cat: '✍️ Content & Social',
    cmds: [
      ['content <brief>', 'Full content package'],
      ['social <brief>', 'Social media content pack'],
      ['social plan <brief>', 'Strategy plan only'],
      ['video <topic>', 'Faceless video full pipeline'],
      ['video script <topic>', 'Video script only'],
      ['video seo <topic>', 'YouTube SEO pack'],
      ['newsletter create <topic>', 'Generate newsletter issue'],
      ['course create <topic>', 'Full course package'],
      ['course outline <topic>', 'Course structure only'],
    ]
  },
  {
    cat: '💼 Sales & Leads',
    cmds: [
      ['leads <niche> <location>', 'Local business lead generation'],
      ['outreach <campaign>', 'Outreach campaign'],
      ['email <brief>', 'Cold email sequence'],
      ['prospect <niche> <location>', 'Appointment setter prospects'],
      ['websales audit <url>', 'Website audit + sales pitch'],
      ['recruit <role> <requirements>', 'Find & screen candidates'],
    ]
  },
  {
    cat: '📈 Crypto & Trading',
    cmds: [
      ['crypto <pair>', 'Technical analysis with signals'],
      ['trade <pair>', 'Trading signal & risk analysis'],
      ['signals', 'Current trading signals'],
      ['signal daily', 'Daily market summary'],
      ['arb scan <product>', 'Arbitrage opportunity scan'],
      ['arb opportunities', 'Top arbitrage opportunities'],
    ]
  },
  {
    cat: '📅 Scheduling',
    cmds: [
      ['schedule', 'List all scheduled tasks'],
      ['schedule add <label> <action> <cron>', 'Add scheduled task (via UI)'],
    ]
  },
];

let _cmdActiveFilter = null;
let _renderedCmds = [];

function loadCommandsTab() {
  // Category pills
  const pills = document.getElementById('cmd-category-pills');
  pills.innerHTML = `<span onclick="setCmdFilter(null)" id="cmd-pill-all"
    style="cursor:pointer;padding:4px 10px;border-radius:10px;font-size:.8em;background:var(--primary);color:#fff">All</span>` +
    COMMAND_GROUPS.map((g,i) => `<span onclick="setCmdFilter(${i})" id="cmd-pill-${i}"
      style="cursor:pointer;padding:4px 10px;border-radius:10px;font-size:.8em;background:var(--surface2);color:var(--text-secondary)">${g.cat}</span>`
    ).join('');
  renderCommands();
}

function setCmdFilter(idx) {
  _cmdActiveFilter = idx;
  document.getElementById('cmd-pill-all').style.background = idx===null ? 'var(--primary)' : 'var(--surface2)';
  document.getElementById('cmd-pill-all').style.color = idx===null ? '#fff' : 'var(--text-secondary)';
  COMMAND_GROUPS.forEach((_,i) => {
    const p = document.getElementById('cmd-pill-' + i);
    if (!p) return;
    p.style.background = i===idx ? 'var(--primary)' : 'var(--surface2)';
    p.style.color = i===idx ? '#fff' : 'var(--text-secondary)';
  });
  renderCommands();
}

function filterCommands() { renderCommands(); }

let _cmdType = 'whatsapp';
function switchCmdType(type, btn) {
  _cmdType = type;
  document.querySelectorAll('.cmd-type-btn').forEach(b => {
    b.classList.remove('active');
    b.style.background = '';
    b.style.color = '';
    b.style.border = '';
  });
  btn.classList.add('active');
  btn.style.background = 'linear-gradient(135deg,#B8960C,#D4AF37)';
  btn.style.color = '#000';
  btn.style.border = 'none';
  renderCommands();
}

function renderCommands() {
  const q = (document.getElementById('cmd-search')?.value || '').toLowerCase();
  const isWA = _cmdType === 'whatsapp';
  const groups = _cmdActiveFilter !== null ? [COMMAND_GROUPS[_cmdActiveFilter]] : COMMAND_GROUPS;
  const list = document.getElementById('cmd-list');
  if (!list) return;
  list.innerHTML = groups.map(g => {
    const rows = g.cmds
      .filter(cmd => !q || cmd[0].toLowerCase().includes(q) || cmd[1].toLowerCase().includes(q))
      .map(cmd => {
        const [cmdStr, desc, waOnly] = cmd;
        let execBtn = '';
        if (!isWA && !waOnly) {
          execBtn = `<button onclick="executeCmd('${escHtml(cmdStr)}')" class="btn-cmd-run" title="Execute in Chat">▶ Run</button>`;
        } else if (!isWA && waOnly) {
          execBtn = `<span style="flex-shrink:0;padding:3px 8px;font-size:.7em;opacity:.4;color:var(--text-muted)">📱 WA only</span>`;
        }
        const waShort = isWA ? `<span style="font-size:.68em;color:var(--text-muted);margin-left:4px">→ send via WhatsApp</span>` : '';
        return `<div class="js-item-hover" style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:7px">
          <code onclick="copyCmd('${escHtml(cmdStr)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();copyCmd('${escHtml(cmdStr)}')}" tabindex="0" role="button" aria-label="Copy command: ${escHtml(cmdStr)}" title="Click to copy" class="cmd-code">${escHtml(cmdStr)}</code>
          <div style="flex:1;font-size:.83em;color:var(--text-secondary);line-height:1.4">${escHtml(desc)}${waShort}</div>
          <button onclick="copyCmd('${escHtml(cmdStr)}')" class="btn-cmd-copy" title="Copy">Copy</button>
          ${execBtn}
        </div>`;
      }).join('');
    if (!rows) return '';
    return `<div style="margin-bottom:20px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden">
      <div style="font-weight:700;font-size:.83em;color:var(--gold-light);padding:10px 14px;background:rgba(212,175,55,.06);border-bottom:1px solid rgba(212,175,55,.12);letter-spacing:.02em">${g.cat}</div>
      <div style="padding:6px 6px">${rows}</div>
    </div>`;
  }).join('');
}
function copyCmd(cmd) {
  navigator.clipboard.writeText(cmd).then(() => toast(`Copied: ${cmd}`, 'info')).catch(() => {});
}

function executeCmd(cmd) {
  // Switch to chat tab and send the command
  switchToChatTab();
  setTimeout(() => {
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = cmd;
      sendChat();
      toast(`Executing: ${cmd}`, 'info');
    }
  }, 200);
}

// ── ROI Metrics ──────────────────────────────────────────────────────────────
async function loadMetrics() {
  const period = document.getElementById('roi-period')?.value || 'all';
  const d = await api('/api/metrics?period=' + period);
  const s = d.summary || {};
  document.getElementById('m-tasks').textContent  = (s.tasks_completed   || 0).toLocaleString();
  document.getElementById('m-leads').textContent  = (s.leads_generated   || 0).toLocaleString();
  document.getElementById('m-hours').textContent  = (s.hours_saved       || 0).toLocaleString();
  document.getElementById('m-saved').textContent  = '€' + (s.cost_saved  || 0).toLocaleString();
  document.getElementById('m-emails').textContent = (s.emails_sent       || 0).toLocaleString();
  document.getElementById('m-content').textContent= (s.content_created   || 0).toLocaleString();

  // New ROI fields
  const humanSavedEl = document.getElementById('m-human-saved');
  if (humanSavedEl) humanSavedEl.textContent = (s.human_hours_saved || Math.round((s.hours_saved||0) * 3)) + 'h';
  const agentsEl = document.getElementById('m-agents-used');
  if (agentsEl) agentsEl.textContent = (s.agents_used || 0).toLocaleString();

  // ROI Summary
  const effEl = document.getElementById('roi-efficiency');
  if (effEl) effEl.textContent = s.efficiency_rate ? s.efficiency_rate + '%' : '–%';
  const effDescEl = document.getElementById('roi-efficiency-desc');
  if (effDescEl) {
    const eff = s.efficiency_rate ? parseFloat(s.efficiency_rate) : null;
    if (eff !== null && !isNaN(eff)) {
      effDescEl.textContent = eff >= 80 ? 'Excellent — agents are highly productive' : eff >= 50 ? 'Good — solid AI utilization' : 'Growing — run more tasks to improve';
    } else {
      effDescEl.textContent = 'Complete tasks to calculate efficiency';
    }
  }
  const avgDurEl = document.getElementById('roi-avg-duration');
  if (avgDurEl) avgDurEl.textContent = s.avg_task_duration || '–';
  const topBotEl = document.getElementById('roi-top-bot');
  if (topBotEl) topBotEl.textContent = s.top_bot || '–';
  const valueEl = document.getElementById('roi-value');
  if (valueEl) valueEl.textContent = '€' + (s.total_value || s.cost_saved || 0).toLocaleString();

  const events = d.events || [];
  const el = document.getElementById('metrics-events');
  if (!events.length) {
    el.innerHTML = '<div class="empty"><div class="icon">📊</div><p>No events yet. Run tasks to start tracking ROI.</p></div>';
    // Render empty chart + breakdowns
    _renderRoiChart([]);
    _renderRoiBreakdowns([]);
    return;
  }
  const typeIcon = {task_completed:'✅',lead_generated:'🎯',email_sent:'📧',content_created:'📝',call_booked:'📞',deal_closed:'💰',ticket_resolved:'🎫',custom:'⭐'};
  el.innerHTML = events.slice(-30).reverse().map(e => {
    const icon = typeIcon[e.type] || '⭐';
    const val = e.value ? ` <span style="color:var(--success);font-weight:600">€${e.value}</span>` : '';
    const agent = e.agent ? ` <code style="font-size:.72em">${escHtml(e.agent)}</code>` : '';
    const note = e.notes ? `<div style="font-size:.77em;color:var(--text-muted);margin-top:2px">${escHtml(e.notes)}</div>` : '';
    const ts = (e.ts||'').split('T')[0];
    return `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
      <span style="font-size:1.1em;margin-top:1px">${icon}</span>
      <div style="flex:1">
        <div style="font-size:.86em">${escHtml(e.type.replace(/_/g,' '))}${agent}${val}</div>
        ${note}
      </div>
      <span style="font-size:.73em;color:var(--text-muted);white-space:nowrap">${ts}</span>
    </div>`;
  }).join('');

  // Render chart and breakdowns
  _renderRoiChart(events);
  _renderRoiBreakdowns(events);
}

function _renderRoiChart(events) {
  const container = document.getElementById('roi-chart-container');
  const labelsEl = document.getElementById('roi-chart-labels');
  if (!container) return;
  if (!events.length) {
    container.innerHTML = '<div class="empty" style="width:100%"><div class="icon">📈</div><p style="font-size:.84em">Record events to see value chart.</p></div>';
    if (labelsEl) labelsEl.innerHTML = '';
    return;
  }
  // Group events by date, summing values
  const byDate = {};
  events.forEach(e => {
    const day = (e.ts||'').split('T')[0] || 'Unknown';
    byDate[day] = (byDate[day] || 0) + (parseFloat(e.value) || 0);
  });
  const sorted = Object.entries(byDate).sort(([a],[b]) => a.localeCompare(b));
  const maxVal = Math.max(...sorted.map(([,v]) => v), 1);
  const maxH = 100;
  container.innerHTML = sorted.map(([date, val]) => {
    const h = Math.max(4, Math.round((val / maxVal) * maxH));
    const isToday = date === new Date().toISOString().split('T')[0];
    return `<div style="flex:1;min-width:20px;display:flex;flex-direction:column;align-items:center;gap:3px" title="${date}: €${val}">
      <div style="font-size:.68em;color:var(--success);font-weight:700">${val>0?'€'+val:''}</div>
      <div style="width:100%;height:${h}px;background:${isToday?'linear-gradient(180deg,#D4AF37,#B8960C)':'linear-gradient(180deg,rgba(212,175,55,.6),rgba(212,175,55,.2))'};border-radius:3px 3px 0 0;transition:all .3s"></div>
    </div>`;
  }).join('');
  if (labelsEl) {
    labelsEl.innerHTML = sorted.map(([date]) => {
      const d = new Date(date);
      const label = isNaN(d.getTime()) ? date : d.toLocaleDateString('en-US',{month:'short',day:'numeric'});
      return `<div style="flex:1;text-align:center;font-size:.62em;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${label}</div>`;
    }).join('');
  }
}

function _renderRoiBreakdowns(events) {
  // Agent breakdown
  const agentEl = document.getElementById('roi-agent-breakdown');
  if (agentEl) {
    const byAgent = {};
    events.forEach(e => {
      if (!e.agent) return;
      if (!byAgent[e.agent]) byAgent[e.agent] = {count: 0, value: 0};
      byAgent[e.agent].count++;
      byAgent[e.agent].value += parseFloat(e.value) || 0;
    });
    const agentEntries = Object.entries(byAgent).sort(([,a],[,b]) => b.count - a.count).slice(0,10);
    if (!agentEntries.length) {
      agentEl.innerHTML = '<div class="empty"><div class="icon">🤖</div><p style="font-size:.84em">No agent data yet.</p></div>';
    } else {
      const maxCount = Math.max(...agentEntries.map(([,v])=>v.count),1);
      agentEl.innerHTML = agentEntries.map(([agent,stats]) => {
        const pct = Math.round((stats.count/maxCount)*100);
        return `<div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;font-size:.82em;margin-bottom:3px">
            <span style="color:var(--text);font-weight:600">${escHtml(agent)}</span>
            <span style="color:var(--text-muted)">${stats.count} events${stats.value>0?' · €'+stats.value:''}</span>
          </div>
          <div style="height:6px;background:rgba(212,175,55,.12);border-radius:3px;overflow:hidden">
            <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,var(--primary-dark),var(--primary));border-radius:3px;transition:width .4s"></div>
          </div>
        </div>`;
      }).join('');
    }
  }
  // Task type breakdown
  const typeEl = document.getElementById('roi-type-breakdown');
  if (typeEl) {
    const byType = {};
    events.forEach(e => {
      const t = e.type || 'custom';
      if (!byType[t]) byType[t] = {count: 0, value: 0};
      byType[t].count++;
      byType[t].value += parseFloat(e.value) || 0;
    });
    const typeEntries = Object.entries(byType).sort(([,a],[,b]) => b.count - a.count);
    const typeIcon2 = {task_completed:'✅',lead_generated:'🎯',email_sent:'📧',content_created:'📝',call_booked:'📞',deal_closed:'💰',ticket_resolved:'🎫',custom:'⭐'};
    if (!typeEntries.length) {
      typeEl.innerHTML = '<div class="empty"><div class="icon">📋</div><p style="font-size:.84em">No task type data yet.</p></div>';
    } else {
      const maxCount = Math.max(...typeEntries.map(([,v])=>v.count),1);
      typeEl.innerHTML = typeEntries.map(([type,stats]) => {
        const pct = Math.round((stats.count/maxCount)*100);
        const icon = typeIcon2[type] || '⭐';
        return `<div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;font-size:.82em;margin-bottom:3px">
            <span style="color:var(--text);font-weight:600">${icon} ${escHtml(type.replace(/_/g,' '))}</span>
            <span style="color:var(--text-muted)">${stats.count}×${stats.value>0?' · €'+stats.value:''}</span>
          </div>
          <div style="height:6px;background:rgba(212,175,55,.12);border-radius:3px;overflow:hidden">
            <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,rgba(212,175,55,.7),rgba(245,196,0,.9));border-radius:3px;transition:width .4s"></div>
          </div>
        </div>`;
      }).join('');
    }
  }
}

async function recordMetric() {
  const type  = document.getElementById('metric-type').value;
  const agent = document.getElementById('metric-agent').value.trim();
  const value = parseFloat(document.getElementById('metric-value').value) || null;
  const notes = document.getElementById('metric-notes').value.trim();
  const r = await api('/api/metrics', {method:'POST',
    body: {type, agent: agent||null, value, notes: notes||null}});
  if (r.ok) {
    toast('Metric recorded!');
    document.getElementById('metric-value').value = '';
    document.getElementById('metric-notes').value = '';
    loadMetrics();
  } else { toast(r.detail || r.error || 'Error', 'error'); }
}

// ── Templates ────────────────────────────────────────────────────────────────
let _allTemplates = [];
let _tmplCatFilter = '';

async function loadTemplates() {
  const d = await api('/api/templates');
  _allTemplates = d.templates || [];
  renderTemplatesGrid();
}

function filterTemplatesCat(cat, btn) {
  _tmplCatFilter = cat;
  document.querySelectorAll('.tmpl-pill').forEach(p => {
    p.classList.remove('active');
    p.style.background = '';
    p.style.color = '';
    p.style.border = '';
  });
  if (btn) {
    btn.classList.add('active');
    btn.style.background = 'linear-gradient(135deg,var(--primary-dark),var(--primary))';
    btn.style.color = '#000';
    btn.style.border = 'none';
  }
  renderTemplatesGrid();
}

function filterTemplates() {
  renderTemplatesGrid();
}

function renderTemplatesGrid() {
  const el = document.getElementById('templates-grid');
  if (!el) return;
  const searchVal = (document.getElementById('template-search')?.value || '').toLowerCase();
  let templates = _allTemplates;
  if (_tmplCatFilter) templates = templates.filter(t => (t.category||'').toLowerCase().includes(_tmplCatFilter.toLowerCase()));
  if (searchVal) templates = templates.filter(t =>
    (t.name||'').toLowerCase().includes(searchVal) ||
    (t.description||'').toLowerCase().includes(searchVal) ||
    (t.category||'').toLowerCase().includes(searchVal)
  );
  if (!templates.length) {
    el.innerHTML = '<div class="empty"><div class="icon">📋</div><p>No templates match your filter.</p></div>';
    return;
  }
  const catColors = {Sales:'rgba(16,185,129,.15)',Support:'rgba(212,175,55,.12)',HR:'rgba(34,211,238,.15)',Content:'rgba(245,158,11,.15)','E-commerce':'rgba(239,68,68,.15)',Marketing:'rgba(168,85,247,.15)',Analytics:'rgba(74,222,128,.15)',Research:'rgba(56,189,248,.15)'};
  const catBorderColors = {Sales:'rgba(16,185,129,.3)',Support:'rgba(212,175,55,.25)',HR:'rgba(34,211,238,.3)',Content:'rgba(245,158,11,.3)','E-commerce':'rgba(239,68,68,.3)',Marketing:'rgba(168,85,247,.3)',Analytics:'rgba(74,222,128,.3)',Research:'rgba(56,189,248,.3)'};
  el.innerHTML = templates.map(t => {
    const col = catColors[t.category] || 'rgba(212,175,55,.1)';
    const bdr = catBorderColors[t.category] || 'rgba(212,175,55,.2)';
    const agents = (t.agents||[]).map(a => `<span style="background:rgba(212,175,55,.08);padding:2px 8px;border-radius:4px;font-size:.72em;border:1px solid rgba(212,175,55,.2);color:var(--gold-light)">${escHtml(a)}</span>`).join(' ');
    const expected = t.expected_results || {};
    const roi = expected.estimated_monthly_revenue || expected.estimated_monthly_savings || expected.estimated_monthly_value || '';
    const steps = (t.setup_steps||[]).map(s => `<li style="margin-bottom:4px">${escHtml(s)}</li>`).join('');
    return `<div style="border:1px solid ${bdr};border-radius:var(--radius);padding:20px;background:linear-gradient(135deg,var(--surface2) 0%,rgba(12,18,36,.98) 100%);display:flex;flex-direction:column;gap:14px;transition:all .25s;position:relative;overflow:hidden" class="js-card-hover">
      <div style="position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,${bdr},transparent);pointer-events:none"></div>
      <div style="display:flex;align-items:center;gap:12px">
        <div style="width:52px;height:52px;border-radius:14px;background:${col};border:1px solid ${bdr};display:flex;align-items:center;justify-content:center;font-size:1.8em;flex-shrink:0">${escHtml(t.icon||'📋')}</div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:1em;color:var(--text);margin-bottom:3px">${escHtml(t.name)}</div>
          <span style="font-size:.73em;background:${col};padding:2px 9px;border-radius:20px;color:var(--text-secondary);border:1px solid ${bdr}">${escHtml(t.category)}</span>
        </div>
        ${roi ? `<div style="text-align:right;flex-shrink:0"><div style="font-size:.68em;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px">Expected</div><div style="font-size:.88em;color:var(--success);font-weight:700;background:rgba(16,185,129,.1);padding:4px 10px;border-radius:8px;border:1px solid rgba(16,185,129,.2)">${escHtml(roi)}</div></div>` : ''}
      </div>
      <p style="font-size:.83em;color:var(--text-secondary);line-height:1.6;margin:0">${escHtml(t.description)}</p>
      <div>
        <div style="font-size:.7em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Agents Deployed</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px">${agents}</div>
      </div>
      ${steps ? `<details style="font-size:.8em"><summary style="cursor:pointer;color:var(--gold);font-weight:600;list-style:none;display:flex;align-items:center;gap:5px"><span>▶</span> Setup Steps</summary><ol style="color:var(--text-muted);margin:8px 0 0 16px;line-height:1.7;padding:0">${steps}</ol></details>` : ''}
      <button onclick="deployTemplate('${jsEsc(t.id)}','${jsEsc(t.name)}')" class="btn-deploy">🚀 Deploy Template</button>
    </div>`;
  }).join('');
}

async function deployTemplate(id, name) {
  if (!confirm(`Deploy template "${name}"?\n\nThis will create a new Worker Bundle with pre-configured agents and schedule.`)) return;
  const r = await api(`/api/templates/${id}/deploy`, {method:'POST'});
  if (r.ok) {
    toast(`✅ Template "${name}" deployed! Check Agents tab.`, 'success');
  } else { toast(r.detail || r.error || 'Deployment failed', 'error'); }
}


async function loadGuardrails() {
  const d = await api('/api/guardrails');
  const pending  = d.pending  || [];
  const log      = d.log      || [];
  const summary  = d.summary  || {};

  document.getElementById('g-pending').textContent  = pending.length;
  document.getElementById('g-approved').textContent = summary.approved || 0;
  document.getElementById('g-rejected').textContent = summary.rejected || 0;
  document.getElementById('g-total').textContent    = summary.total    || 0;

  // Update nav badge for pending approvals
  const navBadge = document.getElementById('guardrail-pending-badge');
  if (navBadge) {
    if (pending.length > 0) {
      navBadge.textContent = pending.length;
      navBadge.style.display = 'inline-block';
    } else {
      navBadge.style.display = 'none';
    }
  }

  // Show/hide notification banner
  const banner = document.getElementById('guardrails-notification-banner');
  if (banner) {
    if (pending.length > 0) {
      banner.style.display = 'flex';
      banner.innerHTML = `<span style="font-size:1.2em">⚠️</span> <strong>${pending.length} pending approval${pending.length!==1?'s':''} require your attention.</strong> Review below before agents proceed.`;
    } else {
      banner.style.display = 'none';
    }
  }

  const pEl = document.getElementById('guardrails-pending');
  if (!pending.length) {
    pEl.innerHTML = '<div class="empty"><div class="icon">✅</div><p>No pending approvals. All clear!</p></div>';
  } else {
    const riskColor = {high:'#ef4444', medium:'#f59e0b', low:'#10b981'};
    const riskBg = {high:'rgba(239,68,68,.08)', medium:'rgba(245,158,11,.08)', low:'rgba(16,185,129,.06)'};
    pEl.innerHTML = pending.map(a => {
      const col = riskColor[a.risk_level] || '#f59e0b';
      const bg = riskBg[a.risk_level] || 'rgba(245,158,11,.06)';
      const reqTime = a.requested_at ? new Date(a.requested_at).toLocaleTimeString() : '';
      return `<div style="border:2px solid ${col};border-radius:var(--radius-sm);padding:14px 16px;margin-bottom:12px;background:${bg};animation:borderGlow 3s ease infinite">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap">
          <div style="flex:1;min-width:200px">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
              <span style="background:${col};color:#fff;border-radius:4px;padding:1px 7px;font-size:.72em;font-weight:700;text-transform:uppercase">${escHtml(a.risk_level||'medium')} RISK</span>
              <span style="font-size:.88em;font-weight:700;color:var(--text)">${escHtml(a.action_type||'Action')}</span>
            </div>
            <div style="font-size:.84em;color:var(--text-secondary);margin:4px 0;line-height:1.5">${escHtml(a.description||'No description')}</div>
            <div style="font-size:.76em;color:var(--text-muted);margin-top:4px">
              Agent: <code style="background:rgba(255,255,255,.06);padding:1px 5px;border-radius:3px">${escHtml(a.agent||'?')}</code>
              ${reqTime ? ` · Requested: ${reqTime}` : ''}
            </div>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">
            <button onclick="approveAction('${jsEsc(a.id)}')" class="btn-approve">✅ Accept</button>
            <button onclick="rejectAction('${jsEsc(a.id)}')" class="btn-reject">🚫 Reject</button>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  const lEl = document.getElementById('guardrails-log');
  if (!log.length) {
    lEl.innerHTML = '<div class="empty"><div class="icon">📋</div><p>No actions logged yet.</p></div>';
  } else {
    const statusIcon = {approved:'✅', rejected:'🚫', pending:'⏳', auto_approved:'✔️'};
    lEl.innerHTML = log.slice(-20).reverse().map(e => {
      const icon = statusIcon[e.status] || '📋';
      const ts = (e.ts||'').replace('T',' ').slice(0,16);
      return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:.83em">
        <span>${icon}</span>
        <div style="flex:1">
          <span>${escHtml(e.action_type||'action')}</span>
          <code style="font-size:.77em;margin-left:4px">${escHtml(e.agent||'?')}</code>
        </div>
        <span style="font-size:.73em;color:var(--text-muted)">${ts}</span>
      </div>`;
    }).join('');
  }
  // Render custom guardrails
  _renderCustomGuardrails(d.custom_rules || []);
}

async function approveAction(id) {
  const r = await api(`/api/guardrails/${id}/approve`, {method:'POST'});
  if (r.ok) { toast('Action approved ✅'); loadGuardrails(); }
  else { toast(r.detail || 'Error', 'error'); }
}

async function rejectAction(id) {
  const reason = prompt('Reason for rejection (optional):') || '';
  const r = await api(`/api/guardrails/${id}/reject`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({reason})});
  if (r.ok) { toast('Action rejected 🚫', 'error'); loadGuardrails(); }
  else { toast(r.detail || 'Error', 'error'); }
}

async function saveGuardrailSettings() {
  const settings = {
    require_approval_for: {
      send_email:    document.getElementById('gr-send-email').checked,
      social_post:   document.getElementById('gr-social-post').checked,
      make_purchase: document.getElementById('gr-make-purchase').checked,
      delete_data:   document.getElementById('gr-delete-data').checked,
      api_calls:     document.getElementById('gr-api-calls').checked,
    },
    rate_limits: {
      emails_per_day: parseInt(document.getElementById('rl-emails').value) || 200,
      posts_per_day:  parseInt(document.getElementById('rl-posts').value) || 10,
      api_per_hour:   parseInt(document.getElementById('rl-api').value) || 100,
    }
  };
  const r = await api('/api/guardrails/settings', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(settings)});
  if (r.ok) { toast('Settings saved ✅'); }
  else { toast(r.detail || 'Error', 'error'); }
}

async function addCustomGuardrail() {
  const type = document.getElementById('gr-custom-type')?.value || 'custom';
  const rule = (document.getElementById('gr-custom-rule')?.value || '').trim();
  const severity = document.getElementById('gr-custom-severity')?.value || 'medium';
  const resultEl = document.getElementById('gr-custom-result');
  if (!rule) {
    if (resultEl) resultEl.innerHTML = '<span style="color:var(--danger)">Rule description is required.</span>';
    return;
  }
  const r = await api('/api/guardrails/custom', {
    method: 'POST',
    body: {type, rule, severity}
  });
  if (r.ok) {
    toast('Custom guardrail added ✅', 'success');
    if (resultEl) resultEl.innerHTML = '<span style="color:var(--success)">✅ Rule saved!</span>';
    document.getElementById('gr-custom-rule').value = '';
    loadGuardrails();
    setTimeout(() => { if (resultEl) resultEl.innerHTML = ''; }, 3000);
  } else {
    const msg = r.detail || r.error || 'Error saving rule';
    if (resultEl) resultEl.innerHTML = `<span style="color:var(--danger)">❌ ${escHtml(msg)}</span>`;
  }
}

function _renderCustomGuardrails(rules) {
  const el = document.getElementById('custom-guardrails-list');
  if (!el) return;
  if (!rules || !rules.length) {
    el.innerHTML = '<div class="empty" style="padding:12px"><div class="icon" style="font-size:1.4em">🔒</div><p style="font-size:.84em">No custom rules yet. Add one on the right.</p></div>';
    return;
  }
  const sevColors = {critical:'#ef4444', high:'#f59e0b', medium:'#eab308', low:'#10b981'};
  const sevIcons = {critical:'🔴', high:'🟠', medium:'🟡', low:'🟢'};
  el.innerHTML = rules.map((rule, idx) => {
    const col = sevColors[rule.severity || 'medium'] || '#eab308';
    const icon = sevIcons[rule.severity || 'medium'] || '🟡';
    return `<div style="border:1px solid ${col}33;border-radius:var(--radius-sm);padding:10px;margin-bottom:8px;background:var(--surface2);border-left:3px solid ${col}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <div style="flex:1">
          <div style="font-size:.78em;font-weight:600;color:${col};margin-bottom:3px">${icon} ${escHtml((rule.type||'custom').replace(/_/g,' '))} · ${escHtml(rule.severity||'medium')}</div>
          <div style="font-size:.83em;color:var(--text-secondary);line-height:1.4">${escHtml(rule.rule||'')}</div>
        </div>
        <button class="btn btn-danger btn-sm" onclick="deleteCustomGuardrail(${JSON.stringify(rule.id||'')})" title="Remove rule" style="flex-shrink:0;padding:2px 7px;font-size:.7em">✕</button>
      </div>
    </div>`;
  }).join('');
}

async function deleteCustomGuardrail(ruleId) {
  if (!ruleId) { toast('Invalid rule ID', 'error'); return; }
  if (!confirm('Remove this guardrail rule?')) return;
  const r = await api(`/api/guardrails/custom/${encodeURIComponent(ruleId)}`, {method: 'DELETE'});
  if (r.ok) { toast('Rule removed', 'error'); loadGuardrails(); }
  else { toast(r.detail || 'Error', 'error'); }
}


let _allMemoryClients = [];

async function loadMemory() {
  const d = await api('/api/memory');
  _allMemoryClients = d.clients || [];
  const recent  = d.recent_interactions || [];

  renderMemoryClients(_allMemoryClients);

  const rEl = document.getElementById('memory-recent');
  if (!recent.length) {
    rEl.innerHTML = '<div class="empty"><div class="icon">📝</div><p>No recent interactions.</p></div>';
  } else {
    rEl.innerHTML = recent.slice(-10).reverse().map(i => {
      const ts = (i.ts||'').replace('T',' ').slice(0,16);
      return `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:.83em">
        <div>${escHtml(i.summary||i.message||'interaction')}</div>
        <div style="font-size:.77em;color:var(--text-muted);margin-top:2px">${ts} · ${escHtml(i.agent||'system')}</div>
      </div>`;
    }).join('');
  }

  // Load conversations
  loadMemoryConversations();
}

function filterMemoryClients() {
  const q = (document.getElementById('memory-search')?.value || '').toLowerCase();
  const statusFilter = document.getElementById('memory-status-filter')?.value || '';
  let filtered = _allMemoryClients;
  if (q) filtered = filtered.filter(c =>
    (c.name||'').toLowerCase().includes(q) ||
    (c.company||'').toLowerCase().includes(q) ||
    (c.email||'').toLowerCase().includes(q) ||
    (c.phone||'').toLowerCase().includes(q)
  );
  if (statusFilter) filtered = filtered.filter(c => (c.status||'prospect') === statusFilter);
  renderMemoryClients(filtered);
}

function renderMemoryClients(clients) {
  const cEl = document.getElementById('memory-clients');
  if (!cEl) return;
  if (!clients.length) {
    cEl.innerHTML = '<div class="empty"><div class="icon">👥</div><p>No clients match. Add a new one on the right.</p></div>';
    return;
  }
  const statusColor = {prospect:'rgba(245,158,11,.2)', lead:'rgba(34,211,238,.2)', customer:'rgba(16,185,129,.2)', churned:'rgba(239,68,68,.12)'};
  cEl.innerHTML = clients.map(c => {
    const col = statusColor[c.status] || 'var(--surface)';
    const lastContact = c.last_contact || (c.updated_at||c.added_at||'').split('T')[0] || '–';
    return `<div class="js-card-row-hover" style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;margin-bottom:8px;background:var(--surface2)">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="font-weight:600;font-size:.9em">${escHtml(c.name)}</div>
          ${c.company ? `<div style="font-size:.8em;color:var(--text-secondary)">${escHtml(c.company)}</div>` : ''}
          ${c.email   ? `<div style="font-size:.77em;color:var(--text-muted)">✉ ${escHtml(c.email)}</div>`   : ''}
          ${c.phone   ? `<div style="font-size:.77em;color:var(--text-muted)">📞 ${escHtml(c.phone)}</div>`   : ''}
          <div style="font-size:.72em;color:var(--text-muted);margin-top:3px">🕐 Last contact: ${escHtml(lastContact)}</div>
        </div>
        <span style="font-size:.73em;background:${col};padding:2px 8px;border-radius:4px;border:1px solid var(--border)">${escHtml(c.status||'prospect')}</span>
      </div>
      ${c.notes ? `<div style="font-size:.78em;color:var(--text-muted);margin-top:6px;line-height:1.4">${escHtml(c.notes)}</div>` : ''}
      <div style="font-size:.72em;color:var(--text-muted);margin-top:4px">${(c.interactions||0)} interactions · added ${(c.added_at||'').split('T')[0]}</div>
      <div style="margin-top:8px;display:flex;gap:5px;flex-wrap:wrap">
        <button class="btn btn-ghost btn-sm" onclick="updateClientStatus('${jsEsc(c.id)}','customer')" style="font-size:.73em">Mark customer</button>
        <button class="btn btn-ghost btn-sm" onclick="updateClientStatus('${jsEsc(c.id)}','lead')" style="font-size:.73em">Mark lead</button>
        <button class="btn btn-danger btn-sm" onclick="deleteClient('${jsEsc(c.id)}')">🗑</button>
      </div>
    </div>`;
  }).join('');
}

let _allConversations = [];
async function loadMemoryConversations() {
  const d = await api('/api/memory/conversations');
  _allConversations = d.conversations || [];
  renderConversations(_allConversations);
}

function filterConversations() {
  const q = (document.getElementById('conv-search')?.value || '').toLowerCase();
  const filtered = q ? _allConversations.filter(c =>
    (c.summary||'').toLowerCase().includes(q) ||
    (c.date||'').includes(q) ||
    (c.title||'').toLowerCase().includes(q)
  ) : _allConversations;
  renderConversations(filtered);
}

function renderConversations(conversations) {
  const el = document.getElementById('memory-conversations');
  if (!el) return;
  if (!conversations.length) {
    el.innerHTML = '<div class="empty"><div class="icon">💬</div><p style="font-size:.84em">No conversations yet. Chat sessions appear here automatically when closed.</p></div>';
    return;
  }
  el.innerHTML = conversations.map((c, idx) => {
    const date = (c.date||c.ts||'').split('T')[0] || '–';
    const summary = (c.summary||c.message||'Chat session').slice(0,120);
    const msgCount = c.message_count || c.messages || 0;
    return `<div class="js-card-row-hover" style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;margin-bottom:8px;background:var(--surface2);cursor:pointer" onclick="toggleConversationDetail(${idx})">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <div style="flex:1">
          <div style="font-size:.85em;font-weight:600;color:var(--text)">${escHtml(c.title||'Chat Session #'+(idx+1))}</div>
          <div style="font-size:.78em;color:var(--text-muted);margin-top:2px;line-height:1.4">${escHtml(summary)}${summary.length>=120?'…':''}</div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div style="font-size:.72em;color:var(--text-muted)">${date}</div>
          ${msgCount ? `<div style="font-size:.7em;color:var(--gold);margin-top:2px">${msgCount} msgs</div>` : ''}
        </div>
      </div>
      <div id="conv-detail-${idx}" style="display:none;margin-top:8px;padding:8px;background:var(--surface);border-radius:var(--radius-sm);border:1px solid var(--border);font-size:.8em;color:var(--text-secondary);line-height:1.5">
        ${escHtml(c.full_summary||c.summary||'No detailed summary available.')}
      </div>
    </div>`;
  }).join('');
}

function toggleConversationDetail(idx) {
  const el = document.getElementById('conv-detail-' + idx);
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

async function addClient() {
  const name    = document.getElementById('mem-name').value.trim();
  const company = document.getElementById('mem-company').value.trim();
  const email   = document.getElementById('mem-email').value.trim();
  const phone   = (document.getElementById('mem-phone')?.value || '').trim();
  const lastContact = (document.getElementById('mem-last-contact')?.value || '').trim();
  const status  = document.getElementById('mem-status').value;
  const notes   = document.getElementById('mem-notes').value.trim();
  if (!name) { toast('Name is required', 'error'); return; }
  const r = await api('/api/memory/clients', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, company: company||null, email: email||null, phone: phone||null, last_contact: lastContact||null, status, notes: notes||null})});
  if (r.ok) {
    toast('Client added ✅');
    document.getElementById('mem-name').value    = '';
    document.getElementById('mem-company').value = '';
    document.getElementById('mem-email').value   = '';
    const phoneEl = document.getElementById('mem-phone');
    if (phoneEl) phoneEl.value = '';
    const lcEl = document.getElementById('mem-last-contact');
    if (lcEl) lcEl.value = '';
    document.getElementById('mem-notes').value   = '';
    loadMemory();
  } else { toast(r.detail || 'Error', 'error'); }
}

async function updateClientStatus(id, status) {
  await api(`/api/memory/clients/${id}`, {method:'PATCH',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({status})});
  loadMemory();
}

async function deleteClient(id) {
  if (!confirm('Delete this client from memory?')) return;
  await api(`/api/memory/clients/${id}`, {method:'DELETE'});
  loadMemory();
}

// ── Integrations ─────────────────────────────────────────────────────────────
async function loadIntegrations() {
  const d = await api('/api/integrations');
  const integrations = d.integrations || [];
  const el = document.getElementById('integrations-grid');
  // Update summary stats
  const connected = integrations.filter(i => i.enabled).length;
  const total = integrations.length;
  const setT = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
  setT('intg-stat-total', total || '–');
  setT('intg-stat-connected', connected || '–');
  setT('intg-stat-pending', (total - connected) || '–');
  setT('intg-stat-pct', total ? Math.round((connected/total)*100)+'%' : '–%');
  if (!integrations.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🔌</div><p>No integrations configured.</p></div>';
    return;
  }
  el.innerHTML = integrations.map(intg => {
    const enabled = intg.enabled === true;
    const statusCol = enabled ? 'var(--success)' : 'var(--text-muted)';
  const fields = (intg.fields||[]).map(f => {
    const isPass = f.type === 'password';
    const savedVal = intg.config && intg.config[f.key] ? String(intg.config[f.key]) : '';
    // Never pre-fill password fields with saved values — show placeholder bullets instead
    const displayVal = isPass ? '' : escHtml(savedVal);
    const placeholder = isPass && savedVal ? '●●●●●●●● (set — paste new value to update)' : escHtml(f.placeholder||'');
    return `
      <div class="form-group" style="margin-bottom:8px">
        <label style="font-size:.78em">${escHtml(f.label)}${isPass && savedVal ? ' <span style="color:var(--success);font-size:.85em">● saved</span>' : ''}</label>
        <input type="${isPass?'password':f.type||'text'}" id="intg-${escHtml(intg.id)}-${escHtml(f.key)}"
          placeholder="${placeholder}"
          value="${displayVal}"
          ${isPass?'autocomplete="new-password"':''}/>
      </div>`}).join('');
    return `<div style="border:1px solid var(--border);border-radius:var(--radius);padding:18px;background:var(--surface2)">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:1.6em">${escHtml(intg.icon||'🔌')}</span>
        <div style="flex:1">
          <div style="font-weight:700;font-size:.95em">${escHtml(intg.name)}</div>
          <div style="font-size:.8em;color:var(--text-muted)">${escHtml(intg.description||'')}</div>
        </div>
        <span style="font-size:.73em;font-weight:600;color:${statusCol}">${enabled ? '● Connected' : '○ Not configured'}</span>
      </div>
      <div>${fields}</div>
      <div style="display:flex;gap:6px;margin-top:8px">
        <button class="btn btn-primary btn-sm" style="flex:1" onclick="saveIntegration('${jsEsc(intg.id)}')">💾 Save</button>
        <button class="btn btn-ghost btn-sm" onclick="testIntegration('${jsEsc(intg.id)}')">🔍 Test</button>
      </div>
      <div id="intg-result-${escHtml(intg.id)}" style="margin-top:6px;font-size:.8em"></div>
    </div>`;
  }).join('');
}

async function saveIntegration(id) {
  const d = await api('/api/integrations');
  const intg = (d.integrations||[]).find(i => i.id === id);
  if (!intg) { toast('Integration not found', 'error'); return; }
  const config = {};
  (intg.fields||[]).forEach(f => {
    const el = document.getElementById(`intg-${id}-${f.key}`);
    if (!el) return;
    const isPass = f.type === 'password';
    const val = el.value;
    if (isPass && !val.trim()) {
      // Keep existing value — user did not provide a new one
      if (intg.config && intg.config[f.key]) config[f.key] = intg.config[f.key];
    } else {
      config[f.key] = val;
    }
  });
  const enabled = Object.values(config).some(v => v && v.toString().trim());
  const r = await api(`/api/integrations/${id}`, {method:'PATCH',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({config, enabled})});
  if (r.ok) { toast(`${intg.name} saved ✅`); loadIntegrations(); }
  else { toast(r.detail || 'Error', 'error'); }
}

async function testIntegration(id) {
  const el = document.getElementById(`intg-result-${id}`);
  if (el) el.textContent = '⏳ Testing…';
  const r = await api(`/api/integrations/${id}/test`, {method:'POST'});
  if (el) {
    if (r.ok) { el.style.color = 'var(--success)'; el.textContent = '✅ ' + (r.message || 'Connection OK'); }
    else       { el.style.color = 'var(--danger)';  el.textContent = '❌ ' + (r.message || r.detail || 'Test failed'); }
  }
}


// ── Theme Customizer ─────────────────────────────────────────────────────────
(function _initTheme() {
  const saved = {};
  try { Object.assign(saved, JSON.parse(localStorage.getItem('ai_employee_theme') || '{}')); } catch(e) {}
  if (saved.mode) _applyThemeMode(saved.mode, false);
  if (saved.accent) _applyAccent(saved.accent, saved.accentDark || saved.accent, false);
  if (saved.density) _applyDensity(saved.density, false);
})();

function _applyThemeMode(mode, save=true) {
  const root = document.documentElement;
  if (mode === 'light') {
    root.style.setProperty('--bg', '#f0f0f0');
    root.style.setProperty('--surface', '#ffffff');
    root.style.setProperty('--surface2', '#f8f8f8');
    root.style.setProperty('--text', '#111111');
    root.style.setProperty('--text-muted', '#555555');
    root.style.setProperty('--border', 'rgba(0,0,0,.15)');
  } else {
    root.style.removeProperty('--bg');
    root.style.removeProperty('--surface');
    root.style.removeProperty('--surface2');
    root.style.removeProperty('--text');
    root.style.removeProperty('--text-muted');
    root.style.removeProperty('--border');
  }
  if (save) {
    const t = JSON.parse(localStorage.getItem('ai_employee_theme') || '{}');
    t.mode = mode; localStorage.setItem('ai_employee_theme', JSON.stringify(t));
  }
  const db = document.getElementById('theme-dark-btn'), lb = document.getElementById('theme-light-btn');
  if (db && lb) {
    if (mode === 'light') {
      lb.style.background = 'rgba(212,175,55,.08)'; lb.style.color = 'var(--gold)'; lb.style.borderColor = 'rgba(212,175,55,.3)';
      db.style.background = 'rgba(255,255,255,.04)'; db.style.color = 'var(--text-muted)'; db.style.borderColor = 'var(--border)';
    } else {
      db.style.background = 'linear-gradient(135deg,#0d0d0d,#1a1a1a)'; db.style.color = 'var(--gold)'; db.style.borderColor = 'rgba(212,175,55,.4)';
      lb.style.background = 'rgba(255,255,255,.05)'; lb.style.color = 'var(--text-muted)'; lb.style.borderColor = 'var(--border)';
    }
  }
}
function setThemeMode(mode) { _applyThemeMode(mode, true); }

function _applyAccent(color, colorDark, save=true) {
  document.documentElement.style.setProperty('--primary', color);
  document.documentElement.style.setProperty('--primary-dark', colorDark);
  document.documentElement.style.setProperty('--gold', color);
  document.documentElement.style.setProperty('--gold-light', color);
  if (save) {
    const t = JSON.parse(localStorage.getItem('ai_employee_theme') || '{}');
    t.accent = color; t.accentDark = colorDark;
    localStorage.setItem('ai_employee_theme', JSON.stringify(t));
  }
}
function setAccentColor(color, colorDark) { _applyAccent(color, colorDark, true); }

function _applyDensity(density, save=true) {
  const root = document.documentElement;
  const scale = density === 'compact' ? '13px' : density === 'spacious' ? '16px' : '14px';
  root.style.setProperty('font-size', scale);
  if (save) {
    const t = JSON.parse(localStorage.getItem('ai_employee_theme') || '{}');
    t.density = density; localStorage.setItem('ai_employee_theme', JSON.stringify(t));
  }
  ['compact','normal','spacious'].forEach(d => {
    const btn = document.getElementById(`density-${d}-btn`);
    if (!btn) return;
    if (d === density) {
      btn.style.background = 'rgba(212,175,55,.08)'; btn.style.color = 'var(--gold)'; btn.style.borderColor = 'rgba(212,175,55,.3)';
    } else {
      btn.style.background = 'rgba(255,255,255,.04)'; btn.style.color = 'var(--text-muted)'; btn.style.borderColor = 'var(--border)';
    }
  });
}
function setDensity(d) { _applyDensity(d, true); }

// ── Options / Settings ────────────────────────────────────────────────────────
const _settingsDrafts = {};

function _getSettingDraft(key, fallbackValue) {
  return Object.prototype.hasOwnProperty.call(_settingsDrafts, key)
    ? _settingsDrafts[key]
    : fallbackValue;
}

function _bindSettingsDraftInputs(containerId) {
  const inputs = document.querySelectorAll('#' + containerId + ' input');
  inputs.forEach(el => {
    const key = el.id.replace('opt-field-', '');
    if (!key) return;
    el.addEventListener('input', () => {
      _settingsDrafts[key] = el.value;
    });
  });
}

async function loadOptions() {
  const d = await api('/api/settings');
  renderSettingsSection('opt-api-keys',   d.api_keys    || []);
  renderSettingsSection('opt-preferences', d.preferences || []);
}

function renderSettingsSection(containerId, fields) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = fields.map(f => `
    <div class="form-group" style="margin-bottom:10px">
      <label style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <span>${escHtml(f.label)}</span>
        ${f.has_value
          ? '<span style="font-size:.73em;color:var(--success);font-weight:600">● set</span>'
          : '<span style="font-size:.73em;color:var(--text-muted)">○ not set</span>'}
      </label>
      <div style="display:flex;gap:6px">
        <input id="opt-field-${escHtml(f.key)}"
          type="${f.type === 'password' ? 'password' : 'text'}"
          placeholder="${escHtml(f.placeholder)}"
          value="${escHtml(_getSettingDraft(f.key, f.value || ''))}"
          autocomplete="off"
          style="flex:1"/>
        ${f.type === 'password'
          ? `<button class="btn btn-ghost btn-sm" style="flex-shrink:0;padding:5px 9px"
               onclick="toggleSecret('opt-field-${jsEsc(f.key)}',this)" title="Show/hide">👁</button>`
          : ''}
      </div>
    </div>`).join('');
  _bindSettingsDraftInputs(containerId);
}

function toggleSecret(inputId, btn) {
  const el = document.getElementById(inputId);
  if (!el) return;
  el.type = el.type === 'password' ? 'text' : 'password';
  btn.textContent = el.type === 'password' ? '👁' : '🙈';
}

async function saveSettings(category) {
  const containerId = 'opt-' + category.replace(/_/g, '-');
  const inputs = document.querySelectorAll('#' + containerId + ' input');
  const updates = {};
  inputs.forEach(el => {
    const key = el.id.replace('opt-field-', '');
    if (key) updates[key] = el.value;
  });
  if (!Object.keys(updates).length) { toast('Nothing to save'); return; }
  const r = await api('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({updates})
  });
  if (r.ok) {
    const msg = r.saved
      ? `✅ Saved ${r.saved} setting${r.saved !== 1 ? 's' : ''}`
      : 'No changes (all values were unchanged)';
    toast(msg, r.saved ? 'success' : 'info');
    if (r.saved) {
      Object.keys(updates).forEach(k => { delete _settingsDrafts[k]; });
      loadOptions();
    }
  } else {
    toast(r.detail || 'Error saving', 'error');
  }
}

async function runSecurityCheck() {
  const el = document.getElementById('opt-security-results');
  el.innerHTML = '<p style="color:var(--text-muted);font-size:.85em;padding:8px 0">⏳ Running security checklist…</p>';
  const d = await api('/api/settings/security-check');
  const findings = d.findings || [];

  const colorMap   = {ok:'var(--success)', warning:'#f59e0b', error:'var(--danger)', info:'var(--accent)'};
  const iconMap    = {ok:'✅', warning:'⚠️', error:'❌', info:'ℹ️'};
  const badgeMap   = {ok:'DONE', warning:'ACTION NEEDED', error:'NOT DONE', info:'INFO'};
  const badgeBgMap = {
    ok:      'rgba(34,197,94,.15)',
    warning: 'rgba(245,158,11,.15)',
    error:   'rgba(239,68,68,.15)',
    info:    'rgba(212,175,55,.12)',
  };
  const warnColor = colorMap.warning;

  if (!findings.length) {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:.85em">No findings.</p>';
    return;
  }

  const done    = findings.filter(f => f.level === 'ok').length;
  const errors  = findings.filter(f => f.level === 'error').length;
  const warns   = findings.filter(f => f.level === 'warning').length;
  const summaryColor = errors ? 'var(--danger)' : warns ? warnColor : 'var(--success)';
  const summaryIcon  = errors ? '❌' : warns ? '⚠️' : '✅';
  const summaryText  = errors
    ? `${errors} critical issue${errors>1?'s':''} found`
    : warns
      ? `${warns} warning${warns>1?'s':''} — review recommended`
      : 'All checks passed — ready for production';

  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:7px;
         background:var(--surface2);border:1px solid var(--border);margin-bottom:10px">
      <span style="font-size:1.2em">${summaryIcon}</span>
      <div>
        <div style="font-size:.88em;font-weight:700;color:${summaryColor}">${summaryText}</div>
        <div style="font-size:.76em;color:var(--text-muted);margin-top:2px">
          ${done} passed · ${errors} critical · ${warns} warnings · ${findings.filter(f=>f.level==='info').length} info
        </div>
      </div>
    </div>
    ${findings.map((f, idx) => {
      const color   = colorMap[f.level]   || 'var(--text)';
      const icon    = iconMap[f.level]    || '•';
      const badge   = badgeMap[f.level]   || f.level.toUpperCase();
      const badgeBg = badgeBgMap[f.level] || 'rgba(255,255,255,.1)';

      let actionHtml = '';
      if (f.action) {
        if (f.action_type === 'command') {
          actionHtml = `
            <div style="margin-top:7px">
              <div style="font-size:.74em;color:var(--text-muted);margin-bottom:3px;font-weight:600;letter-spacing:.03em">▶ COMMAND</div>
              <code style="display:block;background:var(--bg);border:1px solid var(--border);border-radius:5px;
                   padding:6px 10px;font-size:.78em;color:var(--accent);word-break:break-all;
                   white-space:pre-wrap">${escHtml(f.action)}</code>
            </div>`;
        } else if (f.action_type === 'config') {
          actionHtml = `
            <div style="margin-top:7px">
              <div style="font-size:.74em;color:var(--text-muted);margin-bottom:3px;font-weight:600;letter-spacing:.03em">⚙️ ADD TO security.local.yml</div>
              <code style="display:block;background:var(--bg);border:1px solid var(--border);border-radius:5px;
                   padding:6px 10px;font-size:.78em;color:${warnColor};word-break:break-all;
                   white-space:pre-wrap">${escHtml(f.action)}</code>
            </div>`;
        } else {
          actionHtml = `<div style="margin-top:5px;font-size:.78em;color:var(--text-muted)">💡 ${escHtml(f.action)}</div>`;
        }
      }

      let markDoneHtml = '';
      if (f.level !== 'ok' && f.action) {
        const btnId = `sec-done-btn-${idx}`;
        const fbId  = `sec-done-fb-${idx}`;
        markDoneHtml = `
          <div style="margin-top:8px;padding-left:26px;display:flex;align-items:center;gap:8px" id="${fbId}">
            <button id="${btnId}" class="btn btn-ghost btn-sm"
                    style="font-size:.74em;padding:3px 10px;border-color:var(--border)"
                    onclick="markSecurityActionDone(${idx+1},${JSON.stringify(f.title)},${JSON.stringify(f.action)},${JSON.stringify(f.action_type)},'${btnId}','${fbId}')">
              ${f.action_type === 'command' ? '📋 Copy & Mark Done' : '✓ Mark Done'}
            </button>
          </div>`;
      }

      return `
        <div style="display:flex;gap:10px;padding:10px 12px;border-radius:7px;
             background:var(--surface2);border:1px solid var(--border);margin-bottom:6px;
             border-left:3px solid ${color};align-items:flex-start">
          <span style="flex-shrink:0;font-size:1.05em;margin-top:1px">${icon}</span>
          <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <span style="font-size:.76em;color:var(--text-muted);font-weight:600;min-width:18px">${idx+1}.</span>
              <span style="font-size:.87em;font-weight:600;color:${color}">${escHtml(f.title)}</span>
              <span style="font-size:.7em;font-weight:700;letter-spacing:.05em;padding:2px 8px;border-radius:99px;
                   background:${badgeBg};color:${color};border:1px solid ${color}55;flex-shrink:0">${badge}</span>
            </div>
            <div style="font-size:.8em;color:var(--text-muted);margin-top:3px;padding-left:26px">
              ${escHtml(f.detail)}
            </div>
            ${actionHtml ? `<div style="padding-left:26px">${actionHtml}</div>` : ''}
            ${markDoneHtml}
          </div>
        </div>`;
    }).join('')}`;
}

async function markSecurityActionDone(num, title, action, actionType, btnId, fbId) {
  const btn = document.getElementById(btnId);
  const fb  = document.getElementById(fbId);
  if (btn) btn.disabled = true;
  if (actionType === 'command' && action) {
    try { await navigator.clipboard.writeText(action); } catch(e) {}
  }
  await api('/api/history/mark-action', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({title, action, action_type: actionType, check_number: num}),
  });
  if (fb) {
    fb.innerHTML = `<span style="font-size:.78em;color:var(--success);font-weight:600">
      ✅ ${actionType === 'command' ? 'Copied to clipboard — ' : ''}Marked as done and logged to History
    </span>`;
  }
}


// ── Activity History ──────────────────────────────────────────────────────────
let _historyEntries = [];

async function loadHistory() {
  const el = document.getElementById('history-timeline');
  if (!el) return;
  el.innerHTML = '<div class="empty"><div class="icon">⏳</div><p>Loading…</p></div>';
  const d = await api('/api/history?limit=1000');
  _historyEntries = d.entries || [];
  document.getElementById('history-count').textContent =
    `${_historyEntries.length} entr${_historyEntries.length === 1 ? 'y' : 'ies'}`;
  renderHistory(_historyEntries);
}

function filterHistory() {
  const q      = (document.getElementById('history-search')?.value || '').toLowerCase();
  const type   = document.getElementById('history-type-filter')?.value || '';
  const source = document.getElementById('history-source-filter')?.value || '';
  const filtered = _historyEntries.filter(e => {
    if (type   && e.event_type !== type)   return false;
    if (source && e.source     !== source) return false;
    if (q) {
      const hay = (e.description + ' ' + e.event_type + ' ' + (e.source||'')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  document.getElementById('history-count').textContent =
    `${filtered.length} / ${_historyEntries.length} entr${_historyEntries.length === 1 ? 'y' : 'ies'}`;
  renderHistory(filtered);
}

function renderHistory(entries) {
  const el = document.getElementById('history-timeline');
  if (!el) return;
  if (!entries.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🕐</div><p>No activity recorded yet.</p></div>';
    return;
  }

  const typeColor = {
    security_check:       'var(--accent)',
    security_action_done: 'var(--success)',
    settings_saved:       '#6366f1',
    guardrail_approved:   'var(--success)',
    guardrail_rejected:   'var(--danger)',
    agent_command:        'var(--text)',
    task_run:             'var(--accent)',
    worker_triggered:     '#f59e0b',
    system:               'var(--text-muted)',
  };

  // Group entries by date
  const groups = {};
  for (const e of entries) {
    const day = e.ts ? e.ts.slice(0, 10) : 'Unknown';
    (groups[day] = groups[day] || []).push(e);
  }

  el.innerHTML = Object.entries(groups).map(([day, items]) => `
    <div style="margin-bottom:18px">
      <div style="font-size:.74em;font-weight:700;color:var(--text-muted);letter-spacing:.06em;
           text-transform:uppercase;margin-bottom:8px;padding-left:4px">${escHtml(day)}</div>
      ${items.map(e => {
        const color = typeColor[e.event_type] || 'var(--text-muted)';
        const ts    = e.ts ? e.ts.slice(11, 19) : '';
        let detailsHtml = '';
        if (e.details && Object.keys(e.details).length) {
          const dLines = Object.entries(e.details)
            .filter(([,v]) => v !== '' && v !== null && v !== undefined)
            .map(([k, v]) => `<span style="color:var(--text-muted)">${escHtml(k)}:</span> ${escHtml(String(v))}`)
            .join('  ·  ');
          if (dLines) detailsHtml = `
            <div style="font-size:.76em;color:var(--text-muted);margin-top:3px;
                 white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${dLines}</div>`;
        }
        // Action buttons for actionable event types
        let actionsHtml = '';
        if (e.event_type === 'task_run') {
          const raw = (e.details && e.details.description) ? e.details.description : e.description;
          const taskDesc = raw.replace(/^task\s+launched[:\s]+/i,'').replace(/^task[:\s]+/i,'').trim();
          const viewBtn = (e.details && e.details.task_id)
            ? `<button class="btn btn-ghost btn-sm" style="font-size:.72em;padding:2px 8px"
                 onclick="viewTaskById(${JSON.stringify(e.details.task_id)})">📋 View</button>`
            : '';
          actionsHtml = `<div style="display:flex;gap:5px;margin-top:6px">
            <button class="btn btn-ghost btn-sm" style="font-size:.72em;padding:2px 8px;color:var(--gold);border-color:rgba(212,175,55,.3)"
              onclick="rerunTaskFromHistory(${JSON.stringify(taskDesc)})">↩ Re-run</button>
            ${viewBtn}
          </div>`;
        } else if (e.event_type === 'agent_command') {
          const cmd = (e.details && e.details.command) ? e.details.command : e.description;
          actionsHtml = `<div style="margin-top:4px">
            <button class="btn btn-ghost btn-sm" style="font-size:.72em;padding:2px 8px"
              onclick="sendAgentCommandFromHistory(${JSON.stringify(cmd)})">💬 Send Again</button>
          </div>`;
        }
        return `
          <div style="display:flex;gap:10px;padding:9px 12px;border-radius:6px;
               background:var(--surface2);border:1px solid var(--border);margin-bottom:5px;
               border-left:3px solid ${color};align-items:flex-start">
            <span style="flex-shrink:0;font-size:1em">${escHtml(e.icon||'📋')}</span>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <span style="font-size:.86em;font-weight:600;color:${color}">${escHtml(e.description)}</span>
                <span style="font-size:.7em;padding:1px 7px;border-radius:99px;background:var(--bg);
                     border:1px solid var(--border);color:var(--text-muted);flex-shrink:0">
                  ${escHtml(e.source || e.event_type || '')}
                </span>
              </div>
              ${detailsHtml}
              ${actionsHtml}
            </div>
            <span style="flex-shrink:0;font-size:.74em;color:var(--text-muted);white-space:nowrap;
                 padding-top:2px">${escHtml(ts)}</span>
          </div>`;
      }).join('')}
    </div>`).join('');
}

async function clearHistory() {
  if (!confirm('Clear all activity history? This cannot be undone.')) return;
  const r = await api('/api/history/clear', {method:'POST'});
  if (r.ok) { _historyEntries = []; renderHistory([]); toast('History cleared'); }
  else toast('Failed to clear history', 'error');
}

function exportHistory() {
  if (!_historyEntries.length) { toast('No history to export', 'info'); return; }
  const blob = new Blob([JSON.stringify(_historyEntries, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `activity-history-${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.json`;
  a.click();
  URL.revokeObjectURL(url);
  toast('History exported ✅');
}

function rerunTaskFromHistory(description) {
  const taskInput = document.getElementById('task-input');
  if (taskInput) { taskInput.value = description; }
  const tasksBtn = document.querySelector('nav button[onclick*="\'tasks\'"]');
  if (tasksBtn) switchTab('tasks', tasksBtn);
  setTimeout(() => {
    const el = document.getElementById('task-input');
    if (el) { el.focus(); el.scrollIntoView({behavior:'smooth', block:'nearest'}); }
  }, 150);
  toast('Task pre-filled — review and click Launch ↗', 'info');
}

async function viewTaskById(taskId) {
  const r = await api('/api/task/list');
  if (!r.ok) { toast('Could not load tasks', 'error'); return; }
  const plan = (r.plans || []).find(p => p.id === taskId);
  if (plan) {
    const tasksBtn = document.querySelector('nav button[onclick*="\'tasks\'"]');
    if (tasksBtn) switchTab('tasks', tasksBtn);
    setTimeout(() => {
      _taskStore.set(taskId, plan);
      openTaskDetail(taskId);
    }, 200);
  } else {
    toast('Task not found in recent history — it may have been pruned', 'info');
    const tasksBtn = document.querySelector('nav button[onclick*="\'tasks\'"]');
    if (tasksBtn) switchTab('tasks', tasksBtn);
  }
}

function sendAgentCommandFromHistory(cmd) {
  const chatInput = document.getElementById('chat-input');
  if (chatInput) { chatInput.value = cmd; chatInput.focus(); }
  const chatBtn = document.querySelector('#nav-btn-chat');
  if (chatBtn) switchTab('chat', chatBtn);
  toast('Command pre-filled in chat — press Enter to send', 'info');
}

// ── Auto-updater ──────────────────────────────────────────────────────────────
async function loadUpdaterStatus() {
  const el = document.getElementById('opt-updater-status');
  if (!el) return;
  const d = await api('/api/updater/status');
  if (d.error) {
    el.innerHTML = '<p style="color:var(--text-muted)">Updater not running yet — starts automatically with the agent runtime.</p>';
    return;
  }
  const statusColor = {
    up_to_date: 'var(--success)', updated: 'var(--accent)',
    updating: 'var(--warning)', check_failed: 'var(--danger)',
    started: 'var(--text-muted)', initialized: 'var(--text-muted)',
  };
  const local  = d.local_sha  ? d.local_sha.slice(0,8)  : '—';
  const remote = d.remote_sha ? d.remote_sha.slice(0,8) : '—';
  const col    = statusColor[d.status] || 'var(--text-muted)';
  el.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px">
        <div style="font-size:.75em;color:var(--text-muted);margin-bottom:2px">INSTALLED</div>
        <code style="font-size:.9em">${escHtml(local)}</code>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px">
        <div style="font-size:.75em;color:var(--text-muted);margin-bottom:2px">LATEST ON ${escHtml((d.branch||'main').toUpperCase())}</div>
        <code style="font-size:.9em">${escHtml(remote)}</code>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span style="font-size:.8em;font-weight:700;color:${col}">${escHtml(d.status||'unknown')}</span>
      ${d.last_check ? `<span style="font-size:.76em;color:var(--text-muted)">Last check: ${escHtml(d.last_check.slice(0,19).replace('T',' '))} UTC</span>` : ''}
    </div>
    ${d.last_update ? `<div style="font-size:.78em;color:var(--text-muted)">Last update: ${escHtml(d.last_update.slice(0,19).replace('T',' '))} UTC</div>` : ''}
    ${d.restarted_agents && d.restarted_agents.length
      ? `<div style="font-size:.78em;color:var(--text-muted);margin-top:4px">Restarted agents: ${escHtml(d.restarted_agents.join(', '))}</div>` : ''}
    <div style="font-size:.76em;color:var(--text-muted);margin-top:6px">
      Polls every ${d.interval_seconds || 300}s · Repo: ${escHtml(d.repo||'F-game25/AI-EMPLOYEE')}
    </div>`;
}

async function checkForUpdates() {
  const el = document.getElementById('opt-updater-status');
  if (el) el.innerHTML = '<p style="color:var(--text-muted);font-size:.85em;padding:8px 0">⏳ Checking GitHub…</p>';
  const r = await api('/api/updater/check', {method:'POST'});
  if (r.ok) {
    toast(r.message || 'Check triggered');
    // Poll at 2 s, 5 s, 15 s, 30 s — the updater wakes within ~1 s via SIGUSR1
    [2000, 5000, 15000, 30000].forEach(d => setTimeout(loadUpdaterStatus, d));
  } else {
    toast(r.detail || 'Check failed', 'error');
  }
}

async function triggerUpdate() {
  const el = document.getElementById('opt-updater-status');
  if (el) el.innerHTML = '<p style="color:var(--text-muted);font-size:.85em;padding:8px 0">⏳ Downloading update…</p>';
  const r = await api('/api/updater/update', {method:'POST'});
  if (r.ok) {
    toast(r.message || 'Update triggered — affected agents restarting…', 'info');
    // Poll at 3 s, 8 s, 20 s, 45 s — give agents time to restart
    [3000, 8000, 20000, 45000].forEach(d => setTimeout(loadUpdaterStatus, d));
  } else {
    toast(r.detail || 'Update failed', 'error');
  }
}

// ── Nuke data ─────────────────────────────────────────────────────────────────
async function nukeData() {
  const confirm_val = document.getElementById('nuke-confirm').value;
  const el = document.getElementById('nuke-result');
  el.textContent = '⏳ Processing…';
  el.style.color = 'var(--text-muted)';
  const r = await api('/api/settings/nuke', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm: confirm_val})
  });
  if (r.ok) {
    el.style.color = 'var(--success)';
    el.textContent = `✅ Deleted ${r.deleted.length} file(s)${r.deleted.length ? ': ' + r.deleted.join(', ') : ''}`;
    document.getElementById('nuke-confirm').value = '';
    if (r.errors && r.errors.length) {
      el.textContent += ' | Errors: ' + r.errors.join(', ');
      el.style.color = 'var(--warning)';
    }
  } else {
    el.style.color = 'var(--danger)';
    el.textContent = '❌ ' + (r.detail || 'Error');
  }
}

// ── Delete Complete Bot (two-step confirmation) ───────────────────────────────
function deleteBotStep2() {
  const c1 = document.getElementById('uninstall-check1');
  const c2 = document.getElementById('uninstall-check2');
  const el = document.getElementById('uninstall-result');
  if (!c1 || !c2) return;
  if (!c1.checked || !c2.checked) {
    el.style.color = 'var(--danger)';
    el.textContent = '❌ Please tick both checkboxes before continuing.';
    return;
  }
  el.textContent = '';
  document.getElementById('uninstall-step2').style.display = 'block';
  document.getElementById('uninstall-confirm').focus();
}

function deleteBotCancel() {
  document.getElementById('uninstall-step2').style.display = 'none';
  document.getElementById('uninstall-confirm').value = '';
  document.getElementById('uninstall-check1').checked = false;
  document.getElementById('uninstall-check2').checked = false;
  const el = document.getElementById('uninstall-result');
  el.textContent = '';
}

async function deleteBotFinal() {
  const confirm_val = document.getElementById('uninstall-confirm').value;
  const el = document.getElementById('uninstall-result');
  el.style.color = 'var(--text-muted)';
  el.textContent = '⏳ Stopping all agents and removing installation…';
  const r = await api('/api/settings/uninstall', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm: confirm_val})
  });
  if (r.ok) {
    el.style.color = 'var(--success)';
    el.textContent = '✅ AI Employee has been fully uninstalled. You can close this tab.';
    // Disable all further interaction
    document.querySelectorAll('#tab-options button, #tab-options input').forEach(b => b.disabled = true);
  } else {
    el.style.color = 'var(--danger)';
    el.textContent = '❌ ' + (r.detail || 'Uninstall failed');
    document.getElementById('uninstall-confirm').value = '';
  }
}

// Auto-refresh dashboard every 30s (skip when page is hidden)
setInterval(() => { if (!document.hidden && currentTab === 'dashboard') loadDashboard(); }, 30000);
// Auto-refresh doctor panel every 60s when on the dashboard tab
setInterval(() => { if (!document.hidden && currentTab === 'dashboard') loadDoctorPanel(); }, 60000);
// Poll guardrails for pending approvals badge (every 60 seconds, skip when hidden)
setInterval(() => {
  if (document.hidden) return;
  api('/api/guardrails').then(d => {
    const pending = (d.pending || []).length;
    const navBadge = document.getElementById('guardrail-pending-badge');
    if (navBadge) {
      if (pending > 0) { navBadge.textContent = pending; navBadge.style.display = 'inline-block'; }
      else { navBadge.style.display = 'none'; }
    }
  }).catch(() => {});
}, 60000);

// ── Auto-generate scheduler task ID from label ────────────────────────────────
function autoSchedId() {
  const label = document.getElementById('sched-label')?.value || '';
  const idEl = document.getElementById('sched-id');
  if (!idEl || idEl.dataset.manuallySet) return;
  const slug = label.toLowerCase().trim()
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, '_')
    .slice(0, 30);
  const ts = Date.now().toString().slice(-4);
  idEl.value = slug ? slug + '_' + ts : '';
}

// ── Assign task to agent from swarm ──────────────────────────────────────────
function assignTaskToAgent(agentId) {
  const tasksBtn = document.querySelector('nav button[onclick*="tasks"]');
  if (tasksBtn) tasksBtn.click();
  setTimeout(() => {
    const taskInput = document.getElementById('task-input');
    if (taskInput) {
      taskInput.focus();
      taskInput.placeholder = `Describe what you want ${agentId} to do…`;
    }
    if (typeof showManualAgentPicker === 'function') showManualAgentPicker();
    setTimeout(() => {
      const checkbox = document.querySelector(`[data-agent-id="${agentId}"]`);
      if (checkbox) checkbox.click();
    }, 300);
  }, 200);
}

// ── Server-Sent Events for real-time updates ──────────────────────────────────
let _sseRetries = 0;
function connectSSE() {
  if (typeof EventSource === 'undefined') return;
  const es = new EventSource('/api/events');
  es.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data);
      if (typeof d.running === 'number') {
        animateCount('stat-running', d.running);
        const headerSub = document.getElementById('header-sub');
        if (headerSub) headerSub.textContent = `${d.running} agents running`;
      }
      if (d.active_task) {
        const el = document.getElementById('sys-control-sub');
        if (el) el.textContent = `◈ Active task: ${d.active_task}`;
      }
    } catch {}
    _sseRetries = 0;
  };
  es.onerror = () => {
    es.close();
    _sseRetries++;
    // Server is unreachable — immediately reset displayed counts to zero
    animateCount('stat-running', 0);
    const headerSub = document.getElementById('header-sub');
    if (headerSub) headerSub.textContent = 'System offline';
    const sysRing = document.getElementById('sys-ring');
    if (sysRing) sysRing.classList.add('offline');
    const sysControlSub = document.getElementById('sys-control-sub');
    if (sysControlSub) sysControlSub.textContent = 'System offline — server is not reachable';
    if (_sseRetries < 10) setTimeout(connectSSE, Math.min(5000 * _sseRetries, 30000));
  };
}
connectSSE();

// ── BLACKLIGHT ───────────────────────────────────────────────────────────────
const BL_REFRESH_INTERVAL_MS = 8000;  // auto-refresh rate while BLACKLIGHT is running
let _blAutoRefreshTimer = null;

function _blSyncUI(running, goal) {
  // status dot + label (in BLACKLIGHT tab header)
  const dot = document.getElementById('bl-status-dot');
  if (dot) {
    dot.style.background = running ? '#00f0ff' : '#6b7280';
    dot.style.boxShadow = running ? '0 0 12px rgba(0,240,255,.8),0 0 24px rgba(0,240,255,.4)' : 'none';
  }
  const lbl = document.getElementById('bl-status-label');
  if (lbl) { lbl.textContent = running ? '⚡ RUNNING' : 'IDLE'; lbl.style.color = running ? '#00f0ff' : 'rgba(0,240,255,.6)'; }

  // tab toggle
  const tabToggle = document.getElementById('bl-toggle');
  if (tabToggle) tabToggle.checked = running;
  const tabLbl = document.getElementById('bl-toggle-label');
  if (tabLbl) { tabLbl.textContent = running ? 'ON' : 'OFF'; tabLbl.style.color = running ? '#00f0ff' : 'var(--text-muted)'; }

  // dashboard toggle
  const dashToggle = document.getElementById('dash-bl-toggle');
  if (dashToggle) dashToggle.checked = running;
  const dashSub = document.getElementById('dash-bl-sublabel');
  if (dashSub) dashSub.textContent = running ? `⚡ Running — ${goal || 'no goal set'}` : 'Autonomous agent — idle';

  // goal input (pre-fill if known)
  const goalEl = document.getElementById('bl-goal-input');
  if (goalEl && goal && !goalEl.value) goalEl.value = goal;
  const dashGoalEl = document.getElementById('dash-bl-goal-input');
  if (dashGoalEl && goal && !dashGoalEl.value) dashGoalEl.value = goal;

  // auto-refresh timer
  if (running && !_blAutoRefreshTimer) {
    _blAutoRefreshTimer = setInterval(() => { blRefresh(); blLoadLogs(); }, BL_REFRESH_INTERVAL_MS);
  } else if (!running && _blAutoRefreshTimer) {
    clearInterval(_blAutoRefreshTimer);
    _blAutoRefreshTimer = null;
  }
}

async function blRefresh() {
  const d = await api('/api/blacklight/status');
  const running = d.running || false;
  document.getElementById('bl-stat-cycle').textContent   = d.cycle   || 0;
  document.getElementById('bl-stat-opps').textContent    = d.opportunities_found || 0;
  document.getElementById('bl-stat-actions').textContent = d.actions_taken || 0;
  const last = d.last_activity ? d.last_activity.replace('T',' ').replace('Z','') : '—';
  document.getElementById('bl-stat-last').textContent    = last;
  _blSyncUI(running, d.goal || '');
}

async function blLoadLogs() {
  const entries = await api('/api/blacklight/logs?limit=80');
  const el = document.getElementById('bl-log');
  if (!el) return;
  if (!entries || !entries.length) {
    el.innerHTML = '<span style="color:#6b7280">No activity yet — start BLACKLIGHT to see the live log.</span>';
    return;
  }
  const _levelColor = { system:'#00d4e8', cycle:'#00f0ff', info:'#67e8f9', action:'#4ade80',
                        result:'#facc15', eval:'#fb923c', improve:'#f472b6',
                        warn:'#fbbf24', error:'#f87171' };
  const html = entries.slice().reverse().map(e => {
    const col   = _levelColor[e.level] || '#c9d1d9';
    const ts    = (e.ts || '').replace('T',' ').replace('Z','');
    const badge = `<span style="color:${col};font-weight:600;min-width:54px;display:inline-block">[${e.level || 'info'}]</span>`;
    const msg   = (e.msg || '').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return `<div>${badge} <span style="color:#6b7280;font-size:.72em">${ts}</span> ${msg}</div>`;
  }).join('');
  el.innerHTML = html;
}

async function blToggle(on) {
  // Sync both toggles immediately so neither feels laggy
  _blSyncUI(on, document.getElementById('bl-goal-input')?.value || document.getElementById('dash-bl-goal-input')?.value || '');

  if (on) {
    const goal = (document.getElementById('bl-goal-input')?.value || document.getElementById('dash-bl-goal-input')?.value || '').trim();
    if (!goal) {
      // Determine which context triggered the toggle to give a useful hint
      const onDash = !!document.getElementById('dash-bl-goal-input');
      toast(onDash ? 'Set a goal first — type one in the goal field below the BLACKLIGHT toggle' : 'Set a goal first — type one in the goal field above the start button', 'error');
      _blSyncUI(false, '');
      return;
    }
    const r = await api('/api/blacklight/start', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({goal})});
    if (r.ok) {
      toast('⚡ BLACKLIGHT started!');
      blRefresh();
      blLoadLogs();
    } else {
      toast(r.message || 'Failed to start', 'error');
      _blSyncUI(false, '');
    }
  } else {
    const r = await api('/api/blacklight/stop', {method:'POST'});
    toast(r.ok ? '■ BLACKLIGHT stopped' : (r.message || 'Stop failed'), r.ok ? 'info' : 'error');
    setTimeout(blRefresh, 800);
  }
}

async function hermesToggle(on) {
  const r = await api('/api/agents/' + (on ? 'start' : 'stop'), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({bot: 'hermes-agent'})
  });
  if (r.ok) {
    toast(on ? '🧠 Hermes Agent started' : '■ Hermes Agent stopped', on ? 'success' : 'info');
    const sub = document.getElementById('dash-hermes-sublabel');
    if (sub) sub.textContent = on ? '🧠 Running — ready for tasks' : 'Reasoning agent — stopped';
    _updateChatHermesStatus(on);
  } else {
    toast(r.message || (on ? 'Failed to start Hermes' : 'Failed to stop Hermes'), 'error');
    const el = document.getElementById('dash-hermes-toggle');
    if (el) el.checked = !on;
  }
}

function _updateChatHermesStatus(running) {
  const dot = document.getElementById('chat-hermes-dot');
  const lbl = document.getElementById('chat-hermes-label');
  if (dot) dot.style.background = running ? '#4ade80' : '#6b7280';
  if (lbl) lbl.textContent = running ? 'Hermes ● online' : 'Hermes ○ offline';
  const wrap = document.getElementById('chat-hermes-status');
  if (wrap) wrap.style.borderColor = running ? 'rgba(74,222,128,.4)' : 'rgba(148,163,184,.2)';
}

// ── ASCEND FORGE JS ───────────────────────────────────────────────────────────
const RISK_COLORS = {LOW:'#4ade80', MEDIUM:'#fb923c', HIGH:'#ef4444'};
const RISK_BG    = {LOW:'rgba(74,222,128,.12)', MEDIUM:'rgba(251,146,60,.12)', HIGH:'rgba(239,68,68,.12)'};
const STATUS_EMOJI = {pending:'⏳', approved:'✅', rejected:'❌', rolled_back:'↩️', failed:'💥'};

async function afRefresh() {
  try {
    const s = await api('/api/ascend/status');
    // Mode badge
    const badge = document.getElementById('af-mode-badge');
    if (badge) { badge.textContent = s.mode || 'AUTO'; }
    // Stats
    const set = (id, v) => { const el=document.getElementById(id); if(el) el.textContent=v; };
    set('af-stat-pending',  s.pending_count  || 0);
    set('af-stat-approved', s.patches_approved || 0);
    set('af-stat-rejected', s.patches_rejected || 0);
    set('af-stat-total',    s.total_patches   || 0);
    // Activity inline labels
    const act = document.getElementById('af-current-activity');
    if (act) act.textContent = 'Activity: ' + (s.current_activity || 'idle');
    const tgt = document.getElementById('af-current-target');
    if (tgt) tgt.textContent = 'Target: ' + (s.current_target || '—');
    // Highlight active mode button
    ['GENERAL','MONEY','AUTO'].forEach(m => {
      const btn = document.getElementById('af-mode-'+m.toLowerCase());
      if (btn) { btn.classList.toggle('active', s.mode === m); }
    });
    // Auto-approve toggle
    const aa = document.getElementById('af-auto-approve');
    if (aa) aa.checked = !!s.auto_approve_low;
    // Activity feed — premium log style
    const logEl = document.getElementById('af-activity-log');
    if (logEl && Array.isArray(s.activity) && s.activity.length) {
      const levelDot = {warn:'#fb923c', error:'#ef4444', success:'#4ade80'};
      const levelColor = {warn:'#fb923c', error:'#ef4444', success:'#4ade80'};
      logEl.innerHTML = s.activity.map(e => {
        const dot = levelDot[e.level] || 'rgba(217,119,6,.5)';
        const col = levelColor[e.level] || '#d4b483';
        const ts  = (e.ts||'').slice(11,19);
        return `<div style="display:flex;align-items:flex-start;gap:8px;padding:3px 0;border-bottom:1px solid rgba(217,119,6,.06)">
          <span style="width:6px;height:6px;border-radius:50%;background:${dot};margin-top:5px;flex-shrink:0;box-shadow:0 0 5px ${dot}"></span>
          <span style="color:rgba(217,119,6,.5);flex-shrink:0">${ts}</span>
          <span style="color:${col};flex:1;word-break:break-word">${escHtml(e.msg)}</span>
        </div>`;
      }).join('');
      logEl.scrollTop = logEl.scrollHeight;
    }
  } catch(e) { console.warn('afRefresh', e); }
}

async function afSetMode(mode) {
  const r = await api('/api/ascend/mode', {method:'POST',body:{mode}});
  if (r.ok) { toast(`⚙️ Mode: ${mode}`); afRefresh(); }
  else toast(r.detail || 'Failed', 'error');
}

async function afScan() {
  toast('🔍 Scanning system…', 'info');
  const r = await api('/api/ascend/scan', {method:'POST'});
  if (r.ok) {
    toast(`✅ Scan complete — ${(r.patches||[]).length} patch(es) queued`);
    afLoadPatches(); afRefresh();
  } else { toast(r.detail || 'Scan failed', 'error'); }
}

async function afLoadPatches() {
  try {
    const patches = await api('/api/ascend/patches');
    const el = document.getElementById('af-patches-list');
    if (!el) return;
    if (!Array.isArray(patches) || !patches.length) {
      el.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:36px 20px;gap:12px;opacity:.6">
        <div style="font-size:2.2em">📋</div>
        <div style="font-size:.88em;color:var(--text-muted);text-align:center">No pending patches — run a scan to find improvements.</div>
        <button onclick="afScan()" class="btn btn-gold btn-sm" style="margin-top:4px">🔍 Run Scan Now</button>
      </div>`;
      return;
    }
    el.innerHTML = patches.map(p => {
      const rc = RISK_COLORS[p.risk_level] || '#6b7280';
      const rb = RISK_BG[p.risk_level]    || 'rgba(107,114,128,.1)';
      return `<div class="af-patch-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
          <span class="af-risk-badge" style="background:${rb};color:${rc};border:1px solid ${rc}40">${escHtml(p.risk_level||'?')}</span>
          <span style="font-size:.78em;color:#d97706;font-weight:600">${escHtml(p.patch_type||'')}</span>
          <span style="font-size:.75em;color:rgba(217,119,6,.45);margin-left:auto">${(p.timestamp||'').slice(0,16)}</span>
        </div>
        <div style="font-size:.9em;font-weight:700;color:#fef3c7;margin-bottom:4px">${escHtml(p.description)}</div>
        <div style="font-size:.79em;color:rgba(217,119,6,.6);margin-bottom:10px;line-height:1.5">${escHtml(p.reason||'')}</div>
        ${p.diff_preview ? `<details style="margin-bottom:10px"><summary style="font-size:.76em;cursor:pointer;color:rgba(217,119,6,.55);user-select:none">▶ View diff / code changes</summary><pre style="font-size:.73em;background:rgba(6,3,0,.95);border:1px solid rgba(217,119,6,.15);border-radius:6px;padding:10px;overflow-x:auto;color:#c9d1d9;margin-top:6px;line-height:1.5">${escHtml(p.diff_preview)}</pre></details>` : ''}
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn-approve-sm" onclick="afApprove('${p.patch_id}')">✅ Approve</button>
          <button class="btn-reject-sm" onclick="afReject('${p.patch_id}')">❌ Reject</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.warn('afLoadPatches', e); }
}

async function afApprove(id) {
  const r = await api(`/api/ascend/patches/${id}/approve`, {method:'POST'});
  if (r.ok) { toast('✅ Patch approved'); afLoadPatches(); afRefresh(); }
  else toast(r.detail || 'Failed', 'error');
}
async function afReject(id) {
  const r = await api(`/api/ascend/patches/${id}/reject`, {method:'POST'});
  if (r.ok) { toast('❌ Patch rejected'); afLoadPatches(); afRefresh(); }
  else toast(r.detail || 'Failed', 'error');
}
async function afRollback(id) {
  if (!confirm('Roll back this patch?')) return;
  const r = await api(`/api/ascend/patches/${id}/rollback`, {method:'POST'});
  if (r.ok) { toast('↩️ Rolled back'); afLoadChangelog(); afRefresh(); }
  else toast(r.detail || 'Failed', 'error');
}

async function afApplyAllLow() {
  const r = await api('/api/ascend/patches');
  const low = (Array.isArray(r)?r:[]).filter(p=>p.risk_level==='LOW');
  if (!low.length) { toast('No LOW-risk patches pending', 'info'); return; }
  for (const p of low) { await api(`/api/ascend/patches/${p.patch_id}/approve`,{method:'POST'}); }
  toast(`✅ Applied ${low.length} LOW-risk patch(es)`);
  afLoadPatches(); afRefresh();
}

async function afCancelAll() {
  if (!confirm('Cancel all pending patches?')) return;
  const r = await api('/api/ascend/patches');
  const pending = Array.isArray(r) ? r : [];
  for (const p of pending) { await api(`/api/ascend/patches/${p.patch_id}/reject`,{method:'POST'}); }
  toast(`🗑 Cancelled ${pending.length} patch(es)`);
  afLoadPatches(); afRefresh();
}

async function afShowPending() {
  afLoadPatches();
  document.getElementById('tab-ascend').scrollIntoView({behavior:'smooth'});
}

async function afLoadChangelog() {
  try {
    const log = await api('/api/ascend/changelog?limit=30');
    const el = document.getElementById('af-changelog');
    if (!el) return;
    if (!Array.isArray(log) || !log.length) {
      el.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:36px 20px;gap:10px;opacity:.55">
        <div style="font-size:2em">📚</div>
        <div style="font-size:.84em;color:var(--text-muted)">No history yet.</div>
      </div>`;
      return;
    }
    el.innerHTML = log.map(p => {
      const emoji = STATUS_EMOJI[p.status] || '?';
      const rc = RISK_COLORS[p.risk_level] || '#6b7280';
      const rb = RISK_BG[p.risk_level]    || 'rgba(107,114,128,.08)';
      const appliedAt = p.applied_timestamp ? `<span style="color:rgba(74,222,128,.6)"> → applied ${p.applied_timestamp.slice(0,16)}</span>` : '';
      return `<div class="af-log-card">
        <div style="display:flex;align-items:center;gap:7px;margin-bottom:6px;flex-wrap:wrap">
          <span style="font-size:1em;line-height:1">${emoji}</span>
          <span class="af-risk-badge" style="background:${rb};color:${rc};border:1px solid ${rc}40">${escHtml(p.risk_level||'?')}</span>
          <span style="font-size:.74em;color:rgba(217,119,6,.55);font-family:var(--mono)">${escHtml((p.patch_id||'').slice(0,14))}</span>
          <span style="font-size:.73em;color:rgba(217,119,6,.4);margin-left:auto">${(p.timestamp||'').slice(0,16)}${appliedAt}</span>
        </div>
        <div style="font-size:.85em;font-weight:700;color:#fef3c7;margin-bottom:3px">${escHtml(p.description)}</div>
        <div style="font-size:.77em;color:rgba(217,119,6,.55);line-height:1.5;margin-bottom:6px">${escHtml(p.reason||'')}</div>
        ${p.diff_preview ? `<details style="margin-bottom:6px"><summary style="font-size:.74em;cursor:pointer;color:rgba(217,119,6,.45);user-select:none">▶ View diff</summary><pre style="font-size:.71em;background:rgba(6,3,0,.95);border:1px solid rgba(217,119,6,.12);border-radius:6px;padding:10px;overflow-x:auto;color:#c9d1d9;margin-top:5px;line-height:1.5">${escHtml(p.diff_preview)}</pre></details>` : ''}
        ${p.status==='approved' ? `<button class="btn-rollback" onclick="afRollback('${p.patch_id}')">↩️ Rollback</button>` : ''}
      </div>`;
    }).join('');
  } catch(e) { console.warn('afLoadChangelog', e); }
}

async function afSetAutoApprove(enabled) {
  const r = await api('/api/ascend/auto-approve', {method:'POST',body:{enabled}});
  if (r.ok) toast(`Auto-approve LOW: ${enabled?'ON':'OFF'}`);
  else toast('Failed', 'error');
}

// ── Ascend Forge Direct Task Assignment ──────────────────────────────────────
let _afTaskTimer = null;

function afFillTask(text) {
  const el = document.getElementById('af-task-input');
  if (el) { el.value = text; el.focus(); }
}

async function afAnalyzeOnly() {
  const input = document.getElementById('af-task-input');
  const task = (input?.value || '').trim();
  if (!task) { toast('Enter a prompt to analyze', 'error'); return; }
  const panel = document.getElementById('af-task-progress-panel');
  const stxt  = document.getElementById('af-task-status-text');
  const pct   = document.getElementById('af-task-pct');
  const desc  = document.getElementById('af-task-desc');
  const res   = document.getElementById('af-task-result');
  if (panel) panel.style.display = 'block';
  if (stxt)  stxt.textContent = '🗺 Analyzing prompt…';
  if (pct)   pct.textContent = '…';
  if (desc)  desc.textContent = task;
  if (res)   { res.style.display = 'none'; res.textContent = ''; }
  try {
    const r = await api('/api/ascend/analyze', {method:'POST', body:{task}});
    if (!r.ok) { toast(r.detail || 'Analysis failed', 'error'); return; }
    const plan = r.plan || {};
    const lines = [];
    lines.push(`📊 Summary: ${plan.summary || task.slice(0,100)}`);
    if (plan.phases && plan.phases.length) {
      lines.push('');
      lines.push('📋 Plan:');
      plan.phases.forEach(ph => {
        lines.push(`  ${ph.name} (Priority: ${ph.priority})`);
        (ph.items || []).slice(0,5).forEach(it => lines.push(`    • ${it}`));
      });
    } else if (plan.actions && plan.actions.length) {
      lines.push('');
      lines.push('📋 Planned Actions:');
      plan.actions.slice(0,8).forEach(a => lines.push(`  • ${a}`));
    }
    if (plan.patch_types && plan.patch_types.length) lines.push(`\n🔧 Improvements: ${plan.patch_types.join(', ')}`);
    if (plan.mentioned_agents && plan.mentioned_agents.length) lines.push(`🤖 Agents: ${plan.mentioned_agents.join(', ')}`);
    if (plan.mentioned_files && plan.mentioned_files.length) lines.push(`📁 Files: ${plan.mentioned_files.join(', ')}`);
    lines.push('');
    lines.push(plan.has_high_risk ? '⚠️ HIGH risk changes detected — review before executing.' : '✅ Plan ready. Click "Send to Ascend Forge" to execute.');
    if (stxt) stxt.textContent = '🗺 Plan generated';
    if (pct)  pct.textContent = '100%';
    if (res) { res.style.display = 'block'; res.style.color = '#fbbf24'; res.textContent = lines.join('\n'); }
  } catch(e) { toast('Analysis error', 'error'); console.warn('afAnalyzeOnly', e); }
}

async function afSendTask() {
  const input = document.getElementById('af-task-input');
  const task = (input?.value || '').trim();
  if (!task) { toast('Enter a task for Ascend Forge', 'error'); return; }
  const panel = document.getElementById('af-task-progress-panel');
  const bar   = document.getElementById('af-task-progress-bar');
  const pct   = document.getElementById('af-task-pct');
  const stxt  = document.getElementById('af-task-status-text');
  const desc  = document.getElementById('af-task-desc');
  const res   = document.getElementById('af-task-result');
  if (panel) { panel.style.display = 'block'; }
  if (bar)   { bar.style.width = '5%'; }
  if (pct)   { pct.textContent = '5%'; }
  if (stxt)  { stxt.textContent = '🔥 Sending task to Ascend Forge…'; }
  if (desc)  { desc.textContent = task; }
  if (res)   { res.style.display = 'none'; res.textContent = ''; }
  const r = await api('/api/ascend/task', {method:'POST', body:{task}});
  if (!r.ok) { toast(r.detail || 'Failed to send task', 'error'); return; }
  toast('🔥 Task sent to Ascend Forge!');
  if (input) input.value = '';
  if (_afTaskTimer) clearInterval(_afTaskTimer);
  _afTaskTimer = setInterval(_afPollTaskProgress, 2500);
}

async function _afPollTaskProgress() {
  const p = await api('/api/ascend/progress');
  const bar  = document.getElementById('af-task-progress-bar');
  const pct  = document.getElementById('af-task-pct');
  const stxt = document.getElementById('af-task-status-text');
  const res  = document.getElementById('af-task-result');
  // Dashboard mini-widget
  const dashBar  = document.getElementById('dash-af-progress-bar');
  const dashPct  = document.getElementById('dash-af-pct-badge');
  const dashSub  = document.getElementById('dash-af-sublabel');
  const dashWrap = document.getElementById('dash-af-progress-wrap');
  const dashTask = document.getElementById('dash-af-task-text');

  const progress = p.progress || 0;
  const status   = p.status || 'idle';
  const pctStr   = progress + '%';

  if (bar)  bar.style.width  = pctStr;
  if (pct)  pct.textContent  = pctStr;
  if (dashBar) dashBar.style.width = pctStr;
  if (dashPct) { dashPct.textContent = pctStr; dashPct.style.display = progress > 0 ? 'inline-block' : 'none'; }
  if (dashWrap) dashWrap.style.display = status === 'running' ? 'block' : 'none';
  if (dashTask) dashTask.textContent = p.task || '';

  const statusMap = {idle:'idle', running:'🔥 Running…', done:'✅ Done', error:'❌ Error'};
  const statusLabel = statusMap[status] || status;
  if (stxt)  stxt.textContent = statusLabel;
  if (dashSub) dashSub.textContent = status === 'running' ? `🔥 ${p.task?.slice(0,40) || 'Running task…'}` : `Self-improver — ${status}`;

  if (status === 'done' || status === 'error') {
    if (_afTaskTimer) { clearInterval(_afTaskTimer); _afTaskTimer = null; }
    if (res) {
      res.style.display = 'block';
      res.style.color = status === 'error' ? '#ef4444' : '#4ade80';
      res.textContent = p.result || '';
    }
  }
}

// Auto-poll Ascend Forge progress on the dashboard widget (skip when hidden)
setInterval(() => { if (!document.hidden && currentTab === 'dashboard') _afPollTaskProgress(); }, 8000);

// ── BLACKLIGHT Direct Task Assignment ────────────────────────────────────────
let _blTaskTimer = null;

function blFillTask(text) {
  const el = document.getElementById('bl-task-input');
  if (el) { el.value = text; el.focus(); }
}

async function blSendTask() {
  const input = document.getElementById('bl-task-input');
  const task  = (input?.value || '').trim();
  if (!task) { toast('Enter a task for BLACKLIGHT', 'error'); return; }
  const panel = document.getElementById('bl-task-progress-panel');
  const bar   = document.getElementById('bl-task-progress-bar');
  const pct   = document.getElementById('bl-task-pct');
  const stxt  = document.getElementById('bl-task-status-text');
  const res   = document.getElementById('bl-task-result');
  if (panel) panel.style.display = 'block';
  if (bar)   bar.style.width = '10%';
  if (pct)   pct.textContent = '10%';
  if (stxt)  stxt.textContent = '⚡ Launching BLACKLIGHT task…';
  if (res)   { res.style.display = 'none'; res.textContent = ''; }
  const r = await api('/api/blacklight/task', {method:'POST', body:{task}});
  if (!r.ok) { toast(r.detail || 'Failed to launch task', 'error'); return; }
  toast('⚡ BLACKLIGHT launched!');
  if (input) input.value = '';
  if (_blTaskTimer) clearInterval(_blTaskTimer);
  _blTaskTimer = setInterval(_blPollTaskProgress, 2500);
}

async function _blPollTaskProgress() {
  const p   = await api('/api/blacklight/task-progress');
  const bar  = document.getElementById('bl-task-progress-bar');
  const pct  = document.getElementById('bl-task-pct');
  const stxt = document.getElementById('bl-task-status-text');
  const res  = document.getElementById('bl-task-result');
  const progress = p.progress || 0;
  const status   = p.status   || 'idle';
  if (bar) bar.style.width = progress + '%';
  if (pct) pct.textContent = progress + '%';
  const statusMap = {idle:'idle', running:'⚡ Launching…', done:'✅ BLACKLIGHT running', error:'❌ Error'};
  if (stxt) stxt.textContent = statusMap[status] || status;
  if (status === 'done' || status === 'error') {
    if (_blTaskTimer) { clearInterval(_blTaskTimer); _blTaskTimer = null; }
    if (res) {
      res.style.display = 'block';
      res.style.color = status === 'error' ? '#ef4444' : '#4ade80';
      res.textContent = p.result || '';
    }
    if (status === 'done') { blRefresh(); blLoadLogs(); }
  }
}

// ── Agent Presets & Bundle-to-Swarm ──────────────────────────────────────────
const AGENT_PRESETS = {
  business_automator: {
    label: '🏢 Business Automator',
    task:  'Automate all business operations: scheduling, admin tasks, CRM updates, and workflow optimization',
    agents: ['orchestrator','scheduler','task-manager','email-agent','crm-agent','workflow-agent','compliance-agent'],
  },
  money_printer: {
    label: '💰 Money Printer',
    task:  'Maximize revenue through upsells, cross-sells, pricing optimization, and monetization strategies',
    agents: ['sales-agent','pricing-agent','upsell-agent','payment-agent','analytics-agent','lead-scorer','deal-matcher'],
  },
  research_team: {
    label: '🔬 Research Team',
    task:  'Deep research: competitive intelligence, market analysis, trend identification, and strategic insights',
    agents: ['research-agent','financial-deepsearch','web-scraper','data-analyst','report-generator','knowledge-base-agent'],
  },
  lead_gen_swarm: {
    label: '🎯 Lead Generation Swarm',
    task:  'Hunt, qualify, score, and convert high-value leads across all channels',
    agents: ['lead-hunter','lead-scorer','outreach-agent','email-agent','call-agent','linkedin-agent','deal-matcher'],
  },
  content_empire: {
    label: '✍️ Content Empire',
    task:  'Create, optimize, and distribute content across all platforms for maximum reach and SEO value',
    agents: ['content-creator','seo-agent','social-media-agent','blog-writer','video-script-agent','email-copywriter'],
  },
  ecom_powerhouse: {
    label: '🛒 E-com Powerhouse',
    task:  'Manage full e-commerce operations: orders, inventory, fulfillment, and customer experience',
    agents: ['ecom-agent','inventory-agent','fulfillment-agent','customer-support-agent','review-agent','pricing-agent'],
  },
  outreach_machine: {
    label: '📣 Outreach Machine',
    task:  'Execute multi-channel outreach via email, phone, social DMs, and LinkedIn at scale',
    agents: ['email-agent','call-agent','linkedin-agent','social-media-agent','outreach-agent','sequence-agent'],
  },
  analytics_squad: {
    label: '📊 Analytics Squad',
    task:  'Generate comprehensive analytics reports, track KPIs, and surface actionable insights',
    agents: ['analytics-agent','data-analyst','report-generator','kpi-tracker','financial-deepsearch','dashboard-agent'],
  },
};

let _swarmSelectedIds = new Set();

function applyAgentPreset(preset) {
  const p = AGENT_PRESETS[preset];
  if (!p) return;
  _swarmSelectedIds = new Set(p.agents);
  const taskEl = document.getElementById('swarm-bundle-task');
  if (taskEl) taskEl.value = p.task;
  const label = document.getElementById('swarm-preset-label');
  if (label) label.textContent = p.label + ' preset loaded';
  renderSwarmAgentGrid();
  toast(`${p.label} preset loaded — click Send Bundle to Swarm`);
}

function renderSwarmAgentGrid() {
  const grid = document.getElementById('swarm-agent-grid');
  if (!grid) return;
  const agents = _allAgents.length ? _allAgents : (window._swarmAgentList || []);
  if (!agents.length) {
    grid.innerHTML = '<div style="color:var(--text-muted);font-size:.84em;grid-column:1/-1">Load the Swarm tab first to see agents here.</div>';
  } else {
    grid.innerHTML = agents.map(a => {
      const sel = _swarmSelectedIds.has(a.id);
      return `<div onclick="swarmToggleAgent('${a.id}')" style="padding:6px 10px;border-radius:8px;cursor:pointer;font-size:.78em;border:1px solid ${sel?'var(--primary)':'rgba(148,163,184,.15)'};background:${sel?'rgba(212,175,55,.12)':'rgba(255,255,255,.03)'};color:${sel?'var(--gold)':'var(--text-muted)'};transition:all .15s;user-select:none">${sel?'✓ ':''}<span>${a.name||a.id}</span></div>`;
    }).join('');
  }
  const countEl = document.getElementById('swarm-agent-count-label');
  if (countEl) countEl.textContent = _swarmSelectedIds.size + ' agent' + (_swarmSelectedIds.size===1?'':'s') + ' selected';
}

function swarmToggleAgent(id) {
  if (_swarmSelectedIds.has(id)) _swarmSelectedIds.delete(id);
  else _swarmSelectedIds.add(id);
  renderSwarmAgentGrid();
}

function swarmSelectAll() {
  (_allAgents.length ? _allAgents : []).forEach(a => _swarmSelectedIds.add(a.id));
  renderSwarmAgentGrid();
}

function swarmClearAll() {
  _swarmSelectedIds.clear();
  renderSwarmAgentGrid();
}

async function sendBundleToSwarm() {
  if (!_swarmSelectedIds.size) { toast('Select at least one agent', 'error'); return; }
  const taskEl  = document.getElementById('swarm-bundle-task');
  const task    = taskEl?.value?.trim() || '';
  const presetEl= document.getElementById('swarm-preset-label');
  const preset  = (presetEl?.textContent || '').replace(' preset loaded','').replace(/^[🏢💰🔬🎯✍️🛒📣📊] /, '');
  const resultEl= document.getElementById('swarm-bundle-result');
  if (resultEl) resultEl.innerHTML = '<span style="color:var(--gold)">Sending bundle to swarm…</span>';
  const btn = document.getElementById('btn-send-bundle');
  if (btn) btn.disabled = true;
  const r = await api('/api/agents/bundle-swarm', {method:'POST', body:{
    agents: [..._swarmSelectedIds],
    task,
    preset,
  }});
  if (btn) btn.disabled = false;
  if (r.ok) {
    toast(`🚀 Bundle sent! ${r.agents} agent${r.agents===1?'':'s'} dispatched to swarm`);
    if (resultEl) resultEl.innerHTML = `<span style="color:#4ade80">✅ Bundle "${escHtml(r.name)}" deployed — ${r.agents} agent(s) ready.</span>`;
    if (taskEl) taskEl.value = '';
    _swarmSelectedIds.clear();
    renderSwarmAgentGrid();
    setTimeout(loadWorkers, 1500);
  } else {
    toast(r.detail || 'Failed to send bundle', 'error');
    if (resultEl) resultEl.innerHTML = `<span style="color:#ef4444">❌ ${escHtml(r.detail||'Failed')}</span>`;
  }
}

// Helper: escape HTML
function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Auto-refresh ASCEND FORGE every 15s when tab is active (skip when hidden)
setInterval(() => { if (!document.hidden && currentTab === 'ascend') { afRefresh(); afLoadPatches(); } }, 15000);

// ═══════════════════════════════════════════════════════════════════════════
// ── BUDGET TAB ──────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

async function loadBudget() {
  try {
    const data = await api('/api/budget/status');
    const agents = Array.isArray(data) ? data : (data.agents || []);
    const totalSpent = agents.reduce((sum, a) => sum + (a.spent_usd || 0), 0);
    const warned = agents.filter(a => a.status === 'warning').length;
    const exceeded = agents.filter(a => a.status === 'exceeded').length;
    document.getElementById('bud-total-spent').textContent = '$' + totalSpent.toFixed(4);
    document.getElementById('bud-agents-warn').textContent = warned;
    document.getElementById('bud-agents-exceeded').textContent = exceeded;
    document.getElementById('bud-agents-tracked').textContent = agents.length;
    const el = document.getElementById('budget-agents-list');
    if (!agents.length) {
      el.innerHTML = '<div class="empty"><div class="icon">💰</div><p>No agents tracked yet. Run a task to see spending.</p></div>';
      return;
    }
    const statusColor = {ok:'#34d399', warning:'#f59e0b', exceeded:'#ef4444'};
    el.innerHTML = agents.map(a => {
      const col = statusColor[a.status] || '#34d399';
      const pct = Math.min(100, Math.round((a.spent_usd / (a.budget_usd || 10)) * 100));
      return `<div style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <div style="font-weight:600;font-size:.9em"><code>${escHtml(a.agent_id)}</code></div>
          <div style="font-size:.82em;color:${col};font-weight:600">${escHtml(a.status)}</div>
        </div>
        <div style="background:var(--surface2);border-radius:4px;height:6px;margin-bottom:6px">
          <div style="background:${col};width:${pct}%;height:100%;border-radius:4px;transition:width .3s"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:.78em;color:var(--text-muted)">
          <span>$${(a.spent_usd||0).toFixed(4)} spent</span>
          <span>Budget: $${(a.budget_usd||10).toFixed(2)}</span>
          <span>${pct}%</span>
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.warn('loadBudget', e); }
}

async function setBudget() {
  const agent_id = document.getElementById('bud-agent-id').value.trim();
  const monthly_budget_usd = parseFloat(document.getElementById('bud-amount').value);
  if (!agent_id || isNaN(monthly_budget_usd)) { toast('Fill in agent ID and budget amount', 'error'); return; }
  const r = await api('/api/budget/set', {method:'POST', body:{agent_id, monthly_budget_usd}});
  if (r.ok) { toast(`✅ Budget set: ${agent_id} = $${monthly_budget_usd}/month`); loadBudget(); }
  else toast(r.detail || 'Error', 'error');
}

async function resetBudget() {
  const agent_id = document.getElementById('bud-agent-id').value.trim();
  if (!agent_id) { toast('Enter agent ID to reset', 'error'); return; }
  if (!confirm(`Reset usage for ${agent_id}?`)) return;
  const r = await api(`/api/budget/reset/${encodeURIComponent(agent_id)}`, {method:'POST'});
  if (r.ok) { toast(`↺ Usage reset for ${agent_id}`); loadBudget(); }
  else toast(r.detail || 'Error', 'error');
}

async function recordBudgetUsage() {
  const agent_id = document.getElementById('bud-rec-agent').value.trim();
  const model = document.getElementById('bud-rec-model').value.trim() || 'gpt-4o';
  const input_tokens = parseInt(document.getElementById('bud-rec-in').value) || 0;
  const output_tokens = parseInt(document.getElementById('bud-rec-out').value) || 0;
  if (!agent_id) { toast('Enter agent ID', 'error'); return; }
  const r = await api('/api/budget/record', {method:'POST', body:{agent_id, model, input_tokens, output_tokens}});
  if (r.ok) { toast(`📥 Usage recorded for ${agent_id}`); loadBudget(); }
  else toast(r.detail || 'Error', 'error');
}

// ═══════════════════════════════════════════════════════════════════════════
// ── ORG CHART TAB ────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

async function loadOrg() {
  try {
    const d = await api('/api/org/chart');
    const roles = d.roles || [];
    const el = document.getElementById('org-chart-tree');
    if (!roles.length) {
      el.innerHTML = '<div class="empty"><div class="icon">🏢</div><p>No roles defined yet.</p></div>';
      return;
    }
    // Build tree map
    const byId = {};
    roles.forEach(r => { byId[r.role_id] = r; });
    const roots = roles.filter(r => !r.reports_to);
    function renderRole(role, depth=0) {
      const indent = depth * 20;
      const children = roles.filter(r => r.reports_to === role.role_id);
      return `<div style="margin-left:${indent}px;border-left:${depth>0?'2px solid var(--border)':'none'};padding-left:${depth>0?'10px':'0'};margin-bottom:8px">
        <div style="background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;display:flex;justify-content:space-between;align-items:center">
          <div>
            <div style="font-weight:600;font-size:.9em">${escHtml(role.title)}</div>
            <div style="font-size:.78em;color:var(--text-muted)"><code>${escHtml(role.role_id)}</code>${role.agent_id ? ` → <span style="color:var(--primary)">${escHtml(role.agent_id)}</span>` : ' <em>unassigned</em>'}</div>
            ${role.description ? `<div style="font-size:.77em;color:var(--text-secondary);margin-top:3px">${escHtml(role.description)}</div>` : ''}
          </div>
          <button class="btn btn-danger btn-sm" onclick="deleteOrgRole('${jsEsc(role.role_id)}')">🗑</button>
        </div>
        ${children.map(c => renderRole(c, depth+1)).join('')}
      </div>`;
    }
    el.innerHTML = roots.map(r => renderRole(r)).join('') ||
      '<div class="empty"><p>Add roles using the form →</p></div>';
  } catch(e) { console.warn('loadOrg', e); }
}

async function upsertOrgRole() {
  const role_id = document.getElementById('org-role-id').value.trim();
  const title   = document.getElementById('org-role-title').value.trim();
  const description = document.getElementById('org-role-desc').value.trim();
  const reports_to = document.getElementById('org-role-reports').value.trim() || null;
  const agent_id = document.getElementById('org-role-agent').value.trim() || null;
  if (!role_id || !title) { toast('Role ID and Title are required', 'error'); return; }
  const r = await api('/api/org/roles', {method:'POST', body:{role_id, title, description, reports_to, agent_id}});
  if (r.ok) { toast(`✅ Role '${title}' saved`); loadOrg(); }
  else toast(r.detail || 'Error saving role', 'error');
}

async function deleteOrgRole(role_id) {
  if (!confirm(`Delete role '${role_id}'?`)) return;
  const r = await api(`/api/org/roles/${encodeURIComponent(role_id)}`, {method:'DELETE'});
  if (r.ok) { toast('🗑 Role deleted'); loadOrg(); }
  else toast(r.detail || 'Error', 'error');
}

async function delegateOrgTask() {
  const from_role = document.getElementById('org-del-from').value.trim();
  const to_role   = document.getElementById('org-del-to').value.trim();
  const task      = document.getElementById('org-del-task').value.trim();
  if (!from_role || !to_role || !task) { toast('Fill in all delegation fields', 'error'); return; }
  const r = await api('/api/org/delegate', {method:'POST', body:{from_role, to_role, task}});
  if (r.ok) { toast(`✅ Delegated from ${from_role} → ${to_role}`); loadOrg(); }
  else toast(r.detail || 'Error', 'error');
}

async function loadOrgAdapters() {
  try {
    const adapters = await api('/api/org/adapters') || [];
    const el = document.getElementById('org-adapters-list');
    if (!Array.isArray(adapters) || !adapters.length) {
      el.innerHTML = '<div class="empty"><div class="icon">🔌</div><p>No adapters. Register a BYOA agent below.</p></div>';
      return;
    }
    el.innerHTML = adapters.map(a => `<div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--border)">
      <div>
        <span style="font-weight:600">${escHtml(a.name)}</span>
        <code style="font-size:.75em;margin-left:6px;color:var(--text-muted)">${escHtml(a.adapter_id)}</code>
        <span style="font-size:.73em;margin-left:6px;color:var(--text-muted)">${escHtml(a.type)}</span>
      </div>
      <button class="btn btn-danger btn-sm" onclick="deregisterOrgAdapter('${jsEsc(a.adapter_id)}')">🗑</button>
    </div>`).join('');
  } catch(e) { console.warn('loadOrgAdapters', e); }
}

async function registerOrgAdapter() {
  const adapter_id = document.getElementById('org-adp-id').value.trim();
  const name = document.getElementById('org-adp-name').value.trim();
  if (!adapter_id || !name) { toast('Adapter ID and Name required', 'error'); return; }
  const r = await api('/api/org/adapters', {method:'POST', body:{adapter_id, name}});
  if (r.ok) { toast('🔌 Adapter registered'); loadOrgAdapters(); }
  else toast(r.detail || 'Error', 'error');
}

async function deregisterOrgAdapter(adapter_id) {
  if (!confirm(`Remove adapter '${adapter_id}'?`)) return;
  const r = await api(`/api/org/adapters/${encodeURIComponent(adapter_id)}`, {method:'DELETE'});
  if (r.ok) { toast('Adapter removed'); loadOrgAdapters(); }
  else toast(r.detail || 'Error', 'error');
}

// ═══════════════════════════════════════════════════════════════════════════
// ── GOALS TAB ────────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

async function loadGoals() {
  try {
    const [company, projects] = await Promise.all([
      api('/api/goals/company'),
      api('/api/goals/projects'),
    ]);
    const mission = company.mission || '';
    const vision  = company.vision  || '';
    document.getElementById('goals-mission-display').innerHTML = mission
      ? `<div style="font-weight:600;color:var(--text)">${escHtml(mission)}</div>${vision ? `<div style="font-size:.82em;color:var(--text-muted);margin-top:4px">${escHtml(vision)}</div>` : ''}`
      : '<em style="color:var(--text-muted)">No mission set.</em>';
    document.getElementById('goals-mission-input').value = mission;
    document.getElementById('goals-vision-input').value = vision;
    const el = document.getElementById('goals-projects-list');
    const plist = Array.isArray(projects) ? projects : (projects.projects || []);
    if (!plist.length) {
      el.innerHTML = '<div class="empty"><div class="icon">📁</div><p>No projects yet.</p></div>';
      return;
    }
    const pri = {high:'🔴', medium:'🟡', low:'🟢'};
    el.innerHTML = plist.map(p => `<div style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div style="flex:1">
          <div style="font-weight:600;font-size:.9em">${pri[p.priority]||'🟡'} ${escHtml(p.name)}</div>
          <div style="font-size:.82em;color:var(--text-secondary);margin:3px 0">${escHtml(p.goal)}</div>
          ${p.description ? `<div style="font-size:.77em;color:var(--text-muted)">${escHtml(p.description)}</div>` : ''}
        </div>
        <button class="btn btn-danger btn-sm" onclick="deleteGoalProject('${jsEsc(p.project_id)}')">🗑</button>
      </div>
    </div>`).join('');
  } catch(e) { console.warn('loadGoals', e); }
}

async function saveCompanyMission() {
  const mission = document.getElementById('goals-mission-input').value.trim();
  const vision = document.getElementById('goals-vision-input').value.trim();
  if (!mission) { toast('Mission is required', 'error'); return; }
  const r = await api('/api/goals/company', {method:'POST', body:{mission, vision}});
  if (r.ok) { toast('🎯 Mission saved!'); loadGoals(); }
  else toast(r.detail || 'Error', 'error');
}

async function addGoalProject() {
  const name = document.getElementById('goals-proj-name').value.trim();
  const goal = document.getElementById('goals-proj-goal').value.trim();
  const description = document.getElementById('goals-proj-desc').value.trim();
  const priority = document.getElementById('goals-proj-priority').value;
  if (!name || !goal) { toast('Name and Goal are required', 'error'); return; }
  const r = await api('/api/goals/projects', {method:'POST', body:{name, goal, description, priority}});
  if (r.ok) { toast('📁 Project added'); loadGoals(); }
  else toast(r.detail || 'Error', 'error');
}

async function deleteGoalProject(project_id) {
  if (!confirm('Delete this project?')) return;
  const r = await api(`/api/goals/projects/${encodeURIComponent(project_id)}`, {method:'DELETE'});
  if (r.ok) { toast('🗑 Project deleted'); loadGoals(); }
  else toast(r.detail || 'Error', 'error');
}

async function sendCEOMessage() {
  const input = document.getElementById('ceo-chat-input');
  const message = input.value.trim();
  if (!message) return;
  const btn = document.getElementById('ceo-send-btn');
  const log = document.getElementById('ceo-chat-log');
  const status = document.getElementById('ceo-chat-status');
  btn.disabled = true; btn.textContent = '⏳ Sending…';
  status.textContent = 'Routing to CEO agent…';
  input.value = '';
  // Append user message
  log.innerHTML += `<div style="margin-bottom:8px"><span style="color:#f59e0b;font-weight:600">Board → CEO:</span> ${escHtml(message)}</div>`;
  log.scrollTop = log.scrollHeight;
  try {
    const r = await api('/api/ceo/chat', {method:'POST', body:{message}});
    const response = r.response || r.detail || 'No response';
    log.innerHTML += `<div style="margin-bottom:12px;padding-left:12px;border-left:2px solid #f59e0b"><span style="color:#34d399;font-weight:600">CEO → Board:</span><div style="margin-top:3px;white-space:pre-wrap">${escHtml(response)}</div>${r.ticket_id ? `<div style="font-size:.75em;color:var(--text-muted);margin-top:3px">Ticket created: <code>${escHtml(r.ticket_id)}</code></div>` : ''}</div>`;
    log.scrollTop = log.scrollHeight;
    status.textContent = r.goal_context_injected ? '✓ Goal context injected' : '';
  } catch(e) {
    log.innerHTML += `<div style="color:#ef4444">Error: ${escHtml(String(e))}</div>`;
  }
  btn.disabled = false; btn.textContent = '📨 Send';
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TICKETS TAB ──────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

let _activeTicketId = null;

async function loadTickets() {
  try {
    const status = document.getElementById('tkt-filter-status').value;
    const params = status ? `?status=${status}` : '';
    const data = await api('/api/tickets' + params);
    const tickets = Array.isArray(data) ? data : [];
    const total = tickets.length;
    const open = tickets.filter(t => t.status === 'open').length;
    const inprog = tickets.filter(t => t.status === 'in_progress').length;
    const done = tickets.filter(t => t.status === 'done').length;
    document.getElementById('tkt-total').textContent = total;
    document.getElementById('tkt-open').textContent = open;
    document.getElementById('tkt-inprog').textContent = inprog;
    document.getElementById('tkt-done').textContent = done;
    const el = document.getElementById('tickets-list');
    if (!tickets.length) {
      el.innerHTML = '<div class="empty"><div class="icon">🎫</div><p>No tickets. Create one →</p></div>';
      return;
    }
    const statusIcon = {open:'🟡', in_progress:'🔵', blocked:'🔴', done:'✅', cancelled:'⛔'};
    const priColor = {high:'#ef4444', medium:'#f59e0b', low:'#10b981'};
    el.innerHTML = tickets.map(t => {
      const icon = statusIcon[t.status] || '🎫';
      const pc = priColor[t.priority] || '#f59e0b';
      const ts = (t.created_at||'').slice(0,16).replace('T',' ');
      return `<div style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;margin-bottom:8px;cursor:pointer;background:${_activeTicketId===t.ticket_id?'var(--surface2)':'transparent'}" onclick="openTicket('${jsEsc(t.ticket_id)}')">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div style="flex:1">
            <div style="font-size:.88em;font-weight:600">${icon} ${escHtml(t.title)}</div>
            <div style="font-size:.77em;color:var(--text-muted);margin-top:3px">
              <code>${escHtml(t.ticket_id)}</code>
              ${t.agent_id ? ` · ${escHtml(t.agent_id)}` : ''}
              · <span style="color:${pc}">${escHtml(t.priority||'medium')}</span>
              · ${ts}
            </div>
          </div>
          <span style="font-size:.78em;color:var(--text-muted)">${escHtml(t.status)}</span>
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.warn('loadTickets', e); }
}

async function openTicket(ticket_id) {
  _activeTicketId = ticket_id;
  const card = document.getElementById('tkt-detail-card');
  card.style.display = 'block';
  card.scrollIntoView({behavior:'smooth', block:'start'});
  try {
    const t = await api(`/api/tickets/${ticket_id}`);
    const statusOpts = ['open','in_progress','blocked','done','cancelled']
      .map(s => `<option value="${s}"${t.status===s?' selected':''}>${s}</option>`).join('');
    const thread = (t.thread||[]);
    document.getElementById('tkt-detail-body').innerHTML = `
      <div style="margin-bottom:10px">
        <div style="font-weight:700;font-size:.95em;margin-bottom:6px">${escHtml(t.title)}</div>
        <div style="font-size:.82em;color:var(--text-muted);margin-bottom:8px">ID: <code>${escHtml(t.ticket_id)}</code> · Created: ${(t.created_at||'').slice(0,16)}</div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <select id="tkt-status-sel" style="background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);padding:5px 8px;font-size:.82em">${statusOpts}</select>
          <button class="btn btn-primary btn-sm" onclick="updateTicketStatus('${jsEsc(ticket_id)}')">💾 Save Status</button>
        </div>
      </div>
      ${t.description ? `<div style="font-size:.84em;color:var(--text-secondary);margin-bottom:10px">${escHtml(t.description)}</div>` : ''}
      <div style="font-size:.82em;font-weight:600;margin-bottom:6px;color:var(--text-muted)">Thread (${thread.length})</div>
      <div style="max-height:220px;overflow-y:auto;background:var(--bg-deep,#0d1117);border-radius:6px;padding:10px;font-size:.8em;line-height:1.6">
        ${thread.length ? thread.map(c => `<div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid var(--border)">
          <span style="font-weight:600;color:var(--primary)">${escHtml(c.author||'user')}</span>
          <span style="color:var(--text-muted);font-size:.78em;margin-left:6px">${(c.created_at||'').slice(0,16)}</span>
          <div style="margin-top:3px;white-space:pre-wrap">${escHtml(c.body||'')}</div>
        </div>`).join('') : '<span style="color:var(--text-muted)">No comments yet.</span>'}
      </div>`;
    document.getElementById('tkt-comment-input').dataset.ticketId = ticket_id;
    loadTickets();
  } catch(e) { console.warn('openTicket', e); }
}

async function createTicket() {
  const title = document.getElementById('tkt-new-title').value.trim();
  const description = document.getElementById('tkt-new-desc').value.trim();
  const priority = document.getElementById('tkt-new-priority').value;
  const agent_id = document.getElementById('tkt-new-agent').value.trim() || null;
  if (!title) { toast('Ticket title is required', 'error'); return; }
  const r = await api('/api/tickets', {method:'POST', body:{title, description, priority, agent_id, created_by:'user'}});
  if (r.ok || r.ticket_id) {
    toast('🎫 Ticket created!');
    document.getElementById('tkt-new-title').value = '';
    document.getElementById('tkt-new-desc').value = '';
    loadTickets();
  } else toast(r.detail || 'Error', 'error');
}

async function updateTicketStatus(ticket_id) {
  const status = document.getElementById('tkt-status-sel').value;
  const r = await api(`/api/tickets/${ticket_id}`, {method:'PATCH', body:{status, updated_by:'user'}});
  if (r.ok || r.ticket_id) { toast(`✅ Status → ${status}`); loadTickets(); }
  else toast(r.detail || 'Error', 'error');
}

async function addTicketComment() {
  const input = document.getElementById('tkt-comment-input');
  const ticket_id = _activeTicketId || input.dataset.ticketId;
  const body = input.value.trim();
  if (!ticket_id) { toast('Select a ticket first', 'error'); return; }
  if (!body) { toast('Write a comment', 'error'); return; }
  const r = await api(`/api/tickets/${ticket_id}/comment`, {method:'POST', body:{body, author:'user'}});
  if (r.ok || r.comment_id) { toast('💬 Comment posted'); input.value=''; openTicket(ticket_id); }
  else toast(r.detail || 'Error', 'error');
}

async function loadTicketAudit() {
  try {
    const events = await api('/api/tickets/audit/log?limit=30') || [];
    const el = document.getElementById('tickets-audit');
    if (!Array.isArray(events) || !events.length) {
      el.innerHTML = '<div class="empty"><div class="icon">📋</div><p>No audit events yet.</p></div>';
      return;
    }
    const actionIcon = {created:'🆕', status_changed:'🔄', comment_added:'💬'};
    el.innerHTML = events.slice().reverse().slice(0,30).map(e => {
      const icon = actionIcon[e.action] || '📋';
      const ts = (e.ts||'').slice(0,16).replace('T',' ');
      return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:.82em">
        <span>${icon}</span>
        <div style="flex:1"><code>${escHtml(e.ticket_id||'?')}</code> ${escHtml(e.action||'')} ${e.field ? `· ${escHtml(e.field)}: ${escHtml(String(e.old_value||''))}→${escHtml(String(e.new_value||''))}` : ''}</div>
        <span style="font-size:.74em;color:var(--text-muted)">${ts}</span>
      </div>`;
    }).join('');
  } catch(e) { console.warn('loadTicketAudit', e); }
}

// ═══════════════════════════════════════════════════════════════════════════
// ── BOARDROOM TAB (GOVERNANCE) ──────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

async function loadBoardroom() {
  try {
    const [pending, audit] = await Promise.all([
      api('/api/governance/pending'),
      api('/api/governance/audit?limit=30'),
    ]);
    const pList = Array.isArray(pending) ? pending : [];
    const aList = Array.isArray(audit) ? audit : [];
    const approved = aList.filter(e => e.state==='approved').length;
    const rejected = aList.filter(e => e.state==='rejected').length;
    document.getElementById('gov-pending').textContent = pList.length;
    document.getElementById('gov-approved').textContent = approved;
    document.getElementById('gov-rejected').textContent = rejected;
    document.getElementById('gov-total').textContent = aList.length;
    // Banner
    const banner = document.getElementById('gov-pending-banner');
    if (pList.length > 0) {
      banner.style.display = 'flex';
      banner.innerHTML = `<span style="font-size:1.2em">⚠️</span> <strong>${pList.length} action${pList.length!==1?'s':''} pending board approval.</strong> Review below.`;
    } else {
      banner.style.display = 'none';
    }
    // Pending list
    const pEl = document.getElementById('gov-pending-list');
    if (!pList.length) {
      pEl.innerHTML = '<div class="empty"><div class="icon">✅</div><p>No pending approvals.</p></div>';
    } else {
      const riskCol = {critical:'#ef4444', high:'#ef4444', medium:'#f59e0b', low:'#10b981'};
      pEl.innerHTML = pList.map(a => {
        const col = riskCol[a.risk_level] || '#f59e0b';
        return `<div style="border:1px solid ${col};border-radius:var(--radius-sm);padding:12px;margin-bottom:10px;background:var(--surface2)">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
            <div style="flex:1">
              <div style="font-size:.88em;font-weight:600">${escHtml(a.action)}</div>
              <div style="font-size:.8em;color:var(--text-secondary);margin:3px 0">${escHtml(a.description||'')}</div>
              <div style="font-size:.77em;color:var(--text-muted)">Agent: <code>${escHtml(a.agent_id||'?')}</code> · Risk: <span style="color:${col};font-weight:600">${escHtml(a.risk_level||'medium')}</span></div>
            </div>
            <div style="display:flex;gap:5px;flex-shrink:0">
              <button class="btn btn-success btn-sm" onclick="govApprove('${jsEsc(a.action_id)}')">✅ Approve</button>
              <button class="btn btn-danger btn-sm" onclick="govReject('${jsEsc(a.action_id)}')">🚫 Reject</button>
            </div>
          </div>
        </div>`;
      }).join('');
    }
    // Audit list
    const aEl = document.getElementById('gov-audit-list');
    const stateIcon = {approved:'✅', rejected:'🚫', auto_approved:'✔️', pending:'⏳'};
    aEl.innerHTML = aList.slice().reverse().slice(0,20).map(e => {
      const icon = stateIcon[e.state] || '📋';
      const ts = (e.decided_at||e.requested_at||'').slice(0,16).replace('T',' ');
      return `<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--border);font-size:.82em">
        <span>${icon}</span>
        <div style="flex:1"><code>${escHtml(e.agent_id||'?')}</code> · ${escHtml(e.action||'')} <span style="color:var(--text-muted)">· ${escHtml(e.state||'')}</span></div>
        <span style="font-size:.74em;color:var(--text-muted)">${ts}</span>
      </div>`;
    }).join('') || '<div class="empty"><div class="icon">📋</div><p>No audit events.</p></div>';
  } catch(e) { console.warn('loadBoardroom', e); }
}

async function govApprove(action_id) {
  const r = await api(`/api/governance/${encodeURIComponent(action_id)}/approve`, {method:'POST', body:{decided_by:'board'}});
  if (r.ok || r.action_id) { toast('✅ Action approved'); loadBoardroom(); }
  else toast(r.detail || 'Error', 'error');
}

async function govReject(action_id) {
  const note = prompt('Reason for rejection (optional):') || '';
  const r = await api(`/api/governance/${encodeURIComponent(action_id)}/reject`, {method:'POST', body:{decided_by:'board', note}});
  if (r.ok || r.action_id) { toast('🚫 Action rejected', 'error'); loadBoardroom(); }
  else toast(r.detail || 'Error', 'error');
}

async function govPauseAgent() {
  const agent_id = document.getElementById('gov-agent-ctrl-id').value.trim();
  if (!agent_id) { toast('Enter agent ID', 'error'); return; }
  const reason = prompt(`Reason for pausing ${agent_id}?`) || '';
  const r = await api(`/api/governance/pause/${encodeURIComponent(agent_id)}`, {method:'POST', body:{reason}});
  if (r.ok || r.agent_id) { toast(`⏸ ${agent_id} paused`); document.getElementById('gov-agent-status-display').textContent = `${agent_id} is now paused.`; loadBoardroom(); }
  else toast(r.detail || 'Error', 'error');
}

async function govResumeAgent() {
  const agent_id = document.getElementById('gov-agent-ctrl-id').value.trim();
  if (!agent_id) { toast('Enter agent ID', 'error'); return; }
  const r = await api(`/api/governance/resume/${encodeURIComponent(agent_id)}`, {method:'POST', body:{reason:'Board decision'}});
  if (r.ok || r.agent_id) { toast(`▶️ ${agent_id} resumed`); document.getElementById('gov-agent-status-display').textContent = `${agent_id} is now active.`; loadBoardroom(); }
  else toast(r.detail || 'Error', 'error');
}

async function govTerminateAgent() {
  const agent_id = document.getElementById('gov-agent-ctrl-id').value.trim();
  if (!agent_id) { toast('Enter agent ID', 'error'); return; }
  if (!confirm(`Permanently terminate ${agent_id}? This cannot be undone.`)) return;
  const reason = prompt('Reason for termination:') || 'Board decision';
  const r = await api(`/api/governance/terminate/${encodeURIComponent(agent_id)}`, {method:'POST', body:{reason}});
  if (r.ok || r.agent_id) { toast(`⛔ ${agent_id} terminated`, 'error'); document.getElementById('gov-agent-status-display').textContent = `${agent_id} has been terminated.`; loadBoardroom(); }
  else toast(r.detail || 'Error', 'error');
}

async function govTestAction() {
  const agent_id = document.getElementById('gov-test-agent').value.trim();
  const action = document.getElementById('gov-test-action').value.trim();
  const description = document.getElementById('gov-test-desc').value.trim();
  const risk_level = document.getElementById('gov-test-risk').value;
  if (!agent_id || !action) { toast('Agent ID and Action are required', 'error'); return; }
  const r = await api('/api/governance/request', {method:'POST', body:{agent_id, action, description, risk_level}});
  if (r.ok || r.action_id) {
    const state = r.state || '?';
    toast(`🧪 Action submitted — state: ${state}`, state==='auto_approved'?'success':'warning');
    loadBoardroom();
  } else toast(r.detail || 'Error', 'error');
}

// ═══════════════════════════════════════════════════════════════════════════
// ── COMPANIES TAB ────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

async function loadCompanies() {
  try {
    const [companies, active] = await Promise.all([
      api('/api/companies'),
      api('/api/companies/active'),
    ]);
    const list = Array.isArray(companies) ? companies : [];
    const banner = document.getElementById('companies-active-banner');
    if (active && active.name) {
      banner.style.display = 'block';
      banner.innerHTML = `🏗️ Active company: <strong>${escHtml(active.name)}</strong> <code style="font-size:.8em">${escHtml(active.company_id)}</code>`;
    } else {
      banner.style.display = 'none';
    }
    const el = document.getElementById('companies-list');
    if (!list.length) {
      el.innerHTML = '<div class="empty"><div class="icon">🏗️</div><p>No companies yet.</p></div>';
      return;
    }
    el.innerHTML = list.map(c => {
      const isActive = active && c.company_id === active.company_id;
      return `<div style="border:1px solid ${isActive?'var(--success)':'var(--border)'};border-radius:var(--radius-sm);padding:12px;margin-bottom:8px;background:${isActive?'rgba(52,211,153,.05)':'transparent'}">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <div style="font-weight:600">${escHtml(c.name)} ${isActive?'<span style="font-size:.73em;color:var(--success);margin-left:6px">● ACTIVE</span>':''}</div>
            <div style="font-size:.78em;color:var(--text-muted)"><code>${escHtml(c.company_id)}</code>${c.mission ? ` · ${escHtml(c.mission.slice(0,60))}${c.mission.length>60?'…':''}` : ''}</div>
          </div>
          <div style="display:flex;gap:6px">
            ${!isActive ? `<button class="btn btn-primary btn-sm" onclick="switchCompany('${jsEsc(c.company_id)}')">⚡ Switch</button>` : ''}
            <button class="btn btn-ghost btn-sm" onclick="exportCompanyById('${jsEsc(c.company_id)}')">📤</button>
            ${!isActive ? `<button class="btn btn-danger btn-sm" onclick="deleteCompany('${jsEsc(c.company_id)}')">🗑</button>` : ''}
          </div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.warn('loadCompanies', e); }
}

async function createCompany() {
  const name = document.getElementById('co-new-name').value.trim();
  const mission = document.getElementById('co-new-mission').value.trim();
  const description = document.getElementById('co-new-desc').value.trim();
  if (!name) { toast('Company name is required', 'error'); return; }
  const r = await api('/api/companies', {method:'POST', body:{name, mission, description}});
  if (r.ok || r.company_id) { toast(`🏗️ Company '${name}' created!`); loadCompanies(); }
  else toast(r.detail || 'Error', 'error');
}

async function switchCompany(company_id) {
  const r = await api('/api/companies/switch', {method:'POST', body:{company_id}});
  if (r.ok || r.company_id) { toast(`⚡ Switched to ${company_id}`); loadCompanies(); }
  else toast(r.detail || 'Error', 'error');
}

async function deleteCompany(company_id) {
  if (!confirm(`Delete company '${company_id}'? This is irreversible.`)) return;
  const r = await api(`/api/companies/${encodeURIComponent(company_id)}`, {method:'DELETE'});
  if (r.ok) { toast('🗑 Company deleted'); loadCompanies(); }
  else toast(r.detail || 'Error', 'error');
}

async function exportCompany() {
  const company_id = document.getElementById('co-export-id').value.trim();
  if (!company_id) { toast('Enter company ID to export', 'error'); return; }
  exportCompanyById(company_id);
}

async function exportCompanyById(company_id) {
  const r = await api(`/api/companies/${encodeURIComponent(company_id)}/export`);
  if (r.export_version || r.company) {
    const blob = new Blob([JSON.stringify(r, null, 2)], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `company-${company_id}.json`;
    a.click();
    toast('📤 Exported!');
  } else toast(r.detail || 'Error exporting', 'error');
}

async function importCompany() {
  const raw = document.getElementById('co-import-json').value.trim();
  if (!raw) { toast('Paste JSON template to import', 'error'); return; }
  let template;
  try { template = JSON.parse(raw); } catch { toast('Invalid JSON', 'error'); return; }
  const r = await api('/api/companies/import', {method:'POST', body:template});
  if (r.ok || r.company_id) { toast(`📥 Imported: ${r.name||r.company_id}`); loadCompanies(); }
  else toast(r.detail || 'Error', 'error');
}

// ═══════════════════════════════════════════════════════════════════════════
// ── ARTIFACTS TAB ────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

async function loadArtifacts() {
  try {
    const type = document.getElementById('art-filter-type').value;
    const params = type ? `?artifact_type=${type}` : '';
    const data = await api('/api/artifacts' + params);
    const arts = Array.isArray(data) ? data : [];
    document.getElementById('art-total').textContent = arts.length;
    document.getElementById('art-drafts').textContent = arts.filter(a=>a.status==='draft').length;
    document.getElementById('art-deployed').textContent = arts.filter(a=>a.status==='deployed').length;
    document.getElementById('art-approved').textContent = arts.filter(a=>a.status==='approved').length;
    const el = document.getElementById('artifacts-list');
    if (!arts.length) {
      el.innerHTML = '<div class="empty"><div class="icon">📦</div><p>No artifacts yet.</p></div>';
      return;
    }
    const typeIcon = {code:'💻', report:'📊', campaign:'📣', business_plan:'📋', config:'⚙️', other:'📦'};
    const statCol = {draft:'var(--text-muted)', review:'#f59e0b', approved:'#34d399', deployed:'#38bdf8', archived:'#6b7280'};
    el.innerHTML = arts.map(a => {
      const icon = typeIcon[a.type] || '📦';
      const sc = statCol[a.status] || 'var(--text-muted)';
      const ts = (a.updated_at||'').slice(0,16).replace('T',' ');
      const kb = a.content_length ? `${(a.content_length/1024).toFixed(1)}KB` : '';
      return `<div style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;margin-bottom:8px;cursor:pointer" onclick="openArtifact('${jsEsc(a.artifact_id)}')">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div style="flex:1">
            <div style="font-size:.88em;font-weight:600">${icon} ${escHtml(a.title)}</div>
            <div style="font-size:.77em;color:var(--text-muted);margin-top:2px"><code>${escHtml(a.artifact_id)}</code> · ${escHtml(a.type)} · v${a.version||1} · ${kb}</div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:.78em;color:${sc};font-weight:600">${escHtml(a.status)}</div>
            <div style="font-size:.72em;color:var(--text-muted)">${ts}</div>
          </div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.warn('loadArtifacts', e); }
}

async function openArtifact(artifact_id) {
  const card = document.getElementById('art-detail-card');
  card.style.display = 'block';
  card.scrollIntoView({behavior:'smooth'});
  try {
    const a = await api(`/api/artifacts/${artifact_id}`);
    const statusOpts = ['draft','review','approved','archived']
      .map(s => `<option value="${s}"${a.status===s?' selected':''}>${s}</option>`).join('');
    document.getElementById('art-detail-body').innerHTML = `
      <div style="margin-bottom:10px">
        <div style="font-weight:700">${escHtml(a.title)}</div>
        <div style="font-size:.8em;color:var(--text-muted);margin-bottom:8px"><code>${escHtml(a.artifact_id)}</code> · v${a.version||1} · ${escHtml(a.type)} · ${escHtml(a.status)}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <select id="art-status-sel" style="background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);padding:5px 8px;font-size:.82em">${statusOpts}</select>
          <button class="btn btn-primary btn-sm" onclick="updateArtifactStatus('${jsEsc(artifact_id)}')">💾 Status</button>
          <button class="btn btn-success btn-sm" onclick="deployArtifact('${jsEsc(artifact_id)}')">🚀 Deploy</button>
          <button class="btn btn-danger btn-sm" onclick="deleteArtifact('${jsEsc(artifact_id)}')">🗑 Delete</button>
        </div>
      </div>
      <div style="background:var(--bg-deep,#0d1117);border-radius:6px;padding:12px;max-height:300px;overflow-y:auto">
        <pre style="font-size:.78em;color:#c9d1d9;margin:0;white-space:pre-wrap;word-break:break-word">${escHtml(a.content||'')}</pre>
      </div>`;
  } catch(e) { console.warn('openArtifact', e); }
}

async function createArtifact() {
  const title = document.getElementById('art-new-title').value.trim();
  const type = document.getElementById('art-new-type').value;
  const content = document.getElementById('art-new-content').value.trim();
  if (!title || !content) { toast('Title and content are required', 'error'); return; }
  const r = await api('/api/artifacts', {method:'POST', body:{title, artifact_type:type, content, agent_id:'user'}});
  if (r.ok || r.artifact_id) {
    toast('📦 Artifact created!');
    document.getElementById('art-new-title').value = '';
    document.getElementById('art-new-content').value = '';
    loadArtifacts();
  } else toast(r.detail || 'Error', 'error');
}

async function updateArtifactStatus(artifact_id) {
  const status = document.getElementById('art-status-sel').value;
  const r = await api(`/api/artifacts/${artifact_id}`, {method:'PATCH', body:{status}});
  if (r.ok || r.artifact_id) { toast(`✅ Status → ${status}`); loadArtifacts(); }
  else toast(r.detail || 'Error', 'error');
}

async function deployArtifact(artifact_id) {
  const notes = prompt('Deployment notes (optional):') || '';
  const r = await api(`/api/artifacts/${artifact_id}/deploy`, {method:'POST', body:{deploy_notes:notes}});
  if (r.ok || r.artifact_id) { toast('🚀 Artifact deployed!'); openArtifact(artifact_id); loadArtifacts(); }
  else toast(r.detail || 'Error', 'error');
}

async function deleteArtifact(artifact_id) {
  if (!confirm('Delete this artifact?')) return;
  const r = await api(`/api/artifacts/${artifact_id}`, {method:'DELETE'});
  if (r.ok) { document.getElementById('art-detail-card').style.display='none'; toast('🗑 Artifact deleted'); loadArtifacts(); }
  else toast(r.detail || 'Error', 'error');
}

// ═══════════════════════════════════════════════════════════════════════════
// ── OUTPUTS TAB (Artifacts + Sessions) ───────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function switchOutputTab(tab, btn) {
  document.querySelectorAll('.outputs-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const artPanel = document.getElementById('outputs-artifacts-panel');
  const sesPanel = document.getElementById('outputs-sessions-panel');
  if (artPanel) artPanel.style.display = tab === 'artifacts' ? '' : 'none';
  if (sesPanel) sesPanel.style.display = tab === 'sessions' ? '' : 'none';
  if (tab === 'sessions') loadSessions();
}

async function loadSessions() {
  try {
    const data = await api('/api/sessions');
    const sessions = Array.isArray(data) ? data : (data.sessions || []);
    document.getElementById('ses-total').textContent = sessions.length;
    document.getElementById('ses-active').textContent = sessions.filter(s=>s.status==='active').length;
    document.getElementById('ses-paused').textContent = sessions.filter(s=>s.status==='paused').length;
    document.getElementById('ses-completed').textContent = sessions.filter(s=>s.status==='completed').length;
    const el = document.getElementById('sessions-list');
    if (!sessions.length) {
      el.innerHTML = '<div class="empty"><div class="icon">💾</div><p>No sessions. Agents create sessions automatically when tasks start.</p></div>';
      return;
    }
    const statusIcon = {active:'▶️', paused:'⏸', completed:'✅', abandoned:'🗑'};
    el.innerHTML = sessions.map(s => {
      const icon = statusIcon[s.status] || '💾';
      const ts = (s.updated_at||'').slice(0,16).replace('T',' ');
      return `<div style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;margin-bottom:8px;cursor:pointer" onclick="openSession('${jsEsc(s.session_id)}')">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div style="flex:1">
            <div style="font-size:.88em;font-weight:600">${icon} ${escHtml(s.title||s.session_id)}</div>
            <div style="font-size:.77em;color:var(--text-muted);margin-top:2px"><code>${escHtml(s.session_id)}</code> · ${escHtml(s.agent_id||'?')}</div>
          </div>
          <div style="font-size:.77em;color:var(--text-muted)">${ts}</div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.warn('loadSessions', e); }
}

async function createSession() {
  const agent_id = document.getElementById('ses-new-agent').value.trim();
  const title = document.getElementById('ses-new-title').value.trim();
  const ctxRaw = document.getElementById('ses-new-ctx').value.trim();
  if (!agent_id) { toast('Agent ID is required', 'error'); return; }
  let context = {};
  if (ctxRaw) { try { context = JSON.parse(ctxRaw); } catch { toast('Invalid JSON context', 'error'); return; } }
  const r = await api('/api/sessions', {method:'POST', body:{agent_id, title, context}});
  if (r.ok || r.session_id) { toast('💾 Session created!'); loadSessions(); }
  else toast(r.detail || 'Error', 'error');
}

async function openSession(session_id) {
  const card = document.getElementById('ses-detail-card');
  try {
    const s = await api(`/api/sessions/${session_id}`);
    const checkpoints = s.checkpoints || [];
    const ctx = JSON.stringify(s.context||{}, null, 2);
    document.getElementById('ses-detail-body').innerHTML = `
      <div style="margin-bottom:10px">
        <div style="font-weight:700">${escHtml(s.title||s.session_id)}</div>
        <div style="font-size:.8em;color:var(--text-muted);margin-bottom:8px"><code>${escHtml(s.session_id)}</code> · Agent: <code>${escHtml(s.agent_id)}</code> · Status: ${escHtml(s.status)}</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn btn-success btn-sm" onclick="resumeSession('${jsEsc(session_id)}')">▶️ Resume</button>
          <button class="btn btn-warning btn-sm" onclick="closeSession('${jsEsc(session_id)}')">✅ Close</button>
          <button class="btn btn-ghost btn-sm" onclick="saveCheckpoint('${jsEsc(session_id)}')">📌 Checkpoint</button>
        </div>
      </div>
      <div style="font-size:.82em;font-weight:600;margin-bottom:6px">Context</div>
      <pre style="background:var(--bg-deep,#0d1117);border-radius:6px;padding:10px;font-size:.77em;color:#c9d1d9;max-height:180px;overflow:auto;white-space:pre-wrap">${escHtml(ctx)}</pre>
      ${checkpoints.length ? `<div style="font-size:.82em;font-weight:600;margin:10px 0 6px">Checkpoints (${checkpoints.length})</div>
      ${checkpoints.map(cp => `<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:.8em">
        <span>📌 ${escHtml(cp.label)}</span>
        <div style="display:flex;gap:5px">
          <span style="color:var(--text-muted)">${(cp.created_at||'').slice(0,16)}</span>
          <button class="btn btn-warning btn-sm" onclick="restoreCheckpoint('${jsEsc(session_id)}','${jsEsc(cp.checkpoint_id)}')">↩ Restore</button>
        </div>
      </div>`).join('')}` : ''}`;
    card.scrollIntoView({behavior:'smooth'});
  } catch(e) { console.warn('openSession', e); }
}

async function resumeSession(session_id) {
  const r = await api(`/api/sessions/${session_id}/resume`, {method:'POST'});
  if (r.ok || r.session_id) { toast('▶️ Session resumed'); loadSessions(); }
  else toast(r.detail || 'Error', 'error');
}

async function closeSession(session_id) {
  if (!confirm('Mark this session as completed?')) return;
  const r = await api(`/api/sessions/${session_id}`, {method:'DELETE'});
  if (r.ok) { toast('✅ Session closed'); loadSessions(); document.getElementById('ses-detail-body').innerHTML='<div class="empty"><p>Session closed.</p></div>'; }
  else toast(r.detail || 'Error', 'error');
}

async function saveCheckpoint(session_id) {
  const label = prompt('Checkpoint label (e.g. "After auth module"):');
  if (!label) return;
  const r = await api(`/api/sessions/${session_id}/checkpoint`, {method:'POST', body:{label}});
  if (r.ok || r.checkpoint_id) { toast('📌 Checkpoint saved'); openSession(session_id); }
  else toast(r.detail || 'Error', 'error');
}

async function restoreCheckpoint(session_id, checkpoint_id) {
  if (!confirm('Restore session context to this checkpoint? Current context will be overwritten.')) return;
  const r = await api(`/api/sessions/${session_id}/restore/${checkpoint_id}`, {method:'POST'});
  if (r.ok || r.session_id) { toast('↩ Checkpoint restored'); openSession(session_id); }
  else toast(r.detail || 'Error', 'error');
}

// Auto-refresh new tabs every 30s when active (skip when page is hidden)
setInterval(() => {
  if (document.hidden) return;
  if (currentTab === 'budget') loadBudget();
  if (currentTab === 'boardroom') loadBoardroom();
  if (currentTab === 'tickets') loadTickets();
  if (currentTab === 'artifacts') loadSessions();
  if (currentTab === 'crm') loadCRM();
  if (currentTab === 'email-marketing') loadEmailCampaigns();
  if (currentTab === 'meetings') loadMeetings();
  if (currentTab === 'social') loadSocialPosts();
  if (currentTab === 'financial') { loadInvoices(); loadPL(); }
  if (currentTab === 'competitors') { loadCompetitors(); loadCompetitorAlerts(); }
  if (currentTab === 'content-calendar') loadContentCalendar();
}, 30000);
// ══════════════════════════════════════════════════════════════════
//  FEATURE MODULE JAVASCRIPT
// ══════════════════════════════════════════════════════════════════

// ── CRM ──────────────────────────────────────────────────────────
async function loadCRM() {
  try {
    const [leads, stats] = await Promise.all([api('/api/crm/leads'), api('/api/crm/stats')]);
    document.getElementById('crm-total').textContent = stats.total_leads || 0;
    document.getElementById('crm-won').textContent = stats.by_stage?.won || 0;
    document.getElementById('crm-pipeline-val').textContent = '$' + (stats.pipeline_value || 0).toLocaleString();
    document.getElementById('crm-conv').textContent = (stats.conversion_rate || 0) + '%';
    const el = document.getElementById('crm-leads-list');
    if (!leads.length) { el.innerHTML = '<div class="empty"><div class="icon">🎯</div><p>No leads yet.</p></div>'; return; }
    el.innerHTML = leads.map(l => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
      <div><strong>${l.name}</strong> <span style="font-size:.75em;color:var(--text-muted)">${l.company}</span>
        <br><span style="font-size:.8em;color:var(--text-muted)">${l.email}</span>
        <span style="font-size:.75em;background:var(--surface3);padding:2px 6px;border-radius:4px;margin-left:6px">${l.stage}</span>
        <span style="font-size:.75em;color:var(--gold);margin-left:6px">Score: ${l.score}</span></div>
      <div style="text-align:right">
        <div style="font-size:.9em;font-weight:700;color:var(--green)">$${(l.value||0).toLocaleString()}</div>
        <button class="btn btn-ghost btn-sm" onclick="deleteLead('${l.id}')" style="font-size:.7em;margin-top:4px">🗑</button>
      </div></div>`).join('');
  } catch(e) { console.error('CRM load error', e); }
}
async function addLead() {
  const payload = {
    name: document.getElementById('crm-name').value,
    company: document.getElementById('crm-company').value,
    email: document.getElementById('crm-email').value,
    phone: document.getElementById('crm-phone').value,
    value: parseFloat(document.getElementById('crm-value').value) || 0,
    stage: document.getElementById('crm-stage').value,
    notes: document.getElementById('crm-notes').value,
  };
  if (!payload.name) return showToast('Name is required', 'error');
  await api('/api/crm/leads', 'POST', payload);
  ['crm-name','crm-company','crm-email','crm-phone','crm-value','crm-notes'].forEach(id => { const el = document.getElementById(id); if(el) el.value=''; });
  showToast('Lead added!');
  loadCRM();
}
async function deleteLead(id) {
  if (!confirm('Delete this lead?')) return;
  await api(`/api/crm/leads/${id}`, 'DELETE');
  showToast('Lead deleted');
  loadCRM();
}

// ── Email Marketing ───────────────────────────────────────────────
async function loadEmailCampaigns() {
  try {
    const [campaigns, stats] = await Promise.all([api('/api/email-mkt/campaigns'), api('/api/email-mkt/stats')]);
    document.getElementById('em-campaigns').textContent = stats.total_campaigns || 0;
    document.getElementById('em-sent').textContent = stats.total_sent || 0;
    document.getElementById('em-open-rate').textContent = (stats.open_rate || 0) + '%';
    document.getElementById('em-click-rate').textContent = (stats.click_rate || 0) + '%';
    const el = document.getElementById('em-campaign-list');
    if (!campaigns.length) { el.innerHTML = '<div class="empty"><div class="icon">📧</div><p>No campaigns yet.</p></div>'; return; }
    el.innerHTML = campaigns.map(c => `<div style="padding:10px;border-bottom:1px solid var(--border)">
      <div style="display:flex;justify-content:space-between"><strong>${c.name}</strong>
        <span style="font-size:.75em;background:var(--surface3);padding:2px 6px;border-radius:4px">${c.status}</span></div>
      <div style="font-size:.8em;color:var(--text-muted);margin-top:2px">${c.subject}</div>
      <div style="display:flex;gap:10px;margin-top:6px;font-size:.8em">
        <span>Sent: ${c.sent}</span><span>Opened: ${c.opened}</span><span>Clicked: ${c.clicked}</span>
        ${c.status==='draft'?`<button class="btn btn-ghost btn-sm" onclick="sendCampaign('${c.id}')" style="font-size:.75em;padding:2px 8px">📤 Send</button>`:''}
      </div></div>`).join('');
  } catch(e) { console.error('Email load error', e); }
}
async function createEmailCampaign() {
  const recipients = (document.getElementById('em-recipients').value || '').split(',').map(s=>s.trim()).filter(Boolean);
  const payload = {
    name: document.getElementById('em-name').value,
    subject: document.getElementById('em-subject').value,
    body: document.getElementById('em-body').value,
    recipients,
  };
  if (!payload.name) return showToast('Campaign name required', 'error');
  await api('/api/email-mkt/campaigns', 'POST', payload);
  ['em-name','em-subject','em-body','em-recipients'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Campaign created!');
  loadEmailCampaigns();
}
async function sendCampaign(id) {
  if (!confirm('Send this campaign now?')) return;
  await api(`/api/email-mkt/campaigns/${id}/send`, 'POST', {});
  showToast('Campaign sent!');
  loadEmailCampaigns();
}

// ── Meetings ─────────────────────────────────────────────────────
async function loadMeetings() {
  try {
    const [meetings, stats] = await Promise.all([api('/api/meetings/'), api('/api/meetings/stats')]);
    document.getElementById('mt-total').textContent = stats.total || 0;
    document.getElementById('mt-analyzed').textContent = stats.analyzed || 0;
    document.getElementById('mt-pending').textContent = stats.pending || 0;
    document.getElementById('mt-duration').textContent = stats.total_duration_mins || 0;
    const el = document.getElementById('meetings-list');
    if (!meetings.length) { el.innerHTML = '<div class="empty"><div class="icon">🎙️</div><p>No meetings yet.</p></div>'; return; }
    el.innerHTML = meetings.map(m => `<div style="padding:10px;border-bottom:1px solid var(--border)">
      <div style="display:flex;justify-content:space-between"><strong>${m.title}</strong>
        <span style="font-size:.75em;background:var(--surface3);padding:2px 6px;border-radius:4px">${m.status}</span></div>
      <div style="font-size:.8em;color:var(--text-muted)">${m.date} · ${m.platform} · ${m.duration_mins}min</div>
      ${m.summary?`<div style="font-size:.8em;margin-top:6px;color:var(--text)">${m.summary.substring(0,120)}…</div>`:''}
      <div style="display:flex;gap:8px;margin-top:6px">
        ${m.status!=='analyzed'?`<button class="btn btn-ghost btn-sm" onclick="showMeetingAnalysis('${m.id}')" style="font-size:.75em">🤖 Show Analysis</button>`:''}
        <button class="btn btn-ghost btn-sm" onclick="deleteMeeting('${m.id}')" style="font-size:.75em">🗑</button>
      </div></div>`).join('');
  } catch(e) { console.error('Meetings load error', e); }
}
async function addMeeting() {
  const transcript = document.getElementById('mt-transcript').value;
  const payload = {
    title: document.getElementById('mt-title').value,
    platform: document.getElementById('mt-platform').value,
    duration_mins: parseInt(document.getElementById('mt-duration').value) || 0,
    transcript,
  };
  if (!payload.title) return showToast('Title required', 'error');
  const meeting = await api('/api/meetings/', 'POST', payload);
  showToast('Meeting added. Analyzing…');
  const result = await api(`/api/meetings/${meeting.id}/analyze`, 'POST', {transcript});
  document.getElementById('mt-result-card').style.display = '';
  document.getElementById('mt-result-body').textContent = result.follow_up_email || result.summary || 'Analysis complete.';
  ['mt-title','mt-transcript','mt-duration'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  loadMeetings();
}
async function showMeetingAnalysis(id) {
  const data = await api(`/api/meetings/${id}/analyze`, 'POST', {});
  document.getElementById('mt-result-card').style.display = '';
  document.getElementById('mt-result-body').textContent = data.follow_up_email || data.summary || 'No analysis.';
}
async function deleteMeeting(id) {
  await api(`/api/meetings/${id}`, 'DELETE');
  showToast('Meeting deleted');
  loadMeetings();
}

// ── Social Media ──────────────────────────────────────────────────
async function loadSocialPosts() {
  try {
    const [posts, stats] = await Promise.all([api('/api/social/posts'), api('/api/social/stats')]);
    document.getElementById('sm-total').textContent = stats.total_posts || 0;
    document.getElementById('sm-published').textContent = stats.published || 0;
    document.getElementById('sm-scheduled').textContent = stats.scheduled || 0;
    document.getElementById('sm-likes').textContent = stats.total_likes || 0;
    const el = document.getElementById('sm-posts-list');
    if (!posts.length) { el.innerHTML = '<div class="empty"><div class="icon">📱</div><p>No posts yet.</p></div>'; return; }
    el.innerHTML = posts.map(p => `<div style="padding:10px;border-bottom:1px solid var(--border)">
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div style="flex:1">
          <div style="font-size:.85em">${p.content.substring(0,120)}${p.content.length>120?'…':''}</div>
          <div style="display:flex;gap:8px;margin-top:4px;font-size:.75em;color:var(--text-muted)">
            ${(p.platforms||[]).map(pl=>`<span>${pl}</span>`).join('')}
            <span style="background:var(--surface3);padding:1px 6px;border-radius:4px">${p.status}</span>
          </div>
        </div>
        <div style="display:flex;gap:4px;margin-left:8px">
          ${p.status==='draft'?`<button class="btn btn-ghost btn-sm" onclick="publishPost('${p.id}')" style="font-size:.7em">📤</button>`:''}
          <button class="btn btn-ghost btn-sm" onclick="deletePost('${p.id}')" style="font-size:.7em">🗑</button>
        </div>
      </div></div>`).join('');
  } catch(e) { console.error('Social load error', e); }
}
async function generateSocialPost() {
  const topic = document.getElementById('sm-topic').value;
  if (!topic) return showToast('Enter a topic first', 'error');
  showToast('Generating post…');
  const data = await api('/api/social/generate', 'POST', {
    topic, platform: document.getElementById('sm-platform').value,
    tone: document.getElementById('sm-tone').value,
  });
  document.getElementById('sm-content').value = data.content || '';
}
async function saveSocialPost() {
  const content = document.getElementById('sm-content').value;
  if (!content) return showToast('Content required', 'error');
  await api('/api/social/posts', 'POST', {
    content, platforms: [document.getElementById('sm-platform').value],
  });
  document.getElementById('sm-content').value = '';
  document.getElementById('sm-topic').value = '';
  showToast('Post saved!');
  loadSocialPosts();
}
async function publishPost(id) {
  await api(`/api/social/posts/${id}/publish`, 'POST', {});
  showToast('Post published!');
  loadSocialPosts();
}
async function deletePost(id) {
  await api(`/api/social/posts/${id}`, 'DELETE');
  showToast('Post deleted');
  loadSocialPosts();
}

// ── CEO Briefing ──────────────────────────────────────────────────
async function generateBriefing() {
  showToast('Generating briefing…');
  const data = await api('/api/briefing/generate', 'POST', {});
  document.getElementById('briefing-content').textContent = data.content || 'Error generating briefing.';
  document.getElementById('briefing-date').textContent = data.date || '';
  document.getElementById('briefing-card').style.display = '';
  document.getElementById('hc-latest-msg') && (document.getElementById('hc-latest-msg').style.display = 'none');
}
async function loadBriefingHistory() {
  const data = await api('/api/briefing/history');
  const el = document.getElementById('briefing-history');
  if (!data.length) { el.innerHTML = ''; return; }
  el.innerHTML = '<div class="card"><div class="card-header"><div class="card-title">📅 Past Briefings</div></div>' +
    data.slice(-10).reverse().map(b =>
      `<div style="padding:10px;border-bottom:1px solid var(--border)"><strong>${b.date}</strong>
       <div style="font-size:.8em;color:var(--text-muted);margin-top:4px">${(b.content||'').substring(0,200)}…</div></div>`
    ).join('') + '</div>';
}

// ── Finance / Invoicing ───────────────────────────────────────────
function switchFinanceTab(tab, btn) {
  document.querySelectorAll('.fi-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  ['invoices','expenses','pl'].forEach(t => {
    const el = document.getElementById(`fi-${t}-panel`);
    if (el) el.style.display = t === tab ? '' : 'none';
  });
  if (tab === 'invoices') loadInvoices();
  if (tab === 'expenses') loadExpenses();
  if (tab === 'pl') loadPL();
}
async function loadInvoices() {
  try {
    const [invs, pl] = await Promise.all([api('/api/finance/invoices'), api('/api/finance/pl-report')]);
    document.getElementById('fi-revenue').textContent = '$' + (pl.revenue||0).toLocaleString();
    document.getElementById('fi-pending').textContent = '$' + (pl.pending_revenue||0).toLocaleString();
    document.getElementById('fi-total-inv').textContent = pl.total_invoices || 0;
    document.getElementById('fi-overdue').textContent = pl.overdue_invoices || 0;
    const el = document.getElementById('fi-invoice-list');
    if (!invs.length) { el.innerHTML = '<div class="empty"><div class="icon">🧾</div><p>No invoices yet.</p></div>'; return; }
    el.innerHTML = invs.map(i => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
      <div><strong>${i.number}</strong> — ${i.client}
        <div style="font-size:.8em;color:var(--text-muted)">Due: ${i.due_date || 'N/A'}</div></div>
      <div style="text-align:right">
        <div style="font-weight:700;color:var(--green)">$${(i.total||0).toLocaleString()}</div>
        <span style="font-size:.75em;background:var(--surface3);padding:2px 6px;border-radius:4px">${i.status}</span>
        ${i.status==='draft'?`<button class="btn btn-ghost btn-sm" onclick="sendInvoice('${i.id}')" style="font-size:.7em;display:block;margin-top:4px">📤 Send</button>`:''}
        ${i.status==='sent'?`<button class="btn btn-ghost btn-sm" onclick="markPaid('${i.id}')" style="font-size:.7em;display:block;margin-top:4px">✅ Paid</button>`:''}
      </div></div>`).join('');
  } catch(e) { console.error('Invoice load error', e); }
}
async function createInvoice() {
  const payload = {
    client: document.getElementById('fi-client').value,
    client_email: document.getElementById('fi-client-email').value,
    subtotal: parseFloat(document.getElementById('fi-subtotal').value) || 0,
    tax_rate: parseFloat(document.getElementById('fi-tax').value) || 0,
    due_date: document.getElementById('fi-due').value,
    notes: document.getElementById('fi-notes').value,
  };
  if (!payload.client) return showToast('Client name required', 'error');
  await api('/api/finance/invoices', 'POST', payload);
  ['fi-client','fi-client-email','fi-subtotal','fi-tax','fi-due','fi-notes'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Invoice created!');
  loadInvoices();
}
async function sendInvoice(id) {
  await api(`/api/finance/invoices/${id}/send`, 'POST', {});
  showToast('Invoice sent!');
  loadInvoices();
}
async function markPaid(id) {
  await api(`/api/finance/invoices/${id}/mark-paid`, 'POST', {});
  showToast('Invoice marked as paid!');
  loadInvoices();
}
async function loadExpenses() {
  const expenses = await api('/api/finance/expenses');
  const el = document.getElementById('fi-expense-list');
  if (!expenses.length) { el.innerHTML = '<div class="empty"><div class="icon">💸</div><p>No expenses yet.</p></div>'; return; }
  el.innerHTML = expenses.map(e => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between">
    <div><strong>${e.description}</strong><div style="font-size:.8em;color:var(--text-muted)">${e.category} · ${e.date}</div></div>
    <div style="font-weight:700;color:#ef4444">-$${(e.amount||0).toLocaleString()}</div></div>`).join('');
}
async function logExpense() {
  const payload = {
    description: document.getElementById('fi-exp-desc').value,
    amount: parseFloat(document.getElementById('fi-exp-amount').value) || 0,
    category: document.getElementById('fi-exp-cat').value,
    date: document.getElementById('fi-exp-date').value || new Date().toISOString().split('T')[0],
  };
  if (!payload.description) return showToast('Description required', 'error');
  await api('/api/finance/expenses', 'POST', payload);
  ['fi-exp-desc','fi-exp-amount'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Expense logged!');
  loadExpenses();
}
async function loadPL() {
  const pl = await api('/api/finance/pl-report');
  const el = document.getElementById('fi-pl-body');
  const rows = [
    ['Revenue (Paid)', `$${(pl.revenue||0).toLocaleString()}`, 'var(--green)'],
    ['Pending Revenue', `$${(pl.pending_revenue||0).toLocaleString()}`, 'var(--gold)'],
    ['Total Expenses', `-$${(pl.total_expenses||0).toLocaleString()}`, '#ef4444'],
    ['Gross Profit', `$${(pl.gross_profit||0).toLocaleString()}`, pl.gross_profit>=0?'var(--green)':'#ef4444'],
    ['Profit Margin', `${pl.profit_margin||0}%`, 'var(--text-muted)'],
  ];
  el.innerHTML = `<div style="display:grid;gap:8px">${rows.map(([label,val,color])=>
    `<div style="display:flex;justify-content:space-between;padding:8px;background:var(--surface2);border-radius:6px">
       <span>${label}</span><strong style="color:${color}">${val}</strong></div>`
  ).join('')}
  ${pl.expenses_by_category && Object.keys(pl.expenses_by_category).length?
    `<div style="margin-top:8px"><strong style="font-size:.9em">Expenses by Category</strong>
     ${Object.entries(pl.expenses_by_category).map(([k,v])=>
       `<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:.85em">
         <span>${k}</span><span>$${(v||0).toLocaleString()}</span></div>`
     ).join('')}</div>`:''}</div>`;
}

// ── Analytics ─────────────────────────────────────────────────────
async function loadAnalyticsOverview() {
  const data = await api('/api/analytics/overview');
  document.getElementById('an-leads').textContent = data.crm?.total_leads || 0;
  document.getElementById('an-revenue').textContent = '$' + (data.finance?.revenue||0).toLocaleString();
  document.getElementById('an-open-rate').textContent = (data.email?.open_rate||0) + '%';
  document.getElementById('an-posts').textContent = data.social?.posts || 0;
  const el = document.getElementById('an-breakdown');
  el.innerHTML = `<div style="display:grid;gap:8px;font-size:.88em">
    <div style="padding:10px;background:var(--surface2);border-radius:6px">
      <strong>🎯 CRM</strong>
      <div style="margin-top:6px;display:grid;gap:2px">
        <div>Pipeline: <strong>$${(data.crm?.pipeline_value||0).toLocaleString()}</strong></div>
        <div>Won Deals: <strong>${data.crm?.won_deals||0}</strong></div>
        <div>Conversion: <strong>${data.crm?.conversion_rate||0}%</strong></div>
      </div>
    </div>
    <div style="padding:10px;background:var(--surface2);border-radius:6px">
      <strong>📧 Email</strong>
      <div style="margin-top:6px;display:grid;gap:2px">
        <div>Campaigns: <strong>${data.email?.campaigns||0}</strong></div>
        <div>Sent: <strong>${data.email?.sent||0}</strong></div>
      </div>
    </div>
    <div style="padding:10px;background:var(--surface2);border-radius:6px">
      <strong>🎙️ Meetings</strong>
      <div style="margin-top:6px;display:grid;gap:2px">
        <div>Total: <strong>${data.meetings?.total||0}</strong></div>
        <div>Analyzed: <strong>${data.meetings?.analyzed||0}</strong></div>
      </div>
    </div></div>`;
}
async function loadRecommendations() {
  const data = await api('/api/analytics/recommendations');
  const recs = data.recommendations || [];
  const el = document.getElementById('an-recommendations');
  if (!recs.length) { el.innerHTML = '<div class="empty"><p>No recommendations at this time.</p></div>'; return; }
  const colors = {high:'#ef4444', medium:'#f59e0b', low:'#10b981', critical:'#ef4444'};
  el.innerHTML = recs.map(r => `<div style="padding:10px;border-left:3px solid ${colors[r.priority]||'var(--border)'};margin-bottom:8px;background:var(--surface2);border-radius:0 6px 6px 0">
    <div style="font-size:.75em;color:${colors[r.priority]||'var(--text-muted)'};text-transform:uppercase;font-weight:700">${r.type} · ${r.priority}</div>
    <div style="font-size:.88em;margin-top:4px">${r.text}</div>
    ${r.action?`<div style="font-size:.78em;color:var(--text-muted);margin-top:4px">→ ${r.action}</div>`:''}</div>`
  ).join('');
}

// ── Workflows ─────────────────────────────────────────────────────
async function loadWorkflows() {
  const wfs = await api('/api/workflows/');
  const el = document.getElementById('wf-list');
  if (!wfs.length) { el.innerHTML = '<div class="empty"><div class="icon">⚙️</div><p>No workflows yet.</p></div>'; return; }
  el.innerHTML = wfs.map(w => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><strong>${w.name}</strong>
      <div style="font-size:.8em;color:var(--text-muted)">${w.description||''} · Trigger: ${w.trigger?.type||w.trigger}</div>
      <div style="font-size:.78em;color:var(--text-muted)">Steps: ${(w.steps||[]).length} · Runs: ${w.runs||0}</div>
    </div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-ghost btn-sm" onclick="runWorkflow('${w.id}')" style="font-size:.75em">▶ Run</button>
      <button class="btn btn-ghost btn-sm" onclick="deleteWorkflow('${w.id}')" style="font-size:.75em">🗑</button>
    </div></div>`).join('');
}
async function createWorkflow() {
  const stepsRaw = document.getElementById('wf-steps').value;
  const steps = stepsRaw.split('\n').map(l=>l.trim()).filter(Boolean).map(l => {
    const [action, ...desc] = l.split(':');
    return {type: action.trim(), config: desc.join(':').trim()};
  });
  const payload = {
    name: document.getElementById('wf-name').value,
    description: document.getElementById('wf-desc').value,
    trigger: {type: document.getElementById('wf-trigger').value},
    steps,
  };
  if (!payload.name) return showToast('Workflow name required', 'error');
  await api('/api/workflows/', 'POST', payload);
  ['wf-name','wf-desc','wf-steps'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Workflow created!');
  loadWorkflows();
}
async function runWorkflow(id) {
  await api(`/api/workflows/${id}/run`, 'POST', {});
  showToast('Workflow executed!');
  loadWorkflows();
  loadWorkflowRuns();
}
async function deleteWorkflow(id) {
  await api(`/api/workflows/${id}`, 'DELETE');
  showToast('Workflow deleted');
  loadWorkflows();
}
async function loadWorkflowRuns() {
  const runs = await api('/api/workflows/runs');
  const el = document.getElementById('wf-runs-list');
  if (!runs.length) { el.innerHTML = '<div class="empty"><p>No runs yet.</p></div>'; return; }
  el.innerHTML = runs.slice(-10).reverse().map(r => `<div style="padding:8px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;font-size:.85em">
    <div><strong>${r.workflow_name}</strong> <span style="color:var(--text-muted)">· ${r.trigger}</span></div>
    <div><span style="color:var(--green)">${r.status}</span> <span style="color:var(--text-muted);font-size:.8em">${r.started_at}</span></div>
  </div>`).join('');
}

// ── Team ──────────────────────────────────────────────────────────
async function loadTeamMembers() {
  const members = await api('/api/team/members');
  const el = document.getElementById('team-members-list');
  if (!members.length) { el.innerHTML = '<div class="empty"><div class="icon">👥</div><p>No members yet. Invite someone!</p></div>'; return; }
  el.innerHTML = members.map(m => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><strong>${m.name||m.email}</strong>
      <div style="font-size:.8em;color:var(--text-muted)">${m.email}</div></div>
    <div style="text-align:right">
      <span style="font-size:.78em;background:var(--surface3);padding:2px 8px;border-radius:4px">${m.role}</span>
      <span style="font-size:.75em;color:var(--text-muted);display:block;margin-top:2px">${m.status}</span>
    </div></div>`).join('');
}
async function inviteTeamMember() {
  const email = document.getElementById('team-email').value;
  const role = document.getElementById('team-role').value;
  if (!email) return showToast('Email required', 'error');
  const data = await api('/api/team/members/invite', 'POST', {email, role});
  if (data.error) return showToast(data.error, 'error');
  document.getElementById('team-invite-result').innerHTML =
    `<div style="padding:10px;background:var(--surface2);border-radius:6px;font-size:.85em">
     ✅ Invitation sent! Share this token: <code style="color:var(--gold)">${data.token}</code></div>`;
  document.getElementById('team-email').value = '';
  loadTeamMembers();
}

// ── Support ───────────────────────────────────────────────────────
function switchSupportTab(tab, btn) {
  document.querySelectorAll('.sup-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('sup-tickets-panel').style.display = tab === 'tickets' ? '' : 'none';
  document.getElementById('sup-kb-panel').style.display = tab === 'kb' ? '' : 'none';
  if (tab === 'tickets') loadTickets();
  if (tab === 'kb') loadKBArticles();
}
async function loadTickets() {
  try {
    const [tickets, stats] = await Promise.all([
      api('/api/support/tickets' + (document.getElementById('sup-f-status')?.value ? '?status=' + document.getElementById('sup-f-status').value : '')),
      api('/api/support/stats')
    ]);
    document.getElementById('sup-open').textContent = stats.open || 0;
    document.getElementById('sup-progress').textContent = stats.in_progress || 0;
    document.getElementById('sup-resolved').textContent = stats.resolved || 0;
    document.getElementById('sup-kb').textContent = stats.kb_articles || 0;
    const el = document.getElementById('sup-ticket-list');
    if (!tickets.length) { el.innerHTML = '<div class="empty"><div class="icon">🎫</div><p>No tickets.</p></div>'; return; }
    const prioColors = {urgent:'#ef4444',high:'#f59e0b',medium:'#6366f1',low:'#10b981'};
    el.innerHTML = tickets.map(t => `<div style="padding:10px;border-bottom:1px solid var(--border)">
      <div style="display:flex;justify-content:space-between">
        <strong>${t.number}: ${t.subject}</strong>
        <span style="font-size:.75em;background:var(--surface3);padding:2px 6px;border-radius:4px">${t.status}</span>
      </div>
      <div style="font-size:.8em;color:var(--text-muted)">${t.customer_name||''} · ${t.customer_email||''}</div>
      <div style="display:flex;gap:8px;margin-top:6px">
        <span style="font-size:.75em;color:${prioColors[t.priority]||'var(--text-muted)'}">${t.priority}</span>
        <span style="font-size:.75em;color:var(--text-muted)">${t.category}</span>
        <button class="btn btn-ghost btn-sm" onclick="aiSuggestReply('${t.id}')" style="font-size:.7em">🤖 AI Reply</button>
        ${t.status!=='resolved'?`<button class="btn btn-ghost btn-sm" onclick="resolveTicket('${t.id}')" style="font-size:.7em">✅ Resolve</button>`:''}
      </div></div>`).join('');
  } catch(e) { console.error('Support load error', e); }
}
async function createTicket() {
  const payload = {
    subject: document.getElementById('sup-subject').value,
    customer_email: document.getElementById('sup-cust-email').value,
    customer_name: document.getElementById('sup-cust-name').value,
    priority: document.getElementById('sup-priority').value,
    category: document.getElementById('sup-cat').value,
    description: document.getElementById('sup-desc').value,
  };
  if (!payload.subject) return showToast('Subject required', 'error');
  await api('/api/support/tickets', 'POST', payload);
  ['sup-subject','sup-cust-email','sup-cust-name','sup-desc'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Ticket created!');
  loadTickets();
}
async function aiSuggestReply(id) {
  showToast('Generating AI reply…');
  const data = await api(`/api/support/tickets/${id}/ai-suggest`, 'POST', {});
  alert('AI Suggested Reply:\n\n' + (data.suggestion || 'No suggestion.'));
}
async function resolveTicket(id) {
  await api(`/api/support/tickets/${id}`, 'PATCH', {status: 'resolved'});
  showToast('Ticket resolved!');
  loadTickets();
}
async function loadKBArticles() {
  const articles = await api('/api/support/kb');
  const el = document.getElementById('sup-kb-list');
  if (!articles.length) { el.innerHTML = '<div class="empty"><div class="icon">📚</div><p>No articles yet.</p></div>'; return; }
  el.innerHTML = articles.map(a => `<div style="padding:10px;border-bottom:1px solid var(--border)">
    <strong>${a.title}</strong>
    <div style="font-size:.8em;color:var(--text-muted)">${a.category} · Views: ${a.views}</div>
    <div style="font-size:.82em;margin-top:4px">${a.content.substring(0,120)}…</div>
  </div>`).join('');
}
async function createKBArticle() {
  const payload = {
    title: document.getElementById('kb-title').value,
    content: document.getElementById('kb-content').value,
    category: document.getElementById('kb-cat').value,
  };
  if (!payload.title) return showToast('Title required', 'error');
  await api('/api/support/kb', 'POST', payload);
  ['kb-title','kb-content'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Article saved!');
  loadKBArticles();
}

// ── Website Builder ───────────────────────────────────────────────
async function loadPages() {
  const pages = await api('/api/website-builder/pages');
  const el = document.getElementById('wb-pages-list');
  if (!pages.length) { el.innerHTML = '<div class="empty"><div class="icon">🌐</div><p>No pages yet.</p></div>'; return; }
  el.innerHTML = pages.map(p => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><strong>${p.name}</strong>
      <div style="font-size:.8em;color:var(--text-muted)">${p.type} · ${p.business_name}</div></div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-ghost btn-sm" onclick="previewPage('${p.id}')" style="font-size:.75em">👁 Preview</button>
      <button class="btn btn-ghost btn-sm" onclick="deletePage('${p.id}')" style="font-size:.75em">🗑</button>
    </div></div>`).join('');
}
async function generateWebPage() {
  const payload = {
    business_name: document.getElementById('wb-biz').value,
    industry: document.getElementById('wb-industry').value,
    page_type: document.getElementById('wb-type').value,
    description: document.getElementById('wb-desc').value,
  };
  if (!payload.business_name) return showToast('Business name required', 'error');
  showToast('Generating page with AI…');
  await api('/api/website-builder/generate', 'POST', payload);
  showToast('Page generated!');
  loadPages();
}
async function previewPage(id) {
  const page = await api(`/api/website-builder/pages/${id}`);
  const w = window.open('', '_blank');
  w.document.write(page.html_content || '<p>No content.</p>');
}
async function deletePage(id) {
  await api(`/api/website-builder/pages/${id}`, 'DELETE');
  showToast('Page deleted');
  loadPages();
}

// ── Competitors ───────────────────────────────────────────────────
async function loadCompetitors() {
  const comps = await api('/api/competitors/');
  const el = document.getElementById('comp-list');
  if (!comps.length) { el.innerHTML = '<div class="empty"><div class="icon">🔍</div><p>No competitors tracked yet.</p></div>'; return; }
  el.innerHTML = comps.map(c => `<div style="padding:10px;border-bottom:1px solid var(--border)">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div><strong>${c.name}</strong>
        ${c.website?`<a href="${c.website}" target="_blank" style="font-size:.78em;color:var(--accent);margin-left:8px">${c.website}</a>`:''}
        <div style="font-size:.82em;color:var(--text-muted);margin-top:2px">${c.description||''}</div>
        ${c.last_checked?`<div style="font-size:.75em;color:var(--text-muted)">Last analyzed: ${c.last_checked}</div>`:''}
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="analyzeCompetitor('${c.id}')" style="font-size:.75em">🤖 Analyze</button>
        <button class="btn btn-ghost btn-sm" onclick="deleteCompetitor('${c.id}')" style="font-size:.75em">🗑</button>
      </div>
    </div></div>`).join('');
}
async function addCompetitor() {
  const payload = {
    name: document.getElementById('comp-name').value,
    website: document.getElementById('comp-website').value,
    description: document.getElementById('comp-desc').value,
  };
  if (!payload.name) return showToast('Name required', 'error');
  await api('/api/competitors/', 'POST', payload);
  ['comp-name','comp-website','comp-desc'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Competitor added!');
  loadCompetitors();
}
async function analyzeCompetitor(id) {
  showToast('Analyzing competitor with AI…');
  const data = await api(`/api/competitors/${id}/analyze`, 'POST', {});
  document.getElementById('comp-analysis-card').style.display = '';
  document.getElementById('comp-analysis-body').textContent = data.analysis || 'No analysis.';
  loadCompetitors();
}
async function deleteCompetitor(id) {
  await api(`/api/competitors/${id}`, 'DELETE');
  showToast('Competitor removed');
  loadCompetitors();
}

// ── Personal Brand ────────────────────────────────────────────────
function switchBrandTab(tab, btn) {
  document.querySelectorAll('.br-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  ['generate','profile','library'].forEach(t => {
    const el = document.getElementById(`br-${t}-panel`);
    if (el) el.style.display = t === tab ? '' : 'none';
  });
  if (tab === 'library') loadBrandContent();
}
async function generateBrandContent() {
  const topic = document.getElementById('br-topic').value;
  if (!topic) return showToast('Topic required', 'error');
  showToast('Generating content…');
  const data = await api('/api/brand/generate-content', 'POST', {
    topic, content_type: document.getElementById('br-type').value,
  });
  document.getElementById('br-generated').textContent = data.content || '';
}
async function suggestBrandTopics() {
  showToast('Generating topic ideas…');
  const data = await api('/api/brand/topics', 'POST', {});
  const el = document.getElementById('br-topics-list');
  el.innerHTML = (data.topics||[]).map((t,i)=>
    `<div style="padding:6px;border-bottom:1px solid var(--border);font-size:.85em;cursor:pointer"
      onclick="document.getElementById('br-topic').value='${t.replace(/'/g,"\\'")}'">${i+1}. ${t}</div>`
  ).join('');
}
async function saveBrandProfile() {
  const payload = {
    name: document.getElementById('br-p-name').value,
    title: document.getElementById('br-p-title').value,
    industry: document.getElementById('br-p-industry').value,
    target_audience: document.getElementById('br-p-audience').value,
    tone: document.getElementById('br-p-tone').value,
  };
  await api('/api/brand/profile', 'POST', payload);
  showToast('Profile saved!');
}
async function loadBrandContent() {
  const pieces = await api('/api/brand/content');
  const el = document.getElementById('br-content-list');
  if (!pieces.length) { el.innerHTML = '<div class="empty"><div class="icon">📁</div><p>No content saved yet.</p></div>'; return; }
  el.innerHTML = pieces.map(p => `<div style="padding:10px;border-bottom:1px solid var(--border)">
    <div style="display:flex;justify-content:space-between">
      <span style="font-size:.78em;background:var(--surface3);padding:2px 6px;border-radius:4px">${p.type}</span>
      <span style="font-size:.75em;color:var(--text-muted)">${p.created_at?.split('T')[0]||''}</span>
    </div>
    <div style="font-size:.85em;margin-top:6px"><strong>${p.topic}</strong></div>
    <div style="font-size:.82em;color:var(--text-muted);margin-top:4px">${p.content.substring(0,150)}…</div>
    <button class="btn btn-ghost btn-sm" onclick="deleteBrandContent('${p.id}')" style="font-size:.7em;margin-top:6px">🗑 Delete</button>
  </div>`).join('');
}
async function deleteBrandContent(id) {
  await api(`/api/brand/content/${id}`, 'DELETE');
  showToast('Content deleted');
  loadBrandContent();
}

// ── Health Check ──────────────────────────────────────────────────
async function runHealthCheck() {
  showToast('Running health check…');
  const data = await api('/api/health-check/run', 'POST', {});
  document.getElementById('hc-report-card').style.display = '';
  document.getElementById('hc-latest-msg').style.display = 'none';
  const gradeColors = {A:'#10b981',B:'#6366f1',C:'#f59e0b',D:'#ef4444'};
  document.getElementById('hc-grade').textContent = data.grade;
  document.getElementById('hc-grade').style.color = gradeColors[data.grade]||'var(--text)';
  const el = document.getElementById('hc-report-body');
  el.innerHTML = `<div style="margin-bottom:16px">
    <div style="font-size:.9em;font-weight:700;margin-bottom:8px">Overall: ${data.overall_score}/100 (Grade ${data.grade})</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">${Object.entries(data.scores||{}).map(([k,v])=>
      `<div style="padding:6px 12px;background:var(--surface2);border-radius:6px;font-size:.82em">${k}: <strong>${v}</strong></div>`
    ).join('')}</div></div>
  ${data.issues?.length?`<div style="margin-bottom:16px"><strong style="font-size:.9em">⚠️ Issues Found</strong>
    ${data.issues.map(i=>`<div style="padding:8px;margin-top:6px;border-left:3px solid ${i.severity==='critical'?'#ef4444':'#f59e0b'};background:var(--surface2);border-radius:0 6px 6px 0;font-size:.84em">
      <div><strong>${i.area}:</strong> ${i.issue}</div>
      <div style="color:var(--text-muted);margin-top:2px">→ ${i.suggestion}</div></div>`).join('')}</div>`:''}
  ${data.strengths?.length?`<div><strong style="font-size:.9em">✅ Strengths</strong>
    ${data.strengths.map(s=>`<div style="padding:6px 0;font-size:.84em;color:var(--green)">✓ ${s}</div>`).join('')}</div>`:''}`;
}
async function loadHealthHistory() {
  const reports = await api('/api/health-check/history');
  const el = document.getElementById('hc-history');
  if (!reports.length) { el.innerHTML = ''; return; }
  const colors = {A:'#10b981',B:'#6366f1',C:'#f59e0b',D:'#ef4444'};
  el.innerHTML = '<div class="card"><div class="card-header"><div class="card-title">📅 Health History</div></div>' +
    reports.slice(-12).reverse().map(r=>
      `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between">
        <div><strong>${r.date}</strong> <span style="font-size:.82em;color:var(--text-muted)">${r.overall_score}/100</span></div>
        <span style="font-size:1.2em;font-weight:900;color:${colors[r.grade]||'var(--text)'}">${r.grade}</span>
      </div>`
    ).join('') + '</div>';
}

// ── Export & Backup ───────────────────────────────────────────────
async function loadExportModules() {
  const modules = await api('/api/export/modules');
  const el = document.getElementById('export-modules-list');
  el.innerHTML = modules.map(m => `<div style="padding:8px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><strong>${m.key}</strong>
      <span style="font-size:.75em;color:var(--text-muted);margin-left:8px">${m.exists?(m.size_bytes/1024).toFixed(1)+'KB':'no data'}</span></div>
    <div style="display:flex;gap:6px">
      ${m.exists?`<a href="/api/export/json/${m.key}" download class="btn btn-ghost btn-sm" style="font-size:.75em">⬇ JSON</a>`:'<span style="font-size:.75em;color:var(--text-muted)">no data</span>'}
    </div></div>`).join('');
}
async function createBackup() {
  showToast('Creating backup…');
  const data = await api('/api/export/backup', 'POST', {});
  showToast(`Backup created: ${data.backup_file} (${(data.size_bytes/1024).toFixed(0)}KB)`);
  loadBackupsList();
}
async function loadBackupsList() {
  const backups = await api('/api/export/backups');
  const el = document.getElementById('export-backups-list');
  if (!backups.length) { el.innerHTML = '<div class="empty"><div class="icon">🗜️</div><p>No backups yet.</p></div>'; return; }
  el.innerHTML = backups.map(b => `<div style="padding:8px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><div style="font-size:.85em">${b.name}</div>
      <div style="font-size:.75em;color:var(--text-muted)">${(b.size_bytes/1024).toFixed(0)}KB · ${b.created_at}</div></div>
    <a href="/api/export/download-backup/${b.name}" download class="btn btn-ghost btn-sm" style="font-size:.75em">⬇ Download</a>
  </div>`).join('');
}

// ── Auto-load on tab switch (extend base switchTab) ───────────
function switchTab(tab, btn) {
  _switchTabBase(tab, btn);
  const loaders = {
    'crm': loadCRM,
    'email-mkt': loadEmailCampaigns,
    'meetings': loadMeetings,
    'social': loadSocialPosts,
    'briefing': () => api('/api/briefing/latest').then(d => {
      if (d.content) { document.getElementById('briefing-content').textContent = d.content; document.getElementById('briefing-date').textContent = d.date||''; }
    }),
    'invoicing': loadInvoices,
    'analytics-bi': () => { loadAnalyticsOverview(); loadRecommendations(); },
    'workflows': () => { loadWorkflows(); loadWorkflowRuns(); },
    'team': loadTeamMembers,
    'support-desk': loadTickets,
    'website-builder': loadPages,
    'competitors': loadCompetitors,
    'brand': () => api('/api/brand/profile').then(p => {
      if (p.name) { document.getElementById('br-p-name').value=p.name||''; document.getElementById('br-p-title').value=p.title||''; document.getElementById('br-p-industry').value=p.industry||''; document.getElementById('br-p-audience').value=p.target_audience||''; }
    }),
    'health': () => api('/api/health-check/latest').then(d => {
      if (d.grade) { document.getElementById('hc-report-card').style.display=''; document.getElementById('hc-latest-msg').style.display='none'; runHealthCheck && null; }
    }),
    'export': () => { loadExportModules(); loadBackupsList(); },
    'neural-brain': () => { brainLoad(); brainLoadLog(); },
  };
  if (loaders[tab]) { try { loaders[tab](); } catch(e) {} }
}

function rerunTaskFromHistory(description) {
  const taskInput = document.getElementById('task-input');
  if (taskInput) { taskInput.value = description; }
  switchTab('tasks', null);
  setTimeout(() => {
    const el = document.getElementById('task-input');
    if (el) { el.focus(); el.scrollIntoView({behavior:'smooth', block:'nearest'}); }
  }, 150);
  toast('Task pre-filled — review and click Launch ↗', 'info');
}

async function viewTaskById(taskId) {
  const r = await api('/api/task/list');
  if (!r.ok) { toast('Could not load tasks', 'error'); return; }
  const plan = (r.plans || []).find(p => p.id === taskId);
  if (plan) {
    switchTab('tasks', null);
    setTimeout(() => {
      _taskStore.set(taskId, plan);
      openTaskDetail(taskId);
    }, 200);
  } else {
    toast('Task not found in recent history — it may have been pruned', 'info');
    switchTab('tasks', null);
  }
}
// ═══════════════════════════════════════════════════════════════════
// CRM
// ═══════════════════════════════════════════════════════════════════
const CRM_STAGES = ['new_lead','qualified','proposal_sent','negotiation','closed_won','closed_lost'];
const CRM_STAGE_LABELS = {new_lead:'🆕 New Lead',qualified:'✅ Qualified',proposal_sent:'📄 Proposal Sent',negotiation:'🤝 Negotiation',closed_won:'🏆 Closed Won',closed_lost:'❌ Closed Lost'};
const CRM_STAGE_COLORS = {new_lead:'#64748b',qualified:'#3b82f6',proposal_sent:'#8b5cf6',negotiation:'#f59e0b',closed_won:'#10b981',closed_lost:'#ef4444'};

async function loadCRM() {
  try {
    const [pipe, leads] = await Promise.all([
      fetch('/api/crm/pipeline').then(r=>r.json()),
      fetch('/api/crm/leads?search='+encodeURIComponent(document.getElementById('crm-search')?.value||'')).then(r=>r.json())
    ]);
    // Pipeline stats
    document.getElementById('crm-stat-new').textContent = pipe.new_lead?.count ?? 0;
    document.getElementById('crm-stat-qualified').textContent = pipe.qualified?.count ?? 0;
    document.getElementById('crm-stat-proposal').textContent = pipe.proposal_sent?.count ?? 0;
    document.getElementById('crm-stat-won').textContent = pipe.closed_won?.count ?? 0;
    // Kanban
    const kanban = document.getElementById('crm-pipeline-kanban');
    kanban.innerHTML = CRM_STAGES.map(stage => {
      const s = pipe[stage] || {count:0,value:0,leads:[]};
      const color = CRM_STAGE_COLORS[stage];
      const leadsHtml = s.leads.map(l => `
        <div style="background:var(--surface);border:1px solid rgba(255,255,255,.08);border-radius:6px;padding:8px 10px;margin-bottom:6px;font-size:.82em">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <strong style="color:var(--text)">${escHtml(l.name)}</strong>
            <span style="color:${color};font-size:.75em;font-weight:700">Score: ${l.score||0}</span>
          </div>
          ${l.value>0?`<div style="color:#10b981;font-size:.78em">$${Number(l.value).toLocaleString()}</div>`:''}
          <div style="margin-top:6px;display:flex;gap:4px;flex-wrap:wrap">
            ${CRM_STAGES.filter(ns=>ns!==stage).slice(0,3).map(ns=>`<button class="btn btn-ghost" style="font-size:.7em;padding:2px 6px" onclick="moveCRMStage('${l.id}','${ns}')">→${CRM_STAGE_LABELS[ns].split(' ').pop()}</button>`).join('')}
            <button class="btn btn-ghost" style="font-size:.7em;padding:2px 6px;color:#f59e0b" onclick="scoreCRMLead('${l.id}')">🎯 Score</button>
          </div>
        </div>`).join('') || '<div style="color:var(--text-muted);font-size:.82em;text-align:center;padding:8px">Empty</div>';
      return `<div style="border-left:3px solid ${color};padding:8px 10px;background:rgba(255,255,255,.02);border-radius:0 6px 6px 0;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span style="font-size:.82em;font-weight:700;color:${color}">${CRM_STAGE_LABELS[stage]}</span>
          <span style="font-size:.75em;color:var(--text-muted)">${s.count} lead${s.count!==1?'s':''} • $${Number(s.value).toLocaleString()}</span>
        </div>
        ${leadsHtml}</div>`;
    }).join('');
    // All leads list
    const listEl = document.getElementById('crm-leads-list');
    if (!leads.length) { listEl.innerHTML='<div class="empty"><div class="icon">🎯</div><p>No leads found.</p></div>'; return; }
    listEl.innerHTML = leads.map(l => `
      <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em">
        <div style="flex:1">
          <div style="font-weight:600;color:var(--text)">${escHtml(l.name)} ${l.company?`<span style="color:var(--text-muted);font-weight:400">@ ${escHtml(l.company)}</span>`:''}
          </div>
          <div style="color:var(--text-muted);font-size:.78em">${escHtml(l.email||'')} ${l.value>0?`• $${Number(l.value).toLocaleString()}`:''}</div>
        </div>
        <span style="font-size:.75em;padding:2px 8px;border-radius:10px;background:rgba(255,255,255,.06);color:${CRM_STAGE_COLORS[l.stage]||'#64748b'}">${CRM_STAGE_LABELS[l.stage]||l.stage}</span>
        <button class="btn btn-ghost btn-sm" style="font-size:.72em" onclick="deleteCRMLead('${l.id}')">🗑</button>
      </div>`).join('');
  } catch(e) { console.error('CRM load error',e); }
}

async function addCRMLead() {
  const name = document.getElementById('crm-name').value.trim();
  if (!name) { showToast('Name is required','error'); return; }
  const res = document.getElementById('crm-add-result');
  res.innerHTML = '<span style="color:var(--gold)">Adding…</span>';
  try {
    const r = await fetch('/api/crm/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      name, company:document.getElementById('crm-company').value,
      email:document.getElementById('crm-email').value,
      phone:document.getElementById('crm-phone').value,
      value:parseFloat(document.getElementById('crm-value').value)||0,
      source:document.getElementById('crm-source').value,
      notes:document.getElementById('crm-notes').value,
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = `<span style="color:#10b981">✅ Lead added!</span>`;
    ['crm-name','crm-company','crm-email','crm-phone','crm-value','crm-source','crm-notes'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    await loadCRM();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function moveCRMStage(id, stage) {
  try {
    await fetch(`/api/crm/leads/${id}/stage`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage})});
    await loadCRM();
    showToast(`Moved to ${CRM_STAGE_LABELS[stage]}`);
  } catch(e) { showToast('Error moving stage','error'); }
}

async function scoreCRMLead(id) {
  showToast('Scoring lead with AI…','info');
  try {
    const r = await fetch(`/api/crm/score/${id}`,{method:'POST'});
    const data = await r.json();
    await loadCRM();
    showToast(`Score: ${data.score}/100`);
  } catch(e) { showToast('Scoring failed','error'); }
}

async function deleteCRMLead(id) {
  if (!confirm('Delete this lead?')) return;
  await fetch(`/api/crm/leads/${id}`,{method:'DELETE'});
  await loadCRM();
  showToast('Lead deleted');
}

// ═══════════════════════════════════════════════════════════════════
// Email Marketing
// ═══════════════════════════════════════════════════════════════════
async function loadEmailCampaigns() {
  try {
    const camps = await fetch('/api/email/campaigns').then(r=>r.json());
    const tips = await fetch('/api/email/deliverability-tips').then(r=>r.json());
    const el = document.getElementById('em-campaigns-list');
    const sent = camps.filter(c=>c.status==='sent').length;
    const draft = camps.filter(c=>c.status==='draft').length;
    document.getElementById('em-stat-total').textContent = camps.length;
    document.getElementById('em-stat-sent').textContent = sent;
    document.getElementById('em-stat-draft').textContent = draft;
    document.getElementById('em-stat-open-rate').textContent = '—';
    if (!camps.length) { el.innerHTML='<div class="empty"><div class="icon">📧</div><p>No campaigns yet.</p></div>'; }
    else {
      el.innerHTML = camps.map(c=>`
        <div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <strong style="color:var(--text)">${escHtml(c.name)}</strong>
            <span style="font-size:.75em;padding:2px 8px;border-radius:10px;background:${c.status==='sent'?'rgba(16,185,129,.15)':c.status==='draft'?'rgba(100,116,139,.15)':'rgba(245,158,11,.15)'};color:${c.status==='sent'?'#10b981':c.status==='draft'?'#94a3b8':'#f59e0b'}">${c.status}</span>
          </div>
          <div style="color:var(--text-muted);font-size:.78em">${escHtml(c.subject)}</div>
          <div style="margin-top:6px;display:flex;gap:6px">
            ${c.status!=='sent'?`<button class="btn btn-ghost btn-sm" style="font-size:.72em" onclick="sendEmailCampaign('${c.id}')">▶ Send</button>`:''}
            <button class="btn btn-ghost btn-sm" style="font-size:.72em" onclick="showCampaignStats('${c.id}')">📊 Stats</button>
            <button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#ef4444" onclick="deleteEmailCampaign('${c.id}')">🗑</button>
          </div>
        </div>`).join('');
    }
    // Tips
    document.getElementById('em-tips-list').innerHTML = tips.map((t,i)=>`<div style="padding:4px 0;border-bottom:${i<tips.length-1?'1px solid rgba(255,255,255,.04)':'none'}"><span style="color:#06b6d4;margin-right:6px">•</span>${escHtml(t)}</div>`).join('');
  } catch(e) { console.error('Email load error',e); }
}

async function createEmailCampaign() {
  const name = document.getElementById('em-camp-name').value.trim();
  const subject = document.getElementById('em-subject').value.trim();
  const body = document.getElementById('em-body').value.trim();
  if (!name || !subject || !body) { showToast('Name, subject and body required','error'); return; }
  const res = document.getElementById('em-create-result');
  res.innerHTML = '<span style="color:var(--gold)">Creating…</span>';
  try {
    const r = await fetch('/api/email/campaigns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      name, subject, body, from_name:document.getElementById('em-from-name').value
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = '<span style="color:#10b981">✅ Campaign created!</span>';
    ['em-camp-name','em-from-name','em-subject','em-body'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    await loadEmailCampaigns();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function sendEmailCampaign(id) {
  showToast('Sending campaign…','info');
  try {
    await fetch(`/api/email/campaigns/${id}/send`,{method:'POST'});
    await loadEmailCampaigns();
    showToast('Campaign sent!');
  } catch(e) { showToast('Send failed','error'); }
}

async function showCampaignStats(id) {
  const card = document.getElementById('em-stats-card');
  const body = document.getElementById('em-stats-body');
  card.style.display = 'block';
  body.innerHTML = '<span style="color:var(--gold)">Loading stats…</span>';
  try {
    const s = await fetch(`/api/email/campaigns/${id}/stats`).then(r=>r.json());
    body.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:.84em">
        <div style="text-align:center"><div style="font-size:1.4em;font-weight:700;color:#3b82f6">${s.sent}</div><div style="color:var(--text-muted)">Sent</div></div>
        <div style="text-align:center"><div style="font-size:1.4em;font-weight:700;color:#10b981">${s.opens}</div><div style="color:var(--text-muted)">Opens (${s.open_rate}%)</div></div>
        <div style="text-align:center"><div style="font-size:1.4em;font-weight:700;color:#f59e0b">${s.clicks}</div><div style="color:var(--text-muted)">Clicks (${s.click_rate}%)</div></div>
      </div>`;
  } catch(e) { body.innerHTML='<span style="color:#ef4444">Error loading stats</span>'; }
}

async function aiWriteEmail() {
  const goal = document.getElementById('em-write-goal').value.trim();
  if (!goal) { showToast('Enter a goal first','error'); return; }
  const res = document.getElementById('em-write-result');
  res.innerHTML = '<span style="color:var(--gold)">◈ Generating with AI…</span>';
  try {
    const r = await fetch('/api/email/write',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      goal, tone:document.getElementById('em-write-tone').value,
      audience:document.getElementById('em-write-audience').value
    })});
    const data = await r.json();
    res.innerHTML = `<div style="margin-top:8px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;font-size:.83em">
      <div style="font-weight:700;color:var(--gold);margin-bottom:6px">Subject: ${escHtml(data.subject)}</div>
      <pre style="white-space:pre-wrap;color:var(--text-secondary);font-family:inherit;margin:0">${escHtml(data.body)}</pre>
      <div style="margin-top:8px;display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" style="font-size:.72em" data-subject="${escHtml(data.subject)}" data-body="${encodeURIComponent(data.body)}" onclick="populateEmailFormFromEl(this)">→ Use in Campaign</button>
      </div>
    </div>`;
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

function populateEmailForm(subject, bodyEncoded) {
  document.getElementById('em-subject').value = subject;
  document.getElementById('em-body').value = decodeURIComponent(bodyEncoded);
  showToast('Email content copied to form');
}
function populateEmailFormFromEl(btn) {
  const subject = btn.dataset.subject || '';
  const bodyEncoded = btn.dataset.body || '';
  populateEmailForm(subject, bodyEncoded);
}

async function deleteEmailCampaign(id) {
  if (!confirm('Delete this campaign?')) return;
  await fetch(`/api/email/campaigns/${id}`,{method:'DELETE'});
  await loadEmailCampaigns();
  showToast('Campaign deleted');
}

// ═══════════════════════════════════════════════════════════════════
// Meetings
// ═══════════════════════════════════════════════════════════════════
async function loadMeetings() {
  try {
    const meetings = await fetch('/api/meetings').then(r=>r.json());
    const el = document.getElementById('meetings-list');
    if (!meetings.length) { el.innerHTML='<div class="empty"><div class="icon">🗓️</div><p>No meetings yet.</p></div>'; return; }
    el.innerHTML = meetings.map(m=>`
      <div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <strong style="color:var(--text)">${escHtml(m.title)}</strong>
          <span style="font-size:.75em;color:var(--text-muted)">${m.date?m.date.split('T')[0]:''}</span>
        </div>
        ${m.participants?.length?`<div style="color:var(--text-muted);font-size:.78em">👥 ${m.participants.join(', ')}</div>`:''}
        ${m.summary?`<div style="color:#a78bfa;font-size:.78em;margin-top:3px">${escHtml(m.summary.slice(0,80))}…</div>`:''}
        <div style="margin-top:6px;display:flex;gap:5px;flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" style="font-size:.72em" onclick="viewMeeting('${m.id}')">📋 View</button>
          ${m.transcript?`<button class="btn btn-ghost btn-sm" style="font-size:.72em;color:var(--gold)" onclick="summarizeMeeting('${m.id}')">◈ Summarize</button>`:''}
          <button class="btn btn-ghost btn-sm" style="font-size:.72em;color:var(--gold)" onclick="generateMeetingFollowup('${m.id}')">📧 Follow-up</button>
          <button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#ef4444" onclick="deleteMeeting('${m.id}')">🗑</button>
        </div>
      </div>`).join('');
  } catch(e) { console.error('Meetings load error',e); }
}

async function addMeeting() {
  const title = document.getElementById('mtg-title').value.trim();
  if (!title) { showToast('Title is required','error'); return; }
  const res = document.getElementById('mtg-add-result');
  res.innerHTML = '<span style="color:var(--gold)">Saving…</span>';
  const participants = document.getElementById('mtg-participants').value.split(',').map(p=>p.trim()).filter(Boolean);
  try {
    const r = await fetch('/api/meetings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      title, date:document.getElementById('mtg-date').value,
      participants, transcript:document.getElementById('mtg-transcript').value,
      meeting_type:document.getElementById('mtg-type').value,
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = '<span style="color:#10b981">✅ Meeting saved!</span>';
    ['mtg-title','mtg-date','mtg-participants','mtg-transcript'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    await loadMeetings();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function viewMeeting(id) {
  const card = document.getElementById('meeting-detail-card');
  const body = document.getElementById('meeting-detail-body');
  card.style.display = 'block';
  body.innerHTML = '<span style="color:var(--gold)">Loading…</span>';
  try {
    const m = await fetch(`/api/meetings/${id}`).then(r=>r.json());
    body.innerHTML = `
      <div style="font-size:.84em">
        <div style="font-size:1em;font-weight:700;color:var(--text);margin-bottom:8px">${escHtml(m.title)}</div>
        <div style="color:var(--text-muted);margin-bottom:8px">${m.date?m.date.replace('T',' ').split('.')[0]:''} • ${m.participants?.join(', ')||'No participants'}</div>
        ${m.summary?`<div style="background:rgba(167,139,250,.1);border:1px solid rgba(167,139,250,.3);border-radius:6px;padding:8px;margin-bottom:8px"><strong style="color:#a78bfa">Summary:</strong><br>${escHtml(m.summary)}</div>`:''}
        ${m.action_items?.length?`<div style="margin-bottom:8px"><strong style="color:var(--gold)">Action Items:</strong><ul style="margin:4px 0 0 16px;color:var(--text-secondary)">${m.action_items.map(a=>`<li>${typeof a==='object'?escHtml(a.item||JSON.stringify(a)):escHtml(a)}</li>`).join('')}</ul></div>`:''}
        ${m.followup_email?`<div style="background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);border-radius:6px;padding:8px"><strong style="color:#10b981">Follow-up Draft:</strong><pre style="white-space:pre-wrap;font-family:inherit;font-size:.9em;margin-top:4px;color:var(--text-secondary)">${escHtml(m.followup_email)}</pre></div>`:''}
      </div>`;
  } catch(e) { body.innerHTML='<span style="color:#ef4444">Error loading meeting</span>'; }
}

async function summarizeMeeting(id) {
  showToast('AI summarizing…','info');
  try {
    await fetch(`/api/meetings/${id}/summarize`,{method:'POST'});
    await loadMeetings();
    if (document.getElementById('meeting-detail-card').style.display!=='none') viewMeeting(id);
    showToast('Meeting summarized!');
  } catch(e) { showToast('Summarize failed','error'); }
}

async function generateMeetingFollowup(id) {
  showToast('Generating follow-up…','info');
  try {
    await fetch(`/api/meetings/${id}/followup`,{method:'POST'});
    await loadMeetings();
    if (document.getElementById('meeting-detail-card').style.display!=='none') viewMeeting(id);
    showToast('Follow-up email generated!');
  } catch(e) { showToast('Generation failed','error'); }
}

async function deleteMeeting(id) {
  if (!confirm('Delete this meeting?')) return;
  await fetch(`/api/meetings/${id}`,{method:'DELETE'});
  await loadMeetings();
  showToast('Meeting deleted');
}

// ── Assign task to agent from swarm ──────────────────────────────────────────
function assignTaskToAgent(agentId) {
  switchTab('tasks', null);
  setTimeout(() => {
    const taskInput = document.getElementById('task-input');
    if (taskInput) {
      taskInput.focus();
      taskInput.placeholder = `Describe what you want ${agentId} to do…`;
    }
    if (typeof showManualAgentPicker === 'function') showManualAgentPicker();
    setTimeout(() => {
      const checkbox = document.querySelector(`[data-agent-id="${agentId}"]`);
      if (checkbox) checkbox.click();
    }, 300);
  }, 200);
}
// ═══════════════════════════════════════════════════════════════════
// Social Scheduler
// ═══════════════════════════════════════════════════════════════════
const PLATFORM_EMOJIS = {twitter:'🐦',instagram:'📷',linkedin:'💼',tiktok:'🎵',facebook:'👤',youtube:'▶️'};

async function loadSocialPosts() {
  try {
    const [posts, stats] = await Promise.all([
      fetch('/api/social/posts?platform='+encodeURIComponent(document.getElementById('soc-filter-platform')?.value||'')).then(r=>r.json()),
      fetch('/api/social/stats').then(r=>r.json())
    ]);
    document.getElementById('soc-stat-scheduled').textContent = stats.scheduled||0;
    document.getElementById('soc-stat-posted').textContent = stats.posted||0;
    document.getElementById('soc-stat-draft').textContent = stats.draft||0;
    document.getElementById('soc-stat-total').textContent = stats.total||0;
    const el = document.getElementById('social-posts-list');
    if (!posts.length) { el.innerHTML='<div class="empty"><div class="icon">📱</div><p>No posts scheduled yet.</p></div>'; return; }
    el.innerHTML = posts.map(p=>{
      const statusColor = p.status==='posted'?'#10b981':p.status==='scheduled'?'#3b82f6':p.status==='failed'?'#ef4444':'#64748b';
      return `<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span>${PLATFORM_EMOJIS[p.platform]||'📱'} <strong style="color:var(--text)">${p.platform}</strong></span>
          <span style="font-size:.75em;color:${statusColor}">${p.status}</span>
        </div>
        <div style="color:var(--text-secondary);font-size:.82em">${escHtml(p.content.slice(0,100))}${p.content.length>100?'…':''}</div>
        <div style="color:var(--text-muted);font-size:.75em;margin-top:3px">📅 ${p.scheduled_at?p.scheduled_at.replace('T',' ').slice(0,16):''}</div>
        <div style="margin-top:6px;display:flex;gap:5px">
          ${p.status==='scheduled'?`<button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#10b981" onclick="publishSocialPost('${p.id}')">✅ Publish</button>`:''}
          <button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#ef4444" onclick="deleteSocialPost('${p.id}')">🗑</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.error('Social load error',e); }
}

async function schedulePost() {
  const content = document.getElementById('soc-content').value.trim();
  const scheduled_at = document.getElementById('soc-schedule-at').value;
  if (!content || !scheduled_at) { showToast('Content and schedule time required','error'); return; }
  const res = document.getElementById('soc-add-result');
  res.innerHTML = '<span style="color:var(--gold)">Scheduling…</span>';
  try {
    const r = await fetch('/api/social/posts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      platform:document.getElementById('soc-platform').value,
      content, scheduled_at:new Date(scheduled_at).toISOString(),
      campaign:document.getElementById('soc-campaign').value,
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = '<span style="color:#10b981">✅ Post scheduled!</span>';
    ['soc-content','soc-schedule-at','soc-campaign'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    await loadSocialPosts();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function publishSocialPost(id) {
  await fetch(`/api/social/posts/${id}/publish`,{method:'POST'});
  await loadSocialPosts();
  showToast('Post marked as published!');
}

async function deleteSocialPost(id) {
  if (!confirm('Delete this post?')) return;
  await fetch(`/api/social/posts/${id}`,{method:'DELETE'});
  await loadSocialPosts();
  showToast('Post deleted');
}

async function processScheduledPosts() {
  showToast('Processing due posts…','info');
  try {
    const r = await fetch('/api/social/process-due',{method:'POST'}).then(r=>r.json());
    await loadSocialPosts();
    showToast(`Auto-posted ${r.count} post${r.count!==1?'s':''}`);
  } catch(e) { showToast('Error processing posts','error'); }
}

async function generateSocialContent() {
  const topic = document.getElementById('soc-gen-topic').value.trim();
  if (!topic) { showToast('Enter a topic first','error'); return; }
  const res = document.getElementById('soc-gen-result');
  res.innerHTML = '<span style="color:var(--gold)">◈ Generating…</span>';
  try {
    const r = await fetch('/api/social/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      topic, platform:document.getElementById('soc-gen-platform').value
    })});
    const data = await r.json();
    res.innerHTML = `<div style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px;font-size:.83em">
      <div style="color:var(--text-secondary)">${escHtml(data.content)}</div>
      ${data.hashtags?.length?`<div style="color:#6366f1;margin-top:4px;font-size:.85em">${data.hashtags.map(h=>'#'+h.replace('#','')).join(' ')}</div>`:''}
      <button class="btn btn-ghost btn-sm" style="margin-top:6px;font-size:.72em" onclick="document.getElementById('soc-content').value='${encodeURIComponent(data.content+' '+data.hashtags.map(h=>'#'+h.replace('#','')).join(' '))}'; showToast('Content copied to form')">→ Use Content</button>
    </div>`;
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

// ═══════════════════════════════════════════════════════════════════
// CEO Briefing
// ═══════════════════════════════════════════════════════════════════
async function loadCEOBriefing() {
  try {
    const b = await fetch('/api/briefing/today').then(r=>r.json());
    renderBriefingWidget(b, document.getElementById('dash-ceo-briefing'));
  } catch(e) { console.error('Briefing load error',e); }
}

async function loadFullBriefing() {
  try {
    const b = await fetch('/api/briefing/today').then(r=>r.json());
    renderBriefingFull(b);
    loadBriefingHistory();
  } catch(e) { console.error('Briefing load error',e); }
}

async function forceRegenerateBriefing() {
  showToast('Regenerating briefing…','info');
  try {
    const b = await fetch('/api/briefing/generate',{method:'POST'}).then(r=>r.json());
    renderBriefingWidget(b, document.getElementById('dash-ceo-briefing'));
    if (currentTab==='briefing') renderBriefingFull(b);
    showToast('Briefing regenerated!');
  } catch(e) { showToast('Regeneration failed','error'); }
}

function renderBriefingWidget(b, el) {
  if (!el) return;
  const m = b.metrics||{};
  el.innerHTML = `
    <div style="padding:4px 0">
      <div style="font-size:.9em;font-weight:700;color:#818cf8;margin-bottom:6px">${escHtml(b.headline||b.date||'Briefing')}</div>
      <div style="font-size:.83em;color:var(--text-secondary);margin-bottom:10px;line-height:1.5">${escHtml(b.summary||'')}</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;font-size:.78em;text-align:center;margin-bottom:10px">
        <div style="background:rgba(16,185,129,.1);border-radius:6px;padding:6px"><div style="font-weight:700;color:#10b981">$${Number(m.revenue_paid||0).toLocaleString()}</div><div style="color:var(--text-muted)">Revenue</div></div>
        <div style="background:rgba(59,130,246,.1);border-radius:6px;padding:6px"><div style="font-weight:700;color:#3b82f6">${m.leads_total||0}</div><div style="color:var(--text-muted)">Leads</div></div>
        <div style="background:rgba(245,158,11,.1);border-radius:6px;padding:6px"><div style="font-weight:700;color:#f59e0b">${m.chat_messages_today||0}</div><div style="color:var(--text-muted)">Messages</div></div>
      </div>
    </div>`;
}

function renderBriefingFull(b) {
  const el = document.getElementById('briefing-today-body');
  if (!el) return;
  const m = b.metrics||{};
  const sec = b.sections||{};
  el.innerHTML = `
    <div style="font-size:.84em">
      <div style="font-size:1.1em;font-weight:700;color:#818cf8;margin-bottom:10px">${escHtml(b.headline||b.date)}</div>
      <div style="color:var(--text-secondary);line-height:1.6;margin-bottom:16px">${escHtml(b.summary||'')}</div>
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:16px">
        <div style="background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.2);border-radius:8px;padding:12px;text-align:center"><div style="font-size:1.6em;font-weight:800;color:#10b981">$${Number(m.revenue_paid||0).toLocaleString()}</div><div style="color:var(--text-muted);font-size:.8em">Revenue (Paid)</div></div>
        <div style="background:rgba(59,130,246,.1);border:1px solid rgba(59,130,246,.2);border-radius:8px;padding:12px;text-align:center"><div style="font-size:1.6em;font-weight:800;color:#3b82f6">$${Number(m.pipeline_value||0).toLocaleString()}</div><div style="color:var(--text-muted);font-size:.8em">Pipeline Value</div></div>
      </div>
      ${sec.action_items?.length?`<div style="margin-bottom:12px"><div style="font-weight:700;color:var(--gold);margin-bottom:6px">🎯 Action Items</div><ul style="margin:0 0 0 16px;color:var(--text-secondary)">${sec.action_items.map(a=>`<li style="margin-bottom:3px">${escHtml(a)}</li>`).join('')}</ul></div>`:''}
      ${sec.risks?.length?`<div><div style="font-weight:700;color:#ef4444;margin-bottom:6px">⚠️ Risks &amp; Alerts</div><ul style="margin:0 0 0 16px;color:var(--text-secondary)">${sec.risks.map(r=>`<li style="margin-bottom:3px">${escHtml(r)}</li>`).join('')}</ul></div>`:''}
      <div style="margin-top:10px;font-size:.75em;color:var(--text-muted)">Generated: ${b.generated_at||b.date} ${b.ai_generated?'• AI-powered':'• Heuristic'}</div>
    </div>`;
}

async function loadBriefingHistory() {
  try {
    const briefings = await fetch('/api/briefing/history').then(r=>r.json());
    const el = document.getElementById('briefing-history-list');
    if (!briefings.length) { el.innerHTML='<div class="empty"><div class="icon">📰</div><p>No past briefings.</p></div>'; return; }
    el.innerHTML = briefings.slice(0,10).map(b=>`
      <div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em;cursor:pointer" onclick='renderBriefingFull(${JSON.stringify(b)})'>
        <div style="font-weight:600;color:var(--text)">${escHtml(b.date)} ${b.ai_generated?'<span style="color:#818cf8;font-size:.75em">AI</span>':''}</div>
        <div style="color:var(--text-muted);font-size:.78em">${escHtml((b.summary||'').slice(0,70))}…</div>
      </div>`).join('');
  } catch(e) { console.error('Briefing history error',e); }
}

// ═══════════════════════════════════════════════════════════════════
// Financial Tools
// ═══════════════════════════════════════════════════════════════════
function switchFinTab(panel, btn) {
  ['invoices','quotes','expenses','pl'].forEach(p=>{
    const el = document.getElementById('fin-panel-'+p);
    if (el) el.style.display = p===panel?'block':'none';
  });
  document.querySelectorAll('.fin-tab-btn').forEach(b=>b.classList.remove('active','btn-primary'));
  document.querySelectorAll('.fin-tab-btn').forEach(b=>b.classList.add('btn-ghost'));
  btn.classList.remove('btn-ghost');
  btn.classList.add('active','btn-primary');
  if (panel==='invoices') loadInvoices();
  else if (panel==='quotes') loadQuotes();
  else if (panel==='expenses') loadExpenses();
  else if (panel==='pl') loadPL();
}

async function loadInvoices() {
  try {
    const status = document.getElementById('inv-filter-status')?.value||'';
    const invs = await fetch('/api/financial/invoices'+(status?'?status='+status:'')).then(r=>r.json());
    const el = document.getElementById('invoices-list');
    if (!invs.length) { el.innerHTML='<div class="empty"><div class="icon">🧾</div><p>No invoices yet.</p></div>'; return; }
    const statusColor = s => s==='paid'?'#10b981':s==='sent'?'#3b82f6':s==='overdue'?'#ef4444':s==='draft'?'#64748b':'#f59e0b';
    el.innerHTML = invs.map(inv=>`
      <div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
          <strong style="color:var(--text)">${escHtml(inv.invoice_number)}</strong>
          <span style="color:${statusColor(inv.status)};font-size:.8em;font-weight:700">${inv.status.toUpperCase()}</span>
        </div>
        <div style="color:var(--text-secondary)">${escHtml(inv.client_name)} • <strong style="color:#10b981">$${Number(inv.total||0).toLocaleString()}</strong></div>
        <div style="color:var(--text-muted);font-size:.75em">Due: ${inv.due_date||'—'}</div>
        <div style="margin-top:6px;display:flex;gap:5px;flex-wrap:wrap">
          ${inv.status==='draft'?`<button class="btn btn-ghost btn-sm" style="font-size:.72em" onclick="sendInvoice('${inv.id}')">📧 Send</button>`:''}
          ${inv.status!=='paid'?`<button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#10b981" onclick="payInvoice('${inv.id}')">✅ Paid</button>`:''}
          <button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#ef4444" onclick="deleteInvoice('${inv.id}')">🗑</button>
        </div>
      </div>`).join('');
  } catch(e) { console.error('Invoice load error',e); }
}

async function createInvoice() {
  const client = document.getElementById('inv-client').value.trim();
  if (!client) { showToast('Client name required','error'); return; }
  let items = [];
  try { items = JSON.parse(document.getElementById('inv-items').value||'[]'); } catch(e) { showToast('Invalid items JSON','error'); return; }
  const res = document.getElementById('inv-create-result');
  res.innerHTML = '<span style="color:var(--gold)">Creating…</span>';
  try {
    const r = await fetch('/api/financial/invoices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      client_name:client, client_email:document.getElementById('inv-email').value,
      items, due_date:document.getElementById('inv-due').value||undefined,
      notes:document.getElementById('inv-notes').value,
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = `<span style="color:#10b981">✅ Invoice ${escHtml(data.invoice_number)} created!</span>`;
    ['inv-client','inv-email','inv-items','inv-due','inv-notes'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    await loadInvoices();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function sendInvoice(id) {
  await fetch(`/api/financial/invoices/${id}/send`,{method:'POST'});
  await loadInvoices();
  showToast('Invoice marked as sent');
}

async function payInvoice(id) {
  await fetch(`/api/financial/invoices/${id}/pay`,{method:'POST'});
  await loadInvoices();
  showToast('Invoice marked as paid!');
}

async function deleteInvoice(id) {
  if (!confirm('Delete invoice?')) return;
  await fetch(`/api/financial/invoices/${id}`,{method:'DELETE'});
  await loadInvoices();
  showToast('Invoice deleted');
}

async function checkOverdueInvoices() {
  const r = await fetch('/api/financial/reminders').then(r=>r.json());
  showToast(`${r.newly_marked?.length||0} invoices marked overdue, ${r.all_overdue?.length||0} total overdue`);
  await loadInvoices();
}

async function loadQuotes() {
  try {
    const quotes = await fetch('/api/financial/quotes').then(r=>r.json());
    const el = document.getElementById('quotes-list');
    if (!quotes.length) { el.innerHTML='<div class="empty"><div class="icon">📄</div><p>No quotes yet.</p></div>'; return; }
    el.innerHTML = quotes.map(q=>`
      <div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
          <strong style="color:var(--text)">${escHtml(q.quote_number)}</strong>
          <span style="color:#10b981;font-weight:700">$${Number(q.total||0).toLocaleString()}</span>
        </div>
        <div style="color:var(--text-secondary)">${escHtml(q.client_name)}</div>
        <div style="color:var(--text-muted);font-size:.75em">Valid until: ${q.valid_until||'—'}</div>
        <button class="btn btn-ghost btn-sm" style="margin-top:5px;font-size:.72em;color:#ef4444" onclick="deleteQuote('${q.id}')">🗑 Delete</button>
      </div>`).join('');
  } catch(e) { console.error('Quotes load error',e); }
}

async function createQuote() {
  const client = document.getElementById('quo-client').value.trim();
  if (!client) { showToast('Client name required','error'); return; }
  let items = [];
  try { items = JSON.parse(document.getElementById('quo-items').value||'[]'); } catch(e) { showToast('Invalid items JSON','error'); return; }
  const res = document.getElementById('quo-create-result');
  res.innerHTML = '<span style="color:var(--gold)">Creating…</span>';
  try {
    const r = await fetch('/api/financial/quotes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      client_name:client, client_email:document.getElementById('quo-email').value,
      items, valid_until:document.getElementById('quo-valid').value||undefined,
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = `<span style="color:#10b981">✅ Quote ${escHtml(data.quote_number)} created!</span>`;
    await loadQuotes();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function deleteQuote(id) {
  if (!confirm('Delete quote?')) return;
  await fetch(`/api/financial/quotes/${id}`,{method:'DELETE'});
  await loadQuotes();
  showToast('Quote deleted');
}

async function loadExpenses() {
  try {
    const expenses = await fetch('/api/financial/expenses').then(r=>r.json());
    const el = document.getElementById('expenses-list');
    if (!expenses.length) { el.innerHTML='<div class="empty"><div class="icon">💸</div><p>No expenses yet.</p></div>'; return; }
    const total = expenses.reduce((s,e)=>s+Number(e.amount||0),0);
    el.innerHTML = `<div style="padding:8px 0;border-bottom:1px solid rgba(16,185,129,.2);margin-bottom:6px;font-size:.84em;font-weight:700;color:#ef4444">Total: $${total.toLocaleString(undefined,{minimumFractionDigits:2})}</div>`+
    expenses.map(exp=>`
      <div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em;display:flex;justify-content:space-between;align-items:center">
        <div><div style="font-weight:600;color:var(--text)">${escHtml(exp.description)}</div><div style="color:var(--text-muted);font-size:.78em">${escHtml(exp.category)} • ${exp.date}</div></div>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="color:#ef4444;font-weight:700">$${Number(exp.amount||0).toLocaleString()}</span>
          <button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#ef4444" onclick="deleteExpense('${exp.id}')">🗑</button>
        </div>
      </div>`).join('');
  } catch(e) { console.error('Expenses load error',e); }
}

async function addExpense() {
  const desc = document.getElementById('exp-desc').value.trim();
  const amount = parseFloat(document.getElementById('exp-amount').value||0);
  if (!desc || !amount) { showToast('Description and amount required','error'); return; }
  const res = document.getElementById('exp-add-result');
  res.innerHTML = '<span style="color:var(--gold)">Adding…</span>';
  try {
    const r = await fetch('/api/financial/expenses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      description:desc, amount, category:document.getElementById('exp-category').value,
      date:document.getElementById('exp-date').value||undefined,
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = '<span style="color:#10b981">✅ Expense added!</span>';
    ['exp-desc','exp-amount','exp-date'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    await loadExpenses();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function deleteExpense(id) {
  if (!confirm('Delete expense?')) return;
  await fetch(`/api/financial/expenses/${id}`,{method:'DELETE'});
  await loadExpenses();
  showToast('Expense deleted');
}

async function loadPL() {
  try {
    const pl = await fetch('/api/financial/pl').then(r=>r.json());
    const el = document.getElementById('pl-body');
    const profitColor = pl.profit>=0?'#10b981':'#ef4444';
    el.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;font-size:.84em;margin-bottom:16px">
        <div style="background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.2);border-radius:8px;padding:14px;text-align:center">
          <div style="font-size:1.8em;font-weight:800;color:#10b981">$${Number(pl.revenue||0).toLocaleString()}</div>
          <div style="color:var(--text-muted)">Revenue (Paid)</div>
          <div style="color:var(--text-muted);font-size:.8em">${pl.paid_invoices||0} paid invoices</div>
        </div>
        <div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.2);border-radius:8px;padding:14px;text-align:center">
          <div style="font-size:1.8em;font-weight:800;color:#ef4444">$${Number(pl.expenses||0).toLocaleString()}</div>
          <div style="color:var(--text-muted)">Expenses</div>
          <div style="color:var(--text-muted);font-size:.8em">${pl.expense_count||0} entries</div>
        </div>
        <div style="background:rgba(212,175,55,.08);border:1px solid rgba(212,175,55,.2);border-radius:8px;padding:14px;text-align:center">
          <div style="font-size:1.8em;font-weight:800;color:${profitColor}">$${Number(pl.profit||0).toLocaleString()}</div>
          <div style="color:var(--text-muted)">Net Profit</div>
        </div>
        <div style="background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.2);border-radius:8px;padding:14px;text-align:center">
          <div style="font-size:1.8em;font-weight:800;color:#f59e0b">${pl.profit_margin||0}%</div>
          <div style="color:var(--text-muted)">Profit Margin</div>
        </div>
      </div>
      ${pl.overdue_invoices>0?`<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:12px;font-size:.84em"><span style="color:#ef4444;font-weight:700">⚠️ ${pl.overdue_invoices} overdue invoice${pl.overdue_invoices!==1?'s':''}</span> — <span style="color:var(--text-muted)">pending revenue: $${Number(pl.pending_revenue||0).toLocaleString()}</span></div>`:''}`;
  } catch(e) { document.getElementById('pl-body').innerHTML='<span style="color:#ef4444">Error loading P&L</span>'; }
}

// ═══════════════════════════════════════════════════════════════════
// Competitors
// ═══════════════════════════════════════════════════════════════════
async function loadCompetitors() {
  try {
    const comps = await fetch('/api/competitors').then(r=>r.json());
    const el = document.getElementById('competitors-list');
    if (!comps.length) { el.innerHTML='<div class="empty"><div class="icon">🕵️</div><p>No competitors tracked yet.</p></div>'; return; }
    el.innerHTML = comps.map(c=>`
      <div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <strong style="color:var(--text)">${escHtml(c.name)}</strong>
          <span style="font-size:.75em;color:var(--text-muted)">${c.last_analyzed?'Analyzed '+c.last_analyzed.split('T')[0]:'Not analyzed'}</span>
        </div>
        ${c.website?`<div style="color:#6366f1;font-size:.78em">${escHtml(c.website)}</div>`:''}
        ${c.analysis?`<div style="color:var(--text-muted);font-size:.78em;margin-top:3px">${escHtml(c.analysis.slice(0,80))}…</div>`:''}
        <div style="margin-top:6px;display:flex;gap:5px">
          <button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#818cf8" onclick="analyzeCompetitor('${c.id}')">◈ Analyze</button>
          <button class="btn btn-ghost btn-sm" style="font-size:.72em" onclick="viewCompetitorDetail('${c.id}')">🔍 View</button>
          <button class="btn btn-ghost btn-sm" style="font-size:.72em;color:#ef4444" onclick="deleteCompetitor('${c.id}')">🗑</button>
        </div>
      </div>`).join('');
  } catch(e) { console.error('Competitors load error',e); }
}

async function addCompetitor() {
  const name = document.getElementById('comp-name').value.trim();
  if (!name) { showToast('Name is required','error'); return; }
  const res = document.getElementById('comp-add-result');
  res.innerHTML = '<span style="color:var(--gold)">Adding…</span>';
  try {
    const r = await fetch('/api/competitors',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      name, website:document.getElementById('comp-website').value,
      pricing:document.getElementById('comp-pricing').value,
      target_market:document.getElementById('comp-market').value,
      notes:document.getElementById('comp-notes').value,
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = '<span style="color:#10b981">✅ Competitor added!</span>';
    ['comp-name','comp-website','comp-pricing','comp-market','comp-notes'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    await loadCompetitors();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function analyzeCompetitor(id) {
  showToast('AI analyzing competitor…','info');
  try {
    await fetch(`/api/competitors/${id}/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
    await loadCompetitors();
    await loadCompetitorAlerts();
    showToast('Analysis complete!');
  } catch(e) { showToast('Analysis failed','error'); }
}

async function viewCompetitorDetail(id) {
  const card = document.getElementById('comp-detail-card');
  const body = document.getElementById('comp-detail-body');
  card.style.display = 'block';
  body.innerHTML = '<span style="color:var(--gold)">Loading…</span>';
  try {
    const c = await fetch(`/api/competitors/${id}`).then(r=>r.json());
    body.innerHTML = `
      <div style="font-size:.84em">
        <div style="font-weight:700;color:var(--text);font-size:1.05em;margin-bottom:8px">${escHtml(c.name)}</div>
        ${c.analysis?`<div style="color:var(--text-secondary);margin-bottom:10px">${escHtml(c.analysis)}</div>`:'<div style="color:var(--text-muted);margin-bottom:10px">Not yet analyzed.</div>'}
        ${c.strengths?.length?`<div style="margin-bottom:6px"><strong style="color:#10b981">Strengths:</strong> ${c.strengths.map(s=>`<span style="font-size:.85em;color:var(--text-secondary)">${escHtml(s)}</span>`).join(', ')}</div>`:''}
        ${c.weaknesses?.length?`<div style="margin-bottom:6px"><strong style="color:#ef4444">Weaknesses:</strong> ${c.weaknesses.map(w=>`<span style="font-size:.85em;color:var(--text-secondary)">${escHtml(w)}</span>`).join(', ')}</div>`:''}
        ${c.opportunities?.length?`<div style="margin-bottom:6px"><strong style="color:#f59e0b">Opportunities:</strong> ${c.opportunities.map(o=>`<span style="font-size:.85em;color:var(--text-secondary)">${escHtml(o)}</span>`).join(', ')}</div>`:''}
        ${c.threats?.length?`<div><strong style="color:#8b5cf6">Threats:</strong> ${c.threats.map(t=>`<span style="font-size:.85em;color:var(--text-secondary)">${escHtml(t)}</span>`).join(', ')}</div>`:''}
      </div>`;
  } catch(e) { body.innerHTML='<span style="color:#ef4444">Error loading competitor</span>'; }
}

async function deleteCompetitor(id) {
  if (!confirm('Remove this competitor from tracking?')) return;
  await fetch(`/api/competitors/${id}`,{method:'DELETE'});
  await loadCompetitors();
  showToast('Competitor removed');
}

async function loadCompetitorAlerts() {
  try {
    const alerts = await fetch('/api/competitors/alerts').then(r=>r.json());
    const el = document.getElementById('competitor-alerts-list');
    if (!alerts.length) { el.innerHTML='<div class="empty"><div class="icon">✅</div><p>No alerts.</p></div>'; return; }
    el.innerHTML = alerts.slice(0,10).map(a=>`
      <div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.84em">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
          <strong style="color:var(--text)">${escHtml(a.competitor_name)}</strong>
          <span style="font-size:.72em;color:var(--text-muted)">${a.created_at?a.created_at.split('T')[0]:''}</span>
        </div>
        <div style="color:var(--text-secondary);font-size:.82em">${escHtml(a.message)}</div>
        <button class="btn btn-ghost btn-sm" style="margin-top:4px;font-size:.7em" onclick="dismissCompetitorAlert('${a.id}')">✓ Dismiss</button>
      </div>`).join('');
  } catch(e) {}
}

async function dismissCompetitorAlert(id) {
  await fetch(`/api/competitors/alerts/${id}/dismiss`,{method:'POST'});
  await loadCompetitorAlerts();
}

// ═══════════════════════════════════════════════════════════════════
// Content Calendar
// ═══════════════════════════════════════════════════════════════════
async function loadContentCalendar() {
  try {
    const platform = document.getElementById('cc-filter-platform')?.value||'';
    const status = document.getElementById('cc-filter-status')?.value||'';
    const qs = new URLSearchParams();
    if (platform) qs.set('platform',platform);
    if (status) qs.set('status',status);
    const {entries, stats} = await fetch('/api/content-calendar?'+qs.toString()).then(r=>r.json());
    document.getElementById('cc-stat-total').textContent = stats.total||0;
    document.getElementById('cc-stat-ideas').textContent = stats.by_status?.idea||0;
    document.getElementById('cc-stat-scheduled').textContent = stats.scheduled_upcoming||0;
    document.getElementById('cc-stat-published').textContent = stats.published_this_month||0;
    const el = document.getElementById('content-calendar-entries');
    if (!entries.length) { el.innerHTML='<div class="empty"><div class="icon">🗃️</div><p>No calendar entries. Add one or generate with AI.</p></div>'; return; }
    // Group by date
    const byDate = {};
    entries.forEach(e=>{const d=e.date||'Unknown';(byDate[d]=byDate[d]||[]).push(e);});
    const statusColors = {idea:'#64748b',draft:'#f59e0b',scheduled:'#3b82f6',published:'#10b981',archived:'#6b7280'};
    el.innerHTML = Object.entries(byDate).map(([dt,dayEntries])=>`
      <div style="margin-bottom:12px">
        <div style="font-size:.8em;font-weight:700;color:var(--gold);padding:4px 0;border-bottom:1px solid rgba(212,175,55,.2);margin-bottom:6px">${dt}</div>
        ${dayEntries.map(e=>`
          <div style="background:var(--surface2);border:1px solid rgba(255,255,255,.06);border-left:3px solid ${statusColors[e.status]||'#64748b'};border-radius:4px;padding:8px 10px;margin-bottom:5px;font-size:.83em">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>${PLATFORM_EMOJIS[e.platform]||'📱'} <strong style="color:var(--text)">${escHtml(e.title)}</strong></span>
              <div style="display:flex;gap:5px;align-items:center">
                <span style="font-size:.75em;color:${statusColors[e.status]}">${e.status}</span>
                <select style="font-size:.72em;background:var(--surface);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:1px 4px" onchange="updateCalendarStatus('${e.id}',this.value)">
                  ${['idea','draft','scheduled','published'].map(s=>`<option value="${s}"${s===e.status?' selected':''}>${s}</option>`).join('')}
                </select>
                <button class="btn btn-ghost btn-sm" style="font-size:.7em;color:#ef4444" onclick="deleteCalendarEntry('${e.id}')">🗑</button>
              </div>
            </div>
            ${e.content?`<div style="color:var(--text-muted);font-size:.82em;margin-top:3px">${escHtml(e.content.slice(0,80))}${e.content.length>80?'…':''}</div>`:''}
          </div>`).join('')}
      </div>`).join('');
  } catch(e) { console.error('Calendar load error',e); }
}

async function addCalendarEntry() {
  const date_str = document.getElementById('cc-date').value;
  const title = document.getElementById('cc-title').value.trim();
  if (!date_str || !title) { showToast('Date and title required','error'); return; }
  const res = document.getElementById('cc-add-result');
  res.innerHTML = '<span style="color:var(--gold)">Adding…</span>';
  try {
    const r = await fetch('/api/content-calendar/entries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      date:date_str, platform:document.getElementById('cc-platform').value,
      content_type:document.getElementById('cc-type').value,
      title, content:document.getElementById('cc-content').value, status:'idea'
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = '<span style="color:#10b981">✅ Entry added!</span>';
    ['cc-date','cc-title','cc-content'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    await loadContentCalendar();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

async function updateCalendarStatus(id, status) {
  await fetch(`/api/content-calendar/entries/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});
  showToast('Status updated');
}

async function deleteCalendarEntry(id) {
  if (!confirm('Delete this entry?')) return;
  await fetch(`/api/content-calendar/entries/${id}`,{method:'DELETE'});
  await loadContentCalendar();
  showToast('Entry deleted');
}

async function generateContentCalendar() {
  const niche = document.getElementById('cc-gen-niche').value.trim();
  if (!niche) { showToast('Enter your niche first','error'); return; }
  const res = document.getElementById('cc-gen-result');
  res.innerHTML = '<span style="color:var(--gold)">◈ Generating calendar… This may take a moment.</span>';
  try {
    const r = await fetch('/api/content-calendar/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      niche, days:parseInt(document.getElementById('cc-gen-days').value||30)
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = `<span style="color:#10b981">✅ Generated ${data.count} content entries!</span>`;
    await loadContentCalendar();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

// ═══════════════════════════════════════════════════════════════════
// Guardrails — Pending Actions
// ═══════════════════════════════════════════════════════════════════
function showSubmitActionForm() {
  const f = document.getElementById('submit-action-form');
  f.style.display = f.style.display==='none'?'block':'none';
}

async function loadPendingActions() {
  try {
    const {actions} = await fetch('/api/guardrails/pending-actions').then(r=>r.json());
    const el = document.getElementById('pending-actions-list');
    if (!actions.length) { el.innerHTML='<div class="empty"><div class="icon">✅</div><p>No pending actions. All clear!</p></div>'; return; }
    const riskColors = {low:'#10b981',medium:'#f59e0b',high:'#f97316',critical:'#ef4444'};
    el.innerHTML = actions.map(a=>`
      <div style="border:1px solid rgba(239,68,68,.2);border-left:3px solid ${riskColors[a.risk_level]||'#f59e0b'};border-radius:6px;padding:12px;margin-bottom:10px;font-size:.84em">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <strong style="color:var(--text)">${escHtml(a.action_type.replace(/_/g,' ').toUpperCase())}</strong>
          <span style="font-size:.78em;padding:2px 8px;border-radius:10px;background:rgba(255,255,255,.06);color:${riskColors[a.risk_level]||'#f59e0b'};font-weight:700">${(a.risk_level||'medium').toUpperCase()}</span>
        </div>
        <div style="color:var(--text-secondary);margin-bottom:8px">${escHtml(a.description)}</div>
        <div style="color:var(--text-muted);font-size:.75em;margin-bottom:8px">Submitted: ${a.created_at?.split('T')[0]||'—'} by ${escHtml(a.submitted_by||'user')}</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-success btn-sm" style="font-size:.78em" onclick="approveAction('${a.id}')">✅ Approve</button>
          <button class="btn btn-danger btn-sm" style="font-size:.78em" onclick="rejectAction('${a.id}')">❌ Reject</button>
        </div>
      </div>`).join('');
  } catch(e) { console.error('Pending actions load error',e); }
}

async function approveAction(id) {
  await fetch(`/api/guardrails/pending-actions/${id}/approve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  await loadPendingActions();
  showToast('Action approved');
}

async function rejectAction(id) {
  await fetch(`/api/guardrails/pending-actions/${id}/reject`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  await loadPendingActions();
  showToast('Action rejected');
}

async function submitPendingAction() {
  const desc = document.getElementById('pa-description').value.trim();
  if (!desc) { showToast('Description is required','error'); return; }
  let payload = {};
  try { payload = JSON.parse(document.getElementById('pa-payload').value||'{}'); } catch(e) {}
  const res = document.getElementById('pa-submit-result');
  res.innerHTML = '<span style="color:var(--gold)">Submitting…</span>';
  try {
    const r = await fetch('/api/guardrails/submit-action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      action_type:document.getElementById('pa-action-type').value,
      description:desc, risk_level:document.getElementById('pa-risk-level').value, payload,
    })});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail||'Error');
    res.innerHTML = '<span style="color:#10b981">✅ Action submitted for review!</span>';
    document.getElementById('pa-description').value = '';
    document.getElementById('pa-payload').value = '';
    await loadPendingActions();
  } catch(e) { res.innerHTML=`<span style="color:#ef4444">Error: ${e.message}</span>`; }
}

// Load CEO briefing in dashboard on startup
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(loadCEOBriefing, 1500);
});

// ══════════════════════════════════════════════════════════════════
//  FEATURE MODULE JAVASCRIPT
// ══════════════════════════════════════════════════════════════════
// ── Meetings ─────────────────────────────────────────────────────
async function loadMeetings() {
  try {
    const [meetings, stats] = await Promise.all([api('/api/meetings/'), api('/api/meetings/stats')]);
    document.getElementById('mt-total').textContent = stats.total || 0;
    document.getElementById('mt-analyzed').textContent = stats.analyzed || 0;
    document.getElementById('mt-pending').textContent = stats.pending || 0;
    document.getElementById('mt-duration').textContent = stats.total_duration_mins || 0;
    const el = document.getElementById('meetings-list');
    if (!meetings.length) { el.innerHTML = '<div class="empty"><div class="icon">🎙️</div><p>No meetings yet.</p></div>'; return; }
    el.innerHTML = meetings.map(m => `<div style="padding:10px;border-bottom:1px solid var(--border)">
      <div style="display:flex;justify-content:space-between"><strong>${m.title}</strong>
        <span style="font-size:.75em;background:var(--surface3);padding:2px 6px;border-radius:4px">${m.status}</span></div>
      <div style="font-size:.8em;color:var(--text-muted)">${m.date} · ${m.platform} · ${m.duration_mins}min</div>
      ${m.summary?`<div style="font-size:.8em;margin-top:6px;color:var(--text)">${m.summary.substring(0,120)}…</div>`:''}
      <div style="display:flex;gap:8px;margin-top:6px">
        ${m.status!=='analyzed'?`<button class="btn btn-ghost btn-sm" onclick="showMeetingAnalysis('${m.id}')" style="font-size:.75em">🤖 Show Analysis</button>`:''}
        <button class="btn btn-ghost btn-sm" onclick="deleteMeeting('${m.id}')" style="font-size:.75em">🗑</button>
      </div></div>`).join('');
  } catch(e) { console.error('Meetings load error', e); }
}
async function addMeeting() {
  const transcript = document.getElementById('mt-transcript').value;
  const payload = {
    title: document.getElementById('mt-title').value,
    platform: document.getElementById('mt-platform').value,
    duration_mins: parseInt(document.getElementById('mt-duration').value) || 0,
    transcript,
  };
  if (!payload.title) return showToast('Title required', 'error');
  const meeting = await api('/api/meetings/', 'POST', payload);
  showToast('Meeting added. Analyzing…');
  const result = await api(`/api/meetings/${meeting.id}/analyze`, 'POST', {transcript});
  document.getElementById('mt-result-card').style.display = '';
  document.getElementById('mt-result-body').textContent = result.follow_up_email || result.summary || 'Analysis complete.';
  ['mt-title','mt-transcript','mt-duration'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  loadMeetings();
}
async function showMeetingAnalysis(id) {
  const data = await api(`/api/meetings/${id}/analyze`, 'POST', {});
  document.getElementById('mt-result-card').style.display = '';
  document.getElementById('mt-result-body').textContent = data.follow_up_email || data.summary || 'No analysis.';
}
async function deleteMeeting(id) {
  await api(`/api/meetings/${id}`, 'DELETE');
  showToast('Meeting deleted');
  loadMeetings();
}

// ── Social Media ──────────────────────────────────────────────────
async function loadSocialPosts() {
  try {
    const [posts, stats] = await Promise.all([api('/api/social/posts'), api('/api/social/stats')]);
    document.getElementById('sm-total').textContent = stats.total_posts || 0;
    document.getElementById('sm-published').textContent = stats.published || 0;
    document.getElementById('sm-scheduled').textContent = stats.scheduled || 0;
    document.getElementById('sm-likes').textContent = stats.total_likes || 0;
    const el = document.getElementById('sm-posts-list');
    if (!posts.length) { el.innerHTML = '<div class="empty"><div class="icon">📱</div><p>No posts yet.</p></div>'; return; }
    el.innerHTML = posts.map(p => `<div style="padding:10px;border-bottom:1px solid var(--border)">
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div style="flex:1">
          <div style="font-size:.85em">${p.content.substring(0,120)}${p.content.length>120?'…':''}</div>
          <div style="display:flex;gap:8px;margin-top:4px;font-size:.75em;color:var(--text-muted)">
            ${(p.platforms||[]).map(pl=>`<span>${pl}</span>`).join('')}
            <span style="background:var(--surface3);padding:1px 6px;border-radius:4px">${p.status}</span>
          </div>
        </div>
        <div style="display:flex;gap:4px;margin-left:8px">
          ${p.status==='draft'?`<button class="btn btn-ghost btn-sm" onclick="publishPost('${p.id}')" style="font-size:.7em">📤</button>`:''}
          <button class="btn btn-ghost btn-sm" onclick="deletePost('${p.id}')" style="font-size:.7em">🗑</button>
        </div>
      </div></div>`).join('');
  } catch(e) { console.error('Social load error', e); }
}
async function generateSocialPost() {
  const topic = document.getElementById('sm-topic').value;
  if (!topic) return showToast('Enter a topic first', 'error');
  showToast('Generating post…');
  const data = await api('/api/social/generate', 'POST', {
    topic, platform: document.getElementById('sm-platform').value,
    tone: document.getElementById('sm-tone').value,
  });
  document.getElementById('sm-content').value = data.content || '';
}
async function saveSocialPost() {
  const content = document.getElementById('sm-content').value;
  if (!content) return showToast('Content required', 'error');
  await api('/api/social/posts', 'POST', {
    content, platforms: [document.getElementById('sm-platform').value],
  });
  document.getElementById('sm-content').value = '';
  document.getElementById('sm-topic').value = '';
  showToast('Post saved!');
  loadSocialPosts();
}
async function publishPost(id) {
  await api(`/api/social/posts/${id}/publish`, 'POST', {});
  showToast('Post published!');
  loadSocialPosts();
}
async function deletePost(id) {
  await api(`/api/social/posts/${id}`, 'DELETE');
  showToast('Post deleted');
  loadSocialPosts();
}

// ── CEO Briefing ──────────────────────────────────────────────────
async function generateBriefing() {
  showToast('Generating briefing…');
  const data = await api('/api/briefing/generate', 'POST', {});
  document.getElementById('briefing-content').textContent = data.content || 'Error generating briefing.';
  document.getElementById('briefing-date').textContent = data.date || '';
  document.getElementById('briefing-card').style.display = '';
  document.getElementById('hc-latest-msg') && (document.getElementById('hc-latest-msg').style.display = 'none');
}
async function loadBriefingHistory() {
  const data = await api('/api/briefing/history');
  const el = document.getElementById('briefing-history');
  if (!data.length) { el.innerHTML = ''; return; }
  el.innerHTML = '<div class="card"><div class="card-header"><div class="card-title">📅 Past Briefings</div></div>' +
    data.slice(-10).reverse().map(b =>
      `<div style="padding:10px;border-bottom:1px solid var(--border)"><strong>${b.date}</strong>
       <div style="font-size:.8em;color:var(--text-muted);margin-top:4px">${(b.content||'').substring(0,200)}…</div></div>`
    ).join('') + '</div>';
}

// ── Finance / Invoicing ───────────────────────────────────────────
function switchFinanceTab(tab, btn) {
  document.querySelectorAll('.fi-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  ['invoices','expenses','pl'].forEach(t => {
    const el = document.getElementById(`fi-${t}-panel`);
    if (el) el.style.display = t === tab ? '' : 'none';
  });
  if (tab === 'invoices') loadInvoices();
  if (tab === 'expenses') loadExpenses();
  if (tab === 'pl') loadPL();
}
async function loadInvoices() {
  try {
    const [invs, pl] = await Promise.all([api('/api/finance/invoices'), api('/api/finance/pl-report')]);
    document.getElementById('fi-revenue').textContent = '$' + (pl.revenue||0).toLocaleString();
    document.getElementById('fi-pending').textContent = '$' + (pl.pending_revenue||0).toLocaleString();
    document.getElementById('fi-total-inv').textContent = pl.total_invoices || 0;
    document.getElementById('fi-overdue').textContent = pl.overdue_invoices || 0;
    const el = document.getElementById('fi-invoice-list');
    if (!invs.length) { el.innerHTML = '<div class="empty"><div class="icon">🧾</div><p>No invoices yet.</p></div>'; return; }
    el.innerHTML = invs.map(i => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
      <div><strong>${i.number}</strong> — ${i.client}
        <div style="font-size:.8em;color:var(--text-muted)">Due: ${i.due_date || 'N/A'}</div></div>
      <div style="text-align:right">
        <div style="font-weight:700;color:var(--green)">$${(i.total||0).toLocaleString()}</div>
        <span style="font-size:.75em;background:var(--surface3);padding:2px 6px;border-radius:4px">${i.status}</span>
        ${i.status==='draft'?`<button class="btn btn-ghost btn-sm" onclick="sendInvoice('${i.id}')" style="font-size:.7em;display:block;margin-top:4px">📤 Send</button>`:''}
        ${i.status==='sent'?`<button class="btn btn-ghost btn-sm" onclick="markPaid('${i.id}')" style="font-size:.7em;display:block;margin-top:4px">✅ Paid</button>`:''}
      </div></div>`).join('');
  } catch(e) { console.error('Invoice load error', e); }
}
async function createInvoice() {
  const payload = {
    client: document.getElementById('fi-client').value,
    client_email: document.getElementById('fi-client-email').value,
    subtotal: parseFloat(document.getElementById('fi-subtotal').value) || 0,
    tax_rate: parseFloat(document.getElementById('fi-tax').value) || 0,
    due_date: document.getElementById('fi-due').value,
    notes: document.getElementById('fi-notes').value,
  };
  if (!payload.client) return showToast('Client name required', 'error');
  await api('/api/finance/invoices', 'POST', payload);
  ['fi-client','fi-client-email','fi-subtotal','fi-tax','fi-due','fi-notes'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Invoice created!');
  loadInvoices();
}
async function sendInvoice(id) {
  await api(`/api/finance/invoices/${id}/send`, 'POST', {});
  showToast('Invoice sent!');
  loadInvoices();
}
async function markPaid(id) {
  await api(`/api/finance/invoices/${id}/mark-paid`, 'POST', {});
  showToast('Invoice marked as paid!');
  loadInvoices();
}
async function loadExpenses() {
  const expenses = await api('/api/finance/expenses');
  const el = document.getElementById('fi-expense-list');
  if (!expenses.length) { el.innerHTML = '<div class="empty"><div class="icon">💸</div><p>No expenses yet.</p></div>'; return; }
  el.innerHTML = expenses.map(e => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between">
    <div><strong>${e.description}</strong><div style="font-size:.8em;color:var(--text-muted)">${e.category} · ${e.date}</div></div>
    <div style="font-weight:700;color:#ef4444">-$${(e.amount||0).toLocaleString()}</div></div>`).join('');
}
async function logExpense() {
  const payload = {
    description: document.getElementById('fi-exp-desc').value,
    amount: parseFloat(document.getElementById('fi-exp-amount').value) || 0,
    category: document.getElementById('fi-exp-cat').value,
    date: document.getElementById('fi-exp-date').value || new Date().toISOString().split('T')[0],
  };
  if (!payload.description) return showToast('Description required', 'error');
  await api('/api/finance/expenses', 'POST', payload);
  ['fi-exp-desc','fi-exp-amount'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Expense logged!');
  loadExpenses();
}
async function loadPL() {
  const pl = await api('/api/finance/pl-report');
  const el = document.getElementById('fi-pl-body');
  const rows = [
    ['Revenue (Paid)', `$${(pl.revenue||0).toLocaleString()}`, 'var(--green)'],
    ['Pending Revenue', `$${(pl.pending_revenue||0).toLocaleString()}`, 'var(--gold)'],
    ['Total Expenses', `-$${(pl.total_expenses||0).toLocaleString()}`, '#ef4444'],
    ['Gross Profit', `$${(pl.gross_profit||0).toLocaleString()}`, pl.gross_profit>=0?'var(--green)':'#ef4444'],
    ['Profit Margin', `${pl.profit_margin||0}%`, 'var(--text-muted)'],
  ];
  el.innerHTML = `<div style="display:grid;gap:8px">${rows.map(([label,val,color])=>
    `<div style="display:flex;justify-content:space-between;padding:8px;background:var(--surface2);border-radius:6px">
       <span>${label}</span><strong style="color:${color}">${val}</strong></div>`
  ).join('')}
  ${pl.expenses_by_category && Object.keys(pl.expenses_by_category).length?
    `<div style="margin-top:8px"><strong style="font-size:.9em">Expenses by Category</strong>
     ${Object.entries(pl.expenses_by_category).map(([k,v])=>
       `<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:.85em">
         <span>${k}</span><span>$${(v||0).toLocaleString()}</span></div>`
     ).join('')}</div>`:''}</div>`;
}

// ── Analytics ─────────────────────────────────────────────────────
async function loadAnalyticsOverview() {
  const data = await api('/api/analytics/overview');
  document.getElementById('an-leads').textContent = data.crm?.total_leads || 0;
  document.getElementById('an-revenue').textContent = '$' + (data.finance?.revenue||0).toLocaleString();
  document.getElementById('an-open-rate').textContent = (data.email?.open_rate||0) + '%';
  document.getElementById('an-posts').textContent = data.social?.posts || 0;
  const el = document.getElementById('an-breakdown');
  el.innerHTML = `<div style="display:grid;gap:8px;font-size:.88em">
    <div style="padding:10px;background:var(--surface2);border-radius:6px">
      <strong>🎯 CRM</strong>
      <div style="margin-top:6px;display:grid;gap:2px">
        <div>Pipeline: <strong>$${(data.crm?.pipeline_value||0).toLocaleString()}</strong></div>
        <div>Won Deals: <strong>${data.crm?.won_deals||0}</strong></div>
        <div>Conversion: <strong>${data.crm?.conversion_rate||0}%</strong></div>
      </div>
    </div>
    <div style="padding:10px;background:var(--surface2);border-radius:6px">
      <strong>📧 Email</strong>
      <div style="margin-top:6px;display:grid;gap:2px">
        <div>Campaigns: <strong>${data.email?.campaigns||0}</strong></div>
        <div>Sent: <strong>${data.email?.sent||0}</strong></div>
      </div>
    </div>
    <div style="padding:10px;background:var(--surface2);border-radius:6px">
      <strong>🎙️ Meetings</strong>
      <div style="margin-top:6px;display:grid;gap:2px">
        <div>Total: <strong>${data.meetings?.total||0}</strong></div>
        <div>Analyzed: <strong>${data.meetings?.analyzed||0}</strong></div>
      </div>
    </div></div>`;
}
async function loadRecommendations() {
  const data = await api('/api/analytics/recommendations');
  const recs = data.recommendations || [];
  const el = document.getElementById('an-recommendations');
  if (!recs.length) { el.innerHTML = '<div class="empty"><p>No recommendations at this time.</p></div>'; return; }
  const colors = {high:'#ef4444', medium:'#f59e0b', low:'#10b981', critical:'#ef4444'};
  el.innerHTML = recs.map(r => `<div style="padding:10px;border-left:3px solid ${colors[r.priority]||'var(--border)'};margin-bottom:8px;background:var(--surface2);border-radius:0 6px 6px 0">
    <div style="font-size:.75em;color:${colors[r.priority]||'var(--text-muted)'};text-transform:uppercase;font-weight:700">${r.type} · ${r.priority}</div>
    <div style="font-size:.88em;margin-top:4px">${r.text}</div>
    ${r.action?`<div style="font-size:.78em;color:var(--text-muted);margin-top:4px">→ ${r.action}</div>`:''}</div>`
  ).join('');
}

// ── Workflows ─────────────────────────────────────────────────────
async function loadWorkflows() {
  const wfs = await api('/api/workflows/');
  const el = document.getElementById('wf-list');
  if (!wfs.length) { el.innerHTML = '<div class="empty"><div class="icon">⚙️</div><p>No workflows yet.</p></div>'; return; }
  el.innerHTML = wfs.map(w => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><strong>${w.name}</strong>
      <div style="font-size:.8em;color:var(--text-muted)">${w.description||''} · Trigger: ${w.trigger?.type||w.trigger}</div>
      <div style="font-size:.78em;color:var(--text-muted)">Steps: ${(w.steps||[]).length} · Runs: ${w.runs||0}</div>
    </div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-ghost btn-sm" onclick="runWorkflow('${w.id}')" style="font-size:.75em">▶ Run</button>
      <button class="btn btn-ghost btn-sm" onclick="deleteWorkflow('${w.id}')" style="font-size:.75em">🗑</button>
    </div></div>`).join('');
}
async function createWorkflow() {
  const stepsRaw = document.getElementById('wf-steps').value;
  const steps = stepsRaw.split('\n').map(l=>l.trim()).filter(Boolean).map(l => {
    const [action, ...desc] = l.split(':');
    return {type: action.trim(), config: desc.join(':').trim()};
  });
  const payload = {
    name: document.getElementById('wf-name').value,
    description: document.getElementById('wf-desc').value,
    trigger: {type: document.getElementById('wf-trigger').value},
    steps,
  };
  if (!payload.name) return showToast('Workflow name required', 'error');
  await api('/api/workflows/', 'POST', payload);
  ['wf-name','wf-desc','wf-steps'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Workflow created!');
  loadWorkflows();
}
async function runWorkflow(id) {
  await api(`/api/workflows/${id}/run`, 'POST', {});
  showToast('Workflow executed!');
  loadWorkflows();
  loadWorkflowRuns();
}
async function deleteWorkflow(id) {
  await api(`/api/workflows/${id}`, 'DELETE');
  showToast('Workflow deleted');
  loadWorkflows();
}
async function loadWorkflowRuns() {
  const runs = await api('/api/workflows/runs');
  const el = document.getElementById('wf-runs-list');
  if (!runs.length) { el.innerHTML = '<div class="empty"><p>No runs yet.</p></div>'; return; }
  el.innerHTML = runs.slice(-10).reverse().map(r => `<div style="padding:8px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;font-size:.85em">
    <div><strong>${r.workflow_name}</strong> <span style="color:var(--text-muted)">· ${r.trigger}</span></div>
    <div><span style="color:var(--green)">${r.status}</span> <span style="color:var(--text-muted);font-size:.8em">${r.started_at}</span></div>
  </div>`).join('');
}

// ── Team ──────────────────────────────────────────────────────────
async function loadTeamMembers() {
  const members = await api('/api/team/members');
  const el = document.getElementById('team-members-list');
  if (!members.length) { el.innerHTML = '<div class="empty"><div class="icon">👥</div><p>No members yet. Invite someone!</p></div>'; return; }
  el.innerHTML = members.map(m => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><strong>${m.name||m.email}</strong>
      <div style="font-size:.8em;color:var(--text-muted)">${m.email}</div></div>
    <div style="text-align:right">
      <span style="font-size:.78em;background:var(--surface3);padding:2px 8px;border-radius:4px">${m.role}</span>
      <span style="font-size:.75em;color:var(--text-muted);display:block;margin-top:2px">${m.status}</span>
    </div></div>`).join('');
}
async function inviteTeamMember() {
  const email = document.getElementById('team-email').value;
  const role = document.getElementById('team-role').value;
  if (!email) return showToast('Email required', 'error');
  const data = await api('/api/team/members/invite', 'POST', {email, role});
  if (data.error) return showToast(data.error, 'error');
  document.getElementById('team-invite-result').innerHTML =
    `<div style="padding:10px;background:var(--surface2);border-radius:6px;font-size:.85em">
     ✅ Invitation sent! Share this token: <code style="color:var(--gold)">${data.token}</code></div>`;
  document.getElementById('team-email').value = '';
  loadTeamMembers();
}

// ── Support ───────────────────────────────────────────────────────
function switchSupportTab(tab, btn) {
  document.querySelectorAll('.sup-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('sup-tickets-panel').style.display = tab === 'tickets' ? '' : 'none';
  document.getElementById('sup-kb-panel').style.display = tab === 'kb' ? '' : 'none';
  if (tab === 'tickets') loadTickets();
  if (tab === 'kb') loadKBArticles();
}
async function loadTickets() {
  try {
    const [tickets, stats] = await Promise.all([
      api('/api/support/tickets' + (document.getElementById('sup-f-status')?.value ? '?status=' + document.getElementById('sup-f-status').value : '')),
      api('/api/support/stats')
    ]);
    document.getElementById('sup-open').textContent = stats.open || 0;
    document.getElementById('sup-progress').textContent = stats.in_progress || 0;
    document.getElementById('sup-resolved').textContent = stats.resolved || 0;
    document.getElementById('sup-kb').textContent = stats.kb_articles || 0;
    const el = document.getElementById('sup-ticket-list');
    if (!tickets.length) { el.innerHTML = '<div class="empty"><div class="icon">🎫</div><p>No tickets.</p></div>'; return; }
    const prioColors = {urgent:'#ef4444',high:'#f59e0b',medium:'#6366f1',low:'#10b981'};
    el.innerHTML = tickets.map(t => `<div style="padding:10px;border-bottom:1px solid var(--border)">
      <div style="display:flex;justify-content:space-between">
        <strong>${t.number}: ${t.subject}</strong>
        <span style="font-size:.75em;background:var(--surface3);padding:2px 6px;border-radius:4px">${t.status}</span>
      </div>
      <div style="font-size:.8em;color:var(--text-muted)">${t.customer_name||''} · ${t.customer_email||''}</div>
      <div style="display:flex;gap:8px;margin-top:6px">
        <span style="font-size:.75em;color:${prioColors[t.priority]||'var(--text-muted)'}">${t.priority}</span>
        <span style="font-size:.75em;color:var(--text-muted)">${t.category}</span>
        <button class="btn btn-ghost btn-sm" onclick="aiSuggestReply('${t.id}')" style="font-size:.7em">🤖 AI Reply</button>
        ${t.status!=='resolved'?`<button class="btn btn-ghost btn-sm" onclick="resolveTicket('${t.id}')" style="font-size:.7em">✅ Resolve</button>`:''}
      </div></div>`).join('');
  } catch(e) { console.error('Support load error', e); }
}
async function createTicket() {
  const payload = {
    subject: document.getElementById('sup-subject').value,
    customer_email: document.getElementById('sup-cust-email').value,
    customer_name: document.getElementById('sup-cust-name').value,
    priority: document.getElementById('sup-priority').value,
    category: document.getElementById('sup-cat').value,
    description: document.getElementById('sup-desc').value,
  };
  if (!payload.subject) return showToast('Subject required', 'error');
  await api('/api/support/tickets', 'POST', payload);
  ['sup-subject','sup-cust-email','sup-cust-name','sup-desc'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Ticket created!');
  loadTickets();
}
async function aiSuggestReply(id) {
  showToast('Generating AI reply…');
  const data = await api(`/api/support/tickets/${id}/ai-suggest`, 'POST', {});
  alert('AI Suggested Reply:\n\n' + (data.suggestion || 'No suggestion.'));
}
async function resolveTicket(id) {
  await api(`/api/support/tickets/${id}`, 'PATCH', {status: 'resolved'});
  showToast('Ticket resolved!');
  loadTickets();
}
async function loadKBArticles() {
  const articles = await api('/api/support/kb');
  const el = document.getElementById('sup-kb-list');
  if (!articles.length) { el.innerHTML = '<div class="empty"><div class="icon">📚</div><p>No articles yet.</p></div>'; return; }
  el.innerHTML = articles.map(a => `<div style="padding:10px;border-bottom:1px solid var(--border)">
    <strong>${a.title}</strong>
    <div style="font-size:.8em;color:var(--text-muted)">${a.category} · Views: ${a.views}</div>
    <div style="font-size:.82em;margin-top:4px">${a.content.substring(0,120)}…</div>
  </div>`).join('');
}
async function createKBArticle() {
  const payload = {
    title: document.getElementById('kb-title').value,
    content: document.getElementById('kb-content').value,
    category: document.getElementById('kb-cat').value,
  };
  if (!payload.title) return showToast('Title required', 'error');
  await api('/api/support/kb', 'POST', payload);
  ['kb-title','kb-content'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Article saved!');
  loadKBArticles();
}

// ── Website Builder ───────────────────────────────────────────────
async function loadPages() {
  const pages = await api('/api/website-builder/pages');
  const el = document.getElementById('wb-pages-list');
  if (!pages.length) { el.innerHTML = '<div class="empty"><div class="icon">🌐</div><p>No pages yet.</p></div>'; return; }
  el.innerHTML = pages.map(p => `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><strong>${p.name}</strong>
      <div style="font-size:.8em;color:var(--text-muted)">${p.type} · ${p.business_name}</div></div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-ghost btn-sm" onclick="previewPage('${p.id}')" style="font-size:.75em">👁 Preview</button>
      <button class="btn btn-ghost btn-sm" onclick="deletePage('${p.id}')" style="font-size:.75em">🗑</button>
    </div></div>`).join('');
}
async function generateWebPage() {
  const payload = {
    business_name: document.getElementById('wb-biz').value,
    industry: document.getElementById('wb-industry').value,
    page_type: document.getElementById('wb-type').value,
    description: document.getElementById('wb-desc').value,
  };
  if (!payload.business_name) return showToast('Business name required', 'error');
  showToast('Generating page with AI…');
  await api('/api/website-builder/generate', 'POST', payload);
  showToast('Page generated!');
  loadPages();
}
async function previewPage(id) {
  const page = await api(`/api/website-builder/pages/${id}`);
  const w = window.open('', '_blank');
  w.document.write(page.html_content || '<p>No content.</p>');
}
async function deletePage(id) {
  await api(`/api/website-builder/pages/${id}`, 'DELETE');
  showToast('Page deleted');
  loadPages();
}

// ── Competitors ───────────────────────────────────────────────────
async function loadCompetitors() {
  const comps = await api('/api/competitors/');
  const el = document.getElementById('comp-list');
  if (!comps.length) { el.innerHTML = '<div class="empty"><div class="icon">🔍</div><p>No competitors tracked yet.</p></div>'; return; }
  el.innerHTML = comps.map(c => `<div style="padding:10px;border-bottom:1px solid var(--border)">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div><strong>${c.name}</strong>
        ${c.website?`<a href="${c.website}" target="_blank" style="font-size:.78em;color:var(--accent);margin-left:8px">${c.website}</a>`:''}
        <div style="font-size:.82em;color:var(--text-muted);margin-top:2px">${c.description||''}</div>
        ${c.last_checked?`<div style="font-size:.75em;color:var(--text-muted)">Last analyzed: ${c.last_checked}</div>`:''}
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="analyzeCompetitor('${c.id}')" style="font-size:.75em">🤖 Analyze</button>
        <button class="btn btn-ghost btn-sm" onclick="deleteCompetitor('${c.id}')" style="font-size:.75em">🗑</button>
      </div>
    </div></div>`).join('');
}
async function addCompetitor() {
  const payload = {
    name: document.getElementById('comp-name').value,
    website: document.getElementById('comp-website').value,
    description: document.getElementById('comp-desc').value,
  };
  if (!payload.name) return showToast('Name required', 'error');
  await api('/api/competitors/', 'POST', payload);
  ['comp-name','comp-website','comp-desc'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  showToast('Competitor added!');
  loadCompetitors();
}
async function analyzeCompetitor(id) {
  showToast('Analyzing competitor with AI…');
  const data = await api(`/api/competitors/${id}/analyze`, 'POST', {});
  document.getElementById('comp-analysis-card').style.display = '';
  document.getElementById('comp-analysis-body').textContent = data.analysis || 'No analysis.';
  loadCompetitors();
}
async function deleteCompetitor(id) {
  await api(`/api/competitors/${id}`, 'DELETE');
  showToast('Competitor removed');
  loadCompetitors();
}

// ── Personal Brand ────────────────────────────────────────────────
function switchBrandTab(tab, btn) {
  document.querySelectorAll('.br-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  ['generate','profile','library'].forEach(t => {
    const el = document.getElementById(`br-${t}-panel`);
    if (el) el.style.display = t === tab ? '' : 'none';
  });
  if (tab === 'library') loadBrandContent();
}
async function generateBrandContent() {
  const topic = document.getElementById('br-topic').value;
  if (!topic) return showToast('Topic required', 'error');
  showToast('Generating content…');
  const data = await api('/api/brand/generate-content', 'POST', {
    topic, content_type: document.getElementById('br-type').value,
  });
  document.getElementById('br-generated').textContent = data.content || '';
}
async function suggestBrandTopics() {
  showToast('Generating topic ideas…');
  const data = await api('/api/brand/topics', 'POST', {});
  const el = document.getElementById('br-topics-list');
  el.innerHTML = (data.topics||[]).map((t,i)=>
    `<div style="padding:6px;border-bottom:1px solid var(--border);font-size:.85em;cursor:pointer"
      onclick="document.getElementById('br-topic').value='${t.replace(/'/g,"\\'")}'">${i+1}. ${t}</div>`
  ).join('');
}
async function saveBrandProfile() {
  const payload = {
    name: document.getElementById('br-p-name').value,
    title: document.getElementById('br-p-title').value,
    industry: document.getElementById('br-p-industry').value,
    target_audience: document.getElementById('br-p-audience').value,
    tone: document.getElementById('br-p-tone').value,
  };
  await api('/api/brand/profile', 'POST', payload);
  showToast('Profile saved!');
}
async function loadBrandContent() {
  const pieces = await api('/api/brand/content');
  const el = document.getElementById('br-content-list');
  if (!pieces.length) { el.innerHTML = '<div class="empty"><div class="icon">📁</div><p>No content saved yet.</p></div>'; return; }
  el.innerHTML = pieces.map(p => `<div style="padding:10px;border-bottom:1px solid var(--border)">
    <div style="display:flex;justify-content:space-between">
      <span style="font-size:.78em;background:var(--surface3);padding:2px 6px;border-radius:4px">${p.type}</span>
      <span style="font-size:.75em;color:var(--text-muted)">${p.created_at?.split('T')[0]||''}</span>
    </div>
    <div style="font-size:.85em;margin-top:6px"><strong>${p.topic}</strong></div>
    <div style="font-size:.82em;color:var(--text-muted);margin-top:4px">${p.content.substring(0,150)}…</div>
    <button class="btn btn-ghost btn-sm" onclick="deleteBrandContent('${p.id}')" style="font-size:.7em;margin-top:6px">🗑 Delete</button>
  </div>`).join('');
}
async function deleteBrandContent(id) {
  await api(`/api/brand/content/${id}`, 'DELETE');
  showToast('Content deleted');
  loadBrandContent();
}

// ── Health Check ──────────────────────────────────────────────────
async function runHealthCheck() {
  showToast('Running health check…');
  const data = await api('/api/health-check/run', 'POST', {});
  document.getElementById('hc-report-card').style.display = '';
  document.getElementById('hc-latest-msg').style.display = 'none';
  const gradeColors = {A:'#10b981',B:'#6366f1',C:'#f59e0b',D:'#ef4444'};
  document.getElementById('hc-grade').textContent = data.grade;
  document.getElementById('hc-grade').style.color = gradeColors[data.grade]||'var(--text)';
  const el = document.getElementById('hc-report-body');
  el.innerHTML = `<div style="margin-bottom:16px">
    <div style="font-size:.9em;font-weight:700;margin-bottom:8px">Overall: ${data.overall_score}/100 (Grade ${data.grade})</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">${Object.entries(data.scores||{}).map(([k,v])=>
      `<div style="padding:6px 12px;background:var(--surface2);border-radius:6px;font-size:.82em">${k}: <strong>${v}</strong></div>`
    ).join('')}</div></div>
  ${data.issues?.length?`<div style="margin-bottom:16px"><strong style="font-size:.9em">⚠️ Issues Found</strong>
    ${data.issues.map(i=>`<div style="padding:8px;margin-top:6px;border-left:3px solid ${i.severity==='critical'?'#ef4444':'#f59e0b'};background:var(--surface2);border-radius:0 6px 6px 0;font-size:.84em">
      <div><strong>${i.area}:</strong> ${i.issue}</div>
      <div style="color:var(--text-muted);margin-top:2px">→ ${i.suggestion}</div></div>`).join('')}</div>`:''}
  ${data.strengths?.length?`<div><strong style="font-size:.9em">✅ Strengths</strong>
    ${data.strengths.map(s=>`<div style="padding:6px 0;font-size:.84em;color:var(--green)">✓ ${s}</div>`).join('')}</div>`:''}`;
}
async function loadHealthHistory() {
  const reports = await api('/api/health-check/history');
  const el = document.getElementById('hc-history');
  if (!reports.length) { el.innerHTML = ''; return; }
  const colors = {A:'#10b981',B:'#6366f1',C:'#f59e0b',D:'#ef4444'};
  el.innerHTML = '<div class="card"><div class="card-header"><div class="card-title">📅 Health History</div></div>' +
    reports.slice(-12).reverse().map(r=>
      `<div style="padding:10px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between">
        <div><strong>${r.date}</strong> <span style="font-size:.82em;color:var(--text-muted)">${r.overall_score}/100</span></div>
        <span style="font-size:1.2em;font-weight:900;color:${colors[r.grade]||'var(--text)'}">${r.grade}</span>
      </div>`
    ).join('') + '</div>';
}

// ── Export & Backup ───────────────────────────────────────────────
async function loadExportModules() {
  const modules = await api('/api/export/modules');
  const el = document.getElementById('export-modules-list');
  el.innerHTML = modules.map(m => `<div style="padding:8px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><strong>${m.key}</strong>
      <span style="font-size:.75em;color:var(--text-muted);margin-left:8px">${m.exists?(m.size_bytes/1024).toFixed(1)+'KB':'no data'}</span></div>
    <div style="display:flex;gap:6px">
      ${m.exists?`<a href="/api/export/json/${m.key}" download class="btn btn-ghost btn-sm" style="font-size:.75em">⬇ JSON</a>`:'<span style="font-size:.75em;color:var(--text-muted)">no data</span>'}
    </div></div>`).join('');
}
async function createBackup() {
  showToast('Creating backup…');
  const data = await api('/api/export/backup', 'POST', {});
  showToast(`Backup created: ${data.backup_file} (${(data.size_bytes/1024).toFixed(0)}KB)`);
  loadBackupsList();
}
async function loadBackupsList() {
  const backups = await api('/api/export/backups');
  const el = document.getElementById('export-backups-list');
  if (!backups.length) { el.innerHTML = '<div class="empty"><div class="icon">🗜️</div><p>No backups yet.</p></div>'; return; }
  el.innerHTML = backups.map(b => `<div style="padding:8px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <div><div style="font-size:.85em">${b.name}</div>
      <div style="font-size:.75em;color:var(--text-muted)">${(b.size_bytes/1024).toFixed(0)}KB · ${b.created_at}</div></div>
    <a href="/api/export/download-backup/${b.name}" download class="btn btn-ghost btn-sm" style="font-size:.75em">⬇ Download</a>
  </div>`).join('');
}

/* ══════════════════════════════════════════════════
   APP STATE MACHINE  (boot → login → dashboard)
══════════════════════════════════════════════════ */
const APP = {
  state: 'boot',
  session: null,

  transition(next) {
    this.state = next;
    document.body.className = 'state-' + next;
  }
};

function retryBoot() {
  const os = document.getElementById('offline-screen');
  if (os) { os.classList.remove('visible'); }
  runBootSequence();
}

function showOffline(msg) {
  const os = document.getElementById('offline-screen');
  const msgEl = document.getElementById('offline-msg');
  if (msgEl && msg) msgEl.textContent = msg;
  if (os) os.classList.add('visible');
}

async function checkHealth() {
  try {
    const res = await fetch('/health', {
      cache: 'no-store',
      signal: AbortSignal.timeout(5000)
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return true;
  } catch (e) {
    return false;
  }
}

function showLogin() {
  const ls = document.getElementById('login-screen');
  if (!ls) return;
  ls.classList.add('visible');
  ls.classList.add('glitch-in');
  setTimeout(() => {
    const inp = document.getElementById('login-user');
    if (inp) inp.focus();
  }, 300);
  APP.transition('login');
}

function hideBoot() {
  const overlay = document.getElementById('boot-overlay');
  if (!overlay) return;
  overlay.classList.add('fade-out');
  setTimeout(() => { overlay.style.display = 'none'; }, 850);
}

async function submitLogin() {
  const user = (document.getElementById('login-user') || {}).value || '';
  const pass = (document.getElementById('login-pass') || {}).value || '';
  const status = document.getElementById('login-status');
  const btn = document.getElementById('login-btn');

  if (!user.trim()) {
    if (status) status.textContent = '> Error: operator ID required';
    return;
  }

  if (btn) { btn.disabled = true; btn.textContent = 'AUTHENTICATING…'; }
  if (status) status.textContent = '> Verifying credentials…';

  await new Promise(r => setTimeout(r, 900 + Math.random() * 400));

  APP.session = { user: user.trim(), loginAt: new Date().toISOString() };
  if (status) status.textContent = '> Access granted. Welcome, ' + user.trim() + '.';

  const sv = document.getElementById('sv-session');
  if (sv) sv.textContent = user.trim();

  setTimeout(() => {
    const ls = document.getElementById('login-screen');
    if (ls) { ls.classList.add('leaving'); }
    setTimeout(() => {
      if (ls) { ls.classList.remove('visible', 'leaving', 'glitch-in'); }
      APP.transition('dashboard');
      startHeartbeat();
      startStatsUpdater();
      startTopbarClock();
      startSysResPolling();
    }, 520);
  }, 600);
}

/* allow pressing Enter on password field */
/* named constants */
const MAX_HEARTBEAT_LINES = 80;
const MAX_CHAT_MESSAGES = 60;
const MAX_AGENTS_TOTAL = 56; /* matches AGENTS_BY_MODE power list */

document.addEventListener('DOMContentLoaded', () => {
  const passEl = document.getElementById('login-pass');
  if (passEl) passEl.addEventListener('keydown', e => { if (e.key === 'Enter') submitLogin(); });
  const userEl = document.getElementById('login-user');
  if (userEl) userEl.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const p = document.getElementById('login-pass');
      if (p) p.focus();
    }
  });
});

/* ══════════════════════════════════════════════════
   BOOT SEQUENCE
══════════════════════════════════════════════════ */
function runBootSequence() {
  const overlay = document.getElementById('boot-overlay');
  const terminal = document.getElementById('boot-terminal');
  const bar = document.getElementById('boot-bar');
  const pct = document.getElementById('boot-pct');
  if (!overlay) return;

  /* reset for retry */
  overlay.style.display = '';
  overlay.classList.remove('fade-out');
  if (terminal) terminal.innerHTML = '';
  if (bar) bar.style.width = '0%';
  if (pct) pct.textContent = '0%';

  // Each entry: [text, cssClass, delayMs, progressTarget]
  // cssClass: '' (gold), 'ok' (green), 'warn' (orange), 'dim' (faint)
  const steps = [
    ['[BOOT]  AI Employee v4.0 — Autonomous Workforce Interface', 'dim', 0, 5],
    ['[SYS ]  Kernel interface initializing…', '', 180, 12],
    ['[SYS ]  Memory subsystem: OK', 'ok', 260, 18],
    ['[SYS ]  CPU sampler: started (background thread)', 'ok', 220, 24],
    ['[NET ]  Binding API server on :3000…', '', 280, 30],
    ['[NET ]  TLS context: ready', 'ok', 200, 36],
    ['[AUTH]  JWT secret: loaded', 'ok', 220, 41],
    ['[AGNT]  Loading agent registry…', '', 300, 47],
    ['[AGNT]  56 agents registered — all modes available', 'ok', 250, 54],
    ['[LLM ]  Probing Ollama endpoint…', '', 320, 60],
    ['[AI  ]  Hybrid router: ONLINE/OFFLINE/AUTO configured', 'ok', 220, 67],
    ['[DB  ]  State store: mounted', 'ok', 200, 73],
    ['[MEM ]  Memory index: warm', 'ok', 180, 78],
    ['[UI  ]  Initializing dashboard interface…', '', 260, 85],
    ['[UI  ]  Particle system: active', 'ok', 180, 91],
    ['[HLTH]  Verifying backend health…', '', 220, 96],
  ];

  let stepIdx = 0;
  let progress = 0;

  function bootLog(text, cls) {
    if (!terminal) return;
    const span = document.createElement('span');
    span.className = 'boot-terminal-line' + (cls ? ' ' + cls : '');
    span.style.animationDelay = '0s';
    span.textContent = text;
    terminal.appendChild(span);
    terminal.scrollTop = terminal.scrollHeight;
  }

  const stageLabel = document.getElementById('boot-stage-label');
  const stageMap = [[10,'SYSTEM CHECK'],[30,'NETWORK'],[50,'AGENTS'],[65,'AI ENGINE'],[80,'DATABASE'],[90,'UI INIT'],[96,'HEALTH CHECK'],[100,'UI READY']];

  function setProgress(target) {
    if (bar) bar.style.width = Math.min(target, 100) + '%';
    if (pct) pct.textContent = Math.min(Math.round(target), 100) + '%';
    if (stageLabel) {
      for (let i = stageMap.length - 1; i >= 0; i--) {
        if (target >= stageMap[i][0]) { stageLabel.textContent = stageMap[i][1]; break; }
      }
    }
  }

  function runNextStep() {
    if (stepIdx >= steps.length) return;
    const [text, cls, delay, prog] = steps[stepIdx++];
    setTimeout(() => {
      bootLog(text, cls);
      setProgress(prog);
      runNextStep();
    }, delay);
  }

  runNextStep();

  // After all steps finish (~3.5 s) start health check loop
  const totalDelay = steps.reduce((acc, s) => acc + s[2], 0) + 400;
  setTimeout(async () => {
    setProgress(96);
    let healthy = false;
    for (let attempt = 0; attempt < 8; attempt++) {
      healthy = await checkHealth();
      if (healthy) break;
      if (attempt < 7) {
        bootLog('[HLTH]  Retrying connection… (' + (attempt + 2) + '/8)', 'warn');
        await new Promise(r => setTimeout(r, 2000));
      }
    }
    if (!healthy) {
      bootLog('[ERR ]  Backend unreachable — connection refused on :3000', 'warn');
      hideBoot();
      showOffline('> Backend unreachable\n> GET /health → connection refused\n> Ensure AI Employee server is running\n> on http://localhost:3000');
      return;
    }
    bootLog('[DONE]  All systems nominal. Welcome, Operator.', 'ok');
    setProgress(100);
    await new Promise(r => setTimeout(r, 600));
    hideBoot();
    setTimeout(() => showLogin(), 200);
  }, totalDelay);
}
runBootSequence();

/* ══════════════════════════════════════════════════
   TOPBAR CLOCK
══════════════════════════════════════════════════ */
function startTopbarClock() {
  const el = document.getElementById('topbar-time');
  if (!el) return;
  function tick() {
    if (document.hidden) return;
    const now = new Date();
    const pad = n => String(n).padStart(2,'0');
    el.textContent = now.getFullYear() + '-' + pad(now.getMonth()+1) + '-' + pad(now.getDate())
      + '  ' + pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
  }
  tick();
  setInterval(tick, 1000);
}

/* ══════════════════════════════════════════════════
   AI HEARTBEAT SYSTEM
══════════════════════════════════════════════════ */
const HB_AGENTS = ['AI-1','AI-2','AI-3','AI-4','AI-5','ORCHESTRATOR','MEMORY','ROUTER','ANALYZER'];
const HB_MSGS = {
  'AI-1': ['Processing task…','Executing sub-plan…','Writing output…','Awaiting confirmation…'],
  'AI-2': ['Waiting for input…','Scanning context…','Routing request…','Idle…'],
  'AI-3': ['Running search query…','Aggregating results…','Compressing memory…'],
  'AI-4': ['Generating response…','Applying template…','Validating output…'],
  'AI-5': ['Monitoring pipeline…','Health check passed.','Retrying failed task…'],
  'ORCHESTRATOR': ['Routing message…','Assigning task to AI-2…','Broadcasting update…','Consensus reached.','Delegating to sub-agent…'],
  'MEMORY': ['Indexing memory…','Pruning old entries…','Recall hit.','Cache warm.'],
  'ROUTER': ['Selecting optimal model…','Latency probe: 12ms','Load balanced.'],
  'ANALYZER': ['Pattern detected.','Anomaly flagged.','Report queued.'],
};

function hbTimestamp() {
  const now = new Date();
  const pad = n => String(n).padStart(2,'0');
  return pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
}

function appendHeartbeatLine(agent, msg) {
  const log = document.getElementById('heartbeat-log');
  if (!log) return;
  const line = document.createElement('div');
  line.className = 'hb-line';
  const isOrch = agent === 'ORCHESTRATOR';
  line.innerHTML = '<span class="hb-ts">' + hbTimestamp() + '</span>'
    + '<span class="' + (isOrch ? 'hb-orch' : 'hb-tag') + '">[' + agent + ']</span> ' + msg;
  log.appendChild(line);
  /* keep last MAX_HEARTBEAT_LINES lines */
  while (log.children.length > MAX_HEARTBEAT_LINES) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

function startHeartbeat() {
  /* initial burst */
  for (let i = 0; i < 4; i++) {
    const agent = HB_AGENTS[Math.floor(Math.random() * HB_AGENTS.length)];
    const msgs = HB_MSGS[agent];
    appendHeartbeatLine(agent, msgs[Math.floor(Math.random() * msgs.length)]);
  }
  function scheduleNext() {
    const delay = 3000 + Math.random() * 5000;
    setTimeout(() => {
      if (!document.hidden) {
        const agent = HB_AGENTS[Math.floor(Math.random() * HB_AGENTS.length)];
        const msgs = HB_MSGS[agent];
        appendHeartbeatLine(agent, msgs[Math.floor(Math.random() * msgs.length)]);
      }
      scheduleNext();
    }, delay);
  }
  scheduleNext();
}

/* ══════════════════════════════════════════════════
   CYBER CHAT (Main Orchestrator)
══════════════════════════════════════════════════ */
const AI_RESPONSES = [
  'Understood. Delegating task to the optimal sub-agent…',
  'Processing your request. ETA ~2 seconds.',
  'Running analysis. Preliminary results will be ready shortly.',
  'Task accepted. AI-3 and AI-4 are now collaborating on this.',
  'Routing to ANALYZER. Pattern detection initiated.',
  'Memory lookup complete. Relevant context loaded.',
  'Sub-agents briefed. Execution pipeline started.',
  'Acknowledged. Streaming results as they arrive.',
  'Confirmed. BLACKLIGHT autonomous loop engaged for this task.',
  'Roger. Orchestrating multi-agent response chain.',
];

let _cyberTyping = false;

function appendCyberMsg(text, role) {
  const box = document.getElementById('cyber-chat-messages');
  if (!box) return;
  const div = document.createElement('div');
  div.className = 'msg-bubble ' + (role === 'user' ? 'msg-user' : 'msg-ai');
  if (role === 'ai') {
    div.innerHTML = '<div class="msg-sender">[ORCHESTRATOR]</div>' + escHtml(text);
  } else {
    div.textContent = text;
  }
  box.appendChild(div);
  while (box.children.length > MAX_CHAT_MESSAGES) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function showTypingIndicator() {
  const box = document.getElementById('cyber-chat-messages');
  if (!box || _cyberTyping) return;
  _cyberTyping = true;
  const div = document.createElement('div');
  div.className = 'msg-typing';
  div.id = 'cyber-typing';
  div.textContent = '[ORCHESTRATOR] typing…';
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function removeTypingIndicator() {
  const el = document.getElementById('cyber-typing');
  if (el) el.remove();
  _cyberTyping = false;
}

function sendCyberChat() {
  const input = document.getElementById('cyber-chat-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  appendCyberMsg(text, 'user');
  appendHeartbeatLine('ORCHESTRATOR', 'Received user query: "' + text.slice(0,40) + (text.length > 40 ? '…' : '') + '"');

  /* try real API first, fall back to fake response */
  showTypingIndicator();
  const delay = 900 + Math.random() * 1200;
  fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({message: text, agent: 'orchestrator'})
  }).then(r => r.ok ? r.json() : null).then(data => {
    removeTypingIndicator();
    const reply = (data && (data.reply || data.response || data.message)) ||
      AI_RESPONSES[Math.floor(Math.random() * AI_RESPONSES.length)];
    appendCyberMsg(reply, 'ai');
    appendHeartbeatLine('ORCHESTRATOR', 'Response delivered.');
  }).catch(() => {
    setTimeout(() => {
      removeTypingIndicator();
      const reply = AI_RESPONSES[Math.floor(Math.random() * AI_RESPONSES.length)];
      appendCyberMsg(reply, 'ai');
    }, delay);
  });
}

/* ══════════════════════════════════════════════════
   SYSTEM STATS UPDATER
══════════════════════════════════════════════════ */
let _fakeCpu = 0;
let _fakeMem = 0;
// Real CPU/RAM values are fed by loadSysRes() via updateCpuRing() and updateStatBar().
// _fakeCpu/_fakeMem are kept as fallback placeholders but not actively simulated.

function updateCpuRing(pct) {
  const circ = document.getElementById('cpu-ring-circle');
  const txt = document.getElementById('cpu-ring-text');
  if (!circ || !txt) return;
  const r = 36, full = 2 * Math.PI * r;
  circ.style.strokeDashoffset = full * (1 - pct / 100);
  txt.textContent = Math.round(pct) + '%';
}

function updateStatBar(barId, valId, pct, label) {
  const bar = document.getElementById(barId);
  const val = document.getElementById(valId);
  if (bar) bar.style.width = Math.min(100, pct) + '%';
  if (val) val.textContent = label;
}

function startStatsUpdater() {
  async function update() {
    if (document.hidden) return;
    /* fetch real status when possible */
    let agents = '–', tasks = '–', uptime = '–', gwStatus = 'online';
    try {
      const s = await fetch('/api/status', {cache:'no-store'});
      if (s.ok) {
        const d = await s.json();
        agents = d.agents_running ?? d.running ?? '–';
        tasks = d.tasks_queued ?? d.queue ?? '–';
        uptime = d.uptime ?? '–';
        gwStatus = d.gateway ?? 'online';
      }
    } catch (_) {}

    const agentNum = typeof agents === 'number' ? agents : (parseInt(agents) || 0);
    updateStatBar('sb-agents', 'sv-agents', agentNum / MAX_AGENTS_TOTAL * 100, agents);
    updateStatBar('sb-tasks', 'sv-tasks', 10, tasks);

    const gw = document.getElementById('sv-gw');
    if (gw) { gw.textContent = gwStatus; gw.style.color = gwStatus === 'online' ? 'var(--success)' : 'var(--danger)'; }
    const up = document.getElementById('sv-uptime');
    if (up) up.textContent = uptime;
  }

  update();
  setInterval(update, 10000);
}

/* ══════════════════════════════════════════════════
   SYSTEM RESOURCES (real hardware metrics)
══════════════════════════════════════════════════ */
let _sysResTimer = null;

function _srBar(pct) {
  const cls = pct >= 85 ? 'hot' : pct >= 65 ? 'warn' : 'ok';
  return `<div class="sysres-bar-track"><div class="sysres-bar-fill ${cls}" style="width:${Math.min(100,pct)}%"></div></div>`;
}

function _srTempColor(t) {
  if (t === null) return 'var(--text-muted)';
  if (t >= 85) return '#f87171';
  if (t >= 70) return '#fbbf24';
  return '#4ade80';
}

function _srTempBadge(t) {
  if (t === null || t === undefined) return '<span class="sysres-na">N/A</span>';
  const col = _srTempColor(t);
  return `<span class="sysres-temp-badge" style="color:${col};border-color:${col}">🌡 ${t}°C</span>`;
}

function _srMetric(label, value, sub, barPct) {
  const bar = (typeof barPct === 'number') ? _srBar(barPct) : '';
  return `<div class="sysres-metric">
    <div class="sysres-metric-header">
      <span class="sysres-metric-label">${label}</span>
      <span class="sysres-metric-value">${value}</span>
    </div>
    ${bar}
    ${sub ? `<div class="sysres-metric-sub">${sub}</div>` : ''}
  </div>`;
}

async function loadSysRes() {
  const grid = document.getElementById('sysres-grid');
  const updEl = document.getElementById('sysres-updated');
  if (!grid) return;
  try {
    const d = await api('/api/system/resources');
    if (d.error) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><p style="color:var(--text-muted)">${escHtml(d.error)}</p></div>`;
      return;
    }

    const cpuVal = typeof d.cpu_pct === 'number' ? d.cpu_pct.toFixed(1) + '%' : '–';
    const cpuCoreSub = (d.cpu_cores && d.cpu_threads)
      ? `${d.cpu_cores} cores · ${d.cpu_threads} threads`
      : (d.cpu_cores ? `${d.cpu_cores} cores` : '');
    const cpuTempBadge = _srTempBadge(d.cpu_temp);

    const ramVal = typeof d.ram_pct === 'number' ? d.ram_pct.toFixed(1) + '%' : '–';
    const ramSub = (d.ram_used_gb && d.ram_total_gb) ? `${d.ram_used_gb} GB / ${d.ram_total_gb} GB` : '';

    const diskVal = typeof d.disk_pct === 'number' ? d.disk_pct.toFixed(1) + '%' : '–';
    const diskSub = (d.disk_used_gb && d.disk_total_gb) ? `${d.disk_used_gb} GB / ${d.disk_total_gb} GB` : '';

    const loadSub = d.load_avg ? `1m ${d.load_avg['1m']}  5m ${d.load_avg['5m']}  15m ${d.load_avg['15m']}` : '';

    // CPU metric — load + temperature together
    let cpuSub = [cpuCoreSub, cpuTempBadge].filter(Boolean).join('  ');
    let html = _srMetric('CPU Load', cpuVal, cpuSub, d.cpu_pct);

    // GPU section — only when NVIDIA GPU is detected
    if (d.gpu_pct !== null && d.gpu_pct !== undefined) {
      const gpuVal = d.gpu_pct.toFixed ? d.gpu_pct.toFixed(0) + '%' : d.gpu_pct + '%';
      const gpuTempBadge = _srTempBadge(d.gpu_temp);
      const gpuNameStr = d.gpu_name ? escHtml(d.gpu_name) : 'GPU';
      const gpuSub = [gpuNameStr, gpuTempBadge].join('  ');
      html += _srMetric('GPU Load', gpuVal, gpuSub, d.gpu_pct);
    }

    html += _srMetric('RAM', ramVal, ramSub, d.ram_pct);
    html += _srMetric('Disk', diskVal, diskSub, d.disk_pct);

    if (d.load_avg) {
      html += _srMetric('Load Avg', d.load_avg['1m'], loadSub, null);
    }

    html += _srMetric('Uptime', d.uptime || '–', '', null);

    grid.innerHTML = html;
    if (updEl) {
      const t = new Date();
      updEl.textContent = 'Updated ' + String(t.getHours()).padStart(2,'0') + ':' + String(t.getMinutes()).padStart(2,'0') + ':' + String(t.getSeconds()).padStart(2,'0');
    }

    // Also feed real CPU into the sidebar ring
    if (typeof d.cpu_pct === 'number') updateCpuRing(d.cpu_pct);
    if (typeof d.ram_pct === 'number') updateStatBar('sb-mem', 'sv-mem', d.ram_pct, d.ram_pct.toFixed(0) + '%');
    if (d.uptime) { const upEl = document.getElementById('sv-uptime'); if (upEl) upEl.textContent = d.uptime; }
  } catch (e) {
    if (grid) grid.innerHTML = '<div class="empty" style="grid-column:1/-1"><p style="color:var(--text-muted)">Metrics unavailable</p></div>';
  }
}

function startSysResPolling() {
  loadSysRes();
  if (_sysResTimer) clearInterval(_sysResTimer);
  // Poll every 5s only when dashboard is active and page is visible
  _sysResTimer = setInterval(() => {
    if (!document.hidden && currentTab === 'dashboard') loadSysRes();
  }, 5000);
}

/* ══════════════════════════════════════════════════
   PARTICLE SYSTEM
══════════════════════════════════════════════════ */
(function initParticles() {
  const canvas = document.getElementById('particles-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H;
  const particles = [];

  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize, {passive:true});

  const GOLD = 'rgba(212,175,55,';
  for (let i = 0; i < 55; i++) {
    particles.push({
      x: Math.random() * W,
      y: Math.random() * H,
      r: Math.random() * 1.5 + 0.3,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      a: Math.random() * 0.5 + 0.1,
      da: (Math.random() - 0.5) * 0.003,
    });
  }

  // Throttle to ~20fps (50ms between frames) and skip entirely when tab is hidden
  let _particleLastTs = 0;
  function frame(ts) {
    if (!document.hidden && ts - _particleLastTs >= 50) {
      _particleLastTs = ts;
      ctx.clearRect(0, 0, W, H);
      for (const p of particles) {
        p.x += p.vx; p.y += p.vy;
        p.a += p.da;
        if (p.a < 0.05) p.da = Math.abs(p.da);
        if (p.a > 0.6) p.da = -Math.abs(p.da);
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
        if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = GOLD + p.a.toFixed(2) + ')';
        ctx.fill();
      }
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx*dx + dy*dy);
          if (dist < 90) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = GOLD + (0.06 * (1 - dist/90)).toFixed(3) + ')';
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();

/* init nav active state */
document.addEventListener('DOMContentLoaded', () => {
  const overviewBtn = document.querySelector('.nav-group-btn[data-group="overview"]');
  if (overviewBtn) overviewBtn.classList.add('active');
  /* ensure body starts in boot state */
  document.body.classList.add('state-boot');
});

// ═══════════════════════════════════════════════════════════════════
// Neural Brain live dashboard
// ═══════════════════════════════════════════════════════════════════

(function() {

// ── private state ──────────────────────────────────────────────────
const _BN = {
  lossHistory:   [],
  rewardHistory: [],
  pollTimer:     null,
};

// ── tiny bar-chart renderer ────────────────────────────────────────
function _renderChart(containerId, values, color) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!values || values.length === 0) {
    el.innerHTML = '<span style="color:var(--text-secondary);font-size:.8em;align-self:center;width:100%;text-align:center">No data yet…</span>';
    return;
  }
  const H = 82;
  const max = Math.max(...values, 0.001);
  const min = Math.min(...values, 0);
  const range = max - min || 0.001;
  const visible = values.slice(-80);
  el.innerHTML = '';
  el.style.display = 'flex';
  el.style.alignItems = 'flex-end';
  el.style.gap = '2px';
  visible.forEach(v => {
    const pct = Math.max(0.02, (v - min) / range);
    const bar = document.createElement('div');
    bar.className = 'bn-chart-bar';
    bar.style.height = Math.round(pct * H) + 'px';
    bar.style.background = color;
    bar.style.flexGrow = '1';
    bar.style.maxWidth = '12px';
    el.appendChild(bar);
  });
}

// ── helpers ────────────────────────────────────────────────────────
function _setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
function _setMsg(msg, cls) {
  const el = document.getElementById('brain-action-msg');
  if (!el) return;
  el.textContent = msg;
  el.style.color = cls === 'ok' ? '#34d399' : cls === 'err' ? '#f87171' : 'var(--text-secondary)';
}

// ── core status loader ─────────────────────────────────────────────
window.brainLoad = async function() {
  try {
    const s = await api('/api/brain/status');

    // Mode / connectivity badges
    const modeDot = document.getElementById('brain-mode-dot');
    const modeLabel = document.getElementById('brain-mode-label');
    const bgDot = document.getElementById('brain-bg-dot');
    if (modeDot && modeLabel) {
      const online = s.is_online;
      modeDot.style.background   = online ? 'var(--success)' : '#f59e0b';
      modeDot.style.boxShadow    = online ? '0 0 8px var(--success)' : '0 0 8px #f59e0b';
      modeLabel.textContent      = online ? 'ONLINE' : 'OFFLINE';
      modeLabel.style.color      = online ? 'var(--success)' : '#f59e0b';
    }
    if (bgDot) {
      const running = s.bg_running;
      bgDot.style.background  = running ? 'var(--success)' : '#6b7280';
      bgDot.style.boxShadow   = running ? '0 0 6px var(--success)' : 'none';
    }
    _setText('brain-bg-label', s.bg_running ? 'BG LOOP ●' : 'BG LOOP ○');

    // Stat values
    _setText('bn-learn-steps',  s.learn_step !== undefined ? s.learn_step.toLocaleString() : '—');
    _setText('bn-experiences',  s.experience_count !== undefined ? s.experience_count.toLocaleString() : '—');
    const bufText = s.buffer_size !== undefined ? `${s.buffer_size.toLocaleString()} / ${(s.buffer_capacity||0).toLocaleString()}` : '—';
    _setText('bn-buffer', bufText);
    _setText('bn-avg-reward',   s.avg_reward !== undefined ? s.avg_reward.toFixed(4) : '—');
    _setText('bn-last-loss',    s.last_loss  !== undefined ? s.last_loss.toFixed(5)  : '—');
    _setText('bn-lr',           s.lr         !== undefined ? s.lr.toExponential(2)   : '—');

    // Model config
    _setText('bn-device',       (s.device || '—').toUpperCase());
    _setText('bn-input-size',   s.cfg_input_size  !== undefined ? s.cfg_input_size  : '—');
    _setText('bn-output-size',  s.cfg_output_size !== undefined ? s.cfg_output_size : '—');
    _setText('bn-hidden',       s.cfg_hidden || '—');
    _setText('bn-batch',        s.cfg_batch_size  !== undefined ? s.cfg_batch_size  : '—');
    _setText('bn-update-freq',  s.cfg_update_freq !== undefined ? s.cfg_update_freq : '—');
    _setText('bn-model-path',   s.model_path || '—');

    // Update rolling histories from server-side loss_history if available
    if (Array.isArray(s.loss_history) && s.loss_history.length > 0) {
      _BN.lossHistory = s.loss_history.slice(-120);
    } else if (s.last_loss > 0) {
      _BN.lossHistory.push(s.last_loss);
      if (_BN.lossHistory.length > 120) _BN.lossHistory.shift();
    }
    if (s.avg_reward !== undefined) {
      _BN.rewardHistory.push(s.avg_reward);
      if (_BN.rewardHistory.length > 120) _BN.rewardHistory.shift();
    }

    // Render charts
    const lossLatest = _BN.lossHistory.length ? _BN.lossHistory.slice(-1)[0].toFixed(5) : '—';
    const rewLatest  = _BN.rewardHistory.length ? _BN.rewardHistory.slice(-1)[0].toFixed(4) : '—';
    _setText('bn-loss-latest',   lossLatest);
    _setText('bn-reward-latest', rewLatest);
    _renderChart('bn-loss-chart',   _BN.lossHistory,   'rgba(251,113,133,.85)');
    _renderChart('bn-reward-chart', _BN.rewardHistory, 'rgba(212,175,55,.85)');

  } catch(e) {
    _setText('brain-mode-label', 'ERROR');
  }
};

// ── log loader ─────────────────────────────────────────────────────
window.brainLoadLog = async function() {
  const logEl = document.getElementById('brain-log');
  if (!logEl) return;
  try {
    const r = await api('/api/brain/log?limit=80');
    const lines = r.lines || [];
    if (lines.length === 0) {
      logEl.innerHTML = '<span style="color:var(--text-secondary)">No brain log entries yet.</span>';
      return;
    }
    logEl.innerHTML = lines.map(l => {
      // Colour-code log levels
      const safe = l.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      if (/ERROR|CRITICAL/.test(safe)) return `<div style="color:#f87171">${safe}</div>`;
      if (/WARNING/.test(safe))        return `<div style="color:#fbbf24">${safe}</div>`;
      if (/smarter|↑/.test(safe))      return `<div style="color:#34d399;font-weight:600">${safe}</div>`;
      if (/↓|regressed/.test(safe))    return `<div style="color:#f87171">${safe}</div>`;
      return `<div>${safe}</div>`;
    }).join('');
    logEl.scrollTop = logEl.scrollHeight;
  } catch(e) {
    logEl.innerHTML = '<span style="color:#f87171">Failed to load log.</span>';
  }
};

// ── convenience wrapper ────────────────────────────────────────────
window.brainRefresh = async function() {
  await brainLoad();
  await brainLoadLog();
  _setMsg('Refreshed ' + new Date().toLocaleTimeString(), 'info');
};

// ── control actions ────────────────────────────────────────────────
window.brainLearn = async function() {
  _setMsg('Triggering learn step…', 'info');
  const r = await api('/api/brain/learn', {method:'POST'});
  if (r.ok) {
    _setMsg(`✓ Learn step ${r.learn_step} — loss: ${(r.loss||0).toFixed(5)}`, 'ok');
    brainLoad();
  } else {
    _setMsg('✗ ' + (r.message || 'Learn failed'), 'err');
  }
};

window.brainForceOffline = async function() {
  _setMsg('Running offline learning…', 'info');
  const r = await api('/api/brain/force-offline', {method:'POST'});
  if (r.ok) {
    _setMsg(`✓ Offline learn — ${r.collected} experiences collected, step ${r.learn_step}`, 'ok');
    brainLoad();
  } else {
    _setMsg('✗ ' + (r.message || 'Offline learn failed'), 'err');
  }
};

window.brainSave = async function() {
  _setMsg('Saving model…', 'info');
  const r = await api('/api/brain/save', {method:'POST'});
  if (r.ok) {
    _setMsg('✓ Model saved to ' + (r.path || 'disk'), 'ok');
  } else {
    _setMsg('✗ ' + (r.message || 'Save failed'), 'err');
  }
};

window.brainClear = async function() {
  if (!confirm('Clear the replay buffer? This cannot be undone.')) return;
  const r = await api('/api/brain/clear', {method:'POST'});
  if (r.ok) {
    _BN.lossHistory = []; _BN.rewardHistory = [];
    _setMsg('✓ Replay buffer cleared.', 'ok');
    brainLoad();
  } else {
    _setMsg('✗ ' + (r.message || 'Clear failed'), 'err');
  }
};

// ── auto-poll ──────────────────────────────────────────────────────
window.brainToggleAutopoll = function(on) {
  const indicator = document.getElementById('brain-poll-indicator');
  if (on) {
    if (indicator) indicator.style.display = '';
    _BN.pollTimer = setInterval(() => {
      // Only poll when the neural-brain tab is visible
      const tab = document.getElementById('tab-neural-brain');
      if (tab && tab.classList.contains('active')) {
        brainLoad();
      }
    }, 5000);
  } else {
    if (indicator) indicator.style.display = 'none';
    if (_BN.pollTimer) { clearInterval(_BN.pollTimer); _BN.pollTimer = null; }
  }
};

})(); // end Neural Brain IIFE
</script>
</body>
</html>"""


"""Stylesheet for the demo block system.

`base_css(theme)` returns the inner CSS for a <style> tag. Colour, font, radius
and spacing come from the theme via CSS custom properties; every block variant's
structural rules live here so the HTML stays minimal and can never render broken.
The mobile nav is a CSS-only checkbox toggle (no JS dependency).
"""
from __future__ import annotations


def font_import_link(theme: dict) -> str:
    imp = theme["fonts"]["import"]
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link href="https://fonts.googleapis.com/css2?family={imp}&display=swap" rel="stylesheet">'
    )


def base_css(theme: dict) -> str:
    p = theme["palette"]
    f = theme["fonts"]
    s = theme["style"]
    root = f""":root{{
  --primary:{p['primary']}; --primary-dark:{p['primary_dark']}; --accent:{p['accent']};
  --bg:{p['bg']}; --alt:{p['alt']}; --surface:{p['surface']}; --text:{p['text']};
  --muted:{p['muted']}; --border:{p['border']}; --on-primary:{p['on_primary']};
  --font-h:{f['heading']}; --font-b:{f['body']};
  --radius:{s['radius']}; --radius-lg:{s['radius_lg']}; --btn-radius:{s['btn_radius']};
  --shadow:{s['shadow']}; --pad:{s['section_pad']}; --container:{s['container']};
}}"""
    return root + _STATIC_CSS


_STATIC_CSS = r"""
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:var(--font-b);color:var(--text);background:var(--bg);line-height:1.65;-webkit-font-smoothing:antialiased}
h1,h2,h3,h4{font-family:var(--font-h);line-height:1.15;font-weight:700;color:var(--text)}
h1{font-size:clamp(2.1rem,5vw,3.6rem)}
h2{font-size:clamp(1.7rem,3.5vw,2.5rem)}
h3{font-size:1.25rem}
p{color:var(--muted)}
a{color:inherit;text-decoration:none}
img{max-width:100%;display:block}
.container{width:100%;max-width:var(--container);margin:0 auto;padding:0 1.5rem}
.section{padding:var(--pad) 0}
.section--alt{background:var(--alt)}
.eyebrow{display:inline-block;font-size:.78rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin-bottom:.8rem}
.lead{font-size:1.12rem;max-width:60ch}
.center{text-align:center}
.center .lead{margin-left:auto;margin-right:auto}
.sec-head{margin-bottom:2.8rem}
.sec-head.center{margin-left:auto;margin-right:auto;max-width:720px}
/* buttons */
.btn{display:inline-flex;align-items:center;gap:.5rem;padding:.9rem 1.7rem;border-radius:var(--btn-radius);font-weight:600;font-family:var(--font-b);cursor:pointer;border:2px solid transparent;transition:transform .15s ease,box-shadow .15s ease,background .15s ease;font-size:1rem}
.btn:hover{transform:translateY(-2px)}
.btn-accent{background:var(--accent);color:#fff;box-shadow:var(--shadow)}
.btn-primary{background:var(--primary);color:var(--on-primary)}
.btn-ghost{background:transparent;border-color:currentColor}
.btn-light{background:#fff;color:var(--primary)}
/* nav */
.nav{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}
.nav .inner{display:flex;align-items:center;justify-content:space-between;height:72px}
.brand{font-family:var(--font-h);font-weight:800;font-size:1.25rem;color:var(--text);display:flex;align-items:center;gap:.55rem}
.brand .dot{width:30px;height:30px;border-radius:9px;background:var(--accent);display:grid;place-items:center;color:#fff;font-size:.95rem}
.nav-links{display:flex;align-items:center;gap:2rem;list-style:none}
.nav-links a{font-weight:500;color:var(--text);font-size:.97rem;opacity:.85}
.nav-links a:hover,.nav-links a.active{opacity:1;color:var(--accent)}
.nav .btn{padding:.62rem 1.2rem}
.nav--split .inner{justify-content:flex-start;gap:3rem}
.nav--split .nav-cta{margin-left:auto}
.nav-toggle,.nav-toggle-label{display:none}
/* hero */
.hero{position:relative;overflow:hidden}
.hero .container{position:relative;z-index:2}
.hero h1{margin-bottom:1.1rem}
.hero p{font-size:1.18rem;max-width:54ch;margin-bottom:2rem}
.hero .btns{display:flex;gap:1rem;flex-wrap:wrap}
.hero--image{color:#fff;padding:7rem 0}
.hero--image h1,.hero--image h3{color:#fff}
.hero--image p{color:rgba(255,255,255,.9)}
.hero--image .bg{position:absolute;inset:0;z-index:0;background-size:cover;background-position:center}
.hero--image .bg::after{content:"";position:absolute;inset:0;background:linear-gradient(120deg,var(--primary-dark) 10%,rgba(0,0,0,.35))}
.hero--gradient{padding:7rem 0;color:#fff;background:linear-gradient(135deg,var(--primary),var(--primary-dark))}
.hero--gradient h1,.hero--gradient h3{color:#fff}.hero--gradient p{color:rgba(255,255,255,.88)}
.hero--gradient .blob{position:absolute;width:520px;height:520px;border-radius:50%;background:var(--accent);opacity:.18;filter:blur(20px);top:-160px;right:-120px}
.hero--split{padding:5.5rem 0}
.hero--split .grid{display:grid;grid-template-columns:1.05fr .95fr;gap:3.5rem;align-items:center}
.hero--split .shot{border-radius:var(--radius-lg);box-shadow:var(--shadow);overflow:hidden;aspect-ratio:4/3;background:var(--alt)}
.hero--split .shot img{width:100%;height:100%;object-fit:cover}
.hero--boxed{padding:5rem 0}
.hero--boxed .box{background:linear-gradient(135deg,var(--primary),var(--primary-dark));color:#fff;border-radius:var(--radius-lg);padding:4.5rem 3rem;text-align:center;box-shadow:var(--shadow)}
.hero--boxed .box h1,.hero--boxed .box h3{color:#fff}.hero--boxed .box p{color:rgba(255,255,255,.9);margin-left:auto;margin-right:auto}
.hero--boxed .box .btns{justify-content:center}
.hero--minimal{padding:6rem 0 4.5rem;text-align:center;border-bottom:1px solid var(--border)}
.hero--minimal p{margin-left:auto;margin-right:auto}.hero--minimal .btns{justify-content:center}
.hero--stats{padding:6rem 0 0}
.hero--stats .statbar{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-top:3.5rem;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:2rem;box-shadow:var(--shadow);transform:translateY(50%)}
.hero--stats{margin-bottom:5rem}
.stat{text-align:center}.stat .num{font-family:var(--font-h);font-size:2rem;font-weight:800;color:var(--accent)}.stat .lbl{font-size:.9rem;color:var(--muted)}
/* page header */
.pagehead{padding:4.5rem 0 3rem;background:linear-gradient(135deg,var(--primary),var(--primary-dark));color:#fff}
.pagehead h1{color:#fff;margin-bottom:.6rem}.pagehead p{color:rgba(255,255,255,.85);max-width:56ch}
.crumbs{font-size:.85rem;color:rgba(255,255,255,.7);margin-bottom:1rem}.crumbs a{color:rgba(255,255,255,.85)}
/* services */
.svc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.5rem}
.svc-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:2rem;transition:transform .18s ease,box-shadow .18s ease}
.svc-card:hover{transform:translateY(-4px);box-shadow:var(--shadow)}
.svc-ico{width:48px;height:48px;border-radius:12px;background:color-mix(in srgb,var(--accent) 16%,transparent);color:var(--accent);display:grid;place-items:center;font-size:1.4rem;margin-bottom:1.1rem}
.svc-card h3{margin-bottom:.5rem}
.svc-list{display:grid;gap:1rem}
.svc-row{display:flex;gap:1.2rem;align-items:flex-start;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.4rem 1.6rem}
.svc-row .n{font-family:var(--font-h);font-weight:800;color:var(--accent);font-size:1.3rem;min-width:2.2rem}
.svc-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1px;background:var(--border);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden}
.svc-tile{background:var(--surface);padding:2.2rem 1.8rem}
.svc-tile .svc-ico{margin-bottom:.9rem}
/* about */
.about--split .grid{display:grid;grid-template-columns:1fr 1fr;gap:3.5rem;align-items:center}
.about--split .shot{border-radius:var(--radius-lg);overflow:hidden;aspect-ratio:5/4;box-shadow:var(--shadow);background:var(--alt)}
.about--split .shot img{width:100%;height:100%;object-fit:cover}
.about p+p{margin-top:1rem}
.values{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.4rem;margin-top:1rem}
.value{padding:1.6rem;border:1px solid var(--border);border-radius:var(--radius);background:var(--surface)}
.value .svc-ico{margin-bottom:.8rem}
.about--quote{text-align:center}
.about--quote blockquote{font-family:var(--font-h);font-size:clamp(1.4rem,3vw,2.1rem);line-height:1.4;max-width:20ch;margin:0 auto 1.4rem;color:var(--text)}
.statband{background:var(--primary);color:#fff;border-radius:var(--radius-lg)}
.statband .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;padding:2.6rem 2rem;text-align:center}
.statband .num{font-family:var(--font-h);font-size:2.2rem;font-weight:800;color:#fff}
.statband .lbl{font-size:.88rem;color:rgba(255,255,255,.8)}
/* reviews */
.rev-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem}
.rev-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:2rem}
.rev-card .stars{color:var(--accent);letter-spacing:2px;margin-bottom:.8rem}
.rev-card p{color:var(--text);font-size:1.02rem}
.rev-card .who{margin-top:1.2rem;font-weight:600;color:var(--muted);font-size:.9rem}
.rev-single{max-width:760px;margin:0 auto;text-align:center}
.rev-single .stars{color:var(--accent);font-size:1.4rem;letter-spacing:3px;margin-bottom:1.2rem}
.rev-single blockquote{font-family:var(--font-h);font-size:clamp(1.3rem,2.6vw,1.9rem);line-height:1.45;color:var(--text);margin-bottom:1rem}
/* cta */
.cta-banner{background:linear-gradient(135deg,var(--primary),var(--primary-dark));color:#fff;text-align:center;border-radius:var(--radius-lg);padding:4rem 2rem}
.cta-banner h2{color:#fff;margin-bottom:.8rem}.cta-banner p{color:rgba(255,255,255,.88);margin:0 auto 2rem;max-width:50ch}
.cta-banner .btns{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap}
.cta-split{display:grid;grid-template-columns:1.4fr 1fr;gap:2rem;align-items:center;background:var(--primary);color:#fff;border-radius:var(--radius-lg);padding:3rem}
.cta-split h2{color:#fff}.cta-split p{color:rgba(255,255,255,.85)}.cta-split .right{text-align:right}
.cta-boxed{text-align:center;border:2px dashed var(--border);border-radius:var(--radius-lg);padding:3.5rem 2rem}
.cta-boxed h2{margin-bottom:.7rem}.cta-boxed p{margin:0 auto 1.8rem;max-width:46ch}
/* contact */
.contact-split{display:grid;grid-template-columns:1fr 1.25fr;gap:3rem;align-items:start}
.info-list{display:grid;gap:1.2rem}
.info-item{display:flex;gap:1rem;align-items:flex-start}
.info-item .svc-ico{flex:0 0 auto;width:42px;height:42px;font-size:1.1rem;margin:0}
.info-item .t{font-weight:600;color:var(--text)}.info-item .v{color:var(--muted);font-size:.95rem}
form.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:2.2rem;box-shadow:var(--shadow)}
.field{margin-bottom:1.1rem}
.field label{display:block;font-weight:600;font-size:.9rem;margin-bottom:.4rem}
.field input,.field textarea{width:100%;padding:.85rem 1rem;border:1px solid var(--border);border-radius:var(--radius);font:inherit;color:var(--text);background:var(--bg)}
.field input:focus,.field textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 20%,transparent)}
.field-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.contact-center{max-width:640px;margin:0 auto}
.contact-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1.4rem}
.contact-cards .info-item{flex-direction:column;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.8rem}
/* footer */
.footer{background:var(--primary-dark);color:rgba(255,255,255,.75);padding:3.5rem 0 2rem}
.footer a{color:rgba(255,255,255,.75)}.footer a:hover{color:#fff}
.footer .cols{display:grid;grid-template-columns:2fr 1fr 1fr;gap:2.5rem;margin-bottom:2.5rem}
.footer .brand{color:#fff;margin-bottom:1rem}
.footer h4{color:#fff;font-size:.95rem;margin-bottom:1rem}
.footer ul{list-style:none;display:grid;gap:.6rem;font-size:.92rem}
.footer .bottom{border-top:1px solid rgba(255,255,255,.12);padding-top:1.5rem;font-size:.85rem;display:flex;justify-content:space-between;flex-wrap:wrap;gap:.5rem}
.footer--simple{text-align:center}
.footer--simple .bottom{justify-content:center;border:none;padding-top:0}
/* gallery + neutral (image-less) panels */
.gal-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:1rem}
.gal-item{aspect-ratio:4/3;border-radius:var(--radius);overflow:hidden;background:var(--alt);box-shadow:var(--shadow)}
.gal-item img{width:100%;height:100%;object-fit:cover;transition:transform .3s ease}
.gal-item:hover img{transform:scale(1.05)}
.shot--neutral:empty{background:linear-gradient(135deg,var(--primary),var(--primary-dark));min-height:300px}
/* responsive */
@media(max-width:860px){
  .nav-links{position:fixed;inset:72px 0 auto 0;flex-direction:column;background:var(--bg);border-bottom:1px solid var(--border);padding:1.2rem 1.5rem;gap:1.1rem;display:none;box-shadow:var(--shadow)}
  .nav-toggle:checked~.nav-links{display:flex}
  .nav-toggle-label{display:inline-flex;flex-direction:column;gap:5px;cursor:pointer;padding:.4rem}
  .nav-toggle-label span{width:24px;height:2px;background:var(--text);border-radius:2px}
  .nav .nav-cta{display:none}
  .hero--split .grid,.about--split .grid,.contact-split,.cta-split{grid-template-columns:1fr}
  .cta-split .right{text-align:left}
  .field-row{grid-template-columns:1fr}
  .statband .grid{grid-template-columns:repeat(2,1fr)}
  .footer .cols{grid-template-columns:1fr;gap:1.8rem}
  .hero--stats .statbar{grid-template-columns:1fr;transform:none;margin-top:2.5rem}
  .hero--stats{margin-bottom:0}
}
@media(max-width:480px){
  .hero--image,.hero--gradient{padding:5rem 0}
  .btn{width:100%;justify-content:center}
  .hero .btns,.cta-banner .btns{flex-direction:column}
}
"""

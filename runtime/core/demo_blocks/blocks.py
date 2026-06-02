"""Section blocks for the demo site generator.

Every function returns a self-contained HTML string built from already-escaped
context values, so model output can never break the layout. Each section type
has several variants; the composer selects which variant + order per job to make
every site visually distinct while staying coherent across its own pages.

Variant counts (kept in VARIANTS) drive deterministic selection in composer.py.
"""
from __future__ import annotations

VARIANTS = {
    "hero": 6, "diensten": 4, "over": 4, "reviews": 3,
    "cta": 3, "contact": 3, "nav": 2, "footer": 2,
}

_NAV_ORDER = [("index.html", "Home"), ("diensten.html", "Diensten"),
              ("over.html", "Over ons"), ("contact.html", "Contact")]


def _btns(ctx, light=False):
    primary = "btn-light" if light else "btn-accent"
    return (f'<div class="btns">'
            f'<a class="btn {primary}" href="contact.html">Offerte aanvragen</a>'
            f'<a class="btn btn-ghost" href="diensten.html">Onze diensten</a></div>')


# ── NAV ───────────────────────────────────────────────────────────────────────
def nav(ctx, v=0):
    links = "".join(
        f'<li><a href="{href}" class="{ "active" if href==ctx["active"] else "" }">{label}</a></li>'
        for href, label in _NAV_ORDER
    )
    cls = "nav nav--split" if v % 2 else "nav"
    return f"""<nav class="{cls}"><div class="container inner">
  <a class="brand" href="index.html"><span class="dot">{ctx['initial']}</span>{ctx['naam']}</a>
  <input type="checkbox" id="navt" class="nav-toggle"><label for="navt" class="nav-toggle-label"><span></span><span></span><span></span></label>
  <ul class="nav-links">{links}</ul>
  <a class="btn btn-accent nav-cta" href="contact.html">Bel ons</a>
</div></nav>"""


# ── HERO ──────────────────────────────────────────────────────────────────────
def hero(ctx, v=0):
    v %= VARIANTS["hero"]
    t, txt = ctx["hero_title"], ctx["hero_text"]
    if v == 0:  # full image overlay
        return f"""<header class="hero hero--image"><div class="bg" style="background-image:url('{ctx['hero_img']}')"></div>
  <div class="container"><span class="eyebrow">{ctx['branche']} in {ctx['plaats']}</span>
  <h1>{t}</h1><p>{txt}</p>{_btns(ctx, light=True)}</div></header>"""
    if v == 1:  # split text + image
        return f"""<header class="hero hero--split"><div class="container grid">
  <div><span class="eyebrow">{ctx['branche']} in {ctx['plaats']}</span><h1>{t}</h1><p>{txt}</p>{_btns(ctx)}</div>
  <div class="shot"><img src="{ctx['hero_img']}" alt="{ctx['naam']}" loading="lazy"></div></div></header>"""
    if v == 2:  # gradient
        return f"""<header class="hero hero--gradient"><div class="blob"></div><div class="container">
  <span class="eyebrow">{ctx['branche']} in {ctx['plaats']}</span><h1>{t}</h1><p>{txt}</p>{_btns(ctx, light=True)}</div></header>"""
    if v == 3:  # boxed
        return f"""<header class="hero hero--boxed"><div class="container"><div class="box">
  <span class="eyebrow">{ctx['branche']} in {ctx['plaats']}</span><h1>{t}</h1><p>{txt}</p>{_btns(ctx, light=True)}</div></div></header>"""
    if v == 4:  # minimal
        return f"""<header class="hero hero--minimal"><div class="container">
  <span class="eyebrow">{ctx['branche']} in {ctx['plaats']}</span><h1>{t}</h1><p class="lead">{txt}</p>{_btns(ctx)}</div></header>"""
    # v==5 stats
    stats = "".join(f'<div class="stat"><div class="num">{n}</div><div class="lbl">{l}</div></div>' for n, l in ctx["stats"])
    return f"""<header class="hero hero--stats"><div class="container">
  <span class="eyebrow">{ctx['branche']} in {ctx['plaats']}</span><h1>{t}</h1><p>{txt}</p>{_btns(ctx)}
  <div class="statbar">{stats}</div></div></header>"""


# ── DIENSTEN ──────────────────────────────────────────────────────────────────
def diensten(ctx, v=0, head=True):
    v %= VARIANTS["diensten"]
    items = ctx["diensten"]
    sh = ('<div class="sec-head center"><span class="eyebrow">Wat wij doen</span>'
          f'<h2>Onze diensten</h2><p class="lead">Vakwerk voor {ctx["plaats"]} en omgeving.</p></div>') if head else ""
    if v == 0:
        cards = "".join(f'<div class="svc-card"><div class="svc-ico">✓</div><h3>{n}</h3><p>{o}</p></div>' for n, o in items)
        body = f'<div class="svc-grid">{cards}</div>'
    elif v == 1:
        rows = "".join(f'<div class="svc-row"><div class="n">{i+1:02d}</div><div><h3>{n}</h3><p>{o}</p></div></div>'
                       for i, (n, o) in enumerate(items))
        body = f'<div class="svc-list">{rows}</div>'
    elif v == 2:
        tiles = "".join(f'<div class="svc-tile"><div class="svc-ico">◆</div><h3>{n}</h3><p>{o}</p></div>' for n, o in items)
        body = f'<div class="svc-tiles">{tiles}</div>'
    else:
        cards = "".join(f'<div class="svc-card"><div class="svc-ico">{i+1}</div><h3>{n}</h3><p>{o}</p></div>'
                        for i, (n, o) in enumerate(items))
        body = f'<div class="svc-grid">{cards}</div>'
    return f'<section class="section"><div class="container">{sh}{body}</div></section>'


# ── OVER ──────────────────────────────────────────────────────────────────────
def over(ctx, v=0, full=False):
    v %= VARIANTS["over"]
    paras = ctx["over_lang"] if full else [ctx["over_kort"]]
    ptext = "".join(f"<p>{p}</p>" for p in paras)
    if v == 0:
        return f"""<section class="section section--alt about about--split"><div class="container grid">
  <div class="shot"><img src="{ctx['about_img']}" alt="{ctx['naam']}" loading="lazy"></div>
  <div><span class="eyebrow">Over ons</span><h2>Vakmanschap uit {ctx['plaats']}</h2>{ptext}
  <p style="margin-top:1.2rem"><a class="btn btn-accent" href="contact.html">Maak kennis</a></p></div></div></section>"""
    if v == 1:
        vals = "".join(f'<div class="value"><div class="svc-ico">{ic}</div><h3>{t}</h3><p>{d}</p></div>'
                       for ic, t, d in ctx["values"])
        return f"""<section class="section about"><div class="container">
  <div class="sec-head center"><span class="eyebrow">Over ons</span><h2>Waar wij voor staan</h2></div>
  {ptext}<div class="values">{vals}</div></div></section>"""
    if v == 2:
        stats = "".join(f'<div><div class="num">{n}</div><div class="lbl">{l}</div></div>' for n, l in ctx["stats"])
        return f"""<section class="section about"><div class="container">
  <div class="sec-head"><span class="eyebrow">Over ons</span><h2>Vakmanschap uit {ctx['plaats']}</h2></div>{ptext}
  <div class="statband" style="margin-top:2.5rem"><div class="grid">{stats}</div></div></div></section>"""
    return f"""<section class="section section--alt about about--quote"><div class="container">
  <span class="eyebrow">Over ons</span><blockquote>{ctx['over_kort']}</blockquote>
  <a class="btn btn-accent" href="contact.html">Neem contact op</a></div></section>"""


# ── REVIEWS ───────────────────────────────────────────────────────────────────
def reviews(ctx, v=0):
    v %= VARIANTS["reviews"]
    revs = ctx["reviews"]
    sh = '<div class="sec-head center"><span class="eyebrow">Klanten aan het woord</span><h2>Wat klanten zeggen</h2></div>'
    if v == 0:
        cards = "".join(f'<div class="rev-card"><div class="stars">★★★★★</div><p>{t}</p><div class="who">— {w}</div></div>'
                        for t, w in revs)
        body = f'<div class="rev-cards">{cards}</div>'
    elif v == 1:
        t, w = revs[0]
        body = f'<div class="rev-single"><div class="stars">★★★★★</div><blockquote>{t}</blockquote><div class="who">— {w}</div></div>'
    else:
        cards = "".join(f'<div class="rev-card"><div class="stars">★★★★★</div><p>{t}</p><div class="who">— {w}</div></div>'
                        for t, w in revs)
        body = f'<div class="rev-cards">{cards}</div>'
    return f'<section class="section section--alt"><div class="container">{sh}{body}</div></section>'


# ── CTA ───────────────────────────────────────────────────────────────────────
def cta(ctx, v=0):
    v %= VARIANTS["cta"]
    t = ctx["cta_text"]
    if v == 0:
        return f"""<section class="section"><div class="container"><div class="cta-banner">
  <h2>Klaar om te starten?</h2><p>{t}</p>
  <div class="btns"><a class="btn btn-light" href="contact.html">Vraag een offerte aan</a></div></div></div></section>"""
    if v == 1:
        return f"""<section class="section"><div class="container"><div class="cta-split">
  <div><h2>Klaar om te starten?</h2><p>{t}</p></div>
  <div class="right"><a class="btn btn-light" href="contact.html">Offerte aanvragen</a></div></div></div></section>"""
    return f"""<section class="section"><div class="container"><div class="cta-boxed">
  <h2>Klaar om te starten?</h2><p>{t}</p><a class="btn btn-accent" href="contact.html">Neem contact op</a></div></div></section>"""


# ── CONTACT ───────────────────────────────────────────────────────────────────
def _info_items(ctx):
    out = []
    if ctx["telefoon"]:
        out.append(("📞", "Telefoon", f'<a href="tel:{ctx["telefoon"]}">{ctx["telefoon"]}</a>'))
    if ctx["email"]:
        out.append(("✉", "E-mail", ctx["email_link"]))
    out.append(("📍", "Werkgebied", ctx["adres"] or f'{ctx["plaats"]} en omgeving'))
    if ctx["website"]:
        out.append(("🌐", "Website", ctx["website_link"]))
    return out


def _form(ctx):
    return f"""<form class="card" name="{ctx['form_name']}" method="POST" data-netlify="true" action="#">
  <div class="field-row"><div class="field"><label>Naam</label><input name="naam" placeholder="Uw naam" required></div>
  <div class="field"><label>Telefoon</label><input name="telefoon" placeholder="06 12345678"></div></div>
  <div class="field"><label>E-mail</label><input type="email" name="email" placeholder="u@voorbeeld.nl" required></div>
  <div class="field"><label>Bericht</label><textarea name="bericht" rows="4" placeholder="Waarmee kunnen we helpen?"></textarea></div>
  <button class="btn btn-accent" type="submit" style="width:100%">Versturen</button></form>"""


def contact(ctx, v=0, head=True):
    v %= VARIANTS["contact"]
    items = _info_items(ctx)
    info = "".join(f'<div class="info-item"><div class="svc-ico">{ic}</div><div><div class="t">{t}</div><div class="v">{val}</div></div></div>'
                   for ic, t, val in items)
    sh = ('<div class="sec-head center"><span class="eyebrow">Contact</span><h2>Vraag een offerte aan</h2>'
          f'<p class="lead">We reageren snel — meestal binnen één werkdag.</p></div>') if head else ""
    if v == 0:
        body = f'<div class="contact-split"><div class="info-list">{info}</div>{_form(ctx)}</div>'
    elif v == 1:
        body = f'<div class="contact-center">{_form(ctx)}<div class="info-list" style="margin-top:2rem;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));display:grid">{info}</div></div>'
    else:
        body = f'<div class="contact-cards">{info}</div><div style="max-width:640px;margin:2.5rem auto 0">{_form(ctx)}</div>'
    return f'<section class="section"><div class="container">{sh}{body}</div></section>'


# ── FOOTER ────────────────────────────────────────────────────────────────────
def footer(ctx, v=0):
    v %= VARIANTS["footer"]
    links = "".join(f'<li><a href="{h}">{l}</a></li>' for h, l in _NAV_ORDER)
    contact_bits = []
    if ctx["telefoon"]:
        contact_bits.append(f'<li><a href="tel:{ctx["telefoon"]}">{ctx["telefoon"]}</a></li>')
    if ctx["email"]:
        contact_bits.append(f'<li>{ctx["email_link"]}</li>')
    contact_bits.append(f'<li>{ctx["plaats"]} en omgeving</li>')
    contact_html = "".join(contact_bits)
    if v == 0:
        return f"""<footer class="footer"><div class="container">
  <div class="cols">
    <div><div class="brand"><span class="dot">{ctx['initial']}</span>{ctx['naam']}</div>
    <p>{ctx['branche'].capitalize()} in {ctx['plaats']} — vakmanschap waar u op kunt bouwen.</p></div>
    <div><h4>Menu</h4><ul>{links}</ul></div>
    <div><h4>Contact</h4><ul>{contact_html}</ul></div>
  </div>
  <div class="bottom"><span>© {ctx['jaar']} {ctx['naam']}</span><span>Website door NEXUS</span></div></div></footer>"""
    return f"""<footer class="footer footer--simple"><div class="container">
  <div class="brand" style="justify-content:center"><span class="dot">{ctx['initial']}</span>{ctx['naam']}</div>
  <ul style="display:flex;gap:1.5rem;justify-content:center;list-style:none;margin:1.2rem 0">{links}</ul>
  <div class="bottom"><span>© {ctx['jaar']} {ctx['naam']} · {ctx['plaats']}</span></div></div></footer>"""

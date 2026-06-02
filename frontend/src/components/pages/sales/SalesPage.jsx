import { useEffect, useState, useCallback } from 'react'
import api from '../../../api/client'
import { Panel, SectionLabel, StatusPill, EmptyState } from '../../nexus-ui'
import './SalesPage.css'

// ── Pipeline model ─────────────────────────────────────────────────────────────
const STATUS_LABELS = {
  gevonden: 'Gevonden', demo_klaar: 'Demo klaar', ter_review: 'Ter review',
  goedgekeurd: 'Goedgekeurd', gepitcht: 'Gepitcht', akkoord: 'Akkoord',
  betaald: 'Betaald', live: 'Live',
}
const STATUS_TONE = {
  gevonden: 'idle', demo_klaar: 'cool', ter_review: 'warn', goedgekeurd: 'success',
  gepitcht: 'purple', akkoord: 'gold', betaald: 'success', live: 'success',
}
const STEPS = [
  { key: 1, label: 'Leads', sub: 'Zoeken & research' },
  { key: 2, label: 'Demo', sub: 'Bekijken & goedkeuren' },
  { key: 3, label: 'Pitch', sub: 'Versturen & akkoord' },
  { key: 4, label: 'Resultaat', sub: 'Prijs · betaling · live' },
]
const stepForStatus = (s) => ({
  gevonden: 1, demo_klaar: 2, ter_review: 2, goedgekeurd: 3,
  gepitcht: 3, akkoord: 4, betaald: 4, live: 4,
}[s] || 1)

function demoUrl(order) {
  if (!order?.demo_pad) return null
  const parts = String(order.demo_pad).split('/').filter(Boolean)
  const base = parts[parts.length - 1] || ''
  if (base === 'index.html') return `/api/demos/${parts[parts.length - 2]}/`
  if (base.endsWith('.html')) return `/api/demos/${base}`
  return `/api/demos/${base}/`
}

function useCopy() {
  const [copied, setCopied] = useState('')
  const copy = (text, tag = '1') => {
    navigator.clipboard?.writeText(text || '')
    setCopied(tag); setTimeout(() => setCopied(''), 1800)
  }
  return [copied, copy]
}

// ── STEP 1 — Leads (find / manual / research) ──────────────────────────────────
function Finder({ onCreated }) {
  const [form, setForm] = useState({ stad: '', branche: '', aantal: '8' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [kandidaten, setKandidaten] = useState([])
  const [melding, setMelding] = useState('')
  const [creating, setCreating] = useState({})
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function zoek(e) {
    e.preventDefault(); setErr(null); setKandidaten([]); setMelding(''); setBusy(true)
    try {
      const res = await api.post('/api/orders/search', { stad: form.stad, branche: form.branche, aantal: parseInt(form.aantal) || 8 })
      if (res.ok) { setKandidaten(res.kandidaten || []); setMelding(res.kandidaten?.length ? '' : (res.melding || 'Geen bedrijven gevonden.')) }
      else setErr(res.error || 'Zoeken mislukt')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  async function voegToe(k, i) {
    setCreating(c => ({ ...c, [i]: true }))
    try {
      const res = await api.post('/api/orders', { bedrijfsnaam: k.bedrijfsnaam, plaats: k.plaats, branche: k.branche, contact: k.contact || '', prijs: 299 })
      if (res.ok) {
        // Carry the finder's website into research_data so research/demo can use it.
        if (k.website) {
          try { await api.post(`/api/orders/${res.order.id}/research-data`, { research_data: { website: k.website } }) } catch { /* non-fatal */ }
        }
        onCreated(res.order); setKandidaten(p => p.filter((_, j) => j !== i))
      } else alert(res.error || 'Aanmaken mislukt')
    } catch (e) { alert(e.message) } finally { setCreating(c => ({ ...c, [i]: false })) }
  }

  return (
    <Panel title="Zoek bedrijven" sub="branche + plaats" tone="gold">
      <form className="sl-form sl-form--row" onSubmit={zoek}>
        <label>Plaats<input required value={form.stad} onChange={e => set('stad', e.target.value)} placeholder="bijv. Leiden" /></label>
        <label>Branche<input required value={form.branche} onChange={e => set('branche', e.target.value)} placeholder="bijv. kapper" /></label>
        <label className="sl-form__narrow">Aantal<input type="number" min="1" max="20" value={form.aantal} onChange={e => set('aantal', e.target.value)} /></label>
        <button className="sl-btn sl-btn--primary" type="submit" disabled={busy}>{busy ? 'Zoeken…' : 'Zoek'}</button>
      </form>
      {err && <p className="sl-err">{err}</p>}
      {melding && <p className="sl-hint">{melding}</p>}
      {kandidaten.length > 0 && (
        <div className="sl-cand">
          <SectionLabel rule>{kandidaten.length} kandidaten</SectionLabel>
          {kandidaten.map((k, i) => {
            const ws = k.website_kwaliteit || (k.heeft_website ? 'onbekend' : 'geen')
            const badge = { geen: ['✓ Geen site', 'success'], slecht: ['⚡ Slechte site', 'warn'], matig: ['~ Matige site', 'cool'], goed: ['✗ Goede site', 'idle'], onbekend: ['? Website', 'idle'] }[ws] || [ws, 'idle']
            return (
              <div key={i} className="sl-cand__row">
                <div className="sl-cand__info">
                  <strong>{k.bedrijfsnaam}</strong>
                  <span className="sl-dim"> — {k.branche} in {k.plaats}</span>
                  <StatusPill size="sm" dot={false} tone={badge[1]} label={badge[0]} />
                </div>
                <button className="sl-btn" onClick={() => voegToe(k, i)} disabled={creating[i] || ws === 'goed'}>
                  {creating[i] ? '…' : ws === 'goed' ? 'Heeft site' : '+ Lead'}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </Panel>
  )
}

function ManualAdd({ onCreated }) {
  const [form, setForm] = useState({ bedrijfsnaam: '', plaats: '', branche: '', contact: '', prijs: '299' })
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(null)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  async function submit(e) {
    e.preventDefault(); setErr(null); setBusy(true)
    try {
      const res = await api.post('/api/orders', { ...form, prijs: parseFloat(form.prijs) || 299 })
      if (res.ok) { onCreated(res.order); setForm({ bedrijfsnaam: '', plaats: '', branche: '', contact: '', prijs: '299' }) } else setErr(res.error || 'Fout')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Panel title="Handmatig toevoegen" tone="cool">
      <form className="sl-form sl-form--grid" onSubmit={submit}>
        <label>Bedrijfsnaam<input required value={form.bedrijfsnaam} onChange={e => set('bedrijfsnaam', e.target.value)} /></label>
        <label>Plaats<input required value={form.plaats} onChange={e => set('plaats', e.target.value)} /></label>
        <label>Branche<input required value={form.branche} onChange={e => set('branche', e.target.value)} /></label>
        <label>Contact<input value={form.contact} onChange={e => set('contact', e.target.value)} placeholder="06-…" /></label>
        <label className="sl-form__narrow">Prijs €<input type="number" value={form.prijs} onChange={e => set('prijs', e.target.value)} /></label>
        <button className="sl-btn sl-btn--primary" type="submit" disabled={busy}>{busy ? '…' : 'Aanmaken'}</button>
      </form>
      {err && <p className="sl-err">{err}</p>}
    </Panel>
  )
}

const _lines = (s) => s.split('\n').map(x => x.trim()).filter(Boolean)

function _initRd(order) {
  let s = {}; try { s = order.research_data ? JSON.parse(order.research_data) : {} } catch { s = {} }
  return {
    telefoon: s.telefoon || '', email: s.email || '', adres: s.adres || '', openingstijden: s.openingstijden || '',
    website: s.website || '',
    social: (s.social || []).join('\n'),
    diensten: (s.diensten || []).map(d => typeof d === 'string' ? d : `${d.naam}${d.omschrijving ? `: ${d.omschrijving}` : ''}`).join('\n'),
    reviews: (s.reviews || []).map(r => typeof r === 'string' ? r : `${r.tekst}${r.naam ? ` | ${r.naam}` : ''}`).join('\n'),
    stats: (s.stats || []).map(st => typeof st === 'string' ? st : `${st.cijfer} | ${st.label}`).join('\n'),
    fotos: s.fotos || [],
  }
}

function ResearchEditor({ order, reload, onAdvance }) {
  const [core, setCore] = useState({ bedrijfsnaam: order.bedrijfsnaam, plaats: order.plaats, branche: order.branche, contact: order.contact || '', prijs: String(order.prijs ?? 299) })
  const [rd, setRd] = useState(() => _initRd(order))
  const [fotos, setFotos] = useState(() => _initRd(order).fotos)
  const [newFoto, setNewFoto] = useState('')
  const [busy, setBusy] = useState(false); const [autoBusy, setAutoBusy] = useState(false)
  const [upBusy, setUpBusy] = useState(false); const [genBusy, setGenBusy] = useState(false)
  const [err, setErr] = useState(null); const [saved, setSaved] = useState(false)
  const setC = (k, v) => { setCore(c => ({ ...c, [k]: v })); setSaved(false) }
  const set = (k, v) => { setRd(r => ({ ...r, [k]: v })); setSaved(false) }

  useEffect(() => {
    setCore({ bedrijfsnaam: order.bedrijfsnaam, plaats: order.plaats, branche: order.branche, contact: order.contact || '', prijs: String(order.prijs ?? 299) })
    const d = _initRd(order); setRd(d); setFotos(d.fotos)
  }, [order.id]) // eslint-disable-line

  function buildResearch() {
    return {
      telefoon: rd.telefoon.trim(), email: rd.email.trim(), adres: rd.adres.trim(), openingstijden: rd.openingstijden.trim(),
      website: rd.website.trim(),
      social: _lines(rd.social),
      fotos,
      diensten: _lines(rd.diensten).map(l => { const i = l.indexOf(':'); return i === -1 ? { naam: l, omschrijving: '' } : { naam: l.slice(0, i).trim(), omschrijving: l.slice(i + 1).trim() } }),
      reviews: _lines(rd.reviews).map(l => { const [t, n] = l.split('|'); return { tekst: t.trim(), naam: (n || '').trim() } }),
      stats: _lines(rd.stats).map(l => { const [c, lab] = l.split('|'); return { cijfer: c.trim(), label: (lab || '').trim() } }),
    }
  }
  async function persist() {
    await api.post(`/api/orders/${order.id}/update`, { ...core, prijs: parseFloat(core.prijs) || 299 })
    await api.post(`/api/orders/${order.id}/research-data`, { research_data: buildResearch() })
  }
  async function autoResearch() {
    setAutoBusy(true); setErr(null)
    try {
      const res = await api.post(`/api/orders/${order.id}/research`, {})
      if (res.ok && res.research_data) {
        const d = res.research_data
        setRd(r => ({
          ...r,
          telefoon: r.telefoon || d.telefoon || '', email: r.email || d.email || '', adres: r.adres || d.adres || '',
          openingstijden: r.openingstijden || d.openingstijden || '', website: r.website || d.website || '',
          social: r.social || (d.social || []).join('\n'),
        }))
        if (d.fotos?.length) setFotos(f => [...new Set([...f, ...d.fotos])])
        reload()
      } else setErr(res.error || 'Research mislukt')
    } catch (e) { setErr(e.message) } finally { setAutoBusy(false) }
  }
  async function uploadFotos(files) {
    if (!files?.length) return
    setUpBusy(true); setErr(null)
    try {
      const fd = new FormData();[...files].forEach(f => fd.append('photos', f))
      const token = sessionStorage.getItem('ai_jwt')
      const res = await fetch(`/api/orders/${order.id}/photo`, { method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd })
      const data = await res.json()
      if (data.ok) setFotos(f => [...f, ...data.urls]); else setErr(data.error || 'Upload mislukt')
    } catch (e) { setErr(e.message) } finally { setUpBusy(false) }
  }
  async function save() {
    setBusy(true); setErr(null)
    try { await persist(); setSaved(true); reload() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  async function genereerDemo() {
    setGenBusy(true); setErr(null)
    try {
      await persist()
      const res = await api.post(`/api/orders/${order.id}/demo`, {})
      if (res.ok) { reload(); onAdvance() } else setErr(res.error || 'Demo genereren mislukt')
    } catch (e) { setErr(e.message) } finally { setGenBusy(false) }
  }

  return (
    <Panel title={`Gegevens — ${core.bedrijfsnaam}`} sub="research + handmatig aanvullen" tone="gold"
      actions={<button className="sl-btn" onClick={autoResearch} disabled={autoBusy}>{autoBusy ? 'Zoeken…' : '⟲ Auto-research'}</button>}>
      <p className="sl-hint">Research vult voor wat het web vindt; vul jij de rest aan of corrigeer. Leeg laten = niet in de demo. Nooit verzinnen.</p>

      <SectionLabel rule>Bedrijf</SectionLabel>
      <div className="sl-form sl-form--grid">
        <label>Bedrijfsnaam<input value={core.bedrijfsnaam} onChange={e => setC('bedrijfsnaam', e.target.value)} /></label>
        <label>Branche<input value={core.branche} onChange={e => setC('branche', e.target.value)} /></label>
        <label>Plaats<input value={core.plaats} onChange={e => setC('plaats', e.target.value)} /></label>
        <label className="sl-form__narrow">Prijs €<input type="number" value={core.prijs} onChange={e => setC('prijs', e.target.value)} /></label>
      </div>

      <SectionLabel rule>Contact &amp; vindbaarheid</SectionLabel>
      <div className="sl-form sl-form--grid">
        <label>Telefoon<input value={rd.telefoon} onChange={e => set('telefoon', e.target.value)} placeholder="(leeg = niet tonen)" /></label>
        <label>E-mail<input value={rd.email} onChange={e => set('email', e.target.value)} placeholder="(leeg = niet tonen)" /></label>
        <label className="sl-form__full">Adres<input value={rd.adres} onChange={e => set('adres', e.target.value)} placeholder="(leeg = ‘plaats en omgeving’)" /></label>
        <label>Website<input value={rd.website} onChange={e => set('website', e.target.value)} /></label>
        <label>Openingstijden<input value={rd.openingstijden} onChange={e => set('openingstijden', e.target.value)} placeholder="Ma-vr 9-17" /></label>
        <label className="sl-form__full">Social media (één per regel)<textarea rows="2" value={rd.social} onChange={e => set('social', e.target.value)} placeholder="https://instagram.com/…" /></label>
      </div>

      <SectionLabel rule>Diensten (één per regel — ‘Naam: korte omschrijving’)</SectionLabel>
      <textarea className="sl-pitch" rows="4" value={rd.diensten} onChange={e => set('diensten', e.target.value)} placeholder={'Knippen: dames, heren en kinderen\nKleuren: balayage en highlights'} />

      <SectionLabel rule>Foto's</SectionLabel>
      <p className="sl-hint">Echte foto's van het bedrijf. Geen foto = neutraal kleurvlak in de demo (geen stockfoto).</p>
      {fotos.length > 0 && (
        <div className="sl-fotos">
          {fotos.map((u, i) => (
            <div className="sl-foto" key={i}>
              <img src={u} alt="" loading="lazy" />
              <button className="sl-foto__del" title="Verwijder" onClick={() => setFotos(f => f.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
        </div>
      )}
      <div className="sl-form sl-form--row">
        <label className="sl-form__full">Foto-URL toevoegen<input value={newFoto} onChange={e => setNewFoto(e.target.value)} placeholder="https://… .jpg" /></label>
        <button className="sl-btn" onClick={() => { if (newFoto.trim()) { setFotos(f => [...f, newFoto.trim()]); setNewFoto('') } }}>+ URL</button>
        <label className="sl-btn sl-upload">{upBusy ? 'Uploaden…' : '⬆ Upload'}<input type="file" accept="image/*" multiple hidden onChange={e => uploadFotos(e.target.files)} /></label>
      </div>

      <SectionLabel rule>Reviews (één per regel — ‘tekst | naam’, alleen echte)</SectionLabel>
      <textarea className="sl-pitch" rows="3" value={rd.reviews} onChange={e => set('reviews', e.target.value)} placeholder={'Snel en netjes geholpen, echt een aanrader! | Sandra'} />

      <SectionLabel rule>Cijfers (één per regel — ‘cijfer | label’, alleen echte)</SectionLabel>
      <textarea className="sl-pitch" rows="2" value={rd.stats} onChange={e => set('stats', e.target.value)} placeholder={'15+ | jaar ervaring\n4.8 | op Google'} />

      {err && <p className="sl-err">{err}</p>}
      <div className="sl-actions">
        <button className="sl-btn" onClick={save} disabled={busy}>{busy ? 'Opslaan…' : saved ? '✓ Opgeslagen' : 'Opslaan'}</button>
        <button className="sl-btn sl-btn--primary" onClick={genereerDemo} disabled={genBusy}>{genBusy ? 'Demo genereren… (~30s)' : 'Opslaan + genereer demo →'}</button>
      </div>
    </Panel>
  )
}

function LeadStep({ order, onCreated, reload, onAdvance, showFinder }) {
  return (
    <div className="sl-stack">
      {(!order || showFinder) && (<><Finder onCreated={onCreated} /><ManualAdd onCreated={onCreated} /></>)}
      {order && <ResearchEditor order={order} reload={reload} onAdvance={onAdvance} />}
    </div>
  )
}

// ── STEP 2 — Demo review ───────────────────────────────────────────────────────
function DemoStep({ order, reload, onAdvance }) {
  const [device, setDevice] = useState('desktop')
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(null)
  const [copied, copy] = useCopy()
  const url = demoUrl(order)
  const fullUrl = url ? `${window.location.origin}${url}` : ''

  async function act(endpoint, advance = false) {
    setBusy(true); setErr(null)
    try {
      const res = await api.post(`/api/orders/${order.id}/${endpoint}`, {})
      if (res.ok) { reload(); if (advance) onAdvance() } else setErr(res.error || 'Fout')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (!url) {
    return (
      <Panel title="Demo" tone="gold">
        <EmptyState title="Nog geen demo" sub="Genereer eerst een demo bij stap Leads (Research → Genereer demo)." />
        <div className="sl-actions"><button className="sl-btn sl-btn--primary" onClick={() => act('demo')} disabled={busy}>{busy ? 'Genereren…' : 'Genereer demo'}</button></div>
        {err && <p className="sl-err">{err}</p>}
      </Panel>
    )
  }
  return (
    <Panel title={`Demo — ${order.bedrijfsnaam}`} sub={order.status === 'goedgekeurd' ? 'goedgekeurd' : 'ter review'} tone="gold"
      actions={
        <div className="sl-seg">
          <button className={device === 'desktop' ? 'on' : ''} onClick={() => setDevice('desktop')}>🖥 Desktop</button>
          <button className={device === 'phone' ? 'on' : ''} onClick={() => setDevice('phone')}>📱 Mobiel</button>
        </div>
      }>
      <div className="sl-urlbar">
        <code>{fullUrl}</code>
        <button className="sl-btn sl-btn--sm" onClick={() => copy(fullUrl)}>{copied ? '✓' : 'Kopieer'}</button>
        <a className="sl-btn sl-btn--sm" href={url} target="_blank" rel="noreferrer">Open ↗</a>
      </div>
      <div className={`sl-preview sl-preview--${device}`}>
        <iframe title="demo-preview" src={url} />
      </div>
      {err && <p className="sl-err">{err}</p>}
      <div className="sl-actions">
        <button className="sl-btn" onClick={() => act('demo')} disabled={busy}>{busy ? '…' : '⟲ Hergenereer'}</button>
        {order.status !== 'goedgekeurd'
          ? <button className="sl-btn sl-btn--primary" onClick={() => act('approve', true)} disabled={busy}>Keur goed →</button>
          : <button className="sl-btn sl-btn--primary" onClick={onAdvance}>Naar pitch →</button>}
      </div>
    </Panel>
  )
}

// ── STEP 3 — Pitch ─────────────────────────────────────────────────────────────
function StuurNaarKlant({ order }) {
  const [data, setData] = useState(null); const [busy, setBusy] = useState(false); const [err, setErr] = useState(null)
  const [copied, copy] = useCopy()
  async function laden() {
    setBusy(true); setErr(null)
    try { const res = await api.get(`/api/orders/${order.id}/stuur-link`); if (res.ok) setData(res); else setErr(res.error) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  if (!data) return (<div className="sl-actions"><button className="sl-btn" onClick={laden} disabled={busy}>{busy ? 'Laden…' : 'Deel-links genereren'}</button>{err && <p className="sl-err">{err}</p>}</div>)
  return (
    <div className="sl-share">
      <div className="sl-urlbar"><code>{data.demo_url}</code><button className="sl-btn sl-btn--sm" onClick={() => copy(data.demo_url)}>{copied ? '✓' : 'Kopieer'}</button></div>
      <div className="sl-actions">
        <a className="sl-btn sl-btn--wa" href={data.whatsapp_url} target="_blank" rel="noreferrer">WhatsApp</a>
        <a className="sl-btn sl-btn--mail" href={data.email_url} target="_blank" rel="noreferrer">E-mail</a>
      </div>
      <p className="sl-hint">HITL: deze knoppen openen WhatsApp/e-mail met de tekst — jíj verstuurt zelf. Er gaat niets automatisch naar buiten.</p>
    </div>
  )
}

function PitchStep({ order, reload, onAdvance }) {
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(null)
  const [pitch, setPitch] = useState(order.pitch_tekst || '')
  const [copied, copy] = useCopy()
  useEffect(() => { setPitch(order.pitch_tekst || '') }, [order.id, order.pitch_tekst])

  async function generate() {
    setBusy(true); setErr(null)
    try {
      const res = await api.post(`/api/orders/${order.id}/pitch`, {})
      if (res.ok) { const full = await api.get(`/api/orders/${order.id}`); if (full.ok) setPitch(full.order.pitch_tekst || '') ; reload() }
      else setErr(res.error || 'Pitch genereren mislukt')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  async function mark(status, advance = false) {
    setBusy(true); setErr(null)
    try {
      const ep = status === 'akkoord' ? 'akkoord' : 'status'
      const res = await api.post(`/api/orders/${order.id}/${ep}`, status === 'akkoord' ? {} : { status })
      if (res.ok) { reload(); if (advance) onAdvance() } else setErr(res.error)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Panel title={`Pitch — ${order.bedrijfsnaam}`} sub="zonder prijs" tone="gold">
      {!pitch
        ? (<><EmptyState title="Nog geen pitch" sub="Genereer een persoonlijk bericht (zonder prijs) dat je naar de klant stuurt." />
            <div className="sl-actions"><button className="sl-btn sl-btn--primary" onClick={generate} disabled={busy}>{busy ? 'Genereren…' : 'Genereer pitch'}</button></div></>)
        : (<>
            <p className="sl-hint">Pas de tekst gerust aan vóór je hem verstuurt.</p>
            <textarea className="sl-pitch" rows="9" value={pitch} onChange={e => setPitch(e.target.value)} />
            <div className="sl-actions">
              <button className="sl-btn" onClick={() => copy(pitch)}>{copied ? '✓ Gekopieerd' : 'Kopieer pitch'}</button>
              <button className="sl-btn" onClick={generate} disabled={busy}>⟲ Opnieuw</button>
            </div>
            <SectionLabel rule>Naar klant sturen</SectionLabel>
            <StuurNaarKlant order={order} />
            <SectionLabel rule>Status</SectionLabel>
            <div className="sl-actions">
              {order.status === 'goedgekeurd' && <button className="sl-btn" onClick={() => mark('gepitcht')} disabled={busy}>Gemarkeerd als verstuurd</button>}
              {order.status === 'gepitcht' && <button className="sl-btn sl-btn--primary" onClick={() => mark('akkoord', true)} disabled={busy}>Klant gaf akkoord →</button>}
              {order.status === 'akkoord' && <span className="sl-ok">✓ Klant akkoord — ga naar Resultaat</span>}
            </div>
          </>)}
      {err && <p className="sl-err">{err}</p>}
    </Panel>
  )
}

// ── STEP 4 — Resultaat ─────────────────────────────────────────────────────────
function ResultStep({ order, reload }) {
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(null)
  const [ref, setRef] = useState(''); const [vervolg, setVervolg] = useState(order.vervolg_tekst || '')
  const [deploy, setDeploy] = useState(null); const [copied, copy] = useCopy()
  useEffect(() => { setVervolg(order.vervolg_tekst || '') }, [order.id, order.vervolg_tekst])

  async function betaald() {
    if (!ref.trim()) { setErr('Vul de PayPal-transactiereferentie in.'); return }
    setBusy(true); setErr(null)
    try { const res = await api.post(`/api/orders/${order.id}/betaald`, { referentie: ref }); if (res.ok) reload(); else setErr(res.error) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  async function doDeploy() {
    setBusy(true); setErr(null)
    try { const res = await api.post(`/api/orders/${order.id}/deploy`, {}); if (res.ok) { setDeploy(res); reload() } else setErr(res.error || 'Deploy mislukt (Netlify-token ingesteld?)') }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  async function markLive() {
    setBusy(true); setErr(null)
    try { const res = await api.post(`/api/orders/${order.id}/status`, { status: 'live' }); if (res.ok) reload(); else setErr(res.error) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const liveUrl = order.live_url || deploy?.live_url

  return (
    <Panel title={`Resultaat — ${order.bedrijfsnaam}`} sub={`€${order.prijs} · ${STATUS_LABELS[order.status]}`} tone="gold">
      {order.status === 'akkoord' && vervolg && (<>
        <SectionLabel rule>Vervolgbericht (prijs + PayPal)</SectionLabel>
        <textarea className="sl-pitch" rows="7" value={vervolg} onChange={e => setVervolg(e.target.value)} />
        <div className="sl-actions"><button className="sl-btn" onClick={() => copy(vervolg)}>{copied ? '✓ Gekopieerd' : 'Kopieer bericht'}</button></div>
      </>)}
      {(order.status === 'akkoord' || order.status === 'gepitcht') && (<>
        <SectionLabel rule>Betaling bevestigen</SectionLabel>
        <p className="sl-hint">PayPal → Activiteit → klik de betaling → Transactie-ID.</p>
        <div className="sl-form sl-form--row">
          <input value={ref} onChange={e => setRef(e.target.value)} placeholder="bijv. 5TY05013RG0287623" />
          <button className="sl-btn sl-btn--primary" onClick={betaald} disabled={busy || !ref.trim()}>{busy ? '…' : 'Betaling bevestigen'}</button>
        </div>
      </>)}
      {order.status === 'betaald' && (<>
        <SectionLabel rule>Live zetten</SectionLabel>
        <div className="sl-actions">
          <button className="sl-btn" onClick={doDeploy} disabled={busy}>{busy ? 'Deployen…' : 'Zet live via Netlify'}</button>
          <button className="sl-btn sl-btn--primary" onClick={markLive} disabled={busy}>Gemarkeerd als live</button>
        </div>
        {deploy?.hosting_voorstel && <pre className="sl-pre">{deploy.hosting_voorstel}</pre>}
      </>)}
      {order.status === 'live' && <p className="sl-ok">✓ Live</p>}
      {liveUrl && <p className="sl-live">🌐 <a href={liveUrl} target="_blank" rel="noreferrer">{liveUrl}</a></p>}
      {err && <p className="sl-err">{err}</p>}
    </Panel>
  )
}

// ── Page shell ─────────────────────────────────────────────────────────────────
export default function SalesPage() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [step, setStep] = useState(1)
  const [showFinder, setShowFinder] = useState(true)

  const load = useCallback(async () => {
    setErr(null)
    try { const res = await api.get('/api/orders'); if (res.ok) setOrders(res.orders || []); else setErr(res.error || 'Fout bij laden') }
    catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const selected = orders.find(o => o.id === selectedId) || null

  function selectOrder(o) { setSelectedId(o.id); setStep(stepForStatus(o.status)); setShowFinder(false) }
  function onCreated(o) { setOrders(p => [o, ...p.filter(x => x.id !== o.id)]); selectOrder(o) }
  async function handleDelete(id, e) {
    e?.stopPropagation()
    const o = orders.find(x => x.id === id)
    if (!confirm(`Verwijder "${o?.bedrijfsnaam || id}"?`)) return
    try { const res = await api.delete(`/api/orders/${id}`); if (res.ok) { setOrders(p => p.filter(x => x.id !== id)); if (selectedId === id) setSelectedId(null) } }
    catch (e) { setErr(e.message) }
  }

  const counts = orders.reduce((a, o) => { a[o.status] = (a[o.status] || 0) + 1; return a }, {})

  return (
    <div className="sl">
      <header className="sl__top">
        <div>
          <h1 className="sl__title">Website Sales</h1>
          <p className="sl__subtitle">Van lead tot live — jij beslist elke stap (HITL).</p>
        </div>
        <div className="sl__top-actions">
          <StatusPill size="sm" tone="cool" dot={false} label="Orders" value={orders.length} />
          {counts.live ? <StatusPill size="sm" tone="success" dot={false} label="Live" value={counts.live} /> : null}
          <button className="sl-btn" onClick={() => { setLoading(true); load() }}>⟲ Vernieuwen</button>
        </div>
      </header>

      <nav className="sl-stepper" aria-label="Sales stappen">
        {STEPS.map(st => {
          const cur = selected ? stepForStatus(selected.status) : 1
          const state = st.key === step ? 'active' : st.key < cur ? 'done' : 'todo'
          const disabled = !selected && st.key !== 1
          return (
            <button key={st.key} className={`sl-step sl-step--${state}`} disabled={disabled} onClick={() => setStep(st.key)}>
              <span className="sl-step__n">{st.key < cur ? '✓' : st.key}</span>
              <span className="sl-step__txt"><strong>{st.label}</strong><em>{st.sub}</em></span>
            </button>
          )
        })}
      </nav>

      {err && <p className="sl-err sl-err--page">{err}</p>}

      <div className="sl__grid">
        <aside className="sl__rail">
          <div className="sl__rail-head">
            <SectionLabel tone="gold" size="sm">Orders</SectionLabel>
            <button className="sl-btn sl-btn--sm" onClick={() => { setSelectedId(null); setStep(1); setShowFinder(true) }}>+ Nieuwe lead</button>
          </div>
          {loading && <p className="sl-dim">Laden…</p>}
          {!loading && orders.length === 0 && <p className="sl-dim">Nog geen orders. Zoek of voeg een lead toe.</p>}
          <div className="sl__rail-list">
            {orders.map(o => (
              <button key={o.id} className={`sl-orow${o.id === selectedId ? ' sl-orow--on' : ''}`} onClick={() => selectOrder(o)}>
                <div className="sl-orow__main">
                  <strong>{o.bedrijfsnaam}</strong>
                  <span className="sl-dim">{o.plaats} · {o.branche}</span>
                </div>
                <StatusPill size="sm" dot={false} tone={STATUS_TONE[o.status] || 'idle'} label={STATUS_LABELS[o.status] || o.status} />
                <span className="sl-orow__del" title="Verwijder" onClick={(e) => handleDelete(o.id, e)}>✕</span>
              </button>
            ))}
          </div>
        </aside>

        <main className="sl__main">
          {step === 1 && <LeadStep order={selected} onCreated={onCreated} reload={load} onAdvance={() => setStep(2)} showFinder={showFinder || !selected} />}
          {step === 2 && (selected ? <DemoStep order={selected} reload={load} onAdvance={() => setStep(3)} /> : <EmptyState title="Kies een order" sub="Selecteer links een order om de demo te bekijken." />)}
          {step === 3 && (selected ? <PitchStep order={selected} reload={load} onAdvance={() => setStep(4)} /> : <EmptyState title="Kies een order" sub="Selecteer links een order voor de pitch." />)}
          {step === 4 && (selected ? <ResultStep order={selected} reload={load} /> : <EmptyState title="Kies een order" sub="Selecteer links een order voor het eindresultaat." />)}
        </main>
      </div>
    </div>
  )
}

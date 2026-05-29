import { useEffect, useState, useCallback } from 'react'
import api from '../../api/client'
import './OrdersPage.css'

const STATUSES = ['gevonden', 'demo_klaar', 'ter_review', 'goedgekeurd', 'gepitcht', 'betaald', 'live']
const STATUS_LABELS = {
  gevonden: 'Gevonden',
  demo_klaar: 'Demo klaar',
  ter_review: 'Ter review',
  goedgekeurd: 'Goedgekeurd',
  gepitcht: 'Gepitcht',
  betaald: 'Betaald',
  live: 'Live',
}

function statusIdx(s) { return STATUSES.indexOf(s) }

function StatusPipe({ current }) {
  const idx = statusIdx(current)
  return (
    <div className="op-pipe">
      {STATUSES.map((s, i) => (
        <span key={s} className={`op-pipe__step${i === idx ? ' op-pipe__step--active' : i < idx ? ' op-pipe__step--done' : ''}`}>
          {STATUS_LABELS[s]}
        </span>
      ))}
    </div>
  )
}

function NewOrderForm({ onCreated }) {
  const [form, setForm] = useState({ bedrijfsnaam: '', plaats: '', branche: '', contact: '', prijs: '299' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function submit(e) {
    e.preventDefault()
    setErr(null)
    setBusy(true)
    try {
      const res = await api.post('/api/orders', {
        ...form,
        prijs: parseFloat(form.prijs) || 299,
      })
      if (res.ok) onCreated(res.order)
      else setErr(res.error || 'Fout bij aanmaken')
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="op-form" onSubmit={submit}>
      <h3>Nieuw bedrijf</h3>
      <label>Bedrijfsnaam<input required value={form.bedrijfsnaam} onChange={e => set('bedrijfsnaam', e.target.value)} /></label>
      <label>Plaats<input required value={form.plaats} onChange={e => set('plaats', e.target.value)} /></label>
      <label>Branche<input required value={form.branche} onChange={e => set('branche', e.target.value)} /></label>
      <label>Contact<input value={form.contact} onChange={e => set('contact', e.target.value)} placeholder="bijv. 06-12345678" /></label>
      <label>Prijs (€)<input type="number" value={form.prijs} onChange={e => set('prijs', e.target.value)} /></label>
      {err && <p className="op-err">{err}</p>}
      <button type="submit" disabled={busy}>{busy ? 'Bezig…' : 'Aanmaken'}</button>
    </form>
  )
}

function BedrijfZoekerPanel({ onCreated }) {
  const [form, setForm] = useState({ stad: '', branche: '', aantal: '8' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [kandidaten, setKandidaten] = useState([])
  const [creating, setCreating] = useState({})

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function zoek(e) {
    e.preventDefault()
    setErr(null); setKandidaten([])
    setBusy(true)
    try {
      const res = await api.post('/api/orders/search', {
        stad: form.stad,
        branche: form.branche,
        aantal: parseInt(form.aantal) || 8,
      })
      if (res.ok) setKandidaten(res.kandidaten || [])
      else setErr(res.error || 'Zoeken mislukt')
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function voegToe(k, idx) {
    setCreating(c => ({ ...c, [idx]: true }))
    try {
      const res = await api.post('/api/orders', {
        bedrijfsnaam: k.bedrijfsnaam,
        plaats: k.plaats,
        branche: k.branche,
        contact: k.contact || '',
        prijs: 299,
      })
      if (res.ok) {
        onCreated(res.order)
        setKandidaten(prev => prev.filter((_, i) => i !== idx))
      } else {
        alert(res.error || 'Aanmaken mislukt')
      }
    } catch (e) { alert(e.message) }
    finally { setCreating(c => ({ ...c, [idx]: false })) }
  }

  async function voegAlleToe() {
    for (let i = 0; i < kandidaten.length; i++) {
      await voegToe(kandidaten[i], i)
    }
  }

  return (
    <div className="op-zoeker">
      <h3>Zoek bedrijven</h3>
      <form className="op-zoeker__form" onSubmit={zoek}>
        <label>Stad<input required value={form.stad} onChange={e => set('stad', e.target.value)} placeholder="bijv. Leiden" /></label>
        <label>Branche<input required value={form.branche} onChange={e => set('branche', e.target.value)} placeholder="bijv. kapper" /></label>
        <label>Aantal<input type="number" min="1" max="20" value={form.aantal} onChange={e => set('aantal', e.target.value)} /></label>
        {err && <p className="op-err">{err}</p>}
        <button type="submit" disabled={busy}>{busy ? 'Zoeken…' : 'Zoek'}</button>
      </form>

      {kandidaten.length > 0 && (
        <div className="op-zoeker__resultaten">
          <div className="op-zoeker__resultaten-header">
            <span>{kandidaten.length} kandidaten gevonden</span>
            <button onClick={voegAlleToe} disabled={Object.values(creating).some(Boolean)}>Voeg alle toe</button>
          </div>
          {kandidaten.map((k, i) => (
            <div key={i} className="op-zoeker__item">
              <div>
                <strong>{k.bedrijfsnaam}</strong>
                <span className="op-card__branche"> — {k.branche} in {k.plaats}</span>
              </div>
              <button onClick={() => voegToe(k, i)} disabled={creating[i]}>
                {creating[i] ? 'Toevoegen…' : '+ Toevoegen'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function PitchBox({ order, onStatusChange }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [copied, setCopied] = useState(false)

  async function markStatus(newStatus) {
    setBusy(true); setErr(null)
    try {
      const res = await api.post(`/api/orders/${order.id}/status`, { status: newStatus })
      if (res.ok) onStatusChange(res.order)
      else setErr(res.error)
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  function copy() {
    navigator.clipboard.writeText(order.pitch_tekst || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="op-pitch">
      <pre className="op-pitch__text">{order.pitch_tekst}</pre>
      <div className="op-pitch__actions">
        <button onClick={copy} disabled={!order.pitch_tekst}>{copied ? 'Gekopieerd!' : 'Kopieer pitch'}</button>
        {order.status === 'goedgekeurd' && (
          <button onClick={() => markStatus('gepitcht')} disabled={busy}>Gemarkeerd als verstuurd</button>
        )}
      </div>
      {err && <p className="op-err">{err}</p>}
    </div>
  )
}

function OrderCard({ order: initialOrder, onRefresh, onPreviewDemo, onDelete }) {
  const [order, setOrder] = useState(initialOrder)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [showPitch, setShowPitch] = useState(!!initialOrder.pitch_tekst)

  useEffect(() => { setOrder(initialOrder); setShowPitch(!!initialOrder.pitch_tekst) }, [initialOrder])

  function update(o) { setOrder(o); onRefresh() }

  async function act(endpoint, body = {}) {
    setBusy(true); setErr(null)
    try {
      const res = await api.post(`/api/orders/${order.id}/${endpoint}`, body)
      if (res.ok) update(res.order || order)
      else setErr(res.error || 'Fout')
      return res
    } catch (e) { setErr(e.message); return { ok: false } }
    finally { setBusy(false) }
  }

  function demoUrl() {
    const token = localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt') || ''
    const fname = order.demo_pad ? order.demo_pad.split('/').pop() : ''
    if (!fname) return null
    return `/api/demos/${fname}?token=${encodeURIComponent(token)}`
  }

  function openDemo() {
    const url = demoUrl()
    if (!url) return alert('Geen demo-bestand gevonden')
    window.open(url, '_blank')
  }

  async function generatePitch() {
    const res = await act('pitch')
    if (res.ok) {
      // Reload the order to get pitch_tekst
      const full = await api.get(`/api/orders/${order.id}`)
      if (full.ok) { setOrder(full.order); setShowPitch(true) }
    }
  }

  async function markStatus(s) {
    setBusy(true); setErr(null)
    try {
      const res = await api.post(`/api/orders/${order.id}/status`, { status: s })
      if (res.ok) update(res.order)
      else setErr(res.error)
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  const s = order.status

  return (
    <div className={`op-card op-card--${s}`}>
      <div className="op-card__head">
        <div>
          <strong>{order.bedrijfsnaam}</strong>
          <span className="op-card__plaats"> — {order.plaats}</span>
          <span className="op-card__branche"> ({order.branche})</span>
        </div>
        <span className={`op-badge op-badge--${s}`}>{STATUS_LABELS[s] || s}</span>
        <button className="op-card__delete" title="Verwijder order" onClick={() => {
          if (confirm(`Verwijder "${order.bedrijfsnaam}"?`)) onDelete?.(order.id)
        }}>✕</button>
      </div>

      <StatusPipe current={s} />

      <div className="op-card__meta">
        <span>€{order.prijs}</span>
        {order.contact && <span>Contact: {order.contact}</span>}
        <span className="op-card__id">{order.id}</span>
      </div>

      <div className="op-card__actions">
        {s === 'gevonden' && (
          <button onClick={() => act('demo')} disabled={busy}>Genereer demo</button>
        )}
        {(s === 'demo_klaar' || s === 'ter_review') && (<>
          <button onClick={() => onPreviewDemo?.(demoUrl())} disabled={!order.demo_pad}>Bekijk demo</button>
          <a className="op-card__newtab" href={demoUrl() || '#'} target="_blank" rel="noreferrer" title="Open in nieuw tabblad">↗</a>
          <button onClick={() => act('approve')} disabled={busy}>Keur goed</button>
        </>)}
        {s === 'goedgekeurd' && !showPitch && (
          <button onClick={generatePitch} disabled={busy}>Genereer pitch</button>
        )}
        {s === 'goedgekeurd' && order.demo_pad && (<>
          <button onClick={() => onPreviewDemo?.(demoUrl())}>Bekijk demo</button>
          <a className="op-card__newtab" href={demoUrl() || '#'} target="_blank" rel="noreferrer" title="Open in nieuw tabblad">↗</a>
        </>)}
        {s === 'gepitcht' && (
          <button onClick={() => markStatus('betaald')} disabled={busy}>Gemarkeerd als betaald</button>
        )}
        {s === 'betaald' && (
          <button onClick={() => markStatus('live')} disabled={busy}>Gemarkeerd als live</button>
        )}
        {s === 'live' && <span className="op-done">Live</span>}
      </div>

      {(showPitch || order.pitch_tekst) && (
        <PitchBox order={order} onStatusChange={o => { setOrder(o); onRefresh() }} />
      )}

      {err && <p className="op-err">{err}</p>}
    </div>
  )
}

export default function OrdersPage() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)
  const [panel, setPanel] = useState(null) // null | 'form' | 'zoeker'
  const [previewUrl, setPreviewUrl] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setErr(null)
    try {
      const res = await api.get('/api/orders')
      if (res.ok) setOrders(res.orders || [])
      else setErr(res.error || 'Fout bij laden')
    } catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  function onCreated(order) {
    setOrders(prev => [order, ...prev])
    setPanel(null)
  }

  function togglePanel(name) {
    setPanel(p => p === name ? null : name)
  }

  function handlePreviewDemo(url) {
    setPreviewUrl(prev => prev === url ? null : url)
  }

  async function handleDelete(id) {
    try {
      const res = await api.delete(`/api/orders/${id}`)
      if (res.ok) {
        setOrders(prev => prev.filter(o => o.id !== id))
        setPreviewUrl(null)
      } else {
        setErr(res.error || 'Verwijderen mislukt')
      }
    } catch (e) { setErr(e.message) }
  }

  return (
    <div className="op-root">
      <div className="op-header">
        <h2>Website-sales pipeline</h2>
        <div className="op-header__actions">
          <button
            className={panel === 'zoeker' ? 'op-btn--active' : ''}
            onClick={() => togglePanel('zoeker')}
          >
            {panel === 'zoeker' ? 'Annuleer' : 'Zoek bedrijven'}
          </button>
          <button
            className={panel === 'form' ? 'op-btn--active' : ''}
            onClick={() => togglePanel('form')}
          >
            {panel === 'form' ? 'Annuleer' : '+ Handmatig'}
          </button>
          <button onClick={load}>Vernieuwen</button>
          {previewUrl && (
            <button onClick={() => setPreviewUrl(null)} className="op-btn--active">✕ Sluit preview</button>
          )}
        </div>
      </div>

      {panel === 'form' && <NewOrderForm onCreated={onCreated} />}
      {panel === 'zoeker' && <BedrijfZoekerPanel onCreated={order => setOrders(prev => [order, ...prev])} />}

      {err && <p className="op-err op-err--page">{err}</p>}
      {loading && <p className="op-loading">Laden…</p>}

      <div className={`op-workspace${previewUrl ? ' op-workspace--split' : ''}`}>
        <div className="op-list">
          {orders.map(o => (
            <OrderCard key={o.id} order={o} onRefresh={load} onPreviewDemo={handlePreviewDemo} onDelete={handleDelete} />
          ))}
          {!loading && orders.length === 0 && (
            <p className="op-empty">Nog geen orders. Gebruik "Zoek bedrijven" of "+ Handmatig".</p>
          )}
        </div>

        {previewUrl && (
          <div className="op-demo-preview">
            <div className="op-demo-preview__bar">
              <span className="op-demo-preview__title">Demo preview</span>
              <a href={previewUrl} target="_blank" rel="noreferrer" className="op-demo-preview__newtab">Openen in nieuw tabblad ↗</a>
              <a href={previewUrl} download className="op-demo-preview__download">Downloaden ↓</a>
              <button onClick={() => setPreviewUrl(null)} className="op-demo-preview__close">✕</button>
            </div>
            <iframe
              src={previewUrl}
              className="op-demo-preview__frame"
              title="Demo preview"
              sandbox="allow-scripts allow-same-origin"
            />
          </div>
        )}
      </div>
    </div>
  )
}

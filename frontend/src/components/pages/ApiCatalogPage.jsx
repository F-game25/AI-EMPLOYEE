import { useEffect, useMemo, useState } from 'react'
import api from '../../api/client'
import './ApiCatalogPage.css'

const SOURCES = ['all', 'node', 'python']

export default function ApiCatalogPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [source, setSource] = useState('all')
  const [query, setQuery] = useState('')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.get('/api/admin/api-catalog'))
    } catch (err) {
      setError(err?.message || 'API catalog unavailable')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const routes = Array.isArray(data?.routes) ? data.routes : []
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return routes.filter(route => {
      if (source !== 'all' && route.source !== source) return false
      if (!q) return true
      return [route.route, route.method, route.source, route.compatibility, route.response_contract]
        .filter(Boolean)
        .some(value => String(value).toLowerCase().includes(q))
    })
  }, [routes, source, query])

  return (
    <main className="api-catalog">
      <section className="api-hero">
        <div>
          <p className="api-kicker">API CATALOG</p>
          <h1>Route Inventory</h1>
          <p>Registered Node and Python API surfaces with auth, compatibility, response contract, and live status labels.</p>
        </div>
        <button type="button" className="api-btn" onClick={load} disabled={loading}>
          {loading ? 'Refreshing' : 'Refresh'}
        </button>
      </section>

      <section className="api-metrics">
        <div><span>Total</span><b>{data?.counts?.total || routes.length}</b></div>
        <div><span>Node</span><b>{data?.counts?.node || 0}</b></div>
        <div><span>Python</span><b>{data?.counts?.python || 0}</b></div>
        <div><span>Canonical</span><b>{data?.counts?.canonical_or_compatibility || data?.counts?.canonical_agent_controller || 0}</b></div>
      </section>

      {error && <div className="api-alert">{error}</div>}

      <section className="api-tools">
        <div className="api-filters">
          {SOURCES.map(option => (
            <button
              key={option}
              type="button"
              className={source === option ? 'api-filter api-filter--active' : 'api-filter'}
              onClick={() => setSource(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Filter route, contract, method, source" />
      </section>

      <section className="api-table-wrap">
        <table className="api-table">
          <thead>
            <tr>
              <th>Method</th>
              <th>Route</th>
              <th>Auth</th>
              <th>Source</th>
              <th>Status</th>
              <th>Contract</th>
              <th>Compatibility</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((route, index) => (
              <tr key={`${route.source}:${route.method}:${route.route}:${index}`}>
                <td><span className="api-method">{route.method}</span></td>
                <td><code>{route.route}</code></td>
                <td>{route.auth_required ? 'required' : 'public'}</td>
                <td>{route.source}</td>
                <td><span className={`api-status api-status--${route.live_status}`}>{route.live_status}</span></td>
                <td>{route.response_contract}</td>
                <td>{route.compatibility}</td>
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan="7" className="api-empty">No routes match this catalog view.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </main>
  )
}

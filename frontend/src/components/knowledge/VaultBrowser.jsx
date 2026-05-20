import { useEffect, useState, useMemo } from 'react';
import api from '../../api/client';

const FOLDER_ICONS = { concepts: '◇', people: '◯', projects: '▤', topics: '▽', daily: '◷' };
const FOLDER_COLORS = { concepts: '#22d3ee', people: '#a855f7', projects: '#fbbf24', topics: '#22c55e', daily: '#9ca3af' };
const FOLDER_ORDER = ['concepts', 'people', 'projects', 'topics', 'daily'];

// filterState: { query: string, activeTag: string|null, sort: 'newest'|'oldest'|'alpha', searchHitIds: Set|null }
export default function VaultBrowser({ selectedId, onSelect, onNewNote, refreshKey = 0, filterState, onNotesLoaded }) {
  const [notes, setNotes] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.get('/api/vault/notes')
      .then((d) => {
        if (cancelled) return;
        const list = Array.isArray(d) ? d : (d?.notes || []);
        setNotes(list);
        onNotesLoaded?.(list);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        // 404 → vault routes not deployed yet; degrade to empty without scary message
        setError(e?.status === 404 ? null : (e?.message || 'failed to load vault'));
        setNotes([]);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const grouped = useMemo(() => {
    // Internal sidebar title search (takes precedence over external filter when both present)
    const internalQ = search.trim().toLowerCase();
    const extQ = filterState?.query?.trim().toLowerCase() || '';
    const activeTag = filterState?.activeTag || null;
    const sort = filterState?.sort || 'newest';
    const searchHitIds = filterState?.searchHitIds || null; // Set of ids from server full-text search

    let filtered = notes;

    // Full-text server search: restrict to hit IDs when present
    if (searchHitIds !== null) {
      filtered = filtered.filter(n => searchHitIds.has(n.id));
    } else if (internalQ) {
      filtered = filtered.filter(n => (n.title || n.id || '').toLowerCase().includes(internalQ));
    } else if (extQ) {
      // Client-side fallback: title + tags
      filtered = filtered.filter(n => {
        const tagStr = (n.tags || []).join(' ').toLowerCase();
        return (n.title || n.id || '').toLowerCase().includes(extQ) || tagStr.includes(extQ);
      });
    }

    if (activeTag) filtered = filtered.filter(n => (n.tags || []).includes(activeTag));

    const g = {};
    for (const n of filtered) {
      const folder = n.folder || 'concepts';
      if (!g[folder]) g[folder] = [];
      g[folder].push(n);
    }
    for (const k of Object.keys(g)) {
      if (sort === 'alpha') {
        g[k].sort((a, b) => (a.title || a.id || '').localeCompare(b.title || b.id || ''));
      } else if (sort === 'oldest') {
        g[k].sort((a, b) => (a.updated || 0) - (b.updated || 0));
      } else {
        // newest first (default)
        g[k].sort((a, b) => (b.updated || 0) - (a.updated || 0));
      }
    }
    // Ordered folder keys: known order first, then any unknown folders alphabetically
    const knownKeys = FOLDER_ORDER.filter((k) => g[k]);
    const extraKeys = Object.keys(g).filter((k) => !FOLDER_ORDER.includes(k)).sort();
    return { groups: g, order: [...knownKeys, ...extraKeys], total: filtered.length };
  }, [notes, search, filterState]);

  return (
    <div className="vb-browser">
      <style>{`
        .vb-browser { display: flex; flex-direction: column; height: 100%; background: rgba(13,13,24,0.4); border-right: 1px solid rgba(229,199,107,0.08); font-family: 'JetBrains Mono', monospace; }
        .vb-toolbar { padding: 10px 12px; border-bottom: 1px solid rgba(229,199,107,0.08); display: flex; gap: 8px; }
        .vb-search { flex: 1; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: #fff; padding: 5px 10px; border-radius: 3px; font-size: 11px; font-family: inherit; outline: none; }
        .vb-search:focus { border-color: #e5c76b; }
        .vb-new { background: #e5c76b; color: #1a1408; border: 0; padding: 5px 10px; border-radius: 3px; font-size: 10px; font-weight: 700; cursor: pointer; letter-spacing: 1px; font-family: inherit; }
        .vb-new:hover { background: #fbbf24; }
        .vb-list { flex: 1; overflow-y: auto; padding: 6px 0; }
        .vb-folder { padding: 8px 12px 4px; font-size: 9px; letter-spacing: 1.5px; color: rgba(255,255,255,0.4); text-transform: uppercase; display: flex; align-items: center; gap: 6px; }
        .vb-item { padding: 5px 12px 5px 28px; font-size: 12px; color: rgba(255,255,255,0.75); cursor: pointer; border-left: 2px solid transparent; background: transparent; border-top: 0; border-right: 0; border-bottom: 0; width: 100%; text-align: left; font-family: inherit; }
        .vb-item:hover, .vb-item:focus-visible { background: rgba(229,199,107,0.05); color: #fff; outline: none; }
        .vb-item.is-active { background: rgba(229,199,107,0.12); border-left-color: #e5c76b; color: #e5c76b; }
        .vb-empty { padding: 20px 12px; font-size: 11px; color: rgba(255,255,255,0.35); text-align: center; line-height: 1.6; }
        .vb-error { padding: 12px; font-size: 11px; color: #ef4444; }
      `}</style>

      <div className="vb-toolbar">
        <input
          className="vb-search"
          type="search"
          placeholder="Search vault…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search vault"
        />
        <button type="button" className="vb-new" onClick={() => onNewNote?.()} aria-label="New note">+ NEW</button>
      </div>

      <div className="vb-list">
        {loading && <div className="vb-empty">loading vault…</div>}
        {error && <div className="vb-error">⚠ {error}</div>}
        {!loading && !error && grouped.order.length === 0 && (
          <div className="vb-empty">
            {(search || filterState?.query || filterState?.activeTag)
              ? <>No notes match current filters.</>
              : <>Vault is empty.<br />Click + NEW to start.</>}
          </div>
        )}
        {grouped.order.map((folder) => {
          const items = grouped.groups[folder];
          return (
            <div key={folder}>
              <div className="vb-folder">
                <span style={{ color: FOLDER_COLORS[folder] || '#999' }}>{FOLDER_ICONS[folder] || '○'}</span>
                {folder} ({items.length})
              </div>
              {items.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`vb-item ${selectedId === n.id ? 'is-active' : ''}`}
                  onClick={() => onSelect?.(n.id)}
                  aria-current={selectedId === n.id ? 'true' : undefined}
                >
                  {n.title || n.id}
                </button>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

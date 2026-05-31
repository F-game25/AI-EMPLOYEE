import { useEffect, useState } from 'react';
import api from '../../api/client';

const slug = (t) => String(t || '').toLowerCase().trim().replace(/\s+/g, '-');

export default function BacklinksPanel({
  noteId,
  frontmatter = {},
  onOpenNote,
  onCreateNote,
  wikilinks = [],
  resolvedTargets,
}) {
  const [backlinks, setBacklinks] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!noteId) { setBacklinks([]); return; }
    let cancelled = false;
    setLoading(true);
    api.get(`/api/vault/notes/${encodeURIComponent(noteId)}`)
      .then((d) => { if (!cancelled) setBacklinks(d?.backlinks || []); })
      .catch(() => { if (!cancelled) setBacklinks([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [noteId]);

  const resolved = resolvedTargets instanceof Set ? resolvedTargets : new Set(resolvedTargets || []);
  const brokenLinks = (wikilinks || []).filter((t) => !resolved.has(slug(t)));
  const confidence = frontmatter.confidence ?? 0.5;
  const confPct = Math.max(0, Math.min(100, confidence * 100));

  return (
    <div className="bp-panel">
      <style>{`
        .bp-panel { display: flex; flex-direction: column; gap: 16px; padding: 12px; color: rgba(255,255,255,0.85); font-family: 'JetBrains Mono', monospace; }
        .bp-section { background: rgba(13,13,24,0.4); border: 1px solid rgba(229,199,107,0.08); border-radius: 4px; padding: 12px; }
        .bp-title { font-size: 10px; letter-spacing: 1.5px; color: #e5c76b; margin-bottom: 8px; text-transform: uppercase; }
        .bp-empty { font-size: 11px; color: rgba(255,255,255,0.35); font-style: italic; }
        .bp-item { display: flex; align-items: center; padding: 4px 6px; font-size: 12px; cursor: pointer; border-radius: 2px; color: #22d3ee; background: transparent; border: 0; width: 100%; text-align: left; font-family: inherit; }
        .bp-item:hover, .bp-item:focus-visible { background: rgba(34,211,238,0.08); outline: none; }
        .bp-broken { color: #fbbf24; cursor: pointer; padding: 4px 6px; font-size: 12px; border-radius: 2px; background: transparent; border: 0; width: 100%; text-align: left; font-family: inherit; }
        .bp-broken:hover, .bp-broken:focus-visible { background: rgba(245,158,11,0.1); outline: none; }
        .bp-fm-row { display: grid; grid-template-columns: 90px 1fr; gap: 6px; font-size: 11px; padding: 3px 0; align-items: start; }
        .bp-fm-key { color: rgba(255,255,255,0.4); }
        .bp-fm-val { color: rgba(255,255,255,0.85); word-break: break-all; }
        .bp-tag { display: inline-block; background: rgba(229,199,107,0.1); color: #e5c76b; padding: 1px 6px; border-radius: 3px; font-size: 9px; margin: 2px 4px 2px 0; }
        .bp-conf-bar { height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden; margin-top: 4px; }
        .bp-conf-fill { height: 100%; background: linear-gradient(90deg, #ef4444 0%, #fbbf24 50%, #22c55e 100%); transition: width 200ms ease; }
      `}</style>

      <div className="bp-section">
        <div className="bp-title">Metadata</div>
        <div className="bp-fm-row"><span className="bp-fm-key">id</span><span className="bp-fm-val">{noteId || '—'}</span></div>
        <div className="bp-fm-row">
          <span className="bp-fm-key">tags</span>
          <span className="bp-fm-val">
            {(frontmatter.tags || []).length === 0
              ? <span style={{ color: 'rgba(255,255,255,0.3)' }}>—</span>
              : (frontmatter.tags || []).map((t) => <span key={t} className="bp-tag">{t}</span>)}
          </span>
        </div>
        <div className="bp-fm-row">
          <span className="bp-fm-key">confidence</span>
          <span className="bp-fm-val">
            {confPct.toFixed(0)}%
            <div className="bp-conf-bar"><div className="bp-conf-fill" style={{ width: `${confPct}%` }} /></div>
          </span>
        </div>
        <div className="bp-fm-row"><span className="bp-fm-key">verified by</span><span className="bp-fm-val">{frontmatter.verified_by || 'user'}</span></div>
        <div className="bp-fm-row"><span className="bp-fm-key">sources</span><span className="bp-fm-val">{(frontmatter.sources || []).length}</span></div>
      </div>

      <div className="bp-section">
        <div className="bp-title">Linked from ({backlinks.length})</div>
        {loading ? (
          <div className="bp-empty">loading…</div>
        ) : backlinks.length === 0 ? (
          <div className="bp-empty">No notes link here yet</div>
        ) : (
          backlinks.map((b) => {
            const id = typeof b === 'string' ? b : (b?.id ?? b?.target ?? '');
            const label = typeof b === 'string' ? b : (b?.title || b?.id || id);
            return (
              <button key={id} type="button" className="bp-item" onClick={() => onOpenNote?.(id)}>
                ← {label}
              </button>
            );
          })
        )}
      </div>

      {brokenLinks.length > 0 && (
        <div className="bp-section">
          <div className="bp-title">Unresolved links ({brokenLinks.length})</div>
          {brokenLinks.map((t) => (
            <button key={t} type="button" className="bp-broken" onClick={() => onCreateNote?.(t)}>
              + Create "[[{t}]]"
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

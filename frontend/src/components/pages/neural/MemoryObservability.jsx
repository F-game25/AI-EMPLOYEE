import { EmptyState, ErrorState } from '../../nexus-ui'
import Panel from '../../nexus-ui/Panel'
import SectionLabel from '../../nexus-ui/SectionLabel'
import StatusPill from '../../nexus-ui/StatusPill'

function laneTone(lane) {
  const state = String(lane?.state || '').toLowerCase()
  if (state === 'live') return 'success'
  if (state === 'degraded') return 'warn'
  if (state === 'empty') return 'idle'
  return lane?.ready ? 'success' : 'idle'
}

function MemoryStatusCard({ title, lane, metrics = [] }) {
  return (
    <Panel title={title} size="compact" tight corners>
      <div className="nnp-memory-card">
        <div className="nnp-memory-card__head">
          <StatusPill label={(lane?.state || 'unknown').toUpperCase()} tone={laneTone(lane)} size="sm" dot={lane?.ready} />
          <span>{lane?.source || 'not connected'}</span>
        </div>
        <div className="nnp-memory-card__metrics">
          {metrics.map(([label, value]) => (
            <div key={label} className="nnp-memory-card__metric">
              <span>{label}</span>
              <strong>{value ?? 0}</strong>
            </div>
          ))}
        </div>
        {lane?.degraded_reason && <div className="nnp-memory-card__reason">{lane.degraded_reason}</div>}
      </div>
    </Panel>
  )
}

function RouterTraceResult({ result }) {
  if (!result) return (
    <EmptyState icon="[]" title="No retrieval test yet" sub="Run a query to see which memory routes the main AI selects." />
  )
  return (
    <div className="nnp-router-result">
      <div className="nnp-router-result__summary">
        <StatusPill label={result.degraded ? 'DEGRADED' : 'LIVE'} tone={result.degraded ? 'warn' : 'success'} size="sm" />
        <span>confidence {(Number(result.confidence || 0) * 100).toFixed(0)}%</span>
        <span>{result.context?.estimated_tokens || 0} tokens</span>
        <span>{result.trace_id}</span>
      </div>
      <div className="nnp-route-grid">
        {(result.routes || []).map(route => (
          <div key={route.id} className="nnp-route-card">
            <div className="nnp-route-card__title">{route.id}</div>
            <div className="nnp-route-card__meta">{route.hits} hit(s)</div>
            <div className="nnp-route-card__reason">{route.reason}</div>
          </div>
        ))}
      </div>
      {!!result.diagnostics?.length && (
        <div className="nnp-memory-card__reason">{result.diagnostics.join(' · ')}</div>
      )}
      <div className="nnp-router-context">
        <SectionLabel rule>ASSEMBLED CONTEXT</SectionLabel>
        <pre>{result.context?.text || 'No context assembled.'}</pre>
      </div>
      <div className="nnp-router-citations">
        <SectionLabel rule>CITATIONS</SectionLabel>
        {(result.citations || []).slice(0, 12).map((citation, index) => (
          <div key={`${citation.route}-${index}`} className="nnp-citation-row">
            <span>{citation.route}</span>
            <strong>{citation.title}</strong>
            <em>{citation.source || citation.citation}</em>
          </div>
        ))}
        {!result.citations?.length && <div className="nnp-memory-card__reason">No citations returned.</div>}
      </div>
    </div>
  )
}

function MemoryObservability({
  tab,
  status,
  statusError,
  query,
  setQuery,
  retrievalResult,
  retrievalBusy,
  retrievalError,
  onRunRetrieval,
  sqlForm,
  setSqlForm,
  sqlResult,
  onRunSql,
  maintenance,
  maintenanceBusy,
  maintenanceMessage,
  restoreConfirm,
  setRestoreConfirm,
  selectedBackup,
  setSelectedBackup,
  mergeConfirm,
  setMergeConfirm,
  onGraphBackup,
  onGraphRepair,
  onGraphRestore,
  onGraphMerge,
}) {
  const lanes = status?.router?.lanes || {}
  if (statusError) {
    return <ErrorState title="Memory observability unavailable" message={statusError} />
  }

  if (tab === 'router') {
    return (
      <div className="nnp-memory-view">
        <Panel title="Test Hybrid Retrieval" size="compact" tight corners>
          <form className="nnp-router-form" onSubmit={onRunRetrieval}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Ask a memory question, e.g. failed tasks last week, how X relates to Y, or what did we discuss before"
            />
            <button disabled={retrievalBusy}>{retrievalBusy ? 'Routing...' : 'Run Retrieval'}</button>
          </form>
          {retrievalError && <div className="nnp-memory-card__reason">{retrievalError}</div>}
        </Panel>
        <RouterTraceResult result={retrievalResult} />
      </div>
    )
  }

  if (tab === 'rag') {
    const lane = lanes.semantic_rag || status?.semantic
    return (
      <div className="nnp-memory-grid">
        <MemoryStatusCard title="Semantic RAG" lane={lane} metrics={[
          ['Items', lane?.item_count],
          ['Chroma', lane?.chroma_present ? 'yes' : 'no'],
        ]} />
        <Panel title="Route Purpose" size="compact" tight corners>
          <div className="nnp-memory-card__reason">Used for fuzzy document, notes, research and knowledge retrieval. Best for semantic similarity and citation-backed answers.</div>
        </Panel>
      </div>
    )
  }

  if (tab === 'kg') {
    const lane = lanes.knowledge_graph || status?.graph
    const backups = maintenance?.backups || []
    const integrity = maintenance?.integrity || lane?.integrity
    const conflicts = maintenance?.conflicts || []
    const primaryConflict = conflicts[0]
    return (
      <div className="nnp-memory-view">
        <div className="nnp-memory-grid">
          <MemoryStatusCard title="Knowledge Graph" lane={lane} metrics={[
            ['Nodes', lane?.node_count],
            ['Edges', lane?.edge_count],
            ['Native backend', lane?.extension_required === false ? 'yes' : 'no'],
            ['Schema', lane?.schema_version ? `v${lane.schema_version}` : 'pending'],
            ['Integrity', integrity?.status || (lane?.ready ? 'ok' : 'pending')],
            ['Backups', lane?.backup_count ?? backups.length ?? 0],
          ]} />
          <Panel title="Route Purpose" size="compact" tight corners>
            <div className="nnp-memory-card__reason">Used for relationships, dependencies, entity paths and multi-hop reasoning. The graph memory is embedded and offline-native; Neo4j-compatible capability is treated as a core backend, not a user extension.</div>
          </Panel>
        </div>
        <Panel title="Native Graph Maintenance" size="compact" tight corners>
          <div className="nnp-maintenance">
            <div className="nnp-maintenance__summary">
              <StatusPill label={(integrity?.status || 'pending').toUpperCase()} tone={integrity?.ok !== false ? 'success' : 'warn'} size="sm" dot={integrity?.ok !== false} />
              <span>{integrity?.errors?.length ? integrity.errors.join(' · ') : 'Embedded graph integrity checks are clean.'}</span>
            </div>
            <div className="nnp-maintenance__actions">
              <button type="button" onClick={onGraphBackup} disabled={maintenanceBusy}>{maintenanceBusy ? 'Working...' : 'Create Backup'}</button>
              <button type="button" onClick={onGraphRepair} disabled={maintenanceBusy}>Repair Graph</button>
            </div>
            {maintenanceMessage && <div className="nnp-memory-card__reason">{maintenanceMessage}</div>}
          </div>
        </Panel>
        <Panel title="Restore Point" size="compact" tight corners>
          <div className="nnp-restore">
            <select value={selectedBackup} onChange={e => setSelectedBackup(e.target.value)}>
              <option value="">Select backup</option>
              {backups.map(backup => (
                <option key={backup.id} value={backup.id}>
                  {backup.created_at} · {backup.kind} · {Math.round((backup.bytes || 0) / 1024)} KB
                </option>
              ))}
            </select>
            <input
              value={restoreConfirm}
              onChange={e => setRestoreConfirm(e.target.value)}
              placeholder="Type RESTORE_NATIVE_GRAPH"
            />
            <button
              type="button"
              onClick={onGraphRestore}
              disabled={maintenanceBusy || !selectedBackup || restoreConfirm !== 'RESTORE_NATIVE_GRAPH'}
            >
              Restore Selected Backup
            </button>
            {!backups.length && <EmptyState icon="[]" title="No graph backups" sub="Create a backup before running risky graph maintenance." />}
          </div>
        </Panel>
        <Panel title="Entity Conflict Review" size="compact" tight corners>
          <div className="nnp-conflicts">
            {conflicts.slice(0, 8).map(group => (
              <div key={group.label} className="nnp-conflict-row">
                <div>
                  <strong>{group.label}</strong>
                  <span>{group.count} duplicate candidate(s)</span>
                  <em>{group.candidates?.map(node => node.id).join(', ')}</em>
                </div>
              </div>
            ))}
            {!conflicts.length && <EmptyState icon="[]" title="No duplicate entities" sub="The native graph has no exact-label merge candidates." />}
            {!!primaryConflict && (
              <div className="nnp-restore">
                <input
                  value={mergeConfirm}
                  onChange={e => setMergeConfirm(e.target.value)}
                  placeholder="Type MERGE_NATIVE_GRAPH"
                />
                <button
                  type="button"
                  onClick={() => onGraphMerge(primaryConflict)}
                  disabled={maintenanceBusy || mergeConfirm !== 'MERGE_NATIVE_GRAPH'}
                >
                  Merge Highest Confidence Group
                </button>
              </div>
            )}
          </div>
        </Panel>
      </div>
    )
  }

  if (tab === 'sql') {
    const sql = status?.sql || lanes.structured_sql || {}
    return (
      <div className="nnp-memory-view">
        <div className="nnp-memory-grid">
          <MemoryStatusCard title="SQL Memory" lane={sql} metrics={[
            ['Databases', sql.databases?.length || 0],
            ['Max rows', sql.max_rows || 100],
            ['Read only', sql.readonly ? 'yes' : 'no'],
          ]} />
          <Panel title="Read-only Query" size="compact" tight corners>
            <form className="nnp-router-form nnp-router-form--stack" onSubmit={onRunSql}>
              <select value={sqlForm.database} onChange={e => setSqlForm({ ...sqlForm, database: e.target.value })}>
                <option value="">Select database</option>
                {(sql.databases || []).map(db => <option key={db.id} value={db.id}>{db.name}</option>)}
              </select>
              <textarea rows={4} value={sqlForm.sql} onChange={e => setSqlForm({ ...sqlForm, sql: e.target.value })} placeholder="SELECT ... LIMIT 50" />
              <button>Run Read-only SQL</button>
            </form>
          </Panel>
        </div>
        <Panel title="SQL Databases" size="compact" tight corners>
          <div className="nnp-table-list">
            {(sql.databases || []).map(db => (
              <div key={db.id} className="nnp-db-row">
                <strong>{db.name}</strong>
                <span>{db.tables?.length || 0} table(s)</span>
                <em>{(db.tables || []).slice(0, 5).map(t => t.name).join(', ') || db.error || 'no tables'}</em>
              </div>
            ))}
            {!sql.databases?.length && <EmptyState icon="[]" title="No local SQL databases" sub="Structured memory will appear when local state DBs exist." />}
          </div>
        </Panel>
        {sqlResult && (
          <Panel title="SQL Result Preview" size="compact" tight corners>
            <pre className="nnp-sql-result">{JSON.stringify(sqlResult.rows || sqlResult, null, 2)}</pre>
          </Panel>
        )}
      </div>
    )
  }

  if (tab === 'episodic') {
    const lane = lanes.episodic_session || status?.episodic
    return (
      <div className="nnp-memory-grid">
        <MemoryStatusCard title="Episodic Session Memory" lane={lane} metrics={[
          ['Conversations', lane?.conversation_count],
          ['Interactions', lane?.recent_interactions],
        ]} />
        <Panel title="Route Purpose" size="compact" tight corners>
          <div className="nnp-memory-card__reason">Used when the user asks to continue, remember prior context, inspect conversation history, or preserve task continuity.</div>
        </Panel>
      </div>
    )
  }

  if (tab === 'procedural') {
    const lane = lanes.procedural_skills || status?.procedural
    return (
      <div className="nnp-memory-grid">
        <MemoryStatusCard title="Procedural Memory" lane={lane} metrics={[
          ['Skills', lane?.skill_count],
          ['Agents', lane?.agent_count],
          ['Workflows', lane?.workflow_count],
        ]} />
        <Panel title="Active Packs" size="compact" tight corners>
          <div className="nnp-pack-list">
            {(lane?.packs || []).slice(0, 40).map(pack => <span key={pack}>{pack}</span>)}
            {!lane?.packs?.length && <EmptyState icon="[]" title="No procedural packs" sub="Skills and workflow templates are not loaded." />}
          </div>
        </Panel>
      </div>
    )
  }

  return null
}

export default MemoryObservability

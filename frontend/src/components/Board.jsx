import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { fmtAgo, fmtEta } from '../format'
import { StatusPill, Loading, ErrorBox, navigate } from './Common'
import { ControlBar } from './Control'

function ProgressBar({ q }) {
  const total = Math.max(q.total, 1)
  const pct = (n) => `${(100 * n) / total}%`
  const running = q.running ? 1 : 0
  return (
    <div className="progress" title={`${q.completed}/${q.total} runs`}>
      <div className="seg ok" style={{ width: pct(q.passed) }} />
      <div className="seg fail" style={{ width: pct(q.failed) }} />
      <div className="seg run" style={{ width: pct(running) }} />
    </div>
  )
}

function QueueCard({ q }) {
  const eta = fmtEta(q.eta_seconds)
  return (
    <div
      className={`card ${q.running ? 'is-running' : ''}`}
      onClick={() => navigate(`#/q/${encodeURIComponent(q.id)}`)}
    >
      <div className="head">
        <div>
          <div className="stem">{q.stem}</div>
          <div className="ts">{q.id.slice(q.stem.length + 1)}</div>
        </div>
        <StatusPill status={q.status} />
      </div>
      <ProgressBar q={q} />
      <div className="foot">
        <span className="counts">
          <b>{q.completed}</b>/{q.total} runs
          {q.failed > 0 && <span style={{ color: 'var(--fail)' }}> · {q.failed} failed</span>}
        </span>
        {q.running && eta ? (
          <span className="eta">{eta}</span>
        ) : (
          <span>{fmtAgo(q.last_activity)}</span>
        )}
      </div>
    </div>
  )
}

// Match a queue against a free-text query (case-insensitive, all terms must hit).
// Searches the experiment name, the full run id (carries the timestamp) and status.
function matchesQuery(q, terms) {
  if (terms.length === 0) return true
  const hay = `${q.stem} ${q.id} ${q.status}`.toLowerCase()
  return terms.every((t) => hay.includes(t))
}

export default function Board() {
  const [queues, setQueues] = useState(null)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')

  const load = useCallback(
    () => api.queues().then(setQueues).catch(setError),
    [],
  )
  useEffect(() => {
    load()
    const t = setInterval(load, 5000) // light board-level poll
    return () => clearInterval(t)
  }, [load])

  if (error) return <><ControlBar onChanged={load} /><ErrorBox error={error} /></>
  if (!queues) return <><ControlBar onChanged={load} /><Loading what="queues" /></>

  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const filtered = queues.filter((q) => matchesQuery(q, terms))
  const running = filtered.filter((q) => q.running)
  const rest = filtered.filter((q) => !q.running)

  return (
    <div>
      <ControlBar onChanged={load} />
      {queues.length > 0 && (
        <div className="board-search">
          <input
            className="txt search-input"
            type="search"
            placeholder="search experiments by name, timestamp, status…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          {terms.length > 0 && (
            <span className="search-count">{filtered.length} / {queues.length}</span>
          )}
        </div>
      )}
      {queues.length === 0 && <div className="empty-state">no queue-runs found under logs/_queue</div>}
      {queues.length > 0 && filtered.length === 0 && (
        <div className="empty-state">no experiments match “{query.trim()}”</div>
      )}
      {running.length > 0 && (
        <>
          <div className="section-title">running now</div>
          <div className="board">{running.map((q) => <QueueCard key={q.id} q={q} />)}</div>
        </>
      )}
      {rest.length > 0 && (
        <>
          <div className="section-title">{running.length ? 'history' : 'all experiments'}</div>
          <div className="board">{rest.map((q) => <QueueCard key={q.id} q={q} />)}</div>
        </>
      )}
    </div>
  )
}

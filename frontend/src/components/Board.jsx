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
// Searches the experiment name, the full run id (carries the timestamp), the
// inferred task/env and status.
function matchesQuery(q, terms) {
  if (terms.length === 0) return true
  const hay = `${q.stem} ${q.id} ${q.env || ''} ${q.status}`.toLowerCase()
  return terms.every((t) => hay.includes(t))
}

const UNGROUPED = '— unknown task —'

// Group queue-runs by their inferred task/env, ordered by most-recent activity.
// Each group's experiments are sorted newest-first (temporal order in a group).
function groupByTask(queues) {
  const byTask = new Map()
  for (const q of queues) {
    const key = q.env || UNGROUPED
    if (!byTask.has(key)) byTask.set(key, [])
    byTask.get(key).push(q)
  }
  const groups = []
  for (const [task, items] of byTask) {
    items.sort((a, b) => (b.last_activity || '').localeCompare(a.last_activity || ''))
    groups.push({ task, items, lastActivity: items[0]?.last_activity || '' })
  }
  groups.sort((a, b) => b.lastActivity.localeCompare(a.lastActivity))
  return groups
}

function TaskGroup({ group, collapsed, onToggle }) {
  const { task, items } = group
  return (
    <section className="task-group">
      <button className="task-head" onClick={onToggle} aria-expanded={!collapsed}>
        <span className={`task-caret ${collapsed ? 'is-collapsed' : ''}`}>▾</span>
        <span className="task-name">{task}</span>
        <span className="task-count">{items.length}</span>
      </button>
      {!collapsed && (
        <div className="board">{items.map((q) => <QueueCard key={q.id} q={q} />)}</div>
      )}
    </section>
  )
}

const COLLAPSE_KEY = 'cockpit.collapsedTasks'

function loadCollapsed() {
  try {
    return new Set(JSON.parse(localStorage.getItem(COLLAPSE_KEY)) || [])
  } catch {
    return new Set()
  }
}

export default function Board() {
  const [queues, setQueues] = useState(null)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [collapsed, setCollapsed] = useState(loadCollapsed)

  const load = useCallback(
    () => api.queues().then(setQueues).catch(setError),
    [],
  )
  useEffect(() => {
    load()
    const t = setInterval(load, 5000) // light board-level poll
    return () => clearInterval(t)
  }, [load])

  const toggleTask = useCallback((task) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      next.has(task) ? next.delete(task) : next.add(task)
      try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...next])) } catch { /* ignore */ }
      return next
    })
  }, [])

  if (error) return <><ControlBar onChanged={load} /><ErrorBox error={error} /></>
  if (!queues) return <><ControlBar onChanged={load} /><Loading what="queues" /></>

  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const filtered = queues.filter((q) => matchesQuery(q, terms))
  // Running experiments get their own section up top; the per-task groups below
  // hold only the rest, so every group is freely collapsible.
  const running = filtered
    .filter((q) => q.running)
    .sort((a, b) => (b.last_activity || '').localeCompare(a.last_activity || ''))
  const groups = groupByTask(filtered.filter((q) => !q.running))

  return (
    <div>
      <ControlBar onChanged={load} />
      {queues.length > 0 && (
        <div className="board-search">
          <input
            className="txt search-input"
            type="search"
            placeholder="search experiments by name, task, timestamp, status…"
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
      {groups.map((g) => (
        <TaskGroup
          key={g.task}
          group={g}
          collapsed={collapsed.has(g.task)}
          onToggle={() => toggleTask(g.task)}
        />
      ))}
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { fmtAgo } from '../format'
import { Loading, ErrorBox } from './Common'
import QueueEditor from './QueueEditor'

// The "scheduled" tab: the pending queue of experiments waiting to run. NOT a
// log of what already ran (that lives in the experiments tab) — only what's
// lined up. The backend dispatcher launches the head entry onto a GPU as soon
// as one frees up.

function ScheduledRow({ entry, pos, anyFree, onEdit, onRemove, removing }) {
  const next = pos === 0
  const launching = next && anyFree
  return (
    <div className="spec-row">
      <span className={`sched-pos ${next ? 'next' : ''}`}>{pos + 1}</span>
      <div className="info">
        <div className="nm">
          {entry.queue}
          {entry.start_from != null && <span className="sm2"> · from #{entry.start_from}</span>}
        </div>
        <div className="sm2">
          scheduled {fmtAgo(entry.enqueued_at)}
          {next && (anyFree
            ? <span style={{ color: 'var(--ok)' }}> · launching…</span>
            : <span style={{ color: 'var(--run)' }}> · next — waiting for a free GPU</span>)}
        </div>
      </div>
      <button className="btn sm" disabled={launching} onClick={() => onEdit(entry)}
              title={launching ? 'launching — too late to edit' : 'edit this experiment’s queue'}>
        Edit…
      </button>
      <button className="btn danger sm" disabled={removing === entry.id} onClick={() => onRemove(entry)}>
        {removing === entry.id ? 'removing…' : 'Remove'}
      </button>
    </div>
  )
}

export default function Scheduled({ anyFree }) {
  const [entries, setEntries] = useState(null)
  const [error, setError] = useState(null)
  const [removing, setRemoving] = useState(null)
  const [editing, setEditing] = useState(null)

  const load = useCallback(() => api.schedule().then(setEntries).catch(setError), [])
  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [load])

  const remove = async (entry) => {
    setRemoving(entry.id); setError(null)
    try { await api.removeSchedule(entry.id); await load() }
    catch (e) { setError(e) }
    finally { setRemoving(null) }
  }

  if (error) return <ErrorBox error={error} />
  if (!entries) return <Loading what="schedule" />

  return (
    <div>
      <div className="sched-head">
        <span className="faint">
          {entries.length === 0
            ? 'nothing scheduled'
            : `${entries.length} queue${entries.length > 1 ? 's' : ''} waiting — each launches when a GPU frees up`}
        </span>
      </div>
      {entries.length === 0 ? (
        <div className="empty-state">
          No experiments scheduled. Use “Schedule experiment” to line one up — it
          runs automatically when a GPU is free.
        </div>
      ) : (
        <div className="spec-list board-specs">
          {entries.map((e, i) => (
            <ScheduledRow key={e.id} entry={e} pos={i} anyFree={anyFree}
                          onEdit={setEditing} onRemove={remove} removing={removing} />
          ))}
        </div>
      )}
      {editing && (
        <QueueEditor
          title="Edit scheduled experiment"
          saveLabel="Save"
          note="Edits this experiment’s staged queue copy in the logs — the learning/queues template is left untouched."
          load={() => api.scheduleSpec(editing.id)}
          onSave={async (content) => {
            await api.editSchedule(editing.id, content)
            setEditing(null)
            await load()
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

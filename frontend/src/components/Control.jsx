import { useEffect, useState } from 'react'
import { api } from '../api'

function GpuChip({ row, onStop, stopping }) {
  if (row.queue) {
    return (
      <div className="gpu-chip busy">
        <span className="pill running"><span className="led" />gpu{row.gpu}</span>
        <span className="lbl" title={row.container}>{row.queue}</span>
        <button className="btn danger sm" onClick={() => onStop(row)} disabled={stopping === row.container}>
          {stopping === row.container ? 'stopping…' : 'Stop'}
        </button>
      </div>
    )
  }
  return (
    <div className={`gpu-chip ${row.free ? 'free' : 'occupied'}`}>
      <span className="pill empty"><span className="led" />gpu{row.gpu}</span>
      <span className="lbl" title={row.container}>
        {row.free ? 'free' : `busy · ${row.mem_used ?? '?'} MiB`}
      </span>
    </div>
  )
}

export function ControlBar({ onChanged }) {
  const [status, setStatus] = useState(null)
  const [err, setErr] = useState(null)
  const [showLaunch, setShowLaunch] = useState(false)
  const [stopping, setStopping] = useState(null)

  const refresh = () => api.controlStatus().then(setStatus).catch((e) => setErr(e.message))
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  const stop = async (row) => {
    if (!window.confirm(`Stop "${row.queue}" on gpu${row.gpu} (${row.container})? SIGINTs run_queue.py and kills its training child.`)) return
    setStopping(row.container); setErr(null)
    try { await api.stop(row.container); await refresh(); onChanged?.() }
    catch (e) { setErr(e.message) }
    finally { setStopping(null) }
  }

  const rows = status?.containers || []
  const anyFree = status?.any_free
  return (
    <div className="controlbar">
      <span className="lbl">GPUs</span>
      {rows.length === 0 && <span className="faint">no dev containers found</span>}
      {rows.map((r) => <GpuChip key={r.container} row={r} onStop={stop} stopping={stopping} />)}
      <span className="grow" />
      {err && <span className="act-error">{err}</span>}
      <button className="btn primary sm" disabled={!anyFree} onClick={() => setShowLaunch(true)}
              title={anyFree ? 'dispatch to a free GPU' : 'no free GPU'}>
        ＋ Launch queue
      </button>
      {showLaunch && (
        <LaunchModal
          onClose={() => setShowLaunch(false)}
          onLaunched={async () => { setShowLaunch(false); await refresh(); onChanged?.() }}
        />
      )}
    </div>
  )
}

export function QueueActions({ queue, onChanged }) {
  const [text, setText] = useState(queue.conclusion?.text || '')
  const [savedAt, setSavedAt] = useState(queue.conclusion?.updated_at || null)
  const [n, setN] = useState('2')
  const [steps, setSteps] = useState('50000000')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(null)
  const [showPlan, setShowPlan] = useState(false)

  const saveNote = async () => {
    setBusy('note'); setErr(null)
    try { const r = await api.putConclusion(queue.id, text); setSavedAt(r.updated_at) }
    catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  const resume = async () => {
    if (!window.confirm(`Resume the last ${n} run(s) of this queue for ${Number(steps).toLocaleString()} more steps each? Starts GPU training.`)) return
    setBusy('resume'); setErr(null)
    try { await api.resume(queue.id, Number(n), Number(steps)); onChanged?.() }
    catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <div className="section-title" style={{ margin: '0 0 10px' }}>conclusion</div>
      <textarea className="note" placeholder="What did this experiment show? (saved to notes/, shown next time)"
                value={text} onChange={(e) => setText(e.target.value)} />
      <div className="action-row" style={{ marginTop: 8 }}>
        <button className="btn sm" onClick={saveNote} disabled={busy === 'note'}>
          {busy === 'note' ? 'saving…' : 'Save conclusion'}
        </button>
        {savedAt && <span className="note-meta">saved {new Date(savedAt).toLocaleString()}</span>}
      </div>

      <div className="section-title" style={{ margin: '20px 0 10px' }}>next steps</div>
      <div className="action-row">
        <span className="lbl">resume last</span>
        <input className="num" type="number" min="1" value={n} onChange={(e) => setN(e.target.value)} />
        <span className="lbl">run(s) for</span>
        <input className="num" type="number" min="1000000" step="10000000" value={steps} onChange={(e) => setSteps(e.target.value)} style={{ width: 130 }} />
        <span className="lbl">steps</span>
        <button className="btn sm" onClick={resume} disabled={busy === 'resume'}>
          {busy === 'resume' ? 'resuming…' : 'Resume'}
        </button>
        <span style={{ width: 12 }} />
        <button className="btn sm" onClick={() => setShowPlan(true)}>Plan next queue →</button>
      </div>
      {err && <div className="act-error" style={{ marginTop: 8 }}>{err}</div>}

      {showPlan && <PlanNextModal queueId={queue.id} onClose={() => setShowPlan(false)} />}
    </div>
  )
}

function PlanNextModal({ queueId, onClose }) {
  const [draft, setDraft] = useState(null)
  const [filename, setFilename] = useState('')
  const [content, setContent] = useState('')
  const [err, setErr] = useState(null)
  const [saved, setSaved] = useState(null)
  const [overwrite, setOverwrite] = useState(false)

  useEffect(() => {
    api.planNext(queueId).then((d) => { setDraft(d); setFilename(d.filename); setContent(d.yaml) })
      .catch((e) => setErr(e.message))
  }, [queueId])

  const save = async () => {
    setErr(null)
    try { const r = await api.saveQueue(filename, content, overwrite); setSaved(r) }
    catch (e) { setErr(e.message) }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <span className="close" onClick={onClose}>×</span>
        <h3>Plan next queue</h3>
        {!draft ? <div className="loading">drafting…</div> : (
          <>
            <div className="action-row" style={{ marginBottom: 10 }}>
              <span className="lbl">save as</span>
              <input className="txt" value={filename} onChange={(e) => setFilename(e.target.value)} style={{ width: 280 }} />
              <label className="lbl" style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} /> overwrite
              </label>
            </div>
            <textarea className="code" value={content} onChange={(e) => setContent(e.target.value)} />
            <div className="action-row" style={{ marginTop: 10 }}>
              <button className="btn primary sm" onClick={save}>Save to learning/queues/</button>
              {saved && <span className="note-meta" style={{ color: 'var(--ok)' }}>saved → {saved.path}</span>}
              {err && <span className="act-error">{err}</span>}
            </div>
            <div className="faint" style={{ fontSize: 11, marginTop: 8 }}>
              Saves the YAML; launch it afterwards from the board's “Launch queue”.
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function LaunchModal({ onClose, onLaunched }) {
  const [specs, setSpecs] = useState(null)
  const [startFrom, setStartFrom] = useState('')
  const [err, setErr] = useState(null)
  const [launching, setLaunching] = useState(null)

  useEffect(() => { api.specs().then(setSpecs).catch((e) => setErr(e.message)) }, [])

  const launch = async (stem) => {
    if (!window.confirm(`Launch "${stem}"${startFrom ? ` from #${startFrom}` : ''}? This starts GPU training.`)) return
    setLaunching(stem); setErr(null)
    try { await api.launch(stem, startFrom ? Number(startFrom) : null); onLaunched() }
    catch (e) { setErr(e.message); setLaunching(null) }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <span className="close" onClick={onClose}>×</span>
        <h3>Launch a queue</h3>
        <div className="action-row" style={{ marginBottom: 12 }}>
          <span className="lbl">start from run #</span>
          <input className="num" type="number" min="0" placeholder="0" value={startFrom}
                 onChange={(e) => setStartFrom(e.target.value)} />
          <span className="faint" style={{ fontSize: 11 }}>optional — skip earlier runs</span>
        </div>
        {err && <div className="act-error" style={{ marginBottom: 10 }}>{err}</div>}
        {!specs ? <div className="loading">loading specs…</div> : (
          <div className="spec-list">
            {specs.map((s) => (
              <div className="spec-row" key={s.stem}>
                <div className="info">
                  <div className="nm">{s.stem}</div>
                  <div className="sm2">
                    {s.n_runs != null ? `${s.n_runs} runs` : 'runs ?'}
                    {s.axes?.length > 0 && ` · ${s.axes.map((a) => a.split('.').pop()).join(' × ')}`}
                    {s.has_hypothesis && ' · has hypothesis'}
                  </div>
                  {s.summary && <div className="sm2" style={{ marginTop: 3, color: 'var(--txt-dim)' }}>{s.summary}</div>}
                </div>
                <button className="btn primary sm" disabled={launching} onClick={() => launch(s.stem)}>
                  {launching === s.stem ? 'launching…' : 'Launch'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

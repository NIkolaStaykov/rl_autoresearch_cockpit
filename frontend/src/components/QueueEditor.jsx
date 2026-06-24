import { useEffect, useRef, useState } from 'react'

// Editable YAML modal. `load` is an async fn returning { stem, yaml }; `onSave`
// is an async fn called with the edited text. Used to tweak a queue's YAML
// before scheduling it, and to edit a pending scheduled experiment's staged
// copy — neither touches the learning/queues template.
export default function QueueEditor({ title, note, saveLabel = 'Save', load, onSave, onClose }) {
  const [stem, setStem] = useState(null)
  const [content, setContent] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  // Load the YAML once, when the editor opens. `load` is typically a fresh
  // inline closure each render, so depending on its identity would re-fetch on
  // every parent re-render (the control bar / scheduled tab poll on intervals)
  // and clobber what you've typed. Capture the mount-time closure in a ref so
  // the effect can run exactly once.
  const loadRef = useRef(load)
  useEffect(() => {
    let alive = true
    loadRef.current()
      .then((d) => { if (alive) { setStem(d.stem); setContent(d.yaml) } })
      .catch((e) => alive && setErr(e.message))
    return () => { alive = false }
  }, [])

  const save = async () => {
    setBusy(true); setErr(null)
    try { await onSave(content) }
    catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <span className="close" onClick={onClose}>×</span>
        <h3>{title}{stem ? <span className="mono faint" style={{ fontWeight: 400 }}> · {stem}</span> : null}</h3>
        {note && <div className="faint" style={{ fontSize: 12, marginBottom: 10 }}>{note}</div>}
        {content == null && !err ? <div className="loading">loading spec…</div> : (
          <>
            <textarea className="code" value={content || ''} onChange={(e) => setContent(e.target.value)} />
            <div className="action-row" style={{ marginTop: 10 }}>
              <button className="btn primary sm" onClick={save} disabled={busy || content == null}>
                {busy ? 'saving…' : saveLabel}
              </button>
              {err && <span className="act-error">{err}</span>}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'

// Read-only viewer for a queue YAML. `load` is an async fn returning
// { stem, yaml, snapshot? }. When `snapshot === false` the bytes are the live
// learning/queues file rather than the immutable copy taken at launch, so we
// warn that they may differ from what actually ran.
export default function SpecModal({ title, load, onClose }) {
  const [spec, setSpec] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    load().then((d) => alive && setSpec(d)).catch((e) => alive && setErr(e.message))
    return () => { alive = false }
  }, [load])

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <span className="close" onClick={onClose}>×</span>
        <h3>{title}{spec?.stem ? <span className="mono faint" style={{ fontWeight: 400 }}> · {spec.stem}</span> : null}</h3>
        {err && <div className="error">error: {err}</div>}
        {!err && !spec && <div className="loading">loading spec…</div>}
        {spec && (
          <>
            {spec.snapshot === false && (
              <div className="spec-warn">
                ⚠ No snapshot for this run — showing the current{' '}
                <span className="mono">learning/queues/{spec.stem}.yaml</span>, which may have
                been edited since this experiment ran.
              </div>
            )}
            {spec.snapshot === true && (
              <div className="spec-note">
                Snapshot taken at launch — the exact spec this experiment executed.
              </div>
            )}
            <pre className="spec-yaml">{spec.yaml}</pre>
          </>
        )}
      </div>
    </div>
  )
}

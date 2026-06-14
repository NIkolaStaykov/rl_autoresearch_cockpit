export function StatusPill({ status }) {
  const label = status === 'empty' ? 'no runs' : status
  return (
    <span className={`pill ${status}`}>
      <span className="led" />
      {label}
    </span>
  )
}

export function Loading({ what = 'data' }) {
  return <div className="loading">loading {what}…</div>
}

export function ErrorBox({ error }) {
  return <div className="error">error: {String(error.message || error)}</div>
}

export function navigate(hash) {
  window.location.hash = hash
}

// Thin fetch layer over the cockpit backend.

async function get(path) {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${path}`)
  return r.json()
}

async function send(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body == null ? undefined : JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `${r.status} ${r.statusText}`)
  return data
}

export const api = {
  health: () => get('/api/health'),
  queues: () => get('/api/queues'),
  queue: (id, withMetrics = true) =>
    get(`/api/queues/${encodeURIComponent(id)}?with_metrics=${withMetrics}`),
  run: (exp) => get(`/api/runs/${encodeURIComponent(exp)}`),

  // settings (success metric)
  getSettings: () => get('/api/settings'),
  putSettings: (patch) => send('PUT', '/api/settings', patch),

  // control
  specs: () => get('/api/queue_specs'),
  controlStatus: () => get('/api/control/status'),
  launch: (queue, startFrom) => send('POST', '/api/control/launch', { queue, start_from: startFrom }),
  resume: (id, n, steps) => send('POST', '/api/control/resume', { n, steps, source_dir: id }),
  stop: (container) => send('POST', '/api/control/stop', { container }),
  putConclusion: (id, text) => send('PUT', `/api/queues/${encodeURIComponent(id)}/conclusion`, { text }),
  planNext: (id) => send('POST', `/api/queues/${encodeURIComponent(id)}/plan-next`),
  saveQueue: (filename, content, overwrite = false) =>
    send('POST', '/api/queue_specs/save', { filename, content, overwrite }),
}

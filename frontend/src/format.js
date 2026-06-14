// Small formatting helpers shared across views.

export function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  if (typeof v !== 'number') return String(v)
  return v.toFixed(digits)
}

export function fmtPct(v, digits = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

// Percentage with precision that scales to the magnitude, so small held-success
// fractions (e.g. 0.0006 -> "0.06%") don't collapse to "0%".
export function fmtRatePct(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const p = v * 100
  if (p === 0) return '0%'
  const digits = p < 1 ? 2 : p < 10 ? 1 : 0
  return `${p.toFixed(digits)}%`
}

// Format a value by its declared kind ('pct' -> percentage, else number).
export function fmtByKind(v, kind) {
  return kind === 'pct' ? fmtRatePct(v) : fmtNum(v)
}

export function fmtDuration(s) {
  if (!s && s !== 0) return '—'
  s = Math.round(s)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h) return `${h}h ${m}m`
  if (m) return `${m}m ${sec}s`
  return `${sec}s`
}

export function fmtEta(s) {
  if (!s && s !== 0) return null
  return `~${fmtDuration(s)} left`
}

export function fmtAgo(iso) {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  const diff = (Date.now() - then) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function fmtSteps(v) {
  if (!v && v !== 0) return '—'
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `${(v / 1e6).toFixed(0)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`
  return String(v)
}

// Short, meaningful label for a dotted sweep-param key. The bare leaf is often
// ambiguous (`obs_noise.scales.joint_pos` -> "joint_pos" loses that it's a NOISE
// level), so we keep the nearest meaningful ancestor as a qualifier.
const _QUAL = { obs_noise: 'noise', bias_scales: 'bias', reward_config: 'reward' }
const _GENERIC = new Set(['scales', 'values', 'config'])

export function axisLabel(key) {
  const parts = String(key).split('.')
  const leaf = parts[parts.length - 1]
  let qual = null
  for (let i = parts.length - 2; i >= 0; i--) {
    if (!_GENERIC.has(parts[i])) { qual = parts[i]; break }
  }
  return qual && _QUAL[qual] ? `${leaf} ${_QUAL[qual]}` : leaf
}

// Status -> color token (matches CSS custom props).
export const STATUS_COLOR = {
  running: 'var(--run)',
  done: 'var(--ok)',
  failed: 'var(--fail)',
  pending: 'var(--idle)',
  empty: 'var(--idle)',
}

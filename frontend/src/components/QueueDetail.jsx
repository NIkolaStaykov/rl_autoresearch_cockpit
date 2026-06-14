import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { fmtNum, fmtByKind, fmtDuration, fmtSteps, axisLabel } from '../format'
import { StatusPill, Loading, ErrorBox, navigate } from './Common'
import Verdict from './Verdict'
import { QueueActions } from './Control'
import { useView } from '../view'

function DivBadge({ div }) {
  if (!div || div.flag === 'ok') return <span className="faint mono">—</span>
  const title = (div.reasons || []).join('; ')
  return (
    <span className={`divg ${div.flag}`} title={title}>
      <span className="d-led" />
      {div.flag}
    </span>
  )
}

function Hypothesis({ hyp, doc, stem }) {
  return (
    <div style={{ display: 'grid', gap: 12, marginBottom: 8 }}>
      {!hyp && (
        <div className="panel" style={{ color: 'var(--txt-faint)', fontSize: 12 }}>
          No structured <span className="mono">hypothesis:</span> block — add one to{' '}
          <span className="mono">learning/queues/{stem}.yaml</span> (axis / group / metric /
          expect) to get an automatic verdict and an expected-vs-actual chart.
        </div>
      )}
      {hyp && (
        <div className="panel">
          <div className="section-title" style={{ margin: '0 0 10px' }}>hypothesis</div>
          <div className="hyp-grid">
            {hyp.axis && (<><span className="k">axis</span><span>{hyp.axis}</span></>)}
            {hyp.group && (<><span className="k">group</span><span>{hyp.group}</span></>)}
            {hyp.metric && (<><span className="k">metric</span><span>{hyp.metric}</span></>)}
            {hyp.expect && Object.entries(hyp.expect).map(([k, v]) => (
              <Fragment key={k}><span className="k">expect · {k}</span><span>{String(v)}</span></Fragment>
            ))}
          </div>
        </div>
      )}
      {doc && <div className="panel doc">{doc}</div>}
    </div>
  )
}

function RewardCell({ value, max }) {
  if (value === null || value === undefined) return <span className="faint mono">—</span>
  const w = max > 0 ? Math.max(2, (100 * value) / max) : 2
  return (
    <div className="bar-cell">
      <div className="bar" style={{ width: `${w}px` }} />
      <span className="val">{fmtNum(value)}</span>
    </div>
  )
}

// Sort ordering for non-numeric columns. Lower rank sorts first when ascending.
const STATUS_RANK = { running: 0, done: 1, failed: 2, pending: 3 }
const DIV_RANK = { ok: 0, warn: 1, diverged: 2 }
// Columns where a first click should sort high-to-low (you usually want the best first).
const DESC_FIRST = new Set(['reward', 'success', 'health', 'steps', 'wall'])

// nulls/undefined always sort last (both directions); ties break by run idx for stability.
function sortRuns(runs, get, dir) {
  const mult = dir === 'asc' ? 1 : -1
  return [...runs].sort((ra, rb) => {
    const a = get(ra), b = get(rb)
    const an = a === null || a === undefined
    const bn = b === null || b === undefined
    if (an && bn) return ra.idx - rb.idx
    if (an) return 1
    if (bn) return -1
    let c
    if (typeof a === 'number' && typeof b === 'number') c = a - b
    else c = String(a).localeCompare(String(b), undefined, { numeric: true })
    return c !== 0 ? c * mult : ra.idx - rb.idx
  })
}

function SortTh({ id, sort, onSort, children, ...rest }) {
  const active = sort.key === id
  return (
    <th {...rest} className={`sortable${active ? ' sorted' : ''}`} onClick={() => onSort(id)}>
      {children}
      <span className="sort-ind">{active ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</span>
    </th>
  )
}

function Matrix({ d, flavor }) {
  const axes = useMemo(() => d.axes || [], [d.axes])
  const sm = d.success_metric || { label: 'success', kind: 'pct' }
  const rewardOf = (r) => r.reward?.[flavor]
  const successOf = (r) => r.success?.[flavor]
  const maxReward = Math.max(0, ...d.runs.map((r) => rewardOf(r) || 0))

  const [sort, setSort] = useState({ key: 'idx', dir: 'asc' })
  const onSort = useCallback((key) => {
    setSort((s) => s.key === key
      ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: DESC_FIRST.has(key) ? 'desc' : 'asc' })
  }, [])

  // Accessor per sortable column; rebuilt when axes/flavor change.
  const accessors = useMemo(() => {
    const m = {
      idx: (r) => r.idx,
      status: (r) => STATUS_RANK[r.status] ?? 9,
      suffix: (r) => r.suffix,
      reward: (r) => r.reward?.[flavor],
      success: (r) => r.success?.[flavor],
      health: (r) => DIV_RANK[r.divergence?.flag] ?? null,
      steps: (r) => r.final_step,
      wall: (r) => r.duration_s,
    }
    for (const a of axes) m[`p:${a}`] = (r) => r.params?.[a]
    return m
  }, [axes, flavor])

  const rows = useMemo(
    () => sortRuns(d.runs, accessors[sort.key] || accessors.idx, sort.dir),
    [d.runs, accessors, sort],
  )

  return (
    <div className="matrix-wrap">
      <table className="matrix">
        <thead>
          <tr>
            <SortTh id="idx" sort={sort} onSort={onSort}>#</SortTh>
            <SortTh id="status" sort={sort} onSort={onSort}>status</SortTh>
            {axes.map((a) => (
              <SortTh key={a} id={`p:${a}`} sort={sort} onSort={onSort}>{axisLabel(a)}</SortTh>
            ))}
            {axes.length === 0 && <SortTh id="suffix" sort={sort} onSort={onSort}>suffix</SortTh>}
            <SortTh id="reward" sort={sort} onSort={onSort}>reward<span className="th-flavor"> {flavor}</span></SortTh>
            <SortTh id="success" sort={sort} onSort={onSort} title={`success metric: ${sm.id || sm.label} (${flavor})`}>{sm.label}<span className="th-flavor"> {flavor}</span></SortTh>
            <SortTh id="health" sort={sort} onSort={onSort}>health</SortTh>
            <SortTh id="steps" sort={sort} onSort={onSort}>steps</SortTh>
            <SortTh id="wall" sort={sort} onSort={onSort}>wall</SortTh>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.idx}
              className="run-row"
              onClick={() => r.exp_name && navigate(`#/r/${encodeURIComponent(r.exp_name)}`)}
            >
              <td className="idx">{r.idx}</td>
              <td><StatusPill status={r.status} /></td>
              {axes.map((a) => (
                <td key={a} className="cell-param">{String(r.params?.[a] ?? '—')}</td>
              ))}
              {axes.length === 0 && <td className="cell-param">{r.suffix}</td>}
              <td>
                {r.status === 'running' && rewardOf(r) == null
                  ? <span className="mono" style={{ color: 'var(--run)' }}>training…</span>
                  : <RewardCell value={rewardOf(r)} max={maxReward} />}
              </td>
              <td className="num">{fmtByKind(successOf(r), sm.kind)}</td>
              <td><DivBadge div={r.divergence} /></td>
              <td className="num faint">
                {r.status === 'running' && r.progress != null ? (
                  <span title={`${fmtSteps(r.final_step)} steps`}>
                    <span className="miniprog"><span className="fill" style={{ width: `${r.progress * 100}%` }} /></span>
                    {' '}{Math.round(r.progress * 100)}%
                  </span>
                ) : fmtSteps(r.final_step)}
              </td>
              <td className="num faint">{fmtDuration(r.duration_s)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function QueueDetail({ id }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState(null)
  const { flavor, nonce } = useView()

  const reload = useCallback(
    () => api.queue(id).then(setD).catch(setError),
    [id, nonce],
  )
  useEffect(() => {
    setD(null); setError(null)
    reload()
    const t = setInterval(reload, 8000)
    return () => clearInterval(t)
  }, [reload])

  if (error) return <ErrorBox error={error} />
  if (!d) return <Loading what="queue" />

  return (
    <div>
      <div className="qhead">
        <div style={{ flex: 1 }}>
          <h2>{d.stem}</h2>
          <div className="qmeta">
            {d.id.slice(d.stem.length + 1)} · {d.completed}/{d.total} runs
            {d.axes.length > 0 && <> · axes: {d.axes.map(axisLabel).join(' × ')}</>}
          </div>
        </div>
        <StatusPill status={d.running ? 'running' : 'done'} />
      </div>

      <div style={{ marginTop: 18 }}>
        {d.verdict && <Verdict verdict={d.verdict} />}
        <Hypothesis hyp={d.hypothesis} doc={d.doc} stem={d.stem} />
      </div>

      <div className="section-title">runs</div>
      <Matrix d={d} flavor={flavor} />

      <QueueActions queue={d} onChanged={reload} />
    </div>
  )
}

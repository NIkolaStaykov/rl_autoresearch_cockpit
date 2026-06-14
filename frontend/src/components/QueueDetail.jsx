import { Fragment, useCallback, useEffect, useState } from 'react'
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

function Matrix({ d, flavor }) {
  const axes = d.axes || []
  const sm = d.success_metric || { label: 'success', kind: 'pct' }
  const rewardOf = (r) => r.reward?.[flavor]
  const successOf = (r) => r.success?.[flavor]
  const maxReward = Math.max(0, ...d.runs.map((r) => rewardOf(r) || 0))
  return (
    <div className="matrix-wrap">
      <table className="matrix">
        <thead>
          <tr>
            <th>#</th>
            <th>status</th>
            {axes.map((a) => <th key={a}>{axisLabel(a)}</th>)}
            {axes.length === 0 && <th>suffix</th>}
            <th>reward<span className="th-flavor"> {flavor}</span></th>
            <th title={`success metric: ${sm.id || sm.label} (${flavor})`}>{sm.label}<span className="th-flavor"> {flavor}</span></th>
            <th>health</th>
            <th>steps</th>
            <th>wall</th>
          </tr>
        </thead>
        <tbody>
          {d.runs.map((r) => (
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

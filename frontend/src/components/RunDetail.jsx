import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { api } from '../api'
import { fmtNum, fmtByKind, fmtSteps } from '../format'
import { Loading, ErrorBox } from './Common'
import { useView } from '../view'

function Kpi({ label, value, tone }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone || ''}`}>{value}</div>
    </div>
  )
}

function Curve({ curve }) {
  if (!curve || curve.length === 0) return <div className="empty-state">no eval curve yet</div>
  const data = curve.map(([step, reward]) => ({ step, reward }))
  return (
    <div className="panel" style={{ height: 300, padding: '18px 10px 8px 0' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 18, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="#20252e" vertical={false} />
          <XAxis dataKey="step" tickFormatter={fmtSteps} stroke="#5f6b7a"
                 tick={{ fontSize: 11, fontFamily: 'monospace' }} />
          <YAxis stroke="#5f6b7a" tick={{ fontSize: 11, fontFamily: 'monospace' }} width={44} />
          <Tooltip
            contentStyle={{ background: '#12151a', border: '1px solid #313846', borderRadius: 6, fontFamily: 'monospace', fontSize: 12 }}
            labelFormatter={(s) => `step ${fmtSteps(s)}`}
            formatter={(v) => [fmtNum(v), 'reward']}
          />
          <Line type="monotone" dataKey="reward" stroke="#4ade80" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function Breakdown({ summary }) {
  const entries = Object.entries(summary || {})
    .filter(([k]) => k.startsWith('eval/episode_reward/'))
    .map(([k, v]) => [k.replace('eval/episode_reward/', ''), v])
    .filter(([, v]) => typeof v === 'number')
  if (entries.length === 0) return null
  const mag = Math.max(...entries.map(([, v]) => Math.abs(v)), 1e-6)
  return (
    <div className="breakdown">
      {entries.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([name, v]) => {
        const w = (50 * Math.abs(v)) / mag
        return (
          <div className="row" key={name}>
            <span className="name">{name}</span>
            <div className="track">
              <div className="axis" />
              <div className={`fill ${v >= 0 ? 'pos' : 'neg'}`} style={{ width: `${w}%` }} />
            </div>
            <span style={{ textAlign: 'right', color: v >= 0 ? 'var(--ok)' : 'var(--fail)' }}>
              {fmtNum(v)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function RunDetail({ exp }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState(null)
  const { flavor, settings } = useView()

  useEffect(() => {
    let alive = true
    setD(null); setError(null)
    let timer = null
    const load = () =>
      api.run(exp).then((x) => {
        if (!alive) return
        setD(x)
        // keep polling while the run is still training
        if (x && !x.completed && !x.error && !timer) timer = setInterval(load, 5000)
      }).catch((e) => alive && setError(e))
    load()
    return () => { alive = false; if (timer) clearInterval(timer) }
  }, [exp])

  if (error) return <ErrorBox error={error} />
  if (!d) return <Loading what="run" />
  if (d.error) return <div className="error">{d.error}</div>

  const s = d.summary || {}
  const kl = s['training/kl_mean']
  const vloss = s['training/v_loss']
  const div = d.divergence
  const ind = d.indicators || {}
  const reward = ind.reward?.[flavor]
  const succId = settings?.success_metric || 'success_per_step'
  const succ = ind.success_metrics?.[succId]
  return (
    <div>
      <div className="qhead">
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 18, wordBreak: 'break-all' }}>{d.name}</h2>
          <div className="qmeta">
            {d.env_name} · {d.n_evals} evals · {fmtSteps(d.final_step)} steps
            {d.completed ? ' · completed' : ' · in progress (live)'}
          </div>
        </div>
      </div>

      {div && div.flag !== 'ok' && (
        <div className={`banner ${div.flag}`}>
          <span>{div.flag === 'diverged' ? '⚠ diverged' : '△ warning'}</span>
          <span className="faint">{(div.reasons || []).join(' · ')}</span>
        </div>
      )}

      <div className="kpis">
        <Kpi label={`reward · ${flavor}`} value={fmtNum(reward)} tone="good" />
        <Kpi label={`${succ?.label || 'success'} · ${flavor}`} value={succ ? fmtByKind(succ[flavor], succ.kind) : '—'} />
        <Kpi label="train kl" value={fmtNum(kl, 3)} tone={kl > 0.1 ? 'warn' : ''} />
        <Kpi label="ep kl" value={fmtNum(s['episode/kl_mean'], 3)} />
        <Kpi label="v_loss" value={fmtNum(vloss, 2)} />
        <Kpi label="mean std" value={fmtNum(s['training/policy_dist_mean_std'], 3)} />
      </div>

      <div className="section-title">reward curve</div>
      <Curve curve={d.curve} />

      <div className="section-title">reward breakdown (final eval)</div>
      <Breakdown summary={s} />
    </div>
  )
}

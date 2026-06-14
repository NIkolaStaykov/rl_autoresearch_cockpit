import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { axisLabel } from '../format'

const PALETTE = ['#5eb1ff', '#4ade80', '#fbbf24', '#f87171', '#c084fc', '#34d399']

const ARROW = { increasing: '↑ increasing', decreasing: '↓ decreasing', flat: '→ flat', insufficient: '· too few points' }

function mergeSeries(series) {
  // Build one row per axis value, a column per group.
  const xs = new Set()
  series.forEach((s) => s.points.forEach((p) => xs.add(p.x)))
  const sorted = [...xs].sort((a, b) => a - b)
  return sorted.map((x) => {
    const row = { x }
    series.forEach((s) => {
      const pt = s.points.find((p) => p.x === x)
      if (pt && pt.y != null) row[String(s.group)] = pt.y
    })
    return row
  })
}

export default function Verdict({ verdict, metric }) {
  if (!verdict) return null
  const { overall, series } = verdict
  const data = mergeSeries(series)
  const hasData = data.length > 0

  return (
    <div className="panel" style={{ marginBottom: 12 }}>
      <div className="verdict-head">
        <span className="section-title" style={{ margin: 0 }}>hypothesis verdict</span>
        <span className={`verdict-badge ${overall}`}>{overall}</span>
        <span className="faint mono" style={{ fontSize: 11 }}>
          {verdict.metric} vs {axisLabel(verdict.axis)}
        </span>
      </div>

      <div className="verdict-series">
        {series.map((s) => (
          <div className="vrow" key={String(s.group)}>
            <span className="vgroup">{String(s.group)}</span>
            <span className="vtrend">
              expect {s.expected || '—'} · saw {ARROW[s.observed] || s.observed}
            </span>
            <span className={`vmark ${s.verdict || 'insufficient'}`}>
              {s.verdict === 'holds' ? '✓ holds'
                : s.verdict === 'contradicted' ? '✗ contradicted'
                : s.verdict === 'partial' ? '~ partial'
                : '— n/a'}
            </span>
          </div>
        ))}
      </div>

      {hasData && (
        <div className="vchart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 12, right: 20, bottom: 6, left: 0 }}>
              <CartesianGrid stroke="#20252e" vertical={false} />
              <XAxis dataKey="x" stroke="#5f6b7a" tick={{ fontSize: 11, fontFamily: 'monospace' }}
                     type="number" domain={['auto', 'auto']} />
              <YAxis stroke="#5f6b7a" tick={{ fontSize: 11, fontFamily: 'monospace' }} width={44} />
              <Tooltip
                contentStyle={{ background: '#12151a', border: '1px solid #313846', borderRadius: 6, fontFamily: 'monospace', fontSize: 12 }}
                labelFormatter={(x) => `${axisLabel(verdict.axis)} = ${x}`}
              />
              <Legend wrapperStyle={{ fontFamily: 'monospace', fontSize: 11 }} />
              {series.map((s, i) => (
                <Line key={String(s.group)} type="monotone" dataKey={String(s.group)}
                      stroke={PALETTE[i % PALETTE.length]} strokeWidth={2}
                      connectNulls dot={{ r: 3 }} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useData, fmtB, fmtPct } from '../useData.js'

const WINDOWS = { 21: '~1 MO', 63: '~3 MO', 126: '~6 MO' }
const ERAS = ['all', '2010-2013', '2014-2017', '2018-2021', '2022-now']

function Tiles({ agg }) {
  const sides = [['buy', 'LONG'], ['fade', 'FADE']]
  return (
    <div className="tiles">
      {sides.map(([side, label]) => {
        const a = agg?.[side]
        if (!a || !a.n) {
          return (
            <div className="tile" key={side}>
              <div className="label">{label} SIGNALS</div>
              <div className="value mut">n=0</div>
            </div>
          )
        }
        const color = side === 'buy' ? 'var(--green)' : 'var(--red)'
        return (
          <Fragmented key={side}>
            <div className="tile">
              <div className="label">{label} · HIT RATE</div>
              <div className="value" style={{ color }}>{Math.round(a.hit_rate * 100)}%</div>
              <div className="sub">n={a.n} signals</div>
            </div>
            <div className="tile">
              <div className="label">{label} · MEAN EXCESS vs SPY</div>
              {/* for fades, negative excess is the win */}
              <div className="value" style={{ color: (side === 'buy') === (a.mean_excess >= 0) ? 'var(--green)' : 'var(--red)' }}>
                {fmtPct(a.mean_excess)}
              </div>
              <div className="sub">
                95% CI [{fmtPct(a.ci95?.[0] ?? 0)}, {fmtPct(a.ci95?.[1] ?? 0)}]
                {a.ci_includes_zero && <span style={{ color: 'var(--amber)' }}> — includes zero</span>}
              </div>
            </div>
          </Fragmented>
        )
      })}
    </div>
  )
}
const Fragmented = ({ children }) => <>{children}</>

function SigTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tooltip">
      <b>{d.id}</b> · {d.fired.toUpperCase()} · z {d.z >= 0 ? '+' : ''}{d.z}<br />
      knowledge {d.knowledge_date} · {fmtPct(d.excess)} excess<br />
      <span className="mut">{d.in_sample ? 'in-sample' : 'holdout'} · click for detail</span>
    </div>
  )
}

function SignalCard({ sig, window }) {
  if (!sig) return (
    <p className="mut" style={{ marginTop: 12 }}>
      Click any signal in the scatter to see what buying (or fading) it would have done.
    </p>
  )
  const o = sig.outcome ?? {}
  return (
    <div className="sigcard">
      <h2>
        <Link className={`tick ${sig.fired === 'fade' ? 'fade' : ''}`} to={`/company/${sig.id}`}>{sig.id}</Link>
        {' '}— {sig.fired.toUpperCase()} fired on quarter ending {sig.quarter_end}
      </h2>
      <dl>
        <dt>obligations that quarter</dt><dd>{fmtB(sig.obligations)} (baseline {fmtB(sig.trailing_mean)})</dd>
        <dt>z-score</dt><dd>{sig.z >= 0 ? '+' : ''}{sig.z}σ</dd>
        <dt>knowledge date</dt><dd>{sig.knowledge_date} <span className="mut">(quarter end + 135d reporting lag)</span></dd>
        <dt>entry</dt><dd>{sig.entry_date} @ {sig.entry_price?.toFixed(2)}</dd>
        {Object.entries(WINDOWS).map(([w, label]) => {
          const r = o[w]
          return (
            <Fragmented key={w}>
              <dt>{label} outcome</dt>
              <dd>
                {r ? (
                  <>
                    stock {fmtPct(r.ret)} · SPY {fmtPct(r.bench)} ·{' '}
                    <b style={{ color: r.excess >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtPct(r.excess)} excess</b>
                  </>
                ) : <span className="mut">insufficient future data</span>}
              </dd>
            </Fragmented>
          )
        })}
        <dt>sample</dt><dd>{sig.in_sample ? 'in-sample (thresholds tuned here)' : 'holdout (out-of-sample)'}</dd>
      </dl>
    </div>
  )
}

function PortfolioPanel() {
  const p = useData('portfolio')
  if (!p || p.__error) return null
  const s = p.stats
  const tiles = [
    ['STRATEGY', s.strategy, 'var(--green)'],
    ['SPY', s.spy, 'var(--ink-2)'],
    ['SECTOR BASKET', s.sector, 'var(--cyan)'],
  ]
  return (
    <div className="panel">
      <h2><span className="accent">§</span> AS A PORTFOLIO — equal-weight active signals, monthly rebalance, ~6-mo holds, 10bps costs</h2>
      <div className="tiles">
        {tiles.map(([label, st, color]) => (
          <div className="tile" key={label}>
            <div className="label">{label}</div>
            <div className="value" style={{ color }}>{fmtPct(st.ann_return)}/yr</div>
            <div className="sub">sharpe {st.sharpe} · max DD {fmtPct(st.max_drawdown, 0)}</div>
          </div>
        ))}
        <div className="tile">
          <div className="label">EXPOSURE</div>
          <div className="value">{p.avg_positions}</div>
          <div className="sub">avg positions · {p.months_invested}/{p.months} months invested</div>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={p.series} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" />
          <XAxis dataKey="month" stroke="var(--hairline)" minTickGap={40} />
          <YAxis scale="log" domain={['auto', 'auto']} stroke="var(--hairline)"
                 tickFormatter={(v) => `${v.toFixed(0)}x`} />
          <Tooltip content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null
            const d = payload[0].payload
            return (
              <div className="chart-tooltip">
                <b>{label}</b> · {d.n} positions<br />
                strategy {d.eq.toFixed(2)}x · SPY {d.eq_spy.toFixed(2)}x · sector {d.eq_sector.toFixed(2)}x
              </div>
            )
          }} />
          {/* validated dark-surface series colors; legend + direct labels carry identity */}
          <Line dataKey="eq" name="strategy" stroke="var(--chart-green)" dot={false} strokeWidth={2} />
          <Line dataKey="eq_spy" name="SPY" stroke="var(--ink-3)" dot={false} strokeWidth={2} />
          <Line dataKey="eq_sector" name="sector basket" stroke="var(--chart-cyan)" dot={false} strokeWidth={2} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
        </LineChart>
      </ResponsiveContainer>
      <p className="mut" style={{ fontSize: 11 }}>{p.note} Log scale.</p>
    </div>
  )
}

export default function Backtest() {
  const backtest = useData('backtest')
  const [win, setWin] = useState('126')
  const [sample, setSample] = useState('all')
  const [era, setEra] = useState('all')
  const [selected, setSelected] = useState(null)

  const rows = useMemo(() => {
    if (!backtest || backtest.__error) return []
    return backtest.tickers
      .filter((r) => r.outcome?.[win]?.excess != null)
      .filter((r) => sample === 'all' || (sample === 'in_sample') === r.in_sample)
      .filter((r) => era === 'all' || r.era === era)
      .map((r) => ({ ...r, ts: Date.parse(r.knowledge_date), excess: r.outcome[win].excess }))
  }, [backtest, win, sample, era])

  if (!backtest) return <div className="loading">LOADING BACKTEST…</div>
  if (backtest.__error) return <div className="loading">NO DATA ({backtest.__error})</div>

  const aggKey = sample === 'all' ? 'all' : sample === 'in_sample' ? 'in_sample' : 'holdout'
  const agg = era === 'all'
    ? backtest.aggregates[win][aggKey]
    : backtest.aggregates[win].eras[era]
  const trainEndTs = Date.parse(backtest.train_end)
  const buys = rows.filter((r) => r.fired === 'buy')
  const fades = rows.filter((r) => r.fired === 'fade')

  return (
    <div style={{ marginTop: 16 }}>
    <PortfolioPanel />
    <div className="panel">
      <h2><span className="accent">◈</span> BACKTEST — every historical signal and what happened next</h2>
      <div className="toggles">
        {Object.entries(WINDOWS).map(([w, label]) => (
          <button key={w} className={win === w ? 'on' : ''} onClick={() => setWin(w)}>{label}</button>
        ))}
        <span style={{ width: 12 }} />
        {['all', 'in_sample', 'holdout'].map((s) => (
          <button key={s} className={sample === s ? 'on' : ''} onClick={() => setSample(s)}>
            {s.replace('_', '-').toUpperCase()}
          </button>
        ))}
        <span style={{ width: 12 }} />
        {ERAS.map((e) => (
          <button key={e} className={era === e ? 'on' : ''} onClick={() => setEra(e)}>{e.toUpperCase()}</button>
        ))}
      </div>

      <Tiles agg={agg} />

      <div style={{ margin: '4px 0 14px' }}>
        <div className="mut" style={{ fontSize: 10, letterSpacing: 1, marginBottom: 4 }}>
          WHY THE MATERIALITY GATE — {WINDOWS[win].toLowerCase()} excess of ungated LONG signals,
          by surge size as a share of annual revenue:
        </div>
        <table className="board" style={{ maxWidth: 640 }}>
          <thead>
            <tr><th>SURGE / REVENUE</th><th className="num">N</th><th className="num">HIT</th><th className="num">MEAN EXCESS</th><th className="num">95% CI</th></tr>
          </thead>
          <tbody>
            {Object.entries(backtest.aggregates[win].materiality ?? {}).map(([b, agg2]) => {
              const a = agg2?.buy
              if (!a?.n) return <tr key={b}><td>{b}</td><td className="num mut" colSpan={4}>n=0</td></tr>
              return (
                <tr key={b}>
                  <td>{b}{b === '<0.5%' && <span className="mut"> (gated out)</span>}</td>
                  <td className="num">{a.n}</td>
                  <td className="num">{Math.round(a.hit_rate * 100)}%</td>
                  <td className="num" style={{ color: a.mean_excess >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {fmtPct(a.mean_excess)}
                  </td>
                  <td className="num mut">
                    {a.ci95 ? `[${fmtPct(a.ci95[0])}, ${fmtPct(a.ci95[1])}]` : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <ResponsiveContainer width="100%" height={380}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" />
          <XAxis
            dataKey="ts" type="number" domain={['dataMin', 'dataMax']}
            tickFormatter={(ts) => new Date(ts).getFullYear()}
            stroke="var(--hairline)"
          />
          <YAxis
            dataKey="excess" type="number"
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
            stroke="var(--hairline)"
          />
          {rows.length > 0 && sample === 'all' && era === 'all' && (
            <ReferenceArea
              x1={trainEndTs} x2={Math.max(...rows.map((r) => r.ts))}
              fill="var(--panel-2)" fillOpacity={0.5}
              label={{ value: 'HOLDOUT →', position: 'insideTopLeft', fill: 'var(--ink-3)', fontSize: 10 }}
            />
          )}
          <ReferenceLine y={0} stroke="var(--ink-3)" strokeDasharray="4 4" />
          <Tooltip content={<SigTooltip />} cursor={{ stroke: 'var(--hairline)' }} />
          {/* buy = validated chart green, fade = validated chart red; the legend
              below plus tooltip labels carry identity beyond color */}
          <Scatter name="LONG signals" data={buys} fill="var(--chart-green)"
                   onClick={(d) => setSelected(d)} shape="circle" />
          <Scatter name="FADE signals" data={fades} fill="var(--chart-red)"
                   onClick={(d) => setSelected(d)} shape="diamond" />
        </ScatterChart>
      </ResponsiveContainer>
      <div className="mut" style={{ fontSize: 11 }}>
        <span style={{ color: 'var(--chart-green)' }}>●</span> long signal ·{' '}
        <span style={{ color: 'var(--chart-red)' }}>◆</span> fade signal · y = {WINDOWS[win].toLowerCase()} return
        minus SPY, measured from the knowledge date · shaded region = out-of-sample holdout
      </div>

      <SignalCard sig={selected} window={win} />
    </div>
    </div>
  )
}

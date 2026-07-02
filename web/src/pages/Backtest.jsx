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
        {p.factors && (
          <div className="tile">
            <div className="label" title={p.factors.note}>FAMA-FRENCH ALPHA</div>
            <div className="value" style={{ color: p.factors.alpha_t >= 2 ? 'var(--green)' : 'var(--amber)' }}>
              {fmtPct(p.factors.alpha_annual)}/yr
            </div>
            <div className="sub">
              t={p.factors.alpha_t}{p.factors.alpha_t >= 2 ? ' (significant)' : ' (weak)'} ·
              β mkt {p.factors.beta_mkt} · R² {p.factors.r2}
            </div>
          </div>
        )}
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
      {p.sweep?.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary className="mut" style={{ cursor: 'pointer', fontSize: 11 }}>
            PARAMETER SWEEP — hold period × weighting, chosen on the train era only (baseline highlighted; the pre-registered config stays the headline)
          </summary>
          <table className="board" style={{ maxWidth: 720, marginTop: 8 }}>
            <thead>
              <tr>
                <th>HOLD</th><th>WEIGHTING</th>
                <th className="num">TRAIN RET/YR</th><th className="num">TRAIN SHARPE</th>
                <th className="num">HOLDOUT RET/YR</th><th className="num">HOLDOUT SHARPE</th>
              </tr>
            </thead>
            <tbody>
              {p.sweep.map((r, i) => (
                <tr key={i} style={r.baseline ? { background: 'rgba(51,255,153,0.05)' } : undefined}>
                  <td>{r.hold_days}d{r.baseline ? ' ◀ baseline' : ''}</td>
                  <td>{r.weighting}</td>
                  <td className="num">{r.train ? fmtPct(r.train.ann_return) : '—'}</td>
                  <td className="num">{r.train ? r.train.sharpe : '—'}</td>
                  <td className="num">{r.holdout ? fmtPct(r.holdout.ann_return) : '—'}</td>
                  <td className="num">{r.holdout ? r.holdout.sharpe : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  )
}

// Rule variants that were evaluated and (honestly) NOT adopted, plus the
// pre-entry run-up buckets. Everything here is disclosure, not the signal.
function VariantsTable({ aggs, winLabel }) {
  const cell = (a, side = 'buy') => {
    const v = a?.[side]
    if (!v?.n) return <td className="num mut" colSpan={3}>n=0</td>
    const win = (side === 'buy') === (v.mean_excess >= 0)
    return (
      <>
        <td className="num">{v.n}</td>
        <td className="num">{Math.round(v.hit_rate * 100)}%</td>
        <td className="num" style={{ color: win ? 'var(--green)' : 'var(--red)' }}>{fmtPct(v.mean_excess)}</td>
      </>
    )
  }
  return (
    <div style={{ margin: '4px 0 14px' }}>
      <div className="mut" style={{ fontSize: 10, letterSpacing: 1, marginBottom: 4 }}>
        RULE VARIANTS EVALUATED ({winLabel} excess) — the pre-registered rule stays primary; variants shown so the comparison is on the record:
      </div>
      <table className="board" style={{ maxWidth: 760 }}>
        <thead>
          <tr>
            <th>VARIANT</th><th>SIDE</th>
            <th className="num">N</th><th className="num">HIT</th><th className="num">MEAN EXCESS</th>
            <th>VERDICT</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>baseline z</td><td>LONG</td>{cell(aggs.all)}
            <td className="mut">the signal</td>
          </tr>
          <tr>
            <td title="z computed on a causally deseasonalized series (federal Q4 always spikes)">seasonally-adjusted z</td>
            <td>LONG</td>{cell(aggs.seasonal)}
            <td className="mut">better in-sample ({aggs.seasonal_in_sample?.buy?.n ? `${Math.round(aggs.seasonal_in_sample.buy.hit_rate * 100)}% hit` : '—'}), worse holdout — not adopted</td>
          </tr>
          <tr>
            <td>baseline z</td><td>FADE</td>{cell(aggs.all, 'fade')}
            <td className="mut">never worked in-sample — retired from ranking</td>
          </tr>
          <tr>
            <td title="fade only when the prior quarter was also below trend">persistent-decline fade</td>
            <td>FADE</td>{cell(aggs.fade2, 'fade')}
            <td className="mut">holdout-only pattern (in-sample {aggs.fade2_in_sample?.fade?.n ? `${Math.round(aggs.fade2_in_sample.fade.hit_rate * 100)}% hit` : '—'}) — adopting it would be holdout-tuning</td>
          </tr>
          <tr>
            <td title="grants + direct payments + other assistance, same z rule">assistance stream</td>
            <td>LONG</td>{cell(aggs.assistance)}
            <td className="mut">fires ~never under the same gates — context only</td>
          </tr>
        </tbody>
      </table>
      <div className="mut" style={{ fontSize: 10, letterSpacing: 1, margin: '10px 0 4px' }}>
        PRE-ENTRY RUN-UP — stock's move vs SPY between quarter end and entry (has the market already priced it?):
      </div>
      <table className="board" style={{ maxWidth: 640 }}>
        <thead>
          <tr><th>RUN-UP</th><th className="num">N</th><th className="num">HIT</th><th className="num">MEAN EXCESS</th></tr>
        </thead>
        <tbody>
          {/* explicit order + ligature-safe labels (mono font turns "<-" into an arrow) */}
          {[['<-10%', 'below −10%'], ['-10-0%', '−10% to 0'], ['0-10%', '0 to +10%'], ['>10%', 'above +10%']].map(([b, label]) => (
            <tr key={b}>
              <td>{label}</td>{cell(aggs.runup?.[b])}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mut" style={{ fontSize: 10, marginTop: 4 }}>
        No monotone decay across buckets — signals stayed profitable even after a &gt;10% chase,
        so run-up is shown on picks as context, not used as a gate.
      </p>
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

      {backtest.placebo && (
        <div style={{ margin: '4px 0 14px' }}>
          <div className="mut" style={{ fontSize: 10, letterSpacing: 1, marginBottom: 4 }}>
            TIMING PLACEBO — same tickers, same signal count, random entry dates ({backtest.placebo.n_perm} permutations):
          </div>
          <div className="tiles">
            <div className="tile">
              <div className="label">REAL TIMING</div>
              <div className="value" style={{ color: 'var(--green)' }}>{fmtPct(backtest.placebo.real_mean_excess)}</div>
              <div className="sub">mean 6-mo excess, n={backtest.placebo.n_signals}</div>
            </div>
            <div className="tile">
              <div className="label">RANDOM TIMING</div>
              <div className="value mut">{fmtPct(backtest.placebo.perm_mean_excess)}</div>
              <div className="sub">permutation mean · 95th pctile {fmtPct(backtest.placebo.perm_p95)}</div>
            </div>
            <div className="tile">
              <div className="label">P-VALUE</div>
              <div className="value" style={{ color: backtest.placebo.p_value <= 0.05 ? 'var(--green)' : 'var(--amber)' }}>
                {backtest.placebo.p_value.toFixed(3)}
              </div>
              <div className="sub">share of random timings ≥ real{backtest.placebo.p_value > 0.05 ? ' — suggestive, not conclusive' : ''}</div>
            </div>
          </div>
        </div>
      )}

      <VariantsTable aggs={backtest.aggregates[win]} winLabel={WINDOWS[win].toLowerCase()} />

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

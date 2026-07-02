import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData, fmtPct } from '../useData.js'

const HORIZONS = [
  ['6m', '6 MONTHS'], ['1y', '1 YEAR'], ['5y', '5 YEARS'], ['20y', '20 YEARS'],
]

function Row({ r, i, rank1total, parent, open, onToggle }) {
  const pos = r.total >= 0
  const width = rank1total > 0 ? Math.max(2, (Math.abs(r.total) / rank1total) * 160) : 2
  const c = r.components
  return (
    <Fragment>
      <tr className="rowbtn" onClick={onToggle}>
        <td className="mut">{String(i + 1).padStart(2, '0')}</td>
        <td>
          <Link className={`tick ${pos ? '' : 'fade'}`} to={`/company/${r.ticker}`}
                onClick={(e) => e.stopPropagation()}>{r.ticker}</Link>
        </td>
        <td className="mut">{parent ?? ''}</td>
        <td style={{ width: 170 }}>
          <span className={`zbar ${pos ? '' : 'neg'}`} style={{ width }} />
        </td>
        <td className="num" style={{ color: pos ? 'var(--green)' : 'var(--red)', fontWeight: 700 }}>
          {fmtPct(r.total)}
        </td>
        <td className="num mut" title={r.band?.pooled
          ? 'P10–P90 of historical outcomes over this horizon (universe pool — this ticker is too young)'
          : "P10–P90 of this ticker's own historical rolling-window outcomes, centered on the projection"}>
          {r.band
            ? <><span style={{ color: 'var(--red)' }}>{fmtPct(r.band.p10, 0)}</span>
                {' … '}
                <span style={{ color: 'var(--green)' }}>{fmtPct(r.band.p90, 0)}</span>
                {r.band.pooled && '*'}</>
            : '—'}
        </td>
        <td className="num">{fmtPct(r.annualized)}/yr</td>
        <td>
          {r.capped && <span className="tag warn" title="hit the model's per-horizon ceiling">CAP</span>}
          {' '}
          {r.short_history && (
            <span className="mut" title={`only ${c.hist_years}y of trading history for this lookback`}>
              {c.hist_years}y hist
            </span>
          )}
          {' '}
          {c.signal_bump > 0 && (
            <span style={{ color: 'var(--green)' }} title="a LONG spending signal fired this quarter — the backtested mean excess is added">
              ⚡SIG
            </span>
          )}
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={8}>
            <div className="expand">
              <b>How this number is built</b> — annualized {fmtPct(r.annualized)} =
              {' '}{Math.round(c.w_hist * 100)}% × own trailing return ({fmtPct(c.hist_cagr)}/yr
              over {c.hist_years}y{c.hist_cagr > 0.6 || c.hist_cagr < -0.5 ? ', clamped' : ''})
              {' '}+ {Math.round((1 - c.w_hist) * 100)}% × SPY baseline ({fmtPct(c.spy_cagr)}/yr)
              {c.spend_tilt !== 0 && (
                <> + {fmtPct(c.spend_tilt)} government-spending tailwind
                  (3y obligations CAGR {c.spend_cagr_3y != null ? fmtPct(c.spend_cagr_3y) : '—'}, damped)</>
              )}
              {c.signal_bump > 0 && <> + {fmtPct(c.signal_bump)} backtested signal bump</>}
              {r.capped && <> — then capped at the horizon ceiling</>}.
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  )
}

export default function Leaderboard() {
  const growth = useData('growth')
  const universe = useData('universe')
  const [hz, setHz] = useState('6m')
  const [open, setOpen] = useState(null)

  if (!growth) return <div className="loading">LOADING PROJECTIONS…</div>
  if (growth.__error) return <div className="loading">NO DATA ({growth.__error})</div>

  const rows = growth.horizons[hz] ?? []
  const rank1total = rows.length ? Math.abs(rows[0].total) : 0

  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <h2><span className="accent">Σ</span> GROWTH LEADERBOARD — projected total return by horizon</h2>
      <div className="toggles">
        {HORIZONS.map(([k, label]) => (
          <button key={k} className={hz === k ? 'on' : ''}
                  onClick={() => { setHz(k); setOpen(null) }}>{label}</button>
        ))}
      </div>
      <table className="board">
        <thead>
          <tr>
            <th>#</th><th>TICKER</th><th>COMPANY</th><th></th>
            <th className="num">PROJ. {hz.toUpperCase()} GROWTH</th>
            <th className="num">P10 … P90</th>
            <th className="num">ANNUALIZED</th><th>FLAGS</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <Row key={r.ticker} r={r} i={i} rank1total={rank1total}
                 parent={universe && !universe.__error ? universe[r.ticker]?.parent : null}
                 open={open === r.ticker}
                 onToggle={() => setOpen(open === r.ticker ? null : r.ticker)} />
          ))}
        </tbody>
      </table>
      <p className="mut" style={{ fontSize: 11, marginTop: 10 }}>
        {growth.caveat} P10…P90 = the historical spread of {hz} outcomes centered on the
        projection (* = universe pool, ticker too young). Click a row to see how its
        number is built.
      </p>
    </div>
  )
}

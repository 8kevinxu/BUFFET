import { Link } from 'react-router-dom'
import { useData, fmtPct } from '../useData.js'

// The forward test that can't be backtest-gamed: cohorts are frozen with real
// entry prices at refresh time and only ever re-marked to market.
export default function Ledger() {
  const ledger = useData('ledger')
  if (!ledger) return <div className="loading">LOADING LEDGER…</div>
  if (ledger.__error) return <div className="loading">NO LEDGER ({ledger.__error})</div>

  const cohorts = [...(ledger.cohorts ?? [])].reverse()
  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <h2><span className="accent">✎</span> PAPER LEDGER — picks frozen at refresh time, marked to market since</h2>
      <p className="mut" style={{ fontSize: 11 }}>
        The only test that can't be curve-fit: each cohort's entry prices were locked on the
        day the signal was published, before the outcome was knowable. This page accumulates
        the strategy's live out-of-sample record.
      </p>
      {cohorts.length === 0 && <p className="mut">No cohorts frozen yet.</p>}
      {cohorts.map((c) => (
        <div key={c.quarter_end} style={{ marginBottom: 18 }}>
          <h2 style={{ marginTop: 14 }}>
            COHORT {c.quarter_end} <span className="mut">frozen {c.frozen_on}</span>
            {c.provisional_at_freeze && <span className="tag warn" style={{ marginLeft: 8 }}>FROZEN ON PROVISIONAL DATA</span>}
            {c.mean_excess != null && (
              <span style={{ marginLeft: 12, color: c.mean_excess >= 0 ? 'var(--green)' : 'var(--red)' }}>
                {fmtPct(c.mean_excess)} vs SPY
              </span>
            )}
          </h2>
          <table className="board">
            <thead>
              <tr>
                <th>TICKER</th><th className="num">Z</th><th className="num">MATERIALITY</th>
                <th className="num">ENTRY</th><th className="num">LAST</th>
                <th className="num">RETURN</th><th className="num">VS SPY</th>
              </tr>
            </thead>
            <tbody>
              {c.picks.map((p) => (
                <tr key={p.ticker}>
                  <td><Link className="tick" to={`/company/${p.ticker}`}>{p.ticker}</Link></td>
                  <td className="num">{p.z >= 0 ? '+' : ''}{p.z}</td>
                  <td className="num">{p.materiality != null ? `${(p.materiality * 100).toFixed(1)}%` : '—'}</td>
                  <td className="num mut">{p.entry_price?.toFixed(2)} <span style={{ fontSize: 10 }}>{p.entry_date}</span></td>
                  <td className="num mut">{p.last_price?.toFixed(2)}</td>
                  <td className="num" style={{ color: p.ret >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtPct(p.ret)}</td>
                  <td className="num" style={{ color: p.excess >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 700 }}>{fmtPct(p.excess)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

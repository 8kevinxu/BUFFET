import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import { fmtB } from '../useData.js'

// Shared board for buys and fades. z-bar width is clamped so one outlier
// doesn't flatten the rest.
export default function PicksBoard({ rows, side, thesis, news }) {
  const [open, setOpen] = useState(null)
  if (!rows?.length) return <p className="mut">No {side} signals this quarter.</p>
  const fade = side === 'fade'
  return (
    <table className="board">
      <thead>
        <tr>
          <th>#</th><th>TICKER</th><th>COMPANY</th>
          <th className="num">Z-SCORE</th><th></th>
          <th className="num" title="surge as a share of the company's latest annual revenue (SEC EDGAR)">MATERIALITY</th>
          <th className="num" title="stock's move vs SPY from quarter end to today — how much of the surge the market has already priced. Backtest: buys stayed profitable across all run-up buckets.">RUN-UP</th>
          <th className="num">QTR OBLIG.</th><th className="num">Δ VS BASE</th>
          <th className="num">HIST. HIT</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const t = thesis?.entries?.[r.ticker]
          const width = Math.min(Math.abs(r.z), 4) * 16
          const isOpen = open === r.ticker
          return (
            <Fragment key={r.ticker}>
              <tr className="rowbtn" onClick={() => setOpen(isOpen ? null : r.ticker)}>
                <td className="mut">{String(i + 1).padStart(2, '0')}</td>
                <td>
                  <Link className={`tick ${fade ? 'fade' : ''}`} to={`/company/${r.ticker}`}
                        onClick={(e) => e.stopPropagation()}>
                    {r.ticker}
                  </Link>
                  {!r.fired && <span className="mut" title="below the ±1.5σ firing threshold"> ·watch</span>}
                </td>
                <td className="mut">{r.parent}</td>
                <td className="num" style={{ color: fade ? 'var(--red)' : 'var(--green)' }}>
                  {r.z >= 0 ? '+' : ''}{r.z.toFixed(2)}σ
                </td>
                <td style={{ width: 70 }}>
                  <span className={`zbar ${fade ? 'neg' : ''}`} style={{ width }} />
                </td>
                <td className="num" style={{ fontWeight: 700 }}>
                  {r.materiality != null
                    ? `${(r.materiality * 100).toFixed(1)}% of rev`
                    : <span className="mut">no rev data</span>}
                </td>
                <td className="num" style={{ color: (r.runup ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {r.runup != null ? `${r.runup >= 0 ? '+' : ''}${(r.runup * 100).toFixed(0)}%` : <span className="mut">—</span>}
                </td>
                <td className="num">{fmtB(r.obligations)}</td>
                <td className="num" style={{ color: r.delta >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {r.delta >= 0 ? '+' : '−'}{fmtB(Math.abs(r.delta)).slice(1)}
                </td>
                <td className="num">
                  {r.track ? `${Math.round(r.track.hit_rate * 100)}% (n=${r.track.n})` : <span className="mut">—</span>}
                </td>
              </tr>
              {isOpen && (
                <tr>
                  <td colSpan={10}>
                    <div className={`expand ${fade ? 'fade' : ''}`}>
                      {t ? (
                        <>
                          <div>{t.thesis}</div>
                          <ul className="risks">
                            {t.risks.map((risk, j) => <li key={j}>{risk}</li>)}
                          </ul>
                          <div className="model">thesis: {t.model} · quarter {t.quarter_end}</div>
                        </>
                      ) : (
                        <div className="mut">No AI thesis generated (run the pipeline with ANTHROPIC_API_KEY set).</div>
                      )}
                      {news?.[r.ticker]?.length > 0 && (
                        <div style={{ marginTop: 8 }}>
                          {news[r.ticker].slice(0, 4).map((n, j) => (
                            <div key={j} className="news-item">
                              <a href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
                              <div className="src">{n.source} {n.date && `· ${n.date}`}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}

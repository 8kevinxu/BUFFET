import { useData, fmtB } from '../useData.js'
import PicksBoard from '../components/PicksBoard.jsx'

function SectorPulse({ sectors }) {
  if (!sectors?.length) return null
  return (
    <div className="panel">
      <h2><span className="accent">▚</span> SECTOR PULSE — agency-level obligations, same quarter</h2>
      <table className="board">
        <thead>
          <tr><th>SECTOR</th><th className="num">Z</th><th className="num">QTR OBLIG.</th><th>PROXY ETF</th></tr>
        </thead>
        <tbody>
          {sectors.map((s) => (
            <tr key={s.id}>
              <td className="mut">{s.label}</td>
              <td className="num" style={{ color: s.z >= 0 ? 'var(--green)' : 'var(--red)' }}>
                {s.z == null ? '—' : `${s.z >= 0 ? '+' : ''}${s.z.toFixed(2)}σ`}
              </td>
              <td className="num">{fmtB(s.obligations)}</td>
              <td>{s.etf}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function NewsRail({ news, picks }) {
  const order = [...(picks?.picks ?? []), ...(picks?.fades ?? [])].map((r) => r.ticker)
  const items = order.flatMap((t) =>
    (news?.[t] ?? []).slice(0, 3).map((n) => ({ ...n, ticker: t })))
  return (
    <div className="panel">
      <h2><span className="accent">▞</span> WIRE</h2>
      {items.length === 0 && <p className="mut">No headlines fetched.</p>}
      {items.slice(0, 24).map((n, i) => (
        <div key={i} className="news-item">
          <span className="for">{n.ticker}</span>
          <a href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
          <div className="src">{n.source} {n.date && `· ${n.date}`}</div>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const picks = useData('picks')
  const thesis = useData('thesis')
  const news = useData('news')

  if (!picks) return <div className="loading">LOADING FEED…</div>
  if (picks.__error) {
    return <div className="loading">NO DATA — run <code>make refresh</code> first ({picks.__error})</div>
  }

  return (
    <div className="cols">
      <div>
        <div className="panel">
          <h2>
            <span className="accent">▲</span> LONG SIGNALS — spending surge, quarter ending {picks.quarter_end}
            {picks.provisional && <span className="tag warn" style={{ marginLeft: 8 }}>PROVISIONAL DATA</span>}
          </h2>
          <PicksBoard rows={picks.picks} side="buy" thesis={thesis} news={news} />
        </div>
        <div className="panel">
          <h2><span className="accent" style={{ color: 'var(--red)' }}>▼</span> FADE SIGNALS — spending collapse</h2>
          <PicksBoard rows={picks.fades} side="fade" thesis={thesis} news={news} />
        </div>
        <SectorPulse sectors={picks.sectors} />
      </div>
      <NewsRail news={news} picks={picks} />
    </div>
  )
}

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

function EarlySignals({ announce }) {
  if (!announce || announce.__error || !announce.awards?.length) return null
  const alerts = announce.awards.filter((a) => a.alert)
  const rest = announce.awards.filter((a) => !a.alert).slice(0, 8 - Math.min(alerts.length, 8))
  const rows = [...alerts.slice(0, 10), ...rest]
  return (
    <div className="panel">
      <h2>
        <span className="accent" style={{ color: 'var(--amber)' }}>⚡</span> EARLY SIGNALS — announced same-day, months before the obligations data
        <span className="mut" style={{ fontWeight: 400, letterSpacing: 0 }}>
          {' '}(DoD daily contract announcements, $7.5M+; announced value ≈ full ceiling. Context, not a backtested signal.)
        </span>
      </h2>
      <table className="board">
        <thead><tr><th>DATE</th><th>TICKER</th><th className="num">ANNOUNCED</th><th className="num" title="announced value as a share of latest annual revenue">% OF REV</th><th>WHAT</th></tr></thead>
        <tbody>
          {rows.map((a, i) => (
            <tr key={i} style={a.alert ? { background: 'rgba(255,176,32,0.06)' } : undefined}>
              <td className="mut">{a.date}</td>
              <td>
                <span className="tick">{a.ticker}</span>
                {a.alert && <span className="tag warn" style={{ marginLeft: 6 }} title="announced value ≥ 0.5% of annual revenue — the materiality bar the backtested signal uses">MATERIAL</span>}
              </td>
              <td className="num">{fmtB(a.amount)}</td>
              <td className="num" style={{ fontWeight: a.alert ? 700 : 400 }}>
                {a.pct_revenue != null ? `${(a.pct_revenue * 100).toFixed(1)}%` : '—'}
              </td>
              <td className="mut" style={{ maxWidth: 420, fontSize: 11 }}>
                {a.modification && <span className="mut">[mod] </span>}
                {a.text.replace(/^[^,]+,\s*/, '').slice(0, 170).toLowerCase()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mut" style={{ fontSize: 10, marginTop: 6 }}>
        {announce.n_alerts} material announcements in the last {announce.days_covered} announcement days · source: {announce.source}
      </p>
    </div>
  )
}

function LiveAwards({ awards }) {
  if (!awards || awards.__error) return null
  const rows = Object.entries(awards.recent ?? {})
    .flatMap(([t, list]) => list.map((a) => ({ ...a, ticker: t })))
    .sort((a, b) => (b.date ?? '').localeCompare(a.date ?? '') || (b.amount ?? 0) - (a.amount ?? 0))
    .slice(0, 12)
  if (!rows.length) return null
  return (
    <div className="panel">
      <h2><span className="accent">◉</span> LIVE AWARDS — largest transactions of the last 60 days, picked tickers
        <span className="mut" style={{ fontWeight: 400, letterSpacing: 0 }}>
          {' '}(civilian awards post in weeks; DoD after its 90-day embargo)
        </span>
      </h2>
      <table className="board">
        <thead><tr><th>DATE</th><th>TICKER</th><th className="num">AMOUNT</th><th>AGENCY</th><th>WHAT</th></tr></thead>
        <tbody>
          {rows.map((a, i) => (
            <tr key={i}>
              <td className="mut">{a.date}</td>
              <td><span className="tick">{a.ticker}</span></td>
              <td className="num">{fmtB(a.amount ?? 0)}</td>
              <td className="mut">{a.agency}</td>
              <td className="mut" style={{ maxWidth: 380, fontSize: 11 }}>
                {(a.desc || a.award_id || '').toLowerCase()}
              </td>
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
  const awards = useData('awards')
  const announce = useData('announce')

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
        <EarlySignals announce={announce} />
        <div className="panel">
          <h2>
            <span className="accent" style={{ color: 'var(--red)' }}>▼</span> SPENDING COLLAPSES — informational only
            <span className="tag warn" style={{ marginLeft: 8 }}>FADES RETIRED</span>
          </h2>
          {picks.fades_retired && (
            <p className="mut" style={{ fontSize: 11, marginBottom: 8 }}>{picks.fades_retired}</p>
          )}
          <PicksBoard rows={picks.fades} side="fade" thesis={thesis} news={news} />
        </div>
        <LiveAwards awards={awards} />
        <SectorPulse sectors={picks.sectors} />
      </div>
      <NewsRail news={news} picks={picks} />
    </div>
  )
}

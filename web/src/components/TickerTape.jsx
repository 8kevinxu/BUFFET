import { Link } from 'react-router-dom'
import { useData, fmtPct } from '../useData.js'

export default function TickerTape() {
  const quotes = useData('quotes')
  const meta = useData('meta')
  if (!quotes || quotes.__error || !meta || meta.__error) return null
  const syms = meta.universe.filter((s) => quotes[s])
  const items = syms.map((s) => {
    const q = quotes[s]
    const cls = q.chg > 0.0005 ? 'up' : q.chg < -0.0005 ? 'down' : 'flat'
    return (
      <Link key={s} to={`/company/${s}`}>
        <span className="sym">{s}</span>{' '}
        <span className={cls}>{q.price.toFixed(2)} {fmtPct(q.chg)}</span>
      </Link>
    )
  })
  return (
    <div className="tape">
      {/* content duplicated so the -50% translate loops seamlessly */}
      <div className="tape-inner">{items}{items.map((el, i) => (
        <span key={`dup${i}`}>{el}</span>
      ))}</div>
    </div>
  )
}

import { useEffect, useMemo, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { createChart } from 'lightweight-charts'
import { useData, fmtB, fmtPct } from '../useData.js'

const CHART_OPTS = {
  layout: {
    background: { color: 'transparent' },
    textColor: '#5c6f7f',
    fontFamily: '"JetBrains Mono", monospace',
    fontSize: 10,
  },
  grid: {
    vertLines: { color: '#17222c' },
    horzLines: { color: '#17222c' },
  },
  rightPriceScale: { borderColor: '#1e2a36' },
  // minBarSpacing must shrink or ~19y of daily bars can't fit the viewport
  timeScale: { borderColor: '#1e2a36', minBarSpacing: 0.05 },
  crosshair: { mode: 0 },
}

function PriceChart({ ticker, prices, spendSeries, rows }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!ref.current || !prices?.length) return
    const chart = createChart(ref.current, { ...CHART_OPTS, height: 420 })

    // top pane: adjusted close
    const price = chart.addAreaSeries({
      lineColor: '#1489a8',
      topColor: 'rgba(20, 137, 168, 0.25)',
      bottomColor: 'rgba(20, 137, 168, 0.02)',
      lineWidth: 2,
      priceScaleId: 'right',
      title: `${ticker} adj close`,
    })
    price.setData(prices.map(([d, v]) => ({ time: d, value: v })))
    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.05, bottom: 0.35 } })

    // bottom panel: quarterly obligations histogram — its own scale stacked
    // below the price pane, sharing only the time axis + crosshair (not a
    // dual-axis chart)
    const oblig = chart.addHistogramSeries({
      color: '#0fab68',
      priceScaleId: 'oblig',
      priceFormat: { type: 'volume' },
      title: 'quarterly obligations',
    })
    const firstPrice = prices[0][0]
    const lastPrice = prices[prices.length - 1][0]
    const spendRows = Object.entries(spendSeries ?? {})
      .filter(([d]) => d >= firstPrice)
      .sort(([a], [b]) => (a < b ? -1 : 1))
    oblig.setData(spendRows.map(([d, v]) => ({ time: d, value: v })))
    chart.priceScale('oblig').applyOptions({ scaleMargins: { top: 0.72, bottom: 0 } })

    // signal-fire markers at knowledge dates
    const markers = (rows ?? [])
      .filter((r) => r.fired && r.knowledge_date >= firstPrice && r.knowledge_date <= lastPrice)
      .map((r) => ({
        time: r.knowledge_date,
        position: r.fired === 'buy' ? 'belowBar' : 'aboveBar',
        color: r.fired === 'buy' ? '#0fab68' : '#ef4257',
        shape: r.fired === 'buy' ? 'arrowUp' : 'arrowDown',
        text: `${r.fired === 'buy' ? 'LONG' : 'FADE'} ${r.z >= 0 ? '+' : ''}${r.z}σ`,
      }))
    price.setMarkers(markers)

    const onResize = () => chart.applyOptions({ width: ref.current?.clientWidth ?? 600 })
    onResize()
    chart.timeScale().fitContent()
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [ticker, prices, spendSeries, rows])
  return <div ref={ref} />
}

export default function Company() {
  const { ticker } = useParams()
  const prices = useData(`prices/${ticker}`)
  const spending = useData('spending')
  const signals = useData('signals')
  const backtest = useData('backtest')
  const thesis = useData('thesis')
  const news = useData('news')
  const universe = useData('universe')
  const awards = useData('awards')
  const audit = useData('audit')

  const rows = useMemo(
    () => (signals?.tickers ?? []).filter((r) => r.id === ticker),
    [signals, ticker],
  )

  if (!prices || !spending || !signals) return <div className="loading">LOADING {ticker}…</div>
  if (prices.__error) return <div className="loading">NO PRICE DATA FOR {ticker}</div>

  const uni = universe && !universe.__error ? universe[ticker] : null
  const track = backtest?.track?.[ticker]
  const t = thesis?.entries?.[ticker]
  const fired = rows.filter((r) => r.fired)
  const drove = awards && !awards.__error ? awards.drivers?.[ticker] : null
  const aud = audit && !audit.__error ? audit[ticker] : null

  return (
    <div style={{ marginTop: 16 }}>
      <div className="panel">
        <h2>
          <span className="accent">◍</span> {ticker}
          {uni && <span className="mut"> — {uni.parent} · {uni.sector}</span>}
        </h2>
        <PriceChart ticker={ticker} prices={prices}
                    spendSeries={spending.tickers?.[ticker]} rows={rows} />
        <div className="mut" style={{ fontSize: 11, marginTop: 4 }}>
          <span style={{ color: '#1489a8' }}>—</span> adjusted close ·{' '}
          <span style={{ color: '#0fab68' }}>▮</span> quarterly federal contract obligations ·
          arrows mark signal knowledge dates (quarter end + 135 days)
        </div>
      </div>

      <div className="cols">
        <div>
        {drove?.rows?.length > 0 && (
          <div className="panel">
            <h2>WHAT DROVE IT — top awards in the {drove.fired === 'buy' ? 'surge' : 'collapse'} quarter ending {drove.quarter_end}</h2>
            <table className="board">
              <thead><tr><th>DATE</th><th className="num">AMOUNT</th><th>AGENCY</th><th>WHAT</th></tr></thead>
              <tbody>
                {drove.rows.map((a, i) => (
                  <tr key={i}>
                    <td className="mut">{a.date}</td>
                    <td className="num">{fmtB(a.amount ?? 0)}</td>
                    <td className="mut">{a.agency}</td>
                    <td className="mut" style={{ fontSize: 11 }}>{(a.desc || a.award_id || '').toLowerCase()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="panel">
          <h2>SIGNAL HISTORY</h2>
          {fired.length === 0 && <p className="mut">This ticker has never fired a signal.</p>}
          {fired.length > 0 && (
            <table className="board">
              <thead>
                <tr><th>QUARTER</th><th className="num">Z</th><th>TYPE</th><th className="num">OBLIG.</th><th>KNOWLEDGE</th></tr>
              </thead>
              <tbody>
                {fired.slice().reverse().map((r) => (
                  <tr key={r.quarter_end}>
                    <td>
                      {r.quarter_end}
                      {r.provisional && <span className="tag warn" style={{ marginLeft: 6 }}>PROV</span>}
                    </td>
                    <td className="num" style={{ color: r.fired === 'buy' ? 'var(--green)' : 'var(--red)' }}>
                      {r.z >= 0 ? '+' : ''}{r.z}
                    </td>
                    <td>{r.fired === 'buy' ? 'LONG' : 'FADE'}</td>
                    <td className="num">{fmtB(r.obligations)}</td>
                    <td className="mut">{r.knowledge_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {track && (
            <p className="mut" style={{ fontSize: 11 }}>
              Track record: {track.n} completed signals · {Math.round(track.hit_rate * 100)}% hit ·{' '}
              mean 6-mo excess {fmtPct(track.mean_excess)}
            </p>
          )}
        </div>
        </div>

        <div>
          {t && (
            <div className="panel">
              <h2>AI THESIS</h2>
              <p style={{ fontSize: 12 }}>{t.thesis}</p>
              <ul className="risks" style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                {t.risks.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
              <div className="model mut" style={{ fontSize: 10 }}>{t.model}</div>
            </div>
          )}
          {uni && (
            <div className="panel">
              <h2>RECIPIENT MAPPING</h2>
              <p className="mut" style={{ fontSize: 11 }}>
                Obligations are summed over USAspending recipient names matching:
              </p>
              <p style={{ fontSize: 12 }}>{uni.patterns.join(' · ')}</p>
              {uni.notes.length > 0 && (
                <p className="mut" style={{ fontSize: 11 }}>{uni.notes.join(' — ')}</p>
              )}
              {aud?.contamination && (
                <p style={{ fontSize: 11 }}
                   className={aud.contamination.leak_pct > 0.05 ? '' : 'mut'}>
                  {aud.contamination.leak_pct > 0.05
                    ? <span style={{ color: 'var(--amber)' }}>
                        ⚠ audit: ~{Math.round(aud.contamination.leak_pct * 100)}% of matched
                        dollars (last 2y) belong to other entities
                        {aud.contamination.top_leaks?.[0] && ` (largest: ${aud.contamination.top_leaks[0].name})`}
                      </span>
                    : <>audit: series ~{(100 - aud.contamination.leak_pct * 100).toFixed(0)}% clean over the last 2y</>}
                </p>
              )}
              {aud?.top?.length > 0 && (
                <p className="mut" style={{ fontSize: 11 }}>
                  largest matched entities: {aud.top.slice(0, 4).map((e) => e.name?.toLowerCase()).join(' · ')}
                </p>
              )}
            </div>
          )}
          {news?.[ticker]?.length > 0 && (
            <div className="panel">
              <h2>WIRE</h2>
              {news[ticker].map((n, i) => (
                <div key={i} className="news-item">
                  <a href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
                  <div className="src">{n.source} {n.date && `· ${n.date}`}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

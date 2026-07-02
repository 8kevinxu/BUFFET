import { useData, fmtB } from '../useData.js'

function SurvivorshipTable() {
  const s = useData('survivorship')
  if (!s || s.__error || !s.years?.length) return null
  return (
    <>
      <p style={{ marginTop: 6 }}>
        Instead of just disclosing it, we measure it: the share of each fiscal
        year's top-100 contract dollars that the universe's patterns actually
        match. The unmatched remainder is mostly states, universities, FFRDC
        operators (MITRE, national labs) and private firms (General Atomics,
        SpaceX, Sierra Nevada, Deloitte) — but any <i>decline</i> going back in
        time is the survivorship gap the backtest can't see.
      </p>
      <table className="board" style={{ maxWidth: 700 }}>
        <tbody>
          <tr>
            {s.years.map((y) => <td key={y.fy} className="num mut" style={{ fontSize: 10 }}>FY{String(y.fy).slice(2)}</td>)}
          </tr>
          <tr>
            {s.years.map((y) => (
              <td key={y.fy} className="num" style={{ color: y.coverage >= 0.7 ? 'var(--green)' : 'var(--amber)' }}>
                {y.coverage != null ? `${Math.round(y.coverage * 100)}%` : '—'}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <p className="mut" style={{ fontSize: 11 }}>
        Coverage is stable ({Math.round(Math.min(...s.years.slice(0, -1).map((y) => y.coverage ?? 1)) * 100)}–
        {Math.round(Math.max(...s.years.map((y) => y.coverage ?? 0)) * 100)}% every full year), so the
        universe isn't dramatically thinner in the early years — but individual
        delisted losers remain invisible. This audit also caught two real gaps
        (RTX's renamed parent entity, GD's NASSCO shipyard), since fixed.
      </p>
    </>
  )
}

export default function Theory() {
  const meta = useData('meta')
  const backtest = useData('backtest')
  const cfg = meta && !meta.__error ? meta.signal_config : null

  return (
    <div className="panel prose" style={{ marginTop: 16 }}>
      <h2><span className="accent">λ</span> THE THEORY</h2>
      <p>
        The US federal government publishes every contract it awards on
        USAspending.gov. When an agency suddenly obligates far more money to a
        company than usual, that company's future revenue just changed — but the
        market may be slow to notice, because the data is published with a lag
        and buried in millions of award rows. This tool tests whether that
        information edge exists and applies it to the newest data.
      </p>

      <h3>THE SIGNAL</h3>
      <ul>
        <li>
          For every (company, quarter): the z-score of that quarter's contract
          obligations against the trailing {cfg?.zscore_window ?? 8}-quarter
          mean and standard deviation.
        </li>
        <li>
          A <b style={{ color: 'var(--green)' }}>LONG</b> signal fires at
          z ≥ +{cfg?.z_buy ?? 1.5}; a <b style={{ color: 'var(--red)' }}>FADE</b> at
          z ≤ {cfg?.z_fade ?? -1.5} — both only when trailing-4-quarter
          obligations exceed {cfg ? fmtB(cfg.dollar_floor) : '$200M'}, so tiny
          denominators can't fire.
        </li>
        <li>
          A LONG must also be <b>material</b>: the surge must be ≥ 0.5% of the
          company's latest annual revenue knowable at the time (SEC EDGAR,
          matched by filing date). Sub-0.5% surges backtest at a coin flip.
        </li>
        <li>
          Company names are matched to tickers with a hand-curated mapping
          (Lockheed appears under multiple legal entities; "Electric Boat" is
          General Dynamics), summed per ticker.
        </li>
        <li>
          <b>Fades are retired.</b> Shorting spending collapses never beat
          chance in-sample — collapses are mostly known contract completions,
          already priced. Collapse rows are still shown, labeled informational.
        </li>
        <li>
          <b>The early tier.</b> DoD announces every contract over ~$7.5M the
          same day at war.gov — months before it reaches USAspending. The
          dashboard's EARLY SIGNALS feed matches announcements to the universe
          and flags material ones (≥0.5% of revenue). It's context, not a
          backtested signal: the reachable archive is only ~3 months deep.
        </li>
      </ul>

      <h3>THE LOOK-AHEAD DEFENSE</h3>
      <p>
        Spending data is not knowable when the quarter ends: DoD contract data
        is embargoed 90 days, and agencies file late. Every signal therefore
        gets a <code>knowledge date</code> = quarter end +{' '}
        {cfg?.knowledge_lag_days ?? 135} days, and backtest returns are only
        measured from the first trading day <i>after</i> it. Quarters whose
        knowledge date hasn't arrived are labeled PROVISIONAL: usable for the
        current ranking (clearly flagged) but never counted as history.
      </p>

      <h3>THE BACKTEST</h3>
      <ul>
        <li>
          Outcome = forward 21/63/126-trading-day total return (adjusted close)
          minus SPY over the same span.
        </li>
        <li>
          Thresholds were fixed using signals with knowledge dates up to{' '}
          {cfg?.train_end ?? '2017-12-31'} (in-sample); everything after is a
          holdout reported separately. We do not tune against the holdout.
        </li>
        <li>
          Aggregates show bootstrap 95% confidence intervals; when a CI includes
          zero, the UI says so instead of hiding it.
        </li>
        <li>
          Two independence checks live on the BACKTEST page: a{' '}
          <b>timing placebo</b> (random entry dates for the same tickers) and a{' '}
          <b>Fama-French regression</b> of the portfolio's monthly returns
          (is it alpha, or market/size/value beta?).
        </li>
      </ul>

      <h3>WHY YOU SHOULD STILL BE SKEPTICAL</h3>
      <ul>
        <li>
          <b>Survivorship bias.</b>{' '}
          {backtest?.caveats?.survivorship ??
            'The universe was curated in 2026 from companies that are still public — losers that delisted are invisible, which especially flatters the fade side.'}
          <SurvivorshipTable />
        </li>
        <li>
          <b>Revisions.</b>{' '}
          {backtest?.caveats?.revisions ??
            'Agencies revise past quarters; recent data is incomplete.'}
        </li>
        <li>
          <b>Small N.</b>{' '}
          {backtest?.caveats?.small_n ??
            'A few hundred signals over ~15 years — every statistic here is noisy.'}
        </li>
        <li>
          <b>Regime risk.</b> A pattern that held 2010–2025 can stop working the
          moment enough capital trades on it.
        </li>
        <li>
          <b>The narrative layer is presentation.</b> The AI-written theses and
          news never feed the score; the ranking is the raw quant signal.
        </li>
      </ul>

      <p className="mut">
        Data: USAspending.gov API (contract obligations, FY2008→present) ·
        stockanalysis.com / Yahoo Finance (adjusted daily closes) · Google News
        RSS + GDELT (headlines). Refreshed by <code>make refresh</code>.
        This is a research toy, not financial advice.
      </p>
    </div>
  )
}

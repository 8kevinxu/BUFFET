import { useData, fmtB } from '../useData.js'

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
          Company names are matched to tickers with a hand-curated mapping
          (Lockheed appears under multiple legal entities; "Electric Boat" is
          General Dynamics), summed per ticker.
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
      </ul>

      <h3>WHY YOU SHOULD STILL BE SKEPTICAL</h3>
      <ul>
        <li>
          <b>Survivorship bias.</b>{' '}
          {backtest?.caveats?.survivorship ??
            'The universe was curated in 2026 from companies that are still public — losers that delisted are invisible, which especially flatters the fade side.'}
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

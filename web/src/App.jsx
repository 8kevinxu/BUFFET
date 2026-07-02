import { NavLink, Route, Routes } from 'react-router-dom'
import { useData } from './useData.js'
import Dashboard from './pages/Dashboard.jsx'
import Backtest from './pages/Backtest.jsx'
import Leaderboard from './pages/Leaderboard.jsx'
import Ledger from './pages/Ledger.jsx'
import Company from './pages/Company.jsx'
import Theory from './pages/Theory.jsx'
import TickerTape from './components/TickerTape.jsx'

function StatusBar() {
  const meta = useData('meta')
  if (!meta || meta.__error) return <div className="statusbar">​</div>
  return (
    <div className="statusbar">
      <span>spending through <b>{meta.spending_through}</b></span>
      <span>prices <b>{meta.prices_through}</b></span>
      <span>
        ranking quarter <b>{meta.ranking_quarter}</b>{' '}
        {meta.ranking_provisional
          ? <span className="tag warn">PROVISIONAL</span>
          : <span className="tag ok">FINAL</span>}
      </span>
      <span>universe <b>{meta.universe_size}</b> tickers</span>
      {meta.thesis_stale && <span className="tag warn">THESIS STALE</span>}
      {meta.announce_alerts > 0 && (
        <span className="tag warn" title="material DoD contract announcements (≥0.5% of a ticker's annual revenue) — see EARLY SIGNALS on the terminal">
          ⚡ {meta.announce_alerts} EARLY ALERTS
        </span>
      )}
      <span className="mut">run {meta.generated}</span>
    </div>
  )
}

export default function App() {
  return (
    <div className="app">
      <header className="masthead">
        <span className="logo">BUFFET<span className="cursor" /></span>
        <span className="mut" style={{ fontSize: 11 }}>
          federal spending → stock signals
        </span>
        <nav className="nav">
          <NavLink to="/" end>TERMINAL</NavLink>
          <NavLink to="/growth">GROWTH</NavLink>
          <NavLink to="/backtest">BACKTEST</NavLink>
          <NavLink to="/ledger">LEDGER</NavLink>
          <NavLink to="/theory">THEORY</NavLink>
        </nav>
      </header>
      <StatusBar />
      <TickerTape />
      <div className="disclaimer">
        ⚠ RESEARCH / EDUCATION TOOL — NOT FINANCIAL ADVICE. Signals are noisy,
        the backtest has survivorship bias, and past excess returns do not
        predict future returns. See THEORY for the full caveats.
      </div>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/growth" element={<Leaderboard />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/ledger" element={<Ledger />} />
        <Route path="/company/:ticker" element={<Company />} />
        <Route path="/theory" element={<Theory />} />
      </Routes>
    </div>
  )
}

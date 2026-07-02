import { useEffect, useState } from 'react'

const cache = new Map()

// Fetch a /data/*.json artifact once per session; module-scope cached.
export function useData(name) {
  const [state, setState] = useState(() => cache.get(name) ?? null)
  useEffect(() => {
    if (cache.has(name)) { setState(cache.get(name)); return }
    let alive = true
    fetch(`${import.meta.env.BASE_URL}data/${name}.json`)
      .then((r) => { if (!r.ok) throw new Error(`${name}: ${r.status}`); return r.json() })
      .then((d) => { cache.set(name, d); if (alive) setState(d) })
      .catch((e) => { if (alive) setState({ __error: String(e) }) })
    return () => { alive = false }
  }, [name])
  return state
}

export const fmtB = (v) =>
  Math.abs(v) >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`

export const fmtPct = (v, dp = 1) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(dp)}%`

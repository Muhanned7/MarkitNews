'use client'

// RSK-007: "Limit capacity" chip — max shares tradable before a hard limit, and what binds.
import { useEffect, useState } from 'react'
import { riskHeaders } from './riskFetch'
import s from './HeadroomChip.module.css'

export default function HeadroomChip({ portfolioId, ticker, side = 'buy', onUseMax, refreshKey }) {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setData(null); setErr(null)
    const t = (ticker || '').trim().toUpperCase()
    if (!portfolioId || !t) return
    const ctrl = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/portfolios/${portfolioId}/headroom/${encodeURIComponent(t)}`, { headers: riskHeaders(), signal: ctrl.signal })
        const json = await res.json()
        if (!res.ok) throw new Error(json.detail || 'Headroom unavailable')
        setData(json)
      } catch (e) {
        if (e.name !== 'AbortError') setErr(e.message)
      }
    }, 300)
    return () => { clearTimeout(timer); ctrl.abort() }
  }, [portfolioId, ticker, refreshKey])

  if (err) return <div className={`${s.chip} ${s.zero}`} role="status">Limit capacity unavailable: {err}</div>
  if (!data) return null
  const h = side === 'sell' ? data.sell : data.buy
  const zero = h.shares <= 0
  const verb = side === 'sell' ? 'Max sell' : 'Max buy'

  return (
    <div className={s.wrap}>
      <div className={`${s.chip} ${zero ? s.zero : s.ok}`} role="status" aria-live="polite">
        <span className={s.label}>Limit capacity</span>
        <span className={s.value}>
          {verb} {h.shares.toLocaleString()} sh
          {!zero && <> (${h.dollars.toLocaleString(undefined, { maximumFractionDigits: 0 })} · {h.pct_nav}% NAV)</>}
        </span>
        <span className={s.bind}>{zero ? (h.reason || `blocked by ${h.binding_label}`) : `bounded by ${h.binding_label}`}</span>
        <button type="button" className={s.linkBtn} onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? 'Hide' : 'Details'}
        </button>
        {onUseMax && !zero && (
          <button type="button" className={s.linkBtn} onClick={() => onUseMax(h.shares)}>Use max</button>
        )}
      </div>
      {open && (
        <table className={s.caps}>
          <thead><tr><th>Constraint</th><th>Max shares</th><th>Note</th></tr></thead>
          <tbody>
            {h.caps.map((c) => (
              <tr key={c.key} className={(h.binding_keys || [h.binding]).includes(c.key) ? s.binding : ''}>
                <td>{c.label}{(h.binding_keys || [h.binding]).includes(c.key) ? ' · binding' : ''}</td>
                <td className={s.num}>{c.max_shares.toLocaleString()}</td>
                <td>{c.reason || (c.current_pct !== null && c.current_pct !== undefined ? `now ${c.current_pct}%` : '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

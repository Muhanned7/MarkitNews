'use client'

// RSK-003 pre-trade what-if: shows before/after for every limit the trade moves,
// and requires an override reason when a hard limit is newly breached or worsened.
import { useEffect, useState } from 'react'
import s from './limits.module.css'

function fmt(v, metric) {
  if (v === null || v === undefined) return '—'
  return metric === 'portfolio_beta' ? Number(v).toFixed(2) : `${Number(v).toFixed(2)}%`
}

const STATUS_SHORT = { hard_breach: 'hard', soft_breach: 'soft', ok: 'ok', na: 'n/a', inactive: 'off' }

export default function PreTradeCheck({ portfolioId, ticker, qty, price, overrideReason, setOverrideReason, onResult }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setData(null); setErr(null); onResult(null)
    const q = parseFloat(qty)
    const p = parseFloat(price)
    if (!portfolioId || !ticker || !q || !p) return
    const ctrl = new AbortController()
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await fetch(`/api/portfolios/${portfolioId}/what-if`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ticker, qty: q, price: p }),
          signal: ctrl.signal
        })
        const json = await res.json()
        if (!res.ok) throw new Error(json.detail || 'Pre-trade check failed')
        setData(json); onResult(json)
      } catch (e) {
        if (e.name !== 'AbortError') setErr(e.message)
      } finally {
        setLoading(false)
      }
    }, 400)
    return () => { clearTimeout(t); ctrl.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portfolioId, ticker, qty, price])

  if (!ticker || !qty || !price) return null
  if (loading && !data) return <div className={s.preTrade} aria-live="polite"><p className={s.hint}>Checking risk limits…</p></div>
  if (err) return <div className={`${s.preTrade} ${s.preTradeBlocked}`} role="alert"><p className={s.preTradeTitle}>{err}</p></div>
  if (!data) return null

  // rows (and entities) whose value or status moves
  const changed = []
  for (const l of data.limits) {
    if (l.entities && l.entities.length) {
      for (const e of l.entities) {
        if (e.before !== e.after || e.before_status !== e.after_status) {
          changed.push({ key: `${l.metric}-${e.scope}`, label: `${l.label} · ${e.scope}`, metric: l.metric, before: e.before, after: e.after, bs: e.before_status, as: e.after_status })
        }
      }
    } else if (l.before !== l.after || l.before_status !== l.after_status) {
      changed.push({ key: l.metric, label: l.label, metric: l.metric, before: l.before, after: l.after, bs: l.before_status, as: l.after_status })
    }
  }
  const blocked = data.requires_override

  return (
    <div className={`${s.preTrade} ${blocked ? s.preTradeBlocked : s.preTradeOk}`} aria-live="polite">
      <p className={s.preTradeTitle}>
        {blocked ? '✕ This trade would breach hard limits:' : '✓ Pre-trade check: no new or worsened hard breach'}
      </p>
      {blocked && (
        <ul className={s.blockList}>
          {data.blocking_breaches.map((b) => <li key={`${b.metric}-${b.scope}`}>{b.message}</li>)}
        </ul>
      )}
      {changed.length > 0 && (
        <table className={s.diffTable}>
          <thead><tr><th>Limit</th><th>Before</th><th>After</th><th>Status</th></tr></thead>
          <tbody>
            {changed.map((c) => (
              <tr key={c.key}>
                <td>{c.label}</td>
                <td className={s.diffNum}>{fmt(c.before, c.metric)}</td>
                <td className={s.diffNum}>{fmt(c.after, c.metric)}</td>
                <td>{STATUS_SHORT[c.bs] || c.bs} → <strong>{STATUS_SHORT[c.as] || c.as}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {blocked && (
        <div className={s.overrideBox}>
          <label htmlFor="override-reason">Override reason (required, min 10 characters, logged)</label>
          <textarea
            id="override-reason"
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            placeholder="Who approved this and why"
          />
          <span className={s.hint}>{overrideReason.trim().length}/10 characters</span>
        </div>
      )}
    </div>
  )
}

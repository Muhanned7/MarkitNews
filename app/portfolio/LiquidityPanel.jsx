'use client'

// RSK-010: days to liquidate, liquidity ladder, liquidity-adjusted VaR.
import { useEffect, useState } from 'react'
import base from './portfolio.module.css'
import s from './limits.module.css'

const usd = (v) => (v === null || v === undefined) ? '—' : `$${Math.round(v).toLocaleString()}`
const PARTS = [0.05, 0.10, 0.20, 0.30]

export default function LiquidityPanel({ portfolioId, refreshKey }) {
  const [part, setPart] = useState(0.20)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!portfolioId) return
    setErr(null)
    fetch(`/api/portfolios/${portfolioId}/liquidity-risk?participation=${part}`)
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || 'Failed'); setData(j) })
      .catch((e) => setErr(e.message))
  }, [portfolioId, part, refreshKey])

  if (err) return <div className={base.panel}><div className={s.section} role="alert">{err}</div></div>
  if (!data) return <div className={base.panel}><div className={s.section}>Loading liquidity…</div></div>

  const ladder = data.ladder.filter((l) => l.days !== 'all')
  const maxDtl = data.ladder.find((l) => l.days === 'all')?.max_days_to_liquidate
  const lv = data.lvar
  const LV_ROWS = [['historical_95', 'Historical 95%'], ['parametric_95', 'Parametric 95%'], ['historical_99', 'Historical 99%'], ['parametric_99', 'Parametric 99%']]

  return (
    <div className={base.panel}>
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>Liquidity risk</h2>
          <span className={s.sectionMeta} title={data._provenance.method}>{data._provenance.basis} · as of {data._provenance.as_of} ⓘ</span>
        </div>
        <div className={s.summaryRow} role="group" aria-label="ADV participation">
          <span className={s.statLabel} style={{ alignSelf: 'center' }}>Participation (% of ADV per day)</span>
          {PARTS.map((p) => (
            <button key={p} className={s.smallBtn} aria-pressed={part === p} onClick={() => setPart(p)}
              style={part === p ? { background: 'var(--brand-tint)', borderColor: 'var(--brand)', color: 'var(--brand-ink)' } : undefined}>
              {Math.round(p * 100)}%
            </button>
          ))}
        </div>

        <div className={s.detailGrid}>
          <div>
            <h3 className={s.sectionTitle}>Liquidity ladder (cumulative % of NAV sellable)</h3>
            <div className={s.ladder}>
              {ladder.map((l) => (
                <div key={l.days} className={s.ladderRow}>
                  <span>{l.days} day{l.days === 1 ? '' : 's'}</span>
                  <div className={s.ladderTrack} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={l.cum_pct_nav} aria-label={`${l.days} days: ${l.cum_pct_nav.toFixed(1)}% of NAV`}>
                    <div className={s.ladderFill} style={{ width: `${Math.min(100, l.cum_pct_nav)}%` }} />
                  </div>
                  <span className={base.figure}>{l.cum_pct_nav.toFixed(1)}%</span>
                </div>
              ))}
            </div>
            <p className={s.hint}>Full exit in {maxDtl?.toFixed(2)} days (slowest position). Cash counts as day-0 liquidity.</p>
            <table className={s.diffTable}>
              <thead><tr><th>Band</th><th>% NAV</th></tr></thead>
              <tbody>{data.bands.map((b) => <tr key={b.band}><td>{b.band}</td><td className={s.diffNum}>{b.pct_nav.toFixed(2)}%</td></tr>)}</tbody>
            </table>
          </div>
          <div>
            <h3 className={s.sectionTitle}>Liquidity-adjusted VaR (1 day)</h3>
            <table className={s.diffTable} style={{ marginTop: 8 }}>
              <thead><tr><th>Method</th><th>VaR</th><th>½ spread</th><th>Impact</th><th>LVaR</th></tr></thead>
              <tbody>
                {LV_ROWS.map(([k, label]) => (
                  <tr key={k}>
                    <td>{label}</td>
                    <td className={s.diffNum}>{usd(lv[k].var_usd)}</td>
                    <td className={s.diffNum}>{usd(lv[k].spread_cost_usd)}</td>
                    <td className={s.diffNum}>{usd(lv[k].impact_cost_usd)}</td>
                    <td className={s.diffNum}><strong>{usd(lv[k].lvar_usd)}</strong> ({lv[k].lvar_pct.toFixed(2)}%)</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className={s.hint}>LVaR = VaR + ½ × quoted spread × MV + square-root market impact (σ<sub>daily</sub> × √(qty/ADV) × MV).</p>
          </div>
        </div>
      </div>
      <div className={base.tableWrapper}>
        <table className={base.table}>
          <thead><tr><th>Ticker</th><th>Shares</th><th>ADV20 (sh)</th><th>% of ADV</th><th>Days to liquidate</th><th>Spread</th><th>½ spread $</th><th>Impact $</th></tr></thead>
          <tbody>
            {data.positions.map((p) => (
              <tr key={p.ticker}>
                <td><strong>{p.ticker}</strong>{p.flag_over_10pct_adv && <span className={`${s.status} ${s.statusAmber}`} style={{ marginLeft: 6 }}>! &gt;10% ADV</span>}</td>
                <td className={base.figure}>{p.quantity.toLocaleString()}</td>
                <td className={base.figure}>{Math.round(p.adv_20d_shares).toLocaleString()}</td>
                <td className={base.figure}>{p.pct_of_adv < 0.01 ? '<0.01' : p.pct_of_adv.toFixed(2)}%</td>
                <td className={base.figure}>{p.days_to_liquidate < 0.01 ? '<0.01' : p.days_to_liquidate.toFixed(2)}</td>
                <td className={base.figure}>{p.spread_bps} bp</td>
                <td className={base.figure}>{usd(p.half_spread_cost_usd)}</td>
                <td className={base.figure}>{usd(p.impact_cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

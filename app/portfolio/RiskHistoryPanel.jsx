'use client'

// RSK-004: pro-forma risk history — NAV vs HWM, underwater drawdown, VaR vs realised P&L.
import { useEffect, useState } from 'react'
import base from './portfolio.module.css'
import s from './limits.module.css'
import RiskChart from './RiskChart'

const RANGES = ['1M', '3M', '6M', '1Y']
const usd = (v) => (v === null || v === undefined) ? '—' : `${v < 0 ? '−' : ''}$${Math.abs(Math.round(v)).toLocaleString()}`
const usdK = (v) => { const a = Math.abs(v); const t = a >= 1000 ? `$${(a / 1000).toFixed(0)}k` : `$${Math.round(a)}`; return v < 0 ? `−${t}` : t }
const pct = (v, d = 2) => (v === null || v === undefined) ? '—' : `${(v * 100).toFixed(d)}%`

export default function RiskHistoryPanel({ portfolioId, refreshKey }) {
  const [range, setRange] = useState('1Y')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [showTable, setShowTable] = useState(false)

  useEffect(() => {
    if (!portfolioId) return
    setErr(null)
    fetch(`/api/portfolios/${portfolioId}/risk-history?range=${range}`)
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || 'Failed'); setData(j) })
      .catch((e) => setErr(e.message))
  }, [portfolioId, range, refreshKey])

  if (err) return <div className={base.panel}><div className={s.section} role="alert">{err}</div></div>
  if (!data) return <div className={base.panel}><div className={s.section}>Loading risk history…</div></div>

  const rows = data.rows.map((r) => ({ ...r, neg_var95_usd: -r.var95_usd, exception: r.pnl_usd < -r.var95_usd }))
  const sm = data.summary
  const exc = rows.filter((r) => r.exception).length

  return (
    <div className={base.panel}>
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>Risk history</h2>
          <span className={s.sectionMeta} title={`${data._provenance.window}. Source: ${data._provenance.source}. As of ${data._provenance.as_of}.`}>
            Pro-forma, current holdings · as of {data._provenance.as_of} ⓘ
          </span>
        </div>
        <div className={s.summaryRow} role="group" aria-label="Range">
          {RANGES.map((r) => (
            <button key={r} className={s.smallBtn} aria-pressed={range === r}
              style={range === r ? { background: 'var(--brand-tint)', borderColor: 'var(--brand)', color: 'var(--brand-ink)' } : undefined}
              onClick={() => setRange(r)}>{r}</button>
          ))}
          <button className={s.smallBtn} onClick={() => setShowTable(!showTable)} aria-expanded={showTable} style={{ marginLeft: 'auto' }}>
            {showTable ? 'Hide table' : 'Table view'}
          </button>
        </div>
        <div className={s.statGrid}>
          <div><span className={s.statLabel}>NAV</span><span className={s.statValue}>{usd(sm.latest_nav)}</span></div>
          <div><span className={s.statLabel}>High-water mark (1Y)</span><span className={s.statValue}>{usd(sm.latest_hwm)}</span></div>
          <div><span className={s.statLabel}>Current drawdown</span><span className={s.statValue}>{pct(sm.latest_drawdown)}</span></div>
          <div><span className={s.statLabel}>Max drawdown (1Y)</span><span className={s.statValue}>{pct(sm.max_drawdown)}</span><span className={s.statSub}>{sm.max_drawdown_date}</span></div>
        </div>

        <RiskChart
          title="NAV and high-water mark"
          data={rows}
          series={[
            { key: 'nav', label: 'NAV', color: 'var(--brand-ink)' },
            { key: 'hwm', label: 'High-water mark', color: 'var(--ink-3)', dashed: true }
          ]}
          yFormat={(v, full) => (full ? usd(v) : usdK(v))}
          bands={data.stress_windows}
        />
        <RiskChart
          title="Drawdown from high-water mark (under water)"
          data={rows}
          height={160}
          series={[{ key: 'drawdown', label: 'Drawdown', color: 'var(--bear)', type: 'area' }]}
          yFormat={(v) => pct(v, 1)}
          bands={data.stress_windows}
        />
        <RiskChart
          title={`Daily P&L vs 1-day VaR 95% (${exc} day${exc === 1 ? '' : 's'} with loss beyond VaR in range)`}
          data={rows}
          series={[
            { key: 'pnl_usd', label: 'Daily P&L', color: 'var(--ink-3)', type: 'bar' },
            { key: 'neg_var95_usd', label: '−VaR 95% (forecast, prior day)', color: 'var(--brand-ink)' }
          ]}
          markerKey="exception"
          markerLabel="Loss beyond VaR"
          yFormat={(v, full) => (full ? usd(v) : usdK(v))}
          bands={data.stress_windows}
        />
        <p className={s.hint}>Shaded areas are the injected mock stress windows (RSK-001). VaR uses the 252 daily returns ending the day before, so there is no lookahead.</p>
      </div>
      {showTable && (
        <div className={base.tableWrapper} style={{ maxHeight: 360, overflowY: 'auto' }}>
          <table className={base.table}>
            <thead><tr><th>Date</th><th>NAV</th><th>HWM</th><th>Drawdown</th><th>P&L</th><th>VaR 95%</th><th>ES 97.5%</th><th>Beta</th><th>Ex-ante vol</th></tr></thead>
            <tbody>
              {[...rows].reverse().map((r) => (
                <tr key={r.date}>
                  <td>{r.date}</td><td className={base.figure}>{usd(r.nav)}</td><td className={base.figure}>{usd(r.hwm)}</td>
                  <td className={base.figure}>{pct(r.drawdown)}</td><td className={base.figure}>{usd(r.pnl_usd)}</td>
                  <td className={base.figure}>{pct(r.var95)}</td><td className={base.figure}>{pct(r.es975)}</td>
                  <td className={base.figure}>{r.beta.toFixed(2)}</td><td className={base.figure}>{pct(r.vol_exante, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

'use client'

// RSK-011: component / marginal VaR, diversification ratio, correlation regime (60d vs 252d) and calm-vs-stress matrices.
import { useEffect, useState } from 'react'
import base from './portfolio.module.css'
import s from './limits.module.css'
import RiskChart from './RiskChart'

const usd = (v) => (v === null || v === undefined) ? '—' : `${v < 0 ? '−' : ''}$${Math.abs(Math.round(v)).toLocaleString()}`

function Matrix({ title, m }) {
  return (
    <div>
      <span className={s.statLabel}>{title} · avg {m.avg.toFixed(2)}</span>
      <table className={s.heat} style={{ marginTop: 6 }}>
        <thead><tr><th /> {m.tickers.map((t) => <th key={t}>{t}</th>)}</tr></thead>
        <tbody>
          {m.matrix.map((row, i) => (
            <tr key={m.tickers[i]}>
              <th>{m.tickers[i]}</th>
              {row.map((v, j) => (
                <td key={j} style={{ background: i === j ? 'var(--surface-2)' : `color-mix(in srgb, var(--brand) ${Math.round(Math.max(0, v) * 55)}%, var(--surface))` }}>
                  {v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AttributionPanel({ portfolioId, refreshKey }) {
  const [conf, setConf] = useState(0.99)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!portfolioId) return
    setErr(null)
    fetch(`/api/portfolios/${portfolioId}/risk-attribution?confidence=${conf}`)
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || 'Failed'); setData(j) })
      .catch((e) => setErr(e.message))
  }, [portfolioId, conf, refreshKey])

  if (err) return <div className={base.panel}><div className={s.section} role="alert">{err}</div></div>
  if (!data) return <div className={base.panel}><div className={s.section}>Loading attribution…</div></div>
  if (!data.positions?.length) return <div className={base.panel}><div className={s.section}>No positions.</div></div>

  const c = data.correlation
  const maxPct = Math.max(...data.positions.map((p) => Math.abs(p.pct_contribution)), 1)

  return (
    <div className={base.panel}>
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>VaR attribution</h2>
          <span className={s.sectionMeta} title={data._provenance.method}>{data._provenance.window} Ledoit-Wolf · as of {data._provenance.as_of} ⓘ</span>
        </div>
        <div className={s.summaryRow} role="group" aria-label="Confidence">
          {[0.95, 0.99].map((v) => (
            <button key={v} className={s.smallBtn} aria-pressed={conf === v} onClick={() => setConf(v)}
              style={conf === v ? { background: 'var(--brand-tint)', borderColor: 'var(--brand)', color: 'var(--brand-ink)' } : undefined}>{Math.round(v * 100)}%</button>
          ))}
        </div>
        <div className={s.statGrid}>
          <div><span className={s.statLabel}>Parametric VaR {Math.round(conf * 100)}% 1d</span><span className={s.statValue}>{usd(data.var_usd)}</span><span className={s.statSub}>{data.var_pct.toFixed(2)}% of NAV</span></div>
          <div><span className={s.statLabel}>Sum of component VaR</span><span className={s.statValue}>{usd(data.sum_component_var_usd)}</span><span className={s.statSub}>{Math.abs(data.sum_component_var_usd - data.var_usd) < 0.01 ? '✓ equals total VaR' : '✕ does not reconcile'}</span></div>
          <div><span className={s.statLabel}>Diversification ratio</span><span className={s.statValue}>{data.diversification_ratio.toFixed(2)}</span><span className={s.statSub}>Σ wᵢσᵢ / σₚ (1 = no diversification)</span></div>
          {c && (
            <div>
              <span className={s.statLabel}>Avg correlation 60d vs 252d</span>
              <span className={s.statValue}>{c.latest.corr_60d.toFixed(2)} / {c.latest.corr_252d.toFixed(2)}</span>
              <span className={s.statSub}>{c.latest.spike ? <strong style={{ color: 'var(--bear)' }}>✕ Correlation spike</strong> : `✓ No spike (Δ ${c.latest.spread >= 0 ? '+' : ''}${c.latest.spread.toFixed(2)}, flag > ${c.threshold})`}</span>
            </div>
          )}
        </div>
      </div>
      <div className={base.tableWrapper}>
        <table className={base.table}>
          <thead><tr><th>Ticker</th><th>Weight</th><th>Standalone VaR</th><th>Marginal VaR (per $1)</th><th>Component VaR</th><th style={{ minWidth: 160 }}>% of VaR</th><th>If cut 1%</th></tr></thead>
          <tbody>
            {data.positions.map((p) => (
              <tr key={p.ticker}>
                <td><strong>{p.ticker}</strong> <span className={base.subText}>{p.sector}</span></td>
                <td className={base.figure}>{p.weight_pct.toFixed(2)}%</td>
                <td className={base.figure}>{usd(p.standalone_var_usd)}</td>
                <td className={base.figure}>{p.marginal_var.toFixed(4)}</td>
                <td className={base.figure}>{usd(p.component_var_usd)}</td>
                <td>
                  <div className={s.ladderRow} style={{ gridTemplateColumns: '1fr 60px' }}>
                    <div className={s.ladderTrack}><div className={s.ladderFill} style={{ width: `${Math.max(0, p.pct_contribution) / maxPct * 100}%` }} /></div>
                    <span className={base.figure}>{p.pct_contribution.toFixed(1)}%</span>
                  </div>
                </td>
                <td className={base.figure}>VaR {usd(p.var_change_if_cut_1pct_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {c && (
        <div className={s.section}>
          <RiskChart
            title={`Average pairwise correlation of holdings: 60d vs 252d (${c.flagged_dates.length} spike day${c.flagged_dates.length === 1 ? '' : 's'} in the last year)`}
            data={c.series}
            series={[
              { key: 'corr_60d', label: '60-day', color: 'var(--brand-ink)' },
              { key: 'corr_252d', label: '252-day', color: 'var(--ink-3)', dashed: true }
            ]}
            markerKey="spike"
            markerLabel={`Spike (60d − 252d > ${c.threshold})`}
            yFormat={(v) => v.toFixed(2)}
            bands={c.stress_windows}
          />
          <div className={s.matrixPair}>
            <Matrix title="Calm-period correlation" m={c.calm_matrix} />
            <Matrix title="Stress-window correlation" m={c.stress_matrix} />
          </div>
        </div>
      )}
    </div>
  )
}

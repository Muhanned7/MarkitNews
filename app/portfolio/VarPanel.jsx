'use client'

// RSK-005 VaR / ES methods side by side + RSK-006 backtest (Kupiec, Christoffersen, Basel zone).
import { useEffect, useState } from 'react'
import base from './portfolio.module.css'
import s from './limits.module.css'
import RiskChart from './RiskChart'

const METHODS = [
  { key: 'historical', label: 'Historical' },
  { key: 'parametric', label: 'Parametric (normal)' },
  { key: 'ewma', label: 'EWMA λ 0.94' },
  { key: 'cornish_fisher', label: 'Cornish-Fisher' }
]
const pct = (v, d = 2) => (v === null || v === undefined) ? '—' : `${(v * 100).toFixed(d)}%`
const usd = (v) => (v === null || v === undefined) ? '—' : `$${Math.round(v).toLocaleString()}`

function Toggle({ label, value, options, onChange }) {
  return (
    <div role="group" aria-label={label} style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
      <span className={s.statLabel} style={{ marginRight: 4 }}>{label}</span>
      {options.map((o) => (
        <button key={o.v} className={s.smallBtn} aria-pressed={value === o.v} onClick={() => onChange(o.v)}
          style={value === o.v ? { background: 'var(--brand-tint)', borderColor: 'var(--brand)', color: 'var(--brand-ink)' } : undefined}>
          {o.l}
        </button>
      ))}
    </div>
  )
}

function Zone({ zone }) {
  if (!zone) return <span className={s.hint}>n/a (99% only)</span>
  const cls = zone === 'green' ? s.zoneGreen : zone === 'amber' ? s.zoneAmber : s.zoneRed
  const icon = zone === 'green' ? '✓' : zone === 'amber' ? '!' : '✕'
  return <span className={`${s.zone} ${cls}`}><span aria-hidden="true">{icon}</span>{zone[0].toUpperCase() + zone.slice(1)}</span>
}

export default function VarPanel({ portfolioId, refreshKey }) {
  const [conf, setConf] = useState(0.99)
  const [horizon, setHorizon] = useState(1)
  const [rep, setRep] = useState(null)
  const [bt, setBt] = useState(null)
  const [btMethod, setBtMethod] = useState('parametric')
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!portfolioId) return
    setErr(null)
    fetch(`/api/portfolios/${portfolioId}/var?confidence=${conf}&horizon=${horizon}`)
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || 'Failed'); setRep(j) })
      .catch((e) => setErr(e.message))
  }, [portfolioId, conf, horizon, refreshKey])

  useEffect(() => {
    if (!portfolioId) return
    setBt(null)
    fetch(`/api/portfolios/${portfolioId}/var-backtest?confidence=${conf}`)
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || 'Failed'); setBt(j) })
      .catch((e) => setErr(e.message))
  }, [portfolioId, conf, refreshKey])

  if (err) return <div className={base.panel}><div className={s.section} role="alert">{err}</div></div>
  if (!rep) return <div className={base.panel}><div className={s.section}>Loading VaR…</div></div>

  const prov = rep._provenance
  const tip = (m) => `${m.method}. Window: ${m.window}. Basis: ${prov.basis}. As of ${prov.as_of}.`
  const pm = rep.portfolio.methods
  const sel = bt?.methods?.[btMethod]
  const series = sel ? sel.series.map((d) => ({ ...d, neg_var: -d.var })) : []

  return (
    <div className={base.panel}>
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>Value at Risk and Expected Shortfall</h2>
          <span className={s.sectionMeta}>{prov.basis} · {prov.window} · as of {prov.as_of}</span>
        </div>
        <div className={s.summaryRow} style={{ gap: 16 }}>
          <Toggle label="Confidence" value={conf} options={[{ v: 0.95, l: '95%' }, { v: 0.99, l: '99%' }]} onChange={setConf} />
          <Toggle label="Horizon" value={horizon} options={[{ v: 1, l: '1 day' }, { v: 10, l: '10 days' }]} onChange={setHorizon} />
        </div>
        {prov.horizon_caveat && <p className={s.caveat} role="note">⚠ {prov.horizon_caveat}</p>}
      </div>
      <div className={base.tableWrapper}>
        <table className={base.table}>
          <thead>
            <tr><th>Method</th><th>VaR {Math.round(conf * 100)}% ({horizon}d)</th><th>VaR $</th><th>ES {Math.round(conf * 100)}% ({horizon}d)</th><th>ES $</th></tr>
          </thead>
          <tbody>
            {METHODS.map((m) => (
              <tr key={m.key}>
                <td><span title={tip(pm[m.key])} style={{ borderBottom: '1px dotted var(--ink-3)', cursor: 'help' }}>{m.label}</span></td>
                <td className={base.figure}>{pct(pm[m.key].var)}</td>
                <td className={base.figure}>{usd(pm[m.key].var_usd)}</td>
                <td className={base.figure}>{pct(pm[m.key].es)}</td>
                <td className={base.figure}>{usd(pm[m.key].es_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={s.section}>
        <p className={s.hint}>
          ES 97.5% (1d): historical {pct(rep.portfolio.es975.historical)} · parametric {pct(rep.portfolio.es975.parametric)}.
          Portfolio return moments: skew {rep.portfolio.moments.skew.toFixed(2)}, excess kurtosis {rep.portfolio.moments.excess_kurtosis.toFixed(2)}.
          Hover a method name for its window and as-of.
        </p>
        <h3 className={s.sectionTitle} style={{ marginTop: 12 }}>By holding (VaR {Math.round(conf * 100)}%, {horizon}d, % of position)</h3>
      </div>
      <div className={base.tableWrapper}>
        <table className={base.table}>
          <thead><tr><th>Ticker</th>{METHODS.map((m) => <th key={m.key}>{m.label}</th>)}<th>Excess kurtosis</th></tr></thead>
          <tbody>
            {rep.positions.map((p) => (
              <tr key={p.ticker}>
                <td><strong>{p.ticker}</strong></td>
                {METHODS.map((m) => <td key={m.key} className={base.figure}>{pct(p.methods[m.key].var)}</td>)}
                <td className={base.figure}>{p.moments.excess_kurtosis.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <hr className={s.divider} />
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>VaR backtest ({bt ? `${bt.test_days} days` : '…'}, {Math.round(conf * 100)}%)</h2>
          {bt && <span className={s.sectionMeta} title={bt._provenance.method}>No lookahead: day-t VaR uses the {bt.estimation_window} returns ending t−1 ⓘ</span>}
        </div>
        {!bt ? <p className={s.hint}>Running backtest…</p> : (
          <>
            <div className={base.tableWrapper}>
              <table className={base.table}>
                <thead><tr><th>Method</th><th>Exceptions</th><th>Expected</th><th>Kupiec LR (p)</th><th>Christoffersen LR (p)</th><th>Basel zone</th><th /></tr></thead>
                <tbody>
                  {METHODS.map((m) => {
                    const r = bt.methods[m.key]
                    return (
                      <tr key={m.key} style={btMethod === m.key ? { background: 'var(--surface-2)' } : undefined}>
                        <td>{m.label}</td>
                        <td className={base.figure}>{r.exceptions}</td>
                        <td className={base.figure}>{r.expected}</td>
                        <td className={base.figure}>{r.kupiec.lr.toFixed(2)} ({r.kupiec.p_value.toFixed(3)}){r.kupiec.reject_95 ? ' ✕ reject' : ''}</td>
                        <td className={base.figure}>{r.christoffersen.lr.toFixed(2)} ({r.christoffersen.p_value.toFixed(3)}){r.christoffersen.reject_95 ? ' ✕ clustered' : ''}</td>
                        <td><Zone zone={r.basel_zone} /></td>
                        <td><button className={s.smallBtn} aria-pressed={btMethod === m.key} onClick={() => setBtMethod(m.key)}>Chart</button></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {sel && (
              <div className={s.chartBlock}>
                <p className={s.preTradeTitle}>
                  {METHODS.find((m) => m.key === btMethod).label}: {sel.exceptions} exceptions vs {sel.expected} expected,
                  Kupiec p = {sel.kupiec.p_value.toFixed(3)}, zone = {sel.basel_zone ? sel.basel_zone[0].toUpperCase() + sel.basel_zone.slice(1) : 'n/a'}
                </p>
                <RiskChart
                  data={series}
                  ariaLabel="Daily portfolio return against negative VaR forecast, exceptions marked"
                  series={[
                    { key: 'return', label: 'Daily return', color: 'var(--ink-3)', type: 'bar' },
                    { key: 'neg_var', label: `−VaR ${Math.round(conf * 100)}% forecast`, color: 'var(--brand-ink)' }
                  ]}
                  markerKey="exception"
                  markerLabel="Exception (loss beyond VaR)"
                  yFormat={(v) => pct(v, 1)}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

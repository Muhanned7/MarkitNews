'use client'

import { useEffect, useState } from 'react'
import base from './portfolio.module.css'
import s from './limits.module.css'
import RiskChart from './RiskChart'

const usd = (v) =>
  v === null || v === undefined
    ? '—'
    : `${v < 0 ? '−' : ''}$${Math.abs(Math.round(v)).toLocaleString()}`

// ---------------------------------------------------------------------------
// RSK-012: Beta & Sector ETF Hedge Calculator + Drawdown Control Rules
// ---------------------------------------------------------------------------
export function HedgePanel({ portfolioId, refreshKey, onPrefillTrade }) {
  const [targetBeta, setTargetBeta] = useState(0.0)
  const [simDd, setSimDd] = useState('')
  const [deriskMode, setDeriskMode] = useState('pro_rata')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!portfolioId) return
    setErr(null)
    const params = new URLSearchParams({
      target_beta: String(targetBeta),
      derisk_mode: deriskMode,
    })
    if (simDd !== '') params.set('simulated_dd_pct', String(simDd))
    fetch(`/api/portfolios/${portfolioId}/hedge-calculator?${params.toString()}`)
      .then(async (r) => {
        const j = await r.json()
        if (!r.ok) throw new Error(j.detail || 'Failed to load hedge calculator')
        setData(j)
      })
      .catch((e) => setErr(e.message))
  }, [portfolioId, targetBeta, simDd, deriskMode, refreshKey])

  if (err) return <div className={base.panel}><div className={s.section} role="alert">{err}</div></div>
  if (!data) return <div className={base.panel}><div className={s.section}>Loading hedge &amp; de-risking calculator…</div></div>

  const bh = data.beta_hedge
  const dc = data.drawdown_control

  return (
    <div className={base.panel}>
      {/* 1. SPY Beta Hedge Section */}
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>1. Portfolio Beta Hedge Calculator (SPY)</h2>
          <span className={s.sectionMeta} title={data._provenance?.method}>
            {data._provenance?.source} · {data._provenance?.window} ⓘ
          </span>
        </div>

        <div className={s.summaryRow} style={{ alignItems: 'center', gap: 10 }}>
          <span className={s.statLabel}>Target Beta:</span>
          {[0.0, 0.25, 0.5, 0.75].map((b) => (
            <button
              key={b}
              className={s.smallBtn}
              aria-pressed={targetBeta === b}
              onClick={() => setTargetBeta(b)}
              style={targetBeta === b ? { background: 'var(--brand-tint)', borderColor: 'var(--brand)', color: 'var(--brand-ink)' } : undefined}
            >
              {b === 0.0 ? '0.00 (Beta-Neutral)' : b.toFixed(2)}
            </button>
          ))}
          {onPrefillTrade && bh.trade.qty !== 0 && (
            <button
              className={s.smallBtn}
              style={{ marginLeft: 'auto', background: 'var(--brand)', color: '#fff', borderColor: 'var(--brand)' }}
              onClick={() => onPrefillTrade(bh.what_if_payload)}
            >
              Stage {bh.trade.action} {Math.abs(bh.trade.qty)} {bh.trade.ticker} in Trade Ticket →
            </button>
          )}
        </div>

        <div className={s.statGrid} style={{ marginTop: 12 }}>
          <div>
            <span className={s.statLabel}>Recommended SPY Trade</span>
            <span className={s.statValue}>
              {bh.trade.action} {Math.abs(bh.trade.qty)} SPY @ ${bh.trade.price.toFixed(2)}
            </span>
            <span className={s.statSub}>
              Notional: {usd(bh.trade.notional_usd)} ({bh.trade.pct_of_nav}% of NAV)
            </span>
          </div>
          <div>
            <span className={s.statLabel}>Portfolio Beta (Before → After)</span>
            <span className={s.statValue}>
              {bh.before.portfolio_beta.toFixed(2)} → {bh.after.portfolio_beta.toFixed(2)}
            </span>
            <span className={s.statSub}>
              {bh.within_tolerance_002 ? '✓ Within ±0.02 target tolerance' : `Residual: ${bh.beta_residual.toFixed(3)}`}
            </span>
          </div>
          <div>
            <span className={s.statLabel}>Ex-Ante Ann. Vol (Before → After)</span>
            <span className={s.statValue}>
              {bh.before.ex_ante_vol_pct.toFixed(2)}% → {bh.after.ex_ante_vol_pct.toFixed(2)}%
            </span>
            <span className={s.statSub}>
              1d 95% VaR: {bh.before.var95_1d_pct.toFixed(2)}% → {bh.after.var95_1d_pct.toFixed(2)}%
            </span>
          </div>
          <div>
            <span className={s.statLabel}>Gross / Net Exposure After</span>
            <span className={s.statValue}>
              {bh.after.gross_exposure_pct.toFixed(1)}% / {bh.after.net_exposure_pct.toFixed(1)}%
            </span>
            <span className={s.statSub}>
              Before: {bh.before.gross_exposure_pct.toFixed(1)}% / {bh.before.net_exposure_pct.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      {/* 2. Sector ETF Hedges & Single-Name Trim Section */}
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>2. Sector Concentration Hedges (SPDR Sector ETF vs Single-Name Trim)</h2>
          <span className={s.sectionMeta}>Resolves sector hard limit (&gt;30%) and soft limit (&gt;27%) breaches</span>
        </div>

        <div className={base.tableWrapper}>
          <table className={base.table}>
            <thead>
              <tr>
                <th>Sector</th>
                <th>Current Weight</th>
                <th>Hard Limit</th>
                <th>Target Weight</th>
                <th>Option A: Sector ETF Short Hedge</th>
                <th>Post-ETF Sector Wt</th>
                <th>Option B: Single-Name Pro-Rata Trim</th>
                <th>Post-Trim Sector Wt</th>
              </tr>
            </thead>
            <tbody>
              {data.sector_hedges.map((sh) => {
                const etf = sh.etf_hedge
                const trim = sh.single_name_trim
                return (
                  <tr key={sh.sector}>
                    <td>
                      <strong>{sh.sector}</strong>{' '}
                      <span
                        className={s.badge}
                        style={{
                          background: sh.status === 'hard_breach' ? 'var(--bear-tint)' : sh.status === 'soft_breach' ? 'var(--warn-tint)' : 'var(--bull-tint)',
                          color: sh.status === 'hard_breach' ? 'var(--bear)' : sh.status === 'soft_breach' ? 'var(--warn)' : 'var(--bull)',
                        }}
                      >
                        {sh.status === 'hard_breach' ? 'HARD BREACH' : sh.status === 'soft_breach' ? 'SOFT WARN' : 'OK'}
                      </span>
                    </td>
                    <td className={base.figure}>{sh.current_weight_pct.toFixed(2)}%</td>
                    <td className={base.figure}>{sh.hard_limit_pct.toFixed(1)}%</td>
                    <td className={base.figure}>{sh.target_weight_pct.toFixed(2)}%</td>
                    <td className={base.figure}>
                      <strong>{etf.trade.action} {Math.abs(etf.trade.qty)} {etf.trade.ticker}</strong> @ ${etf.trade.price.toFixed(2)} ({usd(etf.trade.notional_usd)})
                    </td>
                    <td className={base.figure}>
                      <strong>{etf.post_sector_weight_pct.toFixed(2)}%</strong>{' '}
                      {etf.within_hard_limit && <span style={{ color: 'var(--bull)' }}>✓ ≤{sh.hard_limit_pct}%</span>}
                    </td>
                    <td className={base.figure}>
                      {trim.trades.length === 0
                        ? '—'
                        : trim.trades.map((t) => `${t.action} ${Math.abs(t.qty)} ${t.ticker}`).join(', ')}
                    </td>
                    <td className={base.figure}>
                      <strong>{trim.post_sector_weight_pct.toFixed(2)}%</strong>{' '}
                      {trim.within_hard_limit && <span style={{ color: 'var(--bull)' }}>✓ ≤{sh.hard_limit_pct}%</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. Drawdown Control Rules (R-P1-4) */}
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>3. Drawdown Control Rules &amp; De-Risking Basket (R-P1-4)</h2>
          <span className={s.sectionMeta}>Tier 1 (−5% DD): Alert · Tier 2 (−10% DD): Mandatory 25% Gross Exposure Cut</span>
        </div>

        <div className={s.summaryRow} style={{ alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className={s.statLabel}>Test Drawdown Regime:</span>
          {[
            ['', `Actual (${dc.actual_drawdown_pct.toFixed(2)}%)`],
            ['-5.5', 'Simulate Tier 1 (−5.5%)'],
            ['-10.5', 'Simulate Tier 2 (−10.5%)'],
          ].map(([val, label]) => (
            <button
              key={label}
              className={s.smallBtn}
              aria-pressed={String(simDd) === val}
              onClick={() => setSimDd(val)}
              style={String(simDd) === val ? { background: 'var(--brand-tint)', borderColor: 'var(--brand)', color: 'var(--brand-ink)' } : undefined}
            >
              {label}
            </button>
          ))}
          <span className={s.statLabel} style={{ marginLeft: 16 }}>De-Risk Allocation Mode:</span>
          {[
            ['pro_rata', 'Pro-Rata 25% Cut'],
            ['top_rc', 'Top Euler Risk Contributors First'],
          ].map(([m, label]) => (
            <button
              key={m}
              className={s.smallBtn}
              aria-pressed={deriskMode === m}
              onClick={() => setDeriskMode(m)}
              style={deriskMode === m ? { background: 'var(--brand-tint)', borderColor: 'var(--brand)', color: 'var(--brand-ink)' } : undefined}
            >
              {label}
            </button>
          ))}
        </div>

        <div
          style={{
            marginTop: 12,
            padding: '12px 16px',
            borderRadius: 'var(--r-card)',
            background: dc.tier === 2 ? 'var(--bear-tint)' : dc.tier === 1 ? 'var(--warn-tint)' : 'var(--surface-2)',
            color: dc.tier === 2 ? 'var(--bear)' : dc.tier === 1 ? 'var(--warn)' : 'var(--ink)',
            fontWeight: 600,
          }}
        >
          [{dc.status}] {dc.action_summary}
        </div>

        <div className={s.statGrid} style={{ marginTop: 12 }}>
          <div>
            <span className={s.statLabel}>Gross Exposure Cut</span>
            <span className={s.statValue}>−{dc.achieved_gross_cut_pct.toFixed(2)}%</span>
            <span className={s.statSub}>
              {dc.before.gross_exposure_pct.toFixed(2)}% → {dc.after.gross_exposure_pct.toFixed(2)}% of NAV
            </span>
          </div>
          <div>
            <span className={s.statLabel}>Ex-Ante Vol Reduction</span>
            <span className={s.statValue}>−{dc.vol_reduction_pct.toFixed(2)}%</span>
            <span className={s.statSub}>
              {dc.before.ex_ante_vol_pct.toFixed(2)}% → {dc.after.ex_ante_vol_pct.toFixed(2)}% ann.
            </span>
          </div>
          <div>
            <span className={s.statLabel}>1d 95% VaR (Before → After)</span>
            <span className={s.statValue}>
              {usd(dc.before.var95_1d_usd)} → {usd(dc.after.var95_1d_usd)}
            </span>
            <span className={s.statSub}>
              {dc.before.var95_1d_pct.toFixed(2)}% → {dc.after.var95_1d_pct.toFixed(2)}% of NAV
            </span>
          </div>
          <div>
            <span className={s.statLabel}>252d Pro-Forma HWM</span>
            <span className={s.statValue}>{usd(dc.hwm_usd)}</span>
            <span className={s.statSub}>Current NAV: {usd(dc.before.nav)}</span>
          </div>
        </div>

        <div className={base.tableWrapper} style={{ marginTop: 12 }}>
          <table className={base.table}>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Sector</th>
                <th>Current Qty</th>
                <th>De-Risk Trade Qty</th>
                <th>Price</th>
                <th>Proceeds Freed</th>
                <th>Euler Risk Share</th>
                <th>Rule Rationale</th>
              </tr>
            </thead>
            <tbody>
              {dc.derisk_trades.map((t) => (
                <tr key={t.ticker}>
                  <td><strong>{t.ticker}</strong> <span className={base.subText}>{t.company_name}</span></td>
                  <td>{t.sector}</td>
                  <td className={base.figure}>{t.current_qty}</td>
                  <td className={`${base.figure} ${base.negChange}`}>{t.qty}</td>
                  <td className={base.figure}>${t.price.toFixed(2)}</td>
                  <td className={base.figure}>{usd(Math.abs(t.notional_usd))}</td>
                  <td className={base.figure}>{t.risk_contribution_pct.toFixed(2)}%</td>
                  <td><span className={base.subText}>{t.rationale}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RSK-013: AI Agent Model-Risk Monitor & Kill-Switch
// ---------------------------------------------------------------------------
export function ModelRiskPanel({ portfolioId, refreshKey }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [busyAgent, setBusyAgent] = useState(null)

  async function loadDashboard() {
    setErr(null)
    try {
      const r = await fetch(`/api/risk/model-risk?portfolio_id=${portfolioId || 1}`)
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'Failed to load model-risk dashboard')
      setData(j)
    } catch (e) {
      setErr(e.message)
    }
  }

  useEffect(() => {
    loadDashboard()
  }, [portfolioId, refreshKey])

  async function toggleKillSwitch(ag) {
    setBusyAgent(ag.agent_name)
    try {
      const nextKill = !ag.kill_switch
      const r = await fetch(`/api/risk/model-risk/agents/${ag.agent_name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kill_switch: nextKill,
          reason: nextKill
            ? `Manual kill-switch engaged via Model-Risk Console`
            : `Kill-switch released via Model-Risk Console`,
        }),
      })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'Update failed')
      setData(j)
    } catch (e) {
      alert(e.message)
    } finally {
      setBusyAgent(null)
    }
  }

  async function simulateDegrade(agentName, restore = false) {
    setBusyAgent(agentName)
    try {
      const r = await fetch('/api/risk/model-risk/simulate-degradation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_name: agentName,
          simulated_quality_score: restore ? 0.96 : 0.52,
          ticker: 'AAPL',
          restore,
        }),
      })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'Simulation failed')
      setData(j)
    } catch (e) {
      alert(e.message)
    } finally {
      setBusyAgent(null)
    }
  }

  if (err) return <div className={base.panel}><div className={s.section} role="alert">{err}</div></div>
  if (!data) return <div className={base.panel}><div className={s.section}>Loading AI model-risk monitor…</div></div>

  const vb = data.volatility_bias
  const sum = data.summary

  return (
    <div className={base.panel}>
      {sum.active_banner && (
        <div
          role="alert"
          style={{
            margin: '16px 20px 0 20px',
            padding: '12px 16px',
            borderRadius: 'var(--r-card)',
            background: 'var(--bear-tint)',
            border: '1px solid var(--bear)',
            color: 'var(--bear)',
            fontWeight: 700,
          }}
        >
          ⚠️ {sum.active_banner}
        </div>
      )}

      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>AI Agent Model-Risk Monitor &amp; Kill-Switch Governance (RSK-013)</h2>
          <span className={s.sectionMeta} title={data._provenance?.method}>{data._provenance?.source} ⓘ</span>
        </div>

        <div className={s.statGrid}>
          <div>
            <span className={s.statLabel}>Healthy Specialist Agents</span>
            <span className={s.statValue} style={{ color: 'var(--bull)' }}>
              {sum.healthy_count} / {sum.total_agents}
            </span>
            <span className={s.statSub}>Min quality gate: 0.70</span>
          </div>
          <div>
            <span className={s.statLabel}>Degraded / Killed Agents</span>
            <span className={s.statValue} style={{ color: sum.degraded_count + sum.killed_count > 0 ? 'var(--bear)' : 'var(--ink)' }}>
              {sum.degraded_count} Degraded · {sum.killed_count} Killed
            </span>
            <span className={s.statSub}>Excluded from downstream synthesis</span>
          </div>
          <div>
            <span className={s.statLabel}>Ex-Ante vs Ex-Post Vol Bias</span>
            <span className={s.statValue}>{vb.bias_statistic.toFixed(3)}</span>
            <span className={s.statSub}>
              {vb.within_band ? '✓ Calibrated [0.80, 1.20]' : `✕ ${vb.status} (outside [0.80, 1.20])`}
            </span>
          </div>
          <div>
            <span className={s.statLabel}>Ex-Ante vs Realized Vol (Ann.)</span>
            <span className={s.statValue}>
              {vb.ex_ante_vol_ann_pct.toFixed(1)}% vs {vb.ex_post_vol_ann_pct.toFixed(1)}%
            </span>
            <span className={s.statSub}>Ratio: {vb.ratio_ex_post_to_ex_ante.toFixed(2)}x ({vb.observations}d OOS)</span>
          </div>
        </div>
      </div>

      {/* Per-Agent Quality & Kill-Switch Table */}
      <div className={base.tableWrapper}>
        <table className={base.table}>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Governance Status</th>
              <th>Latest Quality</th>
              <th>Faithfulness / Consistency / Completeness</th>
              <th>Avg Quality (Runs)</th>
              <th>Guardrail Reject %</th>
              <th>Numeric Mismatches</th>
              <th>Model-Risk Controls</th>
            </tr>
          </thead>
          <tbody>
            {data.agents.map((ag) => {
              const isHealthy = ag.status === 'healthy'
              return (
                <tr key={ag.agent_name}>
                  <td>
                    <strong>{ag.label}</strong>
                    <div className={base.subText}>{ag.description}</div>
                  </td>
                  <td>
                    <span
                      className={s.badge}
                      style={{
                        background: isHealthy ? 'var(--bull-tint)' : 'var(--bear-tint)',
                        color: isHealthy ? 'var(--bull)' : 'var(--bear)',
                        fontWeight: 700,
                      }}
                    >
                      {ag.status.toUpperCase()}
                    </span>
                    <div className={base.subText} style={{ marginTop: 2 }}>{ag.status_reason}</div>
                  </td>
                  <td className={base.figure}>
                    <strong>{ag.latest_quality_score.toFixed(2)}</strong>{' '}
                    <span className={base.subText}>(min {ag.min_quality_threshold.toFixed(2)})</span>
                  </td>
                  <td className={base.figure}>
                    {ag.latest_faithfulness_score.toFixed(2)} / {ag.latest_consistency_score.toFixed(2)} / {ag.latest_completeness_score.toFixed(2)}
                  </td>
                  <td className={base.figure}>
                    {ag.avg_quality_score.toFixed(2)} ({ag.total_runs})
                  </td>
                  <td className={base.figure}>{ag.guardrail_rejection_rate_pct.toFixed(1)}%</td>
                  <td className={base.figure}>{ag.numeric_mismatches_count}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <button
                        className={s.smallBtn}
                        disabled={busyAgent === ag.agent_name}
                        onClick={() => toggleKillSwitch(ag)}
                        style={ag.kill_switch ? { background: 'var(--bear)', color: '#fff', borderColor: 'var(--bear)' } : undefined}
                      >
                        {ag.kill_switch ? 'Release Kill-Switch' : 'Kill-Switch'}
                      </button>
                      {isHealthy ? (
                        <button
                          className={s.smallBtn}
                          disabled={busyAgent === ag.agent_name}
                          onClick={() => simulateDegrade(ag.agent_name, false)}
                        >
                          Simulate Degrade (0.52)
                        </button>
                      ) : (
                        <button
                          className={s.smallBtn}
                          disabled={busyAgent === ag.agent_name}
                          onClick={() => simulateDegrade(ag.agent_name, true)}
                          style={{ background: 'var(--bull-tint)', color: 'var(--bull)', borderColor: 'var(--bull)' }}
                        >
                          Restore Healthy (0.96)
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Cross-Agent Disagreement Index */}
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>Cross-Agent Directional Disagreement Index (per Holding)</h2>
          <span className={s.sectionMeta}>Dispersion σ of directional agent stances mapped to [−1, +1]</span>
        </div>
        <div className={base.tableWrapper}>
          <table className={base.table}>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Disagreement Index</th>
                <th>Status</th>
                <th>Sentiment Stance</th>
                <th>Fundamentals Stance</th>
                <th>Technical Stance</th>
                <th>Equity Stance</th>
                <th>Risk Stance</th>
              </tr>
            </thead>
            <tbody>
              {data.disagreement_index.map((row) => (
                <tr key={row.ticker}>
                  <td><strong>{row.ticker}</strong> <span className={base.subText}>{row.sector}</span></td>
                  <td className={base.figure}><strong>{row.disagreement_index.toFixed(3)}</strong></td>
                  <td>
                    <span
                      className={s.badge}
                      style={{
                        background: row.status === 'high_conflict' ? 'var(--bear-tint)' : row.status === 'moderate_conflict' ? 'var(--warn-tint)' : 'var(--bull-tint)',
                        color: row.status === 'high_conflict' ? 'var(--bear)' : row.status === 'moderate_conflict' ? 'var(--warn)' : 'var(--bull)',
                      }}
                    >
                      {row.status.replace('_', ' ').toUpperCase()}
                    </span>
                  </td>
                  <td>{row.agent_stances.sentiment.stance} ({row.agent_stances.sentiment.score})</td>
                  <td>{row.agent_stances.fundamentals.stance} ({row.agent_stances.fundamentals.score})</td>
                  <td>{row.agent_stances.technical.stance} ({row.agent_stances.technical.score})</td>
                  <td>{row.agent_stances.equity.stance} ({row.agent_stances.equity.score})</td>
                  <td>{row.agent_stances.risk.stance} ({row.agent_stances.risk.score})</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Ex-Ante vs Ex-Post Volatility Calibration Chart */}
      {vb.series?.length > 0 && (
        <div className={s.section}>
          <RiskChart
            title={`Ex-Ante Forecast Vol vs 21d Realized Vol (Bias Statistic = ${vb.bias_statistic.toFixed(3)})`}
            data={vb.series}
            series={[
              { key: 'ex_ante_vol_pct', label: 'Ex-Ante Vol % (252d)', color: 'var(--brand-ink)' },
              { key: 'realized_21d_vol_pct', label: 'Realized 21d Vol %', color: 'var(--warn)', dashed: true },
            ]}
            yFormat={(v) => `${v.toFixed(1)}%`}
          />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// RSK-014: Executive Morning Risk Tear Sheet & Export
// ---------------------------------------------------------------------------
export function TearSheetPanel({ portfolioId, refreshKey }) {
  const [sheet, setSheet] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!portfolioId) return
    setErr(null)
    fetch(`/api/portfolios/${portfolioId}/tear-sheet`)
      .then(async (r) => {
        const j = await r.json()
        if (!r.ok) throw new Error(j.detail || 'Failed to load morning tear sheet')
        setSheet(j)
      })
      .catch((e) => setErr(e.message))
  }, [portfolioId, refreshKey])

  if (err) return <div className={base.panel}><div className={s.section} role="alert">{err}</div></div>
  if (!sheet) return <div className={base.panel}><div className={s.section}>Generating Executive Morning Risk Tear Sheet…</div></div>

  const hs = sheet.health_score
  const ov = sheet.overview
  const dod = sheet.day_over_day
  const liq = sheet.liquidity_summary
  const mr = sheet.model_risk_summary
  const btParam = sheet.var_es_summary?.backtest_99?.parametric || {}

  return (
    <div className={base.panel}>
      <div className={s.section}>
        <div className={s.sectionHead} style={{ flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h2 className={s.sectionTitle}>
              Executive Morning Risk Tear Sheet — {sheet.portfolio_name}
            </h2>
            <span className={s.sectionMeta}>
              Generated {sheet.generated_at} · {sheet._provenance?.basis}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <a
              href={`/api/portfolios/${portfolioId}/tear-sheet/export?format=csv`}
              download={`portfolio_${portfolioId}_morning_tear_sheet.csv`}
              className={s.smallBtn}
              style={{ textDecoration: 'none', background: 'var(--brand)', color: '#fff', borderColor: 'var(--brand)' }}
            >
              ⬇ Download CSV Tear Sheet
            </a>
            <a
              href={`/api/portfolios/${portfolioId}/tear-sheet/export?format=html`}
              target="_blank"
              rel="noreferrer"
              className={s.smallBtn}
              style={{ textDecoration: 'none' }}
            >
              🖨 Print / PDF View
            </a>
          </div>
        </div>

        {/* Top KPI & Health Score Strip */}
        <div className={s.statGrid} style={{ marginTop: 12 }}>
          <div>
            <span className={s.statLabel}>Risk Health Score</span>
            <span
              className={s.statValue}
              style={{ color: hs.score >= 80 ? 'var(--bull)' : hs.score >= 65 ? 'var(--warn)' : 'var(--bear)' }}
            >
              {hs.score} / 100
            </span>
            <span className={s.statSub}>{hs.grade}</span>
          </div>
          <div>
            <span className={s.statLabel}>NAV &amp; DoD Change</span>
            <span className={s.statValue}>{usd(ov.nav)}</span>
            <span className={s.statSub}>
              DoD: {dod.nav_dod_usd >= 0 ? '+' : ''}{usd(dod.nav_dod_usd)} ({dod.nav_dod_pct >= 0 ? '+' : ''}{dod.nav_dod_pct.toFixed(2)}%)
            </span>
          </div>
          <div>
            <span className={s.statLabel}>Open Breaches / Basel 99% Zone</span>
            <span className={s.statValue}>
              {sheet.breaches.hard_count} Hard · {sheet.breaches.soft_count} Soft
            </span>
            <span className={s.statSub}>
              Kupiec Backtest: <strong>{(btParam.zone || 'green').toUpperCase()}</strong> ({btParam.exceptions ?? 0} exc / 252d)
            </span>
          </div>
          <div>
            <span className={s.statLabel}>5d Liquid NAV &amp; LVaR Markup</span>
            <span className={s.statValue}>{liq.pct_nav_liquid_5d.toFixed(1)}%</span>
            <span className={s.statSub}>
              99% 1d LVaR: {usd(liq.lvar_99_1d_usd)} ({liq.lvar_to_var_ratio.toFixed(2)}x VaR)
            </span>
          </div>
        </div>
      </div>

      {/* Health Score Deductions & Active Breaches */}
      <div className={s.section}>
        <h3 className={s.sectionTitle} style={{ marginBottom: 8 }}>1. Risk Health Score Deductions &amp; Top Limit Utilisation</h3>
        <div className={base.tableWrapper}>
          <table className={base.table}>
            <thead>
              <tr>
                <th>Deduction Category</th>
                <th>Points Impact</th>
                <th>Explanation</th>
              </tr>
            </thead>
            <tbody>
              {hs.deductions.length === 0 ? (
                <tr><td colSpan={3}>No score deductions — all risk checks green.</td></tr>
              ) : (
                hs.deductions.map((d, i) => (
                  <tr key={i}>
                    <td><strong>{d.category}</strong></td>
                    <td className={`${base.figure} ${base.negChange}`}><strong>{d.points}</strong></td>
                    <td>{d.reason}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* VaR & ES Summary + Top 5 Stress Scenarios */}
      <div className={s.section}>
        <h3 className={s.sectionTitle} style={{ marginBottom: 8 }}>2. Multi-Method VaR / ES &amp; Top 5 Worst Stress Scenarios</h3>
        <div className={base.tableWrapper}>
          <table className={base.table}>
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Category</th>
                <th>Stress P&amp;L ($)</th>
                <th>Stress P&amp;L (% NAV)</th>
                <th>Largest Loss Contributor</th>
                <th>Limits Breached Post-Shock</th>
              </tr>
            </thead>
            <tbody>
              {sheet.top5_stress_scenarios.map((sc) => (
                <tr key={sc.name}>
                  <td><strong>{sc.name}</strong></td>
                  <td>{sc.kind}</td>
                  <td className={`${base.figure} ${base.negChange}`}>{usd(sc.pnl_usd)}</td>
                  <td className={`${base.figure} ${base.negChange}`}>{sc.pnl_pct.toFixed(2)}%</td>
                  <td><strong>{sc.worst_position}</strong></td>
                  <td className={base.figure}>{sc.new_breaches_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Top 3 Euler Risk Contributors & Recommended Hedges */}
      <div className={s.section}>
        <h3 className={s.sectionTitle} style={{ marginBottom: 8 }}>3. Top 3 Risk Contributors, Actionable Hedges &amp; AI Model Governance</h3>
        <div className={base.tableWrapper}>
          <table className={base.table}>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Ticker</th>
                <th>Sector</th>
                <th>Capital Weight</th>
                <th>Share of 99% VaR</th>
                <th>Component VaR ($)</th>
              </tr>
            </thead>
            <tbody>
              {sheet.top3_risk_contributors.map((c, idx) => (
                <tr key={c.ticker}>
                  <td className={base.figure}>#{idx + 1}</td>
                  <td><strong>{c.ticker}</strong></td>
                  <td>{c.sector}</td>
                  <td className={base.figure}>{c.weight_pct.toFixed(2)}%</td>
                  <td className={base.figure}><strong>{c.pct_contribution.toFixed(2)}%</strong></td>
                  <td className={base.figure}>{usd(c.component_var_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className={s.statGrid} style={{ marginTop: 14 }}>
          <div>
            <span className={s.statLabel}>Beta-Neutral SPY Hedge</span>
            <span className={s.statValue}>
              {sheet.hedge_summary.spy_beta_neutral.action} {Math.abs(sheet.hedge_summary.spy_beta_neutral.qty)} SPY
            </span>
            <span className={s.statSub}>
              Notional: {usd(sheet.hedge_summary.spy_beta_neutral.notional_usd)} → Post Beta {sheet.hedge_summary.post_spy_beta.toFixed(2)}
            </span>
          </div>
          <div>
            <span className={s.statLabel}>Sector Breach ETF Hedge</span>
            <span className={s.statValue}>
              {sheet.hedge_summary.sector_hedges.length > 0
                ? `${sheet.hedge_summary.sector_hedges[0].etf_trade.action} ${Math.abs(sheet.hedge_summary.sector_hedges[0].etf_trade.qty)} ${sheet.hedge_summary.sector_hedges[0].etf_trade.ticker}`
                : 'No Sector Breach'}
            </span>
            <span className={s.statSub}>
              {sheet.hedge_summary.sector_hedges.length > 0
                ? `${sheet.hedge_summary.sector_hedges[0].sector}: ${sheet.hedge_summary.sector_hedges[0].current_weight_pct.toFixed(2)}% → ${sheet.hedge_summary.sector_hedges[0].post_sector_weight_pct.toFixed(2)}%`
                : 'All sectors within limits'}
            </span>
          </div>
          <div>
            <span className={s.statLabel}>Drawdown Rule Status</span>
            <span className={s.statValue}>{sheet.hedge_summary.drawdown_status}</span>
            <span className={s.statSub}>Current DD: {dod.drawdown_today_pct.toFixed(2)}% from HWM</span>
          </div>
          <div>
            <span className={s.statLabel}>AI Model-Risk Status</span>
            <span className={s.statValue}>
              {mr.healthy_count} Healthy · {mr.degraded_count + mr.killed_count} Flagged
            </span>
            <span className={s.statSub}>
              Vol Bias: {mr.vol_bias_statistic.toFixed(3)} ({mr.vol_bias_status})
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

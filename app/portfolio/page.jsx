'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import styles from './portfolio.module.css'
import LimitsPanel from './LimitsPanel'
import PreTradeCheck from './PreTradeCheck'
import RiskHistoryPanel from './RiskHistoryPanel'
import VarPanel from './VarPanel'
import StressPanel from './StressPanel'
import LiquidityPanel from './LiquidityPanel'
import AttributionPanel from './AttributionPanel'
import { HedgePanel, ModelRiskPanel, TearSheetPanel } from './Phase4Panels'
import HeadroomChip from '../components/HeadroomChip'
import { notifyRiskChanged } from '../components/riskFetch'

export default function PortfolioPage() {
  const [portfolios, setPortfolios] = useState([])
  const [selectedPortfolioId, setSelectedPortfolioId] = useState(null)
  const [portfolioData, setPortfolioData] = useState(null)
  const [riskData, setRiskData] = useState(null)
  const [activeTab, setActiveTab] = useState('holdings') // 'holdings' | 'risk' | 'limits' | 'journal'
  const [limitsData, setLimitsData] = useState(null) // RSK-002
  const [preTrade, setPreTrade] = useState(null) // RSK-003 what-if result
  const [overrideReason, setOverrideReason] = useState('')
  const [riskRefresh, setRiskRefresh] = useState(0) // bumps RSK-004/005/006 panels after book changes
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showTradeModal, setShowTradeModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)

  // Form states
  const [newPortName, setNewPortName] = useState('')
  const [newPortCash, setNewPortCash] = useState('100000')
  const [tradeTicker, setTradeTicker] = useState('')
  const [tradeSide, setTradeSide] = useState('buy') // 'buy' | 'sell'
  const [tradeQty, setTradeQty] = useState('')
  const [tradePrice, setTradePrice] = useState('')
  const [tradeInvalidationPrice, setTradeInvalidationPrice] = useState('')
  const [tradeThesis, setTradeThesis] = useState('')
  const [tradeMethod, setTradeMethod] = useState('volatility target')
  const [importCsvText, setImportCsvText] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  useEffect(() => {
    loadPortfolios()
    // RSK-008 deep links from the breach drawer
    try {
      const q = new URLSearchParams(window.location.search)
      const pid = parseInt(q.get('pid'), 10)
      if (pid) setSelectedPortfolioId(pid)
      if (q.get('tab') === 'limits') setActiveTab('limits')
      if (q.get('trade') && q.get('ticker')) {
        setTradeSide(q.get('trade') === 'sell' ? 'sell' : 'buy')
        setTradeTicker(q.get('ticker').toUpperCase())
        if (q.get('qty')) setTradeQty(q.get('qty'))
        if (q.get('price')) setTradePrice(q.get('price'))
        setActiveTab('limits')
        setShowTradeModal(true)
      }
    } catch (e) { /* no query */ }
  }, [])

  useEffect(() => {
    if (selectedPortfolioId) {
      loadPortfolioDetail(selectedPortfolioId)
      loadPortfolioRisk(selectedPortfolioId)
      loadLimits(selectedPortfolioId)
    }
  }, [selectedPortfolioId])

  async function loadPortfolios() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/portfolios')
      if (!res.ok) throw new Error('Failed to load portfolios')
      const data = await res.json()
      setPortfolios(data)
      if (data && data.length > 0 && !selectedPortfolioId) {
        setSelectedPortfolioId(data[0].id)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadPortfolioDetail(id) {
    try {
      const res = await fetch(`/api/portfolios/${id}`)
      if (!res.ok) throw new Error('Failed to load portfolio details')
      const data = await res.json()
      setPortfolioData(data)
    } catch (err) {
      console.error(err)
    }
  }

  async function loadPortfolioRisk(id) {
    try {
      const res = await fetch(`/api/portfolios/${id}/risk`)
      if (!res.ok) return
      const data = await res.json()
      setRiskData(data.risk)
    } catch (err) {
      console.error(err)
    }
  }

  async function loadLimits(id) {
    try {
      const res = await fetch(`/api/portfolios/${id}/limits`)
      if (!res.ok) return
      setLimitsData(await res.json())
    } catch (err) {
      console.error(err)
    }
  }

  async function handleCreatePortfolio(e) {
    e.preventDefault()
    if (!newPortName.trim()) return
    setActionLoading(true)
    try {
      const res = await fetch('/api/portfolios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newPortName.trim(),
          cash: parseFloat(newPortCash) || 100000.0,
          benchmark: 'SPY'
        })
      })
      if (!res.ok) throw new Error('Failed to create portfolio')
      const created = await res.json()
      setShowCreateModal(false)
      setNewPortName('')
      await loadPortfolios()
      setSelectedPortfolioId(created.id)
    } catch (err) {
      alert(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  async function handleAddTrade(e) {
    e.preventDefault()
    if (!tradeTicker.trim() || !tradeQty || !tradePrice) return
    setActionLoading(true)
    try {
      const parsedQty = parseFloat(tradeQty)
      const signedQty = tradeSide === 'sell' ? -Math.abs(parsedQty) : Math.abs(parsedQty)
      const res = await fetch(`/api/portfolios/${selectedPortfolioId}/transactions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: tradeTicker.trim().toUpperCase(),
          qty: signedQty,
          price: parseFloat(tradePrice),
          thesis: tradeThesis.trim(),
          sizing_method: tradeMethod,
          invalidation_price: tradeInvalidationPrice ? parseFloat(tradeInvalidationPrice) : null,
          override_reason: overrideReason.trim() || null
        })
      })
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}))
        const d = errJson.detail
        throw new Error((d && typeof d === 'object' ? d.message : d) || 'Failed to record transaction')
      }
      setShowTradeModal(false)
      setTradeTicker('')
      setTradeQty('')
      setTradePrice('')
      setTradeThesis('')
      setTradeInvalidationPrice('')
      setTradeSide('buy')
      setOverrideReason('')
      setPreTrade(null)
      await loadPortfolioDetail(selectedPortfolioId)
      await loadPortfolioRisk(selectedPortfolioId)
      await loadLimits(selectedPortfolioId)
      setRiskRefresh((k) => k + 1)
      notifyRiskChanged()
    } catch (err) {
      alert(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  async function handleImportCsv(e) {
    e.preventDefault()
    if (!importCsvText.trim()) return
    setActionLoading(true)
    try {
      const res = await fetch(`/api/portfolios/${selectedPortfolioId}/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_content: importCsvText })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'CSV import failed')
      setShowImportModal(false)
      setImportCsvText('')
      alert(`Successfully imported ${data.imported_count} positions!`)
      await loadPortfolioDetail(selectedPortfolioId)
      await loadPortfolioRisk(selectedPortfolioId)
      await loadLimits(selectedPortfolioId)
      notifyRiskChanged()
    } catch (err) {
      alert(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  async function handleDeletePosition(ticker) {
    if (!confirm(`Liquidate and remove position ${ticker}?`)) return
    try {
      const res = await fetch(`/api/portfolios/${selectedPortfolioId}/positions/${ticker}`, {
        method: 'DELETE'
      })
      if (!res.ok) throw new Error('Failed to remove position')
      await loadPortfolioDetail(selectedPortfolioId)
      await loadPortfolioRisk(selectedPortfolioId)
      await loadLimits(selectedPortfolioId)
      notifyRiskChanged()
    } catch (err) {
      alert(err.message)
    }
  }

  const holdings = portfolioData?.holdings
  const positions = holdings?.positions || []
  const txs = portfolioData?.recent_transactions || []

  // Check sum of weights - computed from unrounded raw values to guarantee exactly 100.00% without rounding drift
  const totalWeight = holdings && holdings.nav > 0
    ? ((holdings.cash + positions.reduce((acc, p) => acc + (p.market_value || 0), 0)) / holdings.nav * 100.0)
    : 100.0
  const allLong = positions.length > 0 && positions.every(p => (p.side || 'long').toLowerCase() === 'long')

  return (
    <div className={styles.container}>
      {/* Header bar */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>
            <span>💼</span> Portfolio Workstation
          </h1>
          {portfolios.length > 0 && (
            <select
              className={styles.portfolioSelect}
              value={selectedPortfolioId || ''}
              onChange={(e) => setSelectedPortfolioId(Number(e.target.value))}
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} (${(p.nav || p.cash || 0).toLocaleString()})
                </option>
              ))}
            </select>
          )}
          <span className={styles.demoBadge}>Demo data</span>
        </div>

        <div className={styles.headerActions}>
          <button className={styles.btnSecondary} onClick={() => setShowCreateModal(true)}>
            + New portfolio
          </button>
          <button className={styles.btnSecondary} onClick={() => setShowImportModal(true)}>
            📥 Import CSV
          </button>
          <button className={styles.btnPrimary} onClick={() => setShowTradeModal(true)}>
            + Add trade
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--ink-3)' }}>
          Loading portfolio workstation...
        </div>
      ) : error ? (
        <div style={{ padding: '24px', background: 'var(--bear-tint)', color: 'var(--bear)', borderRadius: 'var(--r-panel)' }}>
          {error}
        </div>
      ) : (
        <>
          {/* Top Institutional Metrics Strip: 4x2 Clean Desktop Grid */}
          <div className={styles.metricsGrid}>
            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>Total NAV</span>
              <span className={styles.metricValue}>
                ${(holdings?.nav || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={`${styles.metricSubtext} ${holdings?.total_unrealized_pnl >= 0 ? styles.posChange : styles.negChange}`}>
                {holdings?.total_unrealized_pnl >= 0 ? '+' : ''}${holdings?.total_unrealized_pnl?.toLocaleString()} ({holdings?.total_unrealized_pnl_pct}%)
              </span>
            </div>

            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>Cash</span>
              <span className={styles.metricValue}>
                ${(holdings?.cash || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={styles.metricSubtext}>{holdings?.cash_weight_pct}% of NAV</span>
            </div>

            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>Gross / Net</span>
              <span className={styles.metricValue}>
                ${(holdings?.gross_exposure || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </span>
              <span className={styles.metricSubtext}>{holdings?.gross_exposure_pct}% exposure</span>
            </div>

            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>Holdings</span>
              <span className={styles.metricValue}>{positions.length}</span>
              <span className={styles.metricSubtext}>Across {Object.keys(holdings?.sector_breakdown || {}).length} sectors</span>
            </div>

            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>Portfolio Vol</span>
              <span className={styles.metricValue}>
                {riskData ? `${(riskData.portfolio_volatility * 100).toFixed(1)}%` : '—'}
              </span>
              <span className={styles.metricSubtext}>Annualized 252d</span>
            </div>

            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>Portfolio Beta</span>
              <span className={styles.metricValue}>
                {riskData ? riskData.portfolio_beta.toFixed(2) : '—'}
              </span>
              <span className={styles.metricSubtext}>vs SPY benchmark</span>
            </div>

            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>1-Day 95% VaR</span>
              <span className={`${styles.metricValue} styles.negChange`}>
                {riskData ? `${(riskData.var_95_1d * 100).toFixed(2)}%` : '—'}
              </span>
              <span className={styles.metricSubtext}>Historical 252d (see VaR tab)</span>
            </div>

            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>Effective Bets</span>
              <span className={styles.metricValue}>
                {riskData ? riskData.effective_bets : '—'}
              </span>
              <span className={styles.metricSubtext}>1 / HHI (of invested capital)</span>
            </div>
          </div>

          {/* Workstation Tabs */}
          <div className={styles.tabsBar} role="tablist">
            <button
              role="tab"
              aria-selected={activeTab === 'holdings'}
              className={`${styles.tabBtn} ${activeTab === 'holdings' ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveTab('holdings')}
            >
              Holdings ({positions.length})
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'risk'}
              className={`${styles.tabBtn} ${activeTab === 'risk' ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveTab('risk')}
            >
              Risk Decomposition
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'limits'}
              className={`${styles.tabBtn} ${activeTab === 'limits' ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveTab('limits')}
            >
              Limits
              {limitsData?.summary?.hard_breaches > 0 && (
                <span
                  style={{ marginLeft: 6, padding: '1px 7px', borderRadius: 'var(--r-chip)', background: 'var(--bear-tint)', color: 'var(--bear)', fontSize: 'var(--fs-xs)', fontWeight: 700 }}
                >
                  {limitsData.summary.hard_breaches} hard
                </span>
              )}
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'history'}
              className={`${styles.tabBtn} ${activeTab === 'history' ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveTab('history')}
            >
              Risk History
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'var'}
              className={`${styles.tabBtn} ${activeTab === 'var' ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveTab('var')}
            >
              VaR &amp; Backtest
            </button>
            {[
              ['stress', 'Stress'],
              ['liquidity', 'Liquidity'],
              ['attribution', 'Attribution'],
              ['hedging', 'Hedging'],
              ['model-risk', 'Model Risk'],
              ['tear-sheet', 'Tear Sheet'],
            ].map(([k, label]) => (
              <button
                key={k}
                role="tab"
                aria-selected={activeTab === k}
                className={`${styles.tabBtn} ${activeTab === k ? styles.tabBtnActive : ''}`}
                onClick={() => setActiveTab(k)}
              >
                {label}
              </button>
            ))}
            <button
              role="tab"
              aria-selected={activeTab === 'journal'}
              className={`${styles.tabBtn} ${activeTab === 'journal' ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveTab('journal')}
            >
              Trade Journal ({txs.length})
            </button>
          </div>

          {/* TAB 1: HOLDINGS TABLE */}
          {activeTab === 'holdings' && (
            <div className={styles.panel}>
              <div className={styles.tableWrapper}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th className={styles.stickyCol}>Symbol</th>
                      <th>Sector</th>
                      {!allLong && <th>Side</th>}
                      <th>Quantity</th>
                      <th>Avg Cost</th>
                      <th>Price</th>
                      <th>Market Value</th>
                      <th>Weight %</th>
                      <th>Day P&L</th>
                      <th>Unrealized P&L</th>
                      <th>Verdict</th>
                      <th>Conviction</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos) => {
                      const isUp = pos.unrealized_pnl >= 0
                      const dayUp = pos.day_pnl >= 0
                      const recClass =
                        pos.recommendation === 'buy'
                          ? styles.pillBuy
                          : pos.recommendation === 'sell'
                          ? styles.pillSell
                          : styles.pillHold
                      return (
                        <tr key={pos.id || pos.ticker}>
                          <td className={styles.stickyCol}>
                            <div className={styles.tickerCell}>
                              <Link href={`/analysis/${pos.ticker}`} className={styles.tickerLink}>
                                {pos.ticker}
                              </Link>
                              <span className={styles.subText}>{pos.company_name}</span>
                            </div>
                          </td>
                          <td>
                            <span className={styles.subText}>{pos.sector}</span>
                          </td>
                          {!allLong && (
                            <td>
                              <span style={{ textTransform: 'uppercase', fontSize: 'var(--fs-xs)', fontWeight: 700 }}>
                                {pos.side}
                              </span>
                            </td>
                          )}
                          <td className={styles.figure}>{pos.quantity}</td>
                          <td className={styles.figure}>${pos.avg_cost?.toFixed(2)}</td>
                          <td className={styles.figure}>${pos.current_price?.toFixed(2)}</td>
                          <td className={styles.figure}>${pos.market_value?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                          <td className={styles.figure}>
                            <strong>{pos.weight_pct}%</strong>
                          </td>
                          <td className={`${styles.figure} ${dayUp ? styles.posChange : styles.negChange}`}>
                            {dayUp ? '+' : ''}${pos.day_pnl?.toFixed(2)} ({dayUp ? '+' : ''}{pos.day_change_pct}%)
                          </td>
                          <td className={`${styles.figure} ${isUp ? styles.posChange : styles.negChange}`}>
                            {isUp ? '+' : ''}${pos.unrealized_pnl?.toLocaleString(undefined, { minimumFractionDigits: 2 })} ({isUp ? '+' : ''}{pos.unrealized_pnl_pct}%)
                          </td>
                          <td>
                            <span className={`${styles.pill} ${recClass}`}>
                              {pos.recommendation}
                            </span>
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <span className={styles.figure}>{pos.conviction}/10</span>
                            </div>
                          </td>
                          <td>
                            <button
                              className={styles.actionBtn}
                              title={`Liquidate ${pos.ticker}`}
                              onClick={() => handleDeletePosition(pos.ticker)}
                            >
                              Exit
                            </button>
                          </td>
                        </tr>
                      )
                    })}

                    {/* Cash row */}
                    <tr className={styles.cashRow}>
                      <td colSpan={allLong ? 2 : 3} className={styles.stickyCol}>
                        <strong>Cash & Liquidity (USD)</strong>
                      </td>
                      <td>—</td>
                      <td>—</td>
                      <td>$1.00</td>
                      <td className={styles.figure}>${holdings?.cash?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                      <td className={styles.figure}>
                        <strong>{holdings?.cash_weight_pct}%</strong>
                      </td>
                      <td>—</td>
                      <td>—</td>
                      <td colSpan={3}>
                        <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                          Total Allocation: <strong>{totalWeight.toFixed(2)}%</strong>
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 2: RISK DECOMPOSITION */}
          {activeTab === 'risk' && (
            <div className={styles.panel}>
              <div className={styles.riskGrid}>
                {/* Risk Contribution vs Capital Weight */}
                <div className={styles.cardSection}>
                  <h3 className={styles.sectionHeading}>
                    <span>Euler Risk Contribution vs Capital Weight</span>
                    <span className={styles.subText}>Σ RC% = 100.0%</span>
                  </h3>
                  <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', marginBottom: '16px' }}>
                    Compares % of Capital (Ink) against % of Portfolio Risk (Brand). Names with Risk % &gt; Capital % drive outsized volatility.
                  </p>

                  <div className={styles.rcList}>
                    {riskData?.risk_contributions?.map((rc) => (
                      <div key={rc.ticker} className={styles.rcItem}>
                        <div className={styles.rcHeader}>
                          <span style={{ fontFamily: 'var(--font-figure)', fontWeight: 700 }}>
                            {rc.ticker} ({rc.sector})
                          </span>
                          <span>
                            Capital: <strong style={{ color: 'var(--ink)' }}>{rc.capital_weight_pct}%</strong> | Risk: <strong style={{ color: 'var(--brand)' }}>{rc.risk_contribution_pct}%</strong>
                          </span>
                        </div>
                        <div className={styles.barTrack}>
                          <div className={styles.barCapital} style={{ width: `${Math.min(100, rc.capital_weight_pct * 2)}%` }} />
                          <div className={styles.barRisk} style={{ width: `${Math.min(100, rc.risk_contribution_pct * 2)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Risk Concentration & Heatmap */}
                <div className={styles.cardSection}>
                  <h3 className={styles.sectionHeading}>Holdings Correlation Matrix</h3>
                  <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', marginBottom: '8px' }}>
                    Ledoit-Wolf shrunk covariance correlations (252-day log returns).
                  </p>

                  <div className={styles.heatmapWrapper}>
                    {riskData?.correlation_matrix ? (
                      <table className={styles.heatmapTable}>
                        <thead>
                          <tr>
                            <th className={styles.heatmapHeader}></th>
                            {riskData.correlation_matrix.tickers.map((t) => (
                              <th key={t} className={styles.heatmapHeader}>{t}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {riskData.correlation_matrix.tickers.map((t1, rIdx) => (
                            <tr key={t1}>
                              <td className={styles.heatmapHeader}>{t1}</td>
                              {riskData.correlation_matrix.matrix[rIdx].map((val, cIdx) => {
                                const opacity = Math.abs(val)
                                const bg = val >= 0 ? `rgba(239, 68, 68, ${opacity * 0.7})` : `rgba(59, 130, 246, ${opacity * 0.7})`
                                return (
                                  <td
                                    key={cIdx}
                                    className={styles.heatmapCell}
                                    style={{ background: bg, color: opacity > 0.4 ? '#fff' : 'var(--ink)' }}
                                    title={`${t1} vs ${riskData.correlation_matrix.tickers[cIdx]}: ${val.toFixed(3)}`}
                                  >
                                    {val.toFixed(2)}
                                  </td>
                                )
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <p className={styles.subText}>No correlation matrix available.</p>
                    )}
                  </div>

                  <div style={{ marginTop: '20px', borderTop: '1px solid var(--rule)', paddingTop: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--fs-xs)' }}>
                      <span>HHI Concentration: <strong>{riskData?.hhi}</strong> (of invested capital)</span>
                      <span>Top 5 Weight: <strong>{riskData?.top5_concentration_pct}%</strong></span>
                      <span>97.5% CVaR: <strong>{(riskData?.cvar_975_1d * 100).toFixed(2)}%</strong></span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB: RISK LIMITS (RSK-002 / RSK-003) */}
          {activeTab === 'limits' && (
            <LimitsPanel
              portfolioId={selectedPortfolioId}
              limitsData={limitsData}
              onLimitsChanged={(d) => { setLimitsData(d); notifyRiskChanged() }}
            />
          )}

          {/* TABS: RSK-004 risk history, RSK-005/006 VaR & backtest */}
          {activeTab === 'history' && <RiskHistoryPanel portfolioId={selectedPortfolioId} refreshKey={riskRefresh} />}
          {activeTab === 'var' && <VarPanel portfolioId={selectedPortfolioId} refreshKey={riskRefresh} />}
          {/* TABS: RSK-009 stress, RSK-010 liquidity, RSK-011 attribution */}
          {activeTab === 'stress' && <StressPanel portfolioId={selectedPortfolioId} refreshKey={riskRefresh} />}
          {activeTab === 'liquidity' && <LiquidityPanel portfolioId={selectedPortfolioId} refreshKey={riskRefresh} />}
          {activeTab === 'attribution' && <AttributionPanel portfolioId={selectedPortfolioId} refreshKey={riskRefresh} />}
          {/* TABS: RSK-012 hedging, RSK-013 model risk, RSK-014 tear sheet */}
          {activeTab === 'hedging' && (
            <HedgePanel
              portfolioId={selectedPortfolioId}
              refreshKey={riskRefresh}
              onPrefillTrade={(t) => {
                setTradeTicker(t.ticker)
                setTradeSide(t.qty < 0 ? 'sell' : 'buy')
                setTradeQty(String(Math.abs(t.qty)))
                setTradePrice(String(t.price))
                setShowTradeModal(true)
              }}
            />
          )}
          {activeTab === 'model-risk' && <ModelRiskPanel portfolioId={selectedPortfolioId} refreshKey={riskRefresh} />}
          {activeTab === 'tear-sheet' && <TearSheetPanel portfolioId={selectedPortfolioId} refreshKey={riskRefresh} />}

          {/* TAB 3: TRADE JOURNAL */}
          {activeTab === 'journal' && (
            <div className={styles.panel}>
              <div className={styles.tableWrapper}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Symbol</th>
                      <th>Shares</th>
                      <th>Execution Price</th>
                      <th>Total Value</th>
                      <th>Sizing Model</th>
                      <th>Investment Thesis / Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {txs.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ textAlign: 'center', color: 'var(--ink-3)', padding: '32px' }}>
                          No transactions recorded yet.
                        </td>
                      </tr>
                    ) : (
                      txs.map((t) => (
                        <tr key={t.id}>
                          <td className={styles.subText}>{new Date(t.ts).toLocaleString()}</td>
                          <td>
                            <strong style={{ fontFamily: 'var(--font-figure)' }}>{t.ticker}</strong>
                          </td>
                          <td className={`${styles.figure} ${t.qty >= 0 ? styles.posChange : styles.negChange}`}>
                            {t.qty > 0 ? `+${t.qty}` : t.qty}
                          </td>
                          <td className={styles.figure}>${t.price.toFixed(2)}</td>
                          <td className={styles.figure}>${Math.abs(t.qty * t.price).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                          <td>
                            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)' }}>
                              {t.sizing_method || 'manual'}
                            </span>
                          </td>
                          <td>
                            <div style={{ fontSize: 'var(--fs-xs)' }}>
                              <strong>{t.thesis || t.note}</strong>
                              {t.invalidation_price && (
                                <span style={{ marginLeft: '8px', color: 'var(--bear)' }}>
                                  Stop: ${t.invalidation_price}
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* CREATE PORTFOLIO MODAL */}
      {showCreateModal && (
        <div className={styles.modalOverlay} onClick={() => setShowCreateModal(false)}>
          <div 
            className={styles.modalContent} 
            role="dialog" 
            aria-modal="true" 
            aria-labelledby="create-portfolio-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="create-portfolio-title" className={styles.modalTitle}>Create New Portfolio</h2>
            <form onSubmit={handleCreatePortfolio}>
              <div className={styles.formGroup}>
                <label htmlFor="create-port-name" className={styles.formLabel}>Portfolio Name</label>
                <input
                  id="create-port-name"
                  type="text"
                  required
                  placeholder="e.g. Long-Short Tech Alpha"
                  className={styles.formInput}
                  value={newPortName}
                  onChange={(e) => setNewPortName(e.target.value)}
                />
              </div>

              <div className={styles.formGroup} style={{ marginTop: '12px' }}>
                <label htmlFor="create-port-cash" className={styles.formLabel}>Initial Cash ($)</label>
                <input
                  id="create-port-cash"
                  type="number"
                  required
                  className={styles.formInput}
                  value={newPortCash}
                  onChange={(e) => setNewPortCash(e.target.value)}
                />
              </div>

              <div className={styles.modalActions}>
                <button type="button" className={styles.btnSecondary} onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className={styles.btnPrimary} disabled={actionLoading}>
                  {actionLoading ? 'Creating...' : 'Create Portfolio'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ADD TRADE MODAL */}
      {showTradeModal && (
        <div className={styles.modalOverlay} onClick={() => setShowTradeModal(false)}>
          <div 
            className={styles.modalContent} 
            role="dialog" 
            aria-modal="true" 
            aria-labelledby="trade-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="trade-modal-title" className={styles.modalTitle}>Record Portfolio Trade</h2>
            <form onSubmit={handleAddTrade}>
              {/* Order Side Segmented Toggle */}
              <div className={styles.formGroup}>
                <label id="order-side-label" className={styles.formLabel}>Order Side</label>
                <div 
                  className={styles.segmentedToggle} 
                  role="radiogroup" 
                  aria-labelledby="order-side-label"
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={tradeSide === 'buy'}
                    className={`${styles.segmentBtn} ${tradeSide === 'buy' ? styles.segmentBtnBuyActive : ''}`}
                    onClick={() => setTradeSide('buy')}
                  >
                    BUY (Open / Add)
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={tradeSide === 'sell'}
                    className={`${styles.segmentBtn} ${tradeSide === 'sell' ? styles.segmentBtnSellActive : ''}`}
                    onClick={() => setTradeSide('sell')}
                  >
                    SELL (Close / Reduce)
                  </button>
                </div>
              </div>

              <div className={styles.formGroup} style={{ marginTop: '12px' }}>
                <label htmlFor="trade-ticker" className={styles.formLabel}>Ticker Symbol</label>
                <input
                  id="trade-ticker"
                  type="text"
                  required
                  placeholder="e.g. AAPL"
                  className={styles.formInput}
                  value={tradeTicker}
                  onChange={(e) => setTradeTicker(e.target.value.toUpperCase())}
                />
              </div>

              <div className={styles.formGrid2}>
                <div className={styles.formGroup}>
                  <label htmlFor="trade-qty" className={styles.formLabel}>Shares Quantity</label>
                  <input
                    id="trade-qty"
                    type="number"
                    step="any"
                    required
                    placeholder="e.g. 50"
                    className={styles.formInput}
                    value={tradeQty}
                    onChange={(e) => setTradeQty(e.target.value)}
                  />
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="trade-price" className={styles.formLabel}>Price ($)</label>
                  <input
                    id="trade-price"
                    type="number"
                    step="any"
                    required
                    placeholder="e.g. 228.50"
                    className={styles.formInput}
                    value={tradePrice}
                    onChange={(e) => setTradePrice(e.target.value)}
                  />
                </div>
              </div>

              <div className={styles.formGroup} style={{ marginTop: '12px' }}>
                <label htmlFor="trade-inval" className={styles.formLabel}>Invalidation Price ($ Stop Level)</label>
                <input
                  id="trade-inval"
                  type="number"
                  step="any"
                  placeholder="e.g. 210.00 (optional)"
                  className={styles.formInput}
                  value={tradeInvalidationPrice}
                  onChange={(e) => setTradeInvalidationPrice(e.target.value)}
                />
              </div>

              <div className={styles.formGroup} style={{ marginTop: '12px' }}>
                <label htmlFor="trade-method" className={styles.formLabel}>Sizing Methodology</label>
                <select
                  id="trade-method"
                  className={styles.formInput}
                  value={tradeMethod}
                  onChange={(e) => setTradeMethod(e.target.value)}
                >
                  <option value="volatility target">Volatility Target Model</option>
                  <option value="conviction scaled">Conviction-Scaled Risk Budget</option>
                  <option value="half kelly">Half-Kelly Criterion</option>
                  <option value="manual">Discretionary / Manual</option>
                </select>
              </div>

              <div className={styles.formGroup} style={{ marginTop: '12px' }}>
                <label htmlFor="trade-thesis" className={styles.formLabel}>Investment Thesis</label>
                <input
                  id="trade-thesis"
                  type="text"
                  placeholder="e.g. AI product cycle momentum"
                  className={styles.formInput}
                  value={tradeThesis}
                  onChange={(e) => setTradeThesis(e.target.value)}
                />
              </div>

              <HeadroomChip
                portfolioId={selectedPortfolioId}
                ticker={tradeTicker}
                side={tradeSide}
                onUseMax={(n) => setTradeQty(String(n))}
              />

              <PreTradeCheck
                portfolioId={selectedPortfolioId}
                ticker={tradeTicker.trim().toUpperCase()}
                qty={tradeQty ? String(tradeSide === 'sell' ? -Math.abs(parseFloat(tradeQty)) : Math.abs(parseFloat(tradeQty))) : ''}
                price={tradePrice}
                overrideReason={overrideReason}
                setOverrideReason={setOverrideReason}
                onResult={setPreTrade}
              />

              <div className={styles.modalActions}>
                <button type="button" className={styles.btnSecondary} onClick={() => setShowTradeModal(false)}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className={styles.btnPrimary}
                  disabled={actionLoading || (preTrade?.requires_override && overrideReason.trim().length < 10)}
                >
                  {actionLoading ? 'Recording...' : preTrade?.requires_override ? 'Override & Execute' : tradeSide === 'sell' ? 'Execute Sell' : 'Execute & Log'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CSV IMPORT MODAL */}
      {showImportModal && (
        <div className={styles.modalOverlay} onClick={() => setShowImportModal(false)}>
          <div 
            className={styles.modalContent} 
            role="dialog" 
            aria-modal="true" 
            aria-labelledby="import-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="import-modal-title" className={styles.modalTitle}>Batch Import Positions via CSV</h2>
            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', background: 'var(--surface-2)', padding: '8px 12px', borderRadius: 'var(--r-control)', border: '1px solid var(--rule)', margin: '4px 0' }}>
              Existing holdings import: balances positions without debiting cash.
            </p>
            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
              Enter rows formatted as: <code>ticker,quantity,avg_cost</code>. Delimiters can be comma, tab, or semicolon.
            </p>
            <form onSubmit={handleImportCsv}>
              <div className={styles.formGroup}>
                <label htmlFor="import-csv-text" className={styles.formLabel}>CSV Data</label>
                <textarea
                  id="import-csv-text"
                  rows={6}
                  required
                  placeholder={"AAPL,80,215.00\nMSFT,45,410.00\nNVDA,100,125.00\nJPM,50,210.00"}
                  className={styles.formTextarea}
                  value={importCsvText}
                  onChange={(e) => setImportCsvText(e.target.value)}
                />
              </div>

              <div className={styles.modalActions}>
                <button type="button" className={styles.btnSecondary} onClick={() => setShowImportModal(false)}>
                  Cancel
                </button>
                <button type="submit" className={styles.btnPrimary} disabled={actionLoading}>
                  {actionLoading ? 'Importing...' : 'Import Positions'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

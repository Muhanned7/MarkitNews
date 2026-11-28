'use client'
import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { MOCK_CONTRADICTION_SCENARIOS } from '../../lib/mockContradictions'
import styles from './ContradictionRadar.module.css'

const LIVE_TICKER_PRESETS = ['AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'AMD']

export default function ContradictionRadar({
  ticker = null,
  liveData = null,
  defaultScenarioId = 'meridian-nickel',
}) {
  const { user } = useAuth()
  const isProUser = Boolean(user?.is_admin || user?.plan_code === 'pro')
  const [mode, setMode] = useState(liveData || isProUser ? 'live' : 'demo') // 'live' | 'demo'
  const [activeTicker, setActiveTicker] = useState((ticker || 'AAPL').toUpperCase())
  const [customTickerInput, setCustomTickerInput] = useState('')
  const [watchlistTickers, setWatchlistTickers] = useState([])
  const [liveReport, setLiveReport] = useState(liveData || null)
  const [loadingLive, setLoadingLive] = useState(!liveData)
  const [liveError, setLiveError] = useState(null)
  const [selectedDemoId, setSelectedDemoId] = useState(defaultScenarioId)
  const [severityFilter, setSeverityFilter] = useState('all')

  const fetchLiveContradictions = useCallback(async (sym, forceRefresh = false) => {
    const cleanSym = (sym || 'AAPL').trim().toUpperCase()
    if (!cleanSym) return
    setLoadingLive(true)
    setLiveError(null)
    try {
      const res = await fetch(
        `/api/contradictions/${encodeURIComponent(cleanSym)}${forceRefresh ? '?refresh=1' : ''}`,
        { credentials: 'include', cache: 'no-store' }
      )
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `Could not load live Contradiction Radar for ${cleanSym}`)
      }
      const data = await res.json()
      setLiveReport(data)
    } catch (e) {
      setLiveError(e.message)
    } finally {
      setLoadingLive(false)
    }
  }, [])

  useEffect(() => {
    if (ticker) {
      setActiveTicker(ticker.toUpperCase())
    }
  }, [ticker])

  useEffect(() => {
    if (liveData && liveData.ticker?.toUpperCase() === activeTicker) {
      setLiveReport(liveData)
      setLoadingLive(false)
      return
    }
    if (!isProUser) {
      setMode('demo')
      setLoadingLive(false)
      return
    }
    if (mode === 'live') {
      fetchLiveContradictions(activeTicker, false)
    }
  }, [activeTicker, mode, liveData, isProUser, fetchLiveContradictions])

  useEffect(() => {
    if (ticker) return
    fetch('/api/watchlist', { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        const syms = (d?.tickers || [])
          .map(t => (typeof t === 'string' ? t : t.ticker)?.toUpperCase())
          .filter(Boolean)
        setWatchlistTickers(syms)
        if (syms.length > 0 && !ticker) {
          setActiveTicker(syms[0])
        }
      })
      .catch(() => {})
  }, [ticker])

  const tickerPills = [...new Set([...watchlistTickers, ...LIVE_TICKER_PRESETS])].slice(0, 8)

  const scenario =
    mode === 'live' && liveReport
      ? liveReport
      : MOCK_CONTRADICTION_SCENARIOS[selectedDemoId] || MOCK_CONTRADICTION_SCENARIOS['meridian-nickel']

  const filteredContradictions = (scenario?.contradictions || []).filter(item => {
    if (severityFilter === 'all') return true
    return item.severity === severityFilter
  })

  function handleCustomSearch(e) {
    e.preventDefault()
    const clean = customTickerInput.trim().toUpperCase()
    if (!clean) return
    setMode('live')
    setActiveTicker(clean)
    setCustomTickerInput('')
  }

  return (
    <div className={styles.container}>
      {/* Top Header & Live Ticker / Scenario Selection */}
      <div className={styles.header}>
        <div>
          <div className={styles.eyebrow}>
            <span className={styles.pingDotWrapper}>
              <span className={styles.pingDotWave}></span>
              <span className={styles.pingDotSolid}></span>
            </span>
            <span>
              {mode === 'live'
                ? `Contradiction Radar · Live Multi-Agent & Footprint Output (${activeTicker})`
                : 'Contradiction Radar · Fictional Illustrative Scenarios'}
            </span>
          </div>
          <h2 className={styles.title}>Contradiction Radar</h2>
          <p className={styles.subtitle}>
            Triangulating Western financial wires, localized on-ground hub press, corporate SEC 10-K/8-K disclosures, and Tier-1 supplier feeds with Temporal Regime arbitration.
          </p>
        </div>

        {/* Mode & Ticker Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => {
                if (!isProUser) {
                  if (typeof window !== 'undefined') {
                    window.dispatchEvent(
                      new CustomEvent('open-upgrade-modal', {
                        detail: {
                          message:
                            'Live Contradiction Radar & Epistemic Arbiter inference is a Pro Package capability ($19/mo). Free accounts can explore the Illustrative Demos without consuming backend LLM tokens.',
                        },
                      })
                    )
                  }
                  return
                }
                setMode('live')
              }}
              className={`${styles.scenarioBtn} ${mode === 'live' ? styles.scenarioBtnActive : ''}`}
            >
              {isProUser ? '⚡ Live Agent Output' : '🔒 Live Agent Output (Pro)'}
            </button>
            <button
              type="button"
              onClick={() => setMode('demo')}
              className={`${styles.scenarioBtn} ${mode === 'demo' ? styles.scenarioBtnActive : ''}`}
            >
              🧪 Illustrative Demos
            </button>
            {mode === 'live' && (
              <button
                type="button"
                onClick={() => fetchLiveContradictions(activeTicker, true)}
                className={styles.scenarioBtn}
                disabled={loadingLive}
                title="Re-run live Tri-Perspective feed mesh & Epistemic Arbiter"
              >
                {loadingLive ? 'Refreshing…' : '↻ Refresh Live'}
              </button>
            )}
          </div>

          {mode === 'live' ? (
            <div className={styles.scenarioSwitcher} style={{ alignItems: 'center' }}>
              {!ticker &&
                tickerPills.map(sym => (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => setActiveTicker(sym)}
                    className={`${styles.scenarioBtn} ${activeTicker === sym ? styles.scenarioBtnActive : ''}`}
                  >
                    {watchlistTickers.includes(sym) ? `★ ${sym}` : sym}
                  </button>
                ))}
              {!ticker && (
                <form onSubmit={handleCustomSearch} style={{ display: 'inline-flex', gap: '4px' }}>
                  <input
                    type="text"
                    placeholder="Ticker..."
                    value={customTickerInput}
                    onChange={e => setCustomTickerInput(e.target.value)}
                    style={{
                      width: '84px',
                      padding: '4px 8px',
                      borderRadius: 'var(--r-control)',
                      border: '1px solid var(--rule)',
                      background: 'var(--surface-2)',
                      color: 'var(--ink)',
                      fontSize: 'var(--fs-xs)',
                    }}
                  />
                  <button type="submit" className={styles.scenarioBtn}>
                    Go
                  </button>
                </form>
              )}
            </div>
          ) : (
            <div className={styles.scenarioSwitcher}>
              {Object.values(MOCK_CONTRADICTION_SCENARIOS).map(item => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedDemoId(item.id)}
                  className={`${styles.scenarioBtn} ${selectedDemoId === item.id ? styles.scenarioBtnActive : ''}`}
                >
                  {item.ticker}: {item.company.split(' ')[0]}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {mode === 'live' && loadingLive ? (
        <div
          style={{
            padding: '48px 24px',
            textAlign: 'center',
            background: 'var(--surface)',
            border: '1px solid var(--rule)',
            borderRadius: 'var(--r-panel)',
            color: 'var(--ink-2)',
            marginBottom: '24px',
          }}
        >
          <div style={{ fontWeight: 700, fontSize: 'var(--fs-md)', marginBottom: '6px' }}>
            Synthesizing Live Tri-Perspective Feeds &amp; SEC 10-K Footprint for {activeTicker}…
          </div>
          <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
            Resolving physical operational hubs, Tier-1 suppliers, localized regional press, and Temporal Regimes (ACTIVE_SHOCK vs. RECOVERY_LAG vs. HISTORICAL_STRUCTURAL).
          </div>
        </div>
      ) : mode === 'live' && liveError && !liveReport ? (
        <div
          style={{
            padding: '20px',
            borderRadius: 'var(--r-panel)',
            background: 'var(--bear-tint)',
            color: 'var(--bear)',
            marginBottom: '24px',
            fontWeight: 600,
          }}
        >
          {liveError}
        </div>
      ) : (
        <>
          {/* Verified Corporate Footprint & Supplier Grounding Strip (Live Mode) */}
          {mode === 'live' && (scenario?.footprint_hubs?.length > 0 || scenario?.supplier_watch?.length > 0) && (
            <div
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--rule)',
                borderRadius: 'var(--r-panel)',
                padding: '16px 20px',
                marginBottom: '20px',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '16px',
              }}
            >
              <div>
                <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 700, color: 'var(--ink-3)', textTransform: 'uppercase', marginBottom: '8px' }}>
                  🏭 Verified Physical Hubs Monitored ({scenario.footprint_hubs?.length || 0})
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {(scenario.footprint_hubs || []).map((h, i) => (
                    <a
                      key={i}
                      href={h.source_url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={h.evidence_quote || h.facility_type}
                      style={{
                        padding: '4px 10px',
                        borderRadius: 'var(--r-chip)',
                        background: 'var(--surface-2)',
                        border: '1px solid var(--rule)',
                        color: 'var(--ink)',
                        fontSize: 'var(--fs-xs)',
                        fontWeight: 600,
                        textDecoration: 'none',
                      }}
                    >
                      {h.hub_name} ({h.country_code}) ↗
                    </a>
                  ))}
                </div>
              </div>

              <div>
                <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 700, color: 'var(--ink-3)', textTransform: 'uppercase', marginBottom: '8px' }}>
                  🔗 Critical Tier-1 Suppliers Tracked ({scenario.supplier_watch?.length || 0})
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {(scenario.supplier_watch || []).map((s, i) => (
                    <a
                      key={i}
                      href={s.source_url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={s.evidence_quote || 'Verified Tier-1 Supplier'}
                      style={{
                        padding: '4px 10px',
                        borderRadius: 'var(--r-chip)',
                        background: 'var(--brand-tint)',
                        border: '1px solid var(--brand)',
                        color: 'var(--brand-ink)',
                        fontSize: 'var(--fs-xs)',
                        fontWeight: 700,
                        textDecoration: 'none',
                      }}
                    >
                      {s.supplier} ↗
                    </a>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Active Story Overview Banner */}
          <div className={styles.storyBanner}>
            <div className={styles.storyMeta}>
              <div className={styles.storyMetaLeft}>
                <span
                  className={`${styles.severityChip} ${
                    scenario.severity === 'critical'
                      ? styles.severityCritical
                      : scenario.severity === 'high'
                      ? styles.severityHigh
                      : styles.severityModerate
                  }`}
                >
                  {scenario.severity} Discrepancy
                </span>
                <span className={styles.storyTarget}>
                  Target: <strong>{scenario.company}</strong> ({scenario.ticker})
                </span>
                {scenario._evaluation?.grade && (
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: 'var(--r-chip)',
                      background: 'var(--bull-tint)',
                      color: 'var(--bull)',
                      fontSize: 'var(--fs-xs)',
                      fontWeight: 700,
                    }}
                  >
                    Grade {scenario._evaluation.grade} ({scenario._evaluation.overall_quality_score})
                  </span>
                )}
              </div>
              <span className={styles.storyDate}>Detected: {scenario.date}</span>
            </div>
            <h3 className={styles.storyTitle}>{scenario.eventTitle}</h3>
            <p className={styles.storySummary}>{scenario.summary}</p>
          </div>

          {/* 3-Column Comparative Perspective Cards */}
          <div className={styles.perspectivesGrid}>
            {/* 1. Western Financial Media */}
            <div className={`${styles.tierCard} ${styles.tierCard1}`}>
              <div>
                <div className={styles.tierHeader}>
                  <span className={styles.tierTitle}>
                    <span className={`${styles.tierDot} ${styles.tierDot1}`}></span>
                    Tier 1: Western Financial Media
                  </span>
                  <span className={styles.tierChip}>
                    {scenario.perspectives.western_media.temporal_regime || 'Macro Wire'}
                  </span>
                </div>

                <p className={styles.tierSource}>
                  Source: <strong>{scenario.perspectives.western_media.source}</strong>
                </p>

                <blockquote className={styles.quoteBox}>
                  {scenario.perspectives.western_media.url ? (
                    <a
                      href={scenario.perspectives.western_media.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'inherit', textDecoration: 'none' }}
                    >
                      &ldquo;{scenario.perspectives.western_media.headline}&rdquo; ↗
                    </a>
                  ) : (
                    <>&ldquo;{scenario.perspectives.western_media.headline}&rdquo;</>
                  )}
                </blockquote>

                <p className={styles.biasBox}>
                  <strong style={{ color: 'var(--bear)' }}>Bias Profile:</strong>{' '}
                  {scenario.perspectives.western_media.biasProfile}
                </p>

                <div>
                  <p className={styles.claimsHeader}>Reported Claims:</p>
                  <div className={styles.claimsList}>
                    {scenario.perspectives.western_media.claims.map((claim, idx) => (
                      <div key={idx} className={styles.claimItem}>
                        <span className={styles.claimMarker1}>✕</span>
                        <span>{claim}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className={styles.tierFooter}>Market Lens: Global Financial Wire Consensus</div>
            </div>

            {/* 2. Local / Regional Ground-Truth Press */}
            <div className={`${styles.tierCard} ${styles.tierCard2}`}>
              <div>
                <div className={styles.tierHeader}>
                  <span className={styles.tierTitle}>
                    <span className={`${styles.tierDot} ${styles.tierDot2}`}></span>
                    Tier 2: Local &amp; Regional Press
                  </span>
                  <span className={styles.tierChip}>
                    {scenario.perspectives.local_media.temporal_regime || 'Ground Reality'}
                  </span>
                </div>

                <p className={styles.tierSource}>
                  Source: <strong>{scenario.perspectives.local_media.source}</strong>
                </p>

                <blockquote className={styles.quoteBox}>
                  {scenario.perspectives.local_media.url ? (
                    <a
                      href={scenario.perspectives.local_media.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'inherit', textDecoration: 'none' }}
                    >
                      &ldquo;{scenario.perspectives.local_media.headline}&rdquo; ↗
                    </a>
                  ) : (
                    <>&ldquo;{scenario.perspectives.local_media.headline}&rdquo;</>
                  )}
                </blockquote>

                <p className={styles.biasBox}>
                  <strong style={{ color: 'var(--bull)' }}>Bias Profile:</strong>{' '}
                  {scenario.perspectives.local_media.biasProfile}
                </p>

                <div>
                  <p className={styles.claimsHeader}>Reported Claims:</p>
                  <div className={styles.claimsList}>
                    {scenario.perspectives.local_media.claims.map((claim, idx) => (
                      <div key={idx} className={styles.claimItem}>
                        <span className={styles.claimMarker2}>✓</span>
                        <span>{claim}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className={styles.tierFooter}>Ground Lens: Physical Hub &amp; Local Operations</div>
            </div>

            {/* 3. Corporate PR & Disclosures */}
            <div className={`${styles.tierCard} ${styles.tierCard3}`}>
              <div>
                <div className={styles.tierHeader}>
                  <span className={styles.tierTitle}>
                    <span className={`${styles.tierDot} ${styles.tierDot3}`}></span>
                    Tier 3: Corporate PR &amp; SEC 8-K
                  </span>
                  <span className={styles.tierChip}>
                    {scenario.perspectives.corporate_pr.temporal_regime || 'Official Filing'}
                  </span>
                </div>

                <p className={styles.tierSource}>
                  Source: <strong>{scenario.perspectives.corporate_pr.source}</strong>
                </p>

                <blockquote className={styles.quoteBox}>
                  {scenario.perspectives.corporate_pr.url ? (
                    <a
                      href={scenario.perspectives.corporate_pr.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'inherit', textDecoration: 'none' }}
                    >
                      &ldquo;{scenario.perspectives.corporate_pr.headline}&rdquo; ↗
                    </a>
                  ) : (
                    <>&ldquo;{scenario.perspectives.corporate_pr.headline}&rdquo;</>
                  )}
                </blockquote>

                <p className={styles.biasBox}>
                  <strong style={{ color: 'var(--caution)' }}>Bias Profile:</strong>{' '}
                  {scenario.perspectives.corporate_pr.biasProfile}
                </p>

                <div>
                  <p className={styles.claimsHeader}>Reported Claims:</p>
                  <div className={styles.claimsList}>
                    {scenario.perspectives.corporate_pr.claims.map((claim, idx) => (
                      <div key={idx} className={styles.claimItem}>
                        <span className={styles.claimMarker3}>●</span>
                        <span>{claim}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className={styles.tierFooter}>Corporate Lens: SEC Filings &amp; Tier-1 Supplier Watch</div>
            </div>
          </div>

          {/* Contradiction Matrix / Direct Conflicts */}
          <div className={styles.matrixSection}>
            <div className={styles.matrixHeader}>
              <div>
                <div className={styles.matrixTitleRow}>
                  <h4 className={styles.matrixTitle}>Direct Claim Contradictions</h4>
                  <span className={styles.inconsistenciesBadge}>
                    {scenario.contradictions.length} Discrepancies Arbitrated
                  </span>
                </div>
                <p className={styles.matrixSubtitle}>
                  Highlighting exact areas where sources diverge across physical facts, regional hubs, and temporal supply-chain regimes
                </p>
              </div>

              {/* Filter Pills */}
              <div className={styles.filterBar}>
                {['all', 'critical', 'high', 'moderate'].map(lvl => (
                  <button
                    key={lvl}
                    type="button"
                    onClick={() => setSeverityFilter(lvl)}
                    className={`${styles.filterBtn} ${severityFilter === lvl ? styles.filterBtnActive : ''}`}
                  >
                    {lvl}
                  </button>
                ))}
              </div>
            </div>

            {/* Contradiction Rows */}
            <div>
              {filteredContradictions.map((c, index) => (
                <div key={c.id || index} className={styles.conflictCard}>
                  <div className={styles.conflictHeader}>
                    <div className={styles.conflictHeaderLeft}>
                      <span
                        className={`${styles.severityChip} ${
                          c.severity === 'critical'
                            ? styles.severityCritical
                            : c.severity === 'high'
                            ? styles.severityHigh
                            : styles.severityModerate
                        }`}
                      >
                        {c.severity} Conflict
                      </span>
                      <h5 className={styles.conflictTitle}>Dimension: {c.dimension}</h5>
                    </div>
                    <span className={styles.triangulatedChip}>
                      ✓ {c.temporal_regime ? `${c.temporal_regime} · ` : ''}Ground Truth Triangulated
                    </span>
                  </div>

                  <div className={styles.triClaimsGrid}>
                    <div className={styles.claimBox}>
                      <p className={`${styles.claimBoxLabel} ${styles.claimBoxLabel1}`}>Western Media Stated:</p>
                      <p className={styles.claimBoxText}>&ldquo;{c.westernClaim}&rdquo;</p>
                    </div>

                    <div className={styles.claimBox}>
                      <p className={`${styles.claimBoxLabel} ${styles.claimBoxLabel2}`}>Local On-Ground Press Stated:</p>
                      <p className={styles.claimBoxText}>&ldquo;{c.localClaim}&rdquo;</p>
                    </div>

                    <div className={styles.claimBox}>
                      <p className={`${styles.claimBoxLabel} ${styles.claimBoxLabel3}`}>Corporate PR / SEC 10-K Stated:</p>
                      <p className={styles.claimBoxText}>&ldquo;{c.corporateClaim}&rdquo;</p>
                    </div>
                  </div>

                  <div className={styles.synthesisBox}>
                    <svg
                      className={styles.synthesisIcon}
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <circle cx="12" cy="12" r="10"></circle>
                      <line x1="12" y1="16" x2="12" y2="12"></line>
                      <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    <div>
                      <span className={styles.synthesisTitle}>Ground-Truth &amp; Temporal Regime Synthesis</span>
                      <p className={styles.synthesisText}>{c.synthesis}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Epistemic Verdict & Market Takeaway Section */}
          <div className={styles.arbiterPanel}>
            <div className={styles.arbiterHeader}>
              <span style={{ fontSize: '1.25rem', color: 'var(--brand-ink)' }}>⚖</span>
              <h4 className={styles.arbiterTitle}>Epistemic Arbiter &amp; Key Takeaways</h4>
            </div>

            <div className={styles.arbiterGrid}>
              <div className={styles.arbiterCard}>
                <h5 className={`${styles.arbiterCardTitle} ${styles.arbiterCardTitleBull}`}>✓ Consensus Facts</h5>
                <ul className={styles.arbiterList}>
                  {scenario.epistemicVerdict.consensusFacts.map((fact, idx) => (
                    <li key={idx} className={styles.arbiterListItem}>
                      <span style={{ color: 'var(--bull)', fontWeight: 700 }}>•</span>
                      <span>{fact}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className={styles.arbiterCard}>
                <h5 className={`${styles.arbiterCardTitle} ${styles.arbiterCardTitleCaution}`}>
                  🔍 Narrative Spin Diagnostics
                </h5>
                <p className={styles.arbiterText}>{scenario.epistemicVerdict.spinAnalysis}</p>
              </div>

              <div className={styles.arbiterCard}>
                <h5 className={`${styles.arbiterCardTitle} ${styles.arbiterCardTitleBrand}`}>
                  💡 Synthesized Market Takeaway
                </h5>
                <p className={styles.arbiterText}>{scenario.epistemicVerdict.marketAlpha}</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

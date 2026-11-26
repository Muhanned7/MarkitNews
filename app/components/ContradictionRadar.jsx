'use client'
import { useState } from 'react'
import { MOCK_CONTRADICTION_SCENARIOS } from '../../lib/mockContradictions'
import styles from './ContradictionRadar.module.css'

export default function ContradictionRadar({ defaultScenarioId = 'meridian-nickel' }) {
  const [selectedId, setSelectedId] = useState(defaultScenarioId)
  const [severityFilter, setSeverityFilter] = useState('all')

  const scenario = MOCK_CONTRADICTION_SCENARIOS[selectedId] || MOCK_CONTRADICTION_SCENARIOS['meridian-nickel']

  const filteredContradictions = (scenario?.contradictions || []).filter(item => {
    if (severityFilter === 'all') return true
    return item.severity === severityFilter
  })

  return (
    <div className={styles.container}>
      
      {/* Top Header & Scenario Selection */}
      <div className={styles.header}>
        <div>
          <div className={styles.eyebrow}>
            <span className={styles.pingDotWrapper}>
              <span className={styles.pingDotWave}></span>
              <span className={styles.pingDotSolid}></span>
            </span>
            <span>Contradiction Radar · Illustrative Demo</span>
          </div>
          <h2 className={styles.title}>
            Contradiction Radar
          </h2>
          <p className={styles.subtitle}>
            Where Western wires, local press and company PR disagree. Detecting narrative divergence and damage control across global markets.
          </p>
        </div>

        {/* Case Study Pill Switcher */}
        <div className={styles.scenarioSwitcher}>
          {Object.values(MOCK_CONTRADICTION_SCENARIOS).map(item => (
            <button
              key={item.id}
              onClick={() => setSelectedId(item.id)}
              className={`${styles.scenarioBtn} ${selectedId === item.id ? styles.scenarioBtnActive : ''}`}
            >
              {item.ticker}: {item.company.split(' ')[0]}
            </button>
          ))}
        </div>
      </div>

      {/* Active Story Overview Banner */}
      <div className={styles.storyBanner}>
        <div className={styles.storyMeta}>
          <div className={styles.storyMetaLeft}>
            <span className={`${styles.severityChip} ${
              scenario.severity === 'critical' ? styles.severityCritical :
              scenario.severity === 'high' ? styles.severityHigh :
              styles.severityModerate
            }`}>
              {scenario.severity} Discrepancy
            </span>
            <span className={styles.storyTarget}>
              Target: <strong>{scenario.company}</strong> ({scenario.ticker})
            </span>
          </div>
          <span className={styles.storyDate}>
            Detected: {scenario.date}
          </span>
        </div>
        <h3 className={styles.storyTitle}>
          {scenario.eventTitle}
        </h3>
        <p className={styles.storySummary}>
          {scenario.summary}
        </p>
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
                Macro Alarm
              </span>
            </div>
            
            <p className={styles.tierSource}>
              Source: <strong>{scenario.perspectives.western_media.source}</strong>
            </p>

            <blockquote className={styles.quoteBox}>
              "{scenario.perspectives.western_media.headline}"
            </blockquote>

            <p className={styles.biasBox}>
              <strong style={{ color: 'var(--bear)' }}>Bias Profile:</strong> {scenario.perspectives.western_media.biasProfile}
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

          <div className={styles.tierFooter}>
            Market Lens: Risk-Off / Global Supply Crunch
          </div>
        </div>

        {/* 2. Local / Regional Ground-Truth Press */}
        <div className={`${styles.tierCard} ${styles.tierCard2}`}>
          <div>
            <div className={styles.tierHeader}>
              <span className={styles.tierTitle}>
                <span className={`${styles.tierDot} ${styles.tierDot2}`}></span>
                Tier 2: Local & Regional Press
              </span>
              <span className={styles.tierChip}>
                Ground Reality
              </span>
            </div>
            
            <p className={styles.tierSource}>
              Source: <strong>{scenario.perspectives.local_media.source}</strong>
            </p>

            <blockquote className={styles.quoteBox}>
              "{scenario.perspectives.local_media.headline}"
            </blockquote>

            <p className={styles.biasBox}>
              <strong style={{ color: 'var(--bull)' }}>Bias Profile:</strong> {scenario.perspectives.local_media.biasProfile}
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

          <div className={styles.tierFooter}>
            Ground Lens: Physical Damage & Local Operations
          </div>
        </div>

        {/* 3. Corporate PR & Disclosures */}
        <div className={`${styles.tierCard} ${styles.tierCard3}`}>
          <div>
            <div className={styles.tierHeader}>
              <span className={styles.tierTitle}>
                <span className={`${styles.tierDot} ${styles.tierDot3}`}></span>
                Tier 3: Corporate PR & 8-K
              </span>
              <span className={styles.tierChip}>
                Damage Control
              </span>
            </div>
            
            <p className={styles.tierSource}>
              Source: <strong>{scenario.perspectives.corporate_pr.source}</strong>
            </p>

            <blockquote className={styles.quoteBox}>
              "{scenario.perspectives.corporate_pr.headline}"
            </blockquote>

            <p className={styles.biasBox}>
              <strong style={{ color: 'var(--caution)' }}>Bias Profile:</strong> {scenario.perspectives.corporate_pr.biasProfile}
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

          <div className={styles.tierFooter}>
            Corporate Lens: Shareholder Reassurance & Delivery Insulation
          </div>
        </div>

      </div>

      {/* Contradiction Matrix / Direct Conflicts */}
      <div className={styles.matrixSection}>
        <div className={styles.matrixHeader}>
          <div>
            <div className={styles.matrixTitleRow}>
              <h4 className={styles.matrixTitle}>
                Direct Claim Contradictions
              </h4>
              <span className={styles.inconsistenciesBadge}>
                {scenario.contradictions.length} Inconsistencies Found
              </span>
            </div>
            <p className={styles.matrixSubtitle}>
              Highlighting exact areas where sources directly dispute each other on physical facts and timelines
            </p>
          </div>

          {/* Filter Pills */}
          <div className={styles.filterBar}>
            {['all', 'critical', 'high', 'moderate'].map(lvl => (
              <button
                key={lvl}
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
              {/* Card Header */}
              <div className={styles.conflictHeader}>
                <div className={styles.conflictHeaderLeft}>
                  <span className={`${styles.severityChip} ${
                    c.severity === 'critical' ? styles.severityCritical :
                    c.severity === 'high' ? styles.severityHigh :
                    styles.severityModerate
                  }`}>
                    {c.severity} Conflict
                  </span>
                  <h5 className={styles.conflictTitle}>
                    Dimension: {c.dimension}
                  </h5>
                </div>
                <span className={styles.triangulatedChip}>
                  ✓ Ground Truth Triangulated
                </span>
              </div>

              {/* 3-Way Conflicting Claims Comparison */}
              <div className={styles.triClaimsGrid}>
                <div className={styles.claimBox}>
                  <p className={`${styles.claimBoxLabel} ${styles.claimBoxLabel1}`}>Western Media Stated:</p>
                  <p className={styles.claimBoxText}>"{c.westernClaim}"</p>
                </div>

                <div className={styles.claimBox}>
                  <p className={`${styles.claimBoxLabel} ${styles.claimBoxLabel2}`}>Local On-Ground Press Stated:</p>
                  <p className={styles.claimBoxText}>"{c.localClaim}"</p>
                </div>

                <div className={styles.claimBox}>
                  <p className={`${styles.claimBoxLabel} ${styles.claimBoxLabel3}`}>Corporate PR Stated:</p>
                  <p className={styles.claimBoxText}>"{c.corporateClaim}"</p>
                </div>
              </div>

              {/* Epistemic Synthesis */}
              <div className={styles.synthesisBox}>
                <svg className={styles.synthesisIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="16" x2="12" y2="12"></line>
                  <line x1="12" y1="8" x2="12.01" y2="8"></line>
                </svg>
                <div>
                  <span className={styles.synthesisTitle}>
                    Ground-Truth Synthesis
                  </span>
                  <p className={styles.synthesisText}>
                    {c.synthesis}
                  </p>
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
          <h4 className={styles.arbiterTitle}>
            Epistemic Arbiter & Key Takeaways
          </h4>
        </div>

        <div className={styles.arbiterGrid}>
          {/* Consensus Facts */}
          <div className={styles.arbiterCard}>
            <h5 className={`${styles.arbiterCardTitle} ${styles.arbiterCardTitleBull}`}>
              ✓ Consensus Facts
            </h5>
            <ul className={styles.arbiterList}>
              {scenario.epistemicVerdict.consensusFacts.map((fact, idx) => (
                <li key={idx} className={styles.arbiterListItem}>
                  <span style={{ color: 'var(--bull)', fontWeight: 700 }}>•</span>
                  <span>{fact}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Detected Spin Diagnostics */}
          <div className={styles.arbiterCard}>
            <h5 className={`${styles.arbiterCardTitle} ${styles.arbiterCardTitleCaution}`}>
              🔍 Narrative Spin Diagnostics
            </h5>
            <p className={styles.arbiterText}>
              {scenario.epistemicVerdict.spinAnalysis}
            </p>
          </div>

          {/* Market Synthesis */}
          <div className={styles.arbiterCard}>
            <h5 className={`${styles.arbiterCardTitle} ${styles.arbiterCardTitleBrand}`}>
              💡 Synthesized Market Takeaway
            </h5>
            <p className={styles.arbiterText}>
              {scenario.epistemicVerdict.marketAlpha}
            </p>
          </div>
        </div>
      </div>

    </div>
  )
}

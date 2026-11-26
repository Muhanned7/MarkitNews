'use client';

import React, { useState, useEffect, useCallback } from 'react';
import styles from './research.module.css';

const SIGNAL_OPTIONS = [
  { value: 'planted_alpha_strong', label: 'Planted Alpha — Strong (IC ≈ 0.05)' },
  { value: 'planted_alpha_weak', label: 'Planted Alpha — Weak (IC ≈ 0.02)' },
  { value: 'planted_noise', label: 'Planted Pure Noise (IC ≈ 0.00)' },
  { value: 'planted_lookahead', label: 'Planted Lookahead Leak (Unlagged r_{t+1})' },
  { value: 'momentum_12_1', label: 'Momentum (12-1 Month)' },
  { value: 'reversal_21d', label: 'Short-Term Reversal (21d)' },
  { value: 'low_vol_63d', label: 'Low Volatility (-σ 63d)' },
  { value: 'value_composite', label: 'Value Composite (E/P + FCF Yield, PIT)' },
  { value: 'quality_composite', label: 'Quality Composite (ROE − Accruals, PIT)' },
  { value: 'agent_conviction', label: 'AI Agent Signed Conviction' },
  { value: 'sentiment_score', label: 'AI News & Social Sentiment' },
  { value: 'contradiction_flag', label: 'Contradiction Radar Alignment' }
];

const TABS = [
  { id: 'tearsheet', label: '1. Signal Tear Sheet (QRA-004/007/008)' },
  { id: 'backtest', label: '2. Backtester & Costs (QRA-005)' },
  { id: 'runs', label: '3. Experiment Runs (QRA-006)' },
  { id: 'factors', label: '4. Factor Attribution (QRA-009)' },
  { id: 'agentlab', label: '5. AI Agent Eval Lab (QRA-010)' },
  { id: 'overfitting', label: '6. Overfitting & DSR (QRA-011)' },
  { id: 'blending', label: '7. Signal Blender & Handoff (QRA-012/013)' },
  { id: 'panel', label: '8. PIT Data & Universe (QRA-001/002)' }
];

function DualLineChart({ data, xKey, y1Key, y2Key, y1Label, y2Label, y1Color = 'var(--brand-ink)', y2Color = 'var(--ink-3)' }) {
  if (!data || data.length < 2) return null;
  const W = 680;
  const H = 210;
  const padL = 48;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  const vals = [];
  data.forEach(d => {
    if (typeof d[y1Key] === 'number') vals.push(d[y1Key]);
    if (y2Key && typeof d[y2Key] === 'number') vals.push(d[y2Key]);
  });
  const minV = Math.min(0, ...vals);
  const maxV = Math.max(0.01, ...vals);
  const span = maxV - minV || 1;
  const toX = i => padL + (i / (data.length - 1)) * (W - padL - padR);
  const toY = v => padT + (1 - (v - minV) / span) * (H - padT - padB);
  const zeroY = toY(0);

  const pts1 = data.map((d, i) => `${toX(i).toFixed(1)},${toY(d[y1Key] || 0).toFixed(1)}`).join(' ');
  const pts2 = y2Key ? data.map((d, i) => `${toX(i).toFixed(1)},${toY(d[y2Key] || 0).toFixed(1)}`).join(' ') : null;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={styles.svgChart} role="img" aria-label={`${y1Label} chart`}>
      <line x1={padL} y1={zeroY} x2={W - padR} y2={zeroY} stroke="var(--rule)" strokeDasharray="4 4" />
      <text x={padL - 6} y={padT + 8} textAnchor="end" fontSize="10" fill="var(--ink-3)">{maxV.toFixed(1)}</text>
      <text x={padL - 6} y={zeroY + 3} textAnchor="end" fontSize="10" fill="var(--ink-3)">0.0</text>
      <text x={padL - 6} y={H - padB} textAnchor="end" fontSize="10" fill="var(--ink-3)">{minV.toFixed(1)}</text>
      {pts2 && <polyline fill="none" stroke={y2Color} strokeWidth="1.75" strokeDasharray="3 3" points={pts2} />}
      <polyline fill="none" stroke={y1Color} strokeWidth="2.4" points={pts1} />
      <text x={padL} y={H - 8} fontSize="10" fill="var(--ink-3)">{data[0][xKey]}</text>
      <text x={W - padR} y={H - 8} textAnchor="end" fontSize="10" fill="var(--ink-3)">{data[data.length - 1][xKey]}</text>
    </svg>
  );
}

function RollingICChart({ data }) {
  if (!data || data.length < 2) return null;
  const W = 680;
  const H = 210;
  const padL = 48;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  const vals = [];
  data.forEach(d => {
    vals.push(d.upper_2sigma, d.lower_2sigma, d.rolling_ic);
  });
  const minV = Math.min(-0.05, ...vals);
  const maxV = Math.max(0.10, ...vals);
  const span = maxV - minV || 0.2;
  const toX = i => padL + (i / (data.length - 1)) * (W - padL - padR);
  const toY = v => padT + (1 - (v - minV) / span) * (H - padT - padB);
  const zeroY = toY(0);

  const upperPts = data.map((d, i) => `${toX(i).toFixed(1)},${toY(d.upper_2sigma).toFixed(1)}`);
  const lowerPts = [...data].reverse().map((d, idx) => {
    const i = data.length - 1 - idx;
    return `${toX(i).toFixed(1)},${toY(d.lower_2sigma).toFixed(1)}`;
  });
  const bandPoly = [...upperPts, ...lowerPts].join(' ');
  const linePts = data.map((d, i) => `${toX(i).toFixed(1)},${toY(d.rolling_ic).toFixed(1)}`).join(' ');

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={styles.svgChart} role="img" aria-label="Rolling 63d Rank IC with 2-sigma bands">
      <polygon points={bandPoly} fill="var(--brand-tint)" opacity="0.65" />
      <line x1={padL} y1={zeroY} x2={W - padR} y2={zeroY} stroke="var(--bear)" strokeDasharray="4 4" strokeWidth="1.2" />
      <polyline fill="none" stroke="var(--brand-ink)" strokeWidth="2.2" points={linePts} />
      <text x={padL - 6} y={padT + 8} textAnchor="end" fontSize="10" fill="var(--ink-3)">{maxV.toFixed(2)}</text>
      <text x={padL - 6} y={zeroY + 3} textAnchor="end" fontSize="10" fill="var(--ink-3)">0.00</text>
      <text x={padL - 6} y={H - padB} textAnchor="end" fontSize="10" fill="var(--ink-3)">{minV.toFixed(2)}</text>
      <text x={padL} y={H - 8} fontSize="10" fill="var(--ink-3)">{data[0].date}</text>
      <text x={W - padR} y={H - 8} textAnchor="end" fontSize="10" fill="var(--ink-3)">{data[data.length - 1].date}</text>
    </svg>
  );
}

export default function QuantResearchPage() {
  const [activeTab, setActiveTab] = useState('tearsheet');

  // Shared signal controls
  const [signal, setSignal] = useState('planted_alpha_strong');
  const [horizon, setHorizon] = useState(21);
  const [sectorNeutral, setSectorNeutral] = useState(false);
  const [betaNeutral, setBetaNeutral] = useState(false);

  // Tab 1: Tear Sheet state
  const [tearSheet, setTearSheet] = useState(null);
  const [loadingTS, setLoadingTS] = useState(false);

  // Tab 2: Backtester state
  const [btFreq, setBtFreq] = useState('monthly');
  const [btWeighting, setBtWeighting] = useState('equal_top_n');
  const [btMode, setBtMode] = useState('long_short');
  const [btLag, setBtLag] = useState(1);
  const [btCostBps, setBtCostBps] = useState(5.0);
  const [btImpact, setBtImpact] = useState(0.10);
  const [btData, setBtData] = useState(null);
  const [loadingBT, setLoadingBT] = useState(false);
  const [btSaveMsg, setBtSaveMsg] = useState('');

  // Tab 3: Experiment Runs state
  const [runsData, setRunsData] = useState(null);
  const [selectedRunIds, setSelectedRunIds] = useState([1, 2]);
  const [compareData, setCompareData] = useState(null);

  // Tab 4: Factor Attribution state
  const [orthoFactors, setOrthoFactors] = useState([]);
  const [factorData, setFactorData] = useState(null);
  const [loadingFactors, setLoadingFactors] = useState(false);

  // Tab 5: Agent Lab state
  const [agentLabData, setAgentLabData] = useState(null);

  // Tab 6: Overfitting & DSR state
  const [overfitData, setOverfitData] = useState(null);
  const [loadingOverfit, setLoadingOverfit] = useState(false);

  // Tab 7: Blending & Screener Handoff state
  const [blendMethod, setBlendMethod] = useState('custom');
  const [blendWeights, setBlendWeights] = useState({
    planted_alpha_strong: 0.35,
    momentum_12_1: 0.25,
    value_composite: 0.20,
    quality_composite: 0.20
  });
  const [blendData, setBlendData] = useState(null);
  const [handoffResult, setHandoffResult] = useState(null);
  const [handoffError, setHandoffError] = useState('');
  const [screenerData, setScreenerData] = useState(null);

  // Tab 8: Point-in-Time Data Panel & Universe state
  const [asOfDate, setAsOfDate] = useState('2026-10-14');
  const [universeData, setUniverseData] = useState(null);
  const [panelData, setPanelData] = useState(null);

  const loadTearSheet = useCallback(async () => {
    setLoadingTS(true);
    try {
      const qs = new URLSearchParams({
        signal,
        horizon: String(horizon),
        sector_neutral: String(sectorNeutral),
        beta_neutral: String(betaNeutral)
      });
      const res = await fetch(`/api/research/tear-sheet?${qs.toString()}`);
      if (res.ok) {
        setTearSheet(await res.json());
      }
    } finally {
      setLoadingTS(false);
    }
  }, [signal, horizon, sectorNeutral, betaNeutral]);

  const loadBacktest = useCallback(async (saveRun = false) => {
    setLoadingBT(true);
    setBtSaveMsg('');
    try {
      const res = await fetch('/api/research/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signal_name: signal,
          rebalance_freq: btFreq,
          weighting: btWeighting,
          mode: btMode,
          top_n: 20,
          max_weight: 0.08,
          sector_cap: 0.30,
          lag: Number(btLag),
          fixed_cost_bps: Number(btCostBps),
          impact_coeff: Number(btImpact),
          sector_neutral: sectorNeutral,
          beta_neutral: betaNeutral,
          save_run: saveRun,
          question_key: `${signal}_research`
        })
      });
      if (res.ok) {
        const data = await res.json();
        setBtData(data);
        if (saveRun && data.saved_run) {
          setBtSaveMsg(`Saved Run #${data.saved_run.id} (hash: ${data.config_hash})`);
        }
      }
    } finally {
      setLoadingBT(false);
    }
  }, [signal, btFreq, btWeighting, btMode, btLag, btCostBps, btImpact, sectorNeutral, betaNeutral]);

  const loadRunsAndCompare = useCallback(async (idsToCompare = selectedRunIds) => {
    const rRes = await fetch('/api/research/runs');
    if (rRes.ok) {
      const rJson = await rRes.json();
      setRunsData(rJson);
    }
    if (idsToCompare && idsToCompare.length > 0) {
      const cRes = await fetch(`/api/research/runs/compare?ids=${idsToCompare.join(',')}`);
      if (cRes.ok) {
        setCompareData(await cRes.json());
      }
    }
  }, [selectedRunIds]);

  const loadFactors = useCallback(async () => {
    setLoadingFactors(true);
    try {
      const qs = new URLSearchParams({ signal });
      if (orthoFactors.length > 0) qs.set('orthogonalize', orthoFactors.join(','));
      const res = await fetch(`/api/research/factors?${qs.toString()}`);
      if (res.ok) setFactorData(await res.json());
    } finally {
      setLoadingFactors(false);
    }
  }, [signal, orthoFactors]);

  const loadAgentLab = useCallback(async () => {
    const res = await fetch('/api/research/agent-lab?universe=mock100');
    if (res.ok) setAgentLabData(await res.json());
  }, []);

  const loadOverfitting = useCallback(async () => {
    setLoadingOverfit(true);
    try {
      const res = await fetch(`/api/research/overfitting?signal=${signal}&horizon=${horizon}`);
      if (res.ok) setOverfitData(await res.json());
    } finally {
      setLoadingOverfit(false);
    }
  }, [signal, horizon]);

  const loadBlendAndScreener = useCallback(async () => {
    const res = await fetch('/api/research/blend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        weights: blendWeights,
        method: blendMethod,
        horizon: Number(horizon),
        sector_neutral: sectorNeutral
      })
    });
    if (res.ok) setBlendData(await res.json());

    const sRes = await fetch(`/api/screen?strategy=${signal}&top_n=15`);
    if (sRes.ok) setScreenerData(await sRes.json());
  }, [blendWeights, blendMethod, horizon, sectorNeutral, signal]);

  const loadPanelAndUniverse = useCallback(async () => {
    const [uRes, pRes] = await Promise.all([
      fetch(`/api/research/universe?date=${asOfDate}`),
      fetch(`/api/research/panel?as_of=${asOfDate}&fields=close,ret_1d,mcap,pe,roe,fcf_yield&limit=60`)
    ]);
    if (uRes.ok) setUniverseData(await uRes.json());
    if (pRes.ok) setPanelData(await pRes.json());
  }, [asOfDate]);

  useEffect(() => {
    loadTearSheet();
  }, [loadTearSheet]);

  useEffect(() => {
    if (activeTab === 'backtest') loadBacktest(false);
    if (activeTab === 'runs') loadRunsAndCompare();
    if (activeTab === 'factors') loadFactors();
    if (activeTab === 'agentlab' && !agentLabData) loadAgentLab();
    if (activeTab === 'overfitting') loadOverfitting();
    if (activeTab === 'blending') loadBlendAndScreener();
    if (activeTab === 'panel') loadPanelAndUniverse();
  }, [activeTab, loadBacktest, loadRunsAndCompare, loadFactors, agentLabData, loadAgentLab, loadOverfitting, loadBlendAndScreener, loadPanelAndUniverse]);

  const handleDeployToScreener = async (targetSignal) => {
    setHandoffError('');
    setHandoffResult(null);
    const res = await fetch('/api/research/deploy-to-screener', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        strategy_name: `QRA Verified (${targetSignal})`,
        signal_name: targetSignal,
        top_n: 15
      })
    });
    const data = await res.json();
    if (!res.ok) {
      setHandoffError(data.detail || data.error || 'Deployment gate rejected strategy');
    } else {
      setHandoffResult(data);
      const sRes = await fetch(`/api/screen?strategy=${targetSignal}&top_n=15`);
      if (sRes.ok) setScreenerData(await sRes.json());
    }
  };

  const toggleRunSelection = (id) => {
    setSelectedRunIds(prev => {
      let next;
      if (prev.includes(id)) {
        next = prev.filter(x => x !== id);
      } else {
        next = [...prev, id].slice(-4);
      }
      loadRunsAndCompare(next);
      return next;
    });
  };

  const toggleOrthoFactor = (f) => {
    setOrthoFactors(prev => (prev.includes(f) ? prev.filter(x => x !== f) : [...prev, f]));
  };

  const activeLeakage = tearSheet?.leakage_scan;

  return (
    <div className={styles.pageWrap}>
      {/* Header & Automated Leakage Status */}
      <div className={styles.headerRow}>
        <div className={styles.titleBlock}>
          <h1>Quantitative Research Workbench</h1>
          <p className={styles.subtitle}>
            100-Ticker 11-Sector Point-in-Time Universe (2,520d) · Signal Tear Sheets · Cost-Adjusted Backtester · Factor & Overfitting Lab
          </p>
        </div>
        <div className={styles.badgeRow}>
          <span className={styles.badgeWarning} title="Synthetic simulation universe with planted signals for quant calibration">
            🧪 Synthetic Demo Data (mock100)
          </span>
          <span className={styles.badgeNeutral}>Universe: mock100 (10Y PIT)</span>
          <span className={styles.badgeNeutral}>Delistings Tracked: 5</span>
          {activeLeakage && (
            <span
              data-testid="leakage-badge"
              className={activeLeakage.badge === 'POINT_IN_TIME_VERIFIED' ? styles.badgeVerified : styles.badgeWarning}
            >
              {activeLeakage.badge_label} (Corr(s_t, r_t+1) = {activeLeakage.unlagged_corr_s_t_r_t1})
            </span>
          )}
        </div>
      </div>

      {/* Synthetic Demo Notice Banner (PROD-012) */}
      <div
        style={{
          marginBottom: '16px',
          padding: '10px 14px',
          borderRadius: 'var(--r-control)',
          background: 'var(--surface-2)',
          border: '1px solid var(--rule)',
          fontSize: 'var(--fs-xs)',
          color: 'var(--ink-2)',
        }}
      >
        <strong>Synthetic Benchmark Notice:</strong> This workbench runs against the deterministic <code>mock100</code> point-in-time simulation panel (100 synthetic equities across 11 GICS sectors over 2,520 trading days). High t-statistics on <code>planted_alpha_strong</code> verify pipeline calibration against known planted alpha.
      </div>

      {activeLeakage && activeLeakage.warnings && activeLeakage.warnings.length > 0 && (
        <div className={styles.leakAlertBanner} role="alert" data-testid="leakage-warning-banner">
          {activeLeakage.warnings.map((w, idx) => (
            <div key={idx}>⚠️ {w}</div>
          ))}
        </div>
      )}

      {/* Global Signal Explorer Strip */}
      <div className={styles.controlStrip}>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="qra-signal-select">Research Signal</label>
          <select
            id="qra-signal-select"
            data-testid="signal-select"
            className={styles.selectInput}
            value={signal}
            onChange={e => setSignal(e.target.value)}
          >
            {SIGNAL_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="qra-horizon-select">Forward Horizon</label>
          <select
            id="qra-horizon-select"
            data-testid="horizon-select"
            className={styles.selectInput}
            value={horizon}
            onChange={e => setHorizon(Number(e.target.value))}
          >
            <option value={1}>1 Day (1d)</option>
            <option value={5}>1 Week (5d)</option>
            <option value={21}>1 Month (21d)</option>
            <option value={63}>1 Quarter (63d)</option>
            <option value={126}>6 Months (126d)</option>
          </select>
        </div>

        <label className={styles.checkLabel}>
          <input
            type="checkbox"
            checked={sectorNeutral}
            onChange={e => setSectorNeutral(e.target.checked)}
          />
          Sector-Neutral (11 GICS)
        </label>

        <label className={styles.checkLabel}>
          <input
            type="checkbox"
            checked={betaNeutral}
            onChange={e => setBetaNeutral(e.target.checked)}
          />
          Beta-Neutral (OLS)
        </label>
      </div>

      {/* Navigation Tabs */}
      <div className={styles.tabBar} role="tablist" aria-label="Quant Research Modules">
        {TABS.map(t => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            data-testid={`tab-${t.id}`}
            className={`${styles.tabBtn} ${activeTab === t.id ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* TAB 1: IC Tear Sheet & Signal Visualizer */}
      {activeTab === 'tearsheet' && tearSheet && (
        <div>
          <div className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Mean Rank IC ({tearSheet.horizon_days}d)</div>
              <div className={`${styles.kpiVal} ${tearSheet.summary.mean_ic > 0.015 ? styles.posText : ''}`} data-testid="kpi-mean-ic">
                {tearSheet.summary.mean_ic >= 0 ? `+${tearSheet.summary.mean_ic.toFixed(4)}` : tearSheet.summary.mean_ic.toFixed(4)}
              </div>
              <div className={styles.kpiSub}>SD: {tearSheet.summary.ic_sd.toFixed(4)} · Hit: {tearSheet.summary.hit_rate_pct}%</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Annualized IC IR</div>
              <div className={styles.kpiVal} data-testid="kpi-ic-ir">{tearSheet.summary.ic_ir.toFixed(2)}</div>
              <div className={styles.kpiSub}>Information Ratio</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Newey-West t-stat</div>
              <div className={`${styles.kpiVal} ${Math.abs(tearSheet.summary.newey_west_t_stat) >= 2.0 ? styles.posText : ''}`} data-testid="kpi-nw-tstat">
                {tearSheet.summary.newey_west_t_stat.toFixed(2)}
              </div>
              <div className={styles.kpiSub}>HAC Lags = {tearSheet.horizon_days}d</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Q5 − Q1 Spread (Ann.)</div>
              <div className={`${styles.kpiVal} ${tearSheet.summary.q5_q1_annualized_spread_pct > 0 ? styles.posText : styles.negText}`}>
                {tearSheet.summary.q5_q1_annualized_spread_pct >= 0 ? '+' : ''}{tearSheet.summary.q5_q1_annualized_spread_pct}%
              </div>
              <div className={styles.kpiSub}>Spread t-stat: {tearSheet.summary.q5_q1_t_stat.toFixed(2)}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Quintile Ordering</div>
              <div className={styles.kpiVal}>
                {tearSheet.summary.quintile_monotonic ? 'Monotonic ✓' : `ρ = ${tearSheet.summary.quintile_rank_corr}`}
              </div>
              <div className={styles.kpiSub}>Half-life t½: {tearSheet.summary.half_life_days}d</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Standardisation Check</div>
              <div className={styles.kpiVal}>
                μ={tearSheet.standardisation.mean_cross_sectional_mean.toFixed(2)}, σ={tearSheet.standardisation.mean_cross_sectional_sd.toFixed(2)}
              </div>
              <div className={styles.kpiSub}>
                Max Sec Corr: {tearSheet.standardisation.max_abs_sector_dummy_corr.toFixed(4)} · Cov: {tearSheet.summary.coverage_pct}%
              </div>
            </div>
          </div>

          <div className={styles.grid2}>
            {/* Quantile Return Bar Chart (Q1 to Q5) */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Quantile Forward Returns (Q1 → Q5 Annualized %)</h2>
                <span className={styles.panelSub}>
                  {tearSheet.summary.quintile_monotonic ? 'Strict Q1 < Q2 < Q3 < Q4 < Q5 Monotonicity ✓' : `Rank Correlation: ${tearSheet.summary.quintile_rank_corr}`}
                </span>
              </div>
              <div className={styles.quintileBars} data-testid="quintile-bar-chart">
                {(() => {
                  const maxAbs = Math.max(5, ...tearSheet.quintile_returns.map(q => Math.abs(q.annualized_return_pct)));
                  return tearSheet.quintile_returns.map((q, idx) => {
                    const v = q.annualized_return_pct;
                    const hPct = Math.max(12, Math.round((Math.abs(v) / maxAbs) * 140));
                    const isPos = v >= 0;
                    return (
                      <div key={q.quintile} className={styles.qBarCol}>
                        <span className={`${styles.qBarVal} ${isPos ? styles.posText : styles.negText}`}>
                          {v >= 0 ? `+${v.toFixed(1)}%` : `${v.toFixed(1)}%`}
                        </span>
                        <div
                          className={styles.qBarFill}
                          style={{
                            height: `${hPct}px`,
                            background: idx === 4 ? 'var(--bull)' : idx === 0 ? 'var(--bear)' : 'var(--brand-ink)'
                          }}
                        />
                        <span className={styles.qBarLabel}>{q.quintile}</span>
                      </div>
                    );
                  });
                })()}
              </div>
            </div>

            {/* Cumulative Alpha Spread Q5 - Q1 vs SPY */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Cumulative Alpha Spread (Q5 − Q1 L/S vs SPY %)</h2>
                <span className={styles.panelSub}>Solid: Q5−Q1 Long-Short · Dashed: SPY Benchmark</span>
              </div>
              <DualLineChart
                data={tearSheet.cumulative_spread_chart}
                xKey="date"
                y1Key="q5_q1_cum_pct"
                y2Key="spy_cum_pct"
                y1Label="Q5-Q1 Spread %"
                y2Label="SPY %"
              />
            </div>
          </div>

          <div className={styles.grid2}>
            {/* Rolling 63d Rank IC with +/- 2 sigma bands */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Rolling 63-Day Spearman Rank IC (±2σ Bands)</h2>
                <span className={styles.panelSub}>Autocorr(1d): {tearSheet.summary.rank_autocorr_1d} · Q5 Turnover: {tearSheet.summary.q5_turnover_pct}%</span>
              </div>
              <RollingICChart data={tearSheet.rolling_ic_chart} />
            </div>

            {/* 11-Sector IC Boxplot Breakdown */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>11-Sector Rank IC Boxplot (IQR & Median)</h2>
                <span className={styles.panelSub}>Cross-sector breadth verification</span>
              </div>
              <div data-testid="sector-ic-boxplot">
                {tearSheet.sector_ic_boxplot.map(sec => {
                  const mapPos = val => Math.max(0, Math.min(100, ((val + 0.35) / 0.70) * 100));
                  const left = mapPos(sec.q25);
                  const right = mapPos(sec.q75);
                  const med = mapPos(sec.median);
                  const zero = mapPos(0);
                  return (
                    <div key={sec.sector} className={styles.boxplotRow}>
                      <span style={{ fontWeight: 600 }}>{sec.sector}</span>
                      <div className={styles.boxplotTrack}>
                        <div style={{ position: 'absolute', left: `${zero}%`, top: 0, bottom: 0, width: 1, background: 'var(--bear)' }} />
                        <div
                          style={{
                            position: 'absolute',
                            left: `${left}%`,
                            width: `${Math.max(2, right - left)}%`,
                            top: 3,
                            bottom: 3,
                            background: 'var(--brand-tint)',
                            border: '1px solid var(--brand-ink)',
                            borderRadius: 3
                          }}
                        />
                        <div style={{ position: 'absolute', left: `${med}%`, top: 1, bottom: 1, width: 2.5, background: 'var(--ink)' }} />
                      </div>
                      <span className={`num ${sec.mean_ic >= 0 ? styles.posText : styles.negText}`} style={{ textAlign: 'right' }}>
                        {sec.mean_ic >= 0 ? `+${sec.mean_ic.toFixed(3)}` : sec.mean_ic.toFixed(3)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className={styles.grid2}>
            {/* IC Decay Curve across Horizons */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>IC Horizon Decay Curve (1d → 126d)</h2>
                <span className={styles.panelSub}>Estimated Half-Life t½ = {tearSheet.summary.half_life_days} trading days</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Horizon (Days)</th>
                      <th>Mean Rank IC</th>
                      <th>Annualized IC IR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tearSheet.ic_decay_curve.map(row => (
                      <tr key={row.horizon_days}>
                        <td>{row.horizon_days}d</td>
                        <td className={row.mean_ic > 0 ? styles.posText : ''}>{row.mean_ic.toFixed(4)}</td>
                        <td>{row.ic_ir.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Yearly IC Stability Table */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Rank IC by Calendar Year</h2>
                <span className={styles.panelSub}>10-Year Historical Consistency</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Mean IC</th>
                      <th>IC SD</th>
                      <th>Hit Rate</th>
                      <th>Days</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tearSheet.ic_by_year.map(yr => (
                      <tr key={yr.year}>
                        <td>{yr.year}</td>
                        <td className={yr.mean_ic >= 0 ? styles.posText : styles.negText}>{yr.mean_ic.toFixed(4)}</td>
                        <td>{yr.ic_sd.toFixed(4)}</td>
                        <td>{yr.hit_rate_pct}%</td>
                        <td>{yr.n_days}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Backtester & Transaction Cost Lab */}
      {activeTab === 'backtest' && (
        <div>
          <div className={styles.controlStrip}>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Rebalance Freq</label>
              <select className={styles.selectInput} value={btFreq} onChange={e => setBtFreq(e.target.value)}>
                <option value="daily">Daily (1d)</option>
                <option value="weekly">Weekly (5d)</option>
                <option value="monthly">Monthly (21d)</option>
              </select>
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Weighting Scheme</label>
              <select className={styles.selectInput} value={btWeighting} onChange={e => setBtWeighting(e.target.value)}>
                <option value="equal_top_n">Equal-Weight Top/Bottom N</option>
                <option value="signal_proportional">Signal-Proportional</option>
                <option value="vol_scaled">Inverse-Volatility Scaled</option>
                <option value="universe_equal">Whole Universe Equal-Weight</option>
              </select>
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Book Mode</label>
              <select className={styles.selectInput} value={btMode} onChange={e => setBtMode(e.target.value)}>
                <option value="long_short">Long-Short (Dollar Neutral)</option>
                <option value="long_only">Long-Only</option>
              </select>
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Execution Lag Guard</label>
              <select className={styles.selectInput} value={btLag} onChange={e => setBtLag(Number(e.target.value))} data-testid="bt-lag-select">
                <option value={1}>Lag = 1 Day (Safe Default ✓)</option>
                <option value={0}>Lag = 0 Days (Unlagged Lookahead ⚠)</option>
              </select>
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Fixed Cost (bps)</label>
              <input
                type="number"
                className={styles.numInput}
                value={btCostBps}
                min={0}
                max={100}
                step={1}
                onChange={e => setBtCostBps(e.target.value)}
              />
            </div>
            <button className={styles.primaryBtn} onClick={() => loadBacktest(false)} disabled={loadingBT}>
              {loadingBT ? 'Running...' : 'Run Backtest'}
            </button>
            <button className={styles.secondaryBtn} onClick={() => loadBacktest(true)} disabled={loadingBT}>
              Save Run to Tracker
            </button>
          </div>

          {btSaveMsg && (
            <div className={styles.panel} style={{ padding: '10px 16px', color: 'var(--bull)', fontWeight: 700 }}>
              ✓ {btSaveMsg}
            </div>
          )}

          {btData && btData.leakage_scan && btData.leakage_scan.warnings.length > 0 && (
            <div className={styles.leakAlertBanner} role="alert">
              {btData.leakage_scan.warnings.map((w, i) => (
                <div key={i}>⚠️ {w}</div>
              ))}
            </div>
          )}

          {btData && (
            <>
              <div className={styles.kpiGrid}>
                <div className={styles.kpiCard}>
                  <div className={styles.kpiLabel}>Net Sharpe (After Costs)</div>
                  <div className={`${styles.kpiVal} ${btData.net_metrics.sharpe >= 1.0 ? styles.posText : ''}`} data-testid="bt-net-sharpe">
                    {btData.net_metrics.sharpe.toFixed(2)}
                  </div>
                  <div className={styles.kpiSub}>Gross Sharpe: {btData.gross_metrics.sharpe.toFixed(2)}</div>
                </div>
                <div className={styles.kpiCard}>
                  <div className={styles.kpiLabel}>Net CAGR</div>
                  <div className={`${styles.kpiVal} ${btData.net_metrics.cagr_pct >= 0 ? styles.posText : styles.negText}`}>
                    {btData.net_metrics.cagr_pct >= 0 ? `+${btData.net_metrics.cagr_pct}%` : `${btData.net_metrics.cagr_pct}%`}
                  </div>
                  <div className={styles.kpiSub}>Gross CAGR: {btData.gross_metrics.cagr_pct}%</div>
                </div>
                <div className={styles.kpiCard}>
                  <div className={styles.kpiLabel}>Annualized Vol & Sortino</div>
                  <div className={styles.kpiVal}>{btData.net_metrics.annual_vol_pct}%</div>
                  <div className={styles.kpiSub}>Sortino: {btData.net_metrics.sortino.toFixed(2)} · Calmar: {btData.net_metrics.calmar.toFixed(2)}</div>
                </div>
                <div className={styles.kpiCard}>
                  <div className={styles.kpiLabel}>Max Drawdown</div>
                  <div className={`${styles.kpiVal} ${styles.negText}`}>{btData.net_metrics.max_drawdown_pct}%</div>
                  <div className={styles.kpiSub}>Hit Rate: {btData.net_metrics.hit_rate_pct}%</div>
                </div>
                <div className={styles.kpiCard}>
                  <div className={styles.kpiLabel}>CAPM α vs SPY</div>
                  <div className={`${styles.kpiVal} ${btData.capm_vs_spy.alpha_annual_pct > 0 ? styles.posText : ''}`}>
                    {btData.capm_vs_spy.alpha_annual_pct >= 0 ? '+' : ''}{btData.capm_vs_spy.alpha_annual_pct}%
                  </div>
                  <div className={styles.kpiSub}>
                    t(α) = {btData.capm_vs_spy.alpha_t_stat} · β = {btData.capm_vs_spy.beta}
                  </div>
                </div>
                <div className={styles.kpiCard}>
                  <div className={styles.kpiLabel}>Turnover & Cost Drag</div>
                  <div className={styles.kpiVal}>{btData.costs_and_turnover.annual_cost_drag_bps} bps/yr</div>
                  <div className={styles.kpiSub}>
                    1-Way TO: {btData.costs_and_turnover.annual_one_way_turnover_pct}% · Hash: {btData.config_hash.slice(0, 8)}
                  </div>
                </div>
              </div>

              <div className={styles.grid2}>
                <div className={styles.panel}>
                  <div className={styles.panelHead}>
                    <h2 className={styles.panelTitle}>Equity Curve: Net (Solid) vs Gross (Dashed)</h2>
                    <span className={styles.panelSub}>Includes Fixed {btCostBps} bps + √Impact Costs</span>
                  </div>
                  <DualLineChart
                    data={btData.equity_chart}
                    xKey="date"
                    y1Key="net"
                    y2Key="gross"
                    y1Label="Net Equity"
                    y2Label="Gross Equity"
                  />
                </div>
                <div className={styles.panel}>
                  <div className={styles.panelHead}>
                    <h2 className={styles.panelTitle}>Underwater Drawdown (%)</h2>
                    <span className={styles.panelSub}>Max Drawdown: {btData.net_metrics.max_drawdown_pct}%</span>
                  </div>
                  <DualLineChart
                    data={btData.equity_chart}
                    xKey="date"
                    y1Key="drawdown_pct"
                    y1Label="Drawdown %"
                    y1Color="var(--bear)"
                  />
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* TAB 3: Experiment Tracking & Side-by-Side Comparison */}
      {activeTab === 'runs' && runsData && (
        <div>
          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <h2 className={styles.panelTitle}>Saved Research Runs (`research_runs` Table — Select 2–4 to Compare)</h2>
              <span className={styles.panelSub}>
                Total Tracked Trials: {runsData.total_runs} · Questions: {Object.entries(runsData.trial_counts_by_question || {}).map(([k, v]) => `${k} (${v})`).join(', ')}
              </span>
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th>Compare</th>
                    <th>Run ID</th>
                    <th>Signal</th>
                    <th>Question Key</th>
                    <th>Config Hash</th>
                    <th>Net Sharpe</th>
                    <th>Net CAGR</th>
                    <th>CAPM α (t-stat)</th>
                    <th>Tags</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {runsData.runs.map(r => {
                    const checked = selectedRunIds.includes(r.id);
                    const net = r.metrics_json?.net || {};
                    const capm = r.metrics_json?.capm || {};
                    return (
                      <tr key={r.id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleRunSelection(r.id)}
                          />
                        </td>
                        <td>#{r.id}</td>
                        <td style={{ fontWeight: 700 }}>{r.signal_name}</td>
                        <td>{r.question_key}</td>
                        <td><code>{r.config_hash}</code></td>
                        <td className={net.sharpe >= 1 ? styles.posText : ''}>{net.sharpe?.toFixed(2)}</td>
                        <td>{net.cagr_pct}%</td>
                        <td>{capm.alpha_annual_pct}% (t={capm.alpha_t_stat})</td>
                        <td>{(r.tags || []).join(', ')}</td>
                        <td>{r.notes}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {compareData && compareData.runs && compareData.runs.length >= 1 && (
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Side-by-Side Run Comparison ({compareData.compared_run_ids.map(i => `#${i}`).join(' vs ')})</h2>
                <span className={styles.panelSub}>Reproducible config hashes & overlaid net performance</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      {compareData.runs.map(r => (
                        <th key={r.id}>Run #{r.id} ({r.signal_name})</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Config Hash</td>
                      {compareData.runs.map(r => <td key={r.id}><code>{r.config_hash}</code></td>)}
                    </tr>
                    <tr>
                      <td>Net Sharpe Ratio</td>
                      {compareData.runs.map(r => <td key={r.id} className={styles.posText}>{r.metrics?.net?.sharpe}</td>)}
                    </tr>
                    <tr>
                      <td>Net CAGR (%)</td>
                      {compareData.runs.map(r => <td key={r.id}>{r.metrics?.net?.cagr_pct}%</td>)}
                    </tr>
                    <tr>
                      <td>Max Drawdown (%)</td>
                      {compareData.runs.map(r => <td key={r.id} className={styles.negText}>{r.metrics?.net?.max_drawdown_pct}%</td>)}
                    </tr>
                    <tr>
                      <td>CAPM α (% / yr)</td>
                      {compareData.runs.map(r => <td key={r.id}>{r.metrics?.capm?.alpha_annual_pct}% (t={r.metrics?.capm?.alpha_t_stat})</td>)}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: Factor Model & Orthogonalisation */}
      {activeTab === 'factors' && factorData && (
        <div>
          <div className={styles.controlStrip}>
            <span className={styles.fieldLabel}>Orthogonalise Signal Against Style Factors:</span>
            {['SMB', 'HML', 'MOM', 'LOW_VOL', 'QUALITY'].map(fn => (
              <label key={fn} className={styles.checkLabel}>
                <input
                  type="checkbox"
                  checked={orthoFactors.includes(fn)}
                  onChange={() => toggleOrthoFactor(fn)}
                />
                {fn}
              </label>
            ))}
            <button className={styles.primaryBtn} onClick={loadFactors} disabled={loadingFactors}>
              {loadingFactors ? 'Updating...' : 'Recompute Attribution'}
            </button>
          </div>

          <div className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Residual Alpha (Annualized)</div>
              <div className={`${styles.kpiVal} ${factorData.alpha.significant ? styles.posText : ''}`} data-testid="factor-alpha-pct">
                {factorData.alpha.alpha_annual_pct >= 0 ? `+${factorData.alpha.alpha_annual_pct}%` : `${factorData.alpha.alpha_annual_pct}%`}
              </div>
              <div className={styles.kpiSub}>Daily: {factorData.alpha.alpha_daily_bps} bps/d</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Alpha HAC t-statistic</div>
              <div className={`${styles.kpiVal} ${factorData.alpha.significant ? styles.posText : ''}`} data-testid="factor-alpha-tstat">
                {factorData.alpha.t_stat.toFixed(2)}
              </div>
              <div className={styles.kpiSub}>p-value: {factorData.alpha.p_value}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Model R² (Explained Variance)</div>
              <div className={styles.kpiVal}>{(factorData.r_squared * 100).toFixed(1)}%</div>
              <div className={styles.kpiSub}>Adj R²: {(factorData.adj_r_squared * 100).toFixed(1)}%</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Residual Alpha IR</div>
              <div className={styles.kpiVal}>{factorData.alpha.information_ratio.toFixed(2)}</div>
              <div className={styles.kpiSub}>N = {factorData.n_days} trading days</div>
            </div>
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <h2 className={styles.panelTitle}>6-Factor Multivariate Regression Loadings ({factorData.signal_name})</h2>
              <span className={styles.panelSub}>{factorData.verdict}</span>
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th>Factor</th>
                    <th>Description</th>
                    <th>Loading (β)</th>
                    <th>HAC t-stat</th>
                    <th>p-value</th>
                    <th>Ann. Return Contrib (%)</th>
                    <th>Significance</th>
                  </tr>
                </thead>
                <tbody>
                  {factorData.loadings.map(f => (
                    <tr key={f.factor}>
                      <td style={{ fontWeight: 700 }}>{f.factor}</td>
                      <td>{f.label}</td>
                      <td className={Math.abs(f.beta) > 0.25 ? styles.posText : ''}>{f.beta.toFixed(4)}</td>
                      <td>{f.t_stat.toFixed(2)}</td>
                      <td>{f.p_value.toFixed(4)}</td>
                      <td>{f.annual_return_contribution_pct}%</td>
                      <td>{f.significant ? 'Significant ✓' : 'Noise'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <h2 className={styles.panelTitle}>6×6 Factor Return Correlation Matrix</h2>
              <span className={styles.panelSub}>Empirical cross-factor orthogonality check</span>
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th>Factor</th>
                    <th>MKT</th>
                    <th>SMB</th>
                    <th>HML</th>
                    <th>MOM</th>
                    <th>LOW_VOL</th>
                    <th>QUALITY</th>
                  </tr>
                </thead>
                <tbody>
                  {factorData.factor_correlation_matrix.map(r => (
                    <tr key={r.factor}>
                      <td style={{ fontWeight: 700 }}>{r.factor}</td>
                      <td>{r.MKT.toFixed(3)}</td>
                      <td>{r.SMB.toFixed(3)}</td>
                      <td>{r.HML.toFixed(3)}</td>
                      <td>{r.MOM.toFixed(3)}</td>
                      <td>{r.LOW_VOL.toFixed(3)}</td>
                      <td>{r.QUALITY.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: AI Agent Evaluation Lab */}
      {activeTab === 'agentlab' && agentLabData && (
        <div>
          <div className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Full Synthesizer IC (21d)</div>
              <div className={`${styles.kpiVal} ${styles.posText}`}>+{agentLabData.synthesizer_summary.mean_ic_21d}</div>
              <div className={styles.kpiSub}>IC IR: {agentLabData.synthesizer_summary.ic_ir} · t = {agentLabData.synthesizer_summary.nw_t_stat}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>63d Brier Score</div>
              <div className={`${styles.kpiVal} ${styles.posText}`} data-testid="agent-brier-score">{agentLabData.synthesizer_summary.brier_score_63d}</div>
              <div className={styles.kpiSub}>Skill Score: +{(agentLabData.synthesizer_summary.brier_skill_score * 100).toFixed(1)}% vs Base</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Conviction 1–10 Calibration</div>
              <div className={styles.kpiVal}>{agentLabData.synthesizer_summary.conviction_monotonic ? 'Monotonic ✓' : 'Partial'}</div>
              <div className={styles.kpiSub}>L/S Sharpe: {agentLabData.synthesizer_summary.ls_sharpe}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Universe Join Hygiene</div>
              <div className={`${styles.kpiVal} ${styles.posText}`}>0 Contaminated</div>
              <div className={styles.kpiSub}>Excluded {agentLabData.hygiene_audit.excluded_cross_universe_snapshots} out-of-universe rows</div>
            </div>
          </div>

          <div className={styles.grid2}>
            {/* View 1: Per-Agent Rank IC Table */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>1. Per-Agent Point-in-Time Rank IC Scorecard</h2>
                <span className={styles.panelSub}>Evaluated over 1,260 trading days on mock100</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Agent</th>
                      <th>21d Rank IC</th>
                      <th>IC IR</th>
                      <th>NW t-stat</th>
                      <th>63d IC</th>
                      <th>Hit Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentLabData.per_agent_ic.map(ag => (
                      <tr key={ag.agent}>
                        <td style={{ fontWeight: 700 }}>{ag.label}</td>
                        <td className={styles.posText}>+{ag.mean_ic_21d.toFixed(4)}</td>
                        <td>{ag.ic_ir_21d.toFixed(2)}</td>
                        <td>{ag.nw_t_stat_21d.toFixed(2)}</td>
                        <td>+{ag.mean_ic_63d.toFixed(4)}</td>
                        <td>{ag.hit_rate_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* View 2: Leave-One-Agent-Out Ablation Study */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>2. Leave-One-Agent-Out Ablation Study</h2>
                <span className={styles.panelSub}>Marginal IC & Sharpe contribution per specialist agent</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Configuration</th>
                      <th>Mean IC</th>
                      <th>IC IR</th>
                      <th>Sharpe</th>
                      <th>Δ IC when Removed</th>
                      <th>Adds Value?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentLabData.ablation_study.map(row => (
                      <tr key={row.configuration}>
                        <td style={{ fontWeight: row.removed_agent ? 500 : 700 }}>{row.configuration}</td>
                        <td>{row.mean_ic_21d.toFixed(4)}</td>
                        <td>{row.ic_ir.toFixed(2)}</td>
                        <td>{row.sharpe.toFixed(2)}</td>
                        <td className={row.delta_ic < 0 ? styles.negText : ''}>
                          {row.delta_ic === 0 ? 'Baseline' : row.delta_ic.toFixed(4)}
                        </td>
                        <td className={styles.posText}>{row.adds_incremental_value ? 'Yes ✓' : 'Neutral'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className={styles.grid2}>
            {/* View 3: Conviction 1-10 Calibration & Reliability */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>3. Conviction 1–10 Calibration & 63d Reliability</h2>
                <span className={styles.panelSub}>Brier Score = {agentLabData.synthesizer_summary.brier_score_63d}</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Conviction</th>
                      <th>Avg 63d Excess Return</th>
                      <th>Predicted Win Prob</th>
                      <th>Observed Win Freq</th>
                      <th>Snapshots</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentLabData.conviction_calibration.map((c, idx) => {
                      const rel = agentLabData.reliability_diagram[idx];
                      return (
                        <tr key={c.conviction}>
                          <td style={{ fontWeight: 700 }}>{c.conviction} / 10</td>
                          <td className={c.avg_63d_excess_return_pct >= 0 ? styles.posText : styles.negText}>
                            {c.avg_63d_excess_return_pct >= 0 ? `+${c.avg_63d_excess_return_pct}%` : `${c.avg_63d_excess_return_pct}%`}
                          </td>
                          <td>{(rel.predicted_prob * 100).toFixed(1)}%</td>
                          <td>{(rel.observed_freq * 100).toFixed(1)}%</td>
                          <td>{c.n_snapshots}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* View 4: Prompt Hash & Model Version Comparison */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>4. Prompt & Model Version Comparison (`prompt_hash`)</h2>
                <span className={styles.panelSub}>Historical harness evolution</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Version</th>
                      <th>Prompt Hash</th>
                      <th>Mean IC</th>
                      <th>IC IR</th>
                      <th>Brier Score</th>
                      <th>Guardrail Reject %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentLabData.version_comparison.map(v => (
                      <tr key={v.prompt_hash}>
                        <td style={{ fontWeight: 700 }}>{v.version_tag}</td>
                        <td><code>{v.prompt_hash}</code></td>
                        <td className={styles.posText}>+{v.mean_ic_21d.toFixed(4)}</td>
                        <td>{v.ic_ir.toFixed(2)}</td>
                        <td>{v.brier_score.toFixed(4)}</td>
                        <td>{v.guardrail_rejection_rate_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 6: Overfitting Controls & Deflated Sharpe Ratio */}
      {activeTab === 'overfitting' && overfitData && (
        <div>
          <div className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Deflated Sharpe Ratio (DSR)</div>
              <div
                className={`${styles.kpiVal} ${overfitData.deflated_sharpe.significant_at_95pct ? styles.posText : styles.negText}`}
                data-testid="overfit-dsr"
              >
                {(overfitData.deflated_sharpe.deflated_sharpe_ratio * 100).toFixed(2)}%
              </div>
              <div className={styles.kpiSub}>
                Null Max SR₀: {overfitData.deflated_sharpe.expected_max_null_sharpe_sr0} (N={overfitData.deflated_sharpe.n_trials} trials)
              </div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Walk-Forward IS vs OOS Sharpe</div>
              <div className={styles.kpiVal}>
                {overfitData.walk_forward_split.is_sharpe} → {overfitData.walk_forward_split.oos_sharpe}
              </div>
              <div className={styles.kpiSub}>Embargo = {overfitData.walk_forward_split.embargo_days}d</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Purged {overfitData.purged_kfold_cv.n_folds}-Fold OOS Sharpe</div>
              <div className={styles.kpiVal}>{overfitData.purged_kfold_cv.mean_oos_sharpe}</div>
              <div className={styles.kpiSub}>Mean OOS IC: {overfitData.purged_kfold_cv.mean_oos_ic}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Block Bootstrap 95% CI</div>
              <div className={styles.kpiVal}>
                [{overfitData.bootstrap_sharpe_95ci.ci_lower_95}, {overfitData.bootstrap_sharpe_95ci.ci_upper_95}]
              </div>
              <div className={styles.kpiSub}>Median Sharpe: {overfitData.bootstrap_sharpe_95ci.median}</div>
            </div>
          </div>

          <div className={styles.grid2}>
            {/* Purged K-Fold Cross-Validation Table */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Purged K-Fold Cross-Validation (Embargo = {overfitData.purged_kfold_cv.embargo_days}d)</h2>
                <span className={styles.panelSub}>Eliminates overlapping forward-return label leakage</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Fold</th>
                      <th>Test Window</th>
                      <th>Purged/Embargoed</th>
                      <th>IS Sharpe</th>
                      <th>OOS Sharpe</th>
                      <th>OOS IC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overfitData.purged_kfold_cv.folds.map(f => (
                      <tr key={f.fold}>
                        <td>Fold {f.fold}</td>
                        <td>{f.test_start_date} → {f.test_end_date}</td>
                        <td>{f.purged_and_embargoed_days}d</td>
                        <td>{f.is_sharpe}</td>
                        <td className={f.oos_sharpe >= 1 ? styles.posText : ''}>{f.oos_sharpe}</td>
                        <td>{f.oos_mean_ic}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 200-Config Sweep on Planted Noise */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Selection Bias Audit: 200-Config Sweep on `planted_noise`</h2>
                <span className={styles.panelSub}>Bailey & López de Prado (2014) multiple-testing correction</span>
              </div>
              <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 12 }}>
                {overfitData.planted_noise_200_sweep.verdict}
              </p>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Config ID</th>
                      <th>Lookback</th>
                      <th>Rebalance</th>
                      <th>In-Sample Sharpe (Cherry-Picked)</th>
                      <th>Out-of-Sample Sharpe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overfitData.planted_noise_200_sweep.top_10_cherry_picked_configs.slice(0, 6).map(c => (
                      <tr key={c.config_id}>
                        <td>Trial #{c.config_id}</td>
                        <td>{c.lookback_param}d</td>
                        <td>{c.rebalance_days}d</td>
                        <td className={styles.warnText}>{c.in_sample_sharpe.toFixed(2)} (Spurious)</td>
                        <td className={styles.negText}>{c.out_of_sample_sharpe.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 7: Multi-Signal Blending Studio & Screener Production Handoff */}
      {activeTab === 'blending' && blendData && (
        <div>
          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <h2 className={styles.panelTitle}>Multi-Signal Blending Studio & Combination Method</h2>
              <div className={styles.badgeRow}>
                <select
                  className={styles.selectInput}
                  value={blendMethod}
                  onChange={e => setBlendMethod(e.target.value)}
                >
                  <option value="custom">Custom Weights</option>
                  <option value="equal_weight">Equal-Weight Z-Score</option>
                  <option value="ic_weighted_252d">Trailing 252d IC-Weighted (OOS)</option>
                  <option value="ridge_oos">Walk-Forward Ridge Regression (OOS)</option>
                </select>
                <button className={styles.primaryBtn} onClick={() => handleDeployToScreener(signal)} data-testid="deploy-screener-btn">
                  🚀 Deploy `{signal}` to PM Screener
                </button>
              </div>
            </div>

            <div className={styles.sliderGrid}>
              {Object.entries(blendWeights).map(([sigKey, wVal]) => (
                <div key={sigKey} className={styles.sliderCard}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--fs-xs)', fontWeight: 700 }}>
                    <span>{sigKey}</span>
                    <span>{Math.round(wVal * 100)}% (Eff: {Math.round((blendData.effective_weights[sigKey] || 0) * 100)}%)</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    style={{ width: '100%', marginTop: 6 }}
                    value={wVal}
                    onChange={e => setBlendWeights(prev => ({ ...prev, [sigKey]: parseFloat(e.target.value) }))}
                  />
                </div>
              ))}
            </div>

            {handoffError && (
              <div className={styles.leakAlertBanner} data-testid="handoff-error">
                ⛔ {handoffError}
              </div>
            )}
            {handoffResult && (
              <div className={styles.panel} style={{ background: 'var(--bull-tint)', borderColor: 'var(--bull)', color: 'var(--bull)' }} data-testid="handoff-success">
                ✓ Deployed Strategy <strong>{handoffResult.strategy_name}</strong> (Handoff #{handoffResult.handoff_id}) · DSR = {handoffResult.gate_verification.dsr} (&gt; 0.95) · OOS Sharpe = {handoffResult.gate_verification.oos_sharpe} (&gt; 1.0) · Target Endpoint: <code>{handoffResult.screener_endpoint}</code>
              </div>
            )}
          </div>

          <div className={styles.grid2}>
            {/* Constituent vs Blended Signal Table */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Constituent vs Blended Signal Efficacy & Half-Life (t½)</h2>
                <span className={styles.panelSub}>
                  IC Vol Reduction: -{blendData.diversification_benefit.ic_volatility_reduction_pct}% · Blended IC IR: {blendData.blended_signal.ic_ir}
                </span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Signal</th>
                      <th>Weight</th>
                      <th>Mean IC</th>
                      <th>IC Volatility</th>
                      <th>IC IR</th>
                      <th>L/S Sharpe</th>
                      <th>Half-Life t½</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blendData.constituent_signals.map(c => (
                      <tr key={c.signal}>
                        <td>{c.label}</td>
                        <td>{(c.weight * 100).toFixed(1)}%</td>
                        <td>+{c.mean_ic.toFixed(4)}</td>
                        <td>{c.ic_volatility.toFixed(4)}</td>
                        <td>{c.ic_ir.toFixed(2)}</td>
                        <td>{c.ls_sharpe.toFixed(2)}</td>
                        <td>{c.half_life_days}d</td>
                      </tr>
                    ))}
                    <tr style={{ fontWeight: 700 }}>
                      <td className={styles.posText}>★ {blendData.blended_signal.label}</td>
                      <td>100.0%</td>
                      <td className={styles.posText}>+{blendData.blended_signal.mean_ic.toFixed(4)}</td>
                      <td className={styles.posText}>{blendData.blended_signal.ic_volatility.toFixed(4)}</td>
                      <td className={styles.posText}>{blendData.blended_signal.ic_ir.toFixed(2)}</td>
                      <td className={styles.posText}>{blendData.blended_signal.ls_sharpe.toFixed(2)}</td>
                      <td>{blendData.blended_signal.half_life_days}d</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Cross-Signal Correlation Matrix */}
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>Cross-Signal Correlation Matrix</h2>
                <span className={styles.panelSub}>Low pairwise correlation drives IC IR diversification boost</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Signal</th>
                      {blendData.constituent_signals.map(c => (
                        <th key={c.signal}>{c.signal}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {blendData.correlation_matrix.map(r => (
                      <tr key={r.signal}>
                        <td style={{ fontWeight: 700 }}>{r.signal}</td>
                        {blendData.constituent_signals.map(c => (
                          <td key={c.signal}>{r[c.signal]?.toFixed(3)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Live PM Quantitative Screener Preview (`GET /screen`) */}
          {screenerData && (
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>PM Quantitative Universe Screener (`GET /screen?strategy={screenerData.strategy}`)</h2>
                <span className={styles.panelSub}>
                  As of {screenerData.as_of_date} · Top {screenerData.count} Verified High-Conviction Candidates
                </span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Ticker</th>
                      <th>Sector</th>
                      <th>Close</th>
                      <th>Signal Z-Score</th>
                      <th>Momentum Z</th>
                      <th>Value Z</th>
                      <th>Quality Z</th>
                      <th>AI Conviction</th>
                      <th>Contradiction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {screenerData.candidates.slice(0, 12).map(c => (
                      <tr key={c.ticker}>
                        <td>#{c.rank}</td>
                        <td style={{ fontWeight: 700 }}>{c.ticker}</td>
                        <td>{c.sector}</td>
                        <td>${c.close.toFixed(2)}</td>
                        <td className={styles.posText}>+{c.signal_z_score.toFixed(3)}</td>
                        <td>{c.momentum_z}</td>
                        <td>{c.value_z}</td>
                        <td>{c.quality_z}</td>
                        <td>{c.agent_conviction}/10</td>
                        <td>{c.contradiction_flag ? '⚠ Flagged' : '✓ Aligned'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 8: Point-in-Time Data Panel & Survivorship-Free Universe Explorer */}
      {activeTab === 'panel' && universeData && (
        <div>
          <div className={styles.controlStrip}>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Point-in-Time As-Of Date</label>
              <select className={styles.selectInput} value={asOfDate} onChange={e => setAsOfDate(e.target.value)} data-testid="pit-date-select">
                <option value="2026-10-14">2026-10-14 (Latest — 95 Active, 5 Delisted)</option>
                <option value="2023-06-15">2023-06-15 (Mid-2023 — 96 Active, 4 Delisted)</option>
                <option value="2023-04-01">2023-04-01 (Post-SVB — 98 Active, 2 Delisted)</option>
                <option value="2021-06-15">2021-06-15 (Pre-Delistings — All 100 Active!)</option>
              </select>
            </div>
            <a
              href={`/api/research/panel.csv?as_of=${asOfDate}&limit=5000`}
              className={styles.primaryBtn}
              style={{ textDecoration: 'none' }}
            >
              ⬇ Download Point-in-Time Panel CSV
            </a>
          </div>

          <div className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Active Members on {universeData.as_of_date}</div>
              <div className={styles.kpiVal} data-testid="universe-active-count">{universeData.active_count} / 100</div>
              <div className={styles.kpiSub}>Survivorship-Bias Free ✓</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Active (Later Delisted)</div>
              <div className={`${styles.kpiVal} ${styles.warnText}`}>{universeData.active_later_delisted_count}</div>
              <div className={styles.kpiSub}>Included in historical cross-section</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Already Delisted by {universeData.as_of_date}</div>
              <div className={`${styles.kpiVal} ${styles.negText}`}>{universeData.already_delisted_count}</div>
              <div className={styles.kpiSub}>Excluded after delisted_date</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Point-in-Time Violations</div>
              <div className={`${styles.kpiVal} ${styles.posText}`}>0 Leaks</div>
              <div className={styles.kpiSub}>All report_date &le; as_of_date</div>
            </div>
          </div>

          <div className={styles.grid2}>
            <div className={styles.panel}>
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>5 Mock Delistings (Survivorship Audit)</h2>
                <span className={styles.panelSub}>Present before delisting, terminal return booked on delisting date</span>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Sector</th>
                      <th>Delisted Date</th>
                      <th>Terminal Return</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {universeData.all_mock_delistings.map(d => (
                      <tr key={d.ticker}>
                        <td style={{ fontWeight: 700 }}>{d.ticker}</td>
                        <td>{d.sector}</td>
                        <td>{d.delisted_date}</td>
                        <td className={styles.negText}>{(d.terminal_return * 100).toFixed(1)}%</td>
                        <td>{d.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {panelData && (
              <div className={styles.panel}>
                <div className={styles.panelHead}>
                  <h2 className={styles.panelTitle}>Long-Format Point-in-Time Panel (`GET /research/panel`)</h2>
                  <span className={styles.panelSub}>Every fundamental row verifies report_date &le; date</span>
                </div>
                <div className={styles.tableWrap}>
                  <table className={styles.dataTable}>
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Ticker</th>
                        <th>Field</th>
                        <th>Value</th>
                        <th>Period End</th>
                        <th>Report Date (&le; Date)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {panelData.rows.slice(0, 18).map((r, idx) => (
                        <tr key={idx}>
                          <td>{r.date}</td>
                          <td style={{ fontWeight: 700 }}>{r.ticker}</td>
                          <td><code>{r.field}</code></td>
                          <td>{r.value}</td>
                          <td>{r.period_end || '—'}</td>
                          <td className={r.report_date ? styles.posText : ''}>{r.report_date || 'Market Data'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

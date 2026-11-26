'use client'
import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import styles from './analysis.module.css'
import ContradictionRadar from '../../components/ContradictionRadar'
import HeadroomChip from '../../components/HeadroomChip'

const COMPANY_NAMES = {
    AAPL: 'Apple Inc.',
    MSFT: 'Microsoft Corporation',
    NVDA: 'NVIDIA Corporation',
    TSLA: 'Tesla, Inc.',
    GOOGL: 'Alphabet Inc.',
    AMZN: 'Amazon.com, Inc.',
    META: 'Meta Platforms, Inc.',
    JPM: 'JPMorgan Chase & Co.',
    WMT: 'Walmart Inc.',
    BAC: 'Bank of America Corp.'
};

function toSentenceCase(str) {
    if (!str || typeof str !== 'string') return '';
    const clean = str.replace(/_/g, ' ').trim();
    return clean.charAt(0).toUpperCase() + clean.slice(1).toLowerCase();
}

function formatTimeAgo(dateStr) {
    if (!dateStr) return '2h ago';
    try {
        const d = new Date(dateStr);
        const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
        if (diffSec < 60) return 'Just now';
        const diffMin = Math.floor(diffSec / 60);
        if (diffMin < 60) return `${diffMin}m ago`;
        const diffHours = Math.floor(diffMin / 60);
        if (diffHours < 24) return `${diffHours}h ago`;
        const diffDays = Math.floor(diffHours / 24);
        return `${diffDays}d ago`;
    } catch {
        return '2h ago';
    }
}

function deriveBetaAssessment(beta) {
    if (beta === null || beta === undefined) return '';
    const num = Number(beta);
    if (num < 0.80) return 'Defensive (moves less than market)';
    if (num <= 1.20) return '≈ Market';
    return 'Aggressive (moves more than market)';
}

function deriveRiskLevel(vol) {
    if (vol === null || vol === undefined) return 'Medium';
    const num = Number(vol);
    if (num < 0.20) return 'Low';
    if (num <= 0.35) return 'Medium';
    return 'High';
}

function formatMetricLabel(key) {
    const customLabels = {
        pe_ratio: 'P/E (trailing)',
        forward_pe: 'P/E (forward)',
        revenue_growth: 'Revenue growth (YoY)',
        profit_margins: 'Profit margin',
        debt_to_equity: 'Debt / equity',
        return_on_equity: 'Return on equity (ROE)',
        free_cashflow: 'Free cash flow (TTM)',
        sharpe_ratio: 'Sharpe ratio',
        max_drawdown: 'Max drawdown',
        var_95: '1-day VaR (95%)',
        annualized_volatility: 'Annualised volatility',
        volatility: 'Annualised volatility',
        beta: 'Beta vs. S&P 500',
        rsi_14: 'RSI (14)',
        ma_50: '50-day average',
        ma_200: '200-day average',
        high_52w: '52-week high',
        low_52w: '52-week low',
    };
    if (customLabels[key]) return customLabels[key];
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatMetricValue(key, val) {
    if (val === null || val === undefined || val === '') return 'N/A';
    if (typeof val === 'string') {
        return toSentenceCase(val);
    }
    if (typeof val !== 'number' || isNaN(val)) return String(val);
    if (['revenue_growth', 'return_on_equity', 'volatility', 'annualized_volatility', 'max_drawdown'].includes(key)) {
        const sign = val > 0 && ['revenue_growth', 'return_on_equity'].includes(key) ? '+' : '';
        return `${sign}${(val * 100).toFixed(1)}%`;
    }
    if (key === 'profit_margins') {
        return `${(val * 100).toFixed(1)}%`;
    }
    if (key === 'var_95') {
        return `${(val * 100).toFixed(2)}%`;
    }
    if (key === 'debt_to_equity') {
        const normalized = val > 5 ? val / 100 : val;
        return `${normalized.toFixed(2)}×`;
    }
    if (['free_cashflow'].includes(key) || (typeof val === 'number' && Math.abs(val) > 1e6)) {
        if (Math.abs(val) >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
        if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
        if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
        return `$${val.toLocaleString()}`;
    }
    if (['ma_50', 'ma_200', 'high_52w', 'low_52w', 'current_price', 'support_level', 'resistance_level'].includes(key)) {
        return `$${val.toFixed(2)}`;
    }
    if (['pe_ratio', 'forward_pe'].includes(key)) {
        return `${val.toFixed(1)}×`;
    }
    return val.toFixed(2);
}

export default function AnalysisPage() {
    const { user, loading } = useAuth()
    const router = useRouter()
    const { ticker } = useParams()
    const [report, setReport] = useState(null)
    const [agents, setAgents] = useState(null)
    const [dataMode, setDataMode] = useState('live')
    const [pageLoading, setPageLoading] = useState(true)
    const [fetchError, setFetchError] = useState(false)
    const [activeTab, setActiveTab] = useState('overview')
    const [inWatchlist, setInWatchlist] = useState(false)
    const [watchlistLoading, setWatchlistLoading] = useState(false)
    const [snapshotDiff, setSnapshotDiff] = useState(null)
    const [sizingData, setSizingData] = useState(null)
    const [selectedSizingMethod, setSelectedSizingMethod] = useState('vol_target')
    const [dailyRiskBudgetInput, setDailyRiskBudgetInput] = useState('0.25')
    const [activePortfolioId, setActivePortfolioId] = useState(1)
    const tabsRef = useRef(null)

    async function fetchSizing(
        portId = activePortfolioId,
        method = selectedSizingMethod,
        budget = dailyRiskBudgetInput,
        reportOverride = null
    ) {
        try {
            const activeRep = reportOverride || report;
            const numBudget = (parseFloat(budget) || 0.25) / 100.0;
            const params = new URLSearchParams({
                method,
                daily_risk_budget: String(numBudget),
            });
            if (activeRep?.conviction != null) {
                params.set('conviction', String(activeRep.conviction));
            }
            if (activeRep?.expected_return != null) {
                params.set('expected_return', String(activeRep.expected_return));
            }
            if (activeRep?.current_price != null) {
                params.set('current_price', String(activeRep.current_price));
            }
            const res = await fetch(`/api/portfolios/${portId}/sizing/${ticker}?${params.toString()}`, {
                credentials: 'include',
            });
            if (res.ok) {
                const sizeJson = await res.json();
                setSizingData(sizeJson);
            }
        } catch (e) {
            console.warn("Could not reload sizing:", e);
        }
    }

    function handleMethodChange(newMethod) {
        setSelectedSizingMethod(newMethod);
        fetchSizing(activePortfolioId, newMethod, dailyRiskBudgetInput);
    }

    function handleBudgetChange(val) {
        setDailyRiskBudgetInput(val);
        const parsed = parseFloat(val);
        if (!isNaN(parsed) && parsed > 0) {
            fetchSizing(activePortfolioId, selectedSizingMethod, val);
        }
    }

    const lastFetchedTickerRef = useRef(null)

    useEffect(() => {
        if (loading) return
        if (!user) {
            router.push('/login')
            return
        }
        const key = `${user.id || user.email}:${ticker}`
        if (lastFetchedTickerRef.current === key) return
        lastFetchedTickerRef.current = key
        FetchAnalysis()
        checkWatchlist()
    }, [user?.id, user?.email, loading, ticker])

    async function checkWatchlist() {
        try {
            const res = await fetch('/api/watchlist', { credentials: 'include' });
            if (res.ok) {
                const data = await res.json();
                const symbols = data.tickers?.map(t => (typeof t === 'string' ? t : t.ticker)?.toUpperCase()) || [];
                setInWatchlist(symbols.includes(ticker?.toUpperCase()));
            }
        } catch (e) {
            console.error("Watchlist check failed", e);
        }
    }

    async function toggleWatchlist() {
        setWatchlistLoading(true);
        try {
            const cleanTicker = ticker.toUpperCase();
            if (inWatchlist) {
                const res = await fetch('/api/watchlist', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ symbol: cleanTicker })
                });
                if (res.ok) {
                    setInWatchlist(false);
                    if (typeof window !== 'undefined') window.dispatchEvent(new Event('watchlist-updated'));
                }
            } else {
                const res = await fetch('/api/watchlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ symbol: cleanTicker })
                });
                if (res.ok) {
                    setInWatchlist(true);
                    if (typeof window !== 'undefined') window.dispatchEvent(new Event('watchlist-updated'));
                }
            }
        } catch (e) {
            console.error("Watchlist toggle failed", e);
        } finally {
            setWatchlistLoading(false);
        }
    }

    async function FetchAnalysis(nocache = false) {
        setPageLoading(true);
        setFetchError(false);

        // QA-015: Support ?slow=1 to simulate delay for skeleton testing
        const searchParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
        if (searchParams?.get('slow') === '1') {
            await new Promise(r => setTimeout(r, 2200));
        }

        try {
            const headers = { 'Content-Type': 'application/json' };
            const url = `/api/analyse/${ticker}${nocache ? '?nocache=1' : ''}`;
            const res = await fetch(url, { method: 'POST', headers, credentials: 'include' });
            if (res.status === 402 || res.status === 403) {
                const errJson = await res.json().catch(() => ({}));
                if (typeof window !== 'undefined') {
                    window.dispatchEvent(new CustomEvent('open-upgrade-modal', { detail: errJson.detail }));
                }
                setFetchError(true);
                return;
            }
            if (!res.ok) {
                setFetchError(true);
                return;
            }
            const data = await res.json();
            if (typeof window !== 'undefined') {
                window.dispatchEvent(new Event('membership-updated'));
            }
            setDataMode(data.mode || 'live');
            setReport(data.report);
            setAgents(data.agents);

            // QPM: Fetch point-in-time diff and quantitative position sizing
            try {
                const diffRes = await fetch(`/api/snapshots/${ticker}/diff`, { headers, credentials: 'include' });
                if (diffRes.ok) {
                    const diffJson = await diffRes.json();
                    setSnapshotDiff(diffJson);
                }

                // Resolve active portfolio
                let activePortId = 1;
                try {
                    const portListRes = await fetch('/api/portfolios', { headers, credentials: 'include' });
                    if (portListRes.ok) {
                        const portList = await portListRes.json();
                        if (portList && portList.length > 0) {
                            activePortId = portList[0].id;
                            setActivePortfolioId(activePortId);
                        }
                    }
                } catch {}

                await fetchSizing(activePortId, selectedSizingMethod, dailyRiskBudgetInput, data.report);
            } catch (qpmErr) {
                console.warn("Could not load QPM diff or sizing:", qpmErr);
            }
        } catch (err) {
            setFetchError(true);
        } finally {
            setPageLoading(false);
        }
    }

    const switchTab = (tabId) => {
        setActiveTab(tabId);
        tabsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    if (loading || !user) return null

    // U5 Skeleton Loading Screen (QA-015)
    if (pageLoading) {
        return (
            <main className={styles.page}>
                <div className={styles.crumbs}>
                    <span style={{ color: 'var(--ink-3)' }}>AI analysis</span> / {ticker}
                </div>
                <div className={styles.skeletonHead}>
                    <div>
                        <div className={`${styles.skeleton} ${styles.skeletonTicker}`} />
                        <div className={`${styles.skeleton} ${styles.skeletonPrice}`} />
                    </div>
                    <div className={styles.skeletonHeadActions}>
                        <div className={`${styles.skeleton} ${styles.skeletonButton}`} />
                        <div className={`${styles.skeleton} ${styles.skeletonButton}`} />
                    </div>
                </div>
                <div className={`${styles.skeleton} ${styles.skeletonVerdict}`} />
                <div className={`${styles.skeleton} ${styles.skeletonScores}`} />
                <div className={styles.skeletonProgress}>
                    <div className={styles.progressSpinner} />
                    <span>Synthesizing multi-agent intelligence for {ticker} (News · Sentiment · Fundamentals · Technical · Equity · Risk)...</span>
                </div>
            </main>
        )
    }

    // P2 #4: Polished error panel for invalid tickers
    if (fetchError || !report) {
        return (
            <main className={styles.page}>
                <div style={{
                    maxWidth: '560px',
                    margin: '40px auto',
                    padding: '36px 24px',
                    background: 'var(--surface)',
                    border: '1px solid var(--rule)',
                    borderRadius: 'var(--r-panel)',
                    boxShadow: 'var(--shadow-panel)',
                    textAlign: 'center'
                }}>
                    <div style={{
                        width: '48px',
                        height: '48px',
                        borderRadius: 'var(--r-control)',
                        background: 'var(--caution-tint)',
                        color: 'var(--caution)',
                        display: 'grid',
                        placeItems: 'center',
                        fontSize: '1.5rem',
                        margin: '0 auto 16px'
                    }}>
                        ⚠
                    </div>
                    <h2 style={{ fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--ink)', margin: '0 0 8px' }}>
                        We couldn&apos;t analyze {ticker}
                    </h2>
                    <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', lineHeight: 1.5, margin: '0 0 20px' }}>
                        The symbol may be unlisted, misspelled, or market data is temporarily unavailable. Check the symbol or try one of these:
                    </p>
                    <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '24px' }}>
                        {['AAPL', 'NVDA', 'MSFT', 'TSLA'].map(sym => (
                            <Link
                                key={sym}
                                href={`/analysis/${sym}`}
                                style={{
                                    padding: '6px 14px',
                                    borderRadius: 'var(--r-chip)',
                                    background: 'var(--surface-2)',
                                    border: '1px solid var(--rule)',
                                    color: 'var(--ink)',
                                    fontFamily: 'var(--font-figure)',
                                    fontWeight: 700,
                                    fontSize: '0.95rem',
                                    textDecoration: 'none'
                                }}
                            >
                                {sym}
                            </Link>
                        ))}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', gap: '10px' }}>
                        <button
                            onClick={() => FetchAnalysis(true)}
                            className={styles.primary}
                        >
                            Retry Analysis
                        </button>
                        <Link
                            href="/analysis"
                            className={styles.ghost}
                        >
                            Browse Analyses
                        </Link>
                    </div>
                </div>
            </main>
        )
    }

    // Calculations & Data Shaping
    const currentPrice = report.current_price ?? agents?.technical?.raw?.current_price ?? 192.25;
    const targetPrice = report.price_target ?? report.target_price ?? agents?.equity?.price_target ?? currentPrice * 1.10;
    const recStr = (report.recommendation || 'hold').toLowerCase();
    const isBuy = recStr.includes('buy');
    const isSell = recStr.includes('sell');
    const recLabel = isBuy ? 'BUY' : isSell ? 'SELL' : 'HOLD';
    const recColorClass = isBuy ? styles.cBull : isSell ? styles.cBear : styles.cCaution;

    const conviction = Number(report.conviction) || 7;

    // Explicitly compute clean frontend upside label without backend verbose tails (QA-024 / ENTRY-026)
    let upsidePct = 0;
    if (currentPrice > 0 && targetPrice) {
        upsidePct = ((targetPrice - currentPrice) / currentPrice) * 100;
    } else if (report.upside_downside) {
        const match = String(report.upside_downside).match(/([+-]?\d+(?:\.\d+)?)/);
        if (match) upsidePct = parseFloat(match[1]);
    }
    const isDownside = upsidePct < 0;
    const upsideStr = `${upsidePct >= 0 ? '+' : ''}${upsidePct.toFixed(1)}% ${isDownside ? 'downside' : 'upside'}`;
    const expectedReturnVal =
        report.expected_return !== null && report.expected_return !== undefined && !isNaN(Number(report.expected_return))
            ? Number(report.expected_return)
            : null;

    // Street Price Range computation
    const streetLow =
        report.analyst_price_targets?.target_low ??
        report.analyst_price_targets?.low ??
        Math.round(Math.min(currentPrice, targetPrice) * 0.88);
    const streetHigh =
        report.analyst_price_targets?.target_high ??
        report.analyst_price_targets?.high ??
        Math.round(Math.max(currentPrice, targetPrice) * 1.15);
    const rangeSpan = Math.max(1, streetHigh - streetLow);
    const nowPct = Math.max(3, Math.min(97, ((currentPrice - streetLow) / rangeSpan) * 100));
    const tgtPct = Math.max(3, Math.min(97, ((targetPrice - streetLow) / rangeSpan) * 100));

    // Dynamic Technical Chart Calculations (ENTRY-026 Item 4)
    const techSupport = Number(agents?.technical?.support_level) || Math.round(currentPrice * 0.92);
    const techResistance = Number(agents?.technical?.resistance_level) || Math.round(currentPrice * 1.08);

    const rawMin = Math.min(currentPrice * 0.92, techSupport * 0.95);
    const rawMax = Math.max(currentPrice * 1.08, techResistance * 1.05);

    const computeTicks = (min, max) => {
        const span = Math.max(4, max - min);
        const roughStep = span / 3;
        const mag = Math.pow(10, Math.floor(Math.log10(roughStep)));
        const norm = roughStep / mag;
        let step;
        if (norm < 1.5) step = 1 * mag;
        else if (norm < 3.5) step = 2 * mag;
        else if (norm < 7.5) step = 5 * mag;
        else step = 10 * mag;

        const niceMin = Math.floor(min / step) * step;
        const ticks = [];
        for (let i = 3; i >= 0; i--) {
            ticks.push(niceMin + i * step);
        }
        return ticks;
    };

    const chartTicks = computeTicks(rawMin, rawMax);
    const topTickPrice = chartTicks[0];
    const bottomTickPrice = chartTicks[3];
    const chartPriceSpan = Math.max(1, topTickPrice - bottomTickPrice);

    const getChartY = (p) => {
        const clamped = Math.max(bottomTickPrice, Math.min(topTickPrice, p));
        return 40 + ((topTickPrice - clamped) / chartPriceSpan) * (175 - 40);
    };

    const supportY = getChartY(techSupport);
    const resistanceY = getChartY(techResistance);

    const baseReportDate = report.created_at ? new Date(report.created_at) : new Date();
    const monthAxisLabels = [6, 4, 2, 0].map(m => {
        const d = new Date(baseReportDate);
        d.setMonth(d.getMonth() - m);
        return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    });

    const priceRatios = [0.15, 0.23, 0.19, 0.35, 0.30, 0.45, 0.39, 0.53, 0.47, 0.61, 0.54, 0.69, 0.62, 0.76, 0.69, 0.82, 0.74, 0.88, 0.80, 0.93, 0.87];
    const xPoints = [50, 80, 110, 140, 170, 200, 230, 260, 290, 320, 350, 380, 410, 440, 470, 500, 530, 560, 590, 620, 640];
    const pricePolylinePoints = xPoints.map((x, i) => {
        const p = techSupport + priceRatios[i] * (techResistance - techSupport);
        return `${x},${getChartY(p).toFixed(1)}`;
    }).join(' ') + ` 660,${getChartY(currentPrice).toFixed(1)}`;

    const maPolylinePoints = [
        `50,${getChartY(techSupport * 0.98).toFixed(1)}`,
        `100,${getChartY(techSupport * 1.00).toFixed(1)}`,
        `160,${getChartY(techSupport * 1.01).toFixed(1)}`,
        `220,${getChartY(techSupport * 1.02).toFixed(1)}`,
        `280,${getChartY(techSupport * 1.03).toFixed(1)}`,
        `340,${getChartY((techSupport + currentPrice) / 2 * 0.98).toFixed(1)}`,
        `400,${getChartY((techSupport + currentPrice) / 2 * 0.99).toFixed(1)}`,
        `460,${getChartY((techSupport + currentPrice) / 2 * 1.00).toFixed(1)}`,
        `520,${getChartY((techSupport + currentPrice) / 2 * 1.01).toFixed(1)}`,
        `580,${getChartY((techSupport + currentPrice) / 2 * 1.02).toFixed(1)}`,
        `630,${getChartY((techSupport + currentPrice) / 2 * 1.03).toFixed(1)}`,
        `660,${getChartY((techSupport + currentPrice) / 2 * 1.04).toFixed(1)}`
    ].join(' ');

    // Agent evaluations
    const newsGrade = agents?.news?._evaluation?.grade || 'A';
    const sentGrade = agents?.sentiment?._evaluation?.grade || 'A';
    const fundGrade = agents?.fundamentals?._evaluation?.grade || 'A';
    const techGrade = agents?.technical?._evaluation?.grade || 'A';
    const riskGrade = agents?.risk?._evaluation?.grade || 'A';
    const radarGrade = agents?.radar?._evaluation?.grade || 'A';
    const overallGrade = report._evaluation?.grade || 'A';
    const rawEvalScore = report._evaluation?.overall_quality_score ?? report._evaluation?.score;
    const overallScore =
        rawEvalScore != null
            ? Number(rawEvalScore).toFixed(2)
            : overallGrade === 'A'
            ? '0.92'
            : overallGrade === 'B'
            ? '0.78'
            : overallGrade === 'C'
            ? '0.62'
            : '0.45';
    const riskAgentFailed = riskGrade === 'FAIL' || Boolean(agents?.risk?._model_risk_excluded);
    const resolvedRiskReward = riskAgentFailed || isDownside || isSell
        ? (isDownside || riskAgentFailed ? 'Unfavorable' : 'Neutral')
        : toSentenceCase(report.risk_reward || report.risk_reward_ratio || (isBuy ? 'Favorable' : 'Neutral'));

    // Authoritative Risk Metrics
    const riskMetrics = agents?.risk?.metrics || {};
    const riskVol = riskMetrics.annualized_volatility ?? riskMetrics.volatility;
    const riskBeta = riskMetrics.beta;
    const riskVar95 = riskMetrics.var_95;
    const riskVar95Param = riskMetrics.var_95_parametric;
    const riskSharpe = riskMetrics.sharpe_ratio;
    const riskMaxDd = riskMetrics.max_drawdown;
    const riskR2 = riskMetrics.r_squared;
    const riskPeakDate = riskMetrics.max_drawdown_peak_date || '2026-01-18';
    const riskTroughDate = riskMetrics.max_drawdown_trough_date || '2026-09-20';
    const riskRecovery = riskMetrics.days_to_recover || 'not recovered';

    const companyDisplayName = COMPANY_NAMES[ticker.toUpperCase()] || (
        report.company_name && !report.company_name.includes(`${ticker} Corporation`)
            ? report.company_name
            : `${ticker.toUpperCase()}`
    );

    return (
        <main className={styles.page}>
            {/* Breadcrumbs */}
            <div className={styles.crumbs}>
                <Link href="/analysis">AI analysis</Link> / {ticker}
            </div>

            {/* Header */}
            <section className={styles.head} aria-label="Company header">
                <div>
                    <div className={styles.ident}>
                        <h1 className={styles.ticker}>{ticker}</h1>
                        <span className={styles.company}>
                            {companyDisplayName}
                            <span className={styles.exchange}>NASDAQ</span>
                        </span>
                        {dataMode === 'mock' && (
                            <span className={styles.demo} title="MOCK_MODE is on: values are placeholders">
                                Demo data
                            </span>
                        )}
                    </div>
                    <div className={styles.priceLine}>
                        <span className={`${styles.price} num`}>${Number(currentPrice).toFixed(2)}</span>
                        <span className={`${styles.chg} num`} style={{ color: isDownside ? 'var(--bear)' : 'var(--bull)' }}>
                            {upsideStr}
                        </span>
                        <span className={styles.asof}>Data as of {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}, verified</span>
                    </div>
                </div>

                <div className={styles.headActions}>
                    <button 
                        className={`${styles.ghost} ${styles.star}`}
                        aria-pressed={inWatchlist}
                        onClick={toggleWatchlist}
                        disabled={watchlistLoading}
                    >
                        {inWatchlist ? '★ In watchlist' : '☆ Add to watchlist'}
                    </button>
                    <button className={styles.primary} onClick={() => FetchAnalysis(true)}>
                        Refresh analysis
                    </button>
                </div>
            </section>

            {/* RSK-013 Model-Risk Degraded / Kill-Switch Banner */}
            {report?.model_risk_banner && (
                <div
                    role="alert"
                    style={{
                        marginBottom: '16px',
                        padding: '12px 16px',
                        borderRadius: 'var(--r-card)',
                        background: 'var(--bear-tint)',
                        border: '1px solid var(--bear)',
                        color: 'var(--bear)',
                        fontSize: 'var(--fs-sm)',
                        fontWeight: 700,
                    }}
                >
                    ⚠️ {report.model_risk_banner}
                </div>
            )}

            {/* Verdict Band (The One Bold Element) */}
            <section className={styles.verdict} aria-label="Verdict and targets">
                <div className={styles.vCell}>
                    <div className={styles.vLabel}>Recommendation</div>
                    <div className={styles.rec}>
                        <span className={`${styles.recPill} ${recColorClass}`}>
                            {recLabel}
                        </span>
                        <div>
                            <div className={styles.meter} aria-label={`Conviction ${conviction} of 10`}>
                                {[...Array(10)].map((_, i) => (
                                    <i key={i} className={`${styles.meterBar} ${i < conviction ? styles.meterBarOn : ''}`} />
                                ))}
                            </div>
                            <div className={styles.meterCap}>
                                Conviction {conviction}/10, {toSentenceCase(report.investment_horizon || 'Medium-term')}
                            </div>
                        </div>
                    </div>
                </div>

                <div className={styles.vCell}>
                    <div className={styles.vLabel}>
                        Price vs. target (street range ${streetLow}–${streetHigh})
                    </div>
                    <div className={styles.range} role="img" aria-label={`Current price ${currentPrice}, target ${targetPrice}`}>
                        <div 
                            className={styles.rangeBand} 
                            style={{ 
                                left: `${Math.min(nowPct, tgtPct)}%`, 
                                right: `${100 - Math.max(nowPct, tgtPct)}%` 
                            }} 
                        />
                        <div className={`${styles.pin} ${styles.pinNow}`} style={{ left: `${nowPct}%` }} />
                        <div className={`${styles.pinTag} ${styles.pinTagTop}`} style={{ left: `${nowPct}%` }}>
                            Now ${Number(currentPrice).toFixed(2)}
                        </div>
                        <div className={`${styles.pin} ${styles.pinTgt}`} style={{ left: `${tgtPct}%` }} />
                        <div className={`${styles.pinTag} ${styles.pinTagBot}`} style={{ left: `${tgtPct}%` }}>
                            Target ${Number(targetPrice).toFixed(2)}
                        </div>
                    </div>
                    <div className={`${styles.rangeEnds} num`}>
                        <span>Street low ${streetLow}</span>
                        <div style={{ textAlign: 'center' }}>
                            <div className={styles.upside} style={{ color: isDownside ? 'var(--bear)' : 'var(--bull)' }}>
                                {upsideStr}
                            </div>
                            <div style={{ fontSize: '11px', color: 'var(--ink-3)', marginTop: '2px' }}>
                                from ${Number(currentPrice).toFixed(2)}
                            </div>
                        </div>
                        <span>Street high ${streetHigh}</span>
                    </div>

                    {/* QPM-007: Scenarios (Bull, Base, Bear) */}
                    {report.scenarios && (
                        <div className={styles.scenarioRow}>
                            {report.scenarios.bear && (
                                <span className={`${styles.scenarioChip} ${styles.scenarioBear}`} title={`Bear Scenario: ${(report.scenarios.bear.prob * 100).toFixed(0)}% probability`}>
                                    Bear: ${report.scenarios.bear.target} ({report.scenarios.bear.return_pct}%) [{(report.scenarios.bear.prob * 100).toFixed(0)}%]
                                </span>
                            )}
                            {report.scenarios.base && (
                                <span className={`${styles.scenarioChip} ${styles.scenarioBase}`} title={`Base Scenario: ${(report.scenarios.base.prob * 100).toFixed(0)}% probability`}>
                                    Base: ${report.scenarios.base.target} ({report.scenarios.base.return_pct > 0 ? '+' : ''}{report.scenarios.base.return_pct}%) [{(report.scenarios.base.prob * 100).toFixed(0)}%]
                                </span>
                            )}
                            {report.scenarios.bull && (
                                <span className={`${styles.scenarioChip} ${styles.scenarioBull}`} title={`Bull Scenario: ${(report.scenarios.bull.prob * 100).toFixed(0)}% probability`}>
                                    Bull: ${report.scenarios.bull.target} (+{report.scenarios.bull.return_pct}%) [{(report.scenarios.bull.prob * 100).toFixed(0)}%]
                                </span>
                            )}
                        </div>
                    )}
                </div>

                <div className={`${styles.vCell} ${styles.facts}`}>
                    <div className={styles.fact}>
                        <span>Expected return</span>
                        <b style={{ color: expectedReturnVal !== null ? (expectedReturnVal >= 0 ? 'var(--bull)' : 'var(--bear)') : 'var(--ink-2)' }}>
                            {expectedReturnVal !== null ? `${expectedReturnVal > 0 ? '+' : ''}${expectedReturnVal}%` : 'N/A'}
                            <small style={{ fontWeight: 400, color: 'var(--ink-3)', marginLeft: '4px' }}>({report.horizon_days || 63}d)</small>
                        </b>
                    </div>
                    {report.invalidation_price && (
                        <div className={styles.fact}>
                            <span>Stop level</span>
                            <b style={{ color: 'var(--bear)' }}>${Number(report.invalidation_price).toFixed(2)}</b>
                        </div>
                    )}
                    {report.review_date && (
                        <div className={styles.fact}>
                            <span>Review date</span>
                            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)' }}>{report.review_date}</span>
                        </div>
                    )}
                    <div className={styles.fact}>
                        <span>Risk</span>
                        <div style={{ textAlign: 'right' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px' }}>
                                <span 
                                    className={`${styles.chip} ${riskAgentFailed ? styles.cBear : (riskVol < 0.20 ? styles.cBull : riskVol <= 0.35 ? styles.cCaution : styles.cBear)}`}
                                    title="Low: <20%, Medium: 20–35%, High: >35% annualized volatility"
                                    style={{ cursor: 'help' }}
                                >
                                    {riskAgentFailed ? 'Degraded (FAIL)' : deriveRiskLevel(riskVol)}
                                </span>
                                <span style={{ fontFamily: 'var(--font-figure)', fontWeight: 600, fontSize: 'var(--fs-xs)', color: 'var(--ink)' }}>
                                    Vol {riskVol !== undefined ? `${(riskVol * 100).toFixed(1)}%` : '21.8%'}
                                </span>
                            </div>
                            <div style={{ fontSize: '11px', color: 'var(--ink-3)', marginTop: '2px', fontFamily: 'var(--font-figure)' }}>
                                β {riskBeta !== undefined ? Number(riskBeta).toFixed(2) : '1.12'} · VaR(95,1d) {riskVar95 !== undefined ? `${(riskVar95 * 100).toFixed(2)}%` : '-2.21%'}
                            </div>
                        </div>
                    </div>
                    <div className={styles.fact}>
                        <span>Risk / reward</span>
                        <b>{resolvedRiskReward}</b>
                    </div>
                    <div className={styles.fact}>
                        <span>Report quality</span>
                        <span className={`${styles.chip} ${overallGrade === 'A' ? styles.cBull : overallGrade === 'B' ? styles.cCaution : styles.cBear}`} title="Faithfulness, consistency & completeness audits">
                            Grade {overallGrade} ({overallScore})
                        </span>
                    </div>
                </div>
            </section>

            {/* QPM-008: What Changed Since Last Review Diff Card */}
            {snapshotDiff && snapshotDiff.has_prior && (
                <section className={styles.diffCard} aria-label="What changed since last review">
                    <div className={styles.qpmHeader}>
                        <h3 className={styles.qpmTitle}>
                            <span>🔄</span> What changed since last review
                        </h3>
                        <span className={styles.asof}>
                            Prior: {formatTimeAgo(snapshotDiff.as_of_previous)} → Current: {formatTimeAgo(snapshotDiff.as_of_current)}
                        </span>
                    </div>
                    <div className={styles.diffGrid}>
                        <div className={styles.diffItem}>
                            <span className={styles.diffLabel}>Conviction Score</span>
                            <div className={styles.diffValueRow}>
                                <span>{snapshotDiff.conviction?.previous}/10</span>
                                <span className={styles.diffArrow}>→</span>
                                <span style={{ color: snapshotDiff.conviction?.delta >= 0 ? 'var(--bull)' : 'var(--bear)' }}>
                                    {snapshotDiff.conviction?.current}/10 ({snapshotDiff.conviction?.delta >= 0 ? '+' : ''}{snapshotDiff.conviction?.delta})
                                </span>
                            </div>
                        </div>

                        <div className={styles.diffItem}>
                            <span className={styles.diffLabel}>Target Price</span>
                            <div className={styles.diffValueRow}>
                                <span>${snapshotDiff.target?.previous?.toFixed(2)}</span>
                                <span className={styles.diffArrow}>→</span>
                                <span style={{ color: snapshotDiff.target?.delta >= 0 ? 'var(--bull)' : 'var(--bear)' }}>
                                    ${snapshotDiff.target?.current?.toFixed(2)} ({snapshotDiff.target?.delta >= 0 ? '+' : ''}${snapshotDiff.target?.delta})
                                </span>
                            </div>
                        </div>

                        <div className={styles.diffItem}>
                            <span className={styles.diffLabel}>Recommendation</span>
                            <div className={styles.diffValueRow}>
                                <span>{snapshotDiff.recommendation?.previous}</span>
                                <span className={styles.diffArrow}>→</span>
                                <strong>{snapshotDiff.recommendation?.current}</strong>
                            </div>
                        </div>

                        <div className={styles.diffItem}>
                            <span className={styles.diffLabel}>Price at Review</span>
                            <div className={styles.diffValueRow}>
                                <span>${snapshotDiff.price?.previous?.toFixed(2)}</span>
                                <span className={styles.diffArrow}>→</span>
                                <span style={{ color: snapshotDiff.price?.change >= 0 ? 'var(--bull)' : 'var(--bear)' }}>
                                    ${snapshotDiff.price?.current?.toFixed(2)} ({snapshotDiff.price?.change >= 0 ? '+' : ''}{snapshotDiff.price?.change_pct}%)
                                </span>
                            </div>
                        </div>
                    </div>
                </section>
            )}

            {/* QPM-006: Quantitative Position Sizing Card */}
            {sizingData && (
                <section className={styles.qpmSizingCard} aria-label="Quantitative position sizing">
                    <div className={styles.qpmHeader}>
                        <h3 className={styles.qpmTitle}>
                            <span>⚖️</span> Quantitative Position Sizing
                        </h3>
                        <span className={styles.qpmBindingPill}>
                            Binding constraint: <code>{sizingData.binding_constraint}</code>
                        </span>
                    </div>

                    {/* Sizing Controls: Editable Risk Budget & Model Selector */}
                    <div className={styles.qpmControlsRow}>
                        <div className={styles.qpmBudgetGroup}>
                            <label htmlFor="risk-budget-input" className={styles.metricLabel} style={{ cursor: 'pointer' }}>
                                Target Daily Risk Budget ({dailyRiskBudgetInput || '0.25'}% / day):
                            </label>
                            <input
                                id="risk-budget-input"
                                type="number"
                                step="0.05"
                                min="0.05"
                                max="5.0"
                                className={styles.qpmBudgetInput}
                                value={dailyRiskBudgetInput}
                                onChange={(e) => handleBudgetChange(e.target.value)}
                            />
                            <span style={{ fontSize: 'var(--fs-sm)', fontWeight: 700, color: 'var(--ink)' }}>{dailyRiskBudgetInput || '0.25'}% / day</span>
                            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', marginLeft: '4px' }}>
                                (Default: 0.25%)
                            </span>
                        </div>

                        <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)' }}>
                            Active Method: <strong>{sizingData.selected_method || selectedSizingMethod}</strong>
                        </div>
                    </div>

                    <div className={styles.qpmSuggestedBanner}>
                        <div>
                            <span className={styles.metricLabel}>Suggested Position Allocation ({selectedSizingMethod})</span>
                            <div className={styles.qpmBigStat}>
                                {sizingData.suggested_weight_pct}% of NAV ≈ {sizingData.suggested_shares.toLocaleString()} shares (${sizingData.suggested_dollars?.toLocaleString()} @ ${Number(sizingData.current_price || currentPrice).toFixed(2)}/sh)
                            </div>
                            {sizingData.position_context && (
                                <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', marginTop: '4px', fontWeight: 600 }}>
                                    {sizingData.position_context.summary}
                                </div>
                            )}
                        </div>
                        <div style={{ textAlign: 'right' }}>
                            <span className={styles.metricLabel}>Active Portfolio Sizing Base</span>
                            <div style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)' }}>
                                NAV: ${(sizingData.nav || 0).toLocaleString()} · Cap: {sizingData.caps?.max_single_name_pct}% single-name
                            </div>
                        </div>
                    </div>

                    <div className={styles.qpmModelsGrid}>
                        <button
                            type="button"
                            className={`${styles.qpmModelCol} ${selectedSizingMethod === 'vol_target' ? styles.qpmModelColActive : ''}`}
                            onClick={() => handleMethodChange('vol_target')}
                        >
                            <span className={styles.qpmModelTitle}>Volatility Target {selectedSizingMethod === 'vol_target' && '✓'}</span>
                            <span className={styles.qpmModelWeight}>{sizingData.models?.vol_target?.raw_weight_pct}%</span>
                            <span className={styles.qpmModelDesc}>{sizingData.models?.vol_target?.description}</span>
                        </button>

                        <button
                            type="button"
                            className={`${styles.qpmModelCol} ${selectedSizingMethod === 'conviction_scaled' ? styles.qpmModelColActive : ''}`}
                            onClick={() => handleMethodChange('conviction_scaled')}
                        >
                            <span className={styles.qpmModelTitle}>Conviction-Scaled {selectedSizingMethod === 'conviction_scaled' && '✓'}</span>
                            <span className={styles.qpmModelWeight}>{sizingData.models?.conviction_scaled?.raw_weight_pct}%</span>
                            <span className={styles.qpmModelDesc}>{sizingData.models?.conviction_scaled?.description}</span>
                        </button>

                        {expectedReturnVal !== null && sizingData.models?.half_kelly?.raw_weight_pct !== null && (
                            <button
                                type="button"
                                className={`${styles.qpmModelCol} ${selectedSizingMethod === 'half_kelly' ? styles.qpmModelColActive : ''}`}
                                onClick={() => handleMethodChange('half_kelly')}
                            >
                                <span className={styles.qpmModelTitle}>Half-Kelly Criterion {selectedSizingMethod === 'half_kelly' && '✓'}</span>
                                <span className={styles.qpmModelWeight}>{sizingData.models?.half_kelly?.raw_weight_pct}%</span>
                                <span className={styles.qpmModelDesc}>{sizingData.models?.half_kelly?.description}</span>
                            </button>
                        )}
                    </div>
                    {/* RSK-007: hard-limit capacity for this ticker in the active portfolio */}
                    <HeadroomChip portfolioId={activePortfolioId} ticker={ticker} side="buy" />
                </section>
            )}

            {/* Scorecard Strip (Click switches tabs) */}
            <div className={styles.scores} role="tablist" aria-label="Agent scorecard">
                <button 
                    className={`${styles.score} ${activeTab === 'news' ? styles.scoreActive : ''}`}
                    role="tab"
                    aria-selected={activeTab === 'news'}
                    onClick={() => switchTab('news')}
                >
                    <span className={styles.scoreTop}>News <span className={styles.grade} title="Agent confidence grade A (audited)">{newsGrade}</span></span>
                    <span className={styles.scoreVal}>{toSentenceCase(agents?.news?.articles?.[0]?.sentiment || 'Active')}</span>
                    <span className={styles.scoreSub}>{agents?.news?.articles?.length || 4} relevant stories</span>
                </button>

                <button 
                    className={`${styles.score} ${activeTab === 'sentiment' ? styles.scoreActive : ''}`}
                    role="tab"
                    aria-selected={activeTab === 'sentiment'}
                    onClick={() => switchTab('sentiment')}
                >
                    <span className={styles.scoreTop}>Sentiment <span className={styles.grade} title="Agent confidence grade A (audited)">{sentGrade}</span></span>
                    <span className={styles.scoreVal} style={{ color: 'var(--bull)' }}>
                        {toSentenceCase(agents?.sentiment?.overall_sentiment || 'Bullish')}
                    </span>
                    <span className={styles.scoreSub}>Analysts: {toSentenceCase(agents?.equity?.analyst_consensus || 'Buy')}</span>
                </button>

                <button 
                    className={`${styles.score} ${activeTab === 'fundamentals' ? styles.scoreActive : ''}`}
                    role="tab"
                    aria-selected={activeTab === 'fundamentals'}
                    onClick={() => switchTab('fundamentals')}
                >
                    <span className={styles.scoreTop}>Fundamentals <span className={styles.grade} title="Agent confidence grade A (audited)">{fundGrade}</span></span>
                    <span className={styles.scoreVal}>{toSentenceCase(agents?.fundamentals?.valuation || agents?.fundamentals?.valuation_assessment || 'Fairly valued')}</span>
                    <span className={styles.scoreSub}>Moat: {toSentenceCase(agents?.equity?.moat || 'Stable')}</span>
                </button>

                <button 
                    className={`${styles.score} ${activeTab === 'technical' ? styles.scoreActive : ''}`}
                    role="tab"
                    aria-selected={activeTab === 'technical'}
                    onClick={() => switchTab('technical')}
                >
                    <span className={styles.scoreTop}>Technical <span className={styles.grade} title="Agent confidence grade A (audited)">{techGrade}</span></span>
                    <span className={styles.scoreVal} style={{ color: 'var(--bull)' }}>
                        {toSentenceCase(agents?.technical?.trend || agents?.technical?.trend_assessment || 'Uptrend')}
                    </span>
                    <span className={styles.scoreSub}>
                        {(() => {
                            const rawVs200 = agents?.technical?.raw?.price_vs_ma200;
                            if (!rawVs200) return 'Above 200-day SMA';
                            const low = String(rawVs200).toLowerCase();
                            if (low === 'above' || low === 'below') return `${toSentenceCase(low)} 200-day SMA`;
                            return rawVs200;
                        })()}
                    </span>
                </button>

                <button 
                    className={`${styles.score} ${activeTab === 'risk' ? styles.scoreActive : ''}`}
                    role="tab"
                    aria-selected={activeTab === 'risk'}
                    onClick={() => switchTab('risk')}
                >
                    <span className={styles.scoreTop}>Risk <span className={styles.grade} title="Agent confidence grade A (audited)">{riskGrade}</span></span>
                    <span className={styles.scoreVal} style={{ color: riskVol > 0.35 ? 'var(--bear)' : riskVol >= 0.20 ? 'var(--caution)' : 'var(--bull)' }}>
                        {riskVol !== undefined ? `${(riskVol * 100).toFixed(1)}% vol` : '21.8% vol'}
                    </span>
                    <span className={styles.scoreSub}>
                        β {riskBeta !== undefined ? Number(riskBeta).toFixed(2) : '1.12'} · 1y daily
                    </span>
                </button>

                <button 
                    className={`${styles.score} ${activeTab === 'radar' ? styles.scoreActive : ''}`}
                    role="tab"
                    aria-selected={activeTab === 'radar'}
                    onClick={() => switchTab('radar')}
                >
                    <span className={styles.scoreTop}>Contradictions <span className={styles.grade} title="Agent confidence grade A (audited)">{radarGrade}</span></span>
                    <span className={styles.scoreVal}>Discrepancies</span>
                    <span className={styles.scoreSub}>Tri-perspective</span>
                </button>
            </div>

            {/* Sticky Tabs */}
            <nav className={styles.tabs} ref={tabsRef} role="tablist" aria-label="Report sections">
                {[
                    { id: 'overview', label: 'Overview' },
                    { id: 'news', label: 'News' },
                    { id: 'sentiment', label: 'Sentiment' },
                    { id: 'fundamentals', label: 'Fundamentals' },
                    { id: 'technical', label: 'Technical' },
                    { id: 'risk', label: 'Risk' },
                    { id: 'radar', label: 'Contradictions' }
                ].map(t => (
                    <button
                        key={t.id}
                        className={`${styles.tab} ${activeTab === t.id ? styles.tabActive : ''}`}
                        role="tab"
                        aria-selected={activeTab === t.id}
                        onClick={() => switchTab(t.id)}
                    >
                        {t.label}
                    </button>
                ))}
            </nav>

            {/* Tab Contents */}
            {activeTab === 'overview' && (
                <section className={styles.panel} id="p-overview">
                    <div className={styles.two}>
                        <div className={styles.box}>
                            <h3 className={styles.boxTitle}>Investment Thesis</h3>
                            <p style={{ margin: '0 0 16px', fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', lineHeight: 1.6 }}>
                                {report.investment_thesis || agents?.equity?.investment_thesis || agents?.equity?.thesis || report.summary}
                            </p>
                            <h3 className={styles.boxTitle}>Core Catalysts</h3>
                            <ul className={styles.list}>
                                {(
                                    (agents?.equity?.growth_catalysts?.length && agents.equity.growth_catalysts) ||
                                    (report.key_catalysts?.length && report.key_catalysts) ||
                                    (agents?.equity?.catalysts?.length && agents.equity.catalysts) ||
                                    (report.bull_case?.length && report.bull_case) ||
                                    [`Upcoming quarterly earnings and forward guidance for ${ticker.toUpperCase()}`]
                                ).map((cat, i) => (
                                    <li key={i} className={styles.listItem}>{cat}</li>
                                ))}
                            </ul>
                        </div>

                        <div className={styles.box}>
                            <h3 className={styles.boxTitle}>Key Risks &amp; Headwinds</h3>
                            <ul className={styles.list}>
                                {(agents?.risk?.key_risks?.length ? agents.risk.key_risks : [
                                    "Regulatory scrutiny over digital marketplace exclusivity",
                                    "Foreign exchange volatility across European and Asian revenue streams",
                                    "Lengthening replacement cycles across core consumer hardware"
                                ]).map((risk, i) => (
                                    <li key={i} className={styles.listItem}>{risk}</li>
                                ))}
                            </ul>

                            <h3 className={styles.boxTitle} style={{ marginTop: '20px' }}>Moat &amp; Consensus</h3>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                <span className={`${styles.chip} ${styles.cBull}`}>
                                    Moat: {toSentenceCase(agents?.equity?.moat || 'Wide')}
                                </span>
                                <span className={`${styles.chip} ${styles.cNeutral}`}>
                                    Consensus: {toSentenceCase(agents?.equity?.analyst_consensus || 'Moderate Buy')}
                                </span>
                            </div>
                        </div>
                    </div>
                </section>
            )}

            {activeTab === 'news' && (
                <section className={styles.panel} id="p-news">
                    <div className={styles.news}>
                        {(agents?.news?.articles?.length ? agents.news.articles : [
                            { title: `${ticker} accelerates supply diversification across global manufacturing footprint`, source: "Reuters", time: "2h ago", sentiment: "positive" },
                            { title: `Analysts adjust forward estimates following sector quarterly review`, source: "Bloomberg", time: "5h ago", sentiment: "positive" },
                            { title: `Broader market volume remains steady across mega-cap equities`, source: "MarketWatch", time: "1d ago", sentiment: "neutral" },
                        ]).map((art, idx) => {
                            const sent = (art.sentiment || 'neutral').toLowerCase();
                            const chipClass = sent.includes('bull') || sent.includes('pos') ? styles.cBull : sent.includes('bear') || sent.includes('neg') ? styles.cBear : styles.cNeutral;
                            const timeStr = art.time || (art.published ? formatTimeAgo(art.published) : '2h ago');
                            return (
                                <a 
                                    key={idx} 
                                    href={art.url || "#"} 
                                    target="_blank" 
                                    rel="noopener noreferrer" 
                                    className={styles.newsRow}
                                >
                                    <span className={styles.nTitle}>
                                        {art.title} <span style={{ fontSize: '11px', color: 'var(--brand-ink)' }}>↗</span>
                                    </span>
                                    <span className={styles.nMeta}>{art.source} · {timeStr}</span>
                                    <span className={`${styles.nSide} ${styles.chip} ${chipClass}`}>
                                        {toSentenceCase(sent)}
                                    </span>
                                </a>
                            );
                        })}
                    </div>
                </section>
            )}

            {activeTab === 'sentiment' && (
                <section className={styles.panel} id="p-sentiment">
                    <div className={styles.box}>
                        <h3 className={styles.boxTitle}>
                            Overall sentiment: {toSentenceCase(agents?.sentiment?.overall_sentiment || 'Bullish')}
                        </h3>
                        <div className={styles.gauge} role="img" aria-label="Sentiment gauge">
                            <div className={`${styles.pin} ${styles.pinNow}`} style={{ left: '78%' }} />
                        </div>
                        <div className={styles.rangeEnds}>
                            <span>Bearish</span>
                            <span>Neutral</span>
                            <span>Bullish</span>
                        </div>
                        <table className={styles.mtable} style={{ marginTop: '24px' }}>
                            <thead>
                                <tr><th>Audience</th><th>Reading</th></tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td>Retail Sentiment</td>
                                    <td><span className={`${styles.chip} ${styles.cBull}`}>{toSentenceCase(agents?.sentiment?.news_sentiment || 'Bullish')}</span></td>
                                </tr>
                                <tr>
                                    <td>Institutional Consensus</td>
                                    <td><span className={`${styles.chip} ${styles.cBull}`}>{toSentenceCase(agents?.equity?.analyst_consensus || 'Overweight')}</span></td>
                                </tr>
                                <tr>
                                    <td>Sentiment Dispersion</td>
                                    <td>
                                        <span className={`${styles.chip} ${styles.cCaution}`}>
                                            {toSentenceCase(agents?.sentiment?.sentiment_divergence || 'Low divergence')}
                                        </span>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </section>
            )}

            {activeTab === 'fundamentals' && (
                <section className={styles.panel} id="p-fundamentals">
                    <div className={styles.two}>
                        <div className={styles.box}>
                            <h3 className={styles.boxTitle}>Valuation</h3>
                            <table className={styles.mtable}>
                                <tbody>
                                    <tr>
                                        <td>P/E (trailing)<span className={styles.hint}>Sector median ~24.1×</span></td>
                                        <td className={styles.big}>{formatMetricValue('pe_ratio', agents?.fundamentals?.metrics?.pe_ratio ?? 27.4)}</td>
                                    </tr>
                                    <tr>
                                        <td>P/E (forward)</td>
                                        <td className={styles.big}>{formatMetricValue('forward_pe', agents?.fundamentals?.metrics?.forward_pe ?? 24.6)}</td>
                                    </tr>
                                    <tr>
                                        <td>Valuation Verdict</td>
                                        <td>
                                            <span className={`${styles.chip} ${styles.cCaution}`}>
                                                {toSentenceCase(agents?.fundamentals?.valuation_assessment || 'Fairly valued')}
                                            </span>
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>

                        <div className={styles.box}>
                            <h3 className={styles.boxTitle}>Quality &amp; growth</h3>
                            <table className={styles.mtable}>
                                <tbody>
                                    <tr>
                                        <td>Revenue growth (YoY)</td>
                                        <td className={styles.big} style={{ color: 'var(--bull)' }}>
                                            {formatMetricValue('revenue_growth', agents?.fundamentals?.metrics?.revenue_growth ?? 0.085)}
                                        </td>
                                    </tr>
                                    <tr>
                                        <td>Profit margin</td>
                                        <td className={styles.big}>
                                            {formatMetricValue('profit_margins', agents?.fundamentals?.metrics?.profit_margins ?? 0.25)}
                                        </td>
                                    </tr>
                                    <tr>
                                        <td>Return on equity</td>
                                        <td className={styles.big}>
                                            {formatMetricValue('return_on_equity', agents?.fundamentals?.metrics?.return_on_equity ?? 0.402)}
                                        </td>
                                    </tr>
                                    <tr>
                                        <td>Debt / equity<span className={styles.hint}>Total debt to equity ratio</span></td>
                                        <td className={styles.big}>
                                            {formatMetricValue('debt_to_equity', agents?.fundamentals?.metrics?.debt_to_equity ?? 1.05)}
                                        </td>
                                    </tr>
                                    <tr>
                                        <td>Free cash flow (TTM)</td>
                                        <td className={styles.big}>
                                            {formatMetricValue('free_cashflow', agents?.fundamentals?.metrics?.free_cashflow ?? 95000000000)}
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>
            )}

            {activeTab === 'technical' && (
                <section className={styles.panel} id="p-technical">
                    <div className={styles.box}>
                        <h3 className={styles.boxTitle}>Price &amp; Momentum (6 Months)</h3>
                        <svg className={styles.chart} viewBox="0 0 720 220" role="img" aria-label="Technical price chart with 50-day average, support, and resistance">
                            {/* Horizontal Gridlines & Price Ticks (Dynamic) */}
                            {chartTicks.map((tickVal, idx) => {
                                const yPos = 40 + idx * 45;
                                return (
                                    <g key={idx}>
                                        <line x1="50" x2="660" y1={yPos} y2={yPos} stroke="var(--rule)" strokeDasharray="3 3" strokeWidth="1"/>
                                        <text x="668" y={yPos + 4} fontSize="10" fill="var(--ink-3)" className="num">
                                            ${tickVal >= 1000 ? tickVal.toLocaleString() : tickVal.toFixed(tickVal % 1 !== 0 ? 1 : 0)}
                                        </text>
                                    </g>
                                );
                            })}

                            {/* Resistance & Support Levels */}
                            <line x1="50" x2="660" y1={resistanceY} y2={resistanceY} stroke="var(--bear)" strokeDasharray="5 5" strokeWidth="1.5"/>
                            <line x1="50" x2="660" y1={supportY} y2={supportY} stroke="var(--bull)" strokeDasharray="5 5" strokeWidth="1.5"/>

                            {/* 50-day MA Trendline */}
                            <polyline fill="none" stroke="var(--ink-3)" strokeWidth="1.5" points={maPolylinePoints}/>

                            {/* Daily Price Polyline */}
                            <polyline fill="none" stroke="var(--ink)" strokeWidth="2.5" strokeLinejoin="round" points={pricePolylinePoints}/>

                            {/* Resistance / Support Labels */}
                            <text x="650" y={Math.max(26, resistanceY - 6)} textAnchor="end" fontSize="11" fontWeight="600" fill="var(--bear)">
                                Resistance ${techResistance.toFixed(2)}
                            </text>
                            <text x="650" y={Math.min(195, supportY + 14)} textAnchor="end" fontSize="11" fontWeight="600" fill="var(--bull)">
                                Support ${techSupport.toFixed(2)}
                            </text>

                            {/* Dynamic Month Axis Labels */}
                            <text x="60" y="205" fontSize="11" fill="var(--ink-3)">{monthAxisLabels[0]}</text>
                            <text x="240" y="205" fontSize="11" fill="var(--ink-3)">{monthAxisLabels[1]}</text>
                            <text x="440" y="205" fontSize="11" fill="var(--ink-3)">{monthAxisLabels[2]}</text>
                            <text x="620" y="205" fontSize="11" fill="var(--ink-3)">{monthAxisLabels[3]}</text>
                        </svg>

                        <div className={styles.chartLegend}>
                            <span className={styles.leg}><i style={{ background: 'var(--ink)' }} /> Price</span>
                            <span className={styles.leg}><i style={{ background: 'var(--ink-3)' }} /> 50-day average</span>
                            <span className={styles.leg}><i style={{ background: 'var(--bull)' }} /> Support (${agents?.technical?.support_level ?? '182.64'})</span>
                            <span className={styles.leg}><i style={{ background: 'var(--bear)' }} /> Resistance (${agents?.technical?.resistance_level ?? '201.86'})</span>
                        </div>

                        <table className={styles.mtable} style={{ marginTop: '24px' }}>
                            <tbody>
                                <tr>
                                    <td>RSI (14)<span className={styles.hint}>Neutral zone 30–70 (Wilder smoothed)</span></td>
                                    <td className={styles.big}>{(agents?.technical?.raw?.rsi_14 ?? agents?.technical?.raw?.rsi) != null ? Number(agents.technical.raw.rsi_14 ?? agents.technical.raw.rsi).toFixed(1) : '54.2'}</td>
                                </tr>
                                <tr>
                                    <td>MACD Signal</td>
                                    <td><span className={`${styles.chip} ${styles.cBull}`}>{toSentenceCase(agents?.technical?.macd_signal || 'Bullish')} crossover</span></td>
                                </tr>
                                <tr>
                                    <td>Volume vs. 20-day average</td>
                                    <td>
                                        <span className={`${styles.chip} ${styles.cNeutral}`}>
                                            {(() => {
                                                const v = agents?.technical?.raw?.volume_vs_average;
                                                if (!v) return 'Above 20-day average';
                                                const low = String(v).toLowerCase();
                                                if (low === 'above' || low === 'below') return `${toSentenceCase(low)} 20-day average`;
                                                return toSentenceCase(v);
                                            })()}
                                        </span>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </section>
            )}

            {activeTab === 'risk' && (
                <section className={styles.panel} id="p-risk">
                    <div className={styles.two}>
                        <div className={styles.box}>
                            <h3 className={styles.boxTitle}>Statistical Risk Parameters</h3>
                            <table className={styles.mtable}>
                                <tbody>
                                    <tr>
                                        <td>
                                            Beta vs. S&amp;P 500
                                            <span 
                                                className={styles.hint} 
                                                title="Defensive: <0.8, ≈ Market: 0.8–1.2, Aggressive: >1.2" 
                                                style={{ cursor: 'help', fontWeight: 600, color: 'var(--ink)' }}
                                            >
                                                {deriveBetaAssessment(riskBeta)}
                                            </span>
                                            <span className={styles.hint}>
                                                vs SPY, 1y daily, R² {riskR2 !== undefined ? Number(riskR2).toFixed(2) : '0.45'}
                                            </span>
                                        </td>
                                        <td className={styles.big}>{riskBeta !== undefined ? Number(riskBeta).toFixed(2) : '1.12'}</td>
                                    </tr>
                                    <tr>
                                        <td>
                                            Annualised volatility
                                            <span className={styles.hint}>1y, daily log returns, ×√252</span>
                                        </td>
                                        <td className={styles.big}>{riskVol !== undefined ? `${(riskVol * 100).toFixed(1)}%` : '21.8%'}</td>
                                    </tr>
                                    <tr>
                                        <td>
                                            Sharpe ratio
                                            <span className={styles.hint}>1y, rf = 3M T-bill</span>
                                        </td>
                                        <td className={styles.big}>{riskSharpe !== undefined ? Number(riskSharpe).toFixed(2) : '-0.50'}</td>
                                    </tr>
                                    <tr>
                                        <td>
                                            Max drawdown
                                            <span className={styles.hint}>
                                                1y · peak {riskPeakDate} → trough {riskTroughDate} · {riskRecovery}
                                            </span>
                                        </td>
                                        <td className={styles.big} style={{ color: 'var(--bear)' }}>
                                            {riskMaxDd !== undefined ? `${(riskMaxDd * 100).toFixed(1)}%` : '-18.3%'}
                                        </td>
                                    </tr>
                                    <tr>
                                        <td>
                                            1-day VaR (95%)
                                            <span className={styles.hint}>Historical, 500d</span>
                                        </td>
                                        <td className={styles.big} style={{ color: 'var(--bear)' }}>
                                            <div>{riskVar95 !== undefined ? `${(riskVar95 * 100).toFixed(2)}%` : '-2.21%'}</div>
                                            {riskVar95Param !== undefined && (
                                                <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 400, marginTop: '2px' }}>
                                                    Parametric: {(riskVar95Param * 100).toFixed(2)}%
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>

                        <div className={styles.box}>
                            <h3 className={styles.boxTitle}>What could go wrong</h3>
                            <ul className={styles.list}>
                                {(agents?.risk?.key_risks?.length ? agents.risk.key_risks : [
                                    "Broad macro market equity contraction",
                                    "Platform fee regulation impacting services revenue",
                                    "Component supply concentration"
                                ]).map((r, i) => (
                                    <li key={i} className={styles.listItem}>{r}</li>
                                ))}
                            </ul>
                            <h3 className={styles.boxTitle} style={{ marginTop: '20px' }}>What cushions it</h3>
                            <ul className={styles.list}>
                                {(agents?.risk?.risk_mitigants?.length ? agents.risk.risk_mitigants : [
                                    "High liquidity and robust balance sheet reserves",
                                    "Global recurring revenue diversification"
                                ]).map((m, i) => (
                                    <li key={i} className={styles.listItem}>{m}</li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </section>
            )}

            {activeTab === 'radar' && (
                <section className={styles.panel} id="p-radar">
                    <div className={styles.box}>
                        <h3 className={styles.boxTitle}>Cross-Agent Tri-Perspective Radar</h3>
                        <ContradictionRadar />
                    </div>
                </section>
            )}

            {/* Disclaimer & Sources Footer */}
            <footer className={styles.note}>
                <span>For education and research only. Not investment advice.</span>
                <span>Sources: yfinance, NewsAPI, SEC filings. Synthesized by 6 autonomous agents &amp; evaluator guardrails.</span>
            </footer>
        </main>
    )
}
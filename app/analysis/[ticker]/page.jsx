'use client'
import { useState, useEffect } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useRouter, useParams } from 'next/navigation'
import styles from './analysis.module.css'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';



function NewsSection({ data }) {
    if (!data) return <p className={styles.noData}>No data available</p>
    return (
        <div className={styles.sectionContent}>
            <div className={styles.summaryBlock}>
                <p className={styles.sectionSummary}>{data.summary}</p>
            </div>
            <div className={styles.tagRow}>
                {data.key_themes?.map((t, i) => (
                    <span key={i} className={styles.tag}>{t}</span>
                ))}
            </div>
            {data.supply_chain_risks?.length > 0 && (
                <div className={styles.riskBlock}>
                    <p className={styles.blockLabel}>⚠ Supply Chain Risks</p>
                    <ul className={styles.simpleList}>
                        {data.supply_chain_risks.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                </div>
            )}
            <div className={styles.articleGrid}>
                {data.articles?.map((a, i) => (
                    <a key={i} href={a.url} target="_blank" rel="noopener noreferrer" className={styles.articleCard}>
                        <p className={styles.articleTitle}>{a.title}</p>
                        <p className={styles.articleSource}>{a.source}</p>
                        <p className={styles.articleRelevance}>{a.relevance}</p>
                    </a>
                ))}
            </div>
        </div>
    )
}

function SentimentSection({ data }) {
    if (!data) return <p className={styles.noData}>No data available</p>
    const sentColor = (s) => s === 'bullish' ? '#22c55e' : s === 'bearish' ? '#ef4444' : '#6b7280'
    const sentBg = (s) => s === 'bullish' ? '#22c55e22' : s === 'bearish' ? '#ef444422' : '#6b728022'
    return (
        <div className={styles.sectionContent}>
            <p className={styles.sectionSummary}>{data.summary}</p>
            <div className={styles.metricsRow}>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Overall</span>
                    <span className={styles.metricBoxValue} style={{ color: sentColor(data.overall_sentiment), backgroundColor: sentBg(data.overall_sentiment) }}>
                        {data.overall_sentiment}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Retail</span>
                    <span className={styles.metricBoxValue} style={{ color: sentColor(data.retail_sentiment), backgroundColor: sentBg(data.retail_sentiment) }}>
                        {data.retail_sentiment}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Institutional</span>
                    <span className={styles.metricBoxValue} style={{ color: sentColor(data.institutional_sentiment), backgroundColor: sentBg(data.institutional_sentiment) }}>
                        {data.institutional_sentiment}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Analyst Consensus</span>
                    <span className={styles.metricBoxValue} style={{ color: '#00d4aa', backgroundColor: '#00d4aa22' }}>
                        {data.analyst_consensus}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Sentiment Score</span>
                    <span className={styles.metricBoxValue} style={{ color: '#111827', backgroundColor: '#f3f4f6' }}>
                        {data.sentiment_score}/10
                    </span>
                </div>
            </div>
            <div className={styles.tagRow}>
                {data.key_sentiment_drivers?.map((d, i) => (
                    <span key={i} className={styles.tag}>{d}</span>
                ))}
            </div>
        </div>
    )
}

function FundamentalsSection({ data }) {
    if (!data) return <p className={styles.noData}>No data available</p>
    const healthColor = data.financial_health === 'strong' ? '#22c55e' : data.financial_health === 'weak' ? '#ef4444' : '#f59e0b'
    return (
        <div className={styles.sectionContent}>
            <p className={styles.sectionSummary}>{data.summary}</p>
            <div className={styles.metricsRow}>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Valuation</span>
                    <span className={styles.metricBoxValue} style={{ color: data.valuation === 'undervalued' ? '#22c55e' : data.valuation === 'overvalued' ? '#ef4444' : '#f59e0b', backgroundColor: '#f3f4f6' }}>
                        {data.valuation}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Financial Health</span>
                    <span className={styles.metricBoxValue} style={{ color: healthColor, backgroundColor: '#f3f4f6' }}>
                        {data.financial_health}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Growth Outlook</span>
                    <span className={styles.metricBoxValue} style={{ color: '#00d4aa', backgroundColor: '#00d4aa22' }}>
                        {data.growth_outlook}
                    </span>
                </div>
            </div>
            <div className={styles.metricsGrid}>
                {data.metrics && Object.entries(data.metrics).map(([k, v]) => (
                    <div key={k} className={styles.metricGridItem}>
                        <span className={styles.metricGridLabel}>{k.replace(/_/g, ' ')}</span>
                        <span className={styles.metricGridValue}>
                            {typeof v === 'number' ? (v > 1000000 ? `$${(v/1e9).toFixed(1)}B` : v.toFixed(2)) : v}
                        </span>
                    </div>
                ))}
            </div>
            <div className={styles.casesGrid}>
                <div>
                    <p className={styles.blockLabel} style={{ color: '#22c55e' }}>✓ Strengths</p>
                    <ul className={styles.simpleList}>
                        {data.key_strengths?.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                </div>
                <div>
                    <p className={styles.blockLabel} style={{ color: '#ef4444' }}>✗ Weaknesses</p>
                    <ul className={styles.simpleList}>
                        {data.key_weaknesses?.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                </div>
            </div>
        </div>
    )
}

function TechnicalSection({ data }) {
    if (!data) return <p className={styles.noData}>No data available</p>
    return (
        <div className={styles.sectionContent}>
            <p className={styles.sectionSummary}>{data.summary}</p>
            <div className={styles.metricsRow}>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Trend</span>
                    <span className={styles.metricBoxValue} style={{ color: data.trend === 'bullish' ? '#22c55e' : data.trend === 'bearish' ? '#ef4444' : '#6b7280', backgroundColor: '#f3f4f6' }}>
                        {data.trend} ({data.trend_strength})
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>RSI Signal</span>
                    <span className={styles.metricBoxValue} style={{ color: data.rsi_signal === 'overbought' ? '#ef4444' : data.rsi_signal === 'oversold' ? '#22c55e' : '#6b7280', backgroundColor: '#f3f4f6' }}>
                        {data.rsi_signal}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>MACD</span>
                    <span className={styles.metricBoxValue} style={{ color: data.macd_signal === 'bullish' ? '#22c55e' : '#ef4444', backgroundColor: '#f3f4f6' }}>
                        {data.macd_signal}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Short Term</span>
                    <span className={styles.metricBoxValue} style={{ color: data.short_term_outlook === 'bullish' ? '#22c55e' : data.short_term_outlook === 'bearish' ? '#ef4444' : '#6b7280', backgroundColor: '#f3f4f6' }}>
                        {data.short_term_outlook}
                    </span>
                </div>
            </div>
            <div className={styles.metricsGrid}>
                <div className={styles.metricGridItem}>
                    <span className={styles.metricGridLabel}>Support</span>
                    <span className={styles.metricGridValue}>${data.support_level}</span>
                </div>
                <div className={styles.metricGridItem}>
                    <span className={styles.metricGridLabel}>Resistance</span>
                    <span className={styles.metricGridValue}>${data.resistance_level}</span>
                </div>
                {data.raw && (
                    <>
                        <div className={styles.metricGridItem}>
                            <span className={styles.metricGridLabel}>Current Price</span>
                            <span className={styles.metricGridValue}>${data.raw.current_price}</span>
                        </div>
                        <div className={styles.metricGridItem}>
                            <span className={styles.metricGridLabel}>50-day MA</span>
                            <span className={styles.metricGridValue}>${data.raw.ma50}</span>
                        </div>
                        <div className={styles.metricGridItem}>
                            <span className={styles.metricGridLabel}>RSI</span>
                            <span className={styles.metricGridValue}>{data.raw.rsi}</span>
                        </div>
                        <div className={styles.metricGridItem}>
                            <span className={styles.metricGridLabel}>Volume vs Avg</span>
                            <span className={styles.metricGridValue}>{data.raw.volume_vs_average}</span>
                        </div>
                    </>
                )}
            </div>
            <div className={styles.tagRow}>
                {data.signals?.map((s, i) => <span key={i} className={styles.tag}>{s}</span>)}
            </div>
        </div>
    )
}

function EquitySection({ data }) {
    if (!data) return <p className={styles.noData}>No data available</p>
    return (
        <div className={styles.sectionContent}>
            <p className={styles.sectionSummary}>{data.investment_thesis}</p>
            <div className={styles.metricsRow}>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Analyst Consensus</span>
                    <span className={styles.metricBoxValue} style={{ color: '#00d4aa', backgroundColor: '#00d4aa22' }}>
                        {data.analyst_consensus?.replace('_', ' ')}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Price Target</span>
                    <span className={styles.metricBoxValue} style={{ color: '#111827', backgroundColor: '#f3f4f6' }}>
                        ${data.price_target}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Upside/Downside</span>
                    <span className={styles.metricBoxValue} style={{ color: '#111827', backgroundColor: '#f3f4f6' }}>
                        {data.upside_downside}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Moat</span>
                    <span className={styles.metricBoxValue} style={{ color: data.moat === 'wide' ? '#22c55e' : data.moat === 'none' ? '#ef4444' : '#f59e0b', backgroundColor: '#f3f4f6' }}>
                        {data.moat}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Sector Outlook</span>
                    <span className={styles.metricBoxValue} style={{ color: data.sector_outlook === 'positive' ? '#22c55e' : data.sector_outlook === 'negative' ? '#ef4444' : '#6b7280', backgroundColor: '#f3f4f6' }}>
                        {data.sector_outlook}
                    </span>
                </div>
            </div>
            <div className={styles.casesGrid}>
                <div>
                    <p className={styles.blockLabel}>🏰 Moat Sources</p>
                    <ul className={styles.simpleList}>
                        {data.moat_sources?.map((m, i) => <li key={i}>{m}</li>)}
                    </ul>
                </div>
                <div>
                    <p className={styles.blockLabel}>⚡ Growth Catalysts</p>
                    <ul className={styles.simpleList}>
                        {data.growth_catalysts?.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                </div>
            </div>
        </div>
    )
}

function RiskSection({ data }) {
    if (!data) return <p className={styles.noData}>No data available</p>
    const riskColor = data.overall_risk === 'low' ? '#22c55e' : data.overall_risk === 'high' || data.overall_risk === 'very_high' ? '#ef4444' : '#f59e0b'
    return (
        <div className={styles.sectionContent}>
            <p className={styles.sectionSummary}>{data.summary}</p>
            <div className={styles.metricsRow}>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Overall Risk</span>
                    <span className={styles.metricBoxValue} style={{ color: riskColor, backgroundColor: `${riskColor}22` }}>
                        {data.overall_risk?.replace('_', ' ')}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Volatility</span>
                    <span className={styles.metricBoxValue} style={{ color: '#111827', backgroundColor: '#f3f4f6' }}>
                        {data.volatility_assessment}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Beta</span>
                    <span className={styles.metricBoxValue} style={{ color: '#111827', backgroundColor: '#f3f4f6' }}>
                        {data.beta_assessment}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Sharpe Ratio</span>
                    <span className={styles.metricBoxValue} style={{ color: '#111827', backgroundColor: '#f3f4f6' }}>
                        {data.sharpe_assessment}
                    </span>
                </div>
                <div className={styles.metricBox}>
                    <span className={styles.metricBoxLabel}>Short Squeeze Risk</span>
                    <span className={styles.metricBoxValue} style={{ color: data.short_squeeze_risk === 'high' ? '#ef4444' : data.short_squeeze_risk === 'low' ? '#22c55e' : '#f59e0b', backgroundColor: '#f3f4f6' }}>
                        {data.short_squeeze_risk}
                    </span>
                </div>
            </div>
            <div className={styles.metricsGrid}>
                {data.metrics && Object.entries(data.metrics).map(([k, v]) => (
                    <div key={k} className={styles.metricGridItem}>
                        <span className={styles.metricGridLabel}>{k.replace(/_/g, ' ')}</span>
                        <span className={styles.metricGridValue}>{typeof v === 'number' ? v.toFixed(2) : v}</span>
                    </div>
                ))}
            </div>
            <p className={styles.varNote}>📌 {data.var_interpretation}</p>
            <div className={styles.casesGrid}>
                <div>
                    <p className={styles.blockLabel} style={{ color: '#ef4444' }}>🚨 Key Risks</p>
                    <ul className={styles.simpleList}>
                        {data.key_risks?.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                </div>
                <div>
                    <p className={styles.blockLabel} style={{ color: '#22c55e' }}>🛡 Risk Mitigants</p>
                    <ul className={styles.simpleList}>
                        {data.risk_mitigants?.map((m, i) => <li key={i}>{m}</li>)}
                    </ul>
                </div>
            </div>
        </div>
    )
}
export default function AnalysisPage() {
    const { user, loading } = useAuth()
    const router = useRouter()
    const { ticker } = useParams()
    const [report, setReport] = useState(null)
    const [agents, setAgents] = useState(null)
    const [pageLoading, setPageLoading] = useState(true)
    const [expanded, setExpanded] = useState({})

    useEffect(() => {
        if (loading) return
        if (!user) {
            router.push('/login')
            return
        }
        FetchAnalysis()
    }, [user, loading])

    async function FetchAnalysis() {
        setPageLoading(true)
        try {
            const token = localStorage.getItem('token') || user?.token;
            const headers = { 'Content-Type': 'application/json' };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            const res = await fetch(`${BACKEND_URL}/analyse/${ticker}`, {
                method: 'POST',
                headers
            })
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                console.error("Analysis request failed:", errData);
                return;
            }
            const data = await res.json()
            setReport(data.report)
            setAgents(data.agents)
        } catch (err) {
            console.error(err)
        } finally {
            setPageLoading(false)
        }
    }

    function toggleSection(key) {
        setExpanded(prev => ({ ...prev, [key]: !prev[key] }))
    }

    if (loading || !user) return null

    if (pageLoading) return (
        <main className={styles.loadingScreen}>
            <p className={styles.loadingIcon}>◎</p>
            <p className={styles.loadingText}>Running agent analysis for {ticker}...</p>
            <p className={styles.loadingSubtext}>News · Sentiment · Fundamentals · Technical · Equity · Risk</p>
        </main>
    )

    if (!report) return (
        <main className={styles.loadingScreen}>
            <p className={styles.loadingText}>Failed to load analysis for {ticker}</p>
            <button className={styles.backBtn} onClick={() => router.push('/')}>← Back</button>
        </main>
    )

    const recColor = report.recommendation?.includes('buy') ? '#22c55e' : report.recommendation?.includes('sell') ? '#ef4444' : '#6b7280'
    const recBg = report.recommendation?.includes('buy') ? '#22c55e22' : report.recommendation?.includes('sell') ? '#ef444422' : '#6b728022'

    const sections = [
        { key: 'news', label: '📰 News & Supply Chain', data: agents?.news },
        { key: 'sentiment', label: '💬 Sentiment', data: agents?.sentiment },
        { key: 'fundamentals', label: '📊 Fundamentals', data: agents?.fundamentals },
        { key: 'technical', label: '📈 Technical Analysis', data: agents?.technical },
        { key: 'equity', label: '🔬 Equity Research', data: agents?.equity },
        { key: 'risk', label: '⚠️ Risk Management', data: agents?.risk },
    ]

    return (
        <main className={styles.page}>
            {/* Back */}
            <button className={styles.backBtn} onClick={() => router.back()}>← Back</button>

            {/* Header */}
            <div className={styles.header}>
                <div>
                    <h1 className={styles.ticker}>{ticker}</h1>
                    <p className={styles.horizon}>{report.investment_horizon?.replace('_', ' ')} outlook</p>
                </div>
                <div className={styles.headerRight}>
                    <span className={styles.recBadge} style={{ backgroundColor: recBg, color: recColor }}>
                        {report.recommendation?.replace('_', ' ').toUpperCase()}
                    </span>
                    <span className={styles.conviction}>Conviction {report.conviction}/10</span>
                </div>
            </div>

            {/* Summary card */}
            <div className={styles.summaryCard}>
                <div className={styles.summaryMeta}>
                    <div className={styles.metaItem}>
                        <span className={styles.metaLabel}>Price Target</span>
                        <span className={styles.metaValue}>${report.price_target}</span>
                    </div>
                    <div className={styles.metaItem}>
                        <span className={styles.metaLabel}>Risk/Reward</span>
                        <span className={styles.metaValue}>{report.risk_reward}</span>
                    </div>
                    <div className={styles.metaItem}>
                        <span className={styles.metaLabel}>Position Size</span>
                        <span className={styles.metaValue}>{report.position_sizing}</span>
                    </div>
                </div>
                <p className={styles.summary}>{report.summary}</p>
            </div>

            {/* Bull / Bear */}
            <div className={styles.casesGrid}>
                <div className={styles.bullCard}>
                    <h3 className={styles.caseTitle} style={{ color: '#22c55e' }}>🐂 Bull Case</h3>
                    <ul className={styles.caseList}>
                        {report.bull_case?.map((point, i) => <li key={i}>{point}</li>)}
                    </ul>
                </div>
                <div className={styles.bearCard}>
                    <h3 className={styles.caseTitle} style={{ color: '#ef4444' }}>🐻 Bear Case</h3>
                    <ul className={styles.caseList}>
                        {report.bear_case?.map((point, i) => <li key={i}>{point}</li>)}
                    </ul>
                </div>
            </div>

            {/* Catalysts & Risks */}
            <div className={styles.casesGrid}>
                <div className={styles.card}>
                    <h3 className={styles.caseTitle}>⚡ Key Catalysts</h3>
                    <ul className={styles.caseList}>
                        {report.key_catalysts?.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                </div>
                <div className={styles.card}>
                    <h3 className={styles.caseTitle}>🚨 Key Risks</h3>
                    <ul className={styles.caseList}>
                        {report.key_risks?.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                </div>
            </div>

            {/* Expandable agent sections */}
            {/* Expandable agent sections */}
<h2 className={styles.agentTitle}>Detailed Analysis</h2>
{sections.map(({ key, label, data }) => (
    <div key={key} className={styles.section}>
        <button className={styles.sectionHeader} onClick={() => toggleSection(key)}>
            <span>{label}</span>
            <span className={styles.chevron}>{expanded[key] ? '▲' : '▼'}</span>
        </button>
        {expanded[key] && (
            <div className={styles.sectionBody}>
                {key === 'news' && <NewsSection data={data} />}
                {key === 'sentiment' && <SentimentSection data={data} />}
                {key === 'fundamentals' && <FundamentalsSection data={data} />}
                {key === 'technical' && <TechnicalSection data={data} />}
                {key === 'equity' && <EquitySection data={data} />}
                {key === 'risk' && <RiskSection data={data} />}
            </div>
        )}
    </div>
))}
        </main>
    )
}
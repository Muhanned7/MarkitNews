'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

const BADGE_STYLES = {
  portfolio: {
    bg: 'var(--brand-tint)',
    color: 'var(--brand-ink)',
    border: '1px solid color-mix(in srgb, var(--brand) 40%, transparent)',
  },
  bull: {
    bg: 'var(--bull-tint)',
    color: 'var(--bull)',
    border: '1px solid color-mix(in srgb, var(--bull) 30%, transparent)',
  },
  bear: {
    bg: 'var(--bear-tint)',
    color: 'var(--bear)',
    border: '1px solid color-mix(in srgb, var(--bear) 30%, transparent)',
  },
  caution: {
    bg: 'var(--caution-tint)',
    color: 'var(--caution)',
    border: '1px solid color-mix(in srgb, var(--caution) 30%, transparent)',
  },
  brand: {
    bg: 'var(--surface-2)',
    color: 'var(--ink-2)',
    border: '1px solid var(--rule)',
  },
}

function formatCompactVolume(vol) {
  const n = Number(vol || 0)
  if (!n || n <= 0) return '—'
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

export default function AnalysisIndexPage() {
  const [tickerInput, setTickerInput] = useState('')
  const [tickers, setTickers] = useState([])
  const [asOf, setAsOf] = useState(null)
  const [portfolioCount, setPortfolioCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const router = useRouter()

  const loadHotTickers = useCallback(async (forceRefresh = false) => {
    if (forceRefresh) setRefreshing(true)
    try {
      const qs = forceRefresh ? '?refresh=1' : ''
      const res = await fetch(`/api/hot-tickers${qs}`, {
        credentials: 'include',
        cache: 'no-store',
      })
      if (res.ok) {
        const data = await res.json()
        if (Array.isArray(data.tickers) && data.tickers.length > 0) {
          setTickers(data.tickers)
          setAsOf(data.as_of || null)
          setPortfolioCount(data.portfolio_count || 0)
        }
      }
    } catch (err) {
      console.error('Failed to load live hot tickers:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    loadHotTickers(false)
  }, [loadHotTickers])

  const handleSearch = (e) => {
    e.preventDefault()
    const clean = tickerInput.trim().toUpperCase()
    if (clean) {
      router.push(`/analysis/${clean}`)
    }
  }

  return (
    <div style={{ padding: '28px clamp(16px, 3vw, 40px) 64px', maxWidth: '1180px', margin: '0 auto', width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', gap: '12px', flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--ink)' }}>
          Equity Analysis Hub
        </h2>
        <span style={{
          fontSize: 'var(--fs-xs)',
          fontWeight: 700,
          padding: '3px 10px',
          borderRadius: 'var(--r-chip)',
          background: 'var(--brand-tint)',
          color: 'var(--brand-ink)'
        }}>
          Multi-agent intelligence
        </span>
      </div>

      {/* Search Hero Panel */}
      <div style={{
        background: 'var(--surface)',
        borderRadius: 'var(--r-panel)',
        boxShadow: 'var(--shadow-panel)',
        border: '1px solid var(--rule)',
        padding: 'clamp(20px, 4vw, 36px)',
        marginBottom: '32px',
        textAlign: 'center'
      }}>
        <h1 style={{
          fontFamily: 'var(--font-figure)',
          fontSize: 'clamp(1.8rem, 4vw, 2.5rem)',
          fontWeight: 700,
          color: 'var(--ink)',
          letterSpacing: '.01em',
          margin: '0 auto',
          lineHeight: 1.15,
          maxWidth: '680px'
        }}>
          Autonomous Equity Intelligence
        </h1>
        <p style={{
          margin: '12px auto 0',
          fontSize: 'var(--fs-sm)',
          color: 'var(--ink-2)',
          maxWidth: '560px',
          lineHeight: 1.5
        }}>
          Consensus synthesis combining empirical technical pivots, balance-sheet rigor, news sentiment, supply-chain contradiction arbitration, and statistical risk modeling.
        </p>

        <form onSubmit={handleSearch} style={{
          marginTop: '24px',
          maxWidth: '480px',
          marginLeft: 'auto',
          marginRight: 'auto',
          display: 'flex',
          gap: '8px',
          flexWrap: 'wrap'
        }}>
          <input
            type="text"
            value={tickerInput}
            onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
            placeholder="Search any ticker, e.g. NVDA, PLTR, AAPL..."
            aria-label="Ticker symbol"
            style={{
              flex: '1 1 220px',
              height: '42px',
              padding: '0 14px',
              borderRadius: 'var(--r-control)',
              border: '1px solid var(--rule)',
              background: 'var(--surface-2)',
              color: 'var(--ink)',
              fontSize: 'var(--fs-sm)',
              outline: 'none',
              fontFamily: 'var(--font-ui)'
            }}
          />
          <button
            type="submit"
            style={{
              flex: '1 0 100px',
              height: '42px',
              padding: '0 20px',
              borderRadius: 'var(--r-control)',
              background: 'var(--brand)',
              color: '#06231D',
              fontWeight: 700,
              fontSize: 'var(--fs-sm)',
              border: 'none',
              cursor: 'pointer'
            }}
          >
            Analyze
          </button>
        </form>
      </div>

      {/* Unified Hot Tickers + Portfolio Holdings Grid */}
      <div style={{ marginBottom: '20px' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
          marginBottom: '16px'
        }}>
          <div>
            <h2 style={{ fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
              🔥 Today&apos;s Hot Market Movers &amp; Portfolio Holdings
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
              Live feed combining your active portfolio positions ({portfolioCount} shown) with Yahoo Finance&apos;s top gainers, volume leaders, and trending tickers
              {asOf ? ` • Updated ${asOf}` : ''}
            </p>
          </div>

          <button
            type="button"
            onClick={() => loadHotTickers(true)}
            disabled={refreshing}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--rule)',
              color: 'var(--ink)',
              padding: '7px 14px',
              borderRadius: 'var(--r-control)',
              fontSize: 'var(--fs-xs)',
              fontWeight: 700,
              cursor: refreshing ? 'wait' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            {refreshing ? '↻ Refreshing Live Quotes...' : '↻ Refresh Movers'}
          </button>
        </div>

        {loading ? (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(310px, 1fr))',
            gap: '16px'
          }}>
            {Array.from({ length: 9 }).map((_, idx) => (
              <div
                key={idx}
                style={{
                  height: '215px',
                  borderRadius: 'var(--r-panel)',
                  background: 'var(--surface)',
                  border: '1px solid var(--rule)',
                  padding: '20px',
                  opacity: 0.65
                }}
              >
                <div style={{ width: '40%', height: '22px', background: 'var(--surface-2)', borderRadius: '6px', marginBottom: '10px' }} />
                <div style={{ width: '65%', height: '14px', background: 'var(--surface-2)', borderRadius: '6px', marginBottom: '24px' }} />
                <div style={{ width: '100%', height: '42px', background: 'var(--surface-2)', borderRadius: '8px' }} />
              </div>
            ))}
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(310px, 1fr))',
            gap: '16px'
          }}>
            {tickers.map((stock) => {
              const chgNum = Number(stock.change_pct || 0)
              const isUp = chgNum >= 0
              const chgFormatted = `${isUp ? '+' : '−'}${Math.abs(chgNum).toFixed(2)}%`
              const priceFormatted = `$${Number(stock.price || 0).toFixed(2)}`
              const volRatio = Number(stock.volume_ratio || 1).toFixed(1)

              return (
                <div
                  key={stock.symbol}
                  onClick={() => router.push(`/analysis/${stock.symbol}`)}
                  style={{
                    background: 'var(--surface)',
                    borderRadius: 'var(--r-panel)',
                    boxShadow: 'var(--shadow-panel)',
                    border: stock.in_portfolio
                      ? '1.5px solid color-mix(in srgb, var(--brand) 55%, var(--rule))'
                      : '1px solid var(--rule)',
                    padding: '20px',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    transition: 'transform 0.12s ease, border-color 0.15s ease'
                  }}
                >
                  <div>
                    {/* Top Row: Badges + Sector */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginBottom: '10px' }}>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {(stock.badges || []).map((b, bIdx) => {
                          const st = BADGE_STYLES[b.tone] || BADGE_STYLES.brand
                          return (
                            <span
                              key={bIdx}
                              style={{
                                fontSize: '11px',
                                fontWeight: 700,
                                padding: '2px 8px',
                                borderRadius: 'var(--r-chip)',
                                background: st.bg,
                                color: st.color,
                                border: st.border
                              }}
                            >
                              {b.label}
                            </span>
                          )
                        })}
                      </div>

                      <span style={{
                        fontSize: '11px',
                        padding: '2px 8px',
                        borderRadius: 'var(--r-chip)',
                        background: 'var(--surface-2)',
                        color: 'var(--ink-2)',
                        border: '1px solid var(--rule)',
                        fontWeight: 600
                      }}>
                        {stock.sector}
                      </span>
                    </div>

                    {/* Symbol, Company Name & Live Price / Change */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', marginBottom: '10px' }}>
                      <div>
                        <span style={{
                          fontFamily: 'var(--font-figure)',
                          fontSize: '1.55rem',
                          fontWeight: 700,
                          color: 'var(--ink)',
                          lineHeight: 1.1
                        }}>
                          {stock.symbol}
                        </span>
                        <p style={{ margin: '2px 0 0', fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 500 }}>
                          {stock.name}
                        </p>
                      </div>

                      <div style={{ textAlign: 'right' }}>
                        <div className="num" style={{ fontFamily: 'var(--font-figure)', fontSize: '1.35rem', fontWeight: 700, color: 'var(--ink)', lineHeight: 1.1 }}>
                          {priceFormatted}
                        </div>
                        <div className="num" style={{
                          marginTop: '3px',
                          fontSize: 'var(--fs-xs)',
                          fontWeight: 700,
                          color: isUp ? 'var(--bull)' : 'var(--bear)'
                        }}>
                          {chgFormatted}
                        </div>
                      </div>
                    </div>

                    {/* 1-Line "Why it's moving" summary */}
                    <p style={{
                      margin: '10px 0 12px',
                      fontSize: '12px',
                      color: 'var(--ink-2)',
                      lineHeight: 1.45,
                      background: 'var(--surface-2)',
                      padding: '8px 10px',
                      borderRadius: '8px',
                      border: '1px solid var(--rule)'
                    }}>
                      {stock.why_moving}
                    </p>
                  </div>

                  {/* Footer: Volume vs Avg + Quick Analyze Action */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    paddingTop: '10px',
                    borderTop: '1px solid var(--rule)',
                    fontSize: '11px',
                    color: 'var(--ink-3)'
                  }}>
                    <span className="num">
                      Vol: <strong style={{ color: 'var(--ink-2)' }}>{formatCompactVolume(stock.volume)}</strong>{' '}
                      <span>({volRatio}x avg)</span>
                    </span>

                    <span style={{
                      fontWeight: 700,
                      color: 'var(--brand-ink)',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}>
                      Run 6-Agent Analysis →
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

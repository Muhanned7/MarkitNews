'use client' 
import { useState, useEffect, useRef } from "react"
import { useAuth } from './context/AuthContext'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

function formatTimeAgo(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    const diffSec = Math.floor((Date.now() - d.getTime()) / 1000)
    if (diffSec < 60) return 'Just now'
    const diffMin = Math.floor(diffSec / 60)
    if (diffMin < 60) return `${diffMin}m ago`
    const diffHours = Math.floor(diffMin / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    const diffDays = Math.floor(diffHours / 24)
    return `${diffDays}d ago`
  } catch {
    return ''
  }
}

export default function HomePage() {
  const { user, authReady } = useAuth()
  const [input, setInput] = useState("")
  const [searchLoading, setSearchLoading] = useState(false)
  const [error, setError] = useState(null)
  const [articles, setArticles] = useState([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [watchlist, setWatchlist] = useState([])
  const [selectedTickers, setSelectedTickers] = useState([])
  const router = useRouter()
  const [tiles, setTiles] = useState([])
  const [tilesLoading, setTilesLoading] = useState(true)
  const [isMobile, setIsMobile] = useState(false)
  const scrollRef = useRef(null)
  const observerRef = useRef(null)

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 480)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  const POPULAR_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'JPM',
    'XOM', 'JNJ', 'WMT', 'BAC', 'PFE', 'CVX', 'NFLX', 'AMD', 'INTC', 'DIS', 'UBER', 'COIN'
  ]

  const scroll = (direction) => {
    if (scrollRef.current) {
      const { scrollLeft, clientWidth } = scrollRef.current
      const scrollTo = direction === 'left' 
        ? scrollLeft - clientWidth 
        : scrollLeft + clientWidth
      scrollRef.current.scrollTo({ left: scrollTo, behavior: 'smooth' })
    }
  }

  async function loadWatchlistAndTiles() {
    setTilesLoading(true)
    try {
      const response = await fetch('/api/watchlist', { credentials: 'include' })
      if (!response.ok) {
        setWatchlist([])
        setTiles([])
        return
      }
      const data = await response.json()
      const rawTickers = data.tickers?.map(t => (typeof t === 'string' ? t : t.ticker)?.toUpperCase()).filter(Boolean) || []
      setWatchlist(rawTickers)

      const tickers = rawTickers.slice(0, 6)
      if (tickers.length === 0) {
        setTiles([])
        return
      }
      // Load cached snapshots only (never trigger expensive live 6-agent AI runs automatically on home load)
      const results = await Promise.all(
        tickers.map(ticker =>
          fetch(`/api/snapshots/${ticker}`, { credentials: 'include' })
            .then(r => (r.ok ? r.json() : null))
            .then(d => {
              const latest = d?.snapshots?.[0]?.report_json || d?.latest?.report_json || null
              return latest ? { ticker, ...latest, status: 'done' } : null
            })
            .catch(() => null)
        )
      )
      setTiles(results.filter(Boolean))
    } catch {
      setWatchlist([])
      setTiles([])
    } finally {
      setTilesLoading(false)
    }
  }

  async function fetchFeed({ searchQuery = '', activeTickers = selectedTickers, pageNum = 1, append = false, save = false } = {}) {
    if (append) {
      setLoadingMore(true)
    } else {
      setSearchLoading(true)
      setError(null)
    }

    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: searchQuery,
          tickers: activeTickers,
          page: pageNum,
          limit: 8,
          save: save
        })
      })

      const data = await res.json()
      if (data.error) {
        setError(data.error)
        return
      }

      const incoming = data.scoredArticles || []
      setArticles(prev => append ? [...prev, ...incoming] : incoming)
      setPage(pageNum)
      setHasMore(data.hasMore ?? false)
    } catch (err) {
      setError('Something went wrong loading news. Please try again.')
    } finally {
      setSearchLoading(false)
      setLoadingMore(false)
    }
  }

  function handleTickerClick(ticker) {
    const isSelected = selectedTickers.includes(ticker)
    const updated = isSelected
      ? selectedTickers.filter(t => t !== ticker)
      : [...selectedTickers, ticker]

    setSelectedTickers(updated)
    setInput('')
    fetchFeed({ searchQuery: '', activeTickers: updated, pageNum: 1, append: false })
  }

  function handleClearAll() {
    setSelectedTickers([])
    setInput('')
    fetchFeed({ searchQuery: '', activeTickers: [], pageNum: 1, append: false })
  }

  function handleSearchSubmit() {
    if (!input.trim()) return
    fetchFeed({
      searchQuery: input.trim(),
      activeTickers: selectedTickers,
      pageNum: 1,
      append: false,
      save: true
    })
  }

  const initializedRef = useRef(false)

  useEffect(() => {
    if (initializedRef.current) return
    initializedRef.current = true
    fetchFeed({ searchQuery: '', activeTickers: [], pageNum: 1, append: false })
  }, [])

  useEffect(() => {
    if (!authReady) return
    if (user) {
      loadWatchlistAndTiles()
    } else {
      setWatchlist([])
      setTiles([])
      setTilesLoading(false)
    }
  }, [authReady, user?.id])

  useEffect(() => {
    if (searchLoading || loadingMore || !hasMore) return

    const sentinel = observerRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !loadingMore && !searchLoading) {
        fetchFeed({
          searchQuery: input,
          activeTickers: selectedTickers,
          pageNum: page + 1,
          append: true
        })
      }
    }, { threshold: 0.1, rootMargin: '100px' })

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasMore, loadingMore, searchLoading, page, selectedTickers, input])

  const allTickers = [...new Set([...POPULAR_TICKERS, ...watchlist])]

  return (
    <main style={{
      padding: '24px clamp(16px, 3vw, 40px) 64px',
      maxWidth: '1200px',
      margin: '0 auto',
      width: '100%'
    }}>
      {/* Landing Prompt for Unauthenticated Users */}
      {authReady && !user && (
        <div style={{
          marginBottom: '28px',
          background: 'var(--surface)',
          borderRadius: 'var(--r-panel)',
          border: '1px solid var(--rule)',
          boxShadow: 'var(--shadow-panel)',
          padding: '24px',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '20px'
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px', maxWidth: '640px' }}>
            <div style={{
              width: '44px',
              height: '44px',
              borderRadius: 'var(--r-control)',
              background: 'var(--brand-tint)',
              color: 'var(--brand-ink)',
              display: 'grid',
              placeItems: 'center',
              fontSize: '1.4rem',
              flexShrink: 0
            }}>
              ⚡
            </div>
            <div>
              <span style={{
                fontSize: 'var(--fs-xs)',
                fontWeight: 700,
                color: 'var(--brand-ink)',
                background: 'var(--brand-tint)',
                padding: '2px 8px',
                borderRadius: 'var(--r-chip)'
              }}>
                FinnWinn Analyst Intelligence
              </span>
              <h3 style={{ margin: '6px 0 4px', fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--ink)' }}>
                Research any stock in seconds
              </h3>
              <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', lineHeight: 1.5 }}>
                Triangulate Wall Street targets, technical swing pivots, news sentiment, and statistical risk modeling across your tracked symbols.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <Link
              href="/login"
              style={{
                height: '40px',
                padding: '0 20px',
                background: 'var(--brand)',
                color: '#06231D',
                fontWeight: 700,
                fontSize: 'var(--fs-sm)',
                borderRadius: 'var(--r-control)',
                textDecoration: 'none',
                display: 'inline-flex',
                alignItems: 'center'
              }}
            >
              Sign In →
            </Link>
            <Link
              href="/register"
              style={{
                height: '40px',
                padding: '0 16px',
                background: 'var(--surface)',
                color: 'var(--ink-2)',
                border: '1px solid var(--rule)',
                fontWeight: 600,
                fontSize: 'var(--fs-sm)',
                borderRadius: 'var(--r-control)',
                textDecoration: 'none',
                display: 'inline-flex',
                alignItems: 'center'
              }}
            >
              Register
            </Link>
          </div>
        </div>
      )}

      {/* Tickers Filter Strip */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ margin: 0, fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)' }}>
              Active Market Tickers
            </h2>
            {selectedTickers.length > 0 && (
              <span style={{
                fontSize: 'var(--fs-xs)',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: 'var(--r-chip)',
                background: 'var(--brand-tint)',
                color: 'var(--brand-ink)'
              }}>
                {selectedTickers.length} active
              </span>
            )}
          </div>
          {selectedTickers.length > 0 && (
            <button
              onClick={handleClearAll}
              style={{
                fontSize: 'var(--fs-xs)',
                fontWeight: 600,
                padding: '4px 10px',
                borderRadius: 'var(--r-control)',
                border: '1px solid var(--rule)',
                background: 'var(--surface)',
                color: 'var(--bear)',
                cursor: 'pointer'
              }}
            >
              ✕ Clear filters
            </button>
          )}
        </div>

        <div style={{
          display: 'flex',
          gap: '8px',
          overflowX: 'auto',
          scrollbarWidth: 'none',
          paddingBottom: '4px'
        }}>
          {allTickers.map(ticker => {
            const isWatched = watchlist.includes(ticker)
            const isSelected = selectedTickers.includes(ticker)
            return (
              <button
                key={ticker}
                onClick={() => handleTickerClick(ticker)}
                style={{
                  fontFamily: 'var(--font-figure)',
                  fontSize: '0.95rem',
                  fontWeight: 600,
                  letterSpacing: '.02em',
                  padding: '5px 12px',
                  borderRadius: 'var(--r-chip)',
                  border: isSelected ? '1px solid var(--brand)' : '1px solid var(--rule)',
                  background: isSelected ? 'var(--brand)' : 'var(--surface)',
                  color: isSelected ? '#06231D' : 'var(--ink)',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                  transition: 'all 0.15s ease'
                }}
              >
                {isWatched && <span style={{ color: isSelected ? '#06231D' : 'var(--caution)' }}>★</span>}
                <span>{ticker}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Watchlist Analysis Carousel */}
      {user && tiles.length > 0 && (
        <div style={{ marginBottom: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <h2 style={{ margin: 0, fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)' }}>
              Watchlist Synthesis Highlights
            </h2>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                onClick={() => scroll('left')}
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  border: '1px solid var(--rule)',
                  background: 'var(--surface)',
                  color: 'var(--ink)',
                  cursor: 'pointer',
                  display: 'grid',
                  placeItems: 'center'
                }}
              >
                ←
              </button>
              <button
                onClick={() => scroll('right')}
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  border: '1px solid var(--rule)',
                  background: 'var(--surface)',
                  color: 'var(--ink)',
                  cursor: 'pointer',
                  display: 'grid',
                  placeItems: 'center'
                }}
              >
                →
              </button>
            </div>
          </div>

          <div
            ref={scrollRef}
            style={{
              display: 'flex',
              overflowX: 'auto',
              gap: '14px',
              paddingBottom: '8px',
              scrollbarWidth: 'none'
            }}
          >
            {tiles.map(tile => {
              const rec = (tile.recommendation || 'hold').toLowerCase()
              const isBuy = rec.includes('buy')
              const isSell = rec.includes('sell')
              const chipColor = isBuy ? 'var(--bull)' : isSell ? 'var(--bear)' : 'var(--caution)'
              const chipBg = isBuy ? 'var(--bull-tint)' : isSell ? 'var(--bear-tint)' : 'var(--caution-tint)'

              return (
                <div
                  key={tile.ticker}
                  style={{
                    minWidth: '280px',
                    maxWidth: '320px',
                    flexShrink: 0,
                    background: 'var(--surface)',
                    border: '1px solid var(--rule)',
                    borderRadius: 'var(--r-panel)',
                    boxShadow: 'var(--shadow-panel)',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between'
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '8px' }}>
                      <span style={{ fontFamily: 'var(--font-figure)', fontWeight: 700, fontSize: '1.4rem', color: 'var(--ink)' }}>
                        {tile.ticker}
                      </span>
                      <span style={{
                        fontSize: 'var(--fs-xs)',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: 'var(--r-chip)',
                        background: chipBg,
                        color: chipColor
                      }}>
                        {tile.recommendation?.replace('_', ' ').toUpperCase()}
                      </span>
                    </div>

                    <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                      <span>Target: <b style={{ color: 'var(--ink)' }}>${tile.target_price || tile.price_target || '—'}</b></span>
                      <span>•</span>
                      <span>Horizon: <b style={{ color: 'var(--ink)' }}>{tile.investment_horizon?.replace('_', ' ') || 'Medium'}</b></span>
                    </div>

                    <p style={{
                      margin: '0 0 16px',
                      fontSize: 'var(--fs-xs)',
                      color: 'var(--ink-2)',
                      lineHeight: 1.5,
                      display: '-webkit-box',
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden'
                    }}>
                      {tile.executive_summary || tile.summary || 'Multi-agent analysis verified.'}
                    </p>
                  </div>

                  <button
                    onClick={() => router.push(`/analysis/${tile.ticker}`)}
                    style={{
                      height: '36px',
                      width: '100%',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--rule)',
                      borderRadius: 'var(--r-control)',
                      color: 'var(--brand-ink)',
                      fontWeight: 600,
                      fontSize: 'var(--fs-xs)',
                      cursor: 'pointer'
                    }}
                  >
                    View Synthesis Report →
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Semantic Search Box */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
        <input
          id="search"
          type="text"
          value={input}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSearchSubmit()
          }}
          placeholder={isMobile ? "Search news" : "Search macro trends, company catalysts, Fed rates, semiconductor cycle..."}
          onChange={(e) => setInput(e.target.value)}
          style={{
            flex: 1,
            height: '42px',
            padding: '0 14px',
            borderRadius: 'var(--r-control)',
            border: '1px solid var(--rule)',
            background: 'var(--surface)',
            color: 'var(--ink)',
            fontSize: 'var(--fs-sm)',
            outline: 'none'
          }}
        />
        <button
          type="button"
          onClick={handleSearchSubmit}
          style={{
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
          {searchLoading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {error && (
        <div style={{
          marginBottom: '20px',
          padding: '12px 16px',
          borderRadius: 'var(--r-control)',
          background: 'var(--bear-tint)',
          border: '1px solid var(--bear)',
          color: 'var(--bear)',
          fontSize: 'var(--fs-sm)'
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Chronological Timeline Feed */}
      <section>
        <div style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: '16px',
          paddingBottom: '10px',
          borderBottom: '1px solid var(--rule)'
        }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)' }}>
              {selectedTickers.length > 0 ? (
                <>Market Timeline for {selectedTickers.join(', ')}</>
              ) : input.trim() ? (
                <>Market Timeline for &ldquo;{input}&rdquo;</>
              ) : (
                'Chronological Market Feed'
              )}
            </h3>
            <p style={{ margin: '2px 0 0', fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
              Real-time multi-source wire with verified sentiment &amp; impact ratings
            </p>
          </div>
          {articles.length > 0 && (
            <span style={{
              fontSize: 'var(--fs-xs)',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: 'var(--r-chip)',
              background: 'var(--surface-2)',
              border: '1px solid var(--rule)',
              color: 'var(--ink-3)',
              whiteSpace: 'nowrap'
            }}>
              {articles.length} updates
            </span>
          )}
        </div>

        {articles.length === 0 && !searchLoading && (
          <div style={{
            textAlign: 'center',
            padding: '60px 20px',
            background: 'var(--surface)',
            borderRadius: 'var(--r-panel)',
            border: '1px solid var(--rule)'
          }}>
            <p style={{ fontSize: '2.5rem', margin: '0 0 10px', color: 'var(--ink-3)' }}>◎</p>
            <p style={{ fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)', margin: 0 }}>No headlines found</p>
            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', marginTop: '4px' }}>Try selecting different tickers or clear active filters</p>
          </div>
        )}

        {/* .news Row Pattern from Mockup */}
        <div style={{
          background: 'var(--surface)',
          borderRadius: 'var(--r-panel)',
          border: '1px solid var(--rule)',
          boxShadow: 'var(--shadow-panel)',
          overflow: 'hidden'
        }}>
          {articles.map((article, idx) => {
            const sent = (article.sentiment || 'neutral').toLowerCase()
            const isBull = sent.includes('bull') || sent.includes('pos')
            const isBear = sent.includes('bear') || sent.includes('neg')
            const chipColor = isBull ? 'var(--bull)' : isBear ? 'var(--bear)' : 'var(--neutral)'
            const chipBg = isBull ? 'var(--bull-tint)' : isBear ? 'var(--bear-tint)' : 'var(--neutral-tint)'

            return (
              <div
                key={article.id || idx}
                style={{
                  padding: '16px 20px',
                  borderTop: idx > 0 ? '1px solid var(--rule)' : 'none',
                  display: 'flex',
                  flexWrap: 'wrap',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: '10px 16px',
                  transition: 'background 0.15s'
                }}
              >
                <div style={{ minWidth: 0, flex: '1 1 280px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', flexWrap: 'wrap' }}>
                    {(article.sectors || ['Macro']).map(sec => (
                      <span
                        key={sec}
                        style={{
                          fontSize: 'var(--fs-xs)',
                          fontWeight: 700,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          background: 'var(--surface-2)',
                          border: '1px solid var(--rule)',
                          color: 'var(--ink-3)'
                        }}
                      >
                        {sec}
                      </span>
                    ))}
                    <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                      {article.source} {article.published ? `• ${formatTimeAgo(article.published)}` : ''}
                    </span>
                  </div>

                  <a
                    href={article.url || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      textDecoration: 'none',
                      color: 'var(--ink)',
                      fontWeight: 700,
                      fontSize: 'var(--fs-sm)',
                      lineHeight: 1.4,
                      display: 'block'
                    }}
                  >
                    {article.headline}
                  </a>

                  {article.summary && (
                    <p style={{
                      margin: '6px 0 0',
                      fontSize: 'var(--fs-xs)',
                      color: 'var(--ink-2)',
                      lineHeight: 1.5
                    }}>
                      {article.summary}
                    </p>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0, marginLeft: 'auto' }}>
                  <span style={{
                    fontSize: 'var(--fs-xs)',
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: 'var(--r-chip)',
                    background: chipBg,
                    color: chipColor,
                    textTransform: 'capitalize',
                    whiteSpace: 'nowrap'
                  }}>
                    {article.sentiment}
                  </span>

                  {article.score !== undefined && (
                    <span style={{
                      fontFamily: 'var(--font-figure)',
                      fontSize: 'var(--fs-xs)',
                      fontWeight: 600,
                      color: 'var(--ink-3)',
                      whiteSpace: 'nowrap'
                    }}>
                      Impact {article.score}/10
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Infinite Scroll Sentinel */}
        <div ref={observerRef} style={{ padding: '32px 0', textAlign: 'center' }}>
          {loadingMore && (
            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', margin: 0 }}>
              Loading more updates...
            </p>
          )}
          {!hasMore && articles.length > 0 && (
            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', margin: 0 }}>
              ✓ You&apos;re all caught up
            </p>
          )}
        </div>
      </section>
    </main>
  )
}

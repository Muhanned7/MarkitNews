'use client' 
import { useState, useEffect, useRef } from "react"
import { useAuth } from './context/AuthContext'
import { useRouter } from 'next/navigation'
import { fetchWithRetry } from './utils/apiUtils'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

const SECTOR_COLORS = {
  Technology: { bg: '#e0f2fe', text: '#0369a1', border: '#bae6fd' },
  Financials: { bg: '#fef3c7', text: '#b45309', border: '#fde68a' },
  Healthcare: { bg: '#fce7f3', text: '#be185d', border: '#fbcfe8' },
  Energy: { bg: '#dcfce7', text: '#15803d', border: '#bbf7d0' },
  Consumer: { bg: '#ffedd5', text: '#c2410c', border: '#fed7aa' },
  Macro: { bg: '#f3e8ff', text: '#7e22ce', border: '#e9d5ff' }
}

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

function Page() {
  const [input, setInput] = useState("")
  const [Searchloading, setSearchLoading] = useState(false)
  const [error, setError] = useState(null)
  const [articles, setArticles] = useState([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [similarArticles, setSimilarArticles] = useState([])
  const [watchlist, setWatchlist] = useState([])
  const [selectedTickers, setSelectedTickers] = useState([])
  const router = useRouter()
  const [tiles, setTiles] = useState([])
  const [tilesLoading, setTilesLoading] = useState(true)
  const scrollRef = useRef(null)
  const observerRef = useRef(null)

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

  async function loadWatchlist() {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
    if (!token) {
      setWatchlist([])
      return
    }
    try {
      const response = await fetch('/api/watchlist', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!response.ok) {
        setWatchlist([])
        return
      }
      const data = await response.json()
      setWatchlist(data.tickers?.map(t => t.ticker) || [])
    } catch {
      setWatchlist([])
    }
  }

  async function loadTiles() {
    setTilesLoading(true)
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
      if (!token) {
        setTiles([])
        return
      }
      const res = await fetch('/api/watchlist', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) {
        setTiles([])
        return
      }
      const data = await res.json()
      const tickers = data.tickers?.map(t => t.ticker) || []
      const results = await Promise.all(
        tickers.map(ticker =>
          fetch(`${BACKEND_URL}/analyse/${ticker}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            }
          })
            .then(r => r.json())
            .then(data => ({ ticker, ...data.report, status: 'done' }))
            .catch(() => ({ ticker, status: 'error' }))
        )
      )
      setTiles(results)
    } catch (err) {
      console.error(err)
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
          limit: 6,
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

      if (save && searchQuery) {
        try {
          const simResponse = await fetch('/api/similar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: searchQuery })
          })
          const simData = await simResponse.json()
          setSimilarArticles(simData.results?.matches || [])
        } catch (e) {
          console.warn(e)
        }
      }
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

  useEffect(() => {
    if (Searchloading || loadingMore || !hasMore) return

    const sentinel = observerRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !loadingMore && !Searchloading) {
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
  }, [hasMore, loadingMore, Searchloading, page, selectedTickers, input])

  useEffect(() => {
    fetchFeed({ searchQuery: '', activeTickers: [], pageNum: 1, append: false })
    loadWatchlist()
    loadTiles()
  }, [])

  const allTickers = [...new Set([...POPULAR_TICKERS, ...watchlist])]

  return (
    <main className="min-h-screen p-6" style={{ backgroundColor: '#f0f1f2', color: '#374151' }}>
      
      {/* Tickers & Watchlist Section */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-gray-900">Watch List & Market Tickers</h2>
            {selectedTickers.length > 0 && (
              <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold" style={{ backgroundColor: '#00d4aa22', color: '#008a6e', border: '1px solid #00d4aa66' }}>
                {selectedTickers.length} selected
              </span>
            )}
          </div>
          {selectedTickers.length > 0 && (
            <button
              onClick={handleClearAll}
              className="text-xs font-semibold px-3 py-1.5 rounded-full transition-all border flex items-center gap-1.5 bg-white text-gray-700 hover:bg-gray-100 hover:border-gray-400 border-gray-300 shadow-sm cursor-pointer"
            >
              <span className="text-red-500 font-bold">✕</span> Clear all
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {allTickers.map(ticker => {
            const isWatched = watchlist.includes(ticker)
            const isSelected = selectedTickers.includes(ticker)
            return (
              <button
                key={ticker}
                onClick={() => handleTickerClick(ticker)}
                style={{
                  backgroundColor: isSelected ? '#00d4aa' : '#ffffff',
                  color: isSelected ? '#052e24' : '#374151',
                  fontWeight: isSelected ? '700' : '500',
                  padding: '6px 14px',
                  borderRadius: '20px',
                  fontSize: '13px',
                  border: isSelected ? '1px solid #00a884' : '1px solid #d1d5db',
                  boxShadow: isSelected ? '0 2px 4px rgba(0, 212, 170, 0.4)' : '0 1px 2px rgba(0,0,0,0.04)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
                className="flex items-center gap-1.5 hover:border-teal-400"
              >
                {isWatched && (
                  <span style={{ color: isSelected ? '#052e24' : '#f59e0b', fontSize: '11px' }}>★</span>
                )}
                <span>{ticker}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Analysis Tiles Carousel */}
      {tilesLoading ? (
        <div className="text-center py-16">
          <p className="text-4xl mb-3 animate-pulse text-teal-600">◎</p>
          <p className="text-gray-600 font-medium">Running agent analysis on your watchlist...</p>
          <p className="text-gray-400 text-xs mt-1">Multi-agent equity & risk reports</p>
        </div>
      ) : tiles.length > 0 ? (
        <div className="relative group mb-8">
          <button 
            onClick={() => scroll('left')}
            className="absolute left-[-16px] top-1/2 -translate-y-1/2 z-10 bg-white shadow-lg border rounded-full p-2 hidden md:group-hover:block cursor-pointer hover:bg-gray-50"
          >
            ←
          </button>

          <div 
            ref={scrollRef}
            className="flex overflow-x-auto gap-4 pb-4 no-scrollbar snap-x snap-mandatory"
            style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
          >
            {tiles.map(tile => (
              <div
                key={tile.ticker}
                className="min-w-[280px] max-w-[320px] snap-center bg-white rounded-xl p-5 border border-gray-200 hover:border-teal-400 transition-all shadow-sm flex-shrink-0"
              >
                {tile.status === 'error' ? (
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">{tile.ticker}</h2>
                    <p className="text-red-400 text-sm mt-2">Failed to load analysis</p>
                  </div>
                ) : (
                  <>
                    <div className="flex justify-between items-start mb-3">
                      <h2 className="text-xl font-bold text-gray-900">{tile.ticker}</h2>
                      <span className="text-xs px-2 py-1 rounded font-medium" style={{
                        backgroundColor: tile.recommendation?.includes('buy') ? '#22c55e22' : tile.recommendation?.includes('sell') ? '#ef444422' : '#6b728022',
                        color: tile.recommendation?.includes('buy') ? '#22c55e' : tile.recommendation?.includes('sell') ? '#ef4444' : '#6b7280'
                      }}>
                        {tile.recommendation?.replace('_', ' ').toUpperCase()}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-xs px-2 py-1 rounded" style={{ backgroundColor: '#00d4aa22', color: '#008a6e', fontWeight: 600 }}>
                        Target ${tile.price_target}
                      </span>
                      <span className="text-xs px-2 py-1 rounded" style={{ backgroundColor: '#6b728022', color: '#4b5563' }}>
                        Risk: {tile.risk_reward}
                      </span>
                    </div>

                    <p className="text-sm text-gray-600 line-clamp-3 mb-4">{tile.summary}</p>

                    <button
                      className="w-full py-2 rounded-lg text-sm font-semibold text-black cursor-pointer transition-opacity hover:opacity-90"
                      style={{ backgroundColor: '#00d4aa' }}
                      onClick={() => router.push(`/analysis/${tile.ticker}`)}
                    >
                      View Full Report →
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>

          <button 
            onClick={() => scroll('right')}
            className="absolute right-[-16px] top-1/2 -translate-y-1/2 z-10 bg-white shadow-lg border rounded-full p-2 hidden md:group-hover:block cursor-pointer hover:bg-gray-50"
          >
            →
          </button>
        </div>
      ) : null}

      {/* Search Input Bar */}
      <div className="flex gap-2 mb-6">
        <input 
          id="search" 
          type="text" 
          value={input} 
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSearchSubmit()
          }}
          placeholder="Search macro trends, company catalysts, Fed rates, chip cycle..."
          onChange={(e) => setInput(e.target.value)} 
          className="flex-1 bg-white border border-gray-300 rounded-lg px-4 py-2.5 text-gray-900 placeholder-gray-400 outline-none focus:border-teal-400 shadow-sm"
        />
        <button 
          type="button" 
          onClick={handleSearchSubmit}
          className="px-6 py-2.5 rounded-lg font-semibold text-black cursor-pointer shadow-sm transition-opacity hover:opacity-90"
          style={{ backgroundColor: '#00d4aa' }}
        >
          {Searchloading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {error && (
        <div className="mb-6 px-4 py-3 rounded-lg border text-sm" style={{ backgroundColor: '#ef444422', borderColor: '#ef4444', color: '#b91c1c' }}>
          ⚠ {error}
        </div>
      )}

      {/* Chronological Timeline Feed */}
      <section>
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-gray-300">
          <div>
            <h3 className="text-lg font-bold text-gray-900">
              {selectedTickers.length > 0 ? (
                <>
                  Timeline for <span className="text-teal-700">{selectedTickers.join(', ')}</span>
                </>
              ) : input.trim() ? (
                <>
                  Timeline for <span className="text-teal-700">"{input}"</span>
                </>
              ) : (
                'Chronological Market Timeline'
              )}
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Live chronological stream with AI sentiment & impact ratings
            </p>
          </div>
          {articles.length > 0 && (
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-white border border-gray-200 text-gray-600">
              {articles.length} updates loaded
            </span>
          )}
        </div>

        {articles.length === 0 && !Searchloading && (
          <div className="text-center py-20 bg-white rounded-xl border border-gray-200 shadow-sm">
            <p className="text-5xl mb-3 text-gray-400">◎</p>
            <p className="text-gray-800 text-lg font-semibold">No headlines found</p>
            <p className="text-gray-500 text-sm mt-1">Try selecting different tickers or clear active filters</p>
          </div>
        )}

        <div className="space-y-4">
          {articles.map((article, idx) => (
            <article
              key={article.id || idx}
              className="bg-white rounded-xl p-5 border border-gray-200 hover:border-teal-400 hover:shadow-md transition-all duration-200"
            >
              {/* Header / Badges */}
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div className="flex flex-wrap items-center gap-2">
                  {(article.sectors || ['Macro']).map(sec => {
                    const color = SECTOR_COLORS[sec] || { bg: '#f3f4f6', text: '#374151', border: '#e5e7eb' }
                    return (
                      <span
                        key={sec}
                        className="text-xs font-semibold px-2.5 py-0.5 rounded-full border"
                        style={{
                          backgroundColor: color.bg,
                          color: color.text,
                          borderColor: color.border
                        }}
                      >
                        {sec}
                      </span>
                    )
                  })}
                  {article.published && (
                    <span className="text-xs text-gray-400 font-medium">
                      • {formatTimeAgo(article.published)}
                    </span>
                  )}
                </div>

                <a 
                  href={article.url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-xs font-semibold text-gray-500 hover:text-teal-600 transition-colors flex items-center gap-1"
                >
                  <span>{article.source}</span>
                  <span>↗</span>
                </a>
              </div>

              {/* Title */}
              <h2 className="font-bold text-base md:text-lg text-gray-900 mb-2 leading-snug hover:text-teal-700 transition-colors">
                <a href={article.url} target="_blank" rel="noopener noreferrer">
                  {article.headline}
                </a>
              </h2>

              {/* Summary */}
              <p className="text-sm text-gray-600 mb-3 leading-relaxed">
                {article.summary}
              </p>

              {/* Footer Meta Row */}
              <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-gray-100 text-xs">
                <span
                  className="px-2.5 py-1 rounded-md font-semibold capitalize"
                  style={{
                    backgroundColor:
                      article.sentiment === 'bullish' ? '#dcfce7' :
                      article.sentiment === 'bearish' ? '#fee2e2' : '#f3f4f6',
                    color:
                      article.sentiment === 'bullish' ? '#15803d' :
                      article.sentiment === 'bearish' ? '#b91c1c' : '#4b5563'
                  }}
                >
                  {article.sentiment}
                </span>

                <span 
                  className="px-2.5 py-1 rounded-md font-semibold"
                  style={{ backgroundColor: '#ccfbf1', color: '#0f766e' }}
                >
                  Score {article.score}/10
                </span>

                {article.rationale && (
                  <span className="text-gray-600 bg-gray-50 px-2.5 py-1 rounded-md border border-gray-200">
                    💡 {article.rationale}
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>

        {/* Sentinel & Infinite Scroll Loader */}
        <div ref={observerRef} className="py-8 text-center">
          {loadingMore && (
            <div className="flex items-center justify-center gap-2 text-sm text-gray-600 font-medium">
              <span className="animate-spin text-teal-600 text-lg">◌</span>
              <span>Loading more timeline updates...</span>
            </div>
          )}
          {!hasMore && articles.length > 0 && (
            <p className="text-xs text-gray-500 font-medium">
              ✓ You're all caught up • End of chronological feed
            </p>
          )}
        </div>

        {/* Similar Articles section (when user runs search) */}
        {similarArticles.length > 0 && (
          <div className="mt-12 pt-8 border-t border-gray-300">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Semantically Similar Past Articles</h3>
            <div className="space-y-4">
              {similarArticles.map((item, i) => (
                <div key={item.id || i} className="rounded-xl p-4 bg-white border border-gray-200 shadow-sm">
                  <h4 className="font-semibold text-base mb-1 text-gray-900">{item.metadata?.headline}</h4>
                  <p className="text-sm text-gray-600 mb-2">{item.metadata?.summary}</p>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="px-2 py-1 rounded font-medium bg-teal-50 text-teal-700">
                      Score {item.metadata?.score}/10
                    </span>
                    <span className="px-2 py-1 rounded font-medium bg-gray-100 text-gray-700">
                      {item.metadata?.sentiment}
                    </span>
                    <a 
                      href={item.metadata?.url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-gray-500 hover:text-teal-600 ml-auto flex items-center gap-1"
                    >
                      <span>{item.metadata?.source}</span>
                      <span>↗</span>
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

    </main>
  )
}

export default Page

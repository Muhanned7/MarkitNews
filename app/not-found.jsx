'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

export default function NotFound() {
  const [tickerQuery, setTickerQuery] = useState('')
  const router = useRouter()

  const handleSearch = (e) => {
    e.preventDefault()
    const clean = tickerQuery.trim().toUpperCase()
    if (clean) {
      router.push(`/analysis/${clean}`)
    }
  }

  return (
    <main style={{
      minHeight: 'calc(100vh - 60px)',
      display: 'grid',
      placeItems: 'center',
      padding: '24px 16px',
      background: 'var(--canvas)'
    }}>
      <div style={{
        maxWidth: '520px',
        width: '100%',
        background: 'var(--surface)',
        borderRadius: 'var(--r-panel)',
        border: '1px solid var(--rule)',
        boxShadow: 'var(--shadow-panel)',
        padding: 'clamp(28px, 5vw, 44px)',
        textAlign: 'center'
      }}>
        <div style={{
          fontFamily: 'var(--font-figure)',
          fontSize: '3.5rem',
          fontWeight: 700,
          color: 'var(--brand-ink)',
          lineHeight: 1,
          marginBottom: '10px'
        }}>
          404
        </div>

        <h1 style={{
          fontSize: 'var(--fs-xl)',
          fontWeight: 700,
          color: 'var(--ink)',
          margin: '0 0 8px'
        }}>
          We couldn&apos;t find that page
        </h1>

        <p style={{
          fontSize: 'var(--fs-sm)',
          color: 'var(--ink-2)',
          lineHeight: 1.5,
          margin: '0 0 24px'
        }}>
          The link may be outdated, or the symbol you entered has not been generated yet.
        </p>

        {/* Ticker Search Box */}
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
          <input
            type="search"
            value={tickerQuery}
            onChange={(e) => setTickerQuery(e.target.value)}
            placeholder="Search ticker (e.g. AAPL, NVDA)..."
            aria-label="Search ticker"
            style={{
              flex: 1,
              height: '42px',
              padding: '0 14px',
              borderRadius: 'var(--r-control)',
              border: '1px solid var(--rule)',
              background: 'var(--surface-2)',
              color: 'var(--ink)',
              fontSize: 'var(--fs-sm)',
              outline: 'none'
            }}
          />
          <button
            type="submit"
            style={{
              height: '42px',
              padding: '0 18px',
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

        {/* Action Buttons */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <Link
            href="/"
            style={{
              height: '40px',
              padding: '0 18px',
              background: 'var(--surface-2)',
              color: 'var(--ink)',
              border: '1px solid var(--rule)',
              fontWeight: 600,
              fontSize: 'var(--fs-sm)',
              borderRadius: 'var(--r-control)',
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center'
            }}
          >
            ← Go to News Feed
          </Link>
          <Link
            href="/analysis"
            style={{
              height: '40px',
              padding: '0 18px',
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
            Browse Analyses →
          </Link>
        </div>
      </div>
    </main>
  )
}

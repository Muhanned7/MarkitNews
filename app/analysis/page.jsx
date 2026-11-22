'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

export default function AnalysisIndexPage() {
  const [tickerInput, setTickerInput] = useState('')
  const router = useRouter()

  const handleSearch = (e) => {
    e.preventDefault()
    const clean = tickerInput.trim().toUpperCase()
    if (clean) {
      router.push(`/analysis/${clean}`)
    }
  }

  const FEATURED_TICKERS = [
    { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology', price: '$192.25', chg: '+0.65%' },
    { symbol: 'NVDA', name: 'NVIDIA Corp.', sector: 'Semiconductors', price: '$228.52', chg: '−1.12%' },
    { symbol: 'TSLA', name: 'Tesla Inc.', sector: 'Automotive / AI', price: '$375.23', chg: '+1.45%' },
    { symbol: 'JPM', name: 'JPMorgan Chase & Co.', sector: 'Financials', price: '$331.43', chg: '+0.21%' },
    { symbol: 'MSFT', name: 'Microsoft Corp.', sector: 'Cloud / Software', price: '$428.10', chg: '+0.82%' },
    { symbol: 'AMZN', name: 'Amazon.com Inc.', sector: 'Consumer / Cloud', price: '$186.40', chg: '−0.35%' },
  ]

  return (
    <div style={{ padding: '28px clamp(16px, 3vw, 40px) 64px', maxWidth: '1080px', margin: '0 auto', width: '100%' }}>
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
          Consensus synthesis combining empirical technical pivots, balance-sheet rigor, news sentiment, and statistical risk modeling.
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
            placeholder="Search a ticker, e.g. AAPL"
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

      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)', margin: '0 0 16px' }}>
          Featured Multi-Agent Coverage
        </h2>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '16px'
        }}>
          {FEATURED_TICKERS.map((stock) => {
            const isUp = stock.chg.startsWith('+')
            return (
              <div
                key={stock.symbol}
                onClick={() => router.push(`/analysis/${stock.symbol}`)}
                style={{
                  background: 'var(--surface)',
                  borderRadius: 'var(--r-panel)',
                  boxShadow: 'var(--shadow-panel)',
                  border: '1px solid var(--rule)',
                  padding: '20px',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s ease'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <div>
                    <span style={{
                      fontFamily: 'var(--font-figure)',
                      fontSize: '1.4rem',
                      fontWeight: 700,
                      color: 'var(--ink)'
                    }}>
                      {stock.symbol}
                    </span>
                    <p style={{ margin: '2px 0 0', fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                      {stock.name}
                    </p>
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

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: '16px' }}>
                  <span style={{ fontFamily: 'var(--font-figure)', fontSize: '1.25rem', fontWeight: 600, color: 'var(--ink)' }}>
                    {stock.price}
                  </span>
                  <span style={{
                    fontSize: 'var(--fs-xs)',
                    fontWeight: 700,
                    color: isUp ? 'var(--bull)' : 'var(--bear)'
                  }}>
                    {stock.chg}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

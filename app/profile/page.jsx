'use client'
import { useAuth } from '../context/AuthContext'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useState, useEffect } from 'react'

export default function ProfilePage() {
  const { user, loading, logout } = useAuth()
  const router = useRouter()
  const [watchlistCount, setWatchlistCount] = useState(0)
  const [themePreference, setThemePreference] = useState('system')

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('theme') || 'system'
      const current = document.documentElement.dataset.theme || stored
      setThemePreference(current)
    }

    if (user?.token || (typeof window !== 'undefined' && localStorage.getItem('token'))) {
      const token = user?.token || localStorage.getItem('token')
      fetch('/api/watchlist', {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(res => res.json())
        .then(data => {
          if (Array.isArray(data?.tickers)) {
            setWatchlistCount(data.tickers.length)
          } else if (Array.isArray(data)) {
            setWatchlistCount(data.length)
          }
        })
        .catch(() => {})
    }
  }, [user])

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  const handleThemeChange = (newTheme) => {
    setThemePreference(newTheme)
    if (typeof window !== 'undefined') {
      localStorage.setItem('theme', newTheme)
    }
    if (newTheme === 'system') {
      delete document.documentElement.dataset.theme
    } else {
      document.documentElement.dataset.theme = newTheme
    }
  }

  if (loading) {
    return (
      <div style={{ minHeight: '80vh', display: 'grid', placeItems: 'center', color: 'var(--ink-3)' }}>
        Loading profile...
      </div>
    )
  }

  return (
    <div style={{ padding: '28px clamp(16px, 3vw, 40px) 64px', maxWidth: '840px', margin: '0 auto', width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', gap: '12px' }}>
        <h2 style={{ margin: 0, fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--ink)' }}>
          Analyst Profile &amp; Settings
        </h2>
        <span style={{ 
          fontSize: 'var(--fs-xs)', 
          fontWeight: 700, 
          padding: '3px 10px', 
          borderRadius: 'var(--r-chip)', 
          background: 'var(--bull-tint)', 
          color: 'var(--bull)',
          whiteSpace: 'nowrap'
        }}>
          Account active
        </span>
      </div>

      <div style={{
        background: 'var(--surface)',
        borderRadius: 'var(--r-panel)',
        boxShadow: 'var(--shadow-panel)',
        border: '1px solid var(--rule)',
        overflow: 'hidden',
        marginBottom: '24px'
      }}>
        {/* Header banner */}
        <div style={{
          background: 'var(--surface-2)',
          borderBottom: '1px solid var(--rule)',
          padding: '24px 20px',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          flexWrap: 'wrap'
        }}>
          <div style={{
            width: '54px',
            height: '54px',
            borderRadius: '50%',
            background: 'var(--ink)',
            color: 'var(--surface)',
            display: 'grid',
            placeItems: 'center',
            fontSize: '1.4rem',
            fontWeight: 700,
            flexShrink: 0
          }}>
            {user?.email ? user.email.charAt(0).toUpperCase() : 'U'}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h1 style={{
              margin: 0,
              fontSize: 'var(--fs-xl)',
              fontWeight: 700,
              color: 'var(--ink)',
              overflowWrap: 'break-word',
              wordBreak: 'break-word',
              lineHeight: 1.2
            }}>
              {user?.email ? user.email.split('@')[0] : 'Guest user'}
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', overflowWrap: 'break-word' }}>
              {user?.email ? user.email : 'No active session'}
            </p>
          </div>
        </div>

        {/* Information Grid 2x2 */}
        <div style={{ padding: '24px 20px', display: 'grid', gap: '16px' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '14px'
          }}>
            <div style={{ padding: '16px', borderRadius: 'var(--r-control)', background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
              <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink-3)' }}>Account email</div>
              <p style={{
                margin: '6px 0 0',
                fontSize: 'var(--fs-sm)',
                fontWeight: 700,
                color: 'var(--ink)',
                overflowWrap: 'anywhere',
                wordBreak: 'break-word'
              }}>
                {user?.email || 'Not logged in'}
              </p>
            </div>

            <div style={{ padding: '16px', borderRadius: 'var(--r-control)', background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
              <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink-3)' }}>Active watchlist</div>
              <p style={{ margin: '6px 0 0', fontSize: 'var(--fs-sm)', fontWeight: 700, color: 'var(--ink)' }}>
                {user ? `${watchlistCount} tracked assets` : 'Login to view'}
              </p>
            </div>

            <div style={{ padding: '16px', borderRadius: 'var(--r-control)', background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
              <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink-3)' }}>Session security</div>
              <p style={{ margin: '6px 0 0', fontSize: 'var(--fs-sm)', fontWeight: 700, color: 'var(--bull)' }}>
                {user ? 'Signed in securely' : 'Unauthenticated'}
              </p>
            </div>

            <div style={{ padding: '16px', borderRadius: 'var(--r-control)', background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
              <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink-3)' }}>Data mode</div>
              <p style={{ margin: '6px 0 0', fontSize: 'var(--fs-sm)', fontWeight: 700, color: 'var(--ink)' }}>
                Multi-agent consensus
              </p>
            </div>
          </div>

          <div style={{
            marginTop: '12px',
            paddingTop: '18px',
            borderTop: '1px solid var(--rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            flexWrap: 'wrap'
          }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Link
                href="/analysis"
                style={{
                  height: '38px',
                  padding: '0 14px',
                  borderRadius: 'var(--r-control)',
                  background: 'var(--brand-tint)',
                  color: 'var(--brand-ink)',
                  fontWeight: 600,
                  fontSize: 'var(--fs-sm)',
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center'
                }}
              >
                Explore analysis
              </Link>
              <Link
                href="/"
                style={{
                  height: '38px',
                  padding: '0 14px',
                  borderRadius: 'var(--r-control)',
                  background: 'var(--surface-2)',
                  color: 'var(--ink-2)',
                  border: '1px solid var(--rule)',
                  fontWeight: 600,
                  fontSize: 'var(--fs-sm)',
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center'
                }}
              >
                Market feed
              </Link>
            </div>

            {user && (
              <button
                onClick={handleLogout}
                style={{
                  height: '38px',
                  padding: '0 16px',
                  borderRadius: 'var(--r-control)',
                  background: 'var(--bear-tint)',
                  border: '1px solid var(--bear)',
                  color: 'var(--bear)',
                  fontWeight: 700,
                  fontSize: 'var(--fs-sm)',
                  cursor: 'pointer'
                }}
              >
                Sign out
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Preferences Card */}
      <div style={{
        background: 'var(--surface)',
        borderRadius: 'var(--r-panel)',
        boxShadow: 'var(--shadow-panel)',
        border: '1px solid var(--rule)',
        padding: '24px 20px'
      }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)' }}>
          Workstation Preferences
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <div style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)' }}>Appearance Theme</div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>Switch between light, dark, or system default color modes</div>
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              {['system', 'light', 'dark'].map(t => (
                <button
                  key={t}
                  onClick={() => handleThemeChange(t)}
                  style={{
                    padding: '6px 14px',
                    borderRadius: 'var(--r-control)',
                    fontSize: 'var(--fs-xs)',
                    fontWeight: 600,
                    textTransform: 'capitalize',
                    border: '1px solid var(--rule)',
                    background: themePreference === t ? 'var(--brand)' : 'var(--surface-2)',
                    color: themePreference === t ? '#06231D' : 'var(--ink-2)',
                    cursor: 'pointer'
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--rule)', paddingTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <div style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)' }}>Default Landing Page</div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>Choose your default view upon opening the app</div>
            </div>
            <span style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--brand-ink)', background: 'var(--brand-tint)', padding: '4px 10px', borderRadius: 'var(--r-chip)' }}>
              Market Feed (/)
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

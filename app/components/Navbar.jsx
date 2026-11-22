'use client'
import { useState, useRef, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import styles from './Navbar.module.css'
import BreachAlert from './BreachAlert'

export default function Navbar() {
  const { user, authReady, logout } = useAuth()
  const router = useRouter()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [theme, setTheme] = useState('light')
  const [suggestions, setSuggestions] = useState([])
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [membership, setMembership] = useState(null)
  const dropdownRef = useRef(null)
  const searchContainerRef = useRef(null)
  const searchInputRef = useRef(null)

  useEffect(() => {
    async function fetchMembership() {
      try {
        const token = localStorage.getItem('token') || user?.token
        if (!token) {
          setMembership(null)
          return
        }
        const res = await fetch('/api/billing/wallet', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const data = await res.json()
          setMembership(data.membership || null)
        }
      } catch (e) {}
    }

    if (authReady && user) {
      fetchMembership()
      window.addEventListener('membership-updated', fetchMembership)
      return () => window.removeEventListener('membership-updated', fetchMembership)
    } else {
      setMembership(null)
    }
  }, [authReady, user])

  useEffect(() => {
    // Theme initialization
    const currentTheme = document.documentElement.dataset.theme || 
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    setTheme(currentTheme)
    document.documentElement.dataset.theme = currentTheme

    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false)
      }
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target)) {
        setIsOpen(false)
        setActiveIndex(-1)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)

    // Global Cmd+K / Ctrl+K listener
    function handleKeyDown(e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [])

  // Debounced (150ms) GET /api/tickers?q= lookup
  useEffect(() => {
    const clean = searchQuery.trim()
    if (!clean) {
      setSuggestions([])
      setIsOpen(false)
      setActiveIndex(-1)
      return
    }

    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/tickers?q=${encodeURIComponent(clean)}`)
        if (res.ok) {
          const data = await res.json()
          setSuggestions(data.tickers || [])
          setIsOpen(true)
          setActiveIndex(-1)
        }
      } catch (err) {
        // Silently handle network errors
      }
    }, 150)

    return () => clearTimeout(timer)
  }, [searchQuery])

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark'
    setTheme(nextTheme)
    document.documentElement.dataset.theme = nextTheme
  }

  const toggleNavDrawer = () => {
    document.body.classList.toggle('nav-open')
  }

  const navigateToTicker = (sym) => {
    const target = sym.trim().toUpperCase()
    if (target) {
      router.push(`/analysis/${target}`)
      setSearchQuery('')
      setIsOpen(false)
      setActiveIndex(-1)
    }
  }

function formatSector(sec) {
  if (!sec) return ''
  return sec.split(/[\s/]+/).filter(Boolean).map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ')
}

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    if (activeIndex >= 0 && suggestions[activeIndex]) {
      navigateToTicker(suggestions[activeIndex].symbol)
    } else if (searchQuery.trim()) {
      navigateToTicker(searchQuery)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIndex >= 0 && suggestions[activeIndex]) {
        navigateToTicker(suggestions[activeIndex].symbol)
      } else if (searchQuery.trim()) {
        navigateToTicker(searchQuery)
      }
      return
    }

    if (!isOpen && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      if (suggestions.length > 0) setIsOpen(true)
      return
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex(prev => (prev < suggestions.length - 1 ? prev + 1 : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(prev => (prev > 0 ? prev - 1 : suggestions.length - 1))
    } else if (e.key === 'Escape') {
      setIsOpen(false)
      setActiveIndex(-1)
    }
  }

  return (
    <header className={styles.topbar}>
      <button 
        className={styles.menuBtn} 
        aria-label="Open navigation" 
        onClick={toggleNavDrawer}
      >
        ☰
      </button>

      <Link href="/" className={styles.logo} aria-label="FinnWinn home">
        <span className={styles.logoMark} aria-hidden="true"></span>
        <span>FinnWinn</span>
      </Link>

      <form onSubmit={handleSearchSubmit} className={styles.search} ref={searchContainerRef}>
        <span aria-hidden="true" style={{ cursor: 'pointer' }} onClick={() => searchInputRef.current?.focus()}>⌕</span>
        <input 
          ref={searchInputRef}
          type="text" 
          placeholder="Search tickers" 
          aria-label="Search tickers"
          className={styles.searchInput}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (searchQuery.trim() && suggestions.length > 0) setIsOpen(true)
          }}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls="ticker-suggestions"
          aria-activedescendant={activeIndex >= 0 ? `ticker-opt-${activeIndex}` : undefined}
          autoComplete="off"
        />
        <span className={styles.kbd}>Ctrl K</span>

        {/* QA-008 Autocomplete Dropdown Listbox */}
        {isOpen && searchQuery.trim() && (
          <ul id="ticker-suggestions" role="listbox" className={styles.autocompleteDropdown} aria-label="Ticker search suggestions">
            {suggestions.length > 0 ? (
              suggestions.map((item, idx) => (
                <li
                  key={item.symbol}
                  id={`ticker-opt-${idx}`}
                  role="option"
                  aria-selected={activeIndex === idx}
                  className={`${styles.autocompleteItem} ${activeIndex === idx ? styles.autocompleteItemActive : ''}`}
                  onClick={() => navigateToTicker(item.symbol)}
                  onMouseEnter={() => setActiveIndex(idx)}
                >
                  <div className={styles.autocompleteLeft}>
                    <span className={styles.autocompleteSymbol}>{item.symbol}</span>
                    <span className={styles.autocompleteName}>{item.name}</span>
                  </div>
                  {item.sector && (
                    <span className={styles.autocompleteSector}>{formatSector(item.sector)}</span>
                  )}
                </li>
              ))
            ) : (
              <li className={styles.autocompleteEmpty} onClick={handleSearchSubmit}>
                No matches — press Enter to analyse <strong>{searchQuery.trim().toUpperCase()}</strong>
              </li>
            )}
          </ul>
        )}
      </form>

      <div className={styles.topbarRight}>
        {authReady && user && (
          <Link
            href="/billing"
            style={{
              height: '32px',
              padding: '0 12px',
              borderRadius: 'var(--r-chip)',
              background: membership?.is_pro ? 'var(--brand-tint)' : 'var(--surface-2)',
              border: membership?.is_pro ? '1px solid var(--brand)' : '1px solid var(--rule)',
              color: membership?.is_pro ? 'var(--brand-ink)' : 'var(--ink)',
              fontSize: 'var(--fs-xs)',
              fontWeight: 700,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              whiteSpace: 'nowrap',
            }}
            title={
              membership?.is_pro
                ? 'Pro Package Active — Full Agentic Analysis Enabled'
                : 'Upgrade to Pro Package for Full Agentic Analysis'
            }
          >
            <span>{membership?.is_pro ? '✦ PRO' : '⚡ Upgrade to Pro'}</span>
          </Link>
        )}
        {authReady && user && <BreachAlert />}
        <button 
          className={styles.iconBtn} 
          onClick={toggleTheme} 
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? (
            /* Sun icon */
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>
          ) : (
            /* Moon icon */
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
          )}
        </button>

        {!authReady ? (
          <div className={styles.avatarSkeleton} title="Loading session..." />
        ) : user ? (
          <div className={styles.dropdownWrapper} ref={dropdownRef}>
            <button 
              className={styles.avatar} 
              onClick={() => setDropdownOpen(!dropdownOpen)}
              aria-label="Account menu"
            >
              {user.email ? user.email[0].toUpperCase() : 'U'}
            </button>

            {dropdownOpen && (
              <div className={styles.dropdown}>
                <div className={styles.dropdownHeader}>
                  <p className={styles.dropdownLabel}>Signed in as</p>
                  <p className={styles.dropdownEmail}>{user.email}</p>
                </div>
                <button 
                  className={styles.dropdownItem} 
                  onClick={() => { setDropdownOpen(false); router.push('/portfolio') }}
                >
                  💼 Portfolio
                </button>
                <button 
                  className={styles.dropdownItem} 
                  onClick={() => { setDropdownOpen(false); router.push('/billing') }}
                >
                  💳 Pro &amp; Billing
                </button>
                <button 
                  className={styles.dropdownItem} 
                  onClick={() => { setDropdownOpen(false); router.push('/profile') }}
                >
                  👤 Profile
                </button>
                <button 
                  className={styles.dropdownItemDanger} 
                  onClick={() => { logout(); setDropdownOpen(false); router.push('/login') }}
                >
                  🚪 Logout
                </button>
              </div>
            )}
          </div>
        ) : (
          <>
            <button className={styles.btnSecondary} onClick={() => router.push('/login')}>Login</button>
            <button className={styles.btnPrimary} onClick={() => router.push('/register')}>Register</button>
          </>
        )}
      </div>
    </header>
  )
}
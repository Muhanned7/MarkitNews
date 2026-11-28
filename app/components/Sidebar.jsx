'use client'
import { useAuth } from '../context/AuthContext'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { useState, useEffect } from 'react'
import styles from './Sidebar.module.css'

export default function Sidebar() {
    const { user } = useAuth()
    const pathname = usePathname()
    const [watchlist, setWatchlist] = useState([])

    useEffect(() => {
        if (user) {
            loadWatchlist()
            const handler = () => loadWatchlist()
            window.addEventListener('watchlist-updated', handler)
            return () => window.removeEventListener('watchlist-updated', handler)
        } else {
            setWatchlist([])
        }
    }, [user?.id, user?.email])

    async function loadWatchlist() {
        try {
            const res = await fetch('/api/watchlist', { credentials: 'include' })
            if (!res.ok) return
            const data = await res.json()
            const rawList = data.tickers || []
            const parsed = rawList.map(t => {
                const sym = (typeof t === 'string' ? t : t.ticker)?.toUpperCase()
                return {
                    symbol: sym,
                    price: t.price || null,
                    change_pct: t.change_pct ?? null
                }
            })
            setWatchlist(parsed)
        } catch (err) {
            console.error("Failed to load watchlist in sidebar:", err)
        }
    }

    const closeDrawer = () => {
        if (typeof document !== 'undefined') {
            document.body.classList.remove('nav-open')
        }
    }

    if (!user) return null

    return (
        <aside className={styles.sidebar} aria-label="Main navigation">
            <div className={styles.sideGroup}>
                <div className={styles.sideTitle}>Explore</div>
                <Link
                    href="/"
                    className={styles.navItem}
                    aria-current={pathname === '/' ? 'page' : undefined}
                    onClick={closeDrawer}
                >
                    <span aria-hidden="true">📰</span> News feed
                </Link>
                <Link
                    href="/analysis"
                    className={styles.navItem}
                    aria-current={pathname?.startsWith('/analysis') ? 'page' : undefined}
                    onClick={closeDrawer}
                >
                    <span aria-hidden="true">🤖</span> AI analysis
                </Link>
                <Link
                    href="/contradictions"
                    className={styles.navItem}
                    aria-current={pathname === '/contradictions' ? 'page' : undefined}
                    onClick={closeDrawer}
                >
                    <span aria-hidden="true">⚡</span> Contradiction Radar
                </Link>
                <Link
                    href="/portfolio"
                    className={styles.navItem}
                    aria-current={pathname === '/portfolio' ? 'page' : undefined}
                    onClick={closeDrawer}
                >
                    <span aria-hidden="true">💼</span> Portfolio
                </Link>
                <Link
                    href="/research"
                    className={styles.navItem}
                    aria-current={pathname?.startsWith('/research') ? 'page' : undefined}
                    onClick={closeDrawer}
                >
                    <span aria-hidden="true">🔬</span> Quant Research
                </Link>
                <Link
                    href="/billing"
                    className={styles.navItem}
                    aria-current={pathname === '/billing' ? 'page' : undefined}
                    onClick={closeDrawer}
                >
                    <span aria-hidden="true">💳</span> Pro Package
                </Link>
                <Link
                    href="/profile"
                    className={styles.navItem}
                    aria-current={pathname === '/profile' ? 'page' : undefined}
                    onClick={closeDrawer}
                >
                    <span aria-hidden="true">👤</span> Profile
                </Link>
            </div>

            <div className={styles.sideGroup}>
                <div className={styles.sideTitle}>Watchlist</div>
                {watchlist.length === 0 ? (
                    <p className={styles.empty}>No tickers yet</p>
                ) : (
                    watchlist.map(({ symbol, price, change_pct }) => {
                        const isCurrent = pathname === `/analysis/${symbol}`
                        const hasChange = change_pct !== null && change_pct !== undefined
                        const isUp = hasChange ? change_pct >= 0 : true
                        const chgText = hasChange 
                            ? `${isUp ? '+' : '−'}${Math.abs(change_pct).toFixed(2)}%`
                            : '—'
                        const pxText = price ? `$${price.toFixed(2)}` : 'View report'

                        return (
                            <Link
                                key={symbol}
                                href={`/analysis/${symbol}`}
                                className={styles.wlRow}
                                aria-current={isCurrent ? 'page' : undefined}
                                onClick={closeDrawer}
                            >
                                <span className={styles.wlSym}>{symbol}</span>
                                <span className={`${styles.wlChg} ${isUp ? styles.up : styles.down} num`}>
                                    {chgText}
                                </span>
                                <span className={`${styles.wlPx} num`}>{pxText}</span>
                            </Link>
                        )
                    })
                )}
            </div>
        </aside>
    )
}

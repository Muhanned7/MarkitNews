'use client'
import { useAuth } from '../context/AuthContext'
import { useRouter, usePathname } from 'next/navigation'
import { useState, useEffect } from 'react'
import styles from './Sidebar.module.css'

export default function Sidebar() {
    const { user } = useAuth()
    const router = useRouter()
    const pathname = usePathname()
    const [watchlist, setWatchlist] = useState([])

    useEffect(() => {
        if (user) {
            loadWatchlist()
            const handler = () => loadWatchlist()
            window.addEventListener('watchlist-updated', handler)
            return () => window.removeEventListener('watchlist-updated', handler)
        }
    }, [user])

    async function loadWatchlist() {
        try {
            const token = localStorage.getItem('token') || user?.token
            if (!token) return
            const res = await fetch('/api/watchlist', {
                headers: { 'Authorization': `Bearer ${token}` }
            })
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

    const navigate = (path) => {
        document.body.classList.remove('nav-open')
        router.push(path)
    }

    if (!user) return null

    return (
        <aside className={styles.sidebar} aria-label="Main navigation">
            <div className={styles.sideGroup}>
                <div className={styles.sideTitle}>Explore</div>
                <button
                    className={styles.navItem}
                    aria-current={pathname === '/' ? 'page' : undefined}
                    onClick={() => navigate('/')}
                >
                    <span aria-hidden="true">📰</span> News feed
                </button>
                <button
                    className={styles.navItem}
                    aria-current={pathname?.startsWith('/analysis') ? 'page' : undefined}
                    onClick={() => navigate('/analysis')}
                >
                    <span aria-hidden="true">🤖</span> AI analysis
                </button>
                <button
                    className={styles.navItem}
                    aria-current={pathname === '/contradictions' ? 'page' : undefined}
                    onClick={() => navigate('/contradictions')}
                >
                    <span aria-hidden="true">⚡</span> Contradiction Radar
                </button>
                <button
                    className={styles.navItem}
                    aria-current={pathname === '/portfolio' ? 'page' : undefined}
                    onClick={() => navigate('/portfolio')}
                >
                    <span aria-hidden="true">💼</span> Portfolio
                </button>
                <button
                    className={styles.navItem}
                    aria-current={pathname?.startsWith('/research') ? 'page' : undefined}
                    onClick={() => navigate('/research')}
                >
                    <span aria-hidden="true">🔬</span> Quant Research
                </button>
                <button
                    className={styles.navItem}
                    aria-current={pathname === '/billing' ? 'page' : undefined}
                    onClick={() => navigate('/billing')}
                >
                    <span aria-hidden="true">💳</span> Pro Package
                </button>
                <button
                    className={styles.navItem}
                    aria-current={pathname === '/profile' ? 'page' : undefined}
                    onClick={() => navigate('/profile')}
                >
                    <span aria-hidden="true">👤</span> Profile
                </button>
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
                            <button
                                key={symbol}
                                className={styles.wlRow}
                                aria-current={isCurrent ? 'page' : undefined}
                                onClick={() => navigate(`/analysis/${symbol}`)}
                            >
                                <span className={styles.wlSym}>{symbol}</span>
                                <span className={`${styles.wlChg} ${isUp ? styles.up : styles.down} num`}>
                                    {chgText}
                                </span>
                                <span className={`${styles.wlPx} num`}>{pxText}</span>
                            </button>
                        )
                    })
                )}
            </div>
        </aside>
    )
}
'use client'
import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

export default function BillingPage() {
  const { user, loading } = useAuth()
  const router = useRouter()

  const [packages, setPackages] = useState([])
  const [membership, setMembership] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [pageLoading, setPageLoading] = useState(true)

  // Stripe Sandbox Checkout Sheet state
  const [checkoutSession, setCheckoutSession] = useState(null)
  const [cardName, setCardName] = useState('Alex Rivera')
  const [cardNumber, setCardNumber] = useState('4242 •••• •••• 4242')
  const [cardExpiry, setCardExpiry] = useState('12/29')
  const [cardCvc, setCardCvc] = useState('424')
  const [processingPayment, setProcessingPayment] = useState(false)
  const [bannerMessage, setBannerMessage] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)

  useEffect(() => {
    if (loading) return
    if (!user) {
      router.push('/login')
      return
    }
    loadBillingData()
  }, [user, loading])

  async function loadBillingData() {
    setPageLoading(true)
    try {
      const token = localStorage.getItem('token') || user?.token
      const [pkgRes, walletRes] = await Promise.all([
        fetch('/api/billing/packages'),
        fetch('/api/billing/wallet', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }),
      ])

      if (pkgRes.ok) {
        const pkgData = await pkgRes.json()
        setPackages(pkgData.packages || [])
      }
      if (walletRes.ok) {
        const wData = await walletRes.json()
        setMembership(wData.membership || null)
        setTransactions(wData.transactions || [])
      }

      // Check URL params for auto-checkout or Stripe return
      if (typeof window !== 'undefined') {
        const params = new URLSearchParams(window.location.search)
        if (params.get('checkout') === 'success' && params.get('session_id')) {
          await handleConfirmPayment(params.get('session_id'), params.get('package_id') || 'pro_monthly', '4242')
          window.history.replaceState({}, '', '/billing')
        } else if (params.get('checkout') === 'pro_monthly') {
          window.history.replaceState({}, '', '/billing')
          startProCheckout('pro_monthly')
        }
      }
    } catch (err) {
      setErrorMessage('Could not load billing details.')
    } finally {
      setPageLoading(false)
    }
  }

  async function startProCheckout(packageId = 'pro_monthly') {
    setErrorMessage(null)
    setBannerMessage(null)
    try {
      const token = localStorage.getItem('token') || user?.token
      const res = await fetch('/api/billing/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ package_id: packageId }),
      })
      const data = await res.json()
      if (res.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('email')
        router.push('/login?next=/billing&expired=1')
        return
      }
      if (!res.ok) {
        setErrorMessage(data.detail || 'Unable to start checkout session.')
        return
      }

      if (data.mode === 'stripe_redirect' && data.checkout_url) {
        window.location.href = data.checkout_url
        return
      }

      // Open interactive Stripe Sandbox Checkout sheet
      setCheckoutSession(data)
    } catch (err) {
      setErrorMessage('Could not connect to payment service.')
    }
  }

  async function handleConfirmPayment(sessionId, packageId = 'pro_monthly', last4 = '4242') {
    setProcessingPayment(true)
    setErrorMessage(null)
    try {
      const token = localStorage.getItem('token') || user?.token
      const res = await fetch('/api/billing/confirm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          session_id: sessionId,
          package_id: packageId,
          card_last4: last4,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setErrorMessage(data.detail || 'Payment confirmation failed.')
        return
      }

      setCheckoutSession(null)
      setMembership(data.membership || null)
      if (data.transaction) {
        setTransactions((prev) => [data.transaction, ...prev.filter((t) => t.session_id !== data.transaction.session_id)])
      }
      setBannerMessage(
        data.message ||
          'Pro Package activated! You now have full multi-agent AI analysis for the companies you track.'
      )
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('membership-updated'))
      }
    } catch (err) {
      setErrorMessage('Could not finalize payment confirmation.')
    } finally {
      setProcessingPayment(false)
    }
  }

  if (loading || pageLoading) {
    return (
      <div style={{ minHeight: '80vh', display: 'grid', placeItems: 'center', color: 'var(--ink-3)' }}>
        Loading Pro Package &amp; billing...
      </div>
    )
  }

  const isPro = Boolean(membership?.is_pro)

  return (
    <div style={{ padding: '28px clamp(16px, 3vw, 40px) 64px', maxWidth: '1020px', margin: '0 auto', width: '100%' }}>
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '16px',
          flexWrap: 'wrap',
          marginBottom: '24px',
        }}
      >
        <div>
          <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 700, color: 'var(--brand-ink)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Membership &amp; Capabilities
          </div>
          <h1 style={{ margin: '4px 0 6px', fontSize: 'var(--fs-xl)', fontWeight: 700, color: 'var(--ink)' }}>
            FinnWinn Pro Package
          </h1>
          <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--ink-3)', maxWidth: '640px' }}>
            Unlock autonomous 6-agent equity research, live SEC 10-K &amp; Wikipedia supply-chain discovery, and cross-perspective contradiction alerts for every company you track.
          </p>
        </div>

        <span
          style={{
            fontSize: 'var(--fs-xs)',
            fontWeight: 700,
            padding: '6px 14px',
            borderRadius: 'var(--r-chip)',
            background: isPro ? 'var(--brand-tint)' : 'var(--surface-2)',
            border: isPro ? '1px solid var(--brand)' : '1px solid var(--rule)',
            color: isPro ? 'var(--brand-ink)' : 'var(--ink-2)',
            whiteSpace: 'nowrap',
          }}
        >
          {isPro ? '✦ Pro Package Active' : 'Starter Free Plan'}
        </span>
      </div>

      {/* Confirmation Banner */}
      {bannerMessage && (
        <div
          role="status"
          style={{
            marginBottom: '22px',
            padding: '14px 18px',
            borderRadius: 'var(--r-control)',
            background: 'var(--bull-tint)',
            border: '1px solid var(--bull)',
            color: 'var(--bull)',
            fontSize: 'var(--fs-sm)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <span>✓ {bannerMessage}</span>
          <Link
            href="/analysis"
            style={{
              color: 'var(--bull)',
              fontWeight: 700,
              textDecoration: 'underline',
              whiteSpace: 'nowrap',
            }}
          >
            Run Agentic Analysis →
          </Link>
        </div>
      )}

      {/* Error Banner */}
      {errorMessage && (
        <div
          role="alert"
          style={{
            marginBottom: '22px',
            padding: '12px 16px',
            borderRadius: 'var(--r-control)',
            background: 'var(--bear-tint)',
            border: '1px solid var(--bear)',
            color: 'var(--bear)',
            fontSize: 'var(--fs-sm)',
            fontWeight: 600,
          }}
        >
          ⚠ {errorMessage}
        </div>
      )}

      {/* What You Can Do With Pro — Capabilities Highlight */}
      <div
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--r-panel)',
          border: '1px solid var(--rule)',
          boxShadow: 'var(--shadow-panel)',
          padding: '24px',
          marginBottom: '28px',
        }}
      >
        <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 700, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '14px' }}>
          What You Can Do With the Pro Package
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '16px',
          }}
        >
          <div style={{ padding: '16px', borderRadius: 'var(--r-control)', background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '6px' }}>🤖</div>
            <div style={{ fontWeight: 700, fontSize: 'var(--fs-sm)', color: 'var(--ink)', marginBottom: '4px' }}>
              Agentic Analysis for Tracked Companies
            </div>
            <p style={{ margin: 0, fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', lineHeight: 1.5 }}>
              Deploy 6 specialist AI agents (News, Sentiment, Fundamentals, Technicals, Equity Research &amp; Risk) on any company in your watchlist.
            </p>
          </div>

          <div style={{ padding: '16px', borderRadius: 'var(--r-control)', background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '6px' }}>🏭</div>
            <div style={{ fontWeight: 700, fontSize: 'var(--fs-sm)', color: 'var(--ink)', marginBottom: '4px' }}>
              Corporate Footprint &amp; Supply Chain
            </div>
            <p style={{ margin: 0, fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', lineHeight: 1.5 }}>
              Uncover manufacturing hubs and Tier-1 suppliers verified directly against SEC 10-K filings, Wikipedia, and Link A/B/C guardrails.
            </p>
          </div>

          <div style={{ padding: '16px', borderRadius: 'var(--r-control)', background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '6px' }}>⚡</div>
            <div style={{ fontWeight: 700, fontSize: 'var(--fs-sm)', color: 'var(--ink)', marginBottom: '4px' }}>
              Contradiction Radar
            </div>
            <p style={{ margin: 0, fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', lineHeight: 1.5 }}>
              Compare Western financial wire narratives against localized native-language press from the company&apos;s overseas hubs.
            </p>
          </div>

          <div style={{ padding: '16px', borderRadius: 'var(--r-control)', background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '6px' }}>🔬</div>
            <div style={{ fontWeight: 700, fontSize: 'var(--fs-sm)', color: 'var(--ink)', marginBottom: '4px' }}>
              Quant Factor Research &amp; Sizing
            </div>
            <p style={{ margin: 0, fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', lineHeight: 1.5 }}>
              Access quantitative factor breakdowns, point-in-time thesis drift comparisons, and volatility-targeted position sizing.
            </p>
          </div>
        </div>
      </div>

      {/* Plan Comparison Cards: Starter Free vs Pro Package */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: '20px',
          marginBottom: '32px',
        }}
      >
        {packages.map((pkg) => {
          const isProCard = pkg.id === 'pro_monthly'
          const isCurrentPlan = (isPro && isProCard) || (!isPro && pkg.id === 'free')

          return (
            <div
              key={pkg.id}
              style={{
                background: 'var(--surface)',
                borderRadius: 'var(--r-panel)',
                border: isProCard ? '2px solid var(--brand)' : '1px solid var(--rule)',
                boxShadow: 'var(--shadow-panel)',
                padding: '26px 24px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '10px' }}>
                  <span style={{ fontWeight: 700, fontSize: 'var(--fs-lg)', color: 'var(--ink)' }}>
                    {pkg.name}
                  </span>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '3px 10px',
                      borderRadius: 'var(--r-chip)',
                      background: isProCard ? 'var(--brand-tint)' : 'var(--surface-2)',
                      color: isProCard ? 'var(--brand-ink)' : 'var(--ink-3)',
                      textTransform: 'uppercase',
                    }}
                  >
                    {isCurrentPlan ? 'Active Plan' : pkg.badge}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px', marginBottom: '10px' }}>
                  <span style={{ fontFamily: 'var(--font-figure)', fontSize: '2.4rem', fontWeight: 700, color: 'var(--ink)', lineHeight: 1 }}>
                    ${pkg.price_usd}
                  </span>
                  <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 600 }}>
                    {pkg.price_usd > 0 ? '/ month' : 'forever'}
                  </span>
                </div>

                <p style={{ margin: '0 0 18px', fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', lineHeight: 1.55 }}>
                  {pkg.description}
                </p>

                <div style={{ borderTop: '1px solid var(--rule)', paddingTop: '16px', marginBottom: '22px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ink-3)', textTransform: 'uppercase', marginBottom: '10px' }}>
                    What&apos;s Included
                  </div>
                  <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: '9px' }}>
                    {(pkg.capabilities || []).map((cap, i) => (
                      <li
                        key={i}
                        style={{
                          fontSize: 'var(--fs-xs)',
                          color: 'var(--ink)',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '8px',
                          lineHeight: 1.45,
                        }}
                      >
                        <span style={{ color: 'var(--brand-ink)', fontWeight: 700 }}>✓</span>
                        <span>{cap}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {isProCard ? (
                <button
                  onClick={() => startProCheckout('pro_monthly')}
                  style={{
                    width: '100%',
                    height: '42px',
                    borderRadius: 'var(--r-control)',
                    background: 'var(--brand)',
                    color: '#081c17',
                    border: 0,
                    fontWeight: 700,
                    fontSize: 'var(--fs-sm)',
                    cursor: 'pointer',
                  }}
                >
                  {isPro ? 'Renew / Extend Pro Package ($19)' : 'Upgrade to Pro Package ($19/mo)'}
                </button>
              ) : (
                <button
                  disabled
                  style={{
                    width: '100%',
                    height: '42px',
                    borderRadius: 'var(--r-control)',
                    background: 'var(--surface-2)',
                    color: 'var(--ink-3)',
                    border: '1px solid var(--rule)',
                    fontWeight: 600,
                    fontSize: 'var(--fs-sm)',
                    cursor: 'default',
                  }}
                >
                  {isPro ? 'Included in Pro' : 'Current Plan'}
                </button>
              )}
            </div>
          )
        })}
      </div>

      {/* Payment Receipt History */}
      <div
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--r-panel)',
          border: '1px solid var(--rule)',
          boxShadow: 'var(--shadow-panel)',
          padding: '22px 24px',
        }}
      >
        <h3 style={{ margin: '0 0 14px', fontSize: 'var(--fs-base)', fontWeight: 700, color: 'var(--ink)' }}>
          Billing &amp; Payment Receipts
        </h3>

        {transactions.length === 0 ? (
          <p style={{ margin: 0, fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
            No payments recorded yet. Upgrade to the Pro Package above to unlock full agentic analysis for the companies you track.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--fs-xs)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--rule)', textAlign: 'left', color: 'var(--ink-3)' }}>
                  <th style={{ padding: '8px 10px' }}>Date</th>
                  <th style={{ padding: '8px 10px' }}>Package</th>
                  <th style={{ padding: '8px 10px' }}>Amount</th>
                  <th style={{ padding: '8px 10px' }}>Payment Method</th>
                  <th style={{ padding: '8px 10px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((tx) => (
                  <tr key={tx.session_id} style={{ borderBottom: '1px solid var(--rule)', color: 'var(--ink)' }}>
                    <td style={{ padding: '10px' }}>
                      {tx.completed_at ? new Date(tx.completed_at).toLocaleDateString() : 'Just now'}
                    </td>
                    <td style={{ padding: '10px', fontWeight: 700 }}>{tx.package_name}</td>
                    <td style={{ padding: '10px', fontFamily: 'var(--font-figure)', fontSize: '0.95rem', fontWeight: 700 }}>
                      ${((tx.amount_cents || 1900) / 100).toFixed(2)} {tx.currency || 'USD'}
                    </td>
                    <td style={{ padding: '10px', color: 'var(--ink-2)' }}>
                      Card ending in •••• {tx.card_last4 || '4242'}
                    </td>
                    <td style={{ padding: '10px' }}>
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: 'var(--r-chip)',
                          background: 'var(--bull-tint)',
                          color: 'var(--bull)',
                          fontWeight: 700,
                          textTransform: 'capitalize',
                        }}
                      >
                        {tx.status || 'completed'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Interactive Stripe Checkout Modal (Local Sandbox Mode) */}
      {checkoutSession && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="stripe-checkout-title"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            background: 'rgba(11, 15, 23, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'grid',
            placeItems: 'center',
            padding: '16px',
          }}
          onClick={() => !processingPayment && setCheckoutSession(null)}
        >
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--rule)',
              borderRadius: 'var(--r-panel)',
              boxShadow: 'var(--shadow-panel)',
              maxWidth: '460px',
              width: '100%',
              padding: '26px 24px',
              color: 'var(--ink)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  padding: '3px 9px',
                  borderRadius: 'var(--r-chip)',
                  background: 'var(--brand-tint)',
                  color: 'var(--brand-ink)',
                }}
              >
                Stripe Checkout · Test Mode
              </span>
              <button
                onClick={() => setCheckoutSession(null)}
                disabled={processingPayment}
                style={{ background: 'transparent', border: 0, color: 'var(--ink-3)', fontSize: '1.15rem', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            <h3 id="stripe-checkout-title" style={{ margin: '0 0 4px', fontSize: 'var(--fs-lg)', fontWeight: 700 }}>
              Subscribe to {checkoutSession.package?.name || 'Pro Package'}
            </h3>
            <p style={{ margin: '0 0 18px', fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
              Unlock full multi-agent AI analysis for the companies you track.
            </p>

            <div
              style={{
                padding: '12px 14px',
                borderRadius: 'var(--r-control)',
                background: 'var(--surface-2)',
                border: '1px solid var(--rule)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '18px',
              }}
            >
              <span style={{ fontSize: 'var(--fs-sm)', fontWeight: 600 }}>Total due today</span>
              <span style={{ fontFamily: 'var(--font-figure)', fontSize: '1.4rem', fontWeight: 700 }}>
                ${checkoutSession.package?.price_usd || 19}.00 USD
              </span>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                const cleanDigits = cardNumber.replace(/\D/g, '')
                const last4 = cleanDigits.slice(-4) || '4242'
                handleConfirmPayment(checkoutSession.session_id, checkoutSession.package?.id || 'pro_monthly', last4)
              }}
            >
              <div style={{ display: 'grid', gap: '12px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink-2)', marginBottom: '4px' }}>
                    Cardholder Name
                  </label>
                  <input
                    type="text"
                    required
                    value={cardName}
                    onChange={(e) => setCardName(e.target.value)}
                    style={{
                      width: '100%',
                      height: '38px',
                      padding: '0 12px',
                      borderRadius: 'var(--r-control)',
                      border: '1px solid var(--rule)',
                      background: 'var(--surface-2)',
                      color: 'var(--ink)',
                      fontSize: 'var(--fs-sm)',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink-2)', marginBottom: '4px' }}>
                    Card Number (Stripe Test Card)
                  </label>
                  <input
                    type="text"
                    required
                    value={cardNumber}
                    onChange={(e) => setCardNumber(e.target.value)}
                    style={{
                      width: '100%',
                      height: '38px',
                      padding: '0 12px',
                      borderRadius: 'var(--r-control)',
                      border: '1px solid var(--rule)',
                      background: 'var(--surface-2)',
                      color: 'var(--ink)',
                      fontSize: 'var(--fs-sm)',
                    }}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink-2)', marginBottom: '4px' }}>
                      Expiry
                    </label>
                    <input
                      type="text"
                      required
                      value={cardExpiry}
                      onChange={(e) => setCardExpiry(e.target.value)}
                      style={{
                        width: '100%',
                        height: '38px',
                        padding: '0 12px',
                        borderRadius: 'var(--r-control)',
                        border: '1px solid var(--rule)',
                        background: 'var(--surface-2)',
                        color: 'var(--ink)',
                        fontSize: 'var(--fs-sm)',
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink-2)', marginBottom: '4px' }}>
                      CVC
                    </label>
                    <input
                      type="text"
                      required
                      value={cardCvc}
                      onChange={(e) => setCardCvc(e.target.value)}
                      style={{
                        width: '100%',
                        height: '38px',
                        padding: '0 12px',
                        borderRadius: 'var(--r-control)',
                        border: '1px solid var(--rule)',
                        background: 'var(--surface-2)',
                        color: 'var(--ink)',
                        fontSize: 'var(--fs-sm)',
                      }}
                    />
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={processingPayment}
                style={{
                  width: '100%',
                  height: '42px',
                  borderRadius: 'var(--r-control)',
                  background: 'var(--brand)',
                  color: '#081c17',
                  border: 0,
                  fontWeight: 700,
                  fontSize: 'var(--fs-sm)',
                  cursor: processingPayment ? 'wait' : 'pointer',
                }}
              >
                {processingPayment ? 'Confirming payment...' : `Pay $${checkoutSession.package?.price_usd || 19}.00 & Unlock Pro`}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

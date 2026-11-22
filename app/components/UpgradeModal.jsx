'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

/**
 * Global 402 Payment Required / Pro Package Upgrade Modal.
 * Never shows raw token numbers — strictly highlights what the user can do with the Pro Package.
 */
export default function UpgradeModal() {
  const [modalData, setModalData] = useState(null)
  const router = useRouter()

  useEffect(() => {
    function handleOpen(e) {
      setModalData(
        e.detail || {
          code: 'PRO_UPGRADE_REQUIRED',
          message:
            'Upgrade to the Pro Package to unlock full multi-agent AI analysis and live supply-chain intelligence for the companies you track.',
          feature_name: 'Agentic Company Analysis',
        }
      )
    }
    window.addEventListener('open-upgrade-modal', handleOpen)
    return () => window.removeEventListener('open-upgrade-modal', handleOpen)
  }, [])

  if (!modalData) return null

  const goToProCheckout = () => {
    setModalData(null)
    router.push('/billing?checkout=pro_monthly')
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="upgrade-modal-title"
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
      onClick={() => setModalData(null)}
    >
      <div
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--rule)',
          borderRadius: 'var(--r-panel)',
          boxShadow: 'var(--shadow-panel)',
          maxWidth: '500px',
          width: '100%',
          padding: '28px 24px',
          color: 'var(--ink)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
          <span
            style={{
              fontSize: 'var(--fs-xs)',
              fontWeight: 700,
              padding: '4px 10px',
              borderRadius: 'var(--r-chip)',
              background: 'var(--brand-tint)',
              color: 'var(--brand-ink)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            ✦ Pro Package Feature
          </span>
          <button
            onClick={() => setModalData(null)}
            aria-label="Close modal"
            style={{
              background: 'transparent',
              border: 0,
              color: 'var(--ink-3)',
              fontSize: '1.2rem',
              cursor: 'pointer',
            }}
          >
            ✕
          </button>
        </div>

        <h3 id="upgrade-modal-title" style={{ margin: '0 0 8px', fontSize: 'var(--fs-lg)', fontWeight: 700 }}>
          Unlock {modalData.feature_name || 'Agentic AI Analysis'} with Pro
        </h3>

        <p style={{ margin: '0 0 18px', fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', lineHeight: 1.55 }}>
          {modalData.message}
        </p>

        <div
          style={{
            padding: '18px',
            borderRadius: 'var(--r-control)',
            border: '2px solid var(--brand)',
            background: 'var(--surface-2)',
            marginBottom: '22px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '10px' }}>
            <span style={{ fontWeight: 700, fontSize: 'var(--fs-base)', color: 'var(--ink)' }}>
              FinnWinn Pro Package
            </span>
            <span style={{ fontFamily: 'var(--font-figure)', fontSize: '1.5rem', fontWeight: 700, color: 'var(--ink)' }}>
              $19<span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 500 }}>/month</span>
            </span>
          </div>

          <ul style={{ margin: 0, paddingLeft: '18px', display: 'grid', gap: '8px', fontSize: 'var(--fs-xs)', color: 'var(--ink-2)' }}>
            <li>
              <strong>Agentic Analysis for Tracked Companies:</strong> Run all 6 specialist AI agents + synthesizer consensus on your watchlist stocks.
            </li>
            <li>
              <strong>Live Corporate Footprint &amp; Supply Chain:</strong> Autonomous SEC 10-K, Wikipedia &amp; web supplier discovery.
            </li>
            <li>
              <strong>Contradiction Radar &amp; Quant Research:</strong> Spot divergence between Western wires and local factory press.
            </li>
          </ul>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            onClick={() => setModalData(null)}
            style={{
              padding: '9px 14px',
              borderRadius: 'var(--r-control)',
              background: 'transparent',
              border: '1px solid var(--rule)',
              color: 'var(--ink-3)',
              fontWeight: 600,
              fontSize: 'var(--fs-xs)',
              cursor: 'pointer',
            }}
          >
            Not now
          </button>
          <button
            onClick={goToProCheckout}
            style={{
              padding: '9px 18px',
              borderRadius: 'var(--r-control)',
              background: 'var(--brand)',
              border: 0,
              color: '#081c17',
              fontWeight: 700,
              fontSize: 'var(--fs-xs)',
              cursor: 'pointer',
            }}
          >
            Upgrade to Pro ($19/mo) →
          </button>
        </div>
      </div>
    </div>
  )
}

'use client'
import { useAuth } from '../context/AuthContext'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import ContradictionRadar from '../components/ContradictionRadar'

export default function ContradictionsPage() {
  const { user, authReady } = useAuth()
  const router = useRouter()

  if (!authReady) {
    return (
      <main style={{ minHeight: 'calc(100vh - 60px)', padding: '24px clamp(16px, 3vw, 40px) 64px', background: 'var(--canvas)' }}>
        <div style={{ maxWidth: '1180px', margin: '0 auto' }}>
          <div style={{
            height: '420px',
            borderRadius: 'var(--r-panel)',
            background: 'var(--surface)',
            border: '1px solid var(--rule)',
            animation: 'pulse 1.5s ease-in-out infinite'
          }} />
        </div>
      </main>
    )
  }

  if (!user) {
    return (
      <main style={{ minHeight: 'calc(100vh - 60px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 16px', background: 'var(--canvas)' }}>
        <div style={{
          maxWidth: '520px',
          width: '100%',
          background: 'var(--surface)',
          borderRadius: 'var(--r-panel)',
          border: '1px solid var(--rule)',
          boxShadow: 'var(--shadow-panel)',
          padding: 'clamp(24px, 5vw, 40px)',
          textAlign: 'center'
        }}>
          <div style={{
            width: '48px',
            height: '48px',
            borderRadius: 'var(--r-control)',
            background: 'var(--brand-tint)',
            color: 'var(--brand-ink)',
            display: 'grid',
            placeItems: 'center',
            fontSize: '1.5rem',
            margin: '0 auto 16px'
          }}>
            ⚡
          </div>
          <span style={{
            fontSize: 'var(--fs-xs)',
            fontWeight: 700,
            padding: '2px 8px',
            borderRadius: 'var(--r-chip)',
            background: 'var(--brand-tint)',
            color: 'var(--brand-ink)'
          }}>
            Members Only Access
          </span>
          <h1 style={{ fontSize: 'var(--fs-xl)', fontWeight: 700, color: 'var(--ink)', margin: '14px 0 8px' }}>
            Sign In to Unlock Contradiction Radar
          </h1>
          <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', lineHeight: 1.5, marginBottom: '24px' }}>
            Triangulate Western financial wires, local on-the-ground reports, and corporate PR to catch discrepancies and market spin.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', flexWrap: 'wrap' }}>
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
              Create Account
            </Link>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main style={{ minHeight: 'calc(100vh - 60px)', padding: '24px clamp(16px, 3vw, 40px) 64px', background: 'var(--canvas)' }}>
      <div style={{ maxWidth: '1180px', margin: '0 auto' }}>
        <ContradictionRadar />
      </div>
    </main>
  )
}

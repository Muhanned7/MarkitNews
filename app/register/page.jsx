'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '../context/AuthContext'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const { user, setUser } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (user) {
      router.replace('/')
    }
  }, [user, router])

  const isLengthMet = password.length >= 8

  async function handleRegister(e) {
    if (e) e.preventDefault()
    const cleanEmail = email.trim()
    if (!cleanEmail || !password) {
      setError('Please enter both email and password.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: cleanEmail, password })
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Registration failed.')
        return
      }
      localStorage.setItem('token', data.token)
      localStorage.setItem('email', data.email)
      setUser({ token: data.token, email: data.email })
      router.replace('/')
    } catch (err) {
      setError('Unable to connect to authentication service.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main style={{
      minHeight: 'calc(100vh - 60px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 16px',
      background: 'var(--canvas)'
    }}>
      <div style={{
        background: 'var(--surface)',
        borderRadius: 'var(--r-panel)',
        border: '1px solid var(--rule)',
        boxShadow: 'var(--shadow-panel)',
        padding: 'clamp(24px, 5vw, 36px)',
        width: '100%',
        maxWidth: '420px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
          <span style={{
            width: '14px',
            height: '14px',
            borderRadius: '4px',
            background: 'var(--brand)',
            transform: 'rotate(45deg)',
            display: 'inline-block'
          }}></span>
          <span style={{
            fontFamily: 'var(--font-figure)',
            fontWeight: 700,
            fontSize: '1.75rem',
            letterSpacing: '.01em',
            color: 'var(--ink)'
          }}>
            FinnWinn
          </span>
        </div>
        <p style={{ margin: '0 0 24px', fontSize: 'var(--fs-sm)', color: 'var(--ink-3)' }}>
          Create your analyst workstation account
        </p>

        {error && (
          <div 
            role="alert"
            style={{
              marginBottom: '20px',
              padding: '10px 14px',
              borderRadius: 'var(--r-control)',
              background: 'var(--bear-tint)',
              border: '1px solid var(--bear)',
              color: 'var(--bear)',
              fontSize: 'var(--fs-xs)',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            <span aria-hidden="true">⚠</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleRegister}>
          <div style={{ marginBottom: '16px' }}>
            <label 
              htmlFor="email"
              style={{
                display: 'block',
                fontSize: 'var(--fs-xs)',
                fontWeight: 600,
                color: 'var(--ink-2)',
                marginBottom: '6px'
              }}
            >
              Account email
            </label>
            <input
              id="email"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              data-testid="email-input"
              required
              style={{
                width: '100%',
                height: '42px',
                padding: '0 12px',
                borderRadius: 'var(--r-control)',
                border: '1px solid var(--rule)',
                background: 'var(--surface-2)',
                color: 'var(--ink)',
                fontSize: 'var(--fs-sm)',
                outline: 'none'
              }}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label 
              htmlFor="password"
              style={{
                display: 'block',
                fontSize: 'var(--fs-xs)',
                fontWeight: 600,
                color: 'var(--ink-2)',
                marginBottom: '6px'
              }}
            >
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                data-testid="password-input"
                required
                style={{
                  width: '100%',
                  height: '42px',
                  padding: '0 40px 0 12px',
                  borderRadius: 'var(--r-control)',
                  border: '1px solid var(--rule)',
                  background: 'var(--surface-2)',
                  color: 'var(--ink)',
                  fontSize: 'var(--fs-sm)',
                  outline: 'none'
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                style={{
                  position: 'absolute',
                  right: '8px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--ink-3)',
                  cursor: 'pointer',
                  fontSize: 'var(--fs-xs)',
                  padding: '4px 6px'
                }}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginTop: '6px',
              fontSize: '11px',
              color: isLengthMet ? 'var(--bull)' : 'var(--ink-3)',
              transition: 'color 0.15s ease'
            }}>
              <span>{isLengthMet ? '✓' : '•'}</span>
              <span>Minimum 8 characters</span>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            data-testid="register-button"
            style={{
              width: '100%',
              height: '42px',
              background: 'var(--brand)',
              color: '#06231D',
              fontWeight: 700,
              fontSize: 'var(--fs-sm)',
              borderRadius: 'var(--r-control)',
              border: 'none',
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.75 : 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              marginTop: '8px'
            }}
          >
            {loading && (
              <span style={{
                width: '14px',
                height: '14px',
                border: '2px solid #06231D',
                borderTopColor: 'transparent',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite'
              }}></span>
            )}
            <span>{loading ? 'Creating account...' : 'Create account'}</span>
          </button>
        </form>

        <p style={{
          fontSize: 'var(--fs-xs)',
          color: 'var(--ink-3)',
          marginTop: '20px',
          textAlign: 'center'
        }}>
          Already have an account?{' '}
          <Link href="/login" style={{ color: 'var(--brand-ink)', fontWeight: 600, textDecoration: 'none' }}>
            Sign in
          </Link>
        </p>
      </div>
    </main>
  )
}
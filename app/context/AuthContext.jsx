'use client'
import { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const fetchedRef = useRef(false)

  const refreshSession = useCallback(async () => {
    try {
      // Clean up any legacy insecure localStorage token/email (PROD-014)
      try {
        localStorage.removeItem('token')
        localStorage.removeItem('email')
      } catch {}

      const res = await fetch('/api/auth/me', {
        credentials: 'include',
        cache: 'no-store',
      })
      if (!res.ok) {
        setUser(null)
        return null
      }
      const data = await res.json()
      if (data.authenticated) {
        const sessionUser = {
          id: data.id,
          email: data.email,
          plan_code: data.plan_code || 'free',
          plan_name: data.plan_name || 'Starter Free',
          has_agentic_access: Boolean(data.has_agentic_access),
          capabilities: data.capabilities || [],
        }
        setUser(sessionUser)
        return sessionUser
      }
      setUser(null)
      return null
    } catch {
      setUser(null)
      return null
    } finally {
      setAuthReady(true)
    }
  }, [])

  useEffect(() => {
    if (fetchedRef.current) return
    fetchedRef.current = true
    refreshSession()
  }, [refreshSession])

  const logout = useCallback(async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    } catch {}
    try {
      localStorage.removeItem('token')
      localStorage.removeItem('email')
    } catch {}
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading: !authReady, authReady, logout, setUser, refreshSession }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

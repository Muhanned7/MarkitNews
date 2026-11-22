'use client'
import { createContext, useContext, useEffect, useState } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [authReady, setAuthReady] = useState(false)

  useEffect(() => {
    async function initSession() {
      try {
        const token = localStorage.getItem('token')
        const email = localStorage.getItem('email')
        if (token && email) {
          // Verify stored token against backend so expired/rotated JWTs don't leave a dead session
          try {
            const res = await fetch('/api/billing/wallet', {
              headers: { Authorization: `Bearer ${token}` },
            })
            if (res.status === 401) {
              localStorage.removeItem('token')
              localStorage.removeItem('email')
              setUser(null)
              setAuthReady(true)
              return
            }
          } catch (netErr) {
            // Keep session if backend is temporarily unreachable
          }
          setUser({ token, email })
        }
      } catch (e) {
        // localStorage may fail in restricted browser contexts
      } finally {
        setAuthReady(true)
      }
    }
    initSession()
  }, [])

  function logout() {
    try {
      localStorage.removeItem('token')
      localStorage.removeItem('email')
    } catch (e) {}
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading: !authReady, authReady, logout, setUser }}>
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
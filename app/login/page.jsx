'use client'
import { useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '../context/AuthContext'


const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export default function Login() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState(null)
    const [loading, setLoading] = useState(false)
    const { setUser } = useAuth()
    const router = useRouter()
 

    async function handleLogin() {
        setLoading(true)
        setError(null)
        try {
            const res = await fetch(`${BACKEND_URL}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            })
            const data = await res.json()
            console.log("response:", data)  
            if (!res.ok) {
                console.log("res not ok")
                setError(data.detail)
                return
            }
            localStorage.setItem('token', data.token)
            localStorage.setItem('email', data.email)
            setUser({ token: data.token, email: data.email })
            router.replace('/')
        } catch (err) {
            console.log("error", err)
            setError('Something went wrong', err)
        } finally {
            setLoading(false)
        }
    }

    return (
        <main className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#f0f1f2' }}>
            <div className="bg-white rounded-xl p-8 w-full max-w-md shadow-sm">
                <h1 className="text-2xl font-bold mb-1">market<span style={{ color: '#00d4aa' }}>pulse</span></h1>
                <p className="text-gray-400 text-sm mb-6">Sign in to your account</p>

                {error && (
                    <div className="mb-4 px-4 py-3 rounded-lg border text-sm" style={{ backgroundColor: '#ef444422', borderColor: '#ef4444', color: '#ef4444' }}>
                        ⚠ {error}
                    </div>
                )}

                <input
                    type="email"
                    placeholder="Email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-4 py-2 mb-3 text-black outline-none focus:border-teal-400"
                />
                <input
                    type="password"
                    placeholder="Password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleLogin()}
                    className="w-full border border-gray-300 rounded-lg px-4 py-2 mb-4 text-black outline-none focus:border-teal-400"
                />
                <button
                    onClick={handleLogin}
                    className="w-full py-2 rounded-lg font-medium text-black"
                    style={{ backgroundColor: '#00d4aa' }}
                >
                    {loading ? 'Signing in...' : 'Sign in'}
                </button>
                <p className="text-sm text-gray-400 mt-4 text-center">
                    No account? <a href="/register" className="text-teal-500">Register</a>
                </p>
            </div>
        </main>
    )
}
'use client'
import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { useRouter } from 'next/navigation'

export default function ExternalApiTelemetryPage() {
  const { user, loading } = useAuth()
  const router = useRouter()
  const [data, setData] = useState(null)
  const [pageLoading, setPageLoading] = useState(true)
  const [error, setError] = useState(null)
  const [categoryFilter, setCategoryFilter] = useState('All')
  const [providerFilter, setProviderFilter] = useState('all')
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchTelemetry = useCallback(async () => {
    try {
      const res = await fetch('/api/telemetry/external-apis', {
        credentials: 'include',
        cache: 'no-store',
      })
      if (res.status === 401) {
        router.push('/login?next=/telemetry')
        return
      }
      if (!res.ok) {
        throw new Error('Could not load external API telemetry')
      }
      const json = await res.json()
      setData(json)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setPageLoading(false)
    }
  }, [router])

  useEffect(() => {
    if (loading) return
    if (!user) {
      router.push('/login?next=/telemetry')
      return
    }
    fetchTelemetry()
  }, [user?.id, user?.email, loading, fetchTelemetry, router])

  useEffect(() => {
    if (!autoRefresh || !user) return
    const timer = setInterval(fetchTelemetry, 10000)
    return () => clearInterval(timer)
  }, [autoRefresh, user, fetchTelemetry])

  if (loading || !user) return null

  const overview = data?.overview || {}
  const providers = data?.providers || []
  const recentCalls = data?.recent_calls || []

  const categories = ['All', 'LLM Inference', 'News & Regulatory Filings', 'Financial & Market Data', 'Embeddings & Vector DB']
  const filteredProviders = providers.filter(p => categoryFilter === 'All' || p.category === categoryFilter)
  const filteredCalls = recentCalls.filter(c => providerFilter === 'all' || c.provider === providerFilter)

  function statusBadge(status) {
    const map = {
      active: { label: 'Active', bg: 'var(--bull-tint)', color: 'var(--bull)' },
      ready: { label: 'Ready (0 calls)', bg: 'var(--brand-tint)', color: 'var(--brand-ink)' },
      rate_limited: { label: 'Rate Limited (429)', bg: 'var(--caution-tint)', color: 'var(--caution)' },
      degraded: { label: 'Degraded', bg: 'var(--bear-tint)', color: 'var(--bear)' },
      unconfigured: { label: 'Missing Key', bg: 'var(--surface-2)', color: 'var(--ink-3)' },
    }
    const s = map[status] || map.ready
    return (
      <span
        style={{
          padding: '3px 9px',
          borderRadius: 'var(--r-chip)',
          background: s.bg,
          color: s.color,
          fontSize: 'var(--fs-xs)',
          fontWeight: 700,
          whiteSpace: 'nowrap',
        }}
      >
        {s.label}
      </span>
    )
  }

  return (
    <main style={{ maxWidth: '1360px', margin: '0 auto', padding: '24px clamp(16px, 3vw, 36px) 64px' }}>
      {/* Header */}
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', marginBottom: '24px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
            <h1 style={{ margin: 0, fontSize: 'var(--fs-xl)', fontWeight: 700, color: 'var(--ink)' }}>
              📡 Outbound External API Monitor
            </h1>
            <span
              style={{
                padding: '3px 10px',
                borderRadius: 'var(--r-chip)',
                background: data?.mock_mode_enabled ? 'var(--caution-tint)' : 'var(--bull-tint)',
                color: data?.mock_mode_enabled ? 'var(--caution)' : 'var(--bull)',
                fontSize: 'var(--fs-xs)',
                fontWeight: 700,
              }}
            >
              {data?.mock_mode_enabled ? 'MOCK_MODE: ON' : 'LIVE_MODE: ON'}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--ink-2)' }}>
            Real-time telemetry, daily quota utilization, latency, and HTTP status codes for all 12 third-party APIs called by FinnWinn.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', cursor: 'pointer' }}>
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
            Auto-refresh (10s)
          </label>
          <button
            onClick={fetchTelemetry}
            style={{
              height: '36px',
              padding: '0 14px',
              borderRadius: 'var(--r-control)',
              border: '1px solid var(--rule)',
              background: 'var(--surface)',
              color: 'var(--ink)',
              fontSize: 'var(--fs-xs)',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            ↻ Refresh Now
          </button>
        </div>
      </div>

      {pageLoading ? (
        <div style={{ padding: '48px', textAlign: 'center', color: 'var(--ink-3)' }}>
          Loading outbound API telemetry...
        </div>
      ) : error ? (
        <div style={{ padding: '20px', borderRadius: 'var(--r-panel)', background: 'var(--bear-tint)', color: 'var(--bear)', fontWeight: 600 }}>
          {error}
        </div>
      ) : (
        <>
          {/* Top KPI Strip */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
              gap: '14px',
              marginBottom: '24px',
            }}
          >
            <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 'var(--r-panel)', padding: '16px' }}>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 600, textTransform: 'uppercase' }}>External APIs Tracked</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-figure)', color: 'var(--ink)', marginTop: '4px' }}>
                {overview.configured_providers} / {overview.total_providers_tracked}
              </div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>Configured &amp; ready</div>
            </div>

            <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 'var(--r-panel)', padding: '16px' }}>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 600, textTransform: 'uppercase' }}>Outbound Calls (24h)</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-figure)', color: 'var(--ink)', marginTop: '4px' }}>
                {(overview.total_calls_24h || 0).toLocaleString()}
              </div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                All-time: {(overview.total_calls_all_time || 0).toLocaleString()} calls
              </div>
            </div>

            <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 'var(--r-panel)', padding: '16px' }}>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 600, textTransform: 'uppercase' }}>Success Rate</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-figure)', color: overview.overall_success_rate_pct >= 95 ? 'var(--bull)' : 'var(--caution)', marginTop: '4px' }}>
                {overview.overall_success_rate_pct ?? 100}%
              </div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                429 Rate Limits: {overview.total_rate_limit_429 || 0} · Errors: {overview.total_errors_all_time || 0}
              </div>
            </div>

            <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 'var(--r-panel)', padding: '16px' }}>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 600, textTransform: 'uppercase' }}>Avg Outbound Latency</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-figure)', color: 'var(--ink)', marginTop: '4px' }}>
                {overview.overall_avg_latency_ms || 0} ms
              </div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>Weighted across all providers</div>
            </div>

            <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 'var(--r-panel)', padding: '16px' }}>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', fontWeight: 600, textTransform: 'uppercase' }}>LLM Tokens (24h)</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-figure)', color: 'var(--brand-ink)', marginTop: '4px' }}>
                {(overview.total_llm_tokens_24h || 0).toLocaleString()}
              </div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>Groq + Mistral completions</div>
            </div>
          </div>

          {/* Category Filter Pills */}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
            {categories.map(cat => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat)}
                style={{
                  padding: '6px 14px',
                  borderRadius: 'var(--r-chip)',
                  border: categoryFilter === cat ? '1px solid var(--brand)' : '1px solid var(--rule)',
                  background: categoryFilter === cat ? 'var(--brand-tint)' : 'var(--surface)',
                  color: categoryFilter === cat ? 'var(--brand-ink)' : 'var(--ink-2)',
                  fontSize: 'var(--fs-xs)',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* 12 External APIs Table */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 'var(--r-panel)', padding: '20px', marginBottom: '28px', overflowX: 'auto' }}>
            <h2 style={{ margin: '0 0 14px', fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)' }}>
              External API Providers &amp; Quota Utilization
            </h2>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--fs-sm)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--rule)', color: 'var(--ink-3)', fontSize: 'var(--fs-xs)', textTransform: 'uppercase', textAlign: 'left' }}>
                  <th style={{ padding: '10px 8px' }}>External API</th>
                  <th style={{ padding: '10px 8px' }}>Category</th>
                  <th style={{ padding: '10px 8px' }}>Status</th>
                  <th style={{ padding: '10px 8px' }}>Calls (24h / Total)</th>
                  <th style={{ padding: '10px 8px' }}>Quota Used (24h)</th>
                  <th style={{ padding: '10px 8px' }}>Success %</th>
                  <th style={{ padding: '10px 8px' }}>Avg / p95 Latency</th>
                  <th style={{ padding: '10px 8px' }}>429 / Errors</th>
                  <th style={{ padding: '10px 8px' }}>Where Used in App</th>
                </tr>
              </thead>
              <tbody>
                {filteredProviders.map(p => (
                  <tr key={p.provider} style={{ borderBottom: '1px solid var(--rule)' }}>
                    <td style={{ padding: '12px 8px' }}>
                      <div style={{ fontWeight: 700, color: 'var(--ink)' }}>{p.name}</div>
                      <div style={{ fontSize: '11px', color: 'var(--ink-3)', fontFamily: 'monospace' }}>{p.base_url}</div>
                    </td>
                    <td style={{ padding: '12px 8px', color: 'var(--ink-2)', fontSize: 'var(--fs-xs)' }}>{p.category}</td>
                    <td style={{ padding: '12px 8px' }}>{statusBadge(p.health_status)}</td>
                    <td style={{ padding: '12px 8px', fontFamily: 'var(--font-figure)', fontWeight: 700 }}>
                      {p.calls_24h.toLocaleString()} <span style={{ color: 'var(--ink-3)', fontWeight: 400 }}>/ {p.calls_total.toLocaleString()}</span>
                    </td>
                    <td style={{ padding: '12px 8px', minWidth: '150px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                        <span>{p.quota_used_pct}%</span>
                        <span style={{ color: 'var(--ink-3)' }}>{p.quota_limit.toLocaleString()} {p.quota_window}</span>
                      </div>
                      <div style={{ height: '6px', borderRadius: '4px', background: 'var(--surface-2)', overflow: 'hidden' }}>
                        <div
                          style={{
                            width: `${Math.min(100, Math.max(2, p.quota_used_pct))}%`,
                            height: '100%',
                            background: p.quota_used_pct > 80 ? 'var(--bear)' : p.quota_used_pct > 50 ? 'var(--caution)' : 'var(--brand)',
                          }}
                        />
                      </div>
                    </td>
                    <td style={{ padding: '12px 8px', fontFamily: 'var(--font-figure)', fontWeight: 700, color: p.success_rate_pct >= 95 ? 'var(--bull)' : 'var(--bear)' }}>
                      {p.success_rate_pct}%
                    </td>
                    <td style={{ padding: '12px 8px', fontFamily: 'var(--font-figure)' }}>
                      {p.avg_latency_ms} ms <span style={{ color: 'var(--ink-3)', fontSize: 'var(--fs-xs)' }}>(p95: {p.p95_latency_ms} ms)</span>
                    </td>
                    <td style={{ padding: '12px 8px', fontFamily: 'var(--font-figure)' }}>
                      <span style={{ color: p.rate_limit_429_count > 0 ? 'var(--caution)' : 'var(--ink-3)', fontWeight: 700 }}>
                        {p.rate_limit_429_count}
                      </span>{' '}
                      /{' '}
                      <span style={{ color: p.error_count > 0 ? 'var(--bear)' : 'var(--ink-3)', fontWeight: 700 }}>
                        {p.error_count}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px', fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', maxWidth: '240px' }}>
                      {p.used_by}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Live Outbound Request Stream */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 'var(--r-panel)', padding: '20px', overflowX: 'auto' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
              <h2 style={{ margin: 0, fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--ink)' }}>
                Recent Outbound API Calls ({filteredCalls.length})
              </h2>
              <select
                value={providerFilter}
                onChange={e => setProviderFilter(e.target.value)}
                style={{
                  padding: '6px 10px',
                  borderRadius: 'var(--r-control)',
                  border: '1px solid var(--rule)',
                  background: 'var(--surface-2)',
                  color: 'var(--ink)',
                  fontSize: 'var(--fs-xs)',
                }}
              >
                <option value="all">All Providers</option>
                {providers.map(p => (
                  <option key={p.provider} value={p.provider}>{p.name}</option>
                ))}
              </select>
            </div>

            {filteredCalls.length === 0 ? (
              <div style={{ padding: '28px', textAlign: 'center', color: 'var(--ink-3)', fontSize: 'var(--fs-sm)' }}>
                No outbound calls recorded for this filter yet. Run a search, footprint discovery, or live analysis to watch external API calls stream in real time.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--fs-xs)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--rule)', color: 'var(--ink-3)', textTransform: 'uppercase', textAlign: 'left' }}>
                    <th style={{ padding: '8px' }}>Time</th>
                    <th style={{ padding: '8px' }}>Provider</th>
                    <th style={{ padding: '8px' }}>Operation</th>
                    <th style={{ padding: '8px' }}>Ticker</th>
                    <th style={{ padding: '8px' }}>HTTP Status</th>
                    <th style={{ padding: '8px' }}>Latency</th>
                    <th style={{ padding: '8px' }}>Tokens</th>
                    <th style={{ padding: '8px' }}>Endpoint / Error</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCalls.map(c => (
                    <tr key={c.id} style={{ borderBottom: '1px solid var(--rule)' }}>
                      <td style={{ padding: '9px 8px', color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
                        {c.created_at ? new Date(c.created_at).toLocaleTimeString() : '—'}
                      </td>
                      <td style={{ padding: '9px 8px', fontWeight: 700, color: 'var(--ink)' }}>{c.provider_name || c.provider}</td>
                      <td style={{ padding: '9px 8px', color: 'var(--ink-2)', fontFamily: 'monospace' }}>{c.operation}</td>
                      <td style={{ padding: '9px 8px', fontWeight: 700, fontFamily: 'var(--font-figure)' }}>{c.ticker || '—'}</td>
                      <td style={{ padding: '9px 8px' }}>
                        <span
                          style={{
                            padding: '2px 7px',
                            borderRadius: 'var(--r-chip)',
                            background: c.success ? 'var(--bull-tint)' : 'var(--bear-tint)',
                            color: c.success ? 'var(--bull)' : 'var(--bear)',
                            fontWeight: 700,
                          }}
                        >
                          {c.status_code} {c.success ? 'OK' : 'ERR'}
                        </span>
                      </td>
                      <td style={{ padding: '9px 8px', fontFamily: 'var(--font-figure)', fontWeight: 600 }}>
                        {Number(c.duration_ms || 0).toFixed(1)} ms
                      </td>
                      <td style={{ padding: '9px 8px', fontFamily: 'var(--font-figure)' }}>
                        {c.tokens_used > 0 ? c.tokens_used.toLocaleString() : '—'}
                      </td>
                      <td style={{ padding: '9px 8px', color: c.error_message ? 'var(--bear)' : 'var(--ink-3)', fontFamily: 'monospace', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {c.error_message || c.endpoint}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </main>
  )
}

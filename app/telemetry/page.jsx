'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';

const CATEGORY_COLORS = {
  'LLM Inference': { bg: '#EEF2FF', text: '#3730A3', border: '#C7D2FE' },
  'News & Regulatory Filings': { bg: '#ECFDF5', text: '#065F46', border: '#A7F3D0' },
  'Financial & Market Data': { bg: '#EFF6FF', text: '#1E40AF', border: '#BFDBFE' },
  'Embeddings & Vector DB': { bg: '#FDF4FF', text: '#86198F', border: '#F5D0FE' },
};

const HEALTH_BADGES = {
  active: { label: 'ACTIVE', bg: '#DCFCE7', text: '#15803D' },
  ready: { label: 'READY', bg: '#E0F2FE', text: '#0369A1' },
  rate_limited: { label: '429 RATE LIMITED', bg: '#FEF3C7', text: '#B45309' },
  degraded: { label: 'DEGRADED', bg: '#FEE2E2', text: '#B91C1C' },
  unconfigured: { label: 'MISSING KEY', bg: '#F1F5F9', text: '#64748B' },
};

export default function DeveloperAdminMonitorPage() {
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('apis'); // 'apis' | 'langfuse' | 'prometheus'
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchTelemetry = useCallback(async () => {
    try {
      const res = await fetch('/api/telemetry/external-apis', {
        credentials: 'include',
        cache: 'no-store',
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.detail || `Error ${res.status}`);
      }
      setData(json);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load developer telemetry');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.is_admin) {
      fetchTelemetry();
    } else if (!authLoading) {
      setLoading(false);
    }
  }, [user, authLoading, fetchTelemetry]);

  useEffect(() => {
    if (!autoRefresh || !user?.is_admin) return;
    const id = setInterval(fetchTelemetry, 10000);
    return () => clearInterval(id);
  }, [autoRefresh, user, fetchTelemetry]);

  if (authLoading) {
    return (
      <main style={{ padding: '32px' }}>Checking Developer Admin session...</main>
    );
  }

  if (!user || !user.is_admin) {
    return (
      <main style={{ padding: '48px 32px', maxWidth: '680px', margin: '0 auto' }}>
        <div
          style={{
            background: '#FFFFFF',
            border: '1px solid #FECACA',
            borderRadius: '12px',
            padding: '28px',
          }}
        >
          <div
            style={{
              display: 'inline-block',
              background: '#FEE2E2',
              color: '#991B1B',
              fontSize: '11px',
              fontWeight: 700,
              padding: '4px 10px',
              borderRadius: '999px',
              marginBottom: '12px',
              letterSpacing: '0.06em',
            }}
          >
            403 RESTRICTED • DEVELOPER ADMIN ONLY
          </div>
          <h1 style={{ margin: '0 0 8px', fontSize: '22px', color: '#0F172A' }}>
            Developer Production Monitoring Console
          </h1>
          <p style={{ margin: '0 0 16px', color: '#475569', fontSize: '14px', lineHeight: 1.6 }}>
            This dashboard is restricted to MarketPulse developers and system administrators. Sign in with the
            Developer Admin account (<code>admin@marketpulse.ai</code>) to inspect live External API traffic,
            Prometheus time-series metrics, and Langfuse v4 LLM traces.
          </p>
          <a
            href="/login"
            style={{
              display: 'inline-block',
              background: '#0F172A',
              color: '#FFFFFF',
              padding: '10px 18px',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 600,
              textDecoration: 'none',
            }}
          >
            Sign in as Developer Admin →
          </a>
        </div>
      </main>
    );
  }

  const ov = data?.overview || {};
  const providers = data?.providers || [];
  const recentCalls = data?.recent_calls || [];
  const prom = data?.prometheus || {};
  const lf = data?.langfuse || {};
  const agentEvals = lf.agent_evaluations || {};
  const footprintEvals = lf.footprint_evaluations || {};

  const filteredProviders =
    categoryFilter === 'ALL'
      ? providers
      : providers.filter((p) => p.category === categoryFilter);

  return (
    <main style={{ padding: '28px 32px', maxWidth: '1420px', width: '100%', margin: '0 auto' }}>
          {/* Top Banner & Quick External Monitor Links */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: '16px',
              marginBottom: '22px',
              background: '#0F172A',
              color: '#F8FAFC',
              padding: '22px 24px',
              borderRadius: '12px',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                <span
                  style={{
                    background: '#38BDF8',
                    color: '#0F172A',
                    fontSize: '11px',
                    fontWeight: 800,
                    padding: '3px 9px',
                    borderRadius: '6px',
                    letterSpacing: '0.06em',
                  }}
                >
                  DEVELOPER ADMIN CONSOLE
                </span>
                <span
                  style={{
                    background: data?.mock_mode_enabled ? '#F59E0B' : '#22C55E',
                    color: '#0F172A',
                    fontSize: '11px',
                    fontWeight: 800,
                    padding: '3px 9px',
                    borderRadius: '6px',
                  }}
                >
                  {data?.mock_mode_enabled ? 'MOCK_MODE = TRUE' : 'LIVE PRODUCTION (MOCK_MODE = FALSE)'}
                </span>
                <span style={{ fontSize: '12px', color: '#94A3B8' }}>
                  Signed in as <strong>{user.email}</strong>
                </span>
              </div>
              <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 700 }}>
                Production Observability: External APIs • Prometheus • Langfuse v4
              </h1>
              <p style={{ margin: '6px 0 0', fontSize: '13px', color: '#94A3B8' }}>
                Real-time telemetry across all 12 third-party APIs, Prometheus counters/histograms, and Langfuse v4
                OpenTelemetry LLM traces & guardrail evaluations.
              </p>
            </div>

            {/* Direct Quick-Launch Buttons to Prometheus & Langfuse */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'center' }}>
              <a
                href={prom.production_metrics_url || 'https://finnwinn-api-258199278374.us-east4.run.app/metrics'}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  background: '#EA580C',
                  color: '#FFFFFF',
                  padding: '9px 14px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 700,
                  textDecoration: 'none',
                }}
              >
                🔥 Open Prometheus /metrics ↗
              </a>
              <a
                href={lf.dashboard_url || 'https://cloud.langfuse.com'}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  background: '#4F46E5',
                  color: '#FFFFFF',
                  padding: '9px 14px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 700,
                  textDecoration: 'none',
                }}
              >
                🔭 Open Langfuse Cloud ↗
              </a>
              <a
                href={prom.production_docs_url || 'https://finnwinn-api-258199278374.us-east4.run.app/docs'}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  background: '#1E293B',
                  border: '1px solid #334155',
                  color: '#E2E8F0',
                  padding: '9px 14px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
              >
                📄 FastAPI /docs ↗
              </a>
              <button
                onClick={fetchTelemetry}
                style={{
                  background: '#334155',
                  border: 'none',
                  color: '#F8FAFC',
                  padding: '9px 14px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                ↻ Refresh
              </button>
              <label style={{ fontSize: '12px', color: '#CBD5E1', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                Auto (10s)
              </label>
            </div>
          </div>

          {error && (
            <div
              style={{
                background: '#FEE2E2',
                border: '1px solid #FCA5A5',
                color: '#991B1B',
                padding: '12px 16px',
                borderRadius: '8px',
                marginBottom: '18px',
                fontSize: '13px',
              }}
            >
              {error}
            </div>
          )}

          {/* Top KPI Strip */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))',
              gap: '14px',
              marginBottom: '22px',
            }}
          >
            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '10px', padding: '16px' }}>
              <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 700, textTransform: 'uppercase' }}>
                External APIs Active
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#0F172A', marginTop: '4px' }}>
                {ov.configured_providers ?? 0} / {ov.total_providers_tracked ?? 12}
              </div>
              <div style={{ fontSize: '12px', color: '#16A34A', marginTop: '2px' }}>All API adapters instrumented</div>
            </div>

            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '10px', padding: '16px' }}>
              <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 700, textTransform: 'uppercase' }}>
                Outbound API Calls (24h)
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#0F172A', marginTop: '4px' }}>
                {(ov.total_calls_24h ?? 0).toLocaleString()}
              </div>
              <div style={{ fontSize: '12px', color: '#64748B', marginTop: '2px' }}>
                All-time: {(ov.total_calls_all_time ?? 0).toLocaleString()} calls
              </div>
            </div>

            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '10px', padding: '16px' }}>
              <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 700, textTransform: 'uppercase' }}>
                API Success Rate / Latency
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#15803D', marginTop: '4px' }}>
                {ov.overall_success_rate_pct ?? 100}%
              </div>
              <div style={{ fontSize: '12px', color: '#64748B', marginTop: '2px' }}>
                Avg latency: {ov.overall_avg_latency_ms ?? 0} ms • 429s: {ov.total_rate_limit_429 ?? 0}
              </div>
            </div>

            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '10px', padding: '16px' }}>
              <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 700, textTransform: 'uppercase' }}>
                LLM Tokens Processed (24h)
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#3730A3', marginTop: '4px' }}>
                {(ov.total_llm_tokens_24h ?? 0).toLocaleString()}
              </div>
              <div style={{ fontSize: '12px', color: '#64748B', marginTop: '2px' }}>
                Groq Qwen-27B + Mistral Failover
              </div>
            </div>

            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '10px', padding: '16px' }}>
              <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 700, textTransform: 'uppercase' }}>
                Langfuse Guardrail Pass Rate
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#0369A1', marginTop: '4px' }}>
                {agentEvals.guardrails_pass_pct ?? 100}%
              </div>
              <div style={{ fontSize: '12px', color: '#64748B', marginTop: '2px' }}>
                Avg Quality: {agentEvals.avg_overall_quality ?? '0.94'} • Hallucinations caught:{' '}
                {agentEvals.total_hallucinations_intercepted ?? 0}
              </div>
            </div>
          </div>

          {/* Monitor Switcher Tabs */}
          <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', borderBottom: '1px solid #E2E8F0', paddingBottom: '12px' }}>
            {[
              { id: 'apis', label: '📡 External API Traffic & Quotas (12 Providers)' },
              { id: 'langfuse', label: '🔭 Langfuse v4 Traces & Agent Guardrail Evals' },
              { id: 'prometheus', label: '🔥 Prometheus Metrics & Scrape Targets' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  background: activeTab === tab.id ? '#0F172A' : '#FFFFFF',
                  color: activeTab === tab.id ? '#FFFFFF' : '#334155',
                  border: '1px solid #CBD5E1',
                  padding: '10px 18px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* TAB 1: EXTERNAL API MONITOR */}
          {activeTab === 'apis' && (
            <>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
                {['ALL', 'LLM Inference', 'News & Regulatory Filings', 'Financial & Market Data', 'Embeddings & Vector DB'].map(
                  (cat) => (
                    <button
                      key={cat}
                      onClick={() => setCategoryFilter(cat)}
                      style={{
                        background: categoryFilter === cat ? '#1E293B' : '#F8FAFC',
                        color: categoryFilter === cat ? '#FFFFFF' : '#475569',
                        border: '1px solid #CBD5E1',
                        padding: '6px 12px',
                        borderRadius: '999px',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      {cat}
                    </button>
                  )
                )}
              </div>

              <div
                style={{
                  background: '#FFFFFF',
                  border: '1px solid #E2E8F0',
                  borderRadius: '12px',
                  overflow: 'hidden',
                  marginBottom: '28px',
                }}
              >
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ background: '#F8FAFC', borderBottom: '1px solid #E2E8F0', textAlign: 'left' }}>
                      <th style={{ padding: '12px 14px' }}>External API Provider</th>
                      <th style={{ padding: '12px 14px' }}>Category</th>
                      <th style={{ padding: '12px 14px' }}>Status</th>
                      <th style={{ padding: '12px 14px', textAlign: 'right' }}>24h Calls</th>
                      <th style={{ padding: '12px 14px', textAlign: 'right' }}>Total Calls</th>
                      <th style={{ padding: '12px 14px', textAlign: 'right' }}>Success Rate</th>
                      <th style={{ padding: '12px 14px', textAlign: 'right' }}>Avg / P95 Latency</th>
                      <th style={{ padding: '12px 14px', textAlign: 'right' }}>429s</th>
                      <th style={{ padding: '12px 14px' }}>24h Quota Utilization</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProviders.map((p) => {
                      const catStyle = CATEGORY_COLORS[p.category] || { bg: '#F1F5F9', text: '#334155', border: '#CBD5E1' };
                      const hb = HEALTH_BADGES[p.health_status] || HEALTH_BADGES.ready;
                      return (
                        <tr key={p.provider} style={{ borderBottom: '1px solid #F1F5F9' }}>
                          <td style={{ padding: '12px 14px' }}>
                            <div style={{ fontWeight: 700, color: '#0F172A' }}>{p.name}</div>
                            <div style={{ fontSize: '11px', color: '#64748B', fontFamily: 'monospace' }}>{p.base_url}</div>
                            <div style={{ fontSize: '11px', color: '#475569', marginTop: '2px' }}>{p.used_by}</div>
                          </td>
                          <td style={{ padding: '12px 14px' }}>
                            <span
                              style={{
                                background: catStyle.bg,
                                color: catStyle.text,
                                border: `1px solid ${catStyle.border}`,
                                padding: '3px 8px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                fontWeight: 600,
                              }}
                            >
                              {p.category}
                            </span>
                          </td>
                          <td style={{ padding: '12px 14px' }}>
                            <span
                              style={{
                                background: hb.bg,
                                color: hb.text,
                                padding: '3px 8px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                fontWeight: 700,
                              }}
                            >
                              {hb.label}
                            </span>
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                            {p.calls_24h}
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                            {p.calls_total}
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', color: p.success_rate_pct >= 95 ? '#15803D' : '#B45309' }}>
                            {p.success_rate_pct}%
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                            {p.avg_latency_ms} ms <span style={{ color: '#94A3B8' }}>/ {p.p95_latency_ms} ms</span>
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', color: p.rate_limit_429_count > 0 ? '#B91C1C' : '#64748B' }}>
                            {p.rate_limit_429_count}
                          </td>
                          <td style={{ padding: '12px 14px', minWidth: '170px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                              <span style={{ fontWeight: 700 }}>{p.quota_used_pct}%</span>
                              <span style={{ color: '#64748B' }}>{p.quota_window}</span>
                            </div>
                            <div style={{ height: '6px', background: '#E2E8F0', borderRadius: '999px', overflow: 'hidden' }}>
                              <div
                                style={{
                                  width: `${Math.min(100, p.quota_used_pct)}%`,
                                  height: '100%',
                                  background: p.quota_used_pct > 80 ? '#EF4444' : '#3B82F6',
                                }}
                              />
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Live Call Log Table */}
              <div
                style={{
                  background: '#FFFFFF',
                  border: '1px solid #E2E8F0',
                  borderRadius: '12px',
                  overflow: 'hidden',
                }}
              >
                <div style={{ padding: '14px 18px', borderBottom: '1px solid #E2E8F0', fontWeight: 700, fontSize: '14px' }}>
                  Recent Outbound External API Calls (Live Stream)
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                  <thead>
                    <tr style={{ background: '#F8FAFC', borderBottom: '1px solid #E2E8F0', textAlign: 'left' }}>
                      <th style={{ padding: '10px 14px' }}>Timestamp (UTC)</th>
                      <th style={{ padding: '10px 14px' }}>Provider</th>
                      <th style={{ padding: '10px 14px' }}>Operation / Endpoint</th>
                      <th style={{ padding: '10px 14px' }}>Ticker</th>
                      <th style={{ padding: '10px 14px' }}>HTTP Status</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Latency</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>LLM Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentCalls.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ padding: '20px', textAlign: 'center', color: '#64748B' }}>
                          No outbound API calls recorded yet. Run an analysis or search to see live traffic.
                        </td>
                      </tr>
                    ) : (
                      recentCalls.map((c) => (
                        <tr key={c.id} style={{ borderBottom: '1px solid #F1F5F9' }}>
                          <td style={{ padding: '10px 14px', fontFamily: 'monospace', color: '#475569' }}>
                            {String(c.created_at).slice(0, 19)}
                          </td>
                          <td style={{ padding: '10px 14px', fontWeight: 700 }}>{c.provider_name}</td>
                          <td style={{ padding: '10px 14px', fontFamily: 'monospace', color: '#334155' }}>
                            {c.operation}
                          </td>
                          <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontWeight: 700 }}>
                            {c.ticker || '—'}
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <span
                              style={{
                                background: c.success ? '#DCFCE7' : '#FEE2E2',
                                color: c.success ? '#15803D' : '#B91C1C',
                                padding: '2px 8px',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontFamily: 'monospace',
                              }}
                            >
                              {c.status_code}
                            </span>
                          </td>
                          <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                            {c.duration_ms} ms
                          </td>
                          <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                            {c.tokens_used ? c.tokens_used.toLocaleString() : '—'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* TAB 2: LANGFUSE v4 & AGENT EVALUATIONS MONITOR */}
          {activeTab === 'langfuse' && (
            <div style={{ display: 'grid', gap: '20px' }}>
              <div
                style={{
                  background: '#FFFFFF',
                  border: '1px solid #E2E8F0',
                  borderRadius: '12px',
                  padding: '20px 24px',
                  display: 'flex',
                  flexWrap: 'wrap',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '16px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span
                      style={{
                        background: lf.configured ? '#DCFCE7' : '#FEF3C7',
                        color: lf.configured ? '#15803D' : '#B45309',
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '11px',
                        fontWeight: 700,
                      }}
                    >
                      {lf.configured ? 'CONNECTED TO LANGFUSE CLOUD' : 'LOCAL TRACE MIRROR'}
                    </span>
                    <span style={{ fontSize: '12px', color: '#64748B', fontFamily: 'monospace' }}>
                      {lf.sdk_version} • env: {lf.environment} • key: {lf.public_key_prefix || 'N/A'}
                    </span>
                  </div>
                  <h2 style={{ margin: '8px 0 4px', fontSize: '18px' }}>
                    Langfuse v4 OpenTelemetry Tracing & Guardrail Evaluation Monitor
                  </h2>
                  <p style={{ margin: 0, fontSize: '13px', color: '#475569' }}>
                    Every specialist agent, MCP tool call, Link A/B/C grounding guardrail, and semantic quality
                    evaluator emits nested spans and trace scores to Langfuse Cloud.
                  </p>
                </div>

                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <a
                    href={lf.traces_url || 'https://cloud.langfuse.com'}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      background: '#4F46E5',
                      color: '#FFFFFF',
                      padding: '9px 14px',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: 700,
                      textDecoration: 'none',
                    }}
                  >
                    Open Langfuse Traces ↗
                  </a>
                  <a
                    href={lf.scores_url || 'https://cloud.langfuse.com'}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      background: '#0F172A',
                      color: '#FFFFFF',
                      padding: '9px 14px',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: 700,
                      textDecoration: 'none',
                    }}
                  >
                    Open Langfuse Scores & Evals ↗
                  </a>
                  <a
                    href={lf.datasets_url || 'https://cloud.langfuse.com'}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      background: '#F1F5F9',
                      color: '#0F172A',
                      border: '1px solid #CBD5E1',
                      padding: '9px 14px',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: 700,
                      textDecoration: 'none',
                    }}
                  >
                    Open Golden Datasets ↗
                  </a>
                </div>
              </div>

              {/* LLM Token & Latency Breakdown by Specialist Agent */}
              <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '12px', overflow: 'hidden' }}>
                <div style={{ padding: '14px 18px', borderBottom: '1px solid #E2E8F0', fontWeight: 700, fontSize: '14px' }}>
                  LLM Token Usage & Latency by Specialist Agent
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ background: '#F8FAFC', borderBottom: '1px solid #E2E8F0', textAlign: 'left' }}>
                      <th style={{ padding: '10px 14px' }}>Agent Name</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Total LLM Calls</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Prompt Tokens</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Completion Tokens</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Total Tokens</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Avg Generation Latency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(lf.llm_by_agent || []).map((ag) => (
                      <tr key={ag.agent_name} style={{ borderBottom: '1px solid #F1F5F9' }}>
                        <td style={{ padding: '10px 14px', fontWeight: 700, fontFamily: 'monospace' }}>{ag.agent_name}</td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>{ag.calls}</td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                          {ag.prompt_tokens.toLocaleString()}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                          {ag.completion_tokens.toLocaleString()}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                          {ag.total_tokens.toLocaleString()}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                          {ag.avg_latency_ms} ms
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Recent Guardrail & Evaluator Scores */}
              <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '12px', overflow: 'hidden' }}>
                <div style={{ padding: '14px 18px', borderBottom: '1px solid #E2E8F0', fontWeight: 700, fontSize: '14px' }}>
                  Recent Multi-Agent Faithfulness & Guardrail Evaluations (Mirrored to Langfuse)
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                  <thead>
                    <tr style={{ background: '#F8FAFC', borderBottom: '1px solid #E2E8F0', textAlign: 'left' }}>
                      <th style={{ padding: '10px 14px' }}>Timestamp</th>
                      <th style={{ padding: '10px 14px' }}>Agent</th>
                      <th style={{ padding: '10px 14px' }}>Ticker</th>
                      <th style={{ padding: '10px 14px' }}>Grade</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Overall Quality</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Faithfulness</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Consistency</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right' }}>Hallucinations Caught</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(lf.recent_evaluations || []).map((ev) => (
                      <tr key={ev.id} style={{ borderBottom: '1px solid #F1F5F9' }}>
                        <td style={{ padding: '10px 14px', fontFamily: 'monospace', color: '#475569' }}>
                          {String(ev.created_at).slice(0, 19)}
                        </td>
                        <td style={{ padding: '10px 14px', fontWeight: 700 }}>{ev.agent_name}</td>
                        <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontWeight: 700 }}>{ev.ticker}</td>
                        <td style={{ padding: '10px 14px' }}>
                          <span
                            style={{
                              background: ev.grade === 'A' ? '#DCFCE7' : ev.grade === 'B' ? '#E0F2FE' : '#FEF3C7',
                              color: ev.grade === 'A' ? '#15803D' : ev.grade === 'B' ? '#0369A1' : '#B45309',
                              padding: '2px 8px',
                              borderRadius: '6px',
                              fontWeight: 700,
                            }}
                          >
                            Grade {ev.grade}
                          </span>
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                          {ev.overall_quality_score}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                          {ev.faithfulness_score}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                          {ev.consistency_score}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace' }}>
                          {ev.hallucinations_detected}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 3: PROMETHEUS METRICS & SCRAPE TARGETS */}
          {activeTab === 'prometheus' && (
            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #E2E8F0',
                borderRadius: '12px',
                padding: '24px',
              }}
            >
              <h2 style={{ margin: '0 0 8px', fontSize: '18px' }}>
                Prometheus Time-Series Metrics & Developer Endpoints
              </h2>
              <p style={{ margin: '0 0 18px', fontSize: '13px', color: '#475569' }}>
                FastAPI exports real-time Prometheus counters, gauges, and latency histograms via{' '}
                <code>prometheus_fastapi_instrumentator</code> and <code>backend/agents/metrics.py</code>.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '14px', marginBottom: '22px' }}>
                <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: '10px', padding: '16px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: '#64748B', textTransform: 'uppercase' }}>
                    Production Prometheus Scrape Endpoint (Cloud Run)
                  </div>
                  <div style={{ fontFamily: 'monospace', fontSize: '13px', margin: '8px 0 12px', wordBreak: 'break-all' }}>
                    {prom.production_metrics_url}
                  </div>
                  <a
                    href={prom.production_metrics_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-block',
                      background: '#EA580C',
                      color: '#FFFFFF',
                      padding: '8px 14px',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: 700,
                      textDecoration: 'none',
                    }}
                  >
                    Open Production /metrics ↗
                  </a>
                </div>

                <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: '10px', padding: '16px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: '#64748B', textTransform: 'uppercase' }}>
                    Backend Direct HTML Telemetry View
                  </div>
                  <div style={{ fontFamily: 'monospace', fontSize: '13px', margin: '8px 0 12px', wordBreak: 'break-all' }}>
                    {prom.production_telemetry_html_url}
                  </div>
                  <a
                    href={prom.production_telemetry_html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-block',
                      background: '#0F172A',
                      color: '#FFFFFF',
                      padding: '8px 14px',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: 700,
                      textDecoration: 'none',
                    }}
                  >
                    Open Backend HTML Dashboard ↗
                  </a>
                </div>
              </div>

              <h3 style={{ fontSize: '14px', margin: '0 0 10px' }}>Exported Custom Prometheus Metrics</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '8px' }}>
                {(prom.exported_metrics || []).map((m) => (
                  <div
                    key={m}
                    style={{
                      background: '#0F172A',
                      color: '#38BDF8',
                      padding: '10px 14px',
                      borderRadius: '8px',
                      fontFamily: 'monospace',
                      fontSize: '12px',
                    }}
                  >
                    {m}
                  </div>
                ))}
              </div>
            </div>
          )}
    </main>
  );
}

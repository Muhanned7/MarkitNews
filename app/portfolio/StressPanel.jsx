'use client'

// RSK-009: stress scenarios (historical, market, factor, volatility), reverse stress, editable scenario library.
import { useCallback, useEffect, useState } from 'react'
import base from './portfolio.module.css'
import s from './limits.module.css'

const SECTORS = ['Technology', 'Healthcare', 'Financials', 'Consumer Discretionary', 'Energy', 'Industrials',
  'Communication Services', 'Consumer Staples', 'Utilities']
const KIND_LABEL = { historical: 'Historical replay', market: 'Market (beta)', factor: 'Factor', sector: 'Sector', volatility: 'Volatility', custom: 'Custom' }
const usd = (v) => (v === null || v === undefined) ? '—' : `${v < 0 ? '−' : v > 0 ? '+' : ''}$${Math.abs(Math.round(v)).toLocaleString()}`
const pct = (v, d = 2) => (v === null || v === undefined) ? '—' : `${v < 0 ? '−' : v > 0 ? '+' : ''}${Math.abs(v).toFixed(d)}%`

function PnlBar({ pctNav, maxAbs }) {
  if (pctNav === null || pctNav === undefined || !maxAbs) return null
  const w = Math.min(50, (Math.abs(pctNav) / maxAbs) * 50)
  const neg = pctNav < 0
  return (
    <div className={s.divTrack} aria-hidden="true">
      <div className={s.divMid} />
      <div className={`${s.divFill} ${neg ? s.fillRed : s.fillGreen}`} style={neg ? { right: '50%', width: `${w}%` } : { left: '50%', width: `${w}%` }} />
    </div>
  )
}

const emptyForm = () => ({ id: null, name: '', market: '', sectors: Object.fromEntries(SECTORS.map((x) => [x, ''])), tickers: '' })

function toForm(sc) {
  const f = emptyForm()
  f.id = sc.built_in ? null : sc.id
  f.name = sc.built_in ? `${sc.name} (copy)` : sc.name
  const sh = sc.shocks || {}
  if (sh.market !== undefined) f.market = String(+(sh.market * 100).toFixed(4))
  for (const [k, v] of Object.entries(sh.sectors || {})) f.sectors[k] = String(+(v * 100).toFixed(4))
  f.tickers = Object.entries(sh.tickers || {}).map(([k, v]) => `${k}:${+(v * 100).toFixed(4)}`).join(', ')
  return f
}

function fromForm(f) {
  const shocks = {}
  if (f.market !== '') shocks.market = parseFloat(f.market) / 100
  const sec = Object.fromEntries(Object.entries(f.sectors).filter(([, v]) => v !== '').map(([k, v]) => [k, parseFloat(v) / 100]))
  if (Object.keys(sec).length) shocks.sectors = sec
  const tk = {}
  for (const part of f.tickers.split(',').map((x) => x.trim()).filter(Boolean)) {
    const [t, v] = part.split(':').map((x) => x.trim())
    if (t && v !== undefined) tk[t.toUpperCase()] = parseFloat(v) / 100
  }
  if (Object.keys(tk).length) shocks.tickers = tk
  return shocks
}

export default function StressPanel({ portfolioId, refreshKey }) {
  const [target, setTarget] = useState('10')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(null)
  const [form, setForm] = useState(null)
  const [formErr, setFormErr] = useState(null)

  const load = useCallback(async () => {
    if (!portfolioId) return
    setErr(null)
    try {
      const t = parseFloat(target)
      const q = t > 0 && t < 100 ? `?target_loss_pct=${t}` : ''
      const r = await fetch(`/api/portfolios/${portfolioId}/stress-test${q}`)
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'Failed')
      setData(j)
    } catch (e) { setErr(e.message) }
  }, [portfolioId, target])

  useEffect(() => {
    const t = setTimeout(load, 400) // debounce the reverse-stress target input
    return () => clearTimeout(t)
  }, [load, refreshKey])

  async function saveScenario(e) {
    e.preventDefault()
    setFormErr(null)
    if (!form.name.trim()) { setFormErr('Name is required'); return }
    const shocks = fromForm(form)
    if (!Object.keys(shocks).length) { setFormErr('Enter at least one shock'); return }
    const body = { name: form.name.trim(), kind: 'custom', shocks, portfolio_id: portfolioId }
    const r = await fetch(form.id ? `/api/stress-scenarios/${form.id}` : '/api/stress-scenarios', {
      method: form.id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    })
    const j = await r.json().catch(() => ({}))
    if (!r.ok) { setFormErr(j.detail || 'Save failed'); return }
    setForm(null)
    load()
  }

  async function remove(id) {
    const r = await fetch(`/api/stress-scenarios/${id}`, { method: 'DELETE' })
    if (r.ok) load()
  }

  if (err) return <div className={base.panel}><div className={s.section} role="alert">{err}</div></div>
  if (!data) return <div className={base.panel}><div className={s.section}>Running stress tests…</div></div>

  const rev = data.reverse_stress
  const maxAbs = Math.max(...data.scenarios.filter((r) => r.pnl_pct !== undefined).map((r) => Math.abs(r.pnl_pct)), 1)
  const groups = ['historical', 'market', 'factor', 'sector', 'volatility', 'custom']

  return (
    <div className={base.panel}>
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>Stress tests</h2>
          <span className={s.sectionMeta} title={data._provenance.method}>{data._provenance.basis} ⓘ</span>
        </div>
        <p className={s.caveat} role="note">Mock data: historical replays use approximate S&amp;P sector moves for each window, and factor shocks use an illustrative sector-sensitivity table.</p>

        {rev && (
          <div className={s.statGrid} style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
            <div>
              <span className={s.statLabel}>Reverse stress · S&amp;P move to lose</span>
              <label className={s.statSub} htmlFor="target-loss" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <input id="target-loss" className={s.editInput} style={{ width: 64 }} type="number" step="any" min="0.1" max="99" value={target}
                  onChange={(e) => setTarget(e.target.value)} />% of NAV
              </label>
              <span className={s.statValue}>{rev.spx_move_pct === null ? 'n/a' : pct(rev.spx_move_pct)}</span>
              <span className={s.statSub}>
                {rev.spx_move_pct === null ? rev.note : `Full revaluation: ${usd(rev.confirm_full_revaluation_pnl_usd)} (target ${usd(-rev.target_loss_usd)})${rev.reachable === false ? ' · beyond −100%, not reachable' : ''}`}
              </span>
            </div>
            {rev.drawdown_limit && (
              <div>
                <span className={s.statLabel}>Breach drawdown hard limit ({rev.drawdown_limit.hard_pct}%)</span>
                <span className={s.statValue}>{pct(rev.drawdown_limit.spx_move_to_breach_pct)} S&amp;P</span>
                <span className={s.statSub}>Extra loss {rev.drawdown_limit.extra_loss_to_breach_pct.toFixed(2)}% from today (current DD {rev.drawdown_limit.current_drawdown_pct.toFixed(2)}%)</span>
              </div>
            )}
            {rev.most_plausible && (
              <div>
                <span className={s.statLabel}>Most plausible shock for that loss</span>
                <span className={s.statSub} style={{ color: 'var(--ink)' }}>
                  {rev.most_plausible.per_ticker.map((t) => `${t.ticker} ${pct(t.shock_pct, 1)}`).join(' · ')}
                </span>
                <span className={s.statSub} title={rev.most_plausible.method}>{rev.most_plausible.mahalanobis_daily_sigmas}σ joint move (Mahalanobis) ⓘ</span>
              </div>
            )}
          </div>
        )}

        <div className={s.sectionHead}>
          <h3 className={s.sectionTitle}>Scenario results</h3>
          <button className={s.smallBtn} onClick={() => setForm(form ? null : emptyForm())} aria-expanded={!!form}>
            {form ? 'Close editor' : '+ Custom scenario'}
          </button>
        </div>

        {form && (
          <form className={s.scenarioForm} onSubmit={saveScenario}>
            <label className={s.editField}>Name
              <input className={`${s.editInput} ${s.editInputWide}`} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className={s.editField}>Market move % (via beta)
              <input className={s.editInput} type="number" step="any" value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value })} />
            </label>
            <fieldset className={s.sectorGrid}>
              <legend className={s.statLabel}>Sector moves % (override beta for that sector)</legend>
              {SECTORS.map((x) => (
                <label key={x} className={s.editField}>{x}
                  <input className={s.editInput} type="number" step="any" value={form.sectors[x]}
                    onChange={(e) => setForm({ ...form, sectors: { ...form.sectors, [x]: e.target.value } })} />
                </label>
              ))}
            </fieldset>
            <label className={s.editField}>Ticker overrides (e.g. NVDA:-30, AAPL:-10)
              <input className={`${s.editInput} ${s.editInputWide}`} value={form.tickers} onChange={(e) => setForm({ ...form, tickers: e.target.value })} />
            </label>
            <div className={s.editForm}>
              <button type="submit" className={s.smallBtn}>{form.id ? 'Save changes' : 'Save scenario'}</button>
              <button type="button" className={s.smallBtn} onClick={() => setForm(null)}>Cancel</button>
              {formErr && <span className={s.formError} role="alert">{formErr}</span>}
            </div>
          </form>
        )}
      </div>

      <div className={base.tableWrapper}>
        <table className={base.table}>
          <thead>
            <tr><th>Scenario</th><th>P&amp;L</th><th>% NAV</th><th style={{ minWidth: 140 }}>Impact</th><th>Worst position</th><th>Limits breached after</th><th>Action</th></tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const rows = data.scenarios.filter((r) => (r.kind || 'custom') === g)
              if (!rows.length) return null
              return [
                <tr key={`h-${g}`}><td colSpan={7} className={s.groupRow}>{KIND_LABEL[g]}</td></tr>,
                ...rows.map((r) => {
                  const hard = (r.breaches_after || []).filter((b) => b.status === 'hard_breach')
                  const isOpen = open === r.id
                  return [
                    <tr key={r.id}>
                      <td style={{ whiteSpace: 'normal', minWidth: 200 }}>
                        <button className={s.linkish} onClick={() => setOpen(isOpen ? null : r.id)} aria-expanded={isOpen}>
                          {isOpen ? '▾' : '▸'} {r.name}
                        </button>
                      </td>
                      {r.kind === 'volatility' ? (
                        <>
                          <td colSpan={3} className={base.subText} style={{ whiteSpace: 'normal' }}>
                            VaR99 1d {r.base_var99_pct.toFixed(2)}% → <strong>{r.stressed_var99_pct.toFixed(2)}%</strong> · no direct P&amp;L (no options)
                          </td>
                          <td>—</td><td>—</td>
                        </>
                      ) : (
                        <>
                          <td className={`${base.figure} ${r.pnl_usd < 0 ? base.negChange : base.posChange}`}>{usd(r.pnl_usd)}</td>
                          <td className={base.figure}>{pct(r.pnl_pct)}</td>
                          <td><PnlBar pctNav={r.pnl_pct} maxAbs={maxAbs} /></td>
                          <td className={base.subText}>{r.worst_positions?.[0] ? `${r.worst_positions[0].ticker} ${usd(r.worst_positions[0].pnl_usd)}` : '—'}</td>
                          <td style={{ whiteSpace: 'normal' }}>
                            {hard.length ? <span className={`${s.status} ${s.statusRed}`}>✕ {hard.length} hard</span> : <span className={`${s.status} ${s.statusGreen}`}>✓ none hard</span>}
                          </td>
                        </>
                      )}
                      <td>
                        <button className={s.smallBtn} onClick={() => setForm(toForm(r))}>{r.built_in ? 'Copy' : 'Edit'}</button>
                        {!r.built_in && <button className={s.smallBtn} style={{ marginLeft: 4 }} onClick={() => remove(r.id)}>Delete</button>}
                      </td>
                    </tr>,
                    isOpen && r.kind !== 'volatility' ? (
                      <tr key={`d-${r.id}`} className={s.editRow}>
                        <td colSpan={7}>
                          <div className={s.detailGrid}>
                            <div>
                              <span className={s.statLabel}>Position P&amp;L</span>
                              <table className={s.diffTable}>
                                <thead><tr><th>Ticker</th><th>Shock</th><th>P&amp;L</th></tr></thead>
                                <tbody>{r.positions.map((p) => <tr key={p.ticker}><td>{p.ticker}</td><td className={s.diffNum}>{pct(p.shock_pct, 1)}</td><td className={s.diffNum}>{usd(p.pnl_usd)}</td></tr>)}</tbody>
                              </table>
                              {r.beta_approx_pnl_usd !== undefined && (
                                <p className={s.hint}>Market-only (β {r.portfolio_beta}) estimate: {usd(r.beta_approx_pnl_usd)}</p>
                              )}
                            </div>
                            <div>
                              <span className={s.statLabel}>Limits after the shock</span>
                              {(r.breaches_after || []).length === 0 ? <p className={s.hint}>All limits within.</p> : (
                                <ul className={s.plainList}>
                                  {r.breaches_after.map((b) => (
                                    <li key={b.metric}>
                                      <span className={`${s.status} ${b.status === 'hard_breach' ? s.statusRed : s.statusAmber}`}>{b.status === 'hard_breach' ? '✕ Hard' : '! Soft'}</span>{' '}
                                      {b.label} {b.unit === 'beta' ? Number(b.value).toFixed(2) : `${Number(b.value).toFixed(2)}%`}{b.scopes.length ? ` (${b.scopes.join(', ')})` : ''}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null
                  ]
                })
              ]
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

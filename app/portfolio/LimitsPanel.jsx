'use client'

// RSK-002 Limits tab + RSK-003 breach log. All numbers come from /api/portfolios/{id}/limits and /breaches.
import { useState, useEffect, useCallback } from 'react'
import base from './portfolio.module.css'
import s from './limits.module.css'
import { notifyRiskChanged } from '../components/riskFetch'

const STATUS_TEXT = {
  hard_breach: 'Hard breach',
  soft_breach: 'Soft breach',
  ok: 'Within limit',
  na: 'Not available',
  inactive: 'Inactive'
}

function statusClass(status) {
  if (status === 'hard_breach') return s.statusRed
  if (status === 'soft_breach') return s.statusAmber
  if (status === 'ok') return s.statusGreen
  return s.statusNa
}

function StatusPill({ status }) {
  const icon = status === 'hard_breach' ? '✕' : status === 'soft_breach' ? '!' : status === 'ok' ? '✓' : '–'
  return (
    <span className={`${s.status} ${statusClass(status)}`}>
      <span aria-hidden="true">{icon}</span>{STATUS_TEXT[status] || status}
    </span>
  )
}

function fmt(v, metric) {
  if (v === null || v === undefined) return '—'
  return metric === 'portfolio_beta' ? Number(v).toFixed(2) : `${Number(v).toFixed(2)}%`
}

function limitText(l, which) {
  const hi = which === 'soft' ? l.soft_limit : l.hard_limit
  const lo = which === 'soft' ? l.soft_limit_low : l.hard_limit_low
  if (hi === null || hi === undefined) return '—'
  if (l.direction === 'band') return `${lo} – ${hi}`
  if (l.direction === 'min') return `≥ ${hi}`
  return `${hi}`
}

function UtilBar({ row }) {
  if (row.utilisation_pct === null || row.utilisation_pct === undefined) {
    return <span className={base.subText}>{row.note || '—'}</span>
  }
  const pct = row.utilisation_pct
  const width = Math.min(pct, 150) / 150 * 100
  const fill = row.band === 'red' ? s.fillRed : row.band === 'amber' ? s.fillAmber : s.fillGreen
  return (
    <div className={s.utilCell}>
      <div
        className={s.utilTrack}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={150}
        aria-valuenow={Math.min(pct, 150)}
        aria-label={`${row.label} utilisation ${pct}% of hard limit`}
      >
        <div className={`${s.utilFill} ${fill}`} style={{ width: `${width}%` }} />
        <div className={s.utilMarker} style={{ left: `${100 / 150 * 100}%` }} title="Hard limit (100%)" />
      </div>
      <div className={s.utilText}>{pct.toFixed(1)}% of hard</div>
    </div>
  )
}

function EditLimitRow({ row, portfolioId, onSaved, onCancel }) {
  const [soft, setSoft] = useState(row.soft_limit ?? '')
  const [hard, setHard] = useState(row.hard_limit ?? '')
  const [softLow, setSoftLow] = useState(row.soft_limit_low ?? '')
  const [hardLow, setHardLow] = useState(row.hard_limit_low ?? '')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState(null)
  const [saving, setSaving] = useState(false)

  async function save(e) {
    e.preventDefault()
    setErr(null)
    if (!reason.trim()) { setErr('A reason is required for the audit log.'); return }
    setSaving(true)
    const body = { soft_limit: parseFloat(soft), hard_limit: parseFloat(hard), reason: reason.trim() }
    if (row.direction === 'band') {
      body.soft_limit_low = parseFloat(softLow)
      body.hard_limit_low = parseFloat(hardLow)
    }
    try {
      const res = await fetch(`/api/portfolios/${portfolioId}/limits/${row.metric}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to save limit')
      onSaved(data)
    } catch (e2) {
      setErr(e2.message)
    } finally {
      setSaving(false)
    }
  }

  const id = `lim-${row.metric}`
  return (
    <tr className={s.editRow}>
      <td colSpan={7}>
        <form className={s.editForm} onSubmit={save}>
          {row.direction === 'band' && (
            <>
              <label className={s.editField} htmlFor={`${id}-hl`}>Hard low
                <input id={`${id}-hl`} className={s.editInput} type="number" step="any" value={hardLow} onChange={(e) => setHardLow(e.target.value)} />
              </label>
              <label className={s.editField} htmlFor={`${id}-sl`}>Soft low
                <input id={`${id}-sl`} className={s.editInput} type="number" step="any" value={softLow} onChange={(e) => setSoftLow(e.target.value)} />
              </label>
            </>
          )}
          <label className={s.editField} htmlFor={`${id}-s`}>{row.direction === 'band' ? 'Soft high' : 'Soft'}
            <input id={`${id}-s`} className={s.editInput} type="number" step="any" value={soft} onChange={(e) => setSoft(e.target.value)} />
          </label>
          <label className={s.editField} htmlFor={`${id}-h`}>{row.direction === 'band' ? 'Hard high' : 'Hard'}
            <input id={`${id}-h`} className={s.editInput} type="number" step="any" value={hard} onChange={(e) => setHard(e.target.value)} />
          </label>
          <label className={s.editField} htmlFor={`${id}-r`}>Reason (audit-logged)
            <input id={`${id}-r`} className={`${s.editInput} ${s.editInputWide}`} type="text" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Committee approved widening" />
          </label>
          <button type="submit" className={s.smallBtn} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          <button type="button" className={s.smallBtn} onClick={onCancel}>Cancel</button>
          {err && <div className={s.formError} role="alert">{err}</div>}
        </form>
      </td>
    </tr>
  )
}

function AckForm({ breach, portfolioId, onDone }) {
  const [comment, setComment] = useState('')
  const [open, setOpen] = useState(false)
  const [err, setErr] = useState(null)
  if (breach.status !== 'open') return null
  if (!open) return <button className={s.smallBtn} onClick={() => setOpen(true)}>Acknowledge</button>
  async function submit(e) {
    e.preventDefault()
    if (!comment.trim()) { setErr('Comment required'); return }
    const res = await fetch(`/api/portfolios/${portfolioId}/breaches/${breach.id}/acknowledge`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ comment: comment.trim() })
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) { setErr(data.detail || 'Failed'); return }
    onDone()
  }
  return (
    <form className={s.editForm} onSubmit={submit}>
      <input aria-label="Acknowledgement comment" className={`${s.editInput} ${s.editInputWide}`} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Action plan / owner note" />
      <button type="submit" className={s.smallBtn}>Save</button>
      {err && <span className={s.formError}>{err}</span>}
    </form>
  )
}

export default function LimitsPanel({ portfolioId, limitsData, onLimitsChanged }) {
  const [editing, setEditing] = useState(null)
  const [breaches, setBreaches] = useState([])
  const [showResolved, setShowResolved] = useState(false)

  const loadBreaches = useCallback(async () => {
    if (!portfolioId) return
    try {
      const res = await fetch(`/api/portfolios/${portfolioId}/breaches`)
      if (res.ok) setBreaches(await res.json())
    } catch (e) { console.error(e) }
  }, [portfolioId])

  useEffect(() => { loadBreaches() }, [loadBreaches, limitsData])

  if (!limitsData) {
    return <div className={base.panel}><div className={s.section}>Loading limits…</div></div>
  }
  const rows = limitsData.limits || []
  const sm = limitsData.summary || {}
  const visible = breaches.filter((b) => showResolved || b.status !== 'resolved')

  return (
    <div className={base.panel}>
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>Risk limits</h2>
          <span className={s.sectionMeta}>Utilisation = current ÷ hard limit · 252d Ledoit-Wolf risk · mock data</span>
        </div>
        <div className={s.summaryRow}>
          <span className={`${s.status} ${s.statusRed}`}>✕ {sm.hard_breaches ?? 0} hard</span>
          <span className={`${s.status} ${s.statusAmber}`}>! {sm.soft_breaches ?? 0} soft</span>
          <span className={`${s.status} ${s.statusGreen}`}>✓ {sm.ok ?? 0} within</span>
          {sm.not_available > 0 && <span className={`${s.status} ${s.statusNa}`}>– {sm.not_available} n/a</span>}
        </div>
      </div>
      <div className={base.tableWrapper}>
        <table className={base.table}>
          <thead>
            <tr>
              <th>Limit</th>
              <th>Current</th>
              <th>Soft</th>
              <th>Hard</th>
              <th>Utilisation</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <FragmentRow key={r.metric} r={r} editing={editing} setEditing={setEditing} portfolioId={portfolioId}
                onSaved={(d) => { setEditing(null); onLimitsChanged(d) }} />
            ))}
          </tbody>
        </table>
      </div>

      <hr className={s.divider} />
      <div className={s.section}>
        <div className={s.sectionHead}>
          <h2 className={s.sectionTitle}>Breach log</h2>
          <label className={s.sectionMeta}>
            <input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} /> Show resolved
          </label>
        </div>
      </div>
      <div className={base.tableWrapper}>
        <table className={base.table}>
          <thead>
            <tr>
              <th>Limit / scope</th>
              <th>Severity</th>
              <th>Value vs limit</th>
              <th>First seen</th>
              <th>Last seen</th>
              <th>Status</th>
              <th>Owner / comment</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--ink-3)', padding: '24px' }}>No breaches recorded.</td></tr>
            ) : visible.map((b) => (
              <tr key={b.id}>
                <td><strong>{b.label}</strong>{b.scope ? <span className={base.subText}> · {b.scope}</span> : null}</td>
                <td><StatusPill status={b.severity === 'hard' ? 'hard_breach' : 'soft_breach'} /></td>
                <td className={base.figure}>{fmt(b.value, b.metric)} vs {fmt(b.limit_value, b.metric)}</td>
                <td className={base.subText}>{new Date(b.first_seen).toLocaleString()}</td>
                <td className={base.subText}>{new Date(b.last_seen).toLocaleString()}</td>
                <td>{b.status}{b.resolved_at ? <div className={base.subText}>{new Date(b.resolved_at).toLocaleString()}</div> : null}</td>
                <td style={{ whiteSpace: 'normal' }}>
                  {b.owner && <div className={base.subText}>{b.owner}</div>}
                  {b.comment && <div>{b.comment}</div>}
                  <AckForm breach={b} portfolioId={portfolioId} onDone={() => { loadBreaches(); notifyRiskChanged() }} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FragmentRow({ r, editing, setEditing, portfolioId, onSaved }) {
  return (
    <>
      <tr>
        <td style={{ whiteSpace: 'normal', minWidth: 190 }}>
          <strong>{r.label}</strong>
          <div className={base.subText}>{r.unit}</div>
          {r.breaching && r.breaching.length > 0 && (
            <div className={s.entities}>
              {r.breaching.map((b) => (
                <span key={b.scope} className={`${s.entityChip} ${b.status === 'hard_breach' ? s.entityHard : s.entitySoft}`}>
                  {b.scope} {Number(b.value).toFixed(1)}%{b.status === 'hard_breach' ? ' · hard' : ' · soft'}
                </span>
              ))}
            </div>
          )}
        </td>
        <td className={base.figure}>{fmt(r.value, r.metric)}</td>
        <td className={base.figure}>{limitText(r, 'soft')}</td>
        <td className={base.figure}>{limitText(r, 'hard')}</td>
        <td><UtilBar row={r} /></td>
        <td><StatusPill status={r.status} /></td>
        <td>
          <button className={s.smallBtn} onClick={() => setEditing(editing === r.metric ? null : r.metric)} aria-expanded={editing === r.metric}>
            Edit
          </button>
        </td>
      </tr>
      {editing === r.metric && (
        <EditLimitRow row={r} portfolioId={portfolioId} onSaved={onSaved} onCancel={() => setEditing(null)} />
      )}
    </>
  )
}

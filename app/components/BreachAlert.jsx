'use client'

// RSK-008: navbar breach pill + off-canvas breach drawer.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { riskHeaders, RISK_CHANGED_EVENT, notifyRiskChanged } from './riskFetch'
import s from './BreachAlert.module.css'

const POLL_MS = 60000

function age(sec) {
  if (sec === null || sec === undefined) return ''
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m`
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
  return `${Math.floor(sec / 86400)}d ${Math.floor((sec % 86400) / 3600)}h`
}

function fmt(v, metric) {
  if (v === null || v === undefined) return '—'
  return metric === 'portfolio_beta' ? Number(v).toFixed(2) : `${Number(v).toFixed(2)}%`
}

function AckInline({ b, onDone }) {
  const [open, setOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [err, setErr] = useState(null)
  if (b.status !== 'open') return <span className={s.acked}>Acknowledged{b.owner ? ` by ${b.owner}` : ''}</span>
  if (!open) return <button className={s.btn} onClick={() => setOpen(true)}>Acknowledge</button>
  async function submit(e) {
    e.preventDefault()
    if (!comment.trim()) { setErr('Comment required'); return }
    const res = await fetch(`/api/portfolios/${b.portfolio_id}/breaches/${b.id}/acknowledge`, {
      method: 'POST', headers: riskHeaders(), body: JSON.stringify({ comment: comment.trim() })
    })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) { setErr(j.detail || 'Failed'); return }
    onDone()
  }
  return (
    <form className={s.ackForm} onSubmit={submit}>
      <input aria-label="Acknowledgement comment" className={s.input} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Action plan / owner note" autoFocus />
      <button type="submit" className={s.btn}>Save</button>
      {err && <span className={s.err}>{err}</span>}
    </form>
  )
}

export default function BreachAlert() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(false)
  const closeRef = useRef(null)
  const pillRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/risk/breaches/summary', { headers: riskHeaders(), cache: 'no-store' })
      if (res.ok) setData(await res.json())
    } catch (e) { /* backend offline: keep last state */ }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, POLL_MS)
    window.addEventListener(RISK_CHANGED_EVENT, load)
    return () => { clearInterval(t); window.removeEventListener(RISK_CHANGED_EVENT, load) }
  }, [load])

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); pillRef.current?.focus() }
  }, [open])

  if (!data || data.level === 'clear') return null

  let pillClass = s.pillNeutral
  let text = `${data.acknowledged} acknowledged`
  if (data.level === 'hard') { pillClass = s.pillHard; text = `${data.open_hard} Hard Breach${data.open_hard === 1 ? '' : 'es'}` }
  else if (data.level === 'soft') { pillClass = s.pillSoft; text = `${data.open_soft} Soft Breach${data.open_soft === 1 ? '' : 'es'}` }

  function simulate(b) {
    setOpen(false)
    const t = b.suggestion?.trades?.[0]
    if (t) {
      router.push(`/portfolio?pid=${b.portfolio_id}&trade=sell&ticker=${t.ticker}&qty=${-t.qty}&price=${t.price}`)
    } else {
      router.push(`/portfolio?pid=${b.portfolio_id}&tab=limits`)
    }
  }

  return (
    <>
      <button
        ref={pillRef}
        className={`${s.pill} ${pillClass}`}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label={`${text}. Open breach review`}
      >
        <span aria-hidden="true">⚠️</span> {text}
      </button>

      {open && (
        <div className={s.overlay} onClick={() => setOpen(false)}>
          <aside className={s.drawer} role="dialog" aria-modal="true" aria-labelledby="breach-drawer-title" onClick={(e) => e.stopPropagation()}>
            <div className={s.head}>
              <h2 id="breach-drawer-title" className={s.title}>Active limit breaches</h2>
              <button ref={closeRef} className={s.close} onClick={() => setOpen(false)} aria-label="Close breach review">✕</button>
            </div>
            <p className={s.meta}>
              {data.open_hard} hard · {data.open_soft} soft open · {data.acknowledged} acknowledged · as of {new Date(data.as_of).toLocaleTimeString()}
            </p>
            <ul className={s.list}>
              {data.breaches.map((b) => (
                <li key={b.id} className={`${s.item} ${b.severity === 'hard' ? s.itemHard : s.itemSoft}`}>
                  <div className={s.row1}>
                    <span className={`${s.sev} ${b.severity === 'hard' ? s.sevHard : s.sevSoft}`}>
                      {b.severity === 'hard' ? '✕ Hard' : '! Soft'}
                    </span>
                    <strong>{b.label}</strong>{b.scope ? <span className={s.scope}> · {b.scope}</span> : null}
                  </div>
                  <div className={s.row2}>
                    <span className={s.num}>{fmt(b.value, b.metric)}</span> vs limit <span className={s.num}>{fmt(b.limit_value, b.metric)}</span>
                    <span className={s.dot}>·</span> open {age(b.age_seconds)}
                    <span className={s.dot}>·</span> {b.portfolio_name}
                  </div>
                  {b.suggestion && <div className={s.suggest}>Suggested: {b.suggestion.text}</div>}
                  <div className={s.actions}>
                    <AckInline b={b} onDone={() => { load(); notifyRiskChanged() }} />
                    <button className={s.btn} onClick={() => simulate(b)}>
                      {b.suggestion ? 'Simulate de-risking' : 'Review in Limits'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      )}
    </>
  )
}

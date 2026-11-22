// Shared fetch helper for risk components: forwards the user's bearer token when present.
export function riskHeaders() {
  const h = { 'Content-Type': 'application/json' }
  try {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
    if (token) h['Authorization'] = `Bearer ${token}`
  } catch (e) { /* storage unavailable */ }
  return h
}

// Fired after trades / limit edits / acknowledgements so the navbar badge refreshes immediately.
export const RISK_CHANGED_EVENT = 'finnwinn:risk-changed'
export function notifyRiskChanged() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(RISK_CHANGED_EVENT))
}

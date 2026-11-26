// Shared fetch helper for risk components: relies on httpOnly cookie auth (PROD-014).
export function riskHeaders() {
  return { 'Content-Type': 'application/json' }
}

// Fired after trades / limit edits / acknowledgements so the navbar badge refreshes immediately.
export const RISK_CHANGED_EVENT = 'finnwinn:risk-changed'
export function notifyRiskChanged() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(RISK_CHANGED_EVENT))
}

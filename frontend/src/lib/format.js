export const RISK_COLORS = {
  SAFE: '#34d399',
  SUSPICIOUS: '#fbbf24',
  FLAGGED: '#f43f5e',
}

export const ENTITY_COLORS = {
  Device: '#38bdf8',
  IPAddress: '#a78bfa',
  CreditCard: '#94a3b8',
  Customer: '#2dd4bf',
}

export const STATUS_STYLES = {
  SAFE: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/25',
  SUSPICIOUS: 'bg-amber-500/15 text-amber-300 border border-amber-500/25',
  FLAGGED: 'bg-rose-500/15 text-rose-300 border border-rose-500/25',
}

export function money(value, { compact = false } = {}) {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 0,
  }).format(value)
}

export function count(value) {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('en-US').format(value)
}

export function shortDate(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function nodeColor(node) {
  if (node.kind === 'Account') return RISK_COLORS[node.status] || '#64748b'
  return ENTITY_COLORS[node.kind] || '#64748b'
}

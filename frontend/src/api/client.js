/**
 * Single entry point for every call to the SentinelGraph API.
 *
 * The backend answers failures with a consistent envelope --
 * `{ error: { code, message, detail } }` -- so this module normalises every
 * outcome (HTTP error, network failure, timeout) into one `ApiError` shape.
 * Components then only ever handle three states: loading, error, data.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

const REQUEST_TIMEOUT_MS = 30_000

export class ApiError extends Error {
  constructor(message, { code = 'unknown', detail = null, status = 0 } = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.detail = detail
    this.status = status
  }

  /** True when the problem is the database rather than the request. */
  get isDatabaseIssue() {
    return this.status === 503 || this.code.startsWith('database_')
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  // Let a caller-supplied signal (React cleanup) also abort this request.
  if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true })

  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
  } catch (cause) {
    clearTimeout(timer)
    if (cause.name === 'AbortError') {
      throw new ApiError('The request took too long and was cancelled.', {
        code: 'client_timeout',
      })
    }
    throw new ApiError('Could not reach the SentinelGraph API.', {
      code: 'network_error',
      detail: `Is the backend running at ${BASE_URL}?`,
    })
  } finally {
    clearTimeout(timer)
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const error = payload?.error ?? {}
    throw new ApiError(error.message || `Request failed (${response.status}).`, {
      code: error.code || `http_${response.status}`,
      detail: error.detail ?? null,
      status: response.status,
    })
  }

  return payload
}

const qs = (params) => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const string = search.toString()
  return string ? `?${string}` : ''
}

export const api = {
  health: (signal) => request('/health', { signal }),
  stats: (signal) => request('/stats', { signal }),

  graph: ({ focus, depth = 2, limit = 250 } = {}, signal) =>
    request(`/graph${qs({ focus, depth, limit })}`, { signal }),

  search: (q, signal) => request(`/search${qs({ q, limit: 12 })}`, { signal }),

  account: (accId, signal) => request(`/accounts/${encodeURIComponent(accId)}`, { signal }),
  transactions: (accId, signal) =>
    request(`/accounts/${encodeURIComponent(accId)}/transactions${qs({ limit: 50 })}`, { signal }),
  connections: (accId, signal) =>
    request(`/accounts/${encodeURIComponent(accId)}/connections`, { signal }),
  explain: (accId, signal) => request(`/accounts/${encodeURIComponent(accId)}/explain`, { signal }),

  detectRings: ({ accId } = {}, signal) => request(`/detect/rings${qs({ acc_id: accId })}`, { signal }),
  detectSharedInfrastructure: (signal) => request('/detect/shared-infrastructure', { signal }),
  detectMules: ({ minSenders = 8, payoutRatio = 0.85 } = {}, signal) =>
    request(`/detect/mules${qs({ min_senders: minSenders, payout_ratio: payoutRatio })}`, { signal }),

  tracePath: (source, destination, signal) =>
    request('/trace-path', { method: 'POST', body: { source, destination }, signal }),

  riskScore: (accId, signal) =>
    request('/detect/risk-score', { method: 'POST', body: { acc_id: accId }, signal }),
}

export { BASE_URL }

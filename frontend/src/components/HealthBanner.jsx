import { useEffect } from 'react'
import { api, BASE_URL } from '../api/client'
import { useAsync } from '../hooks/useAsync'

const DOT = {
  ok: 'bg-emerald-400',
  degraded: 'bg-amber-400',
  down: 'bg-rose-400',
  loading: 'bg-slate-500',
}

/**
 * Polls /health so the app degrades visibly rather than silently. When CognoDB
 * is unreachable the whole UI stays usable and says so, instead of every panel
 * failing separately with its own mysterious error.
 */
export function HealthIndicator({ onChange }) {
  const state = useAsync((signal) => api.health(signal), [])

  // Longer than the health request's own timeout (75s). `run()` aborts whatever
  // is in flight, so a shorter interval would cancel a probe that is patiently
  // waiting for a sleeping host to wake -- and the check would never resolve.
  useEffect(() => {
    const timer = setInterval(() => state.run(), 90_000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    onChange?.(state)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status, state.data?.database])

  const status = state.status === 'loading' ? 'loading' : state.status === 'error' ? 'down' : state.data?.status
  const label =
    state.status === 'loading'
      ? 'Checking…'
      : state.status === 'error'
        ? 'API offline'
        : state.data?.database === 'connected'
          ? `CognoDB · ${state.data.latency_ms ?? '—'} ms`
          : 'Database offline'

  return (
    <div
      className="flex items-center gap-2 text-2xs font-medium text-slate-400 px-2.5 py-1.5 rounded-lg bg-ink-850 border border-ink-800"
      title={state.data?.message || state.error?.message || ''}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${DOT[status] || DOT.loading}`} aria-hidden="true" />
      <span className="tabular">{label}</span>
    </div>
  )
}

export function HealthBanner({ health }) {
  const offline = health?.status === 'error' || (health?.data && health.data.status !== 'ok')
  if (!offline) return null

  const message =
    health.status === 'error'
      ? health.error?.message || 'The SentinelGraph API is not responding.'
      : health.data?.message

  return (
    <div
      role="alert"
      className="animate-fade-up bg-rose-500/10 border-b border-rose-500/25 px-4 sm:px-6 py-2.5
                 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
    >
      <span className="chip bg-rose-500/20 text-rose-300">Offline</span>
      <span className="text-slate-300">{message}</span>
      <span className="text-slate-500">
        API: <span className="font-mono">{BASE_URL}</span>
      </span>
    </div>
  )
}

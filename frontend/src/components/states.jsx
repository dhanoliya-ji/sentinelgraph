/**
 * The three states every async view in this app must be able to render.
 * Centralised so that "loading" looks the same everywhere and no panel can
 * quietly forget to handle an empty result or a failure.
 */

export function Skeleton({ className = '', style }) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />
}

export function SkeletonLines({ lines = 3, className = '' }) {
  return (
    <div className={`space-y-2 ${className}`} role="status" aria-label="Loading">
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} className="h-3.5" style={{ width: `${100 - index * 12}%` }} />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function EmptyState({ icon = '○', title, message, action = null }) {
  return (
    <div className="flex flex-col items-center justify-center text-center px-6 py-10 gap-2">
      <div
        className="w-10 h-10 rounded-full border border-ink-700 grid place-items-center text-slate-500 text-lg"
        aria-hidden="true"
      >
        {icon}
      </div>
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {message && <p className="text-xs text-slate-500 max-w-xs leading-relaxed">{message}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry, compact = false }) {
  const isDbIssue = error?.isDatabaseIssue

  return (
    <div
      role="alert"
      className={`flex flex-col items-center justify-center text-center gap-2 ${
        compact ? 'px-4 py-6' : 'px-6 py-10'
      }`}
    >
      <div
        className="w-10 h-10 rounded-full bg-rose-500/10 border border-rose-500/30 grid place-items-center text-rose-400"
        aria-hidden="true"
      >
        !
      </div>
      <p className="text-sm font-medium text-slate-200">
        {isDbIssue ? 'The database is not reachable' : 'Something went wrong'}
      </p>
      <p className="text-xs text-slate-400 max-w-sm leading-relaxed">
        {error?.message || 'An unexpected error occurred.'}
      </p>
      {error?.detail && <p className="text-2xs text-slate-500 max-w-sm leading-relaxed">{error.detail}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-ghost mt-2">
          Try again
        </button>
      )}
    </div>
  )
}

/**
 * Renders the right thing for an async result without every caller repeating
 * the same four-branch conditional.
 */
export function AsyncBoundary({ state, onRetry, loading, empty, isEmpty, children }) {
  if (state.status === 'loading') return loading ?? <SkeletonLines className="p-4" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={onRetry} />
  if (state.status === 'idle') return empty ?? null
  if (isEmpty?.(state.data)) return empty ?? <EmptyState title="Nothing to show" />
  return children(state.data)
}

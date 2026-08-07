import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Runs an async function and exposes the four states every view in this app
 * has to render: idle, loading, error, data. Aborts in-flight work on unmount
 * or when the dependencies change, so a fast click-through never lands stale
 * results in the sidebar.
 */
export function useAsync(fn, deps = [], { immediate = true } = {}) {
  const [state, setState] = useState({ status: immediate ? 'loading' : 'idle', data: null, error: null })
  const controllerRef = useRef(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
    }
  }, [])

  const run = useCallback(
    async (...args) => {
      controllerRef.current?.abort()
      const controller = new AbortController()
      controllerRef.current = controller

      setState((prev) => ({ ...prev, status: 'loading', error: null }))
      try {
        const data = await fn(controller.signal, ...args)
        if (!mountedRef.current || controller.signal.aborted) return null
        setState({ status: 'success', data, error: null })
        return data
      } catch (error) {
        if (!mountedRef.current || controller.signal.aborted) return null
        setState({ status: 'error', data: null, error })
        return null
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    deps,
  )

  useEffect(() => {
    if (immediate) run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { ...state, run, reset: () => setState({ status: 'idle', data: null, error: null }) }
}

/** Debounces a fast-changing value -- used by the search box. */
export function useDebounced(value, delay = 250) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

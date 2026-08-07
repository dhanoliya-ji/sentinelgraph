import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useDebounced } from '../hooks/useAsync'
import { STATUS_STYLES } from '../lib/format'

const KIND_LABEL = {
  Account: 'Account',
  Device: 'Device',
  IPAddress: 'IP address',
  Customer: 'Customer',
}

const KIND_DOT = {
  Account: 'bg-slate-400',
  Device: 'bg-sky-400',
  IPAddress: 'bg-violet-400',
  Customer: 'bg-teal-400',
}

/**
 * Searches accounts, owner names, devices and IP addresses in one box.
 * Debounced so a five-character query is one request, not five.
 */
export function SearchBar({ onSelect }) {
  const [term, setTerm] = useState('')
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState([])
  const [status, setStatus] = useState('idle')
  const [highlight, setHighlight] = useState(0)
  const boxRef = useRef(null)
  const debounced = useDebounced(term, 250)

  useEffect(() => {
    if (!debounced.trim()) {
      setResults([])
      setStatus('idle')
      return
    }
    const controller = new AbortController()
    setStatus('loading')
    api
      .search(debounced.trim(), controller.signal)
      .then((data) => {
        setResults(data?.results ?? [])
        setStatus('success')
        setHighlight(0)
      })
      .catch((error) => {
        if (error.name === 'AbortError') return
        setResults([])
        setStatus('error')
      })
    return () => controller.abort()
  }, [debounced])

  useEffect(() => {
    const close = (event) => {
      if (boxRef.current && !boxRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const choose = (hit) => {
    onSelect(hit)
    setOpen(false)
    setTerm('')
  }

  const onKeyDown = (event) => {
    if (!open || !results.length) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlight((index) => (index + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight((index) => (index - 1 + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(results[highlight])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={boxRef} className="relative w-full sm:w-80">
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm" aria-hidden="true">
          ⌕
        </span>
        <input
          type="search"
          className="input pl-8"
          placeholder="Search account, name, device or IP…"
          value={term}
          onChange={(event) => {
            setTerm(event.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          aria-label="Search the graph"
          aria-expanded={open}
          role="combobox"
          aria-controls="search-results"
        />
      </div>

      {open && term.trim() && (
        <div
          id="search-results"
          role="listbox"
          className="absolute z-30 mt-1.5 w-full panel shadow-2xl shadow-black/50 overflow-hidden animate-fade-up"
        >
          {status === 'loading' && (
            <p className="px-3 py-3 text-xs text-slate-500">Searching…</p>
          )}

          {status === 'error' && (
            <p className="px-3 py-3 text-xs text-rose-300">Search is unavailable right now.</p>
          )}

          {status === 'success' && results.length === 0 && (
            <p className="px-3 py-3 text-xs text-slate-500">
              No accounts, devices or addresses match “{term.trim()}”.
            </p>
          )}

          {results.map((hit, index) => (
            <button
              key={`${hit.kind}-${hit.id}`}
              type="button"
              role="option"
              aria-selected={index === highlight}
              onMouseEnter={() => setHighlight(index)}
              onClick={() => choose(hit)}
              className={`w-full text-left px-3 py-2 flex items-center gap-2.5 transition-colors ${
                index === highlight ? 'bg-ink-800' : 'hover:bg-ink-850'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full shrink-0 ${KIND_DOT[hit.kind] || 'bg-slate-500'}`}
                aria-hidden="true"
              />
              <span className="font-mono text-xs text-slate-200 truncate">{hit.id}</span>
              <span className="text-xs text-slate-500 truncate flex-1">{hit.label}</span>
              {hit.kind === 'Account' && hit.status ? (
                <span className={`chip ${STATUS_STYLES[hit.status] || ''}`}>{hit.status}</span>
              ) : (
                <span className="text-2xs text-slate-600 uppercase tracking-wide">
                  {KIND_LABEL[hit.kind] || hit.kind}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

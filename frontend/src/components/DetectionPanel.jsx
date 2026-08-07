import { useState } from 'react'
import { api } from '../api/client'
import { money } from '../lib/format'
import { EmptyState, ErrorState, SkeletonLines } from './states'

const DETECTORS = [
  {
    key: 'rings',
    label: 'Circular money flows',
    hint: 'Money that leaves an account and comes back to it',
    run: (signal) => api.detectRings({}, signal),
  },
  {
    key: 'shared',
    label: 'Shared devices & addresses',
    hint: 'Different names signing in from the same phone and IP',
    run: (signal) => api.detectSharedInfrastructure(signal),
  },
  {
    key: 'mules',
    label: 'Mule account funnels',
    hint: 'Many small deposits in, one big payment out',
    run: (signal) => api.detectMules({}, signal),
  },
]

function Collapsible({ label, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="text-2xs text-slate-500 hover:text-slate-300 transition-colors"
        aria-expanded={open}
      >
        {open ? '▾' : '▸'} {label}
      </button>
      {open && <div className="mt-1.5 animate-fade-up">{children}</div>}
    </div>
  )
}

function ResultCard({ result, detector, onFocus }) {
  const accounts =
    detector === 'rings'
      ? [...new Set(result.account_chain || [])]
      : detector === 'shared'
        ? (result.accounts || []).map((account) => account.acc_id)
        : detector === 'mules'
          ? [result.mule_account, result.destination]
          : result.chain || []

  return (
    <li className="px-3.5 py-3 border-t border-ink-800 first:border-t-0">
      <p className="text-xs text-slate-300 leading-relaxed">{result.summary}</p>

      <div className="flex flex-wrap gap-1.5 mt-2">
        {accounts.slice(0, 8).map((accId) => (
          <button
            key={accId}
            type="button"
            onClick={() => onFocus(accId)}
            className="font-mono text-2xs px-1.5 py-0.5 rounded bg-ink-800 border border-ink-700
                       text-slate-300 hover:border-sky-500/50 hover:text-sky-300 transition-colors"
          >
            {accId}
          </button>
        ))}
        {accounts.length > 8 && (
          <span className="text-2xs text-slate-600 self-center">+{accounts.length - 8} more</span>
        )}
      </div>

      {detector === 'rings' && (
        <p className="text-2xs text-slate-500 mt-1.5 tabular">
          {result.hops} hops · {money(result.total_cycled_amount)} cycled
        </p>
      )}
      {detector === 'mules' && (
        <p className="text-2xs text-slate-500 mt-1.5 tabular">
          {money(result.inbound_total)} in · {money(result.outbound_total)} out ·{' '}
          {(result.payout_ratio * 100).toFixed(0)}% forwarded
        </p>
      )}
      {detector === 'shared' && (
        <p className="text-2xs text-slate-500 mt-1.5 font-mono">
          {result.device_id} · {result.ip_address}
          {result.is_vpn && <span className="text-amber-400/80"> · VPN</span>}
        </p>
      )}
    </li>
  )
}

function DetectorSection({ detector, onFocus }) {
  const [state, setState] = useState({ status: 'idle', data: null, error: null })

  const run = async () => {
    const controller = new AbortController()
    setState({ status: 'loading', data: null, error: null })
    try {
      const data = await detector.run(controller.signal)
      setState({ status: 'success', data, error: null })
    } catch (error) {
      setState({ status: 'error', data: null, error })
    }
  }

  return (
    <div className="border-b border-ink-800 last:border-b-0">
      <div className="px-3.5 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-200">{detector.label}</p>
            <p className="text-2xs text-slate-500 mt-0.5 leading-relaxed">{detector.hint}</p>
          </div>
          <button
            type="button"
            onClick={run}
            disabled={state.status === 'loading'}
            className="btn-primary !py-1.5 !px-2.5 text-2xs shrink-0"
          >
            {state.status === 'loading' ? 'Running…' : state.status === 'idle' ? 'Run' : 'Re-run'}
          </button>
        </div>

        {state.status === 'success' && (
          <p className="text-xs text-slate-400 mt-2.5 leading-relaxed animate-fade-up">
            {state.data.headline}
          </p>
        )}
      </div>

      {state.status === 'loading' && <SkeletonLines lines={3} className="px-3.5 pb-3" />}

      {state.status === 'error' && (
        <ErrorState error={state.error} onRetry={run} compact />
      )}

      {state.status === 'success' && state.data.count > 0 && (
        <>
          <ul className="bg-ink-950/40">
            {state.data.results.map((result, index) => (
              <ResultCard
                key={index}
                result={result}
                detector={detector.key}
                onFocus={onFocus}
              />
            ))}
          </ul>
          <div className="px-3.5 pb-3">
            <Collapsible label="Show the Cypher this ran">
              <pre className="text-2xs font-mono text-slate-400 bg-ink-950 border border-ink-800 rounded-lg p-2.5 overflow-x-auto leading-relaxed">
                {state.data.cypher}
              </pre>
            </Collapsible>
          </div>
        </>
      )}

      {state.status === 'success' && state.data.count === 0 && (
        <div className="pb-2">
          <EmptyState
            icon="✓"
            title="Nothing found"
            message="No matches for this pattern in the current data."
          />
        </div>
      )}
    </div>
  )
}

function TracePathSection({ onFocus }) {
  const [source, setSource] = useState('ACC_1301')
  const [destination, setDestination] = useState('ACC_1101')
  const [state, setState] = useState({ status: 'idle', data: null, error: null })

  const submit = async (event) => {
    event.preventDefault()
    if (!source.trim() || !destination.trim()) return
    const controller = new AbortController()
    setState({ status: 'loading', data: null, error: null })
    try {
      const data = await api.tracePath(source.trim(), destination.trim(), controller.signal)
      setState({ status: 'success', data, error: null })
    } catch (error) {
      setState({ status: 'error', data: null, error })
    }
  }

  return (
    <div className="px-3.5 py-3 border-b border-ink-800">
      <p className="text-sm font-medium text-slate-200">Trace money between two accounts</p>
      <p className="text-2xs text-slate-500 mt-0.5 leading-relaxed">
        Finds the shortest chain of transfers, up to six steps
      </p>

      <form onSubmit={submit} className="flex flex-col sm:flex-row gap-2 mt-2.5">
        <input
          className="input font-mono text-xs"
          value={source}
          onChange={(event) => setSource(event.target.value)}
          placeholder="From, e.g. ACC_1301"
          aria-label="Source account"
        />
        <input
          className="input font-mono text-xs"
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
          placeholder="To, e.g. ACC_1101"
          aria-label="Destination account"
        />
        <button
          type="submit"
          disabled={state.status === 'loading'}
          className="btn-primary !py-1.5 text-2xs shrink-0"
        >
          {state.status === 'loading' ? 'Tracing…' : 'Trace'}
        </button>
      </form>

      {state.status === 'loading' && <SkeletonLines lines={2} className="mt-3" />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={() => submit(new Event('submit'))} compact />}

      {state.status === 'success' && (
        <div className="mt-3 animate-fade-up">
          <p className="text-xs text-slate-400 leading-relaxed">{state.data.headline}</p>
          {state.data.count > 0 && (
            <ul className="mt-2 space-y-2">
              {state.data.results.map((path, index) => (
                <li key={index} className="bg-ink-950/50 border border-ink-800 rounded-lg p-2.5">
                  <div className="flex flex-wrap items-center gap-1">
                    {path.chain.map((accId, position) => (
                      <span key={`${accId}-${position}`} className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => onFocus(accId)}
                          className="font-mono text-2xs px-1.5 py-0.5 rounded bg-ink-800 border border-ink-700
                                     text-slate-300 hover:border-sky-500/50 hover:text-sky-300 transition-colors"
                        >
                          {accId}
                        </button>
                        {position < path.chain.length - 1 && (
                          <span className="text-2xs text-slate-600 tabular">
                            →{money(path.amounts[position], { compact: true })}→
                          </span>
                        )}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export function DetectionPanel({ onFocus }) {
  return (
    <section className="panel overflow-hidden">
      <div className="panel-header">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">Fraud detection</h2>
          <p className="text-2xs text-slate-500">
            Each button runs one Cypher query against the live graph
          </p>
        </div>
      </div>

      <TracePathSection onFocus={onFocus} />
      {DETECTORS.map((detector) => (
        <DetectorSection key={detector.key} detector={detector} onFocus={onFocus} />
      ))}
    </section>
  )
}

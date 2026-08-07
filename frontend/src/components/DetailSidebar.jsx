import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { STATUS_STYLES, money, shortDate } from '../lib/format'
import { EmptyState, ErrorState, SkeletonLines } from './states'

function RiskMeter({ score, status }) {
  const value = Math.max(0, Math.min(100, score ?? 0))
  const color =
    status === 'FLAGGED' ? 'bg-rose-500' : status === 'SUSPICIOUS' ? 'bg-amber-400' : 'bg-emerald-400'

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-2xs uppercase tracking-wider text-slate-500 font-semibold">Risk score</span>
        <span className="text-lg font-semibold tabular text-slate-100">
          {value}
          <span className="text-xs text-slate-500">/100</span>
        </span>
      </div>
      <div
        className="h-1.5 rounded-full bg-ink-800 overflow-hidden"
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Risk score"
      >
        <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

function Field({ label, value, mono = false }) {
  return (
    <div className="min-w-0">
      <dt className="text-2xs uppercase tracking-wider text-slate-500 font-semibold">{label}</dt>
      <dd className={`text-xs text-slate-200 truncate mt-0.5 ${mono ? 'font-mono' : ''}`}>
        {value ?? '—'}
      </dd>
    </div>
  )
}

const TABS = [
  { key: 'why', label: 'Why flagged' },
  { key: 'transactions', label: 'Transactions' },
  { key: 'connections', label: 'Connections' },
]

function WhyTab({ accId, onHighlight, onRecompute }) {
  const state = useAsync((signal) => api.explain(accId, signal), [accId])
  const [recomputing, setRecomputing] = useState(false)

  const recompute = async () => {
    setRecomputing(true)
    try {
      await api.riskScore(accId)
      await state.run()
      onRecompute?.()
    } finally {
      setRecomputing(false)
    }
  }

  if (state.status === 'loading') return <SkeletonLines lines={4} className="p-3.5" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={state.run} compact />

  const data = state.data

  return (
    <div className="p-3.5 space-y-3">
      <p className="text-xs text-slate-300 leading-relaxed">{data.headline}</p>

      {data.reasons.length === 0 ? (
        <EmptyState
          icon="✓"
          title="No risk signals"
          message="Nothing in this account's connections matches a known fraud pattern."
        />
      ) : (
        <ul className="space-y-2">
          {data.reasons.map((reason, index) => (
            <li key={index}>
              <button
                type="button"
                onClick={() => onHighlight(reason.highlight)}
                className="w-full text-left bg-ink-950/50 border border-ink-800 rounded-lg p-2.5
                           hover:border-sky-500/40 transition-colors group"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-medium text-slate-200">{reason.title}</p>
                  {reason.points != null && (
                    <span className="chip bg-ink-800 text-slate-400 shrink-0 tabular">
                      +{reason.points}
                    </span>
                  )}
                </div>
                <p className="text-2xs text-slate-400 mt-1 leading-relaxed">{reason.text}</p>
                <p className="text-2xs text-sky-400/0 group-hover:text-sky-400/80 transition-colors mt-1">
                  Click to highlight in the graph
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={recompute}
        disabled={recomputing}
        className="btn-ghost w-full text-2xs"
      >
        {recomputing ? 'Recalculating…' : 'Recalculate risk score from the graph'}
      </button>
    </div>
  )
}

function TransactionsTab({ accId, onFocus }) {
  const state = useAsync((signal) => api.transactions(accId, signal), [accId])

  if (state.status === 'loading') return <SkeletonLines lines={5} className="p-3.5" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={state.run} compact />
  if (!state.data?.length)
    return (
      <EmptyState
        icon="○"
        title="No transactions"
        message="This account has never sent or received a transfer in the dataset."
      />
    )

  return (
    <ul className="divide-y divide-ink-800">
      {state.data.map((txn) => (
        <li key={txn.txn_id} className="px-3.5 py-2.5 flex items-center gap-3">
          <span
            className={`chip shrink-0 ${
              txn.direction === 'in'
                ? 'bg-emerald-500/10 text-emerald-400'
                : 'bg-slate-500/10 text-slate-400'
            }`}
          >
            {txn.direction === 'in' ? 'In' : 'Out'}
          </span>
          <div className="min-w-0 flex-1">
            <button
              type="button"
              onClick={() => onFocus(txn.counterparty_id)}
              className="font-mono text-xs text-slate-300 hover:text-sky-300 transition-colors truncate block"
            >
              {txn.counterparty_id}
            </button>
            <p className="text-2xs text-slate-500 truncate">
              {txn.counterparty_name} · {shortDate(txn.timestamp)}
            </p>
          </div>
          <span
            className={`text-xs font-medium tabular shrink-0 ${
              txn.direction === 'in' ? 'text-emerald-400' : 'text-slate-300'
            }`}
          >
            {txn.direction === 'in' ? '+' : '−'}
            {money(txn.amount)}
          </span>
        </li>
      ))}
    </ul>
  )
}

function ConnectionsTab({ accId, onHighlight }) {
  const state = useAsync((signal) => api.connections(accId, signal), [accId])

  if (state.status === 'loading') return <SkeletonLines lines={4} className="p-3.5" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={state.run} compact />

  const groups = [
    { label: 'Customer', items: state.data.customers, primary: 'name', secondary: 'country' },
    { label: 'Devices', items: state.data.devices, primary: 'id', secondary: 'os' },
    { label: 'IP addresses', items: state.data.ips, primary: 'id', secondary: 'country' },
    { label: 'Cards', items: state.data.cards, primary: 'id', secondary: 'issuer' },
  ].filter((group) => group.items?.length)

  if (!groups.length)
    return (
      <EmptyState
        icon="○"
        title="No connected entities"
        message="This account has no device, address or card on record."
      />
    )

  return (
    <div className="p-3.5 space-y-3">
      {groups.map((group) => (
        <div key={group.label}>
          <p className="text-2xs uppercase tracking-wider text-slate-500 font-semibold mb-1.5">
            {group.label}
          </p>
          <ul className="space-y-1">
            {group.items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onHighlight([accId, item.id])}
                  className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg
                             bg-ink-950/50 border border-ink-800 hover:border-sky-500/40 transition-colors"
                >
                  <span className="font-mono text-2xs text-slate-300 truncate">
                    {item[group.primary] || item.id}
                  </span>
                  <span className="text-2xs text-slate-500 truncate shrink-0">
                    {item.is_vpn ? 'VPN · ' : ''}
                    {item[group.secondary]}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

export function DetailSidebar({ selected, onFocus, onHighlight, onDataChanged }) {
  const [tab, setTab] = useState('why')
  const isAccount = selected?.kind === 'Account'
  const accId = isAccount ? selected.id : null

  const account = useAsync(
    (signal) => (accId ? api.account(accId, signal) : Promise.resolve(null)),
    [accId],
    { immediate: Boolean(accId) },
  )

  useEffect(() => setTab('why'), [accId])

  if (!selected) {
    return (
      <aside className="panel h-full flex items-center justify-center">
        <EmptyState
          icon="◎"
          title="Nothing selected"
          message="Click any node in the graph, or search for an account, to see who it is connected to and why it was scored the way it was."
        />
      </aside>
    )
  }

  if (!isAccount) {
    return (
      <aside className="panel h-full overflow-y-auto">
        <div className="panel-header">
          <div className="min-w-0">
            <p className="text-2xs uppercase tracking-wider text-slate-500 font-semibold">
              {selected.kind === 'IPAddress' ? 'IP address' : selected.kind}
            </p>
            <h2 className="text-sm font-mono text-slate-100 truncate">{selected.id}</h2>
          </div>
        </div>
        <div className="p-3.5">
          <p className="text-xs text-slate-400 leading-relaxed">
            {selected.label}. Click a connected account to investigate it, or use “Shared devices &
            addresses” in the detection panel to see every account that touches this one.
          </p>
          <button
            type="button"
            onClick={() => onHighlight([selected.id])}
            className="btn-ghost w-full text-2xs mt-3"
          >
            Highlight in the graph
          </button>
        </div>
      </aside>
    )
  }

  return (
    <aside className="panel h-full flex flex-col overflow-hidden">
      <div className="panel-header !items-start">
        <div className="min-w-0">
          <p className="text-2xs uppercase tracking-wider text-slate-500 font-semibold">Account</p>
          <h2 className="text-base font-mono text-slate-100 truncate">{selected.id}</h2>
          {account.data?.owner_name && (
            <p className="text-xs text-slate-400 truncate">{account.data.owner_name}</p>
          )}
        </div>
        {account.data?.status && (
          <span className={`chip ${STATUS_STYLES[account.data.status] || ''} shrink-0`}>
            {account.data.status}
          </span>
        )}
      </div>

      <div className="px-3.5 py-3 border-b border-ink-800 space-y-3">
        {account.status === 'loading' ? (
          <SkeletonLines lines={3} />
        ) : account.status === 'error' ? (
          <ErrorState error={account.error} onRetry={account.run} compact />
        ) : (
          <>
            <RiskMeter score={account.data?.risk_score} status={account.data?.status} />
            <dl className="grid grid-cols-2 gap-x-3 gap-y-2.5">
              <Field label="Balance" value={money(account.data?.balance)} />
              <Field label="Country" value={account.data?.country} />
              <Field label="Owner" value={account.data?.customer_name} />
              <Field label="Opened" value={shortDate(account.data?.created_at)} />
              <Field
                label="Sent"
                value={`${money(account.data?.sent_total)} · ${account.data?.sent_count ?? 0}`}
              />
              <Field
                label="Received"
                value={`${money(account.data?.received_total)} · ${account.data?.received_count ?? 0}`}
              />
            </dl>
          </>
        )}
      </div>

      <div className="flex border-b border-ink-800 shrink-0" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            onClick={() => setTab(item.key)}
            className={`flex-1 px-2 py-2 text-2xs font-medium transition-colors border-b-2 -mb-px ${
              tab === item.key
                ? 'text-sky-300 border-sky-400'
                : 'text-slate-500 border-transparent hover:text-slate-300'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">
        {tab === 'why' && (
          <WhyTab
            accId={accId}
            onHighlight={onHighlight}
            onRecompute={() => {
              account.run()
              onDataChanged?.()
            }}
          />
        )}
        {tab === 'transactions' && <TransactionsTab accId={accId} onFocus={onFocus} />}
        {tab === 'connections' && <ConnectionsTab accId={accId} onHighlight={onHighlight} />}
      </div>
    </aside>
  )
}

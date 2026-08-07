import { count, money } from '../lib/format'
import { Skeleton } from './states'

function Tile({ label, value, sub, accent = 'text-slate-100', loading, failed }) {
  return (
    <div className="panel px-4 py-3.5 flex flex-col gap-1.5 min-w-0">
      <p className="text-2xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      {loading ? (
        <Skeleton className="h-7 w-20" />
      ) : (
        <p className={`text-2xl font-semibold tabular truncate ${failed ? 'text-slate-600' : accent}`}>
          {failed ? '—' : value}
        </p>
      )}
      {loading ? (
        <Skeleton className="h-3 w-28" />
      ) : (
        <p className="text-2xs text-slate-500 truncate">{failed ? 'Unavailable' : sub}</p>
      )}
    </div>
  )
}

export function StatTiles({ state }) {
  const loading = state.status === 'loading'
  const failed = state.status === 'error'
  const data = state.data ?? {}

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Tile
        label="Accounts"
        value={count(data.total_accounts)}
        sub={`${count(data.customers)} customers · ${money(data.total_balance, { compact: true })} held`}
        loading={loading}
        failed={failed}
      />
      <Tile
        label="Transactions"
        value={count(data.total_transactions)}
        sub={`${money(data.total_transferred, { compact: true })} moved in total`}
        loading={loading}
        failed={failed}
      />
      <Tile
        label="Active fraud rings"
        value={count(data.active_fraud_rings)}
        sub="Closed loops of 3–5 transfers"
        accent="text-rose-400"
        loading={loading}
        failed={failed}
      />
      <Tile
        label="High-risk accounts"
        value={count(data.high_risk_accounts)}
        sub={`${count(data.flagged_accounts)} flagged · ${count(data.suspicious_accounts)} suspicious`}
        accent="text-amber-400"
        loading={loading}
        failed={failed}
      />
    </div>
  )
}

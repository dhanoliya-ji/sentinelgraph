import { useCallback, useState } from 'react'
import { api } from './api/client'
import { useAsync } from './hooks/useAsync'
import { DetailSidebar } from './components/DetailSidebar'
import { DetectionPanel } from './components/DetectionPanel'
import { GraphView } from './components/GraphView'
import { HealthBanner, HealthIndicator } from './components/HealthBanner'
import { SearchBar } from './components/SearchBar'
import { StatTiles } from './components/StatTiles'

export default function App() {
  const [focus, setFocus] = useState(null)
  const [selected, setSelected] = useState(null)
  const [highlight, setHighlight] = useState([])
  const [health, setHealth] = useState(null)
  const [reloadToken, setReloadToken] = useState(0)

  const stats = useAsync((signal) => api.stats(signal), [reloadToken])
  const graph = useAsync(
    (signal) => api.graph({ focus, depth: 2, limit: focus ? 300 : 250 }, signal),
    [focus, reloadToken],
  )

  /** Centre the graph on an account and open it in the sidebar. */
  const focusAccount = useCallback((accId) => {
    if (!accId) return
    setFocus(accId)
    setSelected({ id: accId, kind: 'Account' })
    setHighlight([])
  }, [])

  const onSelectNode = useCallback((node) => {
    setSelected(node ? { id: node.id, kind: node.kind, label: node.label, status: node.status } : null)
    setHighlight([])
  }, [])

  const onSearchSelect = useCallback(
    (hit) => {
      if (hit.kind === 'Account') {
        focusAccount(hit.id)
      } else {
        setSelected({ id: hit.id, kind: hit.kind, label: hit.label })
        setHighlight([hit.id])
      }
    },
    [focusAccount],
  )

  const refreshAll = useCallback(() => setReloadToken((token) => token + 1), [])

  return (
    <div className="min-h-full flex flex-col">
      <header className="sticky top-0 z-20 bg-ink-950/85 backdrop-blur border-b border-ink-800">
        <div className="px-4 sm:px-6 py-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2.5 mr-auto">
            <svg viewBox="0 0 32 32" className="w-7 h-7 shrink-0" aria-hidden="true">
              <path d="M16 9 9 21 23 21Z" fill="none" stroke="#33415c" strokeWidth="1.5" />
              <circle cx="16" cy="9" r="3.2" fill="#f43f5e" />
              <circle cx="9" cy="21" r="3.2" fill="#38bdf8" />
              <circle cx="23" cy="21" r="3.2" fill="#a78bfa" />
            </svg>
            <div>
              <h1 className="text-sm font-semibold text-slate-100 leading-tight">SentinelGraph</h1>
              <p className="text-2xs text-slate-500 leading-tight">
                Financial fraud detection on a graph
              </p>
            </div>
          </div>

          <SearchBar onSelect={onSearchSelect} />

          {focus && (
            <button
              type="button"
              onClick={() => {
                setFocus(null)
                setHighlight([])
              }}
              className="btn-ghost text-2xs"
            >
              ← Whole graph
            </button>
          )}

          <HealthIndicator onChange={setHealth} />
        </div>

        <HealthBanner health={health} />
      </header>

      <main className="flex-1 px-4 sm:px-6 py-4 space-y-4">
        <StatTiles state={stats} />

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)_minmax(0,340px)] gap-4 items-start">
          <div className="order-2 xl:order-1">
            <DetectionPanel onFocus={focusAccount} />
          </div>

          <div className="order-1 xl:order-2 h-[52vh] xl:h-[calc(100vh-15rem)] xl:sticky xl:top-24">
            <GraphView
              state={graph}
              focus={focus}
              selectedId={selected?.id}
              highlight={highlight}
              onSelectNode={onSelectNode}
              onRetry={graph.run}
            />
          </div>

          <div className="order-3 h-[70vh] xl:h-[calc(100vh-15rem)] xl:sticky xl:top-24">
            <DetailSidebar
              selected={selected}
              onFocus={focusAccount}
              onHighlight={setHighlight}
              onDataChanged={refreshAll}
            />
          </div>
        </div>
      </main>

      <footer className="px-4 sm:px-6 py-4 border-t border-ink-800 text-2xs text-slate-600 flex flex-wrap gap-x-4 gap-y-1">
        <span>SentinelGraph — openCypher over Bolt against CognoDB.</span>
        <span>Every query is parameterised; every traversal is bounded.</span>
      </footer>
    </div>
  )
}

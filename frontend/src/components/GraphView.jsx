import { useEffect, useMemo, useRef } from 'react'
import cytoscape from 'cytoscape'
import { ENTITY_COLORS, RISK_COLORS } from '../lib/format'
import { EmptyState, ErrorState } from './states'

const EDGE_COLORS = {
  TRANSFERRED: '#64748b',
  USED_DEVICE: '#0ea5e9',
  LOGGED_IN_FROM: '#8b5cf6',
  LINKED_CARD: '#475569',
  OWNS: '#14b8a6',
}

const STYLESHEET = [
  {
    selector: 'node',
    style: {
      'background-color': 'data(color)',
      width: 'data(size)',
      height: 'data(size)',
      label: 'data(label)',
      color: '#cbd5e1',
      'font-size': 9,
      'font-family': 'Inter, system-ui, sans-serif',
      'font-weight': 500,
      'text-valign': 'bottom',
      'text-margin-y': 5,
      'text-max-width': 90,
      'text-wrap': 'ellipsis',
      'border-width': 1.5,
      'border-color': '#0a0e17',
      'transition-property': 'opacity, border-width, border-color',
      'transition-duration': '160ms',
    },
  },
  {
    selector: 'node[kind = "Account"]',
    style: { shape: 'ellipse' },
  },
  { selector: 'node[kind = "Device"]', style: { shape: 'round-rectangle' } },
  { selector: 'node[kind = "IPAddress"]', style: { shape: 'diamond' } },
  { selector: 'node[kind = "CreditCard"]', style: { shape: 'round-tag' } },
  { selector: 'node[kind = "Customer"]', style: { shape: 'hexagon' } },
  {
    selector: 'edge',
    style: {
      width: 'data(width)',
      'line-color': 'data(color)',
      'target-arrow-color': 'data(color)',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.7,
      'curve-style': 'bezier',
      opacity: 0.5,
      'transition-property': 'opacity, width, line-color',
      'transition-duration': '160ms',
    },
  },
  {
    selector: 'node.selected',
    style: { 'border-width': 4, 'border-color': '#e2e8f0', 'font-size': 11, color: '#f8fafc' },
  },
  {
    selector: '.highlighted',
    style: { opacity: 1, 'border-width': 3, 'border-color': '#f8fafc', 'z-index': 20 },
  },
  { selector: 'edge.highlighted', style: { width: 3.5, 'line-color': '#f8fafc', opacity: 1 } },
  { selector: '.dimmed', style: { opacity: 0.08 } },
]

const LAYOUT = {
  name: 'cose',
  animate: false,
  nodeRepulsion: 9000,
  idealEdgeLength: 70,
  edgeElasticity: 100,
  gravity: 0.5,
  numIter: 900,
  padding: 40,
  randomize: false,
  componentSpacing: 90,
}

const LEGEND = [
  { label: 'Safe account', color: RISK_COLORS.SAFE },
  { label: 'Suspicious', color: RISK_COLORS.SUSPICIOUS },
  { label: 'Flagged', color: RISK_COLORS.FLAGGED },
  { label: 'Device', color: ENTITY_COLORS.Device },
  { label: 'IP address', color: ENTITY_COLORS.IPAddress },
  { label: 'Customer', color: ENTITY_COLORS.Customer },
  { label: 'Credit card', color: ENTITY_COLORS.CreditCard },
]

function toElements({ nodes = [], edges = [] }) {
  const amounts = edges.map((edge) => edge.amount).filter((value) => typeof value === 'number')
  const maxAmount = amounts.length ? Math.max(...amounts) : 0

  return [
    ...nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.kind === 'Account' ? node.id : node.label || node.id,
        kind: node.kind,
        status: node.status,
        risk: node.risk_score,
        color:
          node.kind === 'Account'
            ? RISK_COLORS[node.status] || '#64748b'
            : ENTITY_COLORS[node.kind] || '#64748b',
        // Riskier accounts read as bigger, so the eye lands on them first.
        size: node.kind === 'Account' ? 16 + Math.min(node.risk_score || 0, 100) * 0.16 : 14,
      },
    })),
    ...edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        color: EDGE_COLORS[edge.type] || '#475569',
        width:
          edge.type === 'TRANSFERRED' && maxAmount
            ? 0.8 + ((edge.amount || 0) / maxAmount) * 4
            : 1,
      },
    })),
  ]
}

export function GraphView({ state, selectedId, highlight = [], onSelectNode, onRetry, focus }) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)
  const onSelectRef = useRef(onSelectNode)
  onSelectRef.current = onSelectNode

  const elements = useMemo(() => (state.data ? toElements(state.data) : []), [state.data])

  // Create the instance once; feeding it new elements is far cheaper than
  // tearing down and rebuilding the canvas on every data change.
  useEffect(() => {
    if (!containerRef.current || cyRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      style: STYLESHEET,
      elements: [],
      minZoom: 0.15,
      maxZoom: 3,
      wheelSensitivity: 0.25,
      boxSelectionEnabled: false,
    })

    cy.on('tap', 'node', (event) => onSelectRef.current?.(event.target.data()))
    cy.on('tap', (event) => {
      if (event.target === cy) onSelectRef.current?.(null)
    })

    cyRef.current = cy
    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy || state.status !== 'success') return

    cy.batch(() => {
      cy.elements().remove()
      cy.add(elements)
    })
    if (elements.length) {
      cy.layout(LAYOUT).run()
      cy.fit(undefined, 45)
    }
  }, [elements, state.status])

  // Selection + explainability highlighting.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.batch(() => {
      cy.elements().removeClass('highlighted dimmed selected')

      if (highlight.length) {
        const targets = cy.nodes().filter((node) => highlight.includes(node.id()))
        if (targets.length) {
          const neighbourhood = targets.union(targets.edgesWith(targets))
          cy.elements().addClass('dimmed')
          neighbourhood.removeClass('dimmed').addClass('highlighted')
        }
      }

      if (selectedId) cy.getElementById(selectedId).addClass('selected')
    })
  }, [selectedId, highlight, elements])

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-slate-200">Relationship graph</h2>
          <p className="text-2xs text-slate-500 truncate">
            {focus
              ? `Centred on ${focus} — showing everything within two hops`
              : 'Accounts, the devices and addresses they use, and the money between them'}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            className="btn-ghost !px-2 !py-1 text-2xs"
            onClick={() => cyRef.current?.fit(undefined, 45)}
          >
            Fit
          </button>
          <button
            type="button"
            className="btn-ghost !px-2 !py-1 text-2xs"
            onClick={() => cyRef.current?.layout(LAYOUT).run()}
          >
            Re-layout
          </button>
        </div>
      </div>

      <div className="relative flex-1 min-h-[380px]">
        <div
          ref={containerRef}
          className="absolute inset-0"
          style={{ visibility: state.status === 'success' && elements.length ? 'visible' : 'hidden' }}
          role="application"
          aria-label="Interactive relationship graph"
        />

        {state.status === 'loading' && (
          <div className="absolute inset-0 grid place-items-center">
            <div className="flex flex-col items-center gap-3">
              <div className="flex gap-1.5">
                {[0, 1, 2].map((index) => (
                  <span
                    key={index}
                    className="w-2 h-2 rounded-full bg-sky-400/70 animate-pulse"
                    style={{ animationDelay: `${index * 140}ms` }}
                  />
                ))}
              </div>
              <p className="text-xs text-slate-500">Building the graph…</p>
            </div>
          </div>
        )}

        {state.status === 'error' && (
          <div className="absolute inset-0 grid place-items-center">
            <ErrorState error={state.error} onRetry={onRetry} />
          </div>
        )}

        {state.status === 'success' && !elements.length && (
          <div className="absolute inset-0 grid place-items-center">
            <EmptyState
              icon="◌"
              title="The graph is empty"
              message="No nodes were returned. If you have not loaded the demo data yet, run seed/seed_database.py and refresh."
              action={
                onRetry && (
                  <button type="button" onClick={onRetry} className="btn-ghost mt-2">
                    Refresh
                  </button>
                )
              }
            />
          </div>
        )}

        {state.status === 'success' && elements.length > 0 && (
          <div className="absolute left-3 bottom-3 panel !bg-ink-900/85 backdrop-blur px-3 py-2 flex flex-wrap gap-x-3 gap-y-1.5 max-w-[calc(100%-1.5rem)]">
            {LEGEND.map((item) => (
              <span key={item.label} className="flex items-center gap-1.5 text-2xs text-slate-400">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: item.color }}
                  aria-hidden="true"
                />
                {item.label}
              </span>
            ))}
          </div>
        )}

        {state.data?.truncated && (
          <p className="absolute right-3 top-3 text-2xs text-amber-300/80 bg-amber-500/10 border border-amber-500/25 rounded-md px-2 py-1">
            Showing a capped slice of the graph
          </p>
        )}
      </div>
    </div>
  )
}

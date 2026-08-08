# Screenshots

The six images the root README renders. All captured at 1920×1080 against the
deployed app at <https://sentinelgraph.vercel.app>, running the seeded dataset,
so every figure shown matches the numbers documented in the README.

| File | What it shows |
|---|---|
| `01-dashboard.png` | The whole app: stat tiles, full network, legend |
| `02-ring-detection.png` | Ring detector run — headline, the four-account cycle, $195,600 cycled |
| `03-why-flagged.png` | `ACC_1101` at 100/100, **Why flagged** evidence, one reason highlighted in the graph |
| `04-shared-infrastructure.png` | Both shared-hardware clusters — the six-account fraud farm and the three-account bridge |
| `05-trace-path.png` | `ACC_1301 → ACC_1350 → ACC_1399 → ACC_1101` with amounts at each hop |
| `06-offline-state.png` | The offline banner and a retryable error when the API is unreachable |

To regenerate after changing the UI: reseed with
`python seed/seed_database.py --reset` so the figures still line up, then
recapture at 1920×1080 with the browser at 100% zoom and no bookmarks bar. For
`06`, force the failure with DevTools → Network → **Offline**, then reload.

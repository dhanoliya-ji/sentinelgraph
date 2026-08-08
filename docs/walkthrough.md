# Guided walkthrough

A four-minute tour of the deployed app, in the order the data was built to tell
its story. Open <https://sentinelgraph.vercel.app> and follow along — each step
says what to click, what you should see, and why it matters.

> The API sleeps on Render's free tier. If the header shows *Checking…*, give it
> up to a minute to wake, then carry on.

---

## 1 — The problem, in four numbers

Look at the tiles: **50 accounts, 126 transfers, 1 active fraud ring, 6 high-risk
accounts.**

None of those six accounts are flagged for anything in their own row. Every one
of them is flagged because of *who it is connected to*. That distinction is the
whole reason this is a graph and not a table.

## 2 — The graph

Colour is risk (green safe, amber suspicious, red flagged), node size is the risk
score, edge thickness is the amount moved. The legend sits under the canvas.

Note the shape: a dense knot of red on one side, loose background traffic on the
other. The knot is not a coincidence — it is three planted scenarios that turn
out to share members.

## 3 — Circular money flows

Press **Run** on *Circular money flows*.

> Found 1 circular money flow. The largest cycles $195,600 through 4 accounts.

The chain is `ACC_1101 → ACC_1102 → ACC_1103 → ACC_1104 → ACC_1101` — roughly
$50,000 a hop, decaying slightly each time, spread over eight days. Click any
account chip to centre the graph on the ring.

This is the query a relational schema needs a recursive CTE for. Here it is a
variable-length pattern that reads like the sentence describing it. Expand
**Show the Cypher this ran** to see it.

## 4 — Why an account was flagged ← *the part worth your time*

With `ACC_1101` selected, the sidebar opens on **Why flagged**.

The score is 100/100, and underneath it is every reason that contributed, in
plain English, with the points each one added: member of a circular flow (+35),
shares a device and IP with several accounts (+25), close to accounts already
flagged (+30), signs in through a VPN (+10).

**Click any reason.** The exact subgraph that reason came from lights up while
everything else dims. The score is not a number the app asks you to trust — it
is a claim with the evidence attached, and every piece of evidence is a shape in
the graph you can look at.

## 5 — Shared devices and addresses

Press **Run** on *Shared devices & addresses*. Two clusters come back:

- **Six accounts registered to six different names**, all signing in from device
  `DEV_8899` and IP `192.168.1.100`, a known VPN exit node. Six identities, one
  person.
- **Three accounts** — `ACC_1101`, `ACC_1350`, `ACC_1399` — sharing `DEV_8898`.
  Hold onto that one; it is the bridge in the next step.

The detector deliberately requires the device **and** the IP to match. A shared
device alone is ordinary and would flag half the portfolio; a shared full
fingerprint is not.

## 6 — The mule funnel, and the bridge

Press **Run** on *Mule account funnels*: ten accounts feed `ACC_1350`, which
forwards ~95% of it straight to `ACC_1399` offshore.

Now trace `ACC_1301` → `ACC_1101` (the boxes are pre-filled; press **Trace**).

> Money can move from ACC_1301 to ACC_1101 in as few as 3 steps.
> `ACC_1301 →$4.7K→ ACC_1350 →$59.9K→ ACC_1399 →$41K→ ACC_1101`

That is the punchline. The mule funnel and the laundering ring look like two
unrelated incidents in a table. In the graph they are visibly one operation —
the money walks out of the funnel and straight into the ring, and the shared
device from step 5 is the same seam.

## 7 — The engineering, briefly

- **Show the Cypher this ran** under any detector prints the exact query. Every
  one is parameterised; there is no string-concatenated Cypher in the codebase.
- Every traversal is depth-bounded and every query carries a `LIMIT`, because the
  free CognoDB instance is 0.5 vCPU / 256 MB.
- To see the failure path: open DevTools → Network → **Offline** and reload. The
  app shows one honest banner and a retryable error rather than each panel
  failing separately. That state is captured in
  [`screenshots/06-offline-state.png`](../screenshots/06-offline-state.png).

---

## Reproducing this exactly

The numbers above come from the seeded dataset. To recreate it:

```bash
python seed/seed_database.py --reset
```

The seed is deterministic, so the accounts, amounts and scores will match what
is written here and what the screenshots show.

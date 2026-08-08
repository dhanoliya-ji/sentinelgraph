# Screen recording

> **Link:** _paste your recording URL here (Loom, YouTube unlisted, or a file in this repo)_

The assignment requires a short recording alongside the hosted demo. Aim for
**2–4 minutes**. The run-through below covers every feature and follows the
narrative the data was built to tell.

## Suggested script

**0:00 — What the problem is (20s)**
Open the deployed app. Point at the four tiles.
> "Fifty accounts, a hundred and twenty-six transfers. Six accounts are flagged.
> None of them are flagged because of anything in their own row — they're flagged
> because of who they're connected to."

**0:20 — The graph (25s)**
Point out the legend: colour is risk, size is score, edge thickness is amount.
Note the dense cluster on one side and the loose background traffic on the other.

**0:45 — Circular money flows (35s)**
Run the detector. Read the headline aloud — it's written in English on purpose.
Click `ACC_1101` to centre the graph on the ring.
> "Four accounts, roughly fifty thousand dollars a hop — a hundred and ninety-five
> thousand cycled in total — and it comes back to where it started. That's the
> query a relational database needs a recursive CTE for."

**1:20 — Why flagged (40s)** ← *the part worth lingering on*
With `ACC_1101` selected, open **Why flagged**. Walk down the evidence list.
Click one reason and show the subgraph light up while everything else dims.
> "The score is 100. Here's every reason, in English, with the points each one
> added — and clicking a reason shows you the exact part of the graph it came from."

**2:00 — Shared devices (25s)**
Run the detector.
> "Six accounts, six different names, one phone and one VPN address."

**2:25 — Mule funnel and the bridge (35s)**
Run mule detection, then trace `ACC_1301` → `ACC_1101`.
> "Ten accounts feed one account, which wires ninety-five percent offshore. And
> the offshore account pays the laundering ring. Two incidents in a table — one
> operation in a graph."

**3:00 — Engineering (20s)**
Expand **Show the Cypher this ran** on any detector. Mention parameterised
queries and bounded traversals. Optionally kill the backend to show the offline
banner and a retryable error state.

## Recording tips

- 1920×1080, browser zoom at 100%, no bookmarks bar.
- Run `python seed/seed_database.py --reset` first so the data matches the README exactly.
- Record against the **deployed** URL, not localhost — it doubles as proof the demo link works.
- If the Render free tier has gone to sleep, load the page once before recording.

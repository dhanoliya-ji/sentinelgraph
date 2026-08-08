"""Every Cypher statement used by the application, as named constants.

Two rules hold throughout this file:

1. **No string interpolation.** Every value that varies at runtime is a `$param`
   passed to the driver separately. Nothing here is built with f-strings, `%`
   or `+`. Optional filters use the `($p IS NULL OR ...)` idiom so that one
   static query serves several filter combinations.

2. **Every traversal is bounded and every query has a LIMIT.** The free CognoDB
   c0 instance has 256 MB of RAM; an unbounded `[:TRANSFERRED*]` pattern can
   exhaust it. Variable-length patterns therefore always carry an explicit
   upper bound.

Portability note: CognoDB speaks openCypher, not the full Neo4j dialect. This
file deliberately avoids APOC, `datetime()` arithmetic and `shortestPath()`.
Shortest paths are expressed as a bounded match ordered by `length(path)` --
same result, broader compatibility. Timestamps are stored twice on each
transfer: `timestamp` (ISO-8601 string, for display) and `ts` (epoch seconds
integer, for arithmetic).

Variable-length patterns: measured against CognoDB, `[:REL*n]` returns results
correctly up to three hops and then silently yields **zero rows** at four or
more -- no error, just an empty result. Verified on this dataset, which
contains a known four-hop cycle: `[:TRANSFERRED*4]` returns nothing while the
equivalent four-hop explicit chain returns it. Because the failure is silent,
it would have shipped as "no fraud rings found" rather than as an error.

Every traversal that can exceed three hops is therefore written as a `UNION ALL`
of explicit fixed-length chains, one branch per length. This is more verbose but
it is correct on this engine, it keeps relationship-uniqueness semantics (an
edge is not reused within a single path), and each branch is individually
bounded -- which was the reason for the depth caps in the first place. Patterns
that stay within three hops (`DETECT_FLAGGED_PROXIMITY`) still use `*1..2`.
"""

# ---------------------------------------------------------------------------
# Schema -- executed by seed/seed_database.py
# ---------------------------------------------------------------------------
CONSTRAINTS = [
    "CREATE CONSTRAINT account_id_unique IF NOT EXISTS FOR (a:Account) REQUIRE a.acc_id IS UNIQUE",
    "CREATE CONSTRAINT customer_id_unique IF NOT EXISTS FOR (c:Customer) REQUIRE c.cust_id IS UNIQUE",
    "CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
    "CREATE CONSTRAINT ip_unique IF NOT EXISTS FOR (i:IPAddress) REQUIRE i.ip_address IS UNIQUE",
    "CREATE CONSTRAINT card_unique IF NOT EXISTS FOR (cc:CreditCard) REQUIRE cc.card_number IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX account_status IF NOT EXISTS FOR (a:Account) ON (a.status)",
    "CREATE INDEX account_risk IF NOT EXISTS FOR (a:Account) ON (a.risk_score)",
    "CREATE INDEX account_owner IF NOT EXISTS FOR (a:Account) ON (a.owner_name)",
]

# ---------------------------------------------------------------------------
# Health & stats
# ---------------------------------------------------------------------------
PING = "RETURN 1 AS ok"

STATS = """
MATCH (a:Account)
WITH count(a) AS total_accounts,
     sum(CASE WHEN a.status = 'FLAGGED' THEN 1 ELSE 0 END) AS flagged_accounts,
     sum(CASE WHEN a.status = 'SUSPICIOUS' THEN 1 ELSE 0 END) AS suspicious_accounts,
     sum(CASE WHEN a.risk_score >= 70 THEN 1 ELSE 0 END) AS high_risk_accounts,
     sum(a.balance) AS total_balance
MATCH ()-[t:TRANSFERRED]->()
RETURN total_accounts,
       flagged_accounts,
       suspicious_accounts,
       high_risk_accounts,
       total_balance,
       count(t) AS total_transactions,
       sum(t.amount) AS total_transferred
"""

STATS_ENTITY_COUNTS = """
MATCH (c:Customer) WITH count(c) AS customers
MATCH (d:Device) WITH customers, count(d) AS devices
MATCH (i:IPAddress) WITH customers, devices, count(i) AS ip_addresses
MATCH (cc:CreditCard)
RETURN customers, devices, ip_addresses, count(cc) AS credit_cards
"""

# ---------------------------------------------------------------------------
# Search -- one query across four entity types
# ---------------------------------------------------------------------------
SEARCH = """
CALL {
    MATCH (a:Account)
    WHERE toLower(a.acc_id) CONTAINS $q OR toLower(a.owner_name) CONTAINS $q
    RETURN 'Account' AS kind, a.acc_id AS id, a.owner_name AS label,
           a.status AS status, a.risk_score AS risk_score
    LIMIT $limit
    UNION
    MATCH (d:Device)
    WHERE toLower(d.device_id) CONTAINS $q OR toLower(d.os) CONTAINS $q
    RETURN 'Device' AS kind, d.device_id AS id, d.device_type AS label,
           NULL AS status, NULL AS risk_score
    LIMIT $limit
    UNION
    MATCH (i:IPAddress)
    WHERE toLower(i.ip_address) CONTAINS $q
    RETURN 'IPAddress' AS kind, i.ip_address AS id, i.country AS label,
           NULL AS status, NULL AS risk_score
    LIMIT $limit
    UNION
    MATCH (c:Customer)
    WHERE toLower(c.cust_id) CONTAINS $q OR toLower(c.name) CONTAINS $q
    RETURN 'Customer' AS kind, c.cust_id AS id, c.name AS label,
           c.risk_rating AS status, NULL AS risk_score
    LIMIT $limit
}
RETURN kind, id, label, status, risk_score
LIMIT $limit
"""

# Fallback used automatically if the instance does not support CALL {} subqueries.
SEARCH_SIMPLE = """
MATCH (n)
WHERE (n:Account AND (toLower(n.acc_id) CONTAINS $q OR toLower(n.owner_name) CONTAINS $q))
   OR (n:Device AND toLower(n.device_id) CONTAINS $q)
   OR (n:IPAddress AND toLower(n.ip_address) CONTAINS $q)
   OR (n:Customer AND (toLower(n.cust_id) CONTAINS $q OR toLower(n.name) CONTAINS $q))
RETURN labels(n)[0] AS kind,
       coalesce(n.acc_id, n.device_id, n.ip_address, n.cust_id) AS id,
       coalesce(n.owner_name, n.device_type, n.country, n.name) AS label,
       n.status AS status,
       n.risk_score AS risk_score
LIMIT $limit
"""

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
# Optional filters stay inside one static query via the `$p IS NULL` idiom --
# no query text is assembled at runtime.
ACCOUNT_LIST = """
MATCH (a:Account)
WHERE ($status IS NULL OR a.status = $status)
  AND ($min_risk IS NULL OR a.risk_score >= $min_risk)
OPTIONAL MATCH (c:Customer)-[:OWNS]->(a)
RETURN a.acc_id AS acc_id,
       a.owner_name AS owner_name,
       a.balance AS balance,
       a.risk_score AS risk_score,
       a.status AS status,
       a.country AS country,
       a.created_at AS created_at,
       c.cust_id AS customer_id,
       c.name AS customer_name
ORDER BY a.risk_score DESC, a.acc_id ASC
SKIP $skip
LIMIT $limit
"""

ACCOUNT_COUNT = """
MATCH (a:Account)
WHERE ($status IS NULL OR a.status = $status)
  AND ($min_risk IS NULL OR a.risk_score >= $min_risk)
RETURN count(a) AS total
"""

ACCOUNT_DETAIL = """
MATCH (a:Account {acc_id: $acc_id})
OPTIONAL MATCH (c:Customer)-[:OWNS]->(a)
OPTIONAL MATCH (a)-[out:TRANSFERRED]->()
WITH a, c, count(out) AS sent_count, coalesce(sum(out.amount), 0.0) AS sent_total
OPTIONAL MATCH ()-[inc:TRANSFERRED]->(a)
RETURN a.acc_id AS acc_id,
       a.owner_name AS owner_name,
       a.balance AS balance,
       a.risk_score AS risk_score,
       a.status AS status,
       a.country AS country,
       a.created_at AS created_at,
       c.cust_id AS customer_id,
       c.name AS customer_name,
       c.country AS customer_country,
       c.risk_rating AS customer_risk_rating,
       sent_count,
       sent_total,
       count(inc) AS received_count,
       coalesce(sum(inc.amount), 0.0) AS received_total
"""

ACCOUNT_EXISTS = "MATCH (a:Account {acc_id: $acc_id}) RETURN a.acc_id AS acc_id"

ACCOUNT_TRANSACTIONS = """
MATCH (a:Account {acc_id: $acc_id})
CALL {
    WITH a
    MATCH (a)-[t:TRANSFERRED]->(other:Account)
    WHERE $direction IN ['out', 'both']
    RETURN t, other, 'out' AS direction
    UNION
    WITH a
    MATCH (other:Account)-[t:TRANSFERRED]->(a)
    WHERE $direction IN ['in', 'both']
    RETURN t, other, 'in' AS direction
}
RETURN t.txn_id AS txn_id,
       t.amount AS amount,
       t.currency AS currency,
       t.timestamp AS timestamp,
       t.ts AS ts,
       direction,
       other.acc_id AS counterparty_id,
       other.owner_name AS counterparty_name,
       other.status AS counterparty_status
ORDER BY ts DESC
LIMIT $limit
"""

# Fallback for instances without CALL {} subquery support.
ACCOUNT_TRANSACTIONS_OUT = """
MATCH (a:Account {acc_id: $acc_id})-[t:TRANSFERRED]->(other:Account)
RETURN t.txn_id AS txn_id, t.amount AS amount, t.currency AS currency,
       t.timestamp AS timestamp, t.ts AS ts, 'out' AS direction,
       other.acc_id AS counterparty_id, other.owner_name AS counterparty_name,
       other.status AS counterparty_status
ORDER BY ts DESC
LIMIT $limit
"""

ACCOUNT_TRANSACTIONS_IN = """
MATCH (other:Account)-[t:TRANSFERRED]->(a:Account {acc_id: $acc_id})
RETURN t.txn_id AS txn_id, t.amount AS amount, t.currency AS currency,
       t.timestamp AS timestamp, t.ts AS ts, 'in' AS direction,
       other.acc_id AS counterparty_id, other.owner_name AS counterparty_name,
       other.status AS counterparty_status
ORDER BY ts DESC
LIMIT $limit
"""

ACCOUNT_CONNECTIONS = """
MATCH (a:Account {acc_id: $acc_id})
OPTIONAL MATCH (a)-[:USED_DEVICE]->(d:Device)
WITH a, collect(DISTINCT {id: d.device_id, type: d.device_type, os: d.os}) AS devices
OPTIONAL MATCH (a)-[:LOGGED_IN_FROM]->(i:IPAddress)
WITH a, devices,
     collect(DISTINCT {id: i.ip_address, country: i.country, is_vpn: i.is_vpn}) AS ips
OPTIONAL MATCH (a)-[:LINKED_CARD]->(cc:CreditCard)
WITH a, devices, ips,
     collect(DISTINCT {id: cc.card_number, issuer: cc.issuer, expiry: cc.expiry}) AS cards
OPTIONAL MATCH (c:Customer)-[:OWNS]->(a)
RETURN devices, ips, cards,
       collect(DISTINCT {id: c.cust_id, name: c.name, country: c.country}) AS customers
"""

# ---------------------------------------------------------------------------
# Graph payload for Cytoscape
# ---------------------------------------------------------------------------
# Relationship-centric: one row per edge carrying both endpoints. The service
# layer de-duplicates rows into a node list and an edge list.
_EDGE_PROJECTION = """
RETURN labels(src)[0] AS source_label,
       coalesce(src.acc_id, src.cust_id, src.device_id, src.ip_address, src.card_number) AS source_id,
       coalesce(src.owner_name, src.name, src.device_type, src.country, src.issuer) AS source_label_text,
       src.status AS source_status,
       src.risk_score AS source_risk,
       labels(dst)[0] AS target_label,
       coalesce(dst.acc_id, dst.cust_id, dst.device_id, dst.ip_address, dst.card_number) AS target_id,
       coalesce(dst.owner_name, dst.name, dst.device_type, dst.country, dst.issuer) AS target_label_text,
       dst.status AS target_status,
       dst.risk_score AS target_risk,
       type(rel) AS rel_type,
       rel.amount AS amount,
       rel.timestamp AS timestamp
"""

GRAPH_ALL = (
    """
MATCH (src)-[rel]->(dst)
WITH src, rel, dst
LIMIT $limit
"""
    + _EDGE_PROJECTION
)

# Depth is a literal, not a parameter: openCypher does not allow a parameter in
# a variable-length bound. Two explicit constants cover the depths the UI offers.
GRAPH_FOCUS_1 = (
    """
MATCH (a:Account {acc_id: $acc_id})-[rel]-(other)
WITH a AS src, rel, other AS dst
LIMIT $limit
"""
    + _EDGE_PROJECTION
)

GRAPH_FOCUS_2 = (
    """
MATCH path = (a:Account {acc_id: $acc_id})-[*1..2]-(other)
UNWIND relationships(path) AS rel
WITH DISTINCT rel
WITH startNode(rel) AS src, rel, endNode(rel) AS dst
LIMIT $limit
"""
    + _EDGE_PROJECTION
)

GRAPH_ISOLATED_ACCOUNTS = """
MATCH (a:Account)
WHERE NOT (a)--()
RETURN a.acc_id AS id, a.owner_name AS label_text, a.status AS status,
       a.risk_score AS risk_score
LIMIT $limit
"""

# ---------------------------------------------------------------------------
# Fraud detection
# ---------------------------------------------------------------------------
# Q1 -- circular money-laundering ring. A closed 3-to-5-hop TRANSFERRED loop
# returning to its origin. This is the query a relational schema struggles
# with: the join depth is data-dependent and unknown in advance.
DETECT_RING_FOR_ACCOUNT = """
MATCH (a:Account {acc_id: $acc_id})-[r1:TRANSFERRED]->(n1:Account)
     -[r2:TRANSFERRED]->(n2:Account)-[r3:TRANSFERRED]->(a)
RETURN [a.acc_id, n1.acc_id, n2.acc_id, a.acc_id] AS account_chain,
       [r1.amount, r2.amount, r3.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id] AS txn_ids,
       3 AS hops
UNION ALL
MATCH (a:Account {acc_id: $acc_id})-[r1:TRANSFERRED]->(n1:Account)
     -[r2:TRANSFERRED]->(n2:Account)-[r3:TRANSFERRED]->(n3:Account)
     -[r4:TRANSFERRED]->(a)
RETURN [a.acc_id, n1.acc_id, n2.acc_id, n3.acc_id, a.acc_id] AS account_chain,
       [r1.amount, r2.amount, r3.amount, r4.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp, r4.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id, r4.txn_id] AS txn_ids,
       4 AS hops
UNION ALL
MATCH (a:Account {acc_id: $acc_id})-[r1:TRANSFERRED]->(n1:Account)
     -[r2:TRANSFERRED]->(n2:Account)-[r3:TRANSFERRED]->(n3:Account)
     -[r4:TRANSFERRED]->(n4:Account)-[r5:TRANSFERRED]->(a)
RETURN [a.acc_id, n1.acc_id, n2.acc_id, n3.acc_id, n4.acc_id, a.acc_id] AS account_chain,
       [r1.amount, r2.amount, r3.amount, r4.amount, r5.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp, r4.timestamp, r5.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id, r4.txn_id, r5.txn_id] AS txn_ids,
       5 AS hops
ORDER BY hops ASC
LIMIT $limit
"""

# Scan mode: seed the search from non-SAFE accounts only, so the free instance
# is not asked to test every account for membership in a cycle.
DETECT_RINGS_SCAN = """
MATCH (seed:Account)
WHERE seed.status <> 'SAFE'
WITH seed
ORDER BY seed.risk_score DESC
LIMIT $seed_limit
MATCH (seed)-[r1:TRANSFERRED]->(n1:Account)-[r2:TRANSFERRED]->(n2:Account)
     -[r3:TRANSFERRED]->(seed)
RETURN [seed.acc_id, n1.acc_id, n2.acc_id, seed.acc_id] AS account_chain,
       [r1.amount, r2.amount, r3.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id] AS txn_ids,
       3 AS hops
UNION ALL
MATCH (seed:Account)
WHERE seed.status <> 'SAFE'
WITH seed
ORDER BY seed.risk_score DESC
LIMIT $seed_limit
MATCH (seed)-[r1:TRANSFERRED]->(n1:Account)-[r2:TRANSFERRED]->(n2:Account)
     -[r3:TRANSFERRED]->(n3:Account)-[r4:TRANSFERRED]->(seed)
RETURN [seed.acc_id, n1.acc_id, n2.acc_id, n3.acc_id, seed.acc_id] AS account_chain,
       [r1.amount, r2.amount, r3.amount, r4.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp, r4.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id, r4.txn_id] AS txn_ids,
       4 AS hops
UNION ALL
MATCH (seed:Account)
WHERE seed.status <> 'SAFE'
WITH seed
ORDER BY seed.risk_score DESC
LIMIT $seed_limit
MATCH (seed)-[r1:TRANSFERRED]->(n1:Account)-[r2:TRANSFERRED]->(n2:Account)
     -[r3:TRANSFERRED]->(n3:Account)-[r4:TRANSFERRED]->(n4:Account)
     -[r5:TRANSFERRED]->(seed)
RETURN [seed.acc_id, n1.acc_id, n2.acc_id, n3.acc_id, n4.acc_id, seed.acc_id] AS account_chain,
       [r1.amount, r2.amount, r3.amount, r4.amount, r5.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp, r4.timestamp, r5.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id, r4.txn_id, r5.txn_id] AS txn_ids,
       5 AS hops
ORDER BY hops ASC
LIMIT $limit
"""

# Q2 -- shared infrastructure. Distinct account pairs that share BOTH a device
# and an IP address. `a1.acc_id < a2.acc_id` reports each pair once.
DETECT_SHARED_INFRASTRUCTURE = """
MATCH (a1:Account)-[:LOGGED_IN_FROM]->(ip:IPAddress)<-[:LOGGED_IN_FROM]-(a2:Account)
MATCH (a1)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(a2)
WHERE a1.acc_id < a2.acc_id
RETURN a1.acc_id AS account_a,
       a1.owner_name AS owner_a,
       a1.status AS status_a,
       a2.acc_id AS account_b,
       a2.owner_name AS owner_b,
       a2.status AS status_b,
       ip.ip_address AS ip_address,
       ip.country AS ip_country,
       ip.is_vpn AS is_vpn,
       d.device_id AS device_id,
       d.device_type AS device_type
ORDER BY ip_address, device_id, account_a
LIMIT $limit
"""

# Q5 -- mule funnel. Many senders in, one large payout onward.
DETECT_MULES = """
MATCH (sender:Account)-[t:TRANSFERRED]->(mule:Account)
WITH mule,
     count(DISTINCT sender.acc_id) AS inbound_count,
     sum(t.amount) AS inbound_total,
     min(t.ts) AS first_ts,
     max(t.ts) AS last_ts,
     collect(DISTINCT sender.acc_id) AS senders
WHERE inbound_count >= $min_senders
MATCH (mule)-[out:TRANSFERRED]->(dest:Account)
WITH mule, inbound_count, inbound_total, first_ts, last_ts, senders,
     dest, sum(out.amount) AS outbound_total
WHERE outbound_total >= inbound_total * $payout_ratio
RETURN mule.acc_id AS mule_account,
       mule.owner_name AS mule_owner,
       inbound_count,
       inbound_total,
       senders,
       (last_ts - first_ts) / 86400.0 AS window_days,
       dest.acc_id AS destination,
       dest.owner_name AS destination_owner,
       dest.country AS destination_country,
       dest.status AS destination_status,
       outbound_total
ORDER BY inbound_total DESC
LIMIT $limit
"""

# Q3 -- risk propagation. How close is this account to a FLAGGED one, and
# through what? The traversal deliberately crosses Device and IPAddress nodes,
# so "connected via a shared phone" counts as proximity, not just money.
DETECT_FLAGGED_PROXIMITY = """
MATCH path = (target:Account {acc_id: $acc_id})-[*1..2]-(flagged:Account {status: 'FLAGGED'})
WHERE target <> flagged
WITH flagged, path, length(path) AS hops
ORDER BY hops ASC
RETURN flagged.acc_id AS flagged_account,
       flagged.owner_name AS flagged_owner,
       min(hops) AS distance,
       head(collect([n IN nodes(path) |
            coalesce(n.acc_id, n.device_id, n.ip_address, n.cust_id, n.card_number)])) AS via
LIMIT $limit
"""

# Q4 -- money-flow path tracing. Bounded at 5 hops and ordered by length: the
# portable equivalent of shortestPath(), without depending on it. Written as a
# UNION ALL of explicit chains -- see the module docstring on why variable-length
# patterns cannot be used past three hops here.
TRACE_PATH = """
MATCH (a:Account {acc_id: $source})-[r1:TRANSFERRED]->(b:Account {acc_id: $destination})
RETURN [a.acc_id, b.acc_id] AS chain,
       [a.owner_name, b.owner_name] AS owners,
       [a.status, b.status] AS statuses,
       [r1.amount] AS amounts,
       [r1.timestamp] AS timestamps,
       [r1.txn_id] AS txn_ids,
       1 AS hops
UNION ALL
MATCH (a:Account {acc_id: $source})-[r1:TRANSFERRED]->(n1:Account)
     -[r2:TRANSFERRED]->(b:Account {acc_id: $destination})
RETURN [a.acc_id, n1.acc_id, b.acc_id] AS chain,
       [a.owner_name, n1.owner_name, b.owner_name] AS owners,
       [a.status, n1.status, b.status] AS statuses,
       [r1.amount, r2.amount] AS amounts,
       [r1.timestamp, r2.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id] AS txn_ids,
       2 AS hops
UNION ALL
MATCH (a:Account {acc_id: $source})-[r1:TRANSFERRED]->(n1:Account)
     -[r2:TRANSFERRED]->(n2:Account)-[r3:TRANSFERRED]->(b:Account {acc_id: $destination})
RETURN [a.acc_id, n1.acc_id, n2.acc_id, b.acc_id] AS chain,
       [a.owner_name, n1.owner_name, n2.owner_name, b.owner_name] AS owners,
       [a.status, n1.status, n2.status, b.status] AS statuses,
       [r1.amount, r2.amount, r3.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id] AS txn_ids,
       3 AS hops
UNION ALL
MATCH (a:Account {acc_id: $source})-[r1:TRANSFERRED]->(n1:Account)
     -[r2:TRANSFERRED]->(n2:Account)-[r3:TRANSFERRED]->(n3:Account)
     -[r4:TRANSFERRED]->(b:Account {acc_id: $destination})
RETURN [a.acc_id, n1.acc_id, n2.acc_id, n3.acc_id, b.acc_id] AS chain,
       [a.owner_name, n1.owner_name, n2.owner_name, n3.owner_name, b.owner_name] AS owners,
       [a.status, n1.status, n2.status, n3.status, b.status] AS statuses,
       [r1.amount, r2.amount, r3.amount, r4.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp, r4.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id, r4.txn_id] AS txn_ids,
       4 AS hops
UNION ALL
MATCH (a:Account {acc_id: $source})-[r1:TRANSFERRED]->(n1:Account)
     -[r2:TRANSFERRED]->(n2:Account)-[r3:TRANSFERRED]->(n3:Account)
     -[r4:TRANSFERRED]->(n4:Account)-[r5:TRANSFERRED]->(b:Account {acc_id: $destination})
RETURN [a.acc_id, n1.acc_id, n2.acc_id, n3.acc_id, n4.acc_id, b.acc_id] AS chain,
       [a.owner_name, n1.owner_name, n2.owner_name, n3.owner_name, n4.owner_name,
        b.owner_name] AS owners,
       [a.status, n1.status, n2.status, n3.status, n4.status, b.status] AS statuses,
       [r1.amount, r2.amount, r3.amount, r4.amount, r5.amount] AS amounts,
       [r1.timestamp, r2.timestamp, r3.timestamp, r4.timestamp, r5.timestamp] AS timestamps,
       [r1.txn_id, r2.txn_id, r3.txn_id, r4.txn_id, r5.txn_id] AS txn_ids,
       5 AS hops
ORDER BY hops ASC
LIMIT $limit
"""

# ---------------------------------------------------------------------------
# Risk-score factors -- one query per factor, so the score stays explainable.
# ---------------------------------------------------------------------------
RISK_IN_CYCLE = """
MATCH (a:Account {acc_id: $acc_id})-[:TRANSFERRED]->(n1:Account)
     -[:TRANSFERRED]->(n2:Account)-[:TRANSFERRED]->(a)
RETURN [a.acc_id, n1.acc_id, n2.acc_id, a.acc_id] AS chain, 3 AS hops
UNION ALL
MATCH (a:Account {acc_id: $acc_id})-[:TRANSFERRED]->(n1:Account)
     -[:TRANSFERRED]->(n2:Account)-[:TRANSFERRED]->(n3:Account)
     -[:TRANSFERRED]->(a)
RETURN [a.acc_id, n1.acc_id, n2.acc_id, n3.acc_id, a.acc_id] AS chain, 4 AS hops
UNION ALL
MATCH (a:Account {acc_id: $acc_id})-[:TRANSFERRED]->(n1:Account)
     -[:TRANSFERRED]->(n2:Account)-[:TRANSFERRED]->(n3:Account)
     -[:TRANSFERRED]->(n4:Account)-[:TRANSFERRED]->(a)
RETURN [a.acc_id, n1.acc_id, n2.acc_id, n3.acc_id, n4.acc_id, a.acc_id] AS chain, 5 AS hops
ORDER BY hops ASC
LIMIT 1
"""

# Mirrors DETECT_SHARED_INFRASTRUCTURE exactly: a peer is an account that
# shares BOTH a device and an IP with this one. Sharing only a device is
# unremarkable when 50 accounts sign in from 15 devices; sharing the whole
# fingerprint is not.
RISK_SHARED_INFRA = """
MATCH (a:Account {acc_id: $acc_id})-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(other:Account)
MATCH (a)-[:LOGGED_IN_FROM]->(i:IPAddress)<-[:LOGGED_IN_FROM]-(other)
WHERE other.acc_id <> a.acc_id
RETURN count(DISTINCT other.acc_id) AS both_peers,
       collect(DISTINCT other.acc_id) AS peer_accounts,
       collect(DISTINCT d.device_id) AS shared_devices,
       collect(DISTINCT i.ip_address) AS shared_ips
"""

RISK_FAN_IN = """
MATCH (sender:Account)-[t:TRANSFERRED]->(a:Account {acc_id: $acc_id})
RETURN count(DISTINCT sender.acc_id) AS sender_count,
       sum(t.amount) AS inbound_total,
       min(t.ts) AS first_ts,
       max(t.ts) AS last_ts
"""

RISK_FLAGGED_NEARBY = """
MATCH path = (a:Account {acc_id: $acc_id})-[*1..2]-(f:Account {status: 'FLAGGED'})
WHERE a <> f
RETURN count(DISTINCT f.acc_id) AS flagged_count,
       collect(DISTINCT f.acc_id)[0..5] AS examples
"""

RISK_VPN_LOGIN = """
MATCH (a:Account {acc_id: $acc_id})-[:LOGGED_IN_FROM]->(i:IPAddress)
WHERE i.is_vpn = true
RETURN collect(DISTINCT i.ip_address) AS vpn_ips
"""

RISK_PERSIST = """
MATCH (a:Account {acc_id: $acc_id})
SET a.risk_score = $risk_score,
    a.status = $status
RETURN a.acc_id AS acc_id, a.risk_score AS risk_score, a.status AS status
"""

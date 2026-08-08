"""Load SentinelGraph's demo dataset into CognoDB.

    python seed/seed_database.py            # create schema + data (idempotent)
    python seed/seed_database.py --reset    # wipe everything first
    python seed/seed_database.py --dry-run  # print the plan, touch nothing

Everything is written with MERGE against unique keys, so re-running the script
converges on the same graph rather than duplicating it. Every write is
parameterised and batched with UNWIND -- 50 accounts arrive in one round trip,
not 50 -- because the free c0 instance is small and latency-bound.

The dataset is generated from a fixed random seed, so two people running this
script get byte-identical graphs and the screenshots in the README always
match what you see.

Volumes:  50 accounts · 25 customers · 15 devices · 20 IPs · 30 cards · 125 transfers
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make `backend/` importable so the schema DDL and the risk weights live in
# exactly one place and can never drift from the running application.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402
from neo4j.exceptions import AuthError, ServiceUnavailable  # noqa: E402

from queries import cypher  # noqa: E402
from services import risk_service as risk  # noqa: E402

load_dotenv(ROOT / "backend" / ".env")
load_dotenv(ROOT / ".env")

RNG = random.Random(20260807)
BASE_DATE = datetime(2026, 6, 1, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Aarav", "Priya", "Marcus", "Elena", "Tobias", "Nadia", "Ivan", "Chiara",
    "Kwame", "Sofia", "Hiro", "Lena", "Omar", "Ines", "Viktor", "Amara",
    "Dmitri", "Yara", "Felix", "Rania", "Noor", "Lars", "Mei", "Diego", "Anja",
    "Sergei", "Fatima", "Bruno", "Katya", "Idris", "Camila", "Otto", "Zara",
    "Rafael", "Nina", "Pavel", "Leila", "Hugo", "Sanaa", "Emil", "Tara",
    "Gustav", "Ayesha", "Milos", "Freya", "Jonas", "Aisha", "Karim", "Ilse",
    "Ravi",
]
LAST_NAMES = [
    "Mehta", "Kovac", "Lindqvist", "Okafor", "Duarte", "Fischer", "Volkov",
    "Rossi", "Haddad", "Nakamura", "Bauer", "Silva", "Moreau", "Petrov",
    "Andersen", "Reyes", "Novak", "Kaur", "Weber", "Dimitrov", "Salazar",
    "Berg", "Farah", "Kruger", "Iyer",
]
COUNTRIES = ["US", "GB", "DE", "IN", "SG", "AE", "NL", "BR", "ZA", "PL"]
DEVICE_TYPES = ["mobile", "desktop", "tablet"]
OPERATING_SYSTEMS = ["Android 15", "iOS 19", "Windows 11", "macOS 16", "Ubuntu 26.04"]
ISSUERS = ["Visa", "Mastercard", "Amex", "Discover"]

# --- Scenario account ids --------------------------------------------------
RING = ["ACC_1101", "ACC_1102", "ACC_1103", "ACC_1104"]                    # Scenario 1
SHARED = [f"ACC_120{i}" for i in range(1, 7)]                              # Scenario 2
FEEDERS = [f"ACC_13{i:02d}" for i in range(1, 11)]                         # Scenario 3
MULE = "ACC_1350"
OFFSHORE = "ACC_1399"
BACKGROUND = [f"ACC_10{i:02d}" for i in range(1, 29)]                      # 28 ordinary accounts

ALL_ACCOUNT_IDS = [*BACKGROUND, *RING, *SHARED, *FEEDERS, MULE, OFFSHORE]  # 50

SHARED_IP = "192.168.1.100"
SHARED_DEVICE = "DEV_8899"
OPERATOR_IP = "203.0.113.77"
OPERATOR_DEVICE = "DEV_8898"

# Accounts a human investigator has already confirmed as fraudulent. The seeded
# risk scores are computed against this reference set; the API's
# POST /detect/risk-score then recomputes from whatever is in the graph.
KNOWN_FRAUD = {*RING, OFFSHORE}


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------
def iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


def build_dataset() -> dict:
    customers = [
        {
            "cust_id": f"CUST_{i + 1:03d}",
            "name": f"{FIRST_NAMES[i]} {LAST_NAMES[i % len(LAST_NAMES)]}",
            "country": RNG.choice(COUNTRIES),
            "risk_rating": RNG.choices(["LOW", "MEDIUM", "HIGH"], weights=[6, 3, 1])[0],
        }
        for i in range(25)
    ]

    # 13 ordinary devices + the two devices the fraud scenarios revolve around.
    devices = [
        {
            "device_id": f"DEV_{8001 + i}",
            "device_type": RNG.choice(DEVICE_TYPES),
            "os": RNG.choice(OPERATING_SYSTEMS),
            "fingerprint": f"fp_{RNG.getrandbits(48):012x}",
        }
        for i in range(13)
    ]
    devices += [
        {
            "device_id": OPERATOR_DEVICE,
            "device_type": "desktop",
            "os": "Windows 11",
            "fingerprint": "fp_0000deadbeef",
        },
        {
            "device_id": SHARED_DEVICE,
            "device_type": "mobile",
            "os": "Android 15",
            "fingerprint": "fp_0000cafebabe",
        },
    ]

    # 18 ordinary addresses + the two the scenarios share.
    ips = [
        {
            "ip_address": f"{RNG.randint(11, 210)}.{RNG.randint(0, 255)}."
            f"{RNG.randint(0, 255)}.{RNG.randint(1, 254)}",
            "country": RNG.choice(COUNTRIES),
            "is_vpn": RNG.random() < 0.2,
        }
        for _ in range(18)
    ]
    ips += [
        {"ip_address": SHARED_IP, "country": "RU", "is_vpn": True},
        {"ip_address": OPERATOR_IP, "country": "PA", "is_vpn": True},
    ]

    cards = [
        {
            "card_number": f"****-****-****-{RNG.randint(1000, 9999)}",
            "issuer": RNG.choice(ISSUERS),
            "expiry": f"{RNG.randint(1, 12):02d}/{RNG.randint(27, 31)}",
        }
        for _ in range(30)
    ]
    # Uniqueness is a constraint in the database; enforce it here too.
    seen: set[str] = set()
    unique_cards = []
    for card in cards:
        while card["card_number"] in seen:
            card["card_number"] = f"****-****-****-{RNG.randint(1000, 9999)}"
        seen.add(card["card_number"])
        unique_cards.append(card)
    cards = unique_cards

    # --- Accounts ----------------------------------------------------------
    accounts = []
    for index, acc_id in enumerate(ALL_ACCOUNT_IDS):
        # Denormalised onto the Account so the graph view can label a node
        # without a join. It must name the same person the OWNS edge points at,
        # so both come from the same customer -- see `owns` below.
        owner = customers[index % len(customers)]
        accounts.append(
            {
                "acc_id": acc_id,
                "owner_name": owner["name"],
                "balance": round(RNG.uniform(500, 90_000), 2),
                "country": "KY" if acc_id == OFFSHORE else RNG.choice(COUNTRIES),
                "created_at": (BASE_DATE - timedelta(days=RNG.randint(30, 900)))
                .date()
                .isoformat(),
                # Placeholders -- both are computed below from the finished graph.
                "risk_score": 0,
                "status": "SAFE",
            }
        )

    # Same `i % len(customers)` mapping the owner_name above was taken from.
    owns = [
        {"cust_id": customers[i % len(customers)]["cust_id"], "acc_id": acc["acc_id"],
         "since": acc["created_at"]}
        for i, acc in enumerate(accounts)
    ]

    # --- Device / IP assignment -------------------------------------------
    # Ordinary accounts get device i mod 13 and IP (7i+3) mod 18. Two accounts
    # collide on BOTH only if i == j (mod 234), and there are only 50 accounts
    # -- so the shared-infrastructure detector produces no false positives and
    # every hit it reports is a scenario we planted on purpose.
    used_device, logged_in_from = [], []
    for index, acc_id in enumerate(ALL_ACCOUNT_IDS):
        if acc_id in SHARED:
            device_id, ip_address = SHARED_DEVICE, SHARED_IP
        elif acc_id in (MULE, OFFSHORE, RING[0]):
            device_id, ip_address = OPERATOR_DEVICE, OPERATOR_IP
        else:
            device_id = devices[index % 13]["device_id"]
            ip_address = ips[(index * 7 + 3) % 18]["ip_address"]

        first_seen = BASE_DATE - timedelta(days=RNG.randint(20, 200))
        used_device.append(
            {"acc_id": acc_id, "device_id": device_id,
             "first_seen": iso(first_seen), "last_seen": iso(BASE_DATE)}
        )
        logged_in_from.append(
            {"acc_id": acc_id, "ip_address": ip_address,
             "first_seen": iso(first_seen), "last_seen": iso(BASE_DATE),
             "login_count": RNG.randint(3, 240)}
        )

    linked_card = [
        {"acc_id": ALL_ACCOUNT_IDS[i % len(ALL_ACCOUNT_IDS)],
         "card_number": card["card_number"],
         "linked_at": iso(BASE_DATE - timedelta(days=RNG.randint(10, 500)))}
        for i, card in enumerate(cards)
    ]

    # --- Transfers ---------------------------------------------------------
    transfers: list[dict] = []
    counter = {"n": 0}

    def transfer(source: str, target: str, amount: float, moment: datetime) -> None:
        counter["n"] += 1
        transfers.append(
            {
                "txn_id": f"TXN_{counter['n']:05d}",
                "source": source,
                "target": target,
                "amount": round(amount, 2),
                "currency": "USD",
                "timestamp": iso(moment),
                "ts": int(moment.timestamp()),
            }
        )

    # Scenario 1 -- a closed loop. Each hop keeps a little back, which is what
    # makes it look like trade rather than a mistake.
    ring_start = BASE_DATE + timedelta(days=3)
    ring_amounts = [50_000, 49_200, 48_500, 47_900]
    for hop, amount in enumerate(ring_amounts):
        transfer(
            RING[hop],
            RING[(hop + 1) % len(RING)],
            amount,
            ring_start + timedelta(days=hop * 2, hours=RNG.randint(0, 20)),
        )

    # Scenario 3 -- ten small deposits into one account, then a single payout.
    funnel_start = BASE_DATE + timedelta(days=12)
    inbound_total = 0.0
    for offset, feeder in enumerate(FEEDERS):
        amount = round(RNG.uniform(2_000, 9_500), 2)
        inbound_total += amount
        transfer(feeder, MULE, amount, funnel_start + timedelta(hours=offset * 6 + RNG.randint(0, 4)))
    transfer(MULE, OFFSHORE, round(inbound_total * 0.95, 2), funnel_start + timedelta(days=3, hours=2))

    # The bridge that makes the graph interesting: the offshore account pays a
    # ring member. Neither pattern looks connected on its own; the graph shows
    # they are one operation.
    transfer(OFFSHORE, RING[0], 41_000, funnel_start + timedelta(days=4))

    # Ordinary traffic -- everyday payments among the background accounts, plus
    # a little legitimate activity from the shared-device cluster so it is not
    # trivially separable.
    #
    # Direction is fixed by a random ranking of the accounts, and money only
    # ever flows from a lower rank to a higher one. That makes the background
    # a DAG, so the ONLY cycles in the finished graph are the ones we planted.
    # Without this, ~110 random edges over 34 accounts produce dozens of
    # accidental 3-to-5-hop loops and the ring detector drowns in noise. The
    # ranking is a shuffle rather than account-id order, so the direction of
    # any individual payment still looks arbitrary.
    noise_pool = BACKGROUND + SHARED
    ranking = noise_pool[:]
    RNG.shuffle(ranking)
    rank = {acc_id: position for position, acc_id in enumerate(ranking)}

    for _ in range(110):
        source, target = RNG.sample(noise_pool, 2)
        if rank[source] > rank[target]:
            source, target = target, source
        transfer(
            source,
            target,
            RNG.uniform(50, 5_000),
            BASE_DATE + timedelta(days=RNG.randint(0, 60), hours=RNG.randint(0, 23)),
        )

    return {
        "customers": customers,
        "accounts": accounts,
        "devices": devices,
        "ips": ips,
        "cards": cards,
        "owns": owns,
        "used_device": used_device,
        "logged_in_from": logged_in_from,
        "linked_card": linked_card,
        "transfers": transfers,
    }


# ---------------------------------------------------------------------------
# Risk scoring, applied offline to the generated graph
#
# This mirrors backend/services/risk_service.py exactly and imports its weights,
# so the numbers the seed writes and the numbers POST /detect/risk-score
# computes can never disagree.
# ---------------------------------------------------------------------------
def score_accounts(data: dict) -> None:
    accounts = {a["acc_id"]: a for a in data["accounts"]}

    device_of = {r["acc_id"]: r["device_id"] for r in data["used_device"]}
    ip_of = {r["acc_id"]: r["ip_address"] for r in data["logged_in_from"]}
    vpn_ips = {ip["ip_address"] for ip in data["ips"] if ip["is_vpn"]}

    # Undirected adjacency over every relationship type -- proximity through a
    # shared phone counts, not only proximity through money.
    adjacency: dict[str, set[str]] = defaultdict(set)

    def link(a: str, b: str) -> None:
        adjacency[a].add(b)
        adjacency[b].add(a)

    for row in data["transfers"]:
        link(row["source"], row["target"])
    for row in data["used_device"]:
        link(row["acc_id"], row["device_id"])
    for row in data["logged_in_from"]:
        link(row["acc_id"], row["ip_address"])

    def within_two_hops(start: str) -> set[str]:
        seen, frontier = {start}, deque([(start, 0)])
        reached: set[str] = set()
        while frontier:
            node, depth = frontier.popleft()
            if depth == 2:
                continue
            for neighbour in adjacency[node]:
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                if neighbour in accounts:
                    reached.add(neighbour)
                frontier.append((neighbour, depth + 1))
        return reached

    # Cycle membership over TRANSFERRED edges only, 3 to 5 hops.
    outgoing: dict[str, set[str]] = defaultdict(set)
    for row in data["transfers"]:
        outgoing[row["source"]].add(row["target"])

    def in_cycle(start: str) -> bool:
        stack = [(start, 0)]
        while stack:
            node, depth = stack.pop()
            if depth >= 5:
                continue
            for nxt in outgoing[node]:
                if nxt == start and 3 <= depth + 1 <= 5:
                    return True
                if depth + 1 < 5:
                    stack.append((nxt, depth + 1))
        return False

    inbound: dict[str, list[dict]] = defaultdict(list)
    for row in data["transfers"]:
        inbound[row["target"]].append(row)

    for acc_id, account in accounts.items():
        score = risk.BASE_SCORE

        if in_cycle(acc_id):
            score += risk.POINTS_IN_CYCLE

        peers = [
            other
            for other in accounts
            if other != acc_id
            and device_of.get(other) == device_of.get(acc_id)
            and ip_of.get(other) == ip_of.get(acc_id)
        ]
        if len(peers) >= risk.SHARED_PEER_THRESHOLD:
            score += risk.POINTS_SHARED_BOTH
        elif peers:
            score += risk.POINTS_SHARED_ONE

        incoming = inbound.get(acc_id, [])
        senders = {row["source"] for row in incoming}
        if len(senders) >= risk.FAN_IN_SENDER_THRESHOLD:
            span_days = (max(r["ts"] for r in incoming) - min(r["ts"] for r in incoming)) / 86400
            if span_days <= risk.FAN_IN_WINDOW_DAYS:
                score += risk.POINTS_FAN_IN

        nearby_fraud = len(within_two_hops(acc_id) & KNOWN_FRAUD - {acc_id})
        score += min(
            nearby_fraud * risk.POINTS_PER_FLAGGED_NEIGHBOUR,
            risk.MAX_FLAGGED_NEIGHBOUR_POINTS,
        )

        if ip_of.get(acc_id) in vpn_ips:
            score += risk.POINTS_VPN

        account["risk_score"] = max(0, min(100, score))
        account["status"] = risk.status_for(account["risk_score"])


# ---------------------------------------------------------------------------
# Write queries -- batched, parameterised, MERGE-based
# ---------------------------------------------------------------------------
WRITES: list[tuple[str, str, str]] = [
    (
        "customers",
        "Customer",
        """
        UNWIND $rows AS row
        MERGE (c:Customer {cust_id: row.cust_id})
        SET c.name = row.name, c.country = row.country, c.risk_rating = row.risk_rating
        """,
    ),
    (
        "accounts",
        "Account",
        """
        UNWIND $rows AS row
        MERGE (a:Account {acc_id: row.acc_id})
        SET a.owner_name = row.owner_name, a.balance = row.balance,
            a.risk_score = row.risk_score, a.status = row.status,
            a.country = row.country, a.created_at = row.created_at
        """,
    ),
    (
        "devices",
        "Device",
        """
        UNWIND $rows AS row
        MERGE (d:Device {device_id: row.device_id})
        SET d.device_type = row.device_type, d.os = row.os, d.fingerprint = row.fingerprint
        """,
    ),
    (
        "ips",
        "IPAddress",
        """
        UNWIND $rows AS row
        MERGE (i:IPAddress {ip_address: row.ip_address})
        SET i.country = row.country, i.is_vpn = row.is_vpn
        """,
    ),
    (
        "cards",
        "CreditCard",
        """
        UNWIND $rows AS row
        MERGE (cc:CreditCard {card_number: row.card_number})
        SET cc.issuer = row.issuer, cc.expiry = row.expiry
        """,
    ),
    (
        "owns",
        "OWNS",
        """
        UNWIND $rows AS row
        MATCH (c:Customer {cust_id: row.cust_id})
        MATCH (a:Account {acc_id: row.acc_id})
        MERGE (c)-[r:OWNS]->(a)
        SET r.since = row.since
        """,
    ),
    (
        "used_device",
        "USED_DEVICE",
        """
        UNWIND $rows AS row
        MATCH (a:Account {acc_id: row.acc_id})
        MATCH (d:Device {device_id: row.device_id})
        MERGE (a)-[r:USED_DEVICE]->(d)
        SET r.first_seen = row.first_seen, r.last_seen = row.last_seen
        """,
    ),
    (
        "logged_in_from",
        "LOGGED_IN_FROM",
        """
        UNWIND $rows AS row
        MATCH (a:Account {acc_id: row.acc_id})
        MATCH (i:IPAddress {ip_address: row.ip_address})
        MERGE (a)-[r:LOGGED_IN_FROM]->(i)
        SET r.first_seen = row.first_seen, r.last_seen = row.last_seen,
            r.login_count = row.login_count
        """,
    ),
    (
        "linked_card",
        "LINKED_CARD",
        """
        UNWIND $rows AS row
        MATCH (a:Account {acc_id: row.acc_id})
        MATCH (cc:CreditCard {card_number: row.card_number})
        MERGE (a)-[r:LINKED_CARD]->(cc)
        SET r.linked_at = row.linked_at
        """,
    ),
    (
        "transfers",
        "TRANSFERRED",
        """
        UNWIND $rows AS row
        MATCH (src:Account {acc_id: row.source})
        MATCH (dst:Account {acc_id: row.target})
        MERGE (src)-[t:TRANSFERRED {txn_id: row.txn_id}]->(dst)
        SET t.amount = row.amount, t.currency = row.currency,
            t.timestamp = row.timestamp, t.ts = row.ts
        """,
    ),
]

BATCH_SIZE = 200


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def connect():
    uri = os.getenv("COGNODB_URI", "")
    user = os.getenv("COGNODB_USER", "cognodb")
    password = os.getenv("COGNODB_PASSWORD", "")

    missing = [
        name
        for name, value in (
            ("COGNODB_URI", uri),
            ("COGNODB_USER", user),
            ("COGNODB_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        sys.exit(
            f"\n  Missing environment variable(s): {', '.join(missing)}\n"
            f"  Copy backend/.env.example to backend/.env and fill in the values\n"
            f"  from your CognoDB console, then run this script again.\n"
        )

    return GraphDatabase.driver(uri, auth=(user, password), max_connection_pool_size=5)


def apply_schema(session, dry_run: bool) -> None:
    print("\nSchema")
    for statement in cypher.CONSTRAINTS + cypher.INDEXES:
        name = statement.split()[2]
        if dry_run:
            print(f"  - would create {name}")
            continue
        try:
            session.run(statement)
            print(f"  [ok] {name}")
        except Exception as exc:  # noqa: BLE001
            # Some openCypher engines reject named constraints or IF NOT EXISTS.
            # The dataset is still valid without them, so warn and continue.
            print(f"  [!!] {name}: {type(exc).__name__} -- continuing without it")


def load(session, data: dict, dry_run: bool) -> None:
    print("\nData")
    for key, label, statement in WRITES:
        rows = data[key]
        if dry_run:
            print(f"  - would write {len(rows):>4} {label}")
            continue
        for start in range(0, len(rows), BATCH_SIZE):
            session.run(statement, {"rows": rows[start : start + BATCH_SIZE]})
        print(f"  [ok] {len(rows):>4} {label}")


def reset(session, dry_run: bool) -> None:
    print("\nReset")
    if dry_run:
        print("  - would delete every node and relationship")
        return
    session.run("MATCH (n) DETACH DELETE n")
    print("  [ok] graph cleared")


def report(data: dict) -> None:
    by_status: dict[str, int] = defaultdict(int)
    for account in data["accounts"]:
        by_status[account["status"]] += 1

    print("\nPlanted scenarios")
    print(f"  1. Laundering ring     {' -> '.join(RING)} -> {RING[0]}")
    print(f"  2. Shared device/IP    {', '.join(SHARED)} on {SHARED_DEVICE} / {SHARED_IP}")
    print(f"  3. Mule funnel         {len(FEEDERS)} feeders -> {MULE} -> {OFFSHORE}")
    print(f"  +  Bridge              {OFFSHORE} -> {RING[0]} links scenarios 1 and 3")

    print("\nComputed risk")
    for status in ("FLAGGED", "SUSPICIOUS", "SAFE"):
        print(f"  {status:<12} {by_status.get(status, 0):>3} accounts")

    highest = sorted(data["accounts"], key=lambda a: -a["risk_score"])[:6]
    print("\n  Highest scoring:")
    for account in highest:
        print(f"    {account['acc_id']:<10} {account['risk_score']:>3}/100  {account['status']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the SentinelGraph demo dataset.")
    parser.add_argument("--reset", action="store_true", help="Delete all existing data first.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing.")
    args = parser.parse_args()

    # Windows consoles default to cp1252; make sure output never dies on a glyph.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    print("SentinelGraph seed")
    print("=" * 58)

    data = build_dataset()
    score_accounts(data)

    if args.dry_run:
        apply_schema(None, True)
        if args.reset:
            reset(None, True)
        load(None, data, True)
        report(data)
        print("\nDry run complete -- nothing was written.\n")
        return 0

    driver = connect()
    try:
        driver.verify_connectivity()
        print("Connected to CognoDB.")
    except AuthError:
        print("\n  Authentication failed. Check COGNODB_USER and COGNODB_PASSWORD.\n")
        return 1
    except (ServiceUnavailable, OSError) as exc:
        print(
            f"\n  Could not reach the database ({type(exc).__name__}).\n"
            f"  Check COGNODB_URI and that the instance is running.\n"
        )
        return 1

    try:
        with driver.session() as session:
            if args.reset:
                reset(session, False)
            apply_schema(session, False)
            load(session, data, False)

            counts = session.run(
                "MATCH (n) WITH count(n) AS nodes "
                "MATCH ()-[r]->() RETURN nodes, count(r) AS relationships"
            ).single()

        report(data)
        print(
            f"\nGraph now holds {counts['nodes']} nodes "
            f"and {counts['relationships']} relationships."
        )
        print("Start the API with:  cd backend && uvicorn main:app --reload\n")
    finally:
        driver.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

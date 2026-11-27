"""Create the schema and load synthetic STR data.

Usage:  python db/seed.py "postgresql://doadmin:...@host:25060/defaultdb?sslmode=require"

Volume: Coastal Stays has 2,000 listings x 365 nights (~730k rows). Nights run
from 305 days ago to 60 days ahead, so "next 30 days" is on-the-books data.

Planted signal: in markets with an upcoming event, a few dozen Coastal Stays
listings are priced well under their comp set yet are filling fast. The agent
should find these; the strongest ten are the "push new prices" set.
"""
import io
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg

SEED = 7
TODAY = date.today()
START = TODAY - timedelta(days=305)
NIGHTS = 365

MARKETS = {
    "Gatlinburg, TN": 210,
    "Myrtle Beach, SC": 180,
    "Destin, FL": 240,
    "Scottsdale, AZ": 260,
    "South Lake Tahoe, CA": 300,
}
CUSTOMERS = [("Coastal Stays", "enterprise", 2000), ("Pinecone Rentals", "pro", 150), ("Desert Nest", "starter", 40)]
EVENTS = [  # (market, start offset from today, length, name, lift)
    ("Gatlinburg, TN", 9, 4, "Smoky Mountain Winterfest weekend", 1.45),
    ("South Lake Tahoe, CA", 14, 5, "Holiday ski opening week", 1.60),
    ("Scottsdale, AZ", 20, 3, "Desert arts & food festival", 1.30),
]


def main(dsn: str) -> None:
    rnd = random.Random(SEED)
    listings, rates = [], io.StringIO()
    events = {(m, TODAY + timedelta(days=o + i)): lift for m, o, n, _, lift in EVENTS for i in range(n)}
    event_markets = {e[0] for e in EVENTS}

    for cust_id, (name, _, count) in enumerate(CUSTOMERS, start=1):
        prefix = "".join(w[0] for w in name.split()).upper()
        for n in range(count):
            lid = f"{prefix}-{n:05d}"
            market = rnd.choice(list(MARKETS))
            beds = rnd.choice([1, 2, 2, 3, 3, 4, 5])
            comp_base = MARKETS[market] * (0.6 + 0.25 * beds)
            # Planted underpricing: ~2.5% of Coastal Stays listings in event markets.
            underpriced = cust_id == 1 and market in event_markets and rnd.random() < 0.06
            factor = rnd.uniform(0.62, 0.78) if underpriced else rnd.uniform(0.92, 1.10)
            base = round(comp_base * factor, 2)
            listings.append((lid, cust_id, market, beds, base, round(base * 0.7, 2)))

            for d in range(NIGHTS):
                night = START + timedelta(days=d)
                season = 1.0 + 0.18 * (night.month in (6, 7, 8, 12)) + 0.10 * (night.weekday() >= 4)
                lift = events.get((market, night), 1.0)
                comp_price = comp_base * season * lift * rnd.uniform(0.95, 1.05)
                price = base * season * rnd.uniform(0.97, 1.03)  # base pricing ignores events
                comp_occ = min(0.97, 0.55 * season * lift * rnd.uniform(0.9, 1.1))
                cheapness = comp_price / price
                p_book = min(0.98, comp_occ * cheapness ** 1.5)
                if night > TODAY:  # future nights: only partially on the books yet
                    p_book *= max(0.25, 1 - (night - TODAY).days / 75)
                rates.write(f"{lid}\t{night}\t{price:.2f}\t{comp_price:.2f}\t{'t' if rnd.random() < p_book else 'f'}\t{comp_occ:.3f}\n")

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(Path(__file__).with_name("schema.sql").read_text())
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO customers (name, plan) VALUES (%s, %s)", [(c[0], c[1]) for c in CUSTOMERS])
            cur.executemany("INSERT INTO listings VALUES (%s,%s,%s,%s,%s,%s)", listings)
            cur.executemany("INSERT INTO market_events VALUES (%s,%s,%s,%s,%s)",
                            [(m, TODAY + timedelta(days=o), TODAY + timedelta(days=o + n - 1), nm, lift) for m, o, n, nm, lift in EVENTS])
            rates.seek(0)
            with cur.copy("COPY nightly_rates FROM STDIN") as copy:
                while chunk := rates.read(1 << 20):
                    copy.write(chunk)
        conn.execute("ANALYZE")
        n = conn.execute("SELECT count(*) FROM nightly_rates").fetchone()[0]
        print(f"loaded {len(listings)} listings, {n} listing-nights")


if __name__ == "__main__":
    main(sys.argv[1])

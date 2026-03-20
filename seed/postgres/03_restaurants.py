#!/usr/bin/env python3
"""
03_restaurants.py — seed 200 restaurants into PostgreSQL.

Idempotent: ON CONFLICT DO NOTHING.
Cuisines: Saudi, Egyptian, Lebanese, Fast Food, Indian, Chinese.
commission_rate matches silver.restaurants DDL (cross-audit A-14).
"""

import os
import random
import psycopg2
from faker import Faker

CUISINES = ["Saudi", "Egyptian", "Lebanese", "Fast Food", "Indian", "Chinese"]
CITIES = ["Riyadh", "Jeddah", "Dammam", "Khobar", "Mecca"]
TOTAL_RESTAURANTS = 200
RANDOM_SEED = 42

DSN = os.getenv(
    "PG_DSN",
    "postgresql://orderflow:orderflow_pg_pass@localhost:30432/orderflow"
)


def main():
    fake = Faker("en_US")
    fake.seed_instance(RANDOM_SEED)
    random.seed(RANDOM_SEED)

    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    print(f"Seeding {TOTAL_RESTAURANTS} restaurants...")

    rows = []
    for restaurant_id in range(1, TOTAL_RESTAURANTS + 1):
        rows.append((
            restaurant_id,
            f"{fake.last_name()} {random.choice(CUISINES)} Restaurant",
            random.choice(CUISINES),
            random.choice(CITIES),
            round(random.uniform(2.5, 5.0), 2),       # rating
            round(random.uniform(0.05, 0.25), 4),      # commission_rate
        ))

    cur.executemany(
        """
        INSERT INTO restaurants (id, name, cuisine, city, rating, commission_rate)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        rows,
    )

    cur.execute("SELECT setval('restaurants_id_seq', (SELECT MAX(id) FROM restaurants))")

    conn.commit()
    cur.close()
    conn.close()

    print(f"Done — {TOTAL_RESTAURANTS} restaurants seeded")


if __name__ == "__main__":
    main()

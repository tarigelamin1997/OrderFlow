#!/usr/bin/env python3
"""
05_orders.py — seed 50,000 orders into PostgreSQL.

Idempotent: ON CONFLICT DO NOTHING.
Date range: 2023-01-01 → 2025-01-01.
12% cancellation rate (plan requirement).
"""

import os
import random
from datetime import datetime, timedelta
import psycopg2

TOTAL_ORDERS = 50_000
CANCELLATION_RATE = 0.12
START_DATE = datetime(2023, 1, 1)
END_DATE = datetime(2025, 1, 1)
RANDOM_SEED = 42

TOTAL_USERS = 5_000
TOTAL_RESTAURANTS = 200
TOTAL_DRIVERS = 300

STATUSES = ["pending", "accepted", "picked_up", "delivered", "cancelled"]
# Weights: 12% cancelled, rest distributed among delivery lifecycle
STATUS_WEIGHTS = [0.05, 0.08, 0.10, 0.65, 0.12]

DSN = os.getenv(
    "PG_DSN",
    "postgresql://orderflow:orderflow_pg_pass@localhost:30432/orderflow"
)

DATE_RANGE_SECONDS = int((END_DATE - START_DATE).total_seconds())


def random_datetime() -> datetime:
    offset = random.randint(0, DATE_RANGE_SECONDS)
    return START_DATE + timedelta(seconds=offset)


def main():
    random.seed(RANDOM_SEED)

    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    print(f"Seeding {TOTAL_ORDERS} orders (12% cancellation rate)...")

    batch_size = 1000
    inserted_total = 0

    for batch_start in range(1, TOTAL_ORDERS + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, TOTAL_ORDERS)
        rows = []
        for order_id in range(batch_start, batch_end + 1):
            created_at = random_datetime()
            updated_at = created_at + timedelta(minutes=random.randint(5, 60))
            status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
            rows.append((
                order_id,
                random.randint(1, TOTAL_USERS),
                random.randint(1, TOTAL_RESTAURANTS),
                random.randint(1, TOTAL_DRIVERS) if status != "cancelled" else None,
                status,
                round(random.uniform(10.0, 250.0), 2),
                created_at,
                updated_at,
            ))

        cur.executemany(
            """
            INSERT INTO orders
              (id, user_id, restaurant_id, driver_id, status, total_amount, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            rows,
        )
        inserted_total += batch_end - batch_start + 1
        if batch_start % 10_000 == 1:
            print(f"  Progress: {min(batch_end, TOTAL_ORDERS)}/{TOTAL_ORDERS}")
        conn.commit()

    cur.execute("SELECT setval('orders_id_seq', (SELECT MAX(id) FROM orders))")
    conn.commit()
    cur.close()
    conn.close()

    print(f"Done — {TOTAL_ORDERS} orders seeded")


if __name__ == "__main__":
    main()

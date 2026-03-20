#!/usr/bin/env python3
"""
02_users.py — seed 5,000 users into PostgreSQL.

Idempotent: ON CONFLICT DO NOTHING.
Fixed random seed ensures identical data on every re-run.
Cities: Riyadh, Jeddah, Dammam, Khobar, Mecca.
"""

import os
import random
import psycopg2
from faker import Faker

CITIES = ["Riyadh", "Jeddah", "Dammam", "Khobar", "Mecca"]
TOTAL_USERS = 5_000
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

    print(f"Seeding {TOTAL_USERS} users...")
    inserted = 0
    skipped = 0

    batch_size = 500
    for batch_start in range(1, TOTAL_USERS + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, TOTAL_USERS)
        rows = []
        for user_id in range(batch_start, batch_end + 1):
            rows.append((
                user_id,
                fake.name(),
                fake.email(),
                fake.phone_number()[:50],
                random.choice(CITIES),
            ))

        cur.executemany(
            """
            INSERT INTO users (id, name, email, phone, city)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            rows,
        )
        # Count actual inserts
        inserted += cur.rowcount if cur.rowcount >= 0 else len(rows)
        skipped += len(rows) - (cur.rowcount if cur.rowcount >= 0 else len(rows))

    # Reset sequence to max(id) so new inserts don't collide
    cur.execute("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))")

    conn.commit()
    cur.close()
    conn.close()

    print(f"Done — {TOTAL_USERS} users processed (inserted: ~{inserted}, skipped: ~{skipped})")


if __name__ == "__main__":
    main()

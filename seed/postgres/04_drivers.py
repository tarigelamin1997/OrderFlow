#!/usr/bin/env python3
"""
04_drivers.py — seed 300 drivers into PostgreSQL.

Idempotent: ON CONFLICT DO NOTHING.
"""

import os
import random
import psycopg2
from faker import Faker

CITIES = ["Riyadh", "Jeddah", "Dammam", "Khobar", "Mecca"]
VEHICLE_TYPES = ["motorcycle", "car", "bicycle", "scooter"]
TOTAL_DRIVERS = 300
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

    print(f"Seeding {TOTAL_DRIVERS} drivers...")

    rows = []
    for driver_id in range(1, TOTAL_DRIVERS + 1):
        rows.append((
            driver_id,
            fake.name(),
            fake.phone_number()[:50],
            random.choice(CITIES),
            round(random.uniform(3.0, 5.0), 2),
            random.choice(VEHICLE_TYPES),
        ))

    cur.executemany(
        """
        INSERT INTO drivers (id, name, phone, city, rating, vehicle_type)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        rows,
    )

    cur.execute("SELECT setval('drivers_id_seq', (SELECT MAX(id) FROM drivers))")

    conn.commit()
    cur.close()
    conn.close()

    print(f"Done — {TOTAL_DRIVERS} drivers seeded")


if __name__ == "__main__":
    main()

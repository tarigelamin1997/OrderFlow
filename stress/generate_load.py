#!/usr/bin/env python3
"""
OrderFlow Phase 8 — Stress Test Data Generator

Generates synthetic load for each wave defined in wave_config.yaml.
Inserts into PostgreSQL (orders) and MongoDB (user_events, delivery_updates).
Supports insert, update, delete, burst, and mixed workload modes.
"""

import argparse
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import pymongo
import yaml

# ---------------------------------------------------------------------------
# Constants matching Phase 1 seed data ranges
# ---------------------------------------------------------------------------
USER_ID_RANGE = (1, 5000)
RESTAURANT_ID_RANGE = (1, 200)
DRIVER_ID_RANGE = (1, 300)
ORDER_STATUSES = ["pending", "accepted", "picked_up", "delivered", "cancelled"]
EVENT_TYPES = ["page_view", "click", "search", "add_to_cart", "checkout", "login", "logout"]
DEVICE_TYPES = ["mobile_ios", "mobile_android", "desktop", "tablet"]
PAGES = [
    "/home", "/search", "/restaurant", "/menu", "/cart",
    "/checkout", "/orders", "/profile", "/settings", "/help",
]
DELIVERY_STATUSES = ["assigned", "en_route", "arrived", "picked_up", "delivered"]

# PostgreSQL connection parameters
PG_PARAMS = {
    "host": "localhost",
    "port": 30432,
    "user": "orderflow",
    "password": "orderflow",
    "dbname": "orderflow",
}

# MongoDB connection parameters (no auth — Phase 1 Deviation 9)
MONGO_URI = "mongodb://localhost:30017"
MONGO_DB = "foodtech"

# Batch size for regular (non-burst) inserts
INSERT_BATCH_SIZE = 1000


def load_wave_config(wave_id: int) -> dict:
    """Load and return the wave config for the given wave ID."""
    config_path = Path(__file__).parent / "wave_config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    for wave in config["waves"]:
        if wave["id"] == wave_id:
            return wave

    print(f"ERROR: Wave {wave_id} not found in wave_config.yaml")
    sys.exit(1)


def get_pg_connection():
    """Return a new PostgreSQL connection."""
    return psycopg2.connect(**PG_PARAMS)


def get_mongo_db():
    """Return the MongoDB database object."""
    client = pymongo.MongoClient(MONGO_URI)
    return client[MONGO_DB]


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def generate_order_row() -> tuple:
    """Generate a single synthetic order row.

    Returns (user_id, restaurant_id, driver_id, status, total_amount,
             created_at, updated_at).
    """
    now = datetime.now(timezone.utc)
    created_at = now - timedelta(seconds=random.randint(0, 86400))
    updated_at = created_at + timedelta(seconds=random.randint(0, 3600))
    return (
        random.randint(*USER_ID_RANGE),
        random.randint(*RESTAURANT_ID_RANGE),
        random.randint(*DRIVER_ID_RANGE),
        random.choice(ORDER_STATUSES[:3]),  # new orders: pending/accepted/picked_up
        round(random.uniform(5.00, 150.00), 2),
        created_at,
        updated_at,
    )


def generate_user_event() -> dict:
    """Generate a single synthetic user event document for MongoDB."""
    now = datetime.now(timezone.utc)
    return {
        "user_id": random.randint(*USER_ID_RANGE),
        "event_type": random.choice(EVENT_TYPES),
        "timestamp": now - timedelta(seconds=random.randint(0, 86400)),
        "session_id": str(uuid.uuid4()),
        "page": random.choice(PAGES),
        "device_type": random.choice(DEVICE_TYPES),
        "schema_version": "1.0",
    }


def generate_delivery_update() -> dict:
    """Generate a single synthetic delivery update document for MongoDB."""
    now = datetime.now(timezone.utc)
    return {
        "order_id": random.randint(1, 500000),
        "driver_id": random.randint(*DRIVER_ID_RANGE),
        "status": random.choice(DELIVERY_STATUSES),
        "latitude": round(random.uniform(59.0, 60.0), 6),
        "longitude": round(random.uniform(17.5, 18.5), 6),
        "timestamp": now - timedelta(seconds=random.randint(0, 3600)),
    }


# ---------------------------------------------------------------------------
# Insert operations
# ---------------------------------------------------------------------------

def insert_orders_batch(conn, rows: list[tuple]) -> None:
    """Batch-insert order rows into PostgreSQL."""
    sql = """
        INSERT INTO orders (user_id, restaurant_id, driver_id, status,
                            total_amount, created_at, updated_at)
        VALUES %s
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=INSERT_BATCH_SIZE)
    conn.commit()


def insert_orders(count: int, burst: bool = False) -> dict:
    """Insert `count` orders into PostgreSQL.

    If burst=True, all rows are inserted in a single batch.
    Returns timing info dict.
    """
    if count == 0:
        return {"orders_inserted": 0, "duration_s": 0.0}

    conn = get_pg_connection()
    start = time.time()
    inserted = 0

    try:
        if burst:
            print(f"  [BURST] Generating {count} orders in one batch...")
            rows = [generate_order_row() for _ in range(count)]
            insert_orders_batch(conn, rows)
            inserted = count
            print(f"  [BURST] Inserted {count} orders.")
        else:
            batch = []
            for i in range(count):
                batch.append(generate_order_row())
                if len(batch) >= INSERT_BATCH_SIZE:
                    insert_orders_batch(conn, batch)
                    inserted += len(batch)
                    batch = []
                    if inserted % 5000 == 0:
                        print(f"  Orders inserted: {inserted}/{count}")
            if batch:
                insert_orders_batch(conn, batch)
                inserted += len(batch)
    finally:
        conn.close()

    duration = time.time() - start
    print(f"  Orders complete: {inserted} rows in {duration:.2f}s")
    return {"orders_inserted": inserted, "duration_s": round(duration, 3)}


def insert_user_events(count: int) -> dict:
    """Insert `count` user events into MongoDB."""
    if count == 0:
        return {"user_events_inserted": 0, "duration_s": 0.0}

    db = get_mongo_db()
    collection = db["user_events"]
    start = time.time()
    inserted = 0

    batch = []
    for i in range(count):
        batch.append(generate_user_event())
        if len(batch) >= INSERT_BATCH_SIZE:
            collection.insert_many(batch)
            inserted += len(batch)
            batch = []
            if inserted % 5000 == 0:
                print(f"  User events inserted: {inserted}/{count}")
    if batch:
        collection.insert_many(batch)
        inserted += len(batch)

    duration = time.time() - start
    print(f"  User events complete: {inserted} docs in {duration:.2f}s")
    return {"user_events_inserted": inserted, "duration_s": round(duration, 3)}


def insert_delivery_updates(count: int) -> dict:
    """Insert `count` delivery updates into MongoDB."""
    if count == 0:
        return {"delivery_updates_inserted": 0, "duration_s": 0.0}

    db = get_mongo_db()
    collection = db["delivery_updates"]
    start = time.time()
    inserted = 0

    batch = []
    for i in range(count):
        batch.append(generate_delivery_update())
        if len(batch) >= INSERT_BATCH_SIZE:
            collection.insert_many(batch)
            inserted += len(batch)
            batch = []
            if inserted % 5000 == 0:
                print(f"  Delivery updates inserted: {inserted}/{count}")
    if batch:
        collection.insert_many(batch)
        inserted += len(batch)

    duration = time.time() - start
    print(f"  Delivery updates complete: {inserted} docs in {duration:.2f}s")
    return {"delivery_updates_inserted": inserted, "duration_s": round(duration, 3)}


# ---------------------------------------------------------------------------
# Update / Delete operations
# ---------------------------------------------------------------------------

def update_orders(pct: float) -> dict:
    """UPDATE random `pct` fraction of existing orders to status='delivered'."""
    conn = get_pg_connection()
    start = time.time()

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM orders")
            total = cur.fetchone()[0]
            target = int(total * pct)
            print(f"  Updating {target} orders ({pct*100:.0f}% of {total}) to delivered...")

            cur.execute(
                """
                UPDATE orders
                SET status = 'delivered',
                    updated_at = NOW()
                WHERE id IN (
                    SELECT id FROM orders
                    WHERE status != 'delivered'
                    ORDER BY RANDOM()
                    LIMIT %s
                )
                """,
                (target,),
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    duration = time.time() - start
    print(f"  Updates complete: {affected} rows in {duration:.2f}s")
    return {"orders_updated": affected, "duration_s": round(duration, 3)}


def soft_delete_orders(pct: float) -> dict:
    """Soft-delete random `pct` fraction of orders by setting status='cancelled'."""
    conn = get_pg_connection()
    start = time.time()

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM orders")
            total = cur.fetchone()[0]
            target = int(total * pct)
            print(f"  Soft-deleting {target} orders ({pct*100:.0f}% of {total})...")

            cur.execute(
                """
                UPDATE orders
                SET status = 'cancelled',
                    updated_at = NOW()
                WHERE id IN (
                    SELECT id FROM orders
                    WHERE status != 'cancelled'
                    ORDER BY RANDOM()
                    LIMIT %s
                )
                """,
                (target,),
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    duration = time.time() - start
    print(f"  Soft deletes complete: {affected} rows in {duration:.2f}s")
    return {"orders_soft_deleted": affected, "duration_s": round(duration, 3)}


# ---------------------------------------------------------------------------
# Wave execution
# ---------------------------------------------------------------------------

def run_wave(wave_id: int) -> dict:
    """Execute a single wave and return the combined results."""
    wave = load_wave_config(wave_id)
    print(f"\n{'='*60}")
    print(f"Wave {wave_id}: {wave['description']}")
    print(f"{'='*60}")

    results = {
        "wave_id": wave_id,
        "description": wave["description"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "operations": {},
    }

    wave_start = time.time()

    # --- Measurement-only waves (1 and 12) ---
    orders_count = wave.get("orders", 0)
    user_events_count = wave.get("user_events", 0)
    delivery_updates_count = wave.get("delivery_updates", 0)
    is_burst = wave.get("burst", False)
    is_updates_only = wave.get("updates_only", False)
    is_deletes_only = wave.get("deletes_only", False)
    update_pct = wave.get("update_pct", 0.0)

    # Inserts
    if orders_count > 0:
        results["operations"]["orders"] = insert_orders(orders_count, burst=is_burst)

    if user_events_count > 0:
        results["operations"]["user_events"] = insert_user_events(user_events_count)

    if delivery_updates_count > 0:
        results["operations"]["delivery_updates"] = insert_delivery_updates(
            delivery_updates_count
        )

    # Updates (wave 9 or mixed wave 11)
    if is_updates_only and update_pct > 0:
        results["operations"]["updates"] = update_orders(update_pct)
    elif not is_updates_only and update_pct > 0:
        # Mixed mode: do inserts (already done above) + updates
        results["operations"]["updates"] = update_orders(update_pct)

    # Deletes (wave 10)
    if is_deletes_only:
        delete_pct = wave.get("delete_pct", 0.05)
        results["operations"]["deletes"] = soft_delete_orders(delete_pct)

    # If measurement-only wave, record current counts
    if orders_count == 0 and not is_updates_only and not is_deletes_only:
        results["operations"]["measurement"] = measure_current_counts()

    wave_duration = time.time() - wave_start
    results["total_duration_s"] = round(wave_duration, 3)
    results["finished_at"] = datetime.now(timezone.utc).isoformat()

    print(f"\nWave {wave_id} completed in {wave_duration:.2f}s")
    return results


def measure_current_counts() -> dict:
    """Measure current row counts across PostgreSQL and MongoDB."""
    counts = {}

    # PostgreSQL
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM orders")
            counts["pg_orders_total"] = cur.fetchone()[0]
            cur.execute("SELECT status, COUNT(*) FROM orders GROUP BY status")
            counts["pg_orders_by_status"] = dict(cur.fetchall())
    finally:
        conn.close()

    # MongoDB
    db = get_mongo_db()
    counts["mongo_user_events"] = db["user_events"].count_documents({})
    counts["mongo_delivery_updates"] = db["delivery_updates"].count_documents({})

    print(f"  Current counts: {json.dumps(counts, indent=2, default=str)}")
    return counts


def save_results(wave_id: int, results: dict) -> str:
    """Save wave results to stress/results/wave_{N}.json."""
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / f"wave_{wave_id}.json"

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"Results saved to {output_path}")
    return str(output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="OrderFlow Phase 8 — Stress Test Data Generator"
    )
    parser.add_argument(
        "--wave",
        type=int,
        required=True,
        help="Wave number to execute (1-12)",
    )
    args = parser.parse_args()

    if args.wave < 1 or args.wave > 12:
        print(f"ERROR: Wave must be between 1 and 12, got {args.wave}")
        sys.exit(1)

    results = run_wave(args.wave)
    save_results(args.wave, results)


if __name__ == "__main__":
    main()

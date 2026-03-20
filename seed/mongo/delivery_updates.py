#!/usr/bin/env python3
"""
delivery_updates.py — seed ~15,000 delivery_updates documents into MongoDB.

Idempotent: upsert on _id.
Nested location: {lat, lng, accuracy} as specified in the plan.
Collection: foodtech.delivery_updates
"""

import os
import random
from datetime import datetime, timedelta

from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

TOTAL_UPDATES = 15_000
TOTAL_ORDERS = 50_000
TOTAL_DRIVERS = 300
RANDOM_SEED = 42

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://orderflow:orderflow_mongo_pass@localhost:30017/foodtech?authSource=admin&directConnection=true"
)

DELIVERY_STATUSES = [
    "driver_assigned",
    "heading_to_restaurant",
    "at_restaurant",
    "picked_up",
    "en_route",
    "arrived",
    "delivered",
]

# Saudi Arabia bounding box for realistic coordinates
LAT_MIN, LAT_MAX = 16.0, 32.0
LNG_MIN, LNG_MAX = 36.0, 56.0


def make_update(update_id: int, rng: random.Random) -> dict:
    """Generate a single delivery_update document."""
    created_at = datetime(2023, 1, 1) + timedelta(
        seconds=rng.randint(0, int((datetime(2025, 1, 1) - datetime(2023, 1, 1)).total_seconds()))
    )

    return {
        "_id": f"dlv_{update_id:06d}",
        "order_id": rng.randint(1, TOTAL_ORDERS),
        "driver_id": rng.randint(1, TOTAL_DRIVERS),
        "status": rng.choice(DELIVERY_STATUSES),
        "location": {
            "lat":      round(rng.uniform(LAT_MIN, LAT_MAX), 6),
            "lng":      round(rng.uniform(LNG_MIN, LNG_MAX), 6),
            "accuracy": round(rng.uniform(3.0, 25.0), 1),   # meters GPS accuracy
        },
        "timestamp": created_at,
    }


def main():
    rng = random.Random(RANDOM_SEED)

    client = MongoClient(MONGO_URI)
    db = client["foodtech"]
    collection = db["delivery_updates"]

    print(f"Seeding {TOTAL_UPDATES} delivery_updates documents...")

    batch_size = 500
    total_upserted = 0

    for batch_start in range(1, TOTAL_UPDATES + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, TOTAL_UPDATES)
        ops = []
        for update_id in range(batch_start, batch_end + 1):
            doc = make_update(update_id, rng)
            ops.append(UpdateOne(
                {"_id": doc["_id"]},
                {"$set": doc},
                upsert=True,
            ))

        try:
            result = collection.bulk_write(ops, ordered=False)
            total_upserted += result.upserted_count + result.modified_count
        except BulkWriteError as e:
            total_upserted += e.details.get("nUpserted", 0) + e.details.get("nModified", 0)

    client.close()
    print(f"Done — {TOTAL_UPDATES} delivery_updates seeded ({total_upserted} upserted/modified)")


if __name__ == "__main__":
    main()

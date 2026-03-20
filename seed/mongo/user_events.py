#!/usr/bin/env python3
"""
user_events.py — seed ~30,000 user_events documents into MongoDB.

Idempotent: upsert on _id.
Schema evolution across 3 versions (V1/2023, V2/2024, V3/2025).
Collection: foodtech.user_events
"""

import os
import random
from datetime import datetime, timedelta

from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

TOTAL_EVENTS = 30_000
TOTAL_USERS = 5_000
RANDOM_SEED = 42

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://orderflow:orderflow_mongo_pass@localhost:30017/foodtech?authSource=admin&directConnection=true"
)

EVENT_TYPES = ["page_view", "search", "add_to_cart", "checkout", "order_placed", "order_cancelled"]
DEVICE_TYPES = ["ios", "android", "web"]
APP_VERSIONS = ["3.0.0", "3.1.0", "3.2.0"]

# Schema versions correlate to years as documented in the plan
CITIES_LAT_LNG = {
    "Riyadh":  (24.7136, 46.6753),
    "Jeddah":  (21.4858, 39.1925),
    "Dammam":  (26.4207, 50.0888),
    "Khobar":  (26.2172, 50.1971),
    "Mecca":   (21.3891, 39.8579),
}
CITIES = list(CITIES_LAT_LNG.keys())


def make_event(event_id: int, rng: random.Random) -> dict:
    """Generate a single user_event document with schema evolution."""
    created_at = datetime(2023, 1, 1) + timedelta(
        seconds=rng.randint(0, int((datetime(2025, 6, 1) - datetime(2023, 1, 1)).total_seconds()))
    )
    year = created_at.year

    doc = {
        "_id": f"evt_{event_id:06d}",
        "user_id": rng.randint(1, TOTAL_USERS),
        "event_type": rng.choice(EVENT_TYPES),
        "timestamp": created_at,
        "schema_version": 1 if year == 2023 else (2 if year == 2024 else 3),
    }

    # V2 (2024+): adds session_id and device_type
    if year >= 2024:
        doc["session_id"] = f"sess_{rng.randint(100000, 999999)}"
        doc["device_type"] = rng.choice(DEVICE_TYPES)

    # V3 (2025+): adds app_version and location
    if year >= 2025:
        doc["app_version"] = rng.choice(APP_VERSIONS)
        city = rng.choice(CITIES)
        base_lat, base_lng = CITIES_LAT_LNG[city]
        doc["location"] = {
            "lat": round(base_lat + rng.uniform(-0.05, 0.05), 6),
            "lng": round(base_lng + rng.uniform(-0.05, 0.05), 6),
        }

    return doc


def main():
    rng = random.Random(RANDOM_SEED)

    client = MongoClient(MONGO_URI)
    db = client["foodtech"]
    collection = db["user_events"]

    print(f"Seeding {TOTAL_EVENTS} user_events documents...")

    batch_size = 500
    total_upserted = 0

    for batch_start in range(1, TOTAL_EVENTS + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, TOTAL_EVENTS)
        ops = []
        for event_id in range(batch_start, batch_end + 1):
            doc = make_event(event_id, rng)
            ops.append(UpdateOne(
                {"_id": doc["_id"]},
                {"$set": doc},
                upsert=True,
            ))

        try:
            result = collection.bulk_write(ops, ordered=False)
            total_upserted += result.upserted_count + result.modified_count
        except BulkWriteError as e:
            # Partial writes are fine — idempotent upserts handle conflicts
            total_upserted += e.details.get("nUpserted", 0) + e.details.get("nModified", 0)

        if batch_start % 5_000 == 1:
            print(f"  Progress: {min(batch_end, TOTAL_EVENTS)}/{TOTAL_EVENTS}")

    client.close()
    print(f"Done — {TOTAL_EVENTS} user_events seeded ({total_upserted} upserted/modified)")


if __name__ == "__main__":
    main()

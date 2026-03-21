#!/usr/bin/env python3
"""
gen_phase4.py -- Phase 4 file generator for OrderFlow.

Copy this file (and the whole spark/_gen/ directory) to the EC2 instance
inside ~/OrderFlow, then run:

    python3 ~/OrderFlow/spark/_gen/gen_phase4.py

All Phase 4 files will be created under ~/OrderFlow/.
You can also symlink or copy this to /tmp/ and run from there -- the script
locates its content modules relative to its own __file__.
"""

import os
import stat
import sys

# ── Locate content modules alongside this script ─────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from content_dockerfile          import get as dockerfile_content
from content_silver_ingestion    import get as silver_ingestion_content
from content_feature_engineering import get as feature_engineering_content
from content_gold_writer         import get as gold_writer_content
from content_manifests           import (
    silver_ingestion_yaml,
    feature_engineering_yaml,
    gold_writer_yaml,
)
from content_verify              import get as verify_content
from content_clickhouse          import (
    restaurant_revenue_batch_sql,
    driver_features_batch_sql,
    demand_zone_batch_sql,
    apply_gold_batch_sh,
)

BASE = os.path.expanduser("~/OrderFlow")

# (relative_path, content_callable, executable)
FILES = [
    ("spark/Dockerfile",
     dockerfile_content,                  False),
    ("spark/jobs/silver_ingestion.py",
     silver_ingestion_content,            False),
    ("spark/jobs/feature_engineering.py",
     feature_engineering_content,         False),
    ("spark/jobs/gold_writer.py",
     gold_writer_content,                 False),
    ("spark/manifests/silver-ingestion.yaml",
     silver_ingestion_yaml,               False),
    ("spark/manifests/feature-engineering.yaml",
     feature_engineering_yaml,            False),
    ("spark/manifests/gold-writer.yaml",
     gold_writer_yaml,                    False),
    ("spark/scripts/verify_phase4.sh",
     verify_content,                      True),
    ("clickhouse/gold/09_restaurant_revenue_batch.sql",
     restaurant_revenue_batch_sql,        False),
    ("clickhouse/gold/10_driver_features_batch.sql",
     driver_features_batch_sql,           False),
    ("clickhouse/gold/11_demand_zone_batch.sql",
     demand_zone_batch_sql,               False),
    ("clickhouse/gold/apply_gold_batch.sh",
     apply_gold_batch_sh,                 True),
]


def main() -> None:
    print(f"Writing {len(FILES)} Phase 4 files under {BASE}/")
    print()
    for rel_path, content_fn, executable in FILES:
        abs_path = os.path.join(BASE, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content_fn())
        if executable:
            mode = os.stat(abs_path).st_mode
            os.chmod(abs_path,
                     mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"  created (chmod +x): {rel_path}")
        else:
            print(f"  created:            {rel_path}")

    print()
    print(f"Done. {len(FILES)} files written.")
    print()
    print("Next steps (from ~/OrderFlow):")
    print("  1. docker build -t orderflow/spark-orderflow:3.5.1-delta3 spark/")
    print("  2. kind load docker-image orderflow/spark-orderflow:3.5.1-delta3"
          " --name orderflow")
    print("  3. bash clickhouse/gold/apply_gold_batch.sh")
    print("  4. kubectl apply -f spark/manifests/silver-ingestion.yaml")
    print("  5. (wait for silver-ingestion COMPLETED)")
    print("     kubectl apply -f spark/manifests/feature-engineering.yaml")
    print("  6. (wait for feature-engineering COMPLETED)")
    print("     kubectl apply -f spark/manifests/gold-writer.yaml")
    print("  7. bash spark/scripts/verify_phase4.sh")


if __name__ == "__main__":
    main()

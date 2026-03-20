#!/usr/bin/env python3
"""
check_version_drift.py — cross-file version consistency checker.

Scans every Terraform .tf file, Dockerfile FROM tag, Helm values.yaml,
and requirements.txt in the repo. Finds any hardcoded version that does
not match versions.yaml. Fails CI with exact file + line number of drift.
"""

import re
import sys
import yaml
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
VERSIONS_FILE = REPO_ROOT / "versions.yaml"

# Patterns to detect hardcoded versions per file type.
# Maps component key → list of regex patterns that should NOT appear
# (i.e., a version string that differs from versions.yaml).
# Each pattern group 1 captures the version string found.
VERSION_PATTERNS = {
    "kafka": [
        r'kafka[_-]version\s*[=:]\s*["\']?(\d+\.\d+[\.\d]*)',
        r'FROM\s+(?:confluentinc/cp-kafka|strimzi/kafka):([^\s"\']+)',
        r'kafkaVersion:\s*["\']?(\d+\.\d+[\.\d]*)',
    ],
    "schema_registry": [
        r'FROM\s+confluentinc/cp-schema-registry:([^\s"\']+)',
        r'schema[_-]registry[_-]version\s*[=:]\s*["\']?(\d+\.\d+[\.\d]*)',
    ],
    "debezium": [
        r'FROM\s+debezium/connect:([^\s"\']+)',
        r'debezium[_-]version\s*[=:]\s*["\']?(\d+\.\d+[\.\d]*)',
        r'io\.debezium:debezium-connector[^:]+:([^\s"\'<>]+)',
    ],
    "clickhouse": [
        r'FROM\s+clickhouse/clickhouse-server:([^\s"\']+)',
        r'clickhouse[_-]version\s*[=:]\s*["\']?(\d+\.\d+[\.\d]*)',
    ],
    "spark": [
        r'FROM\s+(?:apache/spark|bitnami/spark):([^\s"\']+)',
        r'spark[_-]version\s*[=:]\s*["\']?(\d+\.\d+[\.\d]*)',
    ],
    "airflow": [
        r'FROM\s+apache/airflow:([^\s"\']+)',
        r'airflow[_-]version\s*[=:]\s*["\']?(\d+\.\d+[\.\d]*)',
    ],
    "postgres": [
        r'FROM\s+postgres:(\d+(?:\.\d+)*)',
        r'postgres[_-]version\s*[=:]\s*["\']?(\d+[\.\d]*)',
        r'image:\s*postgres:(\d+(?:\.\d+)*)',
    ],
    "mongodb": [
        r'FROM\s+mongo:([^\s"\']+)',
        r'mongo[_-]version\s*[=:]\s*["\']?(\d+\.\d+[\.\d]*)',
        r'image:\s*mongo:(\d+(?:\.\d+)*)',
    ],
    "marquez": [
        r'FROM\s+marquezproject/marquez[^:]*:([^\s"\']+)',
        r'marquez[_-]version\s*[=:]\s*["\']?(\d+\.\d+[\.\d]*)',
    ],
    "terraform": [
        r'required_version\s*=\s*["\'][><=~\s]*(\d+\.\d+[\.\d]*)',
    ],
    "dbt_core": [
        r'dbt-core[>=<~!]+(\d+\.\d+[\.\d]*)',
        r'dbt_core[>=<~!]+(\d+\.\d+[\.\d]*)',
    ],
    "dbt_clickhouse": [
        r'dbt-clickhouse[>=<~!]+(\d+\.\d+[\.\d]*)',
    ],
    "dbt_spark": [
        r'dbt-spark[>=<~!]+(\d+\.\d+[\.\d]*)',
    ],
    "great_expectations": [
        r'great[_-]expectations[>=<~!]+(\d+\.\d+[\.\d]*)',
        r'great_expectations[>=<~!]+(\d+\.\d+[\.\d]*)',
    ],
}

# Files/directories to skip
SKIP_DIRS = {".terraform", ".git", "__pycache__", "target", "dbt_packages",
             "logs", ".venv", "venv", "dist", "build", "node_modules"}
SKIP_FILES = {"versions.yaml", "check_version_drift.py", "check_versions.py"}


def load_versions() -> dict:
    with open(VERSIONS_FILE) as f:
        data = yaml.safe_load(f)
    return data["components"]


def version_matches(found: str, expected: str) -> bool:
    """
    Check if the found version string is compatible with the expected version.
    Allows for prefix matching: expected '15' matches found '15', '15.0', '15.2', etc.
    """
    found = found.strip().lstrip("v")
    expected = str(expected).strip()
    # Exact match
    if found == expected:
        return True
    # Prefix match: '15' should match '15.3' but not '150'
    if found.startswith(expected + ".") or found.startswith(expected + "-"):
        return True
    # expected with wildcard suffix in requirements (e.g. '1.8.*')
    base_expected = expected.rstrip(".*")
    if found.startswith(base_expected):
        return True
    return False


def scan_file(filepath: Path, versions: dict) -> list[dict]:
    """Scan a single file for hardcoded version drift. Returns list of findings."""
    findings = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except (OSError, PermissionError):
        return findings

    lines = content.splitlines()

    for component, patterns in VERSION_PATTERNS.items():
        expected_version = str(versions.get(component, ""))
        if not expected_version:
            continue

        for pattern in patterns:
            for lineno, line in enumerate(lines, start=1):
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    found_version = match.group(1)
                    if not version_matches(found_version, expected_version):
                        findings.append({
                            "file": str(filepath.relative_to(REPO_ROOT)),
                            "line": lineno,
                            "component": component,
                            "expected": expected_version,
                            "found": found_version,
                            "context": line.strip(),
                        })

    return findings


def collect_files() -> list[Path]:
    """Walk repo and collect all files to scan."""
    scan_extensions = {".tf", ".yaml", ".yml", ".txt", "Dockerfile", ".env.example"}
    files = []

    for path in REPO_ROOT.rglob("*"):
        # Skip hidden dirs and known non-source dirs
        parts = set(path.parts)
        if any(skip in parts for skip in SKIP_DIRS):
            continue
        if path.name in SKIP_FILES:
            continue
        if not path.is_file():
            continue
        # Include by extension or exact name
        if path.suffix in scan_extensions or path.name == "Dockerfile":
            files.append(path)

    return sorted(files)


def main():
    print(f"Loading versions from {VERSIONS_FILE}")
    versions = load_versions()

    files = collect_files()
    print(f"Scanning {len(files)} files for version drift...\n")

    all_findings = []
    for filepath in files:
        findings = scan_file(filepath, versions)
        all_findings.extend(findings)

    print(f"{'='*60}")
    if all_findings:
        print(f"VERSION DRIFT DETECTED — {len(all_findings)} occurrence(s):\n")
        for f in all_findings:
            print(f"  {f['file']}:{f['line']}")
            print(f"    component : {f['component']}")
            print(f"    expected  : {f['expected']}")
            print(f"    found     : {f['found']}")
            print(f"    context   : {f['context']}")
            print()
        sys.exit(1)
    else:
        print(f"No version drift found across {len(files)} files.")
        sys.exit(0)


if __name__ == "__main__":
    main()

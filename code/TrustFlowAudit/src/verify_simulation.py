#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_result(results_dir: Path) -> dict[str, Any]:
    result_path = results_dir / "results.json"
    if not result_path.exists():
        raise FileNotFoundError(f"missing {result_path}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def by_key(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(row[key]): row for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify TrustFlowAudit BLoP mechanism simulation outputs.")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--expect-trusted-anomaly-events", type=int, default=32220)
    parser.add_argument("--expect-tamper-proof-events", type=int, default=479)
    parser.add_argument("--expect-months", type=int, default=17)
    args = parser.parse_args()

    result = load_result(Path(args.results_dir))
    totals = result["totals"]
    if totals["trusted_anomaly_events"] != args.expect_trusted_anomaly_events:
        raise AssertionError("trusted anomaly event total mismatch")
    if totals["tamper_proof_events"] != args.expect_tamper_proof_events:
        raise AssertionError("tamper-proof event total mismatch")
    if len(result["event_rows"]) != args.expect_months:
        raise AssertionError("month count mismatch")
    if not result["integrity"]["tamper_detected"]:
        raise AssertionError("hash-chain tamper detection must be true")

    governance = result.get("governance_summary")
    if not governance:
        raise AssertionError("missing governance summary")
    if governance["total_whitelist_blocks"] <= 0 or governance["total_critical_alerts"] <= 0:
        raise AssertionError("governance whitelist and alert counters must be positive")

    recovery = by_key(result.get("recovery_summary", []), "scenario")
    required = {"multi_replica_hash_audit", "erasure_audit_only", "erasure_recovery_chain"}
    if set(recovery) != required:
        raise AssertionError(f"recovery scenarios mismatch: {sorted(recovery)}")
    erasure_recovery = recovery["erasure_recovery_chain"]
    erasure_only = recovery["erasure_audit_only"]
    multi_replica = recovery["multi_replica_hash_audit"]
    if erasure_recovery["total_recovered_shards"] <= erasure_only["total_recovered_shards"]:
        raise AssertionError("erasure recovery scenario must recover more shards than audit-only")
    if erasure_recovery["avg_storage_overhead"] >= multi_replica["avg_storage_overhead"]:
        raise AssertionError("erasure recovery storage overhead must be lower than multi-replica")
    if erasure_recovery["total_reputation_penalties"] <= 0:
        raise AssertionError("erasure recovery scenario must record reputation penalties")

    print("simulation verification passed")
    print(f"trusted_anomaly_events={totals['trusted_anomaly_events']}")
    print(f"tamper_proof_events={totals['tamper_proof_events']}")
    print(f"whitelist_blocks={governance['total_whitelist_blocks']}")
    print(
        "erasure_recovery="
        f"detected:{erasure_recovery['total_detected_shards']},"
        f"recovered:{erasure_recovery['total_recovered_shards']},"
        f"closed_loop_rate:{erasure_recovery['closed_loop_rate']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

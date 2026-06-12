#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_result(result_dir: Path) -> dict[str, Any]:
    result_path = result_dir / "consortium_results.json"
    if not result_path.exists():
        raise FileNotFoundError(f"missing {result_path}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def expect_equal(name: str, actual: Any, expected: Any) -> None:
    if expected is not None and actual != expected:
        raise AssertionError(f"{name}: actual={actual!r}, expected={expected!r}")


def verify_result(result: dict[str, Any], args: argparse.Namespace) -> None:
    blocks = result.get("blocks", [])
    metrics = result.get("metrics", [])
    quorum = int(result["quorum"])
    if not blocks:
        raise AssertionError("blocks must not be empty")
    if len(metrics) != len(blocks):
        raise AssertionError(f"metrics length {len(metrics)} != blocks length {len(blocks)}")

    expect_equal("execution_mode", result.get("execution_mode"), args.expect_mode)
    expect_equal("blocks", len(blocks), args.expect_blocks)
    expect_equal("quorum", quorum, args.expect_quorum)
    expect_equal("registered_nodes", len(result.get("registered_nodes", [])), args.expect_registered)
    expect_equal("trusted_nodes", len(result.get("trusted_nodes", [])), args.expect_trusted)
    expect_equal("excluded_nodes", len(result.get("excluded_nodes", [])), args.expect_excluded)
    expect_equal("unavailable_nodes", len(result.get("unavailable_nodes", [])), args.expect_unavailable)
    expect_equal("voting_nodes", len(result.get("voting_nodes", [])), args.expect_voting)

    prev_hash = "GENESIS"
    abnormal_rounds: list[int] = []
    for expected_height, row in enumerate(blocks, start=1):
        if int(row["height"]) != expected_height:
            raise AssertionError(f"height mismatch: actual={row['height']}, expected={expected_height}")
        if row["prev_hash"] != prev_hash:
            raise AssertionError(f"prev_hash mismatch at height {expected_height}")
        if int(row["votes"]) < quorum:
            raise AssertionError(f"votes below quorum at height {expected_height}")
        if int(row["committed_nodes"]) < quorum:
            raise AssertionError(f"committed nodes below quorum at height {expected_height}")
        if not row.get("payload_hash") or not row.get("merkle_root") or not row.get("block_hash"):
            raise AssertionError(f"missing hash field at height {expected_height}")
        if row.get("update_type") != "normal":
            abnormal_rounds.append(expected_height)
        prev_hash = row["block_hash"]

    if prev_hash != result["final_block_hash"]:
        raise AssertionError("final_block_hash does not match last block")
    if args.expect_abnormal_round is not None and abnormal_rounds != args.expect_abnormal_round:
        raise AssertionError(f"abnormal rounds: actual={abnormal_rounds}, expected={args.expect_abnormal_round}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify TrustFlowAudit consortium experiment outputs.")
    parser.add_argument("--result-dir", required=True)
    parser.add_argument("--expect-mode")
    parser.add_argument("--expect-blocks", type=int)
    parser.add_argument("--expect-quorum", type=int)
    parser.add_argument("--expect-registered", type=int)
    parser.add_argument("--expect-trusted", type=int)
    parser.add_argument("--expect-excluded", type=int)
    parser.add_argument("--expect-unavailable", type=int)
    parser.add_argument("--expect-voting", type=int)
    parser.add_argument("--expect-abnormal-round", action="append", type=int)
    args = parser.parse_args()

    result_dir = Path(args.result_dir)
    result = load_result(result_dir)
    verify_result(result, args)
    print(
        "verification passed: "
        f"mode={result.get('execution_mode')}, "
        f"blocks={len(result['blocks'])}, "
        f"quorum={result['quorum']}, "
        f"trusted={len(result.get('trusted_nodes', []))}, "
        f"excluded={len(result.get('excluded_nodes', []))}, "
        f"unavailable={len(result.get('unavailable_nodes', []))}, "
        f"voting={len(result.get('voting_nodes', []))}, "
        f"final_hash={result['final_block_hash'][:16]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

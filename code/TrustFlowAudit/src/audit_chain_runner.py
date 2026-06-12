#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from common import canonical_json, sha256_hex
from consortium_runner import (
    apply_fault_injection,
    available_nodes,
    commit_block,
    commit_block_dry_run,
    load_config,
    make_dry_run_nodes,
    wait_nodes,
)


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_digest(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def strategy_reductions(strategy_summary: list[dict[str, Any]]) -> dict[str, float]:
    baseline = next(row for row in strategy_summary if row["strategy"] == "blop_full_pbft")
    ours = next(row for row in strategy_summary if row["strategy"] == "trustflowaudit")
    return {
        "chain_record_reduction": round(1.0 - ours["total_chain_records"] / baseline["total_chain_records"], 6),
        "amortized_latency_reduction": round(
            1.0 - ours["avg_amortized_event_commit_ms"] / baseline["avg_amortized_event_commit_ms"], 6
        ),
        "evidence_storage_reduction": round(
            1.0 - ours["evidence_storage_overhead"] / baseline["evidence_storage_overhead"], 6
        ),
    }


def build_payloads(simulation: dict[str, Any], artifact_paths: list[Path]) -> list[dict[str, Any]]:
    payloads = [
        {
            "type": "blop_event_integrity_anchor",
            "totals": simulation["totals"],
            "integrity": simulation["integrity"],
        },
        {
            "type": "blop_governance_anchor",
            "governance_summary": simulation["governance_summary"],
        },
        {
            "type": "trustflowaudit_strategy_anchor",
            "strategy_summary": simulation["strategy_summary"],
            "reductions": strategy_reductions(simulation["strategy_summary"]),
        },
        {
            "type": "erasure_recovery_anchor",
            "recovery_summary": simulation["recovery_summary"],
        },
    ]
    artifact_hashes = []
    for path in artifact_paths:
        if path.exists():
            artifact_hashes.append({"path": str(path), "sha256": file_digest(path)})
    payloads.append(
        {
            "type": "artifact_manifest_anchor",
            "simulation_result_hash": sha256_hex(canonical_json(simulation)),
            "artifacts": artifact_hashes,
        }
    )
    return payloads


def run_audit_chain(
    *,
    config: dict[str, Any],
    simulation: dict[str, Any],
    artifact_paths: list[Path],
    dry_run: bool,
) -> dict[str, Any]:
    nodes = make_dry_run_nodes(config) if dry_run else wait_nodes(config)
    nodes = apply_fault_injection(nodes, config)
    trusted = [node for node in nodes if float(node["trust_score"]) >= float(config["trust_threshold"])]
    excluded = [node for node in nodes if float(node["trust_score"]) < float(config["trust_threshold"])]
    unavailable = [node for node in trusted if not bool(node.get("available", True))]
    voting_nodes = available_nodes(trusted)
    quorum = 2 * int(config["fault_tolerance"]) + 1
    if len(voting_nodes) < quorum:
        raise RuntimeError(f"available trusted nodes {len(voting_nodes)} < quorum {quorum}")

    payloads = build_payloads(simulation, artifact_paths)
    artifact_manifest = next(payload for payload in payloads if payload["type"] == "artifact_manifest_anchor")
    commit_fn = commit_block_dry_run if dry_run else commit_block
    prev_hash = "GENESIS"
    block_rows: list[dict[str, Any]] = []
    for height, payload in enumerate(payloads, start=1):
        commit = commit_fn(payload=payload, nodes=voting_nodes, prev_hash=prev_hash, height=height, quorum=quorum)
        prev_hash = commit["block"]["block_hash"]
        block_rows.append(
            {
                "height": height,
                "prev_hash": commit["block"]["prev_hash"],
                "block_hash": prev_hash,
                "votes": commit["votes"],
                "committed_nodes": commit["committed_nodes"],
                "latency_ms": round(commit["latency_ms"], 4),
                "payload_hash": commit["block"]["payload_hash"],
                "merkle_root": commit["block"]["merkle_root"],
                "payload_type": payload["type"],
            }
        )

    return {
        "execution_mode": "dry_run" if dry_run else "zookeeper_container",
        "registered_nodes": nodes,
        "trusted_nodes": trusted,
        "excluded_nodes": excluded,
        "unavailable_nodes": unavailable,
        "voting_nodes": voting_nodes,
        "quorum": quorum,
        "payload_types": [payload["type"] for payload in payloads],
        "payload_count": len(payloads),
        "simulation_result_hash": sha256_hex(canonical_json(simulation)),
        "artifacts": artifact_manifest["artifacts"],
        "artifact_count": len(artifact_manifest["artifacts"]),
        "final_block_hash": prev_hash,
        "blocks": block_rows,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_report(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    latencies = [row["latency_ms"] for row in result["blocks"]]
    lines = [
        "# BLoP 机制结果联盟链锚定报告",
        "",
        "- 不使用 TPM/TEE。",
        f"- 执行模式：`{result['execution_mode']}`。",
        f"- 注册节点数：{len(result['registered_nodes'])}",
        f"- 可信节点数：{len(result['trusted_nodes'])}",
        f"- 排除节点数：{len(result['excluded_nodes'])}",
        f"- 不可用可信节点数：{len(result['unavailable_nodes'])}",
        f"- 实际投票节点数：{len(result['voting_nodes'])}",
        f"- Quorum：{result['quorum']}",
        f"- 锚定 payload 数：{result['payload_count']}",
        f"- 锚定产物数：{result['artifact_count']}",
        f"- 平均提交延迟：{sum(latencies) / len(latencies):.4f} ms",
        f"- 最终区块哈希：`{result['final_block_hash']}`",
        "",
        "## Payload 类型",
        "",
    ]
    lines.extend([f"- `{payload_type}`" for payload_type in result["payload_types"]])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Anchor BLoP simulation outputs to the consortium-chain prototype.")
    parser.add_argument("--config", default=str(ROOT / "config" / "consortium_experiment.json"))
    parser.add_argument("--simulation-results", default=str(ROOT / "results" / "results.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "container_audit_results"))
    parser.add_argument("--artifact-path", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true", help="Run locally without ZooKeeper or container nodes.")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    simulation = load_json(Path(args.simulation_results))
    artifact_paths = [Path(path) for path in args.artifact_path]
    result = run_audit_chain(config=config, simulation=simulation, artifact_paths=artifact_paths, dry_run=args.dry_run)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit_chain_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(result["blocks"], output / "audit_chain_blocks.csv")
    write_report(result, output / "audit_chain_report.md")
    print(f"audit chain anchoring completed: {output.resolve()}")
    print(f"payloads: {result['payload_count']}, quorum: {result['quorum']}")
    print(f"final hash: {result['final_block_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

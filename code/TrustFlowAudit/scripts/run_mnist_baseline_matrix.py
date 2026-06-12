#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from consortium_runner import run_experiment, write_csv, write_report  # noqa: E402


def parse_ints(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def value_slug(value: float | int) -> str:
    return str(value).replace(".", "p")


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pbft_fault_tolerance(node_count: int) -> int:
    if node_count < 4:
        raise ValueError("PBFT node_count must be at least 4")
    return (node_count - 1) // 3


def high_trust_scores(node_count: int) -> list[float]:
    return [96.0 - index * 0.8 for index in range(node_count)]


def low_trust_scores(node_count: int, low_count: int) -> list[float]:
    trusted_count = max(0, node_count - low_count)
    return high_trust_scores(trusted_count) + [62.0 - index for index in range(low_count)]


def dry_run_latency_model() -> dict[str, float]:
    return {
        "base_ms": 8.0,
        "per_node_ms": 1.4,
        "quadratic_ms": 0.16,
        "jitter_ratio": 0.08,
    }


def configure_chain_scale(config: dict[str, Any], node_count: int) -> int:
    f = pbft_fault_tolerance(node_count)
    config["required_nodes"] = node_count
    config["fault_tolerance"] = f
    config.setdefault("chain", {})
    config["chain"]["dry_run_latency_model"] = dry_run_latency_model()
    return f


def scenario_config(base: dict[str, Any], scenario: str, node_count: int) -> dict[str, Any]:
    config = deepcopy(base)
    config.setdefault("chain", {})
    config.setdefault("federated_learning", {})
    config.pop("dry_run_trust_scores", None)
    config.pop("fault_injection", None)

    if scenario == "asgd_no_chain":
        config["chain"]["enabled"] = False
        config["federated_learning"]["training_strategy"] = "asgd"
        return config
    if scenario == "two_factor_no_chain":
        config["chain"]["enabled"] = False
        config["federated_learning"]["training_strategy"] = "two_factor"
        return config
    if scenario == "audit_gate_no_chain":
        config["chain"]["enabled"] = False
        config["federated_learning"]["training_strategy"] = "audit_gate"
        return config
    if scenario == "full_pbft_chain":
        configure_chain_scale(config, node_count)
        config["chain"]["enabled"] = True
        config["federated_learning"]["training_strategy"] = "two_factor"
        config["dry_run_trust_scores"] = high_trust_scores(node_count)
        return config
    if scenario == "audit_gate_chain":
        configure_chain_scale(config, node_count)
        config["chain"]["enabled"] = True
        config["federated_learning"]["training_strategy"] = "audit_gate"
        config["dry_run_trust_scores"] = high_trust_scores(node_count)
        return config
    if scenario == "low_trust_chain":
        f = configure_chain_scale(config, node_count)
        config["chain"]["enabled"] = True
        config["federated_learning"]["training_strategy"] = "two_factor"
        config["dry_run_trust_scores"] = low_trust_scores(node_count, f)
        return config
    if scenario == "fault_chain":
        f = configure_chain_scale(config, node_count)
        config["chain"]["enabled"] = True
        config["federated_learning"]["training_strategy"] = "two_factor"
        config["dry_run_trust_scores"] = high_trust_scores(node_count)
        unavailable = []
        for index in range(f):
            node_number = node_count - index
            unavailable.extend([f"dry-node-{node_number}", f"node{node_number}"])
        config["fault_injection"] = {
            "unavailable_nodes": unavailable,
            "reason": "simulated_node_leave_or_failure",
        }
        return config
    raise ValueError(f"unsupported scenario: {scenario}")


def summarize_result(
    scenario: str,
    node_count: int,
    seed: int,
    epsilon: float,
    rounds: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    latencies = [float(row["latency_ms"]) for row in result.get("blocks", [])]
    if latencies:
        ordered = sorted(latencies)
        p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
        avg_latency = statistics.mean(latencies)
        p95_latency = ordered[p95_index]
        max_latency = max(latencies)
    else:
        avg_latency = 0.0
        p95_latency = 0.0
        max_latency = 0.0
    return {
        "scenario": scenario,
        "node_count": node_count,
        "seed": seed,
        "epsilon": epsilon,
        "rounds": rounds,
        "dataset_mode": result["dataset_mode"],
        "training_strategy": result["training_strategy"],
        "execution_mode": result["execution_mode"],
        "chain_enabled": result["chain_enabled"],
        "registered_nodes": len(result["registered_nodes"]),
        "trusted_nodes": len(result["trusted_nodes"]),
        "excluded_nodes": len(result["excluded_nodes"]),
        "unavailable_nodes": len(result["unavailable_nodes"]),
        "voting_nodes": len(result["voting_nodes"]),
        "fault_tolerance": int(result["quorum"] - 1) // 2 if result["quorum"] else 0,
        "quorum": result["quorum"],
        "blocks": len(result["blocks"]),
        "final_accuracy": result["final_accuracy"],
        "avg_latency_ms": round(avg_latency, 4),
        "p95_latency_ms": round(p95_latency, 4),
        "max_latency_ms": round(max_latency, 4),
        "final_hash_prefix": result["final_block_hash"][:16],
    }


def write_summary(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = output_dir / "summary.csv"
    with summary_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    grouped: dict[tuple[str, int], list[float]] = {}
    for row in rows:
        key = (str(row["scenario"]), int(row["node_count"]))
        grouped.setdefault(key, []).append(float(row["final_accuracy"]))
    lines = [
        "# MNIST baseline matrix summary",
        "",
        "链式场景按 PBFT 的 3f+1 结构扩展节点数量；dry-run 延迟为模型估算，真实容器实测仍以现有 Compose 配置为准。",
        "",
        "| 场景 | 节点数 | 运行数 | 平均最终准确率 | 最高最终准确率 | 最低最终准确率 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (scenario, node_count), values in grouped.items():
        lines.append(
            f"| {scenario} | {node_count} | {len(values)} | {statistics.mean(values):.4f} | {max(values):.4f} | {min(values):.4f} |"
        )
    lines.extend(
        [
            "",
            "注意：`low_trust_chain` 与 `fault_chain` 主要比较审计链投票节点、提交延迟和容错状态；若训练策略相同，模型准确率不应被解释为链机制带来的提升。",
            "",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed-node MNIST baseline matrix for TrustFlowAudit.")
    parser.add_argument("--base-config", default=str(ROOT / "config" / "consortium_mnist_experiment.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "experiments" / "mnist_baseline_matrix"))
    parser.add_argument("--scenarios", default="asgd_no_chain,two_factor_no_chain,audit_gate_no_chain,full_pbft_chain,audit_gate_chain,low_trust_chain,fault_chain")
    parser.add_argument("--node-counts", default="4,7,10")
    parser.add_argument("--seeds", default="20260605,20260606,20260607")
    parser.add_argument("--epsilons", default="2,4,8")
    parser.add_argument("--rounds", type=int, default=100)
    args = parser.parse_args()

    base = load_config(Path(args.base_config))
    output_dir = Path(args.output_dir)
    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    node_counts = parse_ints(args.node_counts)
    seeds = parse_ints(args.seeds)
    epsilons = parse_floats(args.epsilons)

    summary_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_node_counts = [0] if scenario.endswith("_no_chain") else node_counts
        for node_count in scenario_node_counts:
            for seed in seeds:
                for epsilon in epsilons:
                    config = scenario_config(base, scenario, node_count)
                    config["seed"] = seed
                    config["federated_learning"]["epsilon"] = epsilon
                    config["federated_learning"]["rounds"] = args.rounds
                    node_slug = f"n{node_count}" if node_count else "n0"
                    run_dir = output_dir / "runs" / f"{scenario}_{node_slug}_seed{seed}_eps{value_slug(epsilon)}_r{args.rounds}"
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
                    result = run_experiment(config, dry_run=bool(config.get("chain", {}).get("enabled", True)))
                    (run_dir / "consortium_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    write_csv(result["blocks"], run_dir / "consortium_blocks.csv")
                    write_csv(result["metrics"], run_dir / "federated_metrics.csv")
                    write_report(result, run_dir / "container_report.md")
                    row = summarize_result(scenario, node_count, seed, epsilon, args.rounds, result)
                    summary_rows.append(row)
                    print(
                        f"{scenario} nodes={node_count} seed={seed} epsilon={epsilon} rounds={args.rounds} "
                        f"acc={row['final_accuracy']} mode={row['execution_mode']} "
                        f"voting={row['voting_nodes']} quorum={row['quorum']}"
                    )

    write_summary(summary_rows, output_dir)
    print(f"summary: {(output_dir / 'summary.csv').resolve()}")
    print(f"report: {(output_dir / 'summary.md').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

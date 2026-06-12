#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from consortium_runner import run_experiment, write_csv, write_report  # noqa: E402
from run_mnist_baseline_matrix import high_trust_scores, load_config, low_trust_scores, pbft_fault_tolerance, scenario_config  # noqa: E402


def parse_ints(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def value_slug(value: float | int) -> str:
    return str(value).replace(".", "p")


def safe_name(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-").lower()


def quote_yaml(raw: str | Path) -> str:
    return json.dumps(str(raw), ensure_ascii=False)


def volume_spec(host: str | Path, container: str, mode: str | None = None) -> str:
    spec = f"{Path(host).resolve()}:{container}"
    if mode:
        spec = f"{spec}:{mode}"
    return quote_yaml(spec)


def chain_scores(scenario: str, node_count: int) -> list[float]:
    if scenario == "low_trust_chain":
        return low_trust_scores(node_count, pbft_fault_tolerance(node_count))
    return high_trust_scores(node_count)


def render_compose(*, scenario: str, node_count: int, config_host: Path, output_host: Path) -> str:
    services: list[str] = [
        "services:",
        "  zookeeper:",
        "    image: zookeeper:3.9",
        "    environment:",
        "      ZOO_4LW_COMMANDS_WHITELIST: ruok,stat,mntr",
    ]
    scores = chain_scores(scenario, node_count)
    for index, score in enumerate(scores, start=1):
        services.extend(
            [
                f"  node{index}:",
                "    build:",
                f"      context: {quote_yaml(ROOT)}",
                "    command: python3 src/chain_node.py",
                "    environment:",
                f"      NODE_ID: node{index}",
                f"      NODE_HOST: node{index}",
                '      NODE_PORT: "8000"',
                f'      TRUST_SCORE: "{score}"',
                "      ZK_HOSTS: zookeeper:2181",
                '      REGISTER_RETRIES: "60"',
                '      REGISTER_RETRY_DELAY: "1"',
                "    volumes:",
                f"      - {volume_spec(ROOT / 'src', '/app/src', 'ro')}",
                "    depends_on:",
                "      - zookeeper",
                "    healthcheck:",
                "      test:",
                "        - CMD",
                "        - python3",
                "        - -c",
                "        - \"import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)); assert data.get('ok') and data.get('registered')\"",
                "      interval: 5s",
                "      timeout: 3s",
                "      retries: 30",
                "      start_period: 5s",
            ]
        )

    services.extend(
        [
            "  runner:",
            "    build:",
            f"      context: {quote_yaml(ROOT)}",
            "    command: python3 src/consortium_runner.py --config /app/generated/config.json --output-dir /app/out",
            "    environment:",
            "      ZK_HOSTS: zookeeper:2181",
            "      NODE_REGISTRY_PATH: /trustflowaudit/nodes",
            "    volumes:",
            f"      - {volume_spec(ROOT / 'src', '/app/src', 'ro')}",
            f"      - {volume_spec(ROOT / 'data', '/app/data', 'ro')}",
            f"      - {volume_spec(config_host.parent, '/app/generated', 'ro')}",
            f"      - {volume_spec(output_host, '/app/out')}",
            "    depends_on:",
            "      zookeeper:",
            "        condition: service_started",
        ]
    )
    for index in range(1, node_count + 1):
        services.extend(
            [
                f"      node{index}:",
                "        condition: service_healthy",
            ]
        )
    return "\n".join(services) + "\n"


def summarize_result(
    *,
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
    rejected_updates = sum(1 for row in result["metrics"] if row.get("rejected_update"))
    return {
        "scenario": scenario,
        "node_count": node_count,
        "seed": seed,
        "epsilon": epsilon,
        "rounds": rounds,
        "execution_mode": result["execution_mode"],
        "training_strategy": result["training_strategy"],
        "registered_nodes": len(result["registered_nodes"]),
        "trusted_nodes": len(result["trusted_nodes"]),
        "excluded_nodes": len(result["excluded_nodes"]),
        "unavailable_nodes": len(result["unavailable_nodes"]),
        "voting_nodes": len(result["voting_nodes"]),
        "quorum": result["quorum"],
        "blocks": len(result["blocks"]),
        "rejected_updates": rejected_updates,
        "final_accuracy": result["final_accuracy"],
        "avg_latency_ms": round(avg_latency, 4),
        "p95_latency_ms": round(p95_latency, 4),
        "max_latency_ms": round(max_latency, 4),
        "final_hash_prefix": result["final_block_hash"][:16],
    }


def write_summary(rows: list[dict[str, Any]], output_dir: Path) -> None:
    if not rows:
        return
    with (output_dir / "summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Real MNIST Docker experiment summary",
        "",
        "| 场景 | 节点数 | 轮次 | ε | 准确率 | 拒绝更新 | 投票节点 | quorum | 平均延迟(ms) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['scenario']} | {row['node_count']} | {row['rounds']} | {row['epsilon']} | "
            f"{float(row['final_accuracy']):.4f} | {row['rejected_updates']} | {row['voting_nodes']} | "
            f"{row['quorum']} | {float(row['avg_latency_ms']):.4f} |"
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_no_chain(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    result = run_experiment(config, dry_run=False)
    (run_dir / "consortium_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(result["blocks"], run_dir / "consortium_blocks.csv")
    write_csv(result["metrics"], run_dir / "federated_metrics.csv")
    write_report(result, run_dir / "container_report.md")
    return result


def run_docker_compose(*, project: str, compose_file: Path) -> None:
    command = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(compose_file),
        "up",
        "--build",
        "--abort-on-container-exit",
        "--exit-code-from",
        "runner",
        "runner",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run(["docker", "compose", "-p", project, "-f", str(compose_file), "down", "-v"], cwd=ROOT, check=False)


def load_docker_result(run_dir: Path) -> dict[str, Any]:
    result_path = run_dir / "consortium_results.json"
    if not result_path.exists():
        raise FileNotFoundError(f"missing docker result: {result_path}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Docker MNIST experiments for TrustFlowAudit.")
    parser.add_argument("--base-config", default=str(ROOT / "config" / "consortium_mnist_experiment.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "experiments" / "real_mnist_docker"))
    parser.add_argument("--scenarios", default="asgd_no_chain,full_pbft_chain,audit_gate_chain")
    parser.add_argument("--node-counts", default="4")
    parser.add_argument("--seeds", default="20260605")
    parser.add_argument("--epsilons", default="4")
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--malicious-rounds", default="17,37,57,77,97")
    parser.add_argument("--malicious-scale", type=float, default=-12.0)
    args = parser.parse_args()

    if shutil.which("docker") is None:
        raise RuntimeError("docker command not found")
    subprocess.run(["docker", "ps"], check=True, stdout=subprocess.DEVNULL)

    base = load_config(Path(args.base_config))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    node_counts = parse_ints(args.node_counts)
    seeds = parse_ints(args.seeds)
    epsilons = parse_floats(args.epsilons)
    abnormal_rounds = parse_ints(args.malicious_rounds)

    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_node_counts = [0] if scenario.endswith("_no_chain") else node_counts
        for node_count in scenario_node_counts:
            for seed in seeds:
                for epsilon in epsilons:
                    config = scenario_config(base, scenario, node_count)
                    config["seed"] = seed
                    config["federated_learning"]["epsilon"] = epsilon
                    config["federated_learning"]["rounds"] = args.rounds
                    config["federated_learning"]["malicious_update_rounds"] = abnormal_rounds
                    config["federated_learning"]["malicious_scale"] = args.malicious_scale
                    config["federated_learning"].pop("malicious_update_round", None)
                    if config.get("chain"):
                        config["chain"].pop("dry_run_latency_model", None)
                    node_slug = f"n{node_count}" if node_count else "n0"
                    run_dir = output_dir / "runs" / f"{scenario}_{node_slug}_seed{seed}_eps{value_slug(epsilon)}_r{args.rounds}"
                    run_dir.mkdir(parents=True, exist_ok=True)
                    config_path = run_dir / "config.json"
                    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
                    if scenario.endswith("_no_chain"):
                        result = run_no_chain(config, run_dir)
                    else:
                        compose_file = run_dir / "docker-compose.generated.yml"
                        compose_file.write_text(render_compose(scenario=scenario, node_count=node_count, config_host=config_path, output_host=run_dir), encoding="utf-8")
                        project = safe_name(f"tfa-{scenario}-{node_slug}-{seed}-{value_slug(epsilon)}-{args.rounds}")
                        try:
                            run_docker_compose(project=project, compose_file=compose_file)
                        finally:
                            subprocess.run(["docker", "compose", "-p", project, "-f", str(compose_file), "down", "-v"], cwd=ROOT, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        result = load_docker_result(run_dir)
                    row = summarize_result(
                        scenario=scenario,
                        node_count=node_count,
                        seed=seed,
                        epsilon=epsilon,
                        rounds=args.rounds,
                        result=result,
                    )
                    rows.append(row)
                    write_summary(rows, output_dir)
                    print(
                        f"{scenario} nodes={node_count} seed={seed} epsilon={epsilon} "
                        f"rounds={args.rounds} acc={row['final_accuracy']} rejected={row['rejected_updates']} "
                        f"mode={row['execution_mode']} voting={row['voting_nodes']} quorum={row['quorum']}"
                    )
    write_summary(rows, output_dir)
    print(f"summary: {(output_dir / 'summary.csv').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

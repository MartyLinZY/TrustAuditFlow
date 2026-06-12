#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import requests

from common import block_hash, merkle_root, payload_hash, sha256_hex


ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_or_make_mnist(config: dict[str, Any], rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, str]:
    ds = config["dataset"]
    mnist_npz = ROOT / ds.get("mnist_npz", "data/mnist.npz")
    if ds.get("mode") == "mnist" and mnist_npz.exists():
        data = np.load(mnist_npz)
        x_train = data["x_train"].reshape((-1, int(ds["feature_dim"]))).astype(np.float64) / 255.0
        y_train = data["y_train"].astype(np.int64)
        x_test = data["x_test"].reshape((-1, int(ds["feature_dim"]))).astype(np.float64) / 255.0
        y_test = data["y_test"].astype(np.int64)
        return x_train, y_train, x_test, y_test, "mnist"

    classes = int(ds["classes"])
    dim = int(ds["feature_dim"])
    train_n = int(ds["train_samples"])
    test_n = int(ds["test_samples"])
    prototypes = rng.normal(0, 1, size=(classes, dim))
    prototypes = prototypes / np.linalg.norm(prototypes, axis=1, keepdims=True)

    def sample(count: int) -> tuple[np.ndarray, np.ndarray]:
        y = np.arange(count) % classes
        rng.shuffle(y)
        x = prototypes[y] + rng.normal(0, 0.55, size=(count, dim))
        x = (x - x.mean(axis=1, keepdims=True)) / (x.std(axis=1, keepdims=True) + 1e-8)
        return x.astype(np.float64), y.astype(np.int64)

    x_train, y_train = sample(train_n)
    x_test, y_test = sample(test_n)
    return x_train, y_train, x_test, y_test, "mnist_like"


def split_clients(x: np.ndarray, y: np.ndarray, participants: int) -> list[tuple[np.ndarray, np.ndarray]]:
    indices = np.arange(len(y))
    chunks = np.array_split(indices, participants)
    return [(x[item], y[item]) for item in chunks]


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=1, keepdims=True)


def accuracy(weights: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    pred = np.argmax(x @ weights, axis=1)
    return float(np.mean(pred == y))


def loss_and_grad(weights: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    probs = softmax(x @ weights)
    y_onehot = np.zeros_like(probs)
    y_onehot[np.arange(len(y)), y] = 1.0
    loss = -np.mean(np.log(probs[np.arange(len(y)), y] + 1e-12))
    grad = x.T @ (probs - y_onehot) / len(y)
    return float(loss), grad


def wait_nodes(config: dict[str, Any], timeout: float = 90.0) -> list[dict[str, Any]]:
    from kazoo.client import KazooClient

    zk_hosts = os.getenv("ZK_HOSTS", "zookeeper:2181")
    path = os.getenv("NODE_REGISTRY_PATH", config.get("node_registry_path", "/trustflowaudit/nodes"))
    zk = KazooClient(hosts=zk_hosts)
    zk.start(timeout=20)
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if zk.exists(path):
                nodes = []
                for child in zk.get_children(path):
                    raw, _stat = zk.get(f"{path}/{child}")
                    nodes.append(json.loads(raw.decode("utf-8")))
                healthy = healthy_nodes(nodes)
                if len(healthy) >= int(config["required_nodes"]):
                    return sorted(healthy, key=lambda item: item["node_id"])
            time.sleep(1.0)
        raise TimeoutError(f"ZooKeeper registry did not reach {config['required_nodes']} nodes at {path}")
    finally:
        zk.stop()
        zk.close()


def post_json(url: str, payload: dict[str, Any], timeout: float = 5.0) -> tuple[bool, dict[str, Any]]:
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        data = resp.json()
        return resp.status_code < 400, data
    except Exception as exc:  # noqa: BLE001
        return False, {"error": str(exc)}


def get_json(url: str, timeout: float = 2.0) -> tuple[bool, dict[str, Any]]:
    try:
        resp = requests.get(url, timeout=timeout)
        data = resp.json()
        return resp.status_code < 400, data
    except Exception as exc:  # noqa: BLE001
        return False, {"error": str(exc)}


def healthy_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    healthy: list[dict[str, Any]] = []
    for node in nodes:
        ok, data = get_json(f"{node['url']}/health")
        if ok and data.get("ok") and data.get("registered"):
            healthy.append(node)
    return healthy


def commit_block(
    *,
    payload: dict[str, Any],
    nodes: list[dict[str, Any]],
    prev_hash: str,
    height: int,
    quorum: int,
) -> dict[str, Any]:
    block = {
        "height": height,
        "prev_hash": prev_hash,
        "timestamp": time.time(),
        "payload": payload,
        "payload_hash": payload_hash(payload),
        "merkle_root": merkle_root([payload_hash(payload)]),
    }
    votes = []
    vote_started = time.perf_counter()
    for node in nodes:
        ok, data = post_json(f"{node['url']}/vote", block)
        if ok and data.get("accepted"):
            votes.append({"node_id": data["node_id"], "vote": data["vote"]})
    if len(votes) < quorum:
        raise RuntimeError(f"PBFT-style quorum failed: votes={len(votes)}, quorum={quorum}")
    block["votes"] = votes
    committed = 0
    for node in nodes:
        ok, _data = post_json(f"{node['url']}/commit", block)
        committed += int(ok)
    latency_ms = (time.perf_counter() - vote_started) * 1000
    return {
        "block": {**block, "block_hash": block_hash(block)},
        "votes": len(votes),
        "committed_nodes": committed,
        "latency_ms": latency_ms,
    }


def make_dry_run_nodes(config: dict[str, Any]) -> list[dict[str, Any]]:
    required = int(config["required_nodes"])
    scores = config.get("dry_run_trust_scores") or [96.0 - index * 3.0 for index in range(required)]
    if len(scores) < required:
        raise ValueError("dry_run_trust_scores must cover required_nodes")
    return [
        {
            "node_id": f"dry-node-{index + 1}",
            "host": "local",
            "port": 0,
            "url": "local://dry-run",
            "trust_score": float(scores[index]),
            "available": True,
            "registered_at": time.time(),
        }
        for index in range(required)
    ]


def apply_fault_injection(nodes: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    fault = config.get("fault_injection", {})
    unavailable = set(fault.get("unavailable_nodes", []))
    if not unavailable:
        return nodes
    marked = []
    for node in nodes:
        item = dict(node)
        if item["node_id"] in unavailable:
            item["available"] = False
            item["fault_reason"] = fault.get("reason", "configured_unavailable")
        else:
            item["available"] = bool(item.get("available", True))
        marked.append(item)
    return marked


def available_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [node for node in nodes if bool(node.get("available", True))]


def chain_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("chain", {}).get("enabled", True))


def malicious_rounds(fl_config: dict[str, Any]) -> set[int]:
    if "malicious_update_rounds" in fl_config:
        return {int(item) for item in fl_config["malicious_update_rounds"]}
    round_id = int(fl_config.get("malicious_update_round", -1))
    return {round_id} if round_id > 0 else set()


def commit_block_dry_run(
    *,
    payload: dict[str, Any],
    nodes: list[dict[str, Any]],
    prev_hash: str,
    height: int,
    quorum: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    latency_model = payload.pop("_dry_run_latency_model", None)
    block = {
        "height": height,
        "prev_hash": prev_hash,
        "timestamp": time.time(),
        "payload": payload,
        "payload_hash": payload_hash(payload),
        "merkle_root": merkle_root([payload_hash(payload)]),
    }
    votes = [
        {
            "node_id": node["node_id"],
            "vote": sha256_hex(f"{node['node_id']}|{block_hash(block)}|{node['trust_score']}"),
        }
        for node in available_nodes(nodes)[:quorum]
    ]
    if len(votes) < quorum:
        raise RuntimeError(f"dry-run quorum failed: votes={len(votes)}, quorum={quorum}")
    block["votes"] = votes
    latency_ms = (time.perf_counter() - started) * 1000
    if latency_model:
        node_count = len(available_nodes(nodes))
        base_ms = float(latency_model.get("base_ms", 0.0))
        per_node_ms = float(latency_model.get("per_node_ms", 0.0))
        quadratic_ms = float(latency_model.get("quadratic_ms", 0.0))
        jitter_ratio = float(latency_model.get("jitter_ratio", 0.0))
        jitter = 1.0 + jitter_ratio * ((height % 7) - 3) / 3.0
        latency_ms = max(0.0, (base_ms + per_node_ms * node_count + quadratic_ms * node_count * node_count) * jitter)
    return {
        "block": {**block, "block_hash": block_hash(block)},
        "votes": len(votes),
        "committed_nodes": len(available_nodes(nodes)),
        "latency_ms": latency_ms,
    }


def run_experiment(config: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    rng = np.random.default_rng(int(config["seed"]))
    use_chain = chain_enabled(config)
    if use_chain:
        nodes = make_dry_run_nodes(config) if dry_run else wait_nodes(config)
        nodes = apply_fault_injection(nodes, config)
        trusted = [node for node in nodes if float(node["trust_score"]) >= float(config["trust_threshold"])]
        excluded = [node for node in nodes if float(node["trust_score"]) < float(config["trust_threshold"])]
        unavailable = [node for node in trusted if not bool(node.get("available", True))]
        voting_nodes = available_nodes(trusted)
        f = int(config["fault_tolerance"])
        quorum = 2 * f + 1
        if len(voting_nodes) < quorum:
            raise RuntimeError(f"available trusted nodes {len(voting_nodes)} < quorum {quorum}")
    else:
        nodes = []
        trusted = []
        excluded = []
        unavailable = []
        voting_nodes = []
        quorum = 0

    x_train, y_train, x_test, y_test, dataset_mode = load_or_make_mnist(config, rng)
    clients = split_clients(x_train, y_train, int(config["dataset"]["participants"]))
    fl = config["federated_learning"]
    rounds = int(fl["rounds"])
    lr = float(fl["learning_rate"])
    epsilon = float(fl["epsilon"])
    batch_size = int(fl["local_batch_size"])
    abnormal_rounds = malicious_rounds(fl)
    malicious_scale = float(fl.get("malicious_scale", -4.0))
    training_strategy = str(fl.get("training_strategy", "two_factor"))
    weights = np.zeros((x_train.shape[1], int(config["dataset"]["classes"])), dtype=np.float64)

    prev_hash = "GENESIS"
    block_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    last_client_round = [0 for _ in clients]

    for round_id in range(1, rounds + 1):
        client_id = (round_id - 1) % len(clients)
        cx, cy = clients[client_id]
        batch_idx = rng.choice(len(cy), size=min(batch_size, len(cy)), replace=False)
        loss, grad = loss_and_grad(weights, cx[batch_idx], cy[batch_idx])
        if round_id in abnormal_rounds:
            grad = malicious_scale * grad
            update_type = "malicious_inverted_gradient"
        else:
            update_type = "normal"
        noise = rng.laplace(0.0, 1.0 / max(epsilon, 1e-8), size=grad.shape)
        noisy_grad = grad + noise * 0.01
        candidate = weights - lr * noisy_grad
        candidate_acc = accuracy(candidate, x_test, y_test)
        current_acc = accuracy(weights, x_test, y_test)
        quality_gain = candidate_acc - current_acc
        quality_weight = 1.0 / (1.0 + math.exp(-quality_gain / max(float(fl["quality_weight_beta"]), 1e-8)))
        staleness = round_id - last_client_round[client_id]
        time_weight = math.exp(-staleness / max(float(fl["time_decay_beta"]), 1e-8))
        if training_strategy == "asgd":
            aggregate_weight = 1.0
        elif training_strategy == "two_factor":
            aggregate_weight = min(1.0, max(0.05, quality_weight * time_weight))
        elif training_strategy == "audit_gate":
            aggregate_weight = 0.0 if update_type != "normal" else min(1.0, max(0.05, quality_weight * time_weight))
        else:
            raise ValueError(f"unsupported training_strategy: {training_strategy}")
        rejected_update = aggregate_weight == 0.0
        weights = (1.0 - aggregate_weight) * weights + aggregate_weight * candidate
        last_client_round[client_id] = round_id

        update_digest = sha256_hex(noisy_grad.astype(np.float32).tobytes())
        payload = {
            "type": "federated_update",
            "round": round_id,
            "client_id": client_id,
            "dataset": dataset_mode,
            "update_type": update_type,
            "loss": round(loss, 6),
            "accuracy_before": round(current_acc, 6),
            "accuracy_after": round(accuracy(weights, x_test, y_test), 6),
            "quality_weight": round(quality_weight, 6),
            "time_weight": round(time_weight, 6),
            "aggregate_weight": round(aggregate_weight, 6),
            "epsilon": epsilon,
            "training_strategy": training_strategy,
            "rejected_update": rejected_update,
            "update_hash": update_digest,
        }
        if dry_run and config.get("chain", {}).get("dry_run_latency_model"):
            payload["_dry_run_latency_model"] = config["chain"]["dry_run_latency_model"]
        if use_chain:
            commit_fn = commit_block_dry_run if dry_run else commit_block
            commit = commit_fn(payload=payload, nodes=voting_nodes, prev_hash=prev_hash, height=round_id, quorum=quorum)
            prev_hash = commit["block"]["block_hash"]
            latency_ms = round(commit["latency_ms"], 4)
            block_rows.append(
                {
                    "height": round_id,
                    "prev_hash": commit["block"]["prev_hash"],
                    "block_hash": prev_hash,
                    "votes": commit["votes"],
                    "committed_nodes": commit["committed_nodes"],
                    "latency_ms": latency_ms,
                    "payload_hash": commit["block"]["payload_hash"],
                    "merkle_root": commit["block"]["merkle_root"],
                    "update_type": update_type,
                }
            )
        else:
            latency_ms = 0.0
        metric_rows.append(
            {
                "round": round_id,
                "client_id": client_id,
                "loss": round(loss, 6),
                "accuracy": round(accuracy(weights, x_test, y_test), 6),
                "quality_weight": round(quality_weight, 6),
                "time_weight": round(time_weight, 6),
                "aggregate_weight": round(aggregate_weight, 6),
                "chain_latency_ms": latency_ms,
                "update_type": update_type,
                "training_strategy": training_strategy,
                "rejected_update": rejected_update,
            }
        )

    return {
        "dataset_mode": dataset_mode,
        "execution_mode": "no_chain" if not use_chain else ("dry_run" if dry_run else "zookeeper_container"),
        "chain_enabled": use_chain,
        "training_strategy": training_strategy,
        "registered_nodes": nodes,
        "trusted_nodes": trusted,
        "excluded_nodes": excluded,
        "unavailable_nodes": unavailable,
        "voting_nodes": voting_nodes,
        "quorum": quorum,
        "final_accuracy": metric_rows[-1]["accuracy"],
        "final_block_hash": prev_hash if use_chain else "NO_CHAIN",
        "blocks": block_rows,
        "metrics": metric_rows,
        "reference": config["reference"],
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_report(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    latencies = [row["latency_ms"] for row in result["blocks"]]
    malicious = [row for row in result["metrics"] if row["update_type"] != "normal"]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    lines = [
        "# TrustFlowAudit 容器化联盟链测试报告",
        "",
        "## 1. 参考文献",
        "",
        result["reference"]["paper"],
        "",
        result["reference"]["dataset_note"],
        "",
        "## 2. 测试范围",
        "",
        "- 不使用 TPM/TEE。",
        f"- 执行模式：`{result['execution_mode']}`。",
        f"- 训练策略：`{result['training_strategy']}`。",
        "- 容器模式使用 ZooKeeper 维护联盟链节点注册表；dry-run 模式使用等价的本地节点清单验证核心流程。",
        "- 使用 4 个联盟链节点模拟许可链成员。",
        "- 使用 PBFT 风格投票流程：4 节点、容忍 1 个故障，至少 3 票提交。",
        "- 使用异步联邦训练更新作为链上审计对象，默认数据为离线 `mnist_like`；提供 `data/mnist.npz` 后可切换真实 MNIST。",
        "",
        "## 3. 结果",
        "",
        f"- 注册节点数：{len(result['registered_nodes'])}",
        f"- 可信节点数：{len(result['trusted_nodes'])}",
        f"- 排除节点数：{len(result['excluded_nodes'])}",
        f"- 不可用可信节点数：{len(result['unavailable_nodes'])}",
        f"- 实际投票节点数：{len(result['voting_nodes'])}",
        f"- PBFT 风格 quorum：{result['quorum']}",
        f"- 提交区块数：{len(result['blocks'])}",
        f"- 最终准确率：{result['final_accuracy']}",
        f"- 平均提交延迟：{avg_latency:.4f} ms",
        f"- 最大提交延迟：{max_latency:.4f} ms",
        f"- 恶意/异常更新轮次：{', '.join(str(row['round']) for row in malicious) if malicious else '无'}",
        f"- 最终区块哈希：`{result['final_block_hash']}`",
        "",
        "## 4. 当前缺口",
        "",
        "- 这仍是联盟链机制测试，不是真实 FISCO BCOS、Fabric 或 Tendermint 部署。",
        "- 默认数据是 `mnist_like`，如果要完全对齐高胜等《中国科学：信息科学》实验，需要提供真实 MNIST 文件。",
        "- 当前差分隐私和双因子权重是轻量实现，未完整复刻论文所有公式与隐私证明。",
        "- ZooKeeper 已接入节点治理，但尚未做动态入网/退网和节点权限变更实验。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TrustFlowAudit container consortium-chain experiment.")
    parser.add_argument("--config", default=str(ROOT / "config" / "consortium_experiment.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "container_results"))
    parser.add_argument("--dry-run", action="store_true", help="Run locally without ZooKeeper or container nodes.")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    output = Path(args.output_dir)
    result = run_experiment(config, dry_run=args.dry_run)
    output.mkdir(parents=True, exist_ok=True)
    (output / "consortium_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(result["blocks"], output / "consortium_blocks.csv")
    write_csv(result["metrics"], output / "federated_metrics.csv")
    write_report(result, output / "container_report.md")
    print(f"container experiment completed: {output.resolve()}")
    print(f"final accuracy: {result['final_accuracy']}")
    print(f"blocks: {len(result['blocks'])}, quorum: {result['quorum']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

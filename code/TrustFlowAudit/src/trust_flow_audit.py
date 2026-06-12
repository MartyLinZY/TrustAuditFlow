#!/usr/bin/env python3
"""Mechanism-level reproduction and optimization prototype for BLoP.

The single-process simulator intentionally avoids real TPM/TEE/ZooKeeper/blockchain
dependencies. Containerized ZooKeeper and consortium-chain tests live in
consortium_runner.py.
It reproduces the process shape disclosed in the BLoP paper and evaluates a
small TrustFlowAudit optimization idea under one deterministic simulator.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Node:
    node_id: str
    system_id: int
    base_trust: float
    credit_events: float = 0.0
    resource_pressure: int = 0
    trust_score: float = 100.0


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def allocate_counts(total: int, weights: list[float]) -> list[int]:
    weight_sum = sum(weights)
    raw = [total * item / weight_sum for item in weights]
    counts = [math.floor(item) for item in raw]
    remain = total - sum(counts)
    order = sorted(range(len(raw)), key=lambda idx: raw[idx] - counts[idx], reverse=True)
    for idx in order[:remain]:
        counts[idx] += 1
    return counts


def monthly_weights(months: int, pattern: str) -> list[float]:
    if pattern == "decay_fast":
        return [math.exp(-0.18 * month) + 0.05 for month in range(months)]
    if pattern == "decay_slow":
        return [math.exp(-0.08 * month) + 0.20 for month in range(months)]
    if pattern == "increase":
        return [0.45 + 0.075 * month for month in range(months)]
    if pattern == "rare":
        return [0.75 + 0.03 * month for month in range(months)]
    return [1.0 for _ in range(months)]


def build_monthly_events(config: dict[str, Any]) -> list[dict[str, int]]:
    months = int(config["months"])
    event_patterns = {
        "unverified_programs": "decay_fast",
        "data_inconsistency_risks": "decay_slow",
        "unknown_programs": "increase",
        "unfamiliarity_with_tamper_proof_systems": "decay_fast",
        "operational_errors": "decay_slow",
        "other_tampering_activities": "rare",
    }
    monthly = [dict[str, int]() for _ in range(months)]
    for group in config["paper_targets"].values():
        for event_name, total in group.items():
            counts = allocate_counts(int(total), monthly_weights(months, event_patterns[event_name]))
            for month, count in enumerate(counts):
                monthly[month][event_name] = count
    return monthly


def init_nodes(config: dict[str, Any], rng: random.Random) -> list[Node]:
    nodes: list[Node] = []
    systems = int(config["business_systems"])
    for index in range(int(config["critical_hosts"])):
        nodes.append(
            Node(
                node_id=f"N{index + 1:03d}",
                system_id=index % systems + 1,
                base_trust=rng.uniform(82.0, 98.0),
                resource_pressure=rng.choice([0, 0, 0, 1, 1, 2]),
            )
        )
    return nodes


def update_trust_scores(nodes: list[Node], rng: random.Random, month_events: dict[str, int]) -> None:
    total_events = sum(month_events.values())
    affected = max(1, min(len(nodes), int(math.sqrt(total_events))))
    for node in rng.sample(nodes, affected):
        node.credit_events += rng.random() * 0.7 + total_events / max(1, len(nodes)) * 0.002
        node.resource_pressure = min(4, max(0, node.resource_pressure + rng.choice([-1, 0, 0, 1])))
    for node in nodes:
        attestation = max(0.0, min(1.0, node.base_trust / 100.0 - node.credit_events * 0.012))
        credit = max(0.0, 1.0 - min(node.credit_events / 8.0, 1.0))
        performance = max(0.0, 1.0 - node.resource_pressure / 4.0)
        node.trust_score = 100.0 * (0.65 * attestation + 0.25 * credit + 0.10 * performance)


def trusted_nodes(nodes: list[Node], threshold: float) -> list[Node]:
    return sorted([node for node in nodes if node.trust_score >= threshold], key=lambda n: n.trust_score, reverse=True)


def consensus_latency(profile: dict[str, float], node_count: int) -> float:
    return (
        float(profile.get("base_ms", 0.0))
        + float(profile.get("per_node_ms", 0.0)) * node_count
        + float(profile.get("quadratic_ms", 0.0)) * node_count * node_count
    )


def merkle_root(items: list[str]) -> str:
    if not items:
        return hashlib.sha256(b"").hexdigest()
    level = [hashlib.sha256(item.encode("utf-8")).digest() for item in items]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


def hash_chain(events: list[str]) -> tuple[str, bool]:
    prev = "0" * 64
    for event in events:
        prev = hashlib.sha256(f"{prev}|{event}".encode("utf-8")).hexdigest()
    tampered = events.copy()
    if tampered:
        tampered[len(tampered) // 2] = tampered[len(tampered) // 2] + "|tampered"
    check_prev = "0" * 64
    for event in tampered:
        check_prev = hashlib.sha256(f"{check_prev}|{event}".encode("utf-8")).hexdigest()
    return prev, check_prev != prev


def event_total(month_events: dict[str, int]) -> int:
    return sum(month_events.values())


def high_risk_total(month_events: dict[str, int], risk_weights: dict[str, float]) -> int:
    return sum(count for name, count in month_events.items() if float(risk_weights.get(name, 0.0)) >= 0.75)


def governance_metrics(month_events: dict[str, int], agent_count: int, config: dict[str, Any]) -> dict[str, Any]:
    whitelist_checks = month_events["unverified_programs"] + month_events["unknown_programs"]
    whitelist_blocks = whitelist_checks
    tamper_alerts = (
        month_events["unfamiliarity_with_tamper_proof_systems"]
        + month_events["operational_errors"]
        + month_events["other_tampering_activities"]
    )
    critical_alerts = (
        month_events["data_inconsistency_risks"]
        + month_events["unknown_programs"]
        + month_events["other_tampering_activities"]
    )
    training_or_process_alerts = (
        month_events["unfamiliarity_with_tamper_proof_systems"] + month_events["operational_errors"]
    )
    chain_records = math.ceil((whitelist_blocks + tamper_alerts + critical_alerts) / 128)
    coverage = min(1.0, agent_count / max(1, int(config["critical_hosts"])))
    credit_penalty_events = critical_alerts + math.ceil(month_events["operational_errors"] * 0.2)
    return {
        "whitelist_checks": whitelist_checks,
        "whitelist_blocks": whitelist_blocks,
        "tamper_alerts": tamper_alerts,
        "critical_alerts": critical_alerts,
        "training_or_process_alerts": training_or_process_alerts,
        "chain_policy_records": chain_records,
        "agent_coverage": round(coverage, 4),
        "credit_penalty_events": credit_penalty_events,
    }


def summarize_governance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_whitelist_checks": sum(row["whitelist_checks"] for row in rows),
        "total_whitelist_blocks": sum(row["whitelist_blocks"] for row in rows),
        "total_tamper_alerts": sum(row["tamper_alerts"] for row in rows),
        "total_critical_alerts": sum(row["critical_alerts"] for row in rows),
        "total_chain_policy_records": sum(row["chain_policy_records"] for row in rows),
        "total_credit_penalty_events": sum(row["credit_penalty_events"] for row in rows),
        "avg_agent_coverage": round(statistics.mean(row["agent_coverage"] for row in rows), 4),
    }


def recovery_settings(config: dict[str, Any]) -> dict[str, Any]:
    evidence = config["evidence"]
    defaults = {
        "events_per_object": 128,
        "sample_rate": 0.20,
        "high_risk_sample_multiplier": 1.8,
        "commit_batch_size": 8,
        "audit_ms_per_object": 0.02,
        "recovery_ms_per_shard": 0.04,
    }
    return {**defaults, **config.get("recovery", {}), "erasure_k": evidence["erasure_k"], "erasure_m": evidence["erasure_m"]}


def damaged_shards(month_events: dict[str, int]) -> int:
    return (
        math.ceil(month_events["data_inconsistency_risks"] / 12)
        + math.ceil(month_events["unknown_programs"] / 4)
        + month_events["other_tampering_activities"] * 2
        + math.ceil(month_events["operational_errors"] / 20)
    )


def evaluate_recovery_scenarios(
    *,
    month_index: int,
    month_events: dict[str, int],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    settings = recovery_settings(config)
    total_events = event_total(month_events)
    objects = max(1, math.ceil(total_events / int(settings["events_per_object"])))
    damaged = damaged_shards(month_events)
    k = int(settings["erasure_k"])
    m = int(settings["erasure_m"])
    erasure_overhead = (k + m) / k
    base_sample_rate = float(settings["sample_rate"])
    high_risk_sample_rate = min(1.0, base_sample_rate * float(settings["high_risk_sample_multiplier"]))
    commit_batch_size = max(1, int(settings["commit_batch_size"]))
    committee_nodes = int(config["committee_size"])
    confirm_ms = consensus_latency(config["consensus_profiles"]["hotstuff"], committee_nodes)

    scenarios = [
        {
            "scenario": "multi_replica_hash_audit",
            "label": "多副本哈希抽样审计",
            "storage_overhead": 3.0,
            "sample_rate": base_sample_rate,
            "recover": True,
            "recovery_factor": 0.85,
            "record_recovery": False,
        },
        {
            "scenario": "erasure_audit_only",
            "label": "纠删码分片审计但不恢复",
            "storage_overhead": erasure_overhead,
            "sample_rate": base_sample_rate,
            "recover": False,
            "recovery_factor": 0.0,
            "record_recovery": False,
        },
        {
            "scenario": "erasure_recovery_chain",
            "label": "纠删码分片审计+恢复+链上信誉记录",
            "storage_overhead": erasure_overhead,
            "sample_rate": high_risk_sample_rate,
            "recover": True,
            "recovery_factor": 1.0,
            "record_recovery": True,
        },
    ]

    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        detected = min(damaged, math.ceil(damaged * float(scenario["sample_rate"])))
        recoverable_capacity = objects * m
        if scenario["recover"]:
            recovered = min(detected, recoverable_capacity, math.floor(detected * float(scenario["recovery_factor"])))
        else:
            recovered = 0
        unrecoverable = max(0, detected - recovered)
        reputation_penalties = math.ceil(detected / max(1, m)) if scenario["record_recovery"] else 0
        chain_records = math.ceil(detected / commit_batch_size)
        if scenario["record_recovery"]:
            chain_records += math.ceil((recovered + reputation_penalties) / commit_batch_size)
        audit_ms = objects * float(settings["audit_ms_per_object"]) + detected * 0.01
        recovery_ms = recovered * float(settings["recovery_ms_per_shard"])
        rows.append(
            {
                "month": month_index,
                "scenario": scenario["scenario"],
                "label": scenario["label"],
                "objects": objects,
                "damaged_shards": damaged,
                "detected_shards": detected,
                "recovered_shards": recovered,
                "unrecoverable_shards": unrecoverable,
                "reputation_penalties": reputation_penalties,
                "chain_records": chain_records,
                "storage_overhead": round(float(scenario["storage_overhead"]), 4),
                "audit_ms": round(audit_ms, 4),
                "recovery_ms": round(recovery_ms, 4),
                "chain_confirm_ms": round(confirm_ms * chain_records, 4),
                "closed_loop_ms": round(audit_ms + recovery_ms + confirm_ms * chain_records, 4),
            }
        )
    return rows


def summarize_recovery(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for scenario in sorted({row["scenario"] for row in rows}):
        items = [row for row in rows if row["scenario"] == scenario]
        damaged = sum(row["damaged_shards"] for row in items)
        detected = sum(row["detected_shards"] for row in items)
        recovered = sum(row["recovered_shards"] for row in items)
        summary.append(
            {
                "scenario": scenario,
                "label": items[0]["label"],
                "total_damaged_shards": damaged,
                "total_detected_shards": detected,
                "total_recovered_shards": recovered,
                "total_unrecoverable_shards": sum(row["unrecoverable_shards"] for row in items),
                "total_reputation_penalties": sum(row["reputation_penalties"] for row in items),
                "total_chain_records": sum(row["chain_records"] for row in items),
                "detection_rate": round(detected / max(1, damaged), 4),
                "recovery_success_rate": round(recovered / max(1, detected), 4),
                "closed_loop_rate": round(recovered / max(1, damaged), 4),
                "avg_storage_overhead": round(statistics.mean(row["storage_overhead"] for row in items), 4),
                "avg_closed_loop_ms": round(statistics.mean(row["closed_loop_ms"] for row in items), 4),
            }
        )
    return summary


def evaluate_strategy(
    *,
    strategy: dict[str, Any],
    trusted: list[Node],
    month_events: dict[str, int],
    config: dict[str, Any],
) -> dict[str, float | int | str]:
    total = event_total(month_events)
    risk_total = high_risk_total(month_events, config["event_risk_weights"])
    committee_mode = strategy["committee_mode"]
    if committee_mode == "all_trusted":
        consensus_nodes = max(4, len(trusted))
    else:
        consensus_nodes = min(max(4, int(config["committee_size"])), max(4, len(trusted)))

    profile = config["consensus_profiles"][strategy["consensus"]]
    commit_ms = consensus_latency(profile, consensus_nodes)
    batch_size = max(1, int(strategy.get("batch_size", 1)))
    if strategy["name"] == "trustflowaudit":
        high_batch = max(1, int(strategy.get("high_risk_batch_size", batch_size)))
        low_total = max(0, total - risk_total)
        chain_records = math.ceil(low_total / batch_size) + math.ceil(risk_total / high_batch)
    else:
        chain_records = math.ceil(total / batch_size)

    evidence = config["evidence"]
    raw_bytes = int(evidence["raw_event_bytes"]) * total
    chain_bytes = int(evidence["chain_digest_bytes"]) * chain_records
    if strategy.get("erasure_evidence"):
        storage_overhead = (int(evidence["erasure_k"]) + int(evidence["erasure_m"])) / int(evidence["erasure_k"])
    else:
        storage_overhead = 3.0

    return {
        "strategy": strategy["name"],
        "label": strategy["label"],
        "consensus_nodes": consensus_nodes,
        "chain_records": chain_records,
        "batch_commit_ms": round(commit_ms, 4),
        "amortized_event_commit_ms": round(commit_ms * chain_records / max(1, total), 6),
        "chain_log_kb": round(chain_bytes / 1024, 4),
        "raw_evidence_kb": round(raw_bytes / 1024, 4),
        "evidence_storage_overhead": round(storage_overhead, 4),
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(int(config["seed"]))
    nodes = init_nodes(config, rng)
    monthly_events = build_monthly_events(config)
    threshold = float(config["trust_threshold"])

    event_rows: list[dict[str, Any]] = []
    strategy_rows: list[dict[str, Any]] = []
    governance_rows: list[dict[str, Any]] = []
    recovery_rows: list[dict[str, Any]] = []
    chain_events: list[str] = []

    for month_index, month_events in enumerate(monthly_events, start=1):
        update_trust_scores(nodes, rng, month_events)
        current_trusted = trusted_nodes(nodes, threshold)
        agent_count = round(
            int(config["trusted_agents_start"])
            + (int(config["trusted_agents_final"]) - int(config["trusted_agents_start"]))
            * (month_index - 1)
            / max(1, int(config["months"]) - 1)
        )
        base = {
            "month": month_index,
            "trusted_agents": agent_count,
            "trusted_nodes": len(current_trusted),
            "abnormal_nodes": len(nodes) - len(current_trusted),
            "trusted_anomaly_events": sum(
                month_events[name]
                for name in ["unverified_programs", "data_inconsistency_risks", "unknown_programs"]
            ),
            "tamper_proof_events": sum(
                month_events[name]
                for name in [
                    "unfamiliarity_with_tamper_proof_systems",
                    "operational_errors",
                    "other_tampering_activities",
                ]
            ),
            **month_events,
        }
        event_rows.append(base)
        governance_rows.append({"month": month_index, **governance_metrics(month_events, agent_count, config)})
        recovery_rows.extend(evaluate_recovery_scenarios(month_index=month_index, month_events=month_events, config=config))
        for name, count in month_events.items():
            for item in range(count):
                chain_events.append(f"M{month_index}:{name}:{item}")
        for strategy in config["strategies"]:
            strategy_rows.append({"month": month_index, **evaluate_strategy(strategy=strategy, trusted=current_trusted, month_events=month_events, config=config)})

    root, tamper_detected = hash_chain(chain_events)
    merkle = merkle_root(chain_events)
    totals = {
        key: sum(row.get(key, 0) for row in event_rows)
        for key in [
            "unverified_programs",
            "data_inconsistency_risks",
            "unknown_programs",
            "unfamiliarity_with_tamper_proof_systems",
            "operational_errors",
            "other_tampering_activities",
            "trusted_anomaly_events",
            "tamper_proof_events",
        ]
    }
    summary: list[dict[str, Any]] = []
    for strategy in config["strategies"]:
        items = [row for row in strategy_rows if row["strategy"] == strategy["name"]]
        summary.append(
            {
                "strategy": strategy["name"],
                "label": strategy["label"],
                "avg_consensus_nodes": round(statistics.mean(row["consensus_nodes"] for row in items), 4),
                "total_chain_records": sum(row["chain_records"] for row in items),
                "avg_batch_commit_ms": round(statistics.mean(row["batch_commit_ms"] for row in items), 4),
                "avg_amortized_event_commit_ms": round(
                    statistics.mean(row["amortized_event_commit_ms"] for row in items), 6
                ),
                "total_chain_log_kb": round(sum(row["chain_log_kb"] for row in items), 4),
                "evidence_storage_overhead": items[-1]["evidence_storage_overhead"],
            }
        )
    return {
        "totals": totals,
        "event_rows": event_rows,
        "strategy_rows": strategy_rows,
        "strategy_summary": summary,
        "governance_rows": governance_rows,
        "governance_summary": summarize_governance(governance_rows),
        "recovery_rows": recovery_rows,
        "recovery_summary": summarize_recovery(recovery_rows),
        "integrity": {
            "event_count": len(chain_events),
            "hash_chain_root": root,
            "merkle_root": merkle,
            "tamper_detected": tamper_detected,
        },
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


def write_report(config: dict[str, Any], result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    totals = result["totals"]
    summary = result["strategy_summary"]
    governance = result["governance_summary"]
    recovery_summary = result["recovery_summary"]
    baseline = next(item for item in summary if item["strategy"] == "blop_full_pbft")
    ours = next(item for item in summary if item["strategy"] == "trustflowaudit")
    record_reduction = 1 - ours["total_chain_records"] / baseline["total_chain_records"]
    latency_reduction = 1 - ours["avg_amortized_event_commit_ms"] / baseline["avg_amortized_event_commit_ms"]
    storage_reduction = 1 - ours["evidence_storage_overhead"] / baseline["evidence_storage_overhead"]

    lines = [
        "# BLoP 机制复现与 TrustFlowAudit 优化报告",
        "",
        "## 1. 复现定位",
        "",
        "本报告对应单进程机制仿真，不是 BLoP 生产环境复现。该仿真不依赖真实 TPM/TEE、ZooKeeper 或联盟链节点，而是根据论文披露的机制和统计结果，复现可信节点度量、异常事件监测、防篡改日志、PBFT 确认和链上轻量存证过程；容器化 ZooKeeper 与联盟链节点测试由 `consortium_runner.py` 单独执行。",
        "",
        "## 2. BLoP 论文事实",
        "",
        "- BLoP 将区块链、可信计算和隐私保护计算结合，用可信计算与度量模块维护可信节点集合。",
        "- BLoP 通过可信 Agent、可信设备驱动、远程可信服务、白名单管理和事件告警机制监测异常。",
        "- BLoP 使用 PBFT 替代 PoW，以降低共识能耗并提升联盟式场景确认效率。",
        "- 论文实现使用 Python 3.10，ZooKeeper 3.4.11 用于联盟和节点治理。",
        f"- 论文部署规模为 {config['business_systems']} 个高安全需求业务系统、近 {config['critical_hosts']} 台关键主机、{config['months']} 个月。",
        f"- 本原型按论文统计校准：可信异常事件 {totals['trusted_anomaly_events']:,} 个，防篡改事件 {totals['tamper_proof_events']:,} 个。",
        "",
        "## 3. 原型机制",
        "",
        "原型将节点可信度抽象为三个指标：Attestation Records、Credit Records 和 Resource Performance，并计算综合可信评分 `T_j = A(D_j, C_j, P_j)`。达到阈值的节点进入可信节点集合，低于阈值的节点进入异常观察集合。",
        "",
        "事件侧按论文表格复现六类事件：未验证程序、数据不一致风险、未知程序、防篡改系统不熟悉、操作错误和其他篡改活动。所有事件进入哈希链和 Merkle root，用于模拟链上摘要存证与篡改检测。",
        "",
        "在可实现机制上，原型进一步把 Trusted Agent 的白名单检查、告警、阻断和信誉扣分抽象为可统计流程：未验证程序与未知程序触发白名单检查和阻断；数据不一致、未知程序和其他篡改活动进入高风险告警；操作错误和防篡改系统不熟悉进入过程告警，用于后续培训和信誉修正。",
        "",
        "## 4. BLoP 可实现机制统计",
        "",
        f"- 白名单检查次数：{governance['total_whitelist_checks']:,}。",
        f"- 白名单阻断次数：{governance['total_whitelist_blocks']:,}。",
        f"- 防篡改告警次数：{governance['total_tamper_alerts']:,}。",
        f"- 高风险告警次数：{governance['total_critical_alerts']:,}。",
        f"- 链上策略/处置记录数：{governance['total_chain_policy_records']:,}。",
        f"- 信誉扣分事件数：{governance['total_credit_penalty_events']:,}。",
        f"- 平均 Agent 覆盖率：{governance['avg_agent_coverage'] * 100:.2f}%。",
        "",
        "## 5. 优化思路",
        "",
        "TrustFlowAudit 的核心不是重写 BLoP，而是在 BLoP 已有可信度量基础上继续优化区块链过程：",
        "",
        "1. 使用可信评分选择小规模审计委员会，避免所有可信节点都参与每次 PBFT 确认。",
        "2. 对低风险事件进行 Merkle 批量存证，对高风险事件使用更小批次即时确认。",
        "3. 事件原文和大体积证据链下保存，链上只保存摘要、时间戳、责任节点和处置状态。",
        "4. 审计证据采用纠删码式冗余，降低全副本保存带来的存储压力。",
        "",
        "## 6. 仿真结果",
        "",
        "| 策略 | 平均共识节点 | 链上记录数 | 平均批次确认(ms) | 事件摊销确认(ms) | 链上日志(KB) | 证据存储冗余 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary:
        lines.append(
            f"| {item['label']} | {item['avg_consensus_nodes']} | {item['total_chain_records']} | "
            f"{item['avg_batch_commit_ms']} | {item['avg_amortized_event_commit_ms']} | "
            f"{item['total_chain_log_kb']} | {item['evidence_storage_overhead']} |"
        )
    lines.extend(
        [
            "",
            "与 BLoP 式全可信节点 PBFT 基线相比，TrustFlowAudit 在本次配置下得到：",
            "",
            f"- 链上记录数减少约 {record_reduction * 100:.2f}%。",
            f"- 事件摊销确认开销降低约 {latency_reduction * 100:.2f}%。",
            f"- 证据存储冗余降低约 {storage_reduction * 100:.2f}%。",
            f"- 哈希链篡改检测结果：{'通过' if result['integrity']['tamper_detected'] else '未检测到'}。",
            "",
            "## 7. 审计恢复闭环",
            "",
            "| 场景 | 损坏分片 | 检测分片 | 恢复分片 | 检测率 | 恢复成功率 | 闭环率 | 存储冗余 | 链上记录 | 平均闭环耗时(ms) |",
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in recovery_summary:
        lines.append(
            f"| {item['label']} | {item['total_damaged_shards']} | {item['total_detected_shards']} | "
            f"{item['total_recovered_shards']} | {item['detection_rate']} | {item['recovery_success_rate']} | "
            f"{item['closed_loop_rate']} | {item['avg_storage_overhead']} | {item['total_chain_records']} | "
            f"{item['avg_closed_loop_ms']} |"
        )
    lines.extend(
        [
            "",
            "该闭环对应短周期探索方案中的“分片存储 -> 哈希承诺 -> 抽样审计 -> 异常发现 -> 纠删码恢复 -> 链上记录 -> 节点惩罚”。当前实现仍是哈希与延迟模型级原型，但已经把发现、恢复、记录和信誉惩罚串成可复现实验输出。",
            "",
            "## 8. 与课题方向的关系",
            "",
            "该 idea 对应“可信计算优化共识算法”和“基于区块链的高效分布式数据审计方法”两个方向。可信计算部分用于形成可信节点集合和审计委员会；区块链部分用于存证、确认和责任记录；纠删码部分用于降低审计证据的分布式存储冗余。",
            "",
            "## 9. 边界与下一步",
            "",
            "- 当前只做机制仿真，不证明真实密码学安全性。",
            "- PBFT/HotStuff 延迟是模型估算，不是真实链实测。",
            "- 后续可以把事件摘要结构接入真实联盟链，或把证据存储替换为真实 Reed-Solomon 编码库。",
            "- 若需要更贴近证券数据流通场景，可把事件类型映射为授权异常、征信特征计算异常、结果哈希不一致和审计证据缺失。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TrustFlowAudit BLoP mechanism simulation.")
    parser.add_argument("--config", default=str(ROOT / "config" / "blop_simulation.json"))
    parser.add_argument("--results-dir", default=str(ROOT / "results"))
    parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    result = run(config)

    results_dir = Path(args.results_dir)
    reports_dir = Path(args.reports_dir)
    write_csv(result["event_rows"], results_dir / "events_by_month.csv")
    write_csv(result["strategy_rows"], results_dir / "strategy_by_month.csv")
    write_csv(result["strategy_summary"], results_dir / "strategy_summary.csv")
    write_csv(result["governance_rows"], results_dir / "governance_by_month.csv")
    write_csv([result["governance_summary"]], results_dir / "governance_summary.csv")
    write_csv(result["recovery_rows"], results_dir / "recovery_by_month.csv")
    write_csv(result["recovery_summary"], results_dir / "recovery_summary.csv")
    (results_dir / "results.json").write_text(
        json.dumps({"config": config, **result}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(config, result, reports_dir / "BLoP复现与TrustFlowAudit优化报告.md")

    print("TrustFlowAudit simulation completed.")
    print(f"results: {results_dir.resolve()}")
    print(f"report: {(reports_dir / 'BLoP复现与TrustFlowAudit优化报告.md').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

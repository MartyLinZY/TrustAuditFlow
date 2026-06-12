# BLoP 机制覆盖清单

## 已实现

| 机制 | 当前实现 | 主要证据 |
| :--- | :--- | :--- |
| 可信节点评分 | 使用 Attestation Records、Credit Records、Resource Performance 三类指标计算节点可信分 | `src/trust_flow_audit.py`、`results/events_by_month.csv` |
| Trusted Agent 规模变化 | 按 17 个月模拟 Agent 覆盖率变化 | `results/governance_by_month.csv` |
| 白名单检查与阻断 | 未验证程序、未知程序触发白名单检查和阻断统计 | `results/governance_summary.csv` |
| 异常告警 | 数据不一致、未知程序、防篡改异常进入告警统计 | `results/governance_summary.csv` |
| 信誉惩罚 | 高风险事件和操作错误映射为信誉扣分事件 | `results/governance_summary.csv` |
| 防篡改日志 | 所有事件进入哈希链和 Merkle root，支持篡改检测 | `results/results.json` |
| PBFT 替代 PoW | 使用 PBFT/HotStuff 延迟模型比较不同确认策略 | `results/strategy_summary.csv` |
| 可信委员会 | 基于可信分选择小规模审计委员会 | `results/strategy_summary.csv` |
| 分级批量存证 | 低风险事件批量上链，高风险事件小批次即时确认 | `src/trust_flow_audit.py` |
| 纠删码证据冗余 | 用 `(k+m)/k` 估算纠删码证据冗余 | `results/strategy_summary.csv` |
| 审计恢复闭环 | 模拟分片损坏、抽样检测、纠删码恢复、链上记录和信誉惩罚 | `results/recovery_summary.csv` |
| ZooKeeper 节点治理 | 容器节点启动后注册到 ZooKeeper，runner 从注册表读取健康节点 | `src/chain_node.py`、`src/consortium_runner.py`、`docker-compose.yml` |
| 联盟链投票提交 | 4 节点 PBFT 风格投票，quorum=3 后提交区块 | `src/consortium_runner.py`、`src/verify_results.py` |
| 低可信节点排除 | 低可信节点注册但不进入共识投票集合 | `config/consortium_low_trust_experiment.json`、`docker-compose.lowtrust.yml` |
| 故障节点容错 | 节点注册且可信，但在共识阶段不可用；剩余 3 个可信节点满足 quorum 后继续提交 | `config/consortium_fault_experiment.json`、`docker-compose.fault.yml` |
| 联邦学习过程审计 | 使用异步联邦更新作为链上审计对象，记录模型更新摘要、质量权重和异常轮次 | `src/consortium_runner.py` |
| BLoP 机制结果上链 | 将事件完整性、治理统计、策略优化、审计恢复闭环和产物清单锚定为联盟链区块 | `src/audit_chain_runner.py`、`src/verify_audit_chain.py` |

## 暂不实现或仅做替代

| 机制 | 当前处理 |
| :--- | :--- |
| TPM/TEE/SGX 可信硬件 | 明确不使用，改为软件可信评分和可审计日志替代 |
| 真实 TCG 完整性度量 | 不读取硬件 PCR，不做远程证明，使用 Attestation Records 抽象替代 |
| 真实 FISCO BCOS/Fabric/Tendermint | 当前是 PBFT 风格许可链原型，已完成 ZooKeeper + Docker Compose 容器实测，但不声称等价于真实联盟链框架 |
| 真实 Reed-Solomon 编码库 | 当前做机制级恢复模型，后续可替换为真实 RS 编码库 |
| PDP/PoR 密码学证明 | 当前用哈希承诺和 Merkle root 替代，不声称完整密码学安全 |
| 动态入网/退网故障恢复 | 已有 ZooKeeper 注册基础，低可信排除和故障节点容错已通过真实容器测试，动态准入、退网和自动恢复仍未实现 |

## 当前验证命令

```bash
python3 src/trust_flow_audit.py --config config/blop_simulation.json
python3 src/verify_simulation.py --results-dir results
python3 src/consortium_runner.py --config config/consortium_experiment.json --output-dir container_results_dryrun --dry-run
python3 src/verify_results.py --result-dir container_results_dryrun --expect-mode dry_run --expect-blocks 30 --expect-quorum 3 --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-abnormal-round 17
python3 src/consortium_runner.py --config config/consortium_low_trust_experiment.json --output-dir container_results_lowtrust_dryrun --dry-run
python3 src/verify_results.py --result-dir container_results_lowtrust_dryrun --expect-mode dry_run --expect-blocks 30 --expect-quorum 3 --expect-registered 4 --expect-trusted 3 --expect-excluded 1 --expect-abnormal-round 17
python3 src/audit_chain_runner.py --config config/consortium_experiment.json --simulation-results results/results.json --artifact-path reports/BLoP复现与TrustFlowAudit优化报告.md --artifact-path reports/BLoP机制覆盖清单.md --output-dir container_audit_results_dryrun --dry-run
python3 src/verify_audit_chain.py --result-dir container_audit_results_dryrun --expect-mode dry_run --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-quorum 3
python3 src/consortium_runner.py --config config/consortium_fault_experiment.json --output-dir container_results_fault_dryrun --dry-run
python3 src/verify_results.py --result-dir container_results_fault_dryrun --expect-mode dry_run --expect-blocks 30 --expect-quorum 3 --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-unavailable 1 --expect-voting 3 --expect-abnormal-round 17
```

真实容器验证可直接运行：

```bash
scripts/run_container_checks.sh
```

该脚本已完成 6 组测试：默认 FL 链、默认 BLoP 结果上链、低可信节点 FL、低可信节点 BLoP 上链、故障节点 FL、故障节点 BLoP 上链。

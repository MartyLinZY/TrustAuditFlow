# TrustFlowAudit 目标验收记录

## 目标拆解

| 目标项 | 当前状态 | 证据 |
| :--- | :--- | :--- |
| 复现 BLoP 可实现机制 | 已完成机制级复现 | `src/trust_flow_audit.py`、`reports/BLoP机制覆盖清单.md` |
| 不使用 TPM/TEE | 已按要求排除 | README“定位”、`reports/BLoP机制覆盖清单.md` |
| ZooKeeper 节点治理 | 已完成容器内注册和发现 | `docker-compose.yml`、`src/chain_node.py`、`src/consortium_runner.py` |
| 放到容器中运行 | 已完成 Docker Compose 编排 | `Dockerfile`、`docker-compose.yml`、`docker-compose.lowtrust.yml`、`docker-compose.fault.yml` |
| 联盟链测试 | 已完成 PBFT 风格 4 节点联盟链测试 | `scripts/run_container_checks.sh`、`container_results*/consortium_results.json` |
| BLoP 机制结果上链 | 已完成 5 类 payload 锚定 | `src/audit_chain_runner.py`、`container_audit_results*/audit_chain_results.json` |
| 低可信节点排除 | 已完成真实容器验证 | `container_results_lowtrust/consortium_results.json`、`container_audit_results_lowtrust/audit_chain_results.json` |
| 故障节点容错 | 已完成真实容器验证 | `container_results_fault/consortium_results.json`、`container_audit_results_fault/audit_chain_results.json` |
| PPT 计划中的轻量审计闭环 | 已实现机制模型 | `results/recovery_summary.csv`、`reports/BLoP复现与TrustFlowAudit优化报告.md` |

## 真实容器测试证据

已执行：

```bash
scripts/run_container_checks.sh
```

该脚本完成 6 组真实 Docker Compose 测试：

| 测试 | 模式 | 关键校验 | 最终哈希 |
| :--- | :--- | :--- | :--- |
| 默认 FL 联盟链 | `zookeeper_container` | 30 个区块、4 个可信投票节点、quorum=3 | `580475a37aa9a17d0a3cdc7ef7fae58626f983e4ec6533796899d68e1fa55752` |
| 默认 BLoP 结果上链 | `zookeeper_container` | 5 类 payload、4 个可信投票节点、quorum=3 | `735692e736453b7f45a83efa307c90e0cabf20395f2ed5e1a76dc2a7cf751e7d` |
| 低可信 FL 联盟链 | `zookeeper_container` | 1 个低可信节点被排除、3 个可信投票节点、quorum=3 | `3b54c66485b9debe7d4a6c5838b6c843bde58aaec9faec2ecae2bd7e3f694272` |
| 低可信 BLoP 结果上链 | `zookeeper_container` | 1 个低可信节点被排除、3 个可信投票节点、quorum=3 | `738e0dab88249392804f8ec0c3aec2179481a3fa4c632068c7cbdff72fc4ec09` |
| 故障 FL 联盟链 | `zookeeper_container` | 1 个可信节点不可用、3 个投票节点、quorum=3 | `0520aa6548af4ae88096dd254e04e2f6d1d79896612bbc63cba8f6973a62a7f7` |
| 故障 BLoP 结果上链 | `zookeeper_container` | 1 个可信节点不可用、3 个投票节点、quorum=3 | `1784057f9921cd93da76297bf64c262e85e1f542d4722d601f8fac25f0adebcb` |

## 本地复核命令

```bash
python3 -m py_compile src/common.py src/chain_node.py src/consortium_runner.py src/audit_chain_runner.py src/trust_flow_audit.py src/verify_results.py src/verify_simulation.py src/verify_audit_chain.py
docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml config
docker compose -f docker-compose.yml -f docker-compose.fault.yml config
python3 src/verify_results.py --result-dir container_results --expect-mode zookeeper_container --expect-blocks 30 --expect-quorum 3 --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-unavailable 0 --expect-voting 4 --expect-abnormal-round 17
python3 src/verify_results.py --result-dir container_results_lowtrust --expect-mode zookeeper_container --expect-blocks 30 --expect-quorum 3 --expect-registered 4 --expect-trusted 3 --expect-excluded 1 --expect-unavailable 0 --expect-voting 3 --expect-abnormal-round 17
python3 src/verify_results.py --result-dir container_results_fault --expect-mode zookeeper_container --expect-blocks 30 --expect-quorum 3 --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-unavailable 1 --expect-voting 3 --expect-abnormal-round 17
python3 src/verify_audit_chain.py --result-dir container_audit_results --expect-mode zookeeper_container --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-unavailable 0 --expect-voting 4 --expect-quorum 3 --expect-artifacts 1
python3 src/verify_audit_chain.py --result-dir container_audit_results_lowtrust --expect-mode zookeeper_container --expect-registered 4 --expect-trusted 3 --expect-excluded 1 --expect-unavailable 0 --expect-voting 3 --expect-quorum 3 --expect-artifacts 1
python3 src/verify_audit_chain.py --result-dir container_audit_results_fault --expect-mode zookeeper_container --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-unavailable 1 --expect-voting 3 --expect-quorum 3 --expect-artifacts 1
```

上述命令已通过。

## 边界

- 当前是 PBFT 风格许可链原型，不是真实 FISCO BCOS、Fabric 或 Tendermint。
- 默认数据集是 `mnist_like`，不是完整 MNIST；提供 `data/mnist.npz` 后可切换。
- 纠删码恢复是机制模型，不是真实 Reed-Solomon 编码库。
- 不实现 TPM/TEE/SGX，也不做真实 TCG/PCR 远程证明。
- ZooKeeper 已用于注册、发现和节点治理测试，但动态准入、退网和自动恢复仍未实现。

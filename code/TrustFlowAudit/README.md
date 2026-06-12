# TrustFlowAudit

面向数据流通场景的可信过程审计与联盟链校验原型。

本项目用于机制级复现 BLoP 论文中的可信评分、异常监测、防篡改日志、PBFT 确认流程和节点治理思想，并在此基础上实现一个轻量 TrustFlowAudit 方案：用联盟链委员会完成模型/证据摘要校验，用哈希链和 Merkle root 固化审计证据，用分级批量存证降低链上写入压力。

## 定位

- 这是研究原型，不是 BLoP 生产系统复刻。
- 不使用 TPM/TEE；可信根暂以软件可信评分、节点注册、哈希链和共识投票替代。
- 容器化联盟链测试使用 ZooKeeper 做节点注册与成员发现。
- 默认使用离线 `mnist_like` 数据；提供真实 `data/mnist.npz` 后可切换为 MNIST。
- 不修改根目录下原有文献审计平台、脚本和输出。

## 目录

```text
TrustFlowAudit/
  config/
    blop_simulation.json          # BLoP/TrustFlowAudit 机制仿真配置
    consortium_experiment.json    # 联盟链 + 异步联邦学习测试配置
  src/
    trust_flow_audit.py           # 单进程机制仿真
    chain_node.py                 # 容器联盟链节点
    consortium_runner.py          # 联盟链测试 runner
    common.py                     # 哈希、Merkle root 等公共函数
  scripts/
    run_local_checks.sh           # 本地 dry-run 全量检查
    run_container_checks.sh       # Docker Compose 容器全量检查
  docker-compose.yml
  Dockerfile
```

## 一键验证

本地 dry-run 检查不需要 Docker daemon，覆盖语法检查、三套 Compose 配置、BLoP 机制仿真、默认/低可信/故障联盟链 dry-run，以及 BLoP 结果上链 dry-run：

```bash
cd code/TrustFlowAudit
scripts/run_local_checks.sh
```

真实容器检查需要 Docker Desktop 或 Docker daemon 已启动，覆盖默认、低可信节点排除、可信节点故障三类场景，并分别验证 FL 链和 BLoP 机制结果上链：

```bash
cd code/TrustFlowAudit
scripts/run_container_checks.sh
```

## 运行 1：BLoP 机制仿真

```bash
cd code/TrustFlowAudit
python3 src/trust_flow_audit.py --config config/blop_simulation.json
python3 src/verify_simulation.py --results-dir results
```

输出：

- `results/events_by_month.csv`
- `results/strategy_summary.csv`
- `results/governance_summary.csv`
- `results/recovery_summary.csv`
- `results/results.json`
- `reports/BLoP复现与TrustFlowAudit优化报告.md`
- `reports/BLoP机制覆盖清单.md`
- `reports/TrustFlowAudit目标验收记录.md`

## 运行 2：本地 dry-run 联盟链测试

该模式不需要 Docker、ZooKeeper 或 Kazoo，用于快速检查异步联邦更新、PBFT 风格投票、哈希链、Merkle root 和报告生成是否连通。

```bash
cd code/TrustFlowAudit
python3 src/consortium_runner.py \
  --config config/consortium_experiment.json \
  --output-dir container_results_dryrun \
  --dry-run

python3 src/verify_results.py \
  --result-dir container_results_dryrun \
  --expect-mode dry_run \
  --expect-blocks 30 \
  --expect-quorum 3 \
  --expect-registered 4 \
  --expect-trusted 4 \
  --expect-excluded 0 \
  --expect-unavailable 0 \
  --expect-voting 4 \
  --expect-abnormal-round 17
```

输出：

- `container_results_dryrun/consortium_results.json`
- `container_results_dryrun/consortium_blocks.csv`
- `container_results_dryrun/federated_metrics.csv`
- `container_results_dryrun/container_report.md`

## 运行 2.1：低可信节点 dry-run 测试

该场景模拟 4 个节点均注册成功，但第 4 个节点可信分低于阈值，只保留 3 个可信节点参与 PBFT 风格投票。

```bash
cd code/TrustFlowAudit
python3 src/consortium_runner.py \
  --config config/consortium_low_trust_experiment.json \
  --output-dir container_results_lowtrust_dryrun \
  --dry-run

python3 src/verify_results.py \
  --result-dir container_results_lowtrust_dryrun \
  --expect-mode dry_run \
  --expect-blocks 30 \
  --expect-quorum 3 \
  --expect-registered 4 \
  --expect-trusted 3 \
  --expect-excluded 1 \
  --expect-unavailable 0 \
  --expect-voting 3 \
  --expect-abnormal-round 17
```

## 运行 2.2：故障节点 dry-run 测试

该场景模拟 4 个节点均注册且可信，但第 4 个节点在共识阶段不可用。系统保留 3 个可投票可信节点，仍满足 `f=1` 时的 quorum=3。

```bash
cd code/TrustFlowAudit
python3 src/consortium_runner.py \
  --config config/consortium_fault_experiment.json \
  --output-dir container_results_fault_dryrun \
  --dry-run

python3 src/verify_results.py \
  --result-dir container_results_fault_dryrun \
  --expect-mode dry_run \
  --expect-blocks 30 \
  --expect-quorum 3 \
  --expect-registered 4 \
  --expect-trusted 4 \
  --expect-excluded 0 \
  --expect-unavailable 1 \
  --expect-voting 3 \
  --expect-abnormal-round 17
```

## 运行 2.3：BLoP 机制结果 dry-run 上链

该模式把 `results/results.json` 中的 BLoP 机制仿真结果锚定为 5 类联盟链 payload：事件完整性、治理统计、策略优化、审计恢复闭环和产物清单。

```bash
cd code/TrustFlowAudit
python3 src/trust_flow_audit.py --config config/blop_simulation.json
python3 src/audit_chain_runner.py \
  --config config/consortium_experiment.json \
  --simulation-results results/results.json \
  --artifact-path reports/BLoP复现与TrustFlowAudit优化报告.md \
  --artifact-path reports/BLoP机制覆盖清单.md \
  --output-dir container_audit_results_dryrun \
  --dry-run

python3 src/verify_audit_chain.py \
  --result-dir container_audit_results_dryrun \
  --expect-mode dry_run \
  --expect-registered 4 \
  --expect-trusted 4 \
  --expect-excluded 0 \
  --expect-unavailable 0 \
  --expect-voting 4 \
  --expect-quorum 3
```

低可信节点版本：

```bash
python3 src/audit_chain_runner.py \
  --config config/consortium_low_trust_experiment.json \
  --simulation-results results/results.json \
  --artifact-path reports/BLoP复现与TrustFlowAudit优化报告.md \
  --artifact-path reports/BLoP机制覆盖清单.md \
  --output-dir container_audit_results_lowtrust_dryrun \
  --dry-run

python3 src/verify_audit_chain.py \
  --result-dir container_audit_results_lowtrust_dryrun \
  --expect-mode dry_run \
  --expect-registered 4 \
  --expect-trusted 3 \
  --expect-excluded 1 \
  --expect-unavailable 0 \
  --expect-voting 3 \
  --expect-quorum 3
```

故障节点版本：

```bash
python3 src/audit_chain_runner.py \
  --config config/consortium_fault_experiment.json \
  --simulation-results results/results.json \
  --artifact-path reports/BLoP复现与TrustFlowAudit优化报告.md \
  --artifact-path reports/BLoP机制覆盖清单.md \
  --output-dir container_audit_results_fault_dryrun \
  --dry-run

python3 src/verify_audit_chain.py \
  --result-dir container_audit_results_fault_dryrun \
  --expect-mode dry_run \
  --expect-registered 4 \
  --expect-trusted 4 \
  --expect-excluded 0 \
  --expect-unavailable 1 \
  --expect-voting 3 \
  --expect-quorum 3
```

## 运行 3：Docker Compose 联盟链测试

需要 Docker Desktop 或 Docker daemon 已启动。

```bash
cd code/TrustFlowAudit
docker compose up --build --abort-on-container-exit runner
docker compose down

python3 src/verify_results.py \
  --result-dir container_results \
  --expect-mode zookeeper_container \
  --expect-blocks 30 \
  --expect-quorum 3 \
  --expect-registered 4 \
  --expect-trusted 4 \
  --expect-excluded 0 \
  --expect-unavailable 0 \
  --expect-voting 4 \
  --expect-abnormal-round 17
```

该流程会启动：

- `zookeeper`：节点注册表
- `node1` 至 `node4`：4 个许可链成员节点
- `runner`：读取 ZooKeeper 节点清单，发起异步联邦训练更新，并要求至少 3 个可信节点投票确认后提交区块

输出目录为 `container_results/`。

BLoP 机制结果容器上链：

```bash
cd code/TrustFlowAudit
docker compose up --build --abort-on-container-exit audit-runner
python3 src/verify_audit_chain.py --result-dir container_audit_results --expect-mode zookeeper_container --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-unavailable 0 --expect-voting 4 --expect-quorum 3
docker compose down
```

低可信节点容器场景：

```bash
cd code/TrustFlowAudit
docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml up --build --abort-on-container-exit runner
docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml down

python3 src/verify_results.py \
  --result-dir container_results_lowtrust \
  --expect-mode zookeeper_container \
  --expect-blocks 30 \
  --expect-quorum 3 \
  --expect-registered 4 \
  --expect-trusted 3 \
  --expect-excluded 1 \
  --expect-unavailable 0 \
  --expect-voting 3 \
  --expect-abnormal-round 17
```

低可信节点 BLoP 机制结果容器上链：

```bash
cd code/TrustFlowAudit
docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml up --build --abort-on-container-exit audit-runner
python3 src/verify_audit_chain.py --result-dir container_audit_results_lowtrust --expect-mode zookeeper_container --expect-registered 4 --expect-trusted 3 --expect-excluded 1 --expect-unavailable 0 --expect-voting 3 --expect-quorum 3
docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml down
```

故障节点容器场景：

```bash
cd code/TrustFlowAudit
docker compose -f docker-compose.yml -f docker-compose.fault.yml up --build --abort-on-container-exit runner
python3 src/verify_results.py --result-dir container_results_fault --expect-mode zookeeper_container --expect-blocks 30 --expect-quorum 3 --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-unavailable 1 --expect-voting 3 --expect-abnormal-round 17
docker compose -f docker-compose.yml -f docker-compose.fault.yml down
```

故障节点 BLoP 机制结果容器上链：

```bash
cd code/TrustFlowAudit
docker compose -f docker-compose.yml -f docker-compose.fault.yml up --build --abort-on-container-exit audit-runner
python3 src/verify_audit_chain.py --result-dir container_audit_results_fault --expect-mode zookeeper_container --expect-registered 4 --expect-trusted 4 --expect-excluded 0 --expect-unavailable 1 --expect-voting 3 --expect-quorum 3
docker compose -f docker-compose.yml -f docker-compose.fault.yml down
```

## 使用真实 MNIST

默认配置使用可离线运行的 `mnist_like` 数据。若要对齐高胜等《中国科学：信息科学》实验，把 MNIST npz 文件放到：

```text
TrustFlowAudit/data/mnist.npz
```

文件需要包含：

- `x_train`
- `y_train`
- `x_test`
- `y_test`

然后将 [config/consortium_experiment.json](config/consortium_experiment.json) 中的：

```json
"mode": "mnist_like"
```

改为：

```json
"mode": "mnist"
```

## 节点规模与 baseline 扩展实验

容器实测仍保留现有 4 节点复现路径；baseline、隐私预算和节点数量扩展使用 dry-run 节点清单完成。节点规模默认使用 PBFT 常见的 `4/7/10`，对应 `f=1/2/3` 和 quorum `3/5/7`。

快速检查：

```bash
cd code/TrustFlowAudit
python3 scripts/run_mnist_baseline_matrix.py \
  --output-dir experiments/mnist_baseline_matrix_smoke \
  --scenarios asgd_no_chain,full_pbft_chain \
  --node-counts 4,7 \
  --seeds 20260605 \
  --epsilons 4 \
  --rounds 3
```

首轮扩展：

```bash
cd code/TrustFlowAudit
python3 scripts/run_mnist_baseline_matrix.py \
  --output-dir experiments/mnist_node_scale_round30 \
  --node-counts 4,7,10 \
  --seeds 20260605 \
  --epsilons 2,4,8 \
  --rounds 30
```

更接近原文设置的完整矩阵：

```bash
cd code/TrustFlowAudit
python3 scripts/run_mnist_baseline_matrix.py \
  --output-dir experiments/mnist_node_scale_round100 \
  --node-counts 4,7,10 \
  --seeds 20260605,20260606,20260607 \
  --epsilons 2,4,8 \
  --rounds 100
```

输出：

- `summary.csv`：每组场景、节点数、seed、epsilon、最终准确率、投票节点数、quorum、提交延迟。
- `summary.md`：按场景聚合的简要说明。
- `runs/*/`：每次运行的配置、指标、区块和报告。

真实 Docker 实验：

```bash
cd code/TrustFlowAudit
python3 scripts/run_real_mnist_experiments.py \
  --output-dir experiments/real_mnist_docker_attack_r100 \
  --scenarios asgd_no_chain,two_factor_no_chain,full_pbft_chain,audit_gate_chain \
  --node-counts 4 \
  --seeds 20260605 \
  --epsilons 4 \
  --rounds 100 \
  --malicious-rounds 17,37,57,77,97 \
  --malicious-scale -12
```

真实节点规模扩展：

```bash
cd code/TrustFlowAudit
python3 scripts/run_real_mnist_experiments.py \
  --output-dir experiments/real_mnist_docker_attack_nodes_r100 \
  --scenarios full_pbft_chain,audit_gate_chain \
  --node-counts 7,10 \
  --seeds 20260605 \
  --epsilons 4 \
  --rounds 100 \
  --malicious-rounds 17,37,57,77,97 \
  --malicious-scale -12
```

## 当前实验边界

- 联盟链为 PBFT 风格机制测试，不是真实 FISCO BCOS、Fabric 或 Tendermint 部署。
- ZooKeeper 目前负责成员注册和发现；低可信排除与节点故障场景已完成真实容器验证，动态准入、权限变更和自动恢复仍未实现。
- 差分隐私、双因子权重和异常更新检测是轻量实现，尚未完整复刻论文全部公式和证明。
- 哈希链、Merkle root 和投票结果可证明审计流程连通，但不等价于完整密码学安全证明。

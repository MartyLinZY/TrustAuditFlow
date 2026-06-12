#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/10] Python syntax check"
python3 -m py_compile \
  src/common.py \
  src/chain_node.py \
  src/consortium_runner.py \
  src/audit_chain_runner.py \
  src/trust_flow_audit.py \
  src/verify_results.py \
  src/verify_simulation.py \
  src/verify_audit_chain.py \
  scripts/run_mnist_baseline_matrix.py \
  scripts/run_real_mnist_experiments.py

echo "[2/10] Docker Compose config check: default"
docker compose config >/dev/null

echo "[3/10] Docker Compose config check: low-trust override"
docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml config >/dev/null

echo "[4/10] Docker Compose config check: fault override"
docker compose -f docker-compose.yml -f docker-compose.fault.yml config >/dev/null

echo "[5/10] BLoP mechanism simulation"
python3 src/trust_flow_audit.py --config config/blop_simulation.json
python3 src/verify_simulation.py --results-dir results

echo "[6/10] Consortium dry-run: default"
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

echo "[7/10] Consortium dry-run: low-trust node excluded"
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

echo "[8/10] Consortium dry-run: trusted node unavailable"
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

echo "[9/10] BLoP audit-chain dry-runs"
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
  --expect-quorum 3 \
  --expect-artifacts 2

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
  --expect-quorum 3 \
  --expect-artifacts 2

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
  --expect-quorum 3 \
  --expect-artifacts 2

echo "[10/10] Local TrustFlowAudit checks passed"

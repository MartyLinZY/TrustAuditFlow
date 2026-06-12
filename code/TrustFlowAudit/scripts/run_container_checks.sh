#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! docker ps >/dev/null 2>&1; then
  echo "Docker daemon is not available. Start Docker Desktop, then rerun this script." >&2
  exit 1
fi

cleanup_default() {
  docker compose down >/dev/null 2>&1 || true
}

cleanup_lowtrust() {
  docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml down >/dev/null 2>&1 || true
}

cleanup_fault() {
  docker compose -f docker-compose.yml -f docker-compose.fault.yml down >/dev/null 2>&1 || true
}

echo "[1/6] Container consortium test: default FL chain"
trap cleanup_default EXIT
docker compose up --build --abort-on-container-exit runner
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
cleanup_default
trap - EXIT

echo "[2/6] Container BLoP audit-chain test: default"
trap cleanup_default EXIT
docker compose up --build --abort-on-container-exit audit-runner
python3 src/verify_audit_chain.py \
  --result-dir container_audit_results \
  --expect-mode zookeeper_container \
  --expect-registered 4 \
  --expect-trusted 4 \
  --expect-excluded 0 \
  --expect-unavailable 0 \
  --expect-voting 4 \
  --expect-quorum 3 \
  --expect-artifacts 1
cleanup_default
trap - EXIT

echo "[3/6] Container consortium test: low-trust node excluded"
trap cleanup_lowtrust EXIT
docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml up --build --abort-on-container-exit runner
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
cleanup_lowtrust
trap - EXIT

echo "[4/6] Container BLoP audit-chain test: low-trust node excluded"
trap cleanup_lowtrust EXIT
docker compose -f docker-compose.yml -f docker-compose.lowtrust.yml up --build --abort-on-container-exit audit-runner
python3 src/verify_audit_chain.py \
  --result-dir container_audit_results_lowtrust \
  --expect-mode zookeeper_container \
  --expect-registered 4 \
  --expect-trusted 3 \
  --expect-excluded 1 \
  --expect-unavailable 0 \
  --expect-voting 3 \
  --expect-quorum 3 \
  --expect-artifacts 1
cleanup_lowtrust
trap - EXIT

echo "[5/6] Container consortium test: trusted node unavailable"
trap cleanup_fault EXIT
docker compose -f docker-compose.yml -f docker-compose.fault.yml up --build --abort-on-container-exit runner
python3 src/verify_results.py \
  --result-dir container_results_fault \
  --expect-mode zookeeper_container \
  --expect-blocks 30 \
  --expect-quorum 3 \
  --expect-registered 4 \
  --expect-trusted 4 \
  --expect-excluded 0 \
  --expect-unavailable 1 \
  --expect-voting 3 \
  --expect-abnormal-round 17
cleanup_fault
trap - EXIT

echo "[6/6] Container BLoP audit-chain test: trusted node unavailable"
trap cleanup_fault EXIT
docker compose -f docker-compose.yml -f docker-compose.fault.yml up --build --abort-on-container-exit audit-runner
python3 src/verify_audit_chain.py \
  --result-dir container_audit_results_fault \
  --expect-mode zookeeper_container \
  --expect-registered 4 \
  --expect-trusted 4 \
  --expect-excluded 0 \
  --expect-unavailable 1 \
  --expect-voting 3 \
  --expect-quorum 3 \
  --expect-artifacts 1
cleanup_fault
trap - EXIT

echo "Container TrustFlowAudit checks passed"

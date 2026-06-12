#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import sys
import time
from typing import Any

from flask import Flask, jsonify, request
from kazoo.client import KazooClient
from kazoo.exceptions import KazooException

from common import block_hash, canonical_json, payload_hash, sha256_hex


NODE_ID = os.getenv("NODE_ID", "node")
NODE_HOST = os.getenv("NODE_HOST", NODE_ID)
NODE_PORT = int(os.getenv("NODE_PORT", "8000"))
TRUST_SCORE = float(os.getenv("TRUST_SCORE", "90"))
ZK_HOSTS = os.getenv("ZK_HOSTS", "zookeeper:2181")
REGISTRY_PATH = os.getenv("NODE_REGISTRY_PATH", "/trustflowaudit/nodes")
TRUST_THRESHOLD = float(os.getenv("TRUST_THRESHOLD", "70"))
REGISTER_RETRIES = int(os.getenv("REGISTER_RETRIES", "30"))
REGISTER_RETRY_DELAY = float(os.getenv("REGISTER_RETRY_DELAY", "1.0"))

app = Flask(__name__)
ledger: list[dict[str, Any]] = []
zk: KazooClient | None = None
registered_at: float | None = None


def register_node() -> None:
    global registered_at, zk
    last_error: Exception | None = None
    for attempt in range(1, REGISTER_RETRIES + 1):
        try:
            zk = KazooClient(hosts=ZK_HOSTS)
            zk.start(timeout=15)
            zk.ensure_path(REGISTRY_PATH)
            node_path = f"{REGISTRY_PATH}/{NODE_ID}"
            registered_at = time.time()
            payload = {
                "node_id": NODE_ID,
                "host": NODE_HOST,
                "port": NODE_PORT,
                "url": f"http://{NODE_HOST}:{NODE_PORT}",
                "trust_score": TRUST_SCORE,
                "registered_at": registered_at,
            }
            if zk.exists(node_path):
                zk.delete(node_path)
            zk.create(node_path, canonical_json(payload).encode("utf-8"), ephemeral=True)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if zk is not None:
                try:
                    zk.stop()
                    zk.close()
                except KazooException:
                    pass
                zk = None
            time.sleep(REGISTER_RETRY_DELAY)
    raise RuntimeError(f"node {NODE_ID} failed to register in ZooKeeper after {REGISTER_RETRIES} attempts") from last_error


def vote_for_block(block: dict[str, Any]) -> tuple[bool, str]:
    if TRUST_SCORE < TRUST_THRESHOLD:
        return False, "node below trust threshold"
    payload = block.get("payload")
    if not isinstance(payload, dict):
        return False, "missing payload"
    if block.get("payload_hash") != payload_hash(payload):
        return False, "payload hash mismatch"
    if block.get("height", 0) != len(ledger) + 1:
        return False, "height mismatch"
    expected_prev = ledger[-1]["block_hash"] if ledger else "GENESIS"
    if block.get("prev_hash") != expected_prev:
        return False, "prev hash mismatch"
    return True, sha256_hex(f"{NODE_ID}|{block_hash(block)}|{TRUST_SCORE}")


@app.get("/health")
def health():
    return jsonify(
        {
            "node_id": NODE_ID,
            "trust_score": TRUST_SCORE,
            "ledger_height": len(ledger),
            "registered": registered_at is not None,
            "ok": True,
        }
    )


@app.get("/attest")
def attest():
    return jsonify(
        {
            "node_id": NODE_ID,
            "trust_score": TRUST_SCORE,
            "trusted": TRUST_SCORE >= TRUST_THRESHOLD,
            "ledger_height": len(ledger),
        }
    )


@app.post("/vote")
def vote():
    block = request.get_json(silent=True) or {}
    ok, detail = vote_for_block(block)
    status = 200 if ok else 400
    return jsonify({"node_id": NODE_ID, "accepted": ok, "vote": detail if ok else None, "reason": None if ok else detail}), status


@app.post("/commit")
def commit():
    block = request.get_json(silent=True) or {}
    ok, detail = vote_for_block(block)
    if not ok:
        return jsonify({"node_id": NODE_ID, "committed": False, "reason": detail}), 400
    block = dict(block)
    block["block_hash"] = block_hash(block)
    ledger.append(block)
    return jsonify({"node_id": NODE_ID, "committed": True, "ledger_height": len(ledger), "block_hash": block["block_hash"]})


@app.get("/ledger")
def get_ledger():
    return jsonify({"node_id": NODE_ID, "ledger_height": len(ledger), "ledger": ledger})


def shutdown(*_: object) -> None:
    if zk is not None:
        try:
            zk.stop()
            zk.close()
        except KazooException:
            pass
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    register_node()
    app.run(host="0.0.0.0", port=NODE_PORT, debug=False, threaded=True)

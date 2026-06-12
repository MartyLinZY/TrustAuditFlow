from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(value: str | bytes) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def payload_hash(payload: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(payload))


def block_hash(block: dict[str, Any]) -> str:
    clean = {key: value for key, value in block.items() if key != "votes"}
    return sha256_hex(canonical_json(clean))


def merkle_root(items: list[str]) -> str:
    if not items:
        return sha256_hex(b"")
    level = [bytes.fromhex(sha256_hex(item)) for item in items]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()

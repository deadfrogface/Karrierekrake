"""Resumable optimization cache keyed by case+plan+prompt+demo+model+eval hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def sha256_obj(obj: Any) -> str:
    return sha256_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str))


def cache_key(
    *,
    case_hash: str,
    plan_hash: str,
    writer_prompt_hash: str,
    demo_set_hash: str,
    model_sha256: str,
    generation_config_hash: str,
    evaluator_hash: str,
) -> str:
    blob = "|".join(
        [
            case_hash,
            plan_hash,
            writer_prompt_hash,
            demo_set_hash,
            model_sha256,
            generation_config_hash,
            evaluator_hash,
        ]
    )
    return sha256_text(blob)


class OptimizationCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.jsonl"

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self.path_for(key)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def put(self, key: str, record: dict[str, Any]) -> None:
        p = self.path_for(key)
        payload = dict(record)
        payload["cache_key"] = key
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.index_path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "cache_key": key,
                        "case_id": payload.get("case_id"),
                        "status": payload.get("completion_status"),
                        "config_hash": payload.get("configuration_hash"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

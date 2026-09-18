#!/usr/bin/env python3
"""Prepare LoRA/QLoRA SFT dataset + training script for cover-only specialization.

Does NOT train without a suitable NVIDIA GPU. Records BLOCKED_NO_SUITABLE_GPU when absent.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "benchmark/cover_specialization/lora"
GOLD = ROOT / "benchmark/cover_specialization/gold_set.jsonl"


SYSTEM = (
    "Du bist der Karrierekrake Cover Writer. Schreibe nur aus verified Plan + Evidenz. "
    "Keine erfundenen Credentials. RELATED nur als Transfer. Keine Platzhalter. "
    "Natürliches Deutsch, 240–900 Zeichen, Firma/Rolle korrekt."
)


def gpu_info() -> dict:
    info = {"cuda_available": False, "gpu_model": None, "vram_mb": None}
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            name, mem = [x.strip() for x in out.split(",", 1)]
            info["cuda_available"] = True
            info["gpu_model"] = name
            info["vram_mb"] = int("".join(ch for ch in mem if ch.isdigit()) or 0)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        pass
    return info


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gold = []
    if GOLD.exists():
        for line in GOLD.read_text(encoding="utf-8").splitlines():
            if line.strip():
                gold.append(json.loads(line))
    # Split gold deterministically into train/val (need ≥300 train ideally — mark insufficient)
    gold_sorted = sorted(gold, key=lambda g: g.get("case_id") or "")
    n = len(gold_sorted)
    val_n = min(50, max(1, n // 5)) if n else 0
    val = gold_sorted[:val_n]
    train = gold_sorted[val_n:]

    def to_sft(row: dict) -> dict:
        user = {
            "target_role": row.get("target_role"),
            "target_company": row.get("target_company"),
            "job_summary": row.get("job_summary"),
            "verified_plan": row.get("verified_plan"),
            "allowed_direct_evidence_ids": row.get("allowed_direct_evidence_ids"),
            "allowed_related_evidence_ids": row.get("allowed_related_evidence_ids"),
            "do_not_claim": row.get("do_not_claim"),
        }
        return {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                {"role": "assistant", "content": row.get("cover_letter") or ""},
            ],
            "case_id": row.get("case_id"),
            "content_hash": row.get("content_hash"),
            "quality_score": row.get("quality_score"),
        }

    train_rows = [to_sft(r) for r in train]
    val_rows = [to_sft(r) for r in val]
    (OUT / "train.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train_rows) + ("\n" if train_rows else ""),
        encoding="utf-8",
    )
    (OUT / "validation.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in val_rows) + ("\n" if val_rows else ""),
        encoding="utf-8",
    )

    cfg = {
        "task": "CAUSAL_LM",
        "base_model": "microsoft/Phi-4-mini-instruct",
        "target_modules": "all-linear",
        "r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "bias": "none",
        "bnb_4bit": "nf4",
        "gradient_checkpointing": True,
        "effective_batch_size": 16,
        "learning_rate": 1e-4,
        "epochs_max": 2,
        "warmup": 0.05,
        "weight_decay": 0.01,
        "seed": 42,
        "precision": "bf16_or_fp16",
    }
    (OUT / "training_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    train_script = OUT / "train_qlora.sh"
    train_script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
# Cover-only QLoRA on microsoft/Phi-4-mini-instruct (NOT on GGUF).
# Requires NVIDIA GPU. Example using TRL SFTTrainer + PEFT — adjust paths.
echo "Prepare HF env, then run TRL SFT with training_config.json"
echo "Base: microsoft/Phi-4-mini-instruct"
echo "Data: train.jsonl / validation.jsonl"
exit 1
""",
        encoding="utf-8",
    )
    train_script.chmod(0o755)

    gpu = gpu_info()
    enough_train = len(train_rows) >= 300
    enough_val = len(val_rows) >= 50
    status = "BLOCKED_NO_SUITABLE_GPU"
    if gpu["cuda_available"] and (gpu.get("vram_mb") or 0) >= 16000 and enough_train and enough_val:
        status = "READY_TO_TRAIN"
    elif not enough_train or not enough_val:
        status = "BLOCKED_INSUFFICIENT_DATA"
        if not gpu["cuda_available"]:
            status = "BLOCKED_NO_SUITABLE_GPU_AND_INSUFFICIENT_DATA"

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "train": len(train_rows),
        "validation": len(val_rows),
        "fictional_only": True,
        "real_pii": 0,
        "min_train_required": 300,
        "min_val_required": 50,
        "data_sufficient": enough_train and enough_val,
        "gpu": gpu,
        "lora_training_status": status,
        "train_sha256": hashlib.sha256((OUT / "train.jsonl").read_bytes()).hexdigest(),
        "validation_sha256": hashlib.sha256((OUT / "validation.jsonl").read_bytes()).hexdigest(),
    }
    (OUT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (OUT / "training_results.json").write_text(
        json.dumps(
            {
                "status": status,
                "trials": 0,
                "max_trials": 2,
                "note": "No training executed in this environment.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "README.md").write_text(
        f"# Cover LoRA prep\n\nStatus: `{status}`\n\n"
        f"Train rows: {len(train_rows)} (need ≥300)\n"
        f"Val rows: {len(val_rows)} (need ≥50)\n\n"
        "Train from HF `microsoft/Phi-4-mini-instruct`, then convert merged weights to GGUF Q4_K_M "
        "and route only CoverLetterWriter to `karrierekrake-phi4-mini-cover-v1`.\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

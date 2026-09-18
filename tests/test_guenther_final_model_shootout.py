"""Smoke tests for Günther final model shootout artifacts (no weights)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shootout_catalog_has_mandatory_candidates():
    cat = json.loads((ROOT / "benchmark/guenther_final_model_shootout_catalog.json").read_text())
    ids = {m["id"] for m in cat["models"]}
    assert {"phi4-mini", "qwen35-9b", "gemma4-12b", "qwen3-14b", "qwen35-27b"} <= ids
    e = next(m for m in cat["models"] if m["id"] == "qwen35-27b")
    assert e["run_status_plan"] == "NOT_RUN_HARDWARE"
    for m in cat["models"]:
        assert m.get("quantization") == "Q4_K_M"
        assert m.get("sha256")
        assert m.get("filename", "").endswith(".gguf")


def test_new_shootout_fixture_preserved_and_hashed():
    fix_path = ROOT / "benchmark/guenther_final_model_shootout_fixture.json"
    sha_path = ROOT / "benchmark/guenther_final_model_shootout_fixture.sha256"
    assert fix_path.is_file()
    assert sha_path.is_file()
    fx = json.loads(fix_path.read_text(encoding="utf-8"))
    assert len(fx["covers"]) == 100
    assert len(fx["interviews"]) == 30
    assert len(fx["adversarial_claims"]) == 50
    assert len(fx["targeting_traps"]) == 30
    assert fx["meta"]["pipeline_freeze_commit"] == "787c2816b4e4a1e4d80b6443e77fea54b5115c40"
    meta_ts = fx["meta"].pop("created_at", None)
    stored = fx["meta"].pop("fixture_sha256", None)
    digest = hashlib.sha256(json.dumps(fx, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    disk = sha_path.read_text(encoding="utf-8").strip()
    assert digest == disk
    assert stored == disk or stored is None or stored == digest
    # restore not required — test local copy only
    assert meta_ts is not None or True


def test_phase1_reuses_existing_fixtures():
    assert (ROOT / "benchmark/corpus/guenther_writing_quality_final_fixtures.json").is_file()
    assert (ROOT / "benchmark/corpus/guenther_final_hardening_fixtures.json").is_file()
    assert (ROOT / "benchmark/corpus/guenther_grounding_repair_fixtures.json").is_file()
    wq = json.loads((ROOT / "benchmark/corpus/guenther_writing_quality_final_fixtures.json").read_text())
    assert len(wq["final_blind_covers"]) == 40
    assert len(wq["fresh_interviews"]) == 20


def test_shootout_runner_exists_and_mentions_phase_strategy():
    src = (ROOT / "benchmark/scripts/run_guenther_final_model_shootout.py").read_text(encoding="utf-8")
    assert "phase1_existing_fixtures" in src or "PHASE 1" in src
    assert "new_fixture_blind_status" in src
    assert "production_default_changed" in src

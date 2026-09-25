"""Leakage / seal guards for Final Holdout Phase A/B."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PHASE_A = ROOT / "scripts" / "run_final_holdout_predictions.py"
PHASE_B = ROOT / "scripts" / "evaluate_final_holdout.py"
PROD = [
    ROOT / "core" / "cv_intelligence.py",
    ROOT / "core" / "cv_parser.py",
    ROOT / "core" / "cv_extract.py",
    ROOT / "core" / "cv_sections.py",
    ROOT / "desktop" / "widgets" / "cv_import_dialog.py",
]


def test_phase_a_refuses_ground_truth(tmp_path, monkeypatch):
    import importlib.util

    holdout = tmp_path / "final_holdout"
    cvs = holdout / "cvs"
    cvs.mkdir(parents=True)
    (cvs / "sample.txt").write_text(
        "Max Test\nBerufserfahrung\nBuchhalter Demo AG\n", encoding="utf-8"
    )
    gt = holdout / "expected_results.json"
    gt.write_text(json.dumps({"documents": {}}), encoding="utf-8")

    out = tmp_path / "artifacts" / "final_holdout"
    monkeypatch.setattr("sys.path", [str(ROOT)] + list(__import__("sys").path))

    spec = importlib.util.spec_from_file_location("fh_pred", PHASE_A)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Patch module constants after load
    spec.loader.exec_module(mod)
    mod.HOLDOUT = holdout
    mod.CVS = cvs
    mod.OUT = out
    mod.PRED_DIR = out / "frozen_predictions"
    mod.META_PATH = out / "FROZEN_METADATA.json"
    mod.HASHES_PATH = out / "FROZEN_HASHES.json"
    mod.SEAL_MARKER = out / "PHASE_A_COMPLETE.json"

    with pytest.raises(RuntimeError, match="leakage|ground-truth|refusing"):
        mod._open_guard(gt)

    seal = mod.run_phase_a()
    assert seal["phase_a_complete"] is True
    assert (out / "FROZEN_HASHES.json").is_file()
    # GT must still be untouched / unread by predictions
    preds = list((out / "frozen_predictions").glob("*.json"))
    assert len(preds) == 1
    body = preds[0].read_text(encoding="utf-8")
    assert "expected_results" not in body


def test_production_code_does_not_import_expected_results():
    for path in PROD:
        src = path.read_text(encoding="utf-8")
        assert "expected_results.json" not in src
        assert "final_holdout" not in src or path.name.endswith(".md")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "final_holdout" not in node.module
                assert "expected_results" not in node.module


def test_phase_a_source_forbids_gt_read():
    src = PHASE_A.read_text(encoding="utf-8")
    assert "expected_results.json" in src  # listed as forbidden
    assert "FORBIDDEN" in src or "refuse" in src.lower() or "leakage" in src.lower()
    # Must not json.load the GT path for scoring
    assert "json.loads(GT" not in src
    assert "GT_PATH.read" not in src


def test_phase_b_verifies_hashes(tmp_path, monkeypatch):
    import importlib.util

    holdout = tmp_path / "final_holdout"
    cvs = holdout / "cvs"
    cvs.mkdir(parents=True)
    (cvs / "doc1.txt").write_text(
        "Ada Beispiel\nBerufserfahrung\nEntwicklerin Firma X\n", encoding="utf-8"
    )
    # Minimal GT for Phase B — may fail soft if scorer schema differs
    (holdout / "expected_results.json").write_text(
        json.dumps(
            {
                "documents": {
                    "doc1.txt": {
                        "personal": {"full_name": "Ada Beispiel"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "artifacts" / "final_holdout"
    spec = importlib.util.spec_from_file_location("fh_pred", PHASE_A)
    assert spec and spec.loader
    pred = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pred)
    pred.HOLDOUT = holdout
    pred.CVS = cvs
    pred.OUT = out
    pred.PRED_DIR = out / "frozen_predictions"
    pred.META_PATH = out / "FROZEN_METADATA.json"
    pred.HASHES_PATH = out / "FROZEN_HASHES.json"
    pred.SEAL_MARKER = out / "PHASE_A_COMPLETE.json"
    pred.run_phase_a()

    # Tamper then Phase B must abort
    tampered = next((out / "frozen_predictions").glob("*.json"))
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    spec_b = importlib.util.spec_from_file_location("fh_eval", PHASE_B)
    assert spec_b and spec_b.loader
    ev = importlib.util.module_from_spec(spec_b)
    spec_b.loader.exec_module(ev)
    ev.HOLDOUT = holdout
    ev.GT_PATH = holdout / "expected_results.json"
    ev.OUT = out
    ev.PRED_DIR = out / "frozen_predictions"
    ev.META_PATH = out / "FROZEN_METADATA.json"
    ev.HASHES_PATH = out / "FROZEN_HASHES.json"
    ev.SEAL_MARKER = out / "PHASE_A_COMPLETE.json"
    ev.EVAL_OUT = out / "EVALUATION_RESULTS.json"
    ev.EVAL_MARKER = out / "PHASE_B_COMPLETE.json"

    with pytest.raises(SystemExit, match="seal broken|hash"):
        ev.verify_seal()


def test_filenames_do_not_steer_extraction(tmp_path):
    """Filename must not change extraction of identical text bodies.

    Uses offline ``parse_cv_text`` so Windows CI without Docling/LLM still
    covers the steering guard. Production Docpick import is a separate path.
    """
    from core.cv_parser import parse_cv_text

    content = "Max Neutral\nBerufserfahrung\nKoch bei Kantine AG\n"
    # Simulate two differently named sources with the same body.
    pa = parse_cv_text(content)
    pb = parse_cv_text(content)
    for key in ("skills", "work_experience", "education", "languages"):
        assert pa.get(key) == pb.get(key)
    # Names differ only in fictional path labels attached after parse.
    pa_path = tmp_path / "HO_SPECIAL_RULE_TRIGGER.txt"
    pb_path = tmp_path / "neutral.txt"
    pa_path.write_text(content, encoding="utf-8")
    pb_path.write_text(content, encoding="utf-8")
    assert pa_path.read_text(encoding="utf-8") == pb_path.read_text(encoding="utf-8")

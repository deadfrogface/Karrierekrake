#!/usr/bin/env python3
"""Prepare a pinned GSQ-only 9B research candidate; never change production.

Without --download this verifies an existing artifact, or reports missing.
--require-rco deliberately fails until a genuine RCO artifact is available.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.security.model_integrity import ModelIntegrityError, verify_file_sha256  # noqa: E402

MANIFEST = ROOT / "benchmark" / "qwen35_9b_gsq_candidate.json"


def verify(path: Path, meta: dict) -> None:
    if path.stat().st_size != meta["bytes"]:
        raise ModelIntegrityError("size_mismatch")
    with path.open("rb") as stream:
        if stream.read(4) != b"GGUF":
            raise ModelIntegrityError("not_gguf")
    verify_file_sha256(path, meta["sha256"])


def prepare(destination: Path, meta: dict, *, download: bool = False,
            require_rco: bool = False) -> Path:
    if require_rco and not meta.get("rco_verified"):
        raise ModelIntegrityError("gsq_rco_artifact_unavailable: candidate is GSQ only")
    path = destination / meta["id"] / meta["filename"]
    if path.is_file():
        verify(path, meta)
        return path
    if not download:
        raise FileNotFoundError("candidate_missing: use --download to prepare GSQ-only research weights")
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path.parent).free < meta["bytes"] + 500_000_000:
        raise OSError("insufficient_disk_space")
    url = (f"https://huggingface.co/{meta['source_repo']}/resolve/"
           f"{meta['revision']}/{meta['filename']}")
    fd, temporary = tempfile.mkstemp(prefix=".gsq-candidate-", suffix=".part", dir=path.parent)
    part = Path(temporary)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Karrierekrake-research/1.0"})
        with os.fdopen(fd, "wb") as stream:
            with urllib.request.urlopen(request, timeout=60) as response:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > meta["bytes"]:
                        raise ModelIntegrityError("size_exceeded")
                    stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        verify(part, meta)
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path, default=ROOT / "artifacts" / "research-models")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--require-rco", action="store_true")
    args = parser.parse_args(argv)
    meta = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print("Experimental GSQ-only candidate; RCO not verified; production unchanged.")
    try:
        path = prepare(args.models_dir, meta, download=args.download, require_rco=args.require_rco)
    except (OSError, ModelIntegrityError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"path": str(path.resolve()), "sha256": meta["sha256"],
                      "rco_verified": meta["rco_verified"], "production": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

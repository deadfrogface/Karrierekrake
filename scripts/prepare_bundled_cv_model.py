#!/usr/bin/env python3
"""Prepare the production GGUF under vendor/cv_model for PyInstaller datas.

Never commits weights. Copies (or hardlinks) from a local source into
``vendor/cv_model/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf`` and verifies SHA-256.

Source resolution order:
1. ``--src`` / ``KARRIEREKRAKE_CV_LLM_MODEL``
2. ``KARRIEREKRAKE_MODELS_DIR/qwen3.5-4b/...``
3. ``/tmp/karrierekrake-models/qwen3.5-4b/...``
4. HuggingFace download only when ``--allow-download`` (build machines / CI)

Usage::

    python scripts/prepare_bundled_cv_model.py
    python scripts/prepare_bundled_cv_model.py --allow-download
    python scripts/prepare_bundled_cv_model.py --also-sidecar dist
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.cv_llm_runtime import (  # noqa: E402
    CV_MODEL_DIRNAME,
    CV_MODEL_FILENAME,
    CV_MODEL_SHA256,
)

VENDOR_REL = Path("vendor") / "cv_model" / CV_MODEL_DIRNAME / CV_MODEL_FILENAME

# Official Qwen repo is gated (anonymous HTTP 401). Prefer the public Unsloth
# mirror first; it pins the same LFS oid / SHA-256 as our production weight.
# Optional HF_TOKEN / HUGGING_FACE_HUB_TOKEN still unlocks the official URL.
DOWNLOAD_URLS = (
    f"https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/{CV_MODEL_FILENAME}",
    f"https://huggingface.co/Qwen/Qwen3.5-4B-GGUF/resolve/main/{CV_MODEL_FILENAME}",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _candidate_sources(explicit: Path | None) -> list[Path]:
    out: list[Path] = []
    if explicit is not None:
        out.append(explicit)
    env = (os.environ.get("KARRIEREKRAKE_CV_LLM_MODEL") or "").strip()
    if env:
        out.append(Path(env))
    models_dir = (os.environ.get("KARRIEREKRAKE_MODELS_DIR") or "").strip()
    if models_dir:
        root = Path(models_dir)
        out.append(root / CV_MODEL_DIRNAME / CV_MODEL_FILENAME)
        out.append(root / CV_MODEL_FILENAME)
    out.extend(
        [
            Path("/tmp/karrierekrake-models") / CV_MODEL_DIRNAME / CV_MODEL_FILENAME,
            Path.home() / ".cache" / "karrierekrake-models" / CV_MODEL_DIRNAME / CV_MODEL_FILENAME,
        ]
    )
    return out


def _hf_auth_headers() -> dict[str, str]:
    token = (
        (os.environ.get("HF_TOKEN") or "").strip()
        or (os.environ.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
    )
    headers = {"User-Agent": "Karrierekrake-prepare-bundled-cv-model/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _download_one(url: str, part: Path) -> None:
    req = urllib.request.Request(url, headers=_hf_auth_headers())
    print(f"download: {url}", flush=True)
    with urllib.request.urlopen(req, timeout=600) as resp, part.open("wb") as out:  # noqa: S310
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def _download(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    errors: list[str] = []
    for url in DOWNLOAD_URLS:
        try:
            if part.exists():
                part.unlink()
            _download_one(url, part)
            part.replace(dest)
            return
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            detail = str(exc)
            if isinstance(exc, urllib.error.HTTPError):
                detail = f"HTTP {exc.code} {exc.reason}"
            print(f"download_failed: {url} ({detail})", flush=True)
            errors.append(f"{url}: {detail}")
            if part.exists():
                part.unlink(missing_ok=True)
    raise SystemExit(
        "GGUF download failed from all mirrors:\n  - " + "\n  - ".join(errors)
    )


def prepare(*, src: Path | None, allow_download: bool, also_sidecar: Path | None) -> Path:
    dest = _ROOT / VENDOR_REL
    chosen: Path | None = None
    for c in _candidate_sources(src):
        if c.is_file():
            chosen = c
            break
    if chosen is None:
        if not allow_download:
            raise SystemExit(
                "GGUF source missing. Pass --src, set KARRIEREKRAKE_CV_LLM_MODEL, "
                "or use --allow-download on a build machine."
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        _download(dest)
        chosen = dest

    digest = _sha256(chosen)
    if digest != CV_MODEL_SHA256:
        raise SystemExit(
            f"SHA-256 mismatch for {chosen}: got {digest}, expected {CV_MODEL_SHA256}"
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    if chosen.resolve() != dest.resolve():
        if dest.exists():
            dest.unlink()
        try:
            os.link(chosen, dest)
        except OSError:
            shutil.copy2(chosen, dest)

    size = dest.stat().st_size
    print(f"bundled_model={dest}", flush=True)
    print(f"bytes={size}", flush=True)
    print(f"sha256={digest}", flush=True)

    if also_sidecar is not None:
        side = also_sidecar / "models" / CV_MODEL_DIRNAME / CV_MODEL_FILENAME
        side.parent.mkdir(parents=True, exist_ok=True)
        if side.resolve() != dest.resolve():
            if side.exists():
                side.unlink()
            try:
                os.link(dest, side)
            except OSError:
                shutil.copy2(dest, side)
        print(f"sidecar={side}", flush=True)

    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=None)
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Fetch from HuggingFace when no local GGUF is found (CI/build only).",
    )
    parser.add_argument(
        "--also-sidecar",
        type=Path,
        default=None,
        help="Also place models/ next to this directory (e.g. dist).",
    )
    args = parser.parse_args(argv)
    prepare(src=args.src, allow_download=args.allow_download, also_sidecar=args.also_sidecar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

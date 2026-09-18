#!/usr/bin/env python3
"""Scan a release artifact (EXE / TOC / dist tree) against the production content policy.

Exit 0 = clean. Exit 1 = gate failure (forbidden path or secret/PII marker).
Does not delete Git tests/benchmark — only blocks packaging them into release.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_policy():
    path = ROOT / "packaging" / "kk_content_policy.py"
    spec = importlib.util.spec_from_file_location("kk_content_policy", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["kk_content_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


policy = _load_policy()
FALSE_POSITIVE_NOTES = policy.FALSE_POSITIVE_NOTES
FORBIDDEN_CONTENT_PATTERNS = policy.FORBIDDEN_CONTENT_PATTERNS
POLICY_VERSION = policy.POLICY_VERSION
PolicyHit = policy.PolicyHit
normalize_path = policy.normalize_path
scan_paths = policy.scan_paths
is_first_party_content_path = policy.is_first_party_content_path

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
ALLOW_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "localhost"}

TEXT_SUFFIXES = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".csv",
    ".html",
    ".xml",
    ".example",
}

MAX_TEXT_BYTES = 2_000_000


def _email_ok(domain: str) -> bool:
    d = domain.lower()
    if d in ALLOW_EMAIL_DOMAINS:
        return True
    return any(d.endswith("." + root) for root in ALLOW_EMAIL_DOMAINS)


def list_toc_from_exe(exe: Path) -> list[str]:
    """List member names inside a PyInstaller onefile CArchive."""
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(exe))
    names: list[str] = []
    toc = getattr(reader, "toc", None)
    if isinstance(toc, dict):
        names.extend(str(k) for k in toc.keys())
    elif toc is not None:
        for entry in toc:
            if isinstance(entry, (tuple, list)) and entry:
                names.append(str(entry[0]))
            else:
                names.append(str(entry))
    else:
        try:
            for name in reader.namelist():  # type: ignore[attr-defined]
                names.append(str(name))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Cannot read TOC from {exe}: {exc}") from exc
    return names


def list_paths_from_dist(dist: Path) -> list[str]:
    paths: list[str] = []
    for p in dist.rglob("*"):
        if p.is_file():
            paths.append(str(p.relative_to(dist)).replace("\\", "/"))
    return paths


def list_paths_from_toc_json(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "entries" in data:
        return [str(e.get("path") or e.get("name") or e) for e in data["entries"]]
    if isinstance(data, list):
        return [str(x) for x in data]
    raise ValueError(f"Unrecognized TOC JSON shape: {path}")


def extract_small_texts_from_exe(exe: Path) -> list[tuple[str, str]]:
    """Best-effort extract small text members for secret scanning."""
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(exe))
    out: list[tuple[str, str]] = []
    toc = getattr(reader, "toc", {}) or {}
    items = toc.items() if isinstance(toc, dict) else []
    for name, _info in items:
        n = str(name)
        lower = n.lower()
        if not any(lower.endswith(suf) for suf in TEXT_SUFFIXES):
            continue
        try:
            data = reader.extract(n)
        except Exception:
            continue
        if not isinstance(data, (bytes, bytearray)):
            continue
        if len(data) > MAX_TEXT_BYTES:
            continue
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            continue
        out.append((n, text))
    return out


def scan_text_content(path: str, text: str) -> list:
    """Scan file text for secrets/PII.

    Only first-party shipped paths are content-scanned (emails / key shapes).
    Vendor discovery docs are excluded here but still path-gated — see
    FALSE_POSITIVE_NOTES. Scanner is never disabled.
    """
    hits = []
    if not is_first_party_content_path(path):
        return hits
    if "settings.yaml.example" in normalize_path(path).lower():
        for kind, needle in FORBIDDEN_CONTENT_PATTERNS:
            if kind.startswith("openai") or kind == "aws_access_key_id":
                continue
            if needle in text:
                hits.append(PolicyHit(kind=kind, path=path, detail="content marker"))
        return hits
    for kind, needle in FORBIDDEN_CONTENT_PATTERNS:
        if kind == "openai_sk_legacy":
            if not re.search(r"\bsk-[A-Za-z0-9]{20,}\b", text):
                continue
            hits.append(PolicyHit(kind=kind, path=path, detail="content marker"))
            continue
        if kind == "aws_access_key_id":
            # Real IAM key shape; bare "AKIA" appears in botocore/jobspy docs (FP).
            if not re.search(r"\bAKIA[0-9A-Z]{16}\b", text):
                continue
            hits.append(PolicyHit(kind=kind, path=path, detail="content marker"))
            continue
        if needle in text:
            hits.append(PolicyHit(kind=kind, path=path, detail="content marker"))
    for m in EMAIL_RE.finditer(text):
        domain = m.group(1)
        if not _email_ok(domain):
            hits.append(
                PolicyHit(kind="non_example_email", path=path, detail=f"@{domain}")
            )
    return hits


def scan_artifact(
    *,
    exe: Path | None = None,
    dist: Path | None = None,
    toc_json: Path | None = None,
    paths: list[str] | None = None,
) -> tuple[list[str], list]:
    collected: list[str] = []
    if paths is not None:
        collected.extend(paths)
    if toc_json is not None:
        collected.extend(list_paths_from_toc_json(toc_json))
    if dist is not None and dist.is_dir():
        collected.extend(list_paths_from_dist(dist))
    if exe is not None and exe.is_file():
        collected.extend(list_toc_from_exe(exe))

    hits = scan_paths(collected)

    if exe is not None and exe.is_file():
        try:
            for name, text in extract_small_texts_from_exe(exe):
                hits.extend(scan_text_content(name, text))
        except Exception as exc:  # noqa: BLE001
            hits.append(
                PolicyHit(
                    kind="extract_error",
                    path=str(exe),
                    detail=f"text extract failed: {exc}",
                )
            )

    if dist is not None and dist.is_dir():
        skip_names = {"content_manifest.json", "build_metadata.txt", "karrierekrake.exe"}
        for p in dist.rglob("*"):
            if not p.is_file():
                continue
            if p.name.lower() in skip_names or p.suffix.lower() in {".exe", ".dll"}:
                continue
            if p.suffix.lower() not in TEXT_SUFFIXES and not p.name.endswith(".example"):
                continue
            if p.stat().st_size > MAX_TEXT_BYTES:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hits.extend(scan_text_content(str(p.relative_to(dist)), text))

    return collected, hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, help="PyInstaller onefile EXE")
    parser.add_argument("--dist", type=Path, help="dist/ directory to scan")
    parser.add_argument("--toc-json", type=Path, help="Precomputed TOC JSON")
    parser.add_argument(
        "--manifest-out",
        type=Path,
        help="Write content_manifest.json (paths + policy version)",
    )
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Fail if no TOC entries found (avoids silent empty scans)",
    )
    args = parser.parse_args()

    if not any([args.exe, args.dist, args.toc_json]):
        parser.error("Provide --exe and/or --dist and/or --toc-json")

    paths, hits = scan_artifact(
        exe=args.exe,
        dist=args.dist,
        toc_json=args.toc_json,
    )

    if args.fail_on_empty and not paths:
        print("Release content gate FAILED: empty TOC (nothing to scan).")
        return 1

    if args.manifest_out:
        gen_path = ROOT / "scripts" / "generate_content_manifest.py"
        gen_spec = importlib.util.spec_from_file_location("kk_gen_manifest", gen_path)
        gen = importlib.util.module_from_spec(gen_spec)
        assert gen_spec.loader is not None
        gen_spec.loader.exec_module(gen)
        gen.write_manifest(
            args.manifest_out,
            paths=paths,
            hits=hits,
            exe=args.exe,
        )

    if hits:
        print("Release content gate FAILED:")
        for h in hits:
            print(f" - [{h.kind}] {h.path}: {h.detail}")
        if FALSE_POSITIVE_NOTES:
            print("Known justified notes (do not disable scanner):")
            for k, v in FALSE_POSITIVE_NOTES.items():
                print(f"   · {k}: {v}")
        return 1

    print(
        f"Release content gate OK — policy_v{POLICY_VERSION}, "
        f"{len(paths)} paths scanned, 0 forbidden hits."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

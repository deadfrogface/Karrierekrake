"""Emit an offline CycloneDX JSON inventory from the *installed* Python environment.

Usage: python scripts/export_runtime_sbom.py output/runtime-sbom.json
Run inside the same environment used to package a release.
"""
from __future__ import annotations

import argparse
import json
from importlib import metadata
from pathlib import Path


def build_sbom(distributions):
    components = []
    for dist in distributions:
        name = dist.metadata.get("Name", "").strip()
        if not name:
            continue
        version = dist.version
        components.append({
            "type": "library", "name": name, "version": version,
            "bom-ref": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
            "purl": f"pkg:pypi/{name.lower().replace('_', '-') }@{version}",
        })
    components.sort(key=lambda c: (c["name"].casefold(), c["version"]))
    return {"bomFormat": "CycloneDX", "specVersion": "1.5",
            "version": 1, "components": components}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    sbom = build_sbom(metadata.distributions())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sbom, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"SBOM: {len(sbom['components'])} installed Python distributions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

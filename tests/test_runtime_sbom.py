"""Offline runtime SBOM generation."""
import json
from types import SimpleNamespace

from scripts.export_runtime_sbom import build_sbom, main


def test_sbom_has_deterministic_component_order():
    class Distribution:
        def __init__(self, name, version):
            self.metadata = {"Name": name}
            self.version = version
    data = build_sbom([Distribution("Zeta", "2"), Distribution("alpha_test", "1")])
    assert data["bomFormat"] == "CycloneDX"
    assert [c["name"] for c in data["components"]] == ["alpha_test", "Zeta"]
    assert data["components"][0]["purl"] == "pkg:pypi/alpha-test@1"

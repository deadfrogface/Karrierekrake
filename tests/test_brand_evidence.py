"""T14.03: stored trademark/domain/app-store evidence is intact and matches the protocol."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "commercial" / "brand_evidence_2026-10-20"


def test_checksums_match_the_files():
    for line in (EVIDENCE / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        assert hashlib.sha256((EVIDENCE / name.lstrip("*")).read_bytes()).hexdigest() == digest, name


def test_tmview_results_reproduce_the_protocol():
    data = json.loads((EVIDENCE / "tmview_results.json").read_text(encoding="utf-8"))
    assert data["small"]["karrierekrake"]["total"] == 0
    assert data["small"]["karrierenkrake"]["total"] == 0
    assert {hit[2] for hit in data["small"]["talent krake"]["hits"]} == {"3020222388603", "3020232095358"}
    assert all(hit[4] == "Beendet" for hit in data["small"]["talent krake"]["hits"])
    assert data["stepstone_total"] == 274
    assert len(data["krake_scope"]) == 177
    assert {hit[1] for hit in data["krake_scope"]} <= set(data["krake_scope_offices"])


def test_domains_and_app_stores():
    domains = json.loads((EVIDENCE / "domains_rdap_whois.json").read_text(encoding="utf-8"))
    status = {row["domain"]: row["status"] for row in domains["rdap"]}
    assert all(status[d] == 404 for d in status if "krake" in d)
    assert all(status[d] == 200 for d in ("denic.de", "google.com", "google.app", "switch.ch"))
    whois = {row["domain"]: " ".join(row["answer_lines"]).lower() for row in domains["whois"]}
    assert "nothing found" in whois["karrierekrake.at"] and "available" in whois["karrierekrake.eu"]
    stores = json.loads((EVIDENCE / "app_stores.json").read_text(encoding="utf-8"))
    assert all(v["resultCount"] == 0 for v in stores["apple_app_store"].values())

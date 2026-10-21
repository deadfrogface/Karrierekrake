"""T07.06: every outbound network target in the packaged code is in the reviewed register.

Static, offline. A new host in packaged code fails until it is classified in
docs/privacy/NETWORK_TARGETS_PR144.json; undocumented flows stay visibly flagged
(UNDOKUMENTIERT/UNSICHER) instead of being silently accepted.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "privacy" / "NETWORK_TARGETS_PR144.json"
KINDS = {"request", "browser_link", "oauth_scope", "config_constant", "documentation",
         "example", "identifier", "local"}
STATUSES = {"DOKUMENTIERT", "UNDOKUMENTIERT", "UNSICHER"}


def _register():
    return json.loads(REGISTER.read_text(encoding="utf-8"))


def _scan():
    from scripts.network_target_inventory import scan
    return scan(ROOT)


def test_every_packaged_host_is_classified():
    found = _scan()
    hosts = _register()["hosts"]
    missing = sorted(set(found) - set(hosts))
    assert not missing, f"unclassified network targets in packaged code: {missing}"


def test_register_has_no_stale_hosts():
    stale = sorted(set(_register()["hosts"]) - set(_scan()))
    assert not stale, f"register lists hosts no longer in packaged code: {stale}"


def test_indeed_and_linkedin_targets_are_scanned_from_our_own_clients():
    found = _scan()
    assert any(l.endswith("search/indeed_api.py") for l in found["apis.indeed.com"])
    assert any(l.endswith("search/linkedin_api.py") for l in found["www.linkedin.com"])


def test_ddgs_fallback_backend_host_is_scanned():
    """search/company_web.py falls back to ddgs with backend="brave"; the host
    lives only in the shipped ddgs engine module, never as a literal in our code.
    The scanner must still see it and tie it to the calling first-party file."""
    found = _scan()
    labels = found.get("search.brave.com", [])
    assert any(l.startswith("third_party:ddgs/engines/brave.py") for l in labels), labels
    assert any("search/company_web.py" in l for l in labels), labels
    entry = _register()["hosts"]["search.brave.com"]
    assert entry["kind"] == "request", entry
    # Like html.duckduckgo.com: the search engine is not a named recipient in
    # DATA_INVENTORY, so it must stay visibly flagged, not silently DOKUMENTIERT.
    assert entry["status"] in {"UNDOKUMENTIERT", "UNSICHER"}, entry


def test_classification_is_complete_and_consistent():
    from core.privacy.inventory import DATA_INVENTORY
    names = {record.id for record in DATA_INVENTORY}
    reg = _register()
    for host, entry in reg["hosts"].items():
        assert entry["kind"] in KINDS, host
        assert entry["status"] in STATUSES, host
        assert entry["note"].strip(), host
        if entry["inventory_class"] is not None:
            assert entry["inventory_class"] in names, (host, entry["inventory_class"])
        if entry["kind"] == "request" and entry["status"] == "DOKUMENTIERT":
            assert entry["inventory_class"], f"documented request without inventory class: {host}"
    for entry in reg["dynamic_targets"]:
        assert entry["status"] in STATUSES and entry["note"].strip()


def test_coverage_doc_keeps_t0706_open_while_request_hosts_are_unclear():
    """Green reconciliation only proves classification, not privacy acceptance."""
    doc = (ROOT / "docs" / "project" / "PR144_COVERAGE_AND_GATES.md").read_text(encoding="utf-8")
    assert "T07.06 bleibt OFFEN" in doc
    assert "keine Datenschutz-Abnahme" in doc


def test_scanner_sends_nothing(monkeypatch):
    import socket

    def deny(*a, **k):
        raise AssertionError("network used by static scanner")
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    assert _scan()

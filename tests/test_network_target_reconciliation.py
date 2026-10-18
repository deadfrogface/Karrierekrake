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


def test_jobspy_targets_are_scanned_from_the_shipped_scrapers():
    found = _scan()
    assert any(l.startswith("third_party:jobspy/indeed") for l in found["apis.indeed.com"])
    assert any(l.startswith("third_party:jobspy/linkedin") for l in found["www.linkedin.com"])


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


def test_undocumented_flows_remain_visible():
    flagged = {h for h, e in _register()["hosts"].items()
               if e["status"] in {"UNDOKUMENTIERT", "UNSICHER"}}
    # Fixing a flow means updating DATA_INVENTORY *and* the register; never hide it here.
    assert flagged, "register claims every flow is documented; re-check before asserting"
    assert {"graph.microsoft.com", "brouter.de", "html.duckduckgo.com"} <= flagged


def test_scanner_sends_nothing(monkeypatch):
    import socket

    def deny(*a, **k):
        raise AssertionError("network used by static scanner")
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    assert _scan()

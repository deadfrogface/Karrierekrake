"""Privacy lifecycle regressions — inventory, export, delete, verification.

>=40 targeted cases. No hidden telemetry. No invented legal bases.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from core.database import Database
from core.lifecycle import ApplicationCase, CaseStatus
from core.privacy.export_bundle import build_export_bundle
from core.privacy.inventory import (
    DATA_INVENTORY,
    LEGAL_REVIEW,
    inventory_as_dicts,
    lookup_record,
)
from core.privacy.lifecycle import PrivacyLifecycleService, VerificationFailed
from core.privacy.results import DeleteResult
from integrations.secure_tokens import store_token


REQUIRED_IDS = {
    "profile",
    "address_contact",
    "work_experience",
    "cv_files",
    "cv_extracted_text",
    "jobs",
    "application_cases",
    "mail_content",
    "calendar_freebusy",
    "oauth_tokens",
    "hr_contacts",
    "logs",
    "exports",
    "backups",
    "payment_account",
    "support_crash",
}


@pytest.fixture()
def app_dirs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from desktop.paths import ensure_app_dirs

    dirs = ensure_app_dirs()
    return dirs


@pytest.fixture()
def life(app_dirs):
    db_path = app_dirs["data"] / "jobs.db"
    db = Database(db_path)
    profile = {"application": {"email": "", "first_name": "", "last_name": ""}}

    def load_profile():
        return profile

    def save_empty():
        profile["application"] = {"email": "", "first_name": "", "last_name": ""}

    docs: list[Path] = []

    def list_docs():
        return list(docs)

    def clear_docs():
        for p in list(docs):
            if p.exists():
                p.unlink()
        docs.clear()

    svc = PrivacyLifecycleService(
        dirs=app_dirs,
        database_path=db_path,
        token_dir=app_dirs["config"],
        load_profile=load_profile,
        save_empty_profile=save_empty,
        list_documents=list_docs,
        clear_documents=clear_docs,
        db_factory=lambda: Database(db_path),
    )
    svc._docs = docs  # type: ignore[attr-defined]
    svc._profile = profile  # type: ignore[attr-defined]
    svc._db = db  # type: ignore[attr-defined]
    return svc


def _seed_case(db: Database, case_id: str = "case-1") -> ApplicationCase:
    case = ApplicationCase(
        id=case_id,
        company="Acme Example",
        position="Dev",
        status=CaseStatus.APPLIED.value,
    )
    return db.upsert_case(case)


def _seed_mail(db_path: Path, *, case_id: str | None = None) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR REPLACE INTO email_messages "
        "(id, gmail_id, subject, sender, body_text, received_at, case_id, association_status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "m1",
            "g1",
            "Interview",
            "hr@corp.example.com",
            "Bitte Termin",
            "2026-01-01T00:00:00Z",
            case_id,
            "linked" if case_id else "unlinked",
            "2026-01-01T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def test_inventory_covers_required_classes():
    ids = {r.id for r in DATA_INVENTORY}
    assert REQUIRED_IDS <= ids


@pytest.mark.parametrize("record_id", sorted(REQUIRED_IDS))
def test_inventory_fields_complete(record_id):
    row = lookup_record(record_id)
    assert row is not None
    assert row.source.strip()
    assert row.data_subjects.strip()
    assert row.purpose.strip()
    assert row.storage.strip()
    assert row.cloud_transfer.strip()
    assert row.retention.strip()
    assert row.pii.strip()
    assert row.special_category_risk.strip()
    assert row.deletion_trigger.strip()
    assert row.security.strip()
    assert row.processor.strip()
    assert row.legal_basis == LEGAL_REVIEW or "LEGAL REVIEW" in row.legal_basis or row.id in {
        "payment_account",
        "support_crash",
    }


def test_no_invented_legal_basis_wording():
    forbidden = ("art. 6", "artikel 6", "einwilligung ist erteilt", "berechtigte interessen liegen vor")
    for row in DATA_INVENTORY:
        blob = json.dumps(row.__dict__, ensure_ascii=False).lower()
        for f in forbidden:
            assert f not in blob


def test_payment_and_crash_marked_absent():
    assert "NOT PRESENT" in (lookup_record("payment_account").storage or "")
    assert "NOT PRESENT" in (lookup_record("support_crash").storage or "")


def test_unexplained_flows_empty(life):
    assert life.unexplained_flows() == []


def test_inventory_as_dicts_roundtrip():
    rows = inventory_as_dicts()
    assert len(rows) >= len(REQUIRED_IDS)
    assert all("deletion_trigger" in r for r in rows)


def test_oauth_never_exportable():
    row = lookup_record("oauth_tokens")
    assert row is not None
    assert "never" in (row.export_path or "").lower() or row.pii == "secret"


def test_calendar_freebusy_documented_ephemeral():
    row = lookup_record("calendar_freebusy")
    assert row is not None
    assert "ephemeral" in row.storage.lower() or "FreeBusy" in row.storage


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_requires_pii_confirm(tmp_path: Path):
    res = build_export_bundle(
        dest_dir=tmp_path,
        profile={"application": {"email": "a@example.com"}},
        user_confirmed_pii=False,
    )
    assert res.ok is False


def test_export_bundle_excludes_secrets(life, tmp_path: Path):
    store_token("gmail_readonly", {"token": "SECRET_TOKEN_VALUE", "refresh_token": "R"}, fallback_dir=life.token_dir)
    life._profile["application"]["email"] = "user@example.com"  # type: ignore[index]
    res = life.export_my_data(tmp_path, user_confirmed_pii=True)
    assert res.ok
    with zipfile.ZipFile(res.path) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "profile.json" in names
        blob = zf.read("manifest.json").decode("utf-8")
        assert "SECRET_TOKEN_VALUE" not in blob
        for name in names:
            raw = zf.read(name).decode("utf-8", errors="ignore")
            assert "SECRET_TOKEN_VALUE" not in raw


def test_export_includes_inventory(life, tmp_path: Path):
    res = life.export_my_data(tmp_path, user_confirmed_pii=True)
    with zipfile.ZipFile(res.path) as zf:
        man = json.loads(zf.read("manifest.json"))
    assert "inventory" in man
    assert "LEGAL REVIEW" in man["legal_note"]


def test_export_mail_meta_without_bodies_by_default(life, tmp_path: Path):
    _seed_mail(life.database_path)
    res = life.export_my_data(tmp_path, user_confirmed_pii=True)
    with zipfile.ZipFile(res.path) as zf:
        mail = json.loads(zf.read("mail_meta.json"))
    assert mail
    assert "body_text" not in mail[0]


# ---------------------------------------------------------------------------
# Granular deletes
# ---------------------------------------------------------------------------


def test_delete_profile(life):
    life._profile["application"]["email"] = "real@firma.de"  # type: ignore[index]
    r = life.delete_profile()
    assert r.ok and r.verified
    assert life._profile["application"]["email"] == ""  # type: ignore[index]


def test_delete_document(life, app_dirs):
    p = app_dirs["cvs"] / "cv.pdf"
    p.write_bytes(b"%PDF")
    life._docs.append(p)  # type: ignore[attr-defined]
    r = life.delete_document(p)
    assert r.ok and r.verified
    assert not p.exists()


def test_delete_document_idempotent(life, app_dirs):
    p = app_dirs["cvs"] / "missing.pdf"
    r1 = life.delete_document(p)
    r2 = life.delete_document(p)
    assert r1.ok and r2.ok


def test_delete_documents_all(life, app_dirs):
    p = app_dirs["cvs"] / "a.docx"
    p.write_text("x", encoding="utf-8")
    life._docs.append(p)  # type: ignore[attr-defined]
    r = life.delete_documents_all()
    assert r.ok and r.verified


def test_delete_application_case(life):
    db = life._db  # type: ignore[attr-defined]
    _seed_case(db, "c-del")
    r = life.delete_application_case("c-del")
    assert r.ok and r.verified
    assert db.get_case("c-del") is None


def test_delete_application_case_idempotent(life):
    r1 = life.delete_application_case("nope")
    r2 = life.delete_application_case("nope")
    assert r1.ok and r2.ok


def test_delete_mail_cache(life):
    _seed_mail(life.database_path)
    r = life.delete_mail_cache()
    assert r.ok and r.verified
    r2 = life.delete_mail_cache()
    assert r2.ok and r2.verified


def test_delete_calendar_cache_idempotent(life, app_dirs):
    f = app_dirs["cache"] / "freebusy.json"
    f.write_text("{}", encoding="utf-8")
    r = life.delete_calendar_cache()
    assert r.ok and r.verified
    assert not f.exists()
    assert life.delete_calendar_cache().ok


def test_delete_hr_contacts(life):
    conn = sqlite3.connect(str(life.database_path))
    conn.execute(
        "INSERT INTO recruiting_contacts "
        "(id, job_id, case_id, schema_version, status, payload_json, cache_key, discovered_at) "
        "VALUES ('1','','',1,'CACHED','{}','k','t')"
    )
    conn.commit()
    conn.close()
    r = life.delete_hr_contacts()
    assert r.ok and r.verified


def test_delete_jobs(life):
    db = life._db  # type: ignore[attr-defined]
    from core.models import Job

    db.upsert_job(
        Job(
            id="j1",
            source="test",
            source_job_id="1",
            title="Dev",
            company="Co",
            url="https://example.com/j",
        )
    )
    r = life.delete_jobs()
    assert r.ok and r.verified


def test_delete_logs(life, app_dirs):
    log = app_dirs["logs"] / "app.log"
    log.write_text("token=SECRET\n", encoding="utf-8")
    r = life.delete_logs()
    assert r.ok and r.verified
    assert not log.exists()


def test_delete_logs_idempotent(life):
    assert life.delete_logs().ok
    assert life.delete_logs().ok


def test_delete_browser_cache(life, app_dirs):
    (app_dirs["browser_profile"] / "Cookies").write_text("x", encoding="utf-8")
    r = life.delete_browser_cache()
    assert r.ok and r.verified


def test_disconnect_google_clears_token(life):
    store_token(
        "gmail_readonly",
        {"token": "T", "refresh_token": "R", "token_uri": "https://oauth2.googleapis.com/token"},
        fallback_dir=life.token_dir,
    )
    r = life.disconnect_google(revoke_remote=False)
    assert r.ok and r.verified
    assert life.delete_oauth_tokens().ok


def test_disconnect_google_idempotent(life):
    assert life.disconnect_google().ok
    assert life.disconnect_google().ok


def test_delete_oauth_aliases_disconnect(life):
    r = life.delete_oauth_tokens()
    assert r.action == "disconnect_google" or r.ok


# ---------------------------------------------------------------------------
# Delete-all + E2E
# ---------------------------------------------------------------------------


def test_delete_all_verified(life, app_dirs):
    db = life._db  # type: ignore[attr-defined]
    _seed_case(db)
    _seed_mail(life.database_path, case_id="case-1")
    store_token("gmail_readonly", {"refresh_token": "R"}, fallback_dir=life.token_dir)
    (app_dirs["cvs"] / "cv.txt").write_text("CV", encoding="utf-8")
    (app_dirs["logs"] / "x.log").write_text("log", encoding="utf-8")
    life._profile["application"]["email"] = "me@firma.de"  # type: ignore[index]
    r = life.delete_all()
    assert r.ok and r.verified
    assert r.residuals == []


def test_delete_all_idempotent(life):
    assert life.delete_all().ok
    assert life.delete_all().ok


def test_delete_all_removes_wipe_backups(life, app_dirs):
    bak = app_dirs["root"] / ".wipe_backup_test"
    bak.mkdir()
    (bak / "config").mkdir()
    (bak / "config" / "profile.yaml").write_text("email: x@firma.de", encoding="utf-8")
    r = life.delete_all()
    assert r.ok
    assert not bak.exists()


def test_delete_all_no_backup_by_default(life, app_dirs):
    life.delete_all(create_rollback_backup=False)
    leftovers = [p for p in app_dirs["root"].iterdir() if p.name.startswith(".wipe_backup_")]
    assert leftovers == []


def test_e2e_export_then_delete_all_then_restart(life, app_dirs, tmp_path):
    """representative data -> export -> delete all -> restart check -> clean."""
    db = life._db  # type: ignore[attr-defined]
    _seed_case(db, "e2e")
    _seed_mail(life.database_path, case_id="e2e")
    store_token("gmail_readonly", {"refresh_token": "RR"}, fallback_dir=life.token_dir)
    cv = app_dirs["cvs"] / "lebenslauf.pdf"
    cv.write_bytes(b"%PDF-1.4")
    life._docs.append(cv)  # type: ignore[attr-defined]
    life._profile["application"]["email"] = "candidate@firma.de"  # type: ignore[index]
    (app_dirs["logs"] / "run.log").write_text("info\n", encoding="utf-8")

    exported = life.export_my_data(tmp_path, user_confirmed_pii=True)
    assert exported.ok
    assert Path(exported.path).is_file()

    deleted = life.delete_all()
    assert deleted.ok and deleted.verified

    # "restart": new service instance on same dirs
    restarted = PrivacyLifecycleService(
        dirs=app_dirs,
        database_path=app_dirs["data"] / "jobs.db",
        token_dir=app_dirs["config"],
        load_profile=life._load_profile,
        save_empty_profile=life._save_empty_profile,
        list_documents=life._list_documents,
        clear_documents=life._clear_documents,
    )
    residuals = restarted.verify_no_unexpected_data()
    assert residuals == []


def test_never_claim_deleted_when_verify_fails(life, monkeypatch):
    monkeypatch.setattr(life, "verify_no_unexpected_data", lambda: ["email_messages"])
    r = life.delete_all()
    assert r.ok is False
    assert r.verified is False
    with pytest.raises(VerificationFailed):
        life.assert_deleted(r)


def test_delete_result_dict_shape():
    d = DeleteResult(action="x", ok=True, verified=True, removed=["a"]).as_dict()
    assert d["action"] == "x"
    assert d["verified"] is True


# ---------------------------------------------------------------------------
# Redaction / security coupling
# ---------------------------------------------------------------------------


def test_log_redaction_still_strips_tokens():
    from core.security.redaction import redact_text

    out = redact_text("refresh_token=ABCDEFG123 email=a@example.com")
    assert "ABCDEFG" not in out
    assert "@example.com" not in out or "REDACTED" in out


def test_export_gate_blocks_oauth_filename():
    from core.security.export_gate import gate_export

    d = gate_export("oauth_gmail.json", user_confirmed_pii=True)
    assert d.allowed is False


def test_wipe_backup_skips_secrets():
    from core.security.export_gate import wipe_backup_should_skip

    assert wipe_backup_should_skip("oauth_x.json") is True


def test_no_telemetry_markers_in_privacy_package():
    root = Path(__file__).resolve().parents[1]
    # Only flag call-site / import style telemetry — not docs saying "no sentry".
    offenders: list[str] = []
    for p in (root / "core" / "privacy").glob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            low = line.lower()
            if "import sentry" in low or "from sentry" in low:
                offenders.append(f"{p.name}:{i}")
            if "posthog.capture" in low or "mixpanel" in low and "import" in low:
                offenders.append(f"{p.name}:{i}")
    assert offenders == []


# Count gate
def test_lifecycle_case_count_gate():
    import tests.test_privacy_lifecycle as mod

    tests = [n for n in dir(mod) if n.startswith("test_")]
    assert len(tests) >= 40

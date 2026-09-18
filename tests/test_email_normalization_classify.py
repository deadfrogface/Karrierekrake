"""Email normalization + classification corpus (synthetic only, PR28).

No real recruiting mail. Bodies are untrusted content throughout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.email_classify import (
    CLASSIFIER_VERSION,
    EmailLifecycleClass,
    classify_email,
    classify_normalized,
)
from integrations.email_normalize import (
    NORMALIZED_EMAIL_VERSION,
    needs_renormalization,
    normalize_from_parts,
    normalize_raw_mime,
    split_quoted_history,
    split_signature,
)

FIXTURES = Path(__file__).parent / "fixtures" / "email_corpus"
CORPUS = FIXTURES / "normalization_corpus.json"
UNAMBIGUOUS = FIXTURES / "unambiguous_classification.json"


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert len(data) >= 150, f"need >=150 normalization cases, got {len(data)}"
    return data


def _normalize_case(row: dict):
    if row.get("raw_mime") is not None:
        return normalize_raw_mime(row["raw_mime"])
    return normalize_from_parts(
        subject=row.get("subject") or "",
        sender=row.get("sender") or "hr@nordlicht.example.com",
        body_html_or_text=row.get("body") or "",
    )


def test_corpus_size_and_privacy_markers(corpus):
    assert len(corpus) >= 150
    blob = CORPUS.read_text(encoding="utf-8").lower()
    for banned in ("@gmail.com", "@googlemail.com", "@outlook.com", "@yahoo.com"):
        assert banned not in blob


def test_no_parser_crash_on_full_corpus(corpus):
    for row in corpus:
        ne = _normalize_case(row)
        assert ne.schema_version == NORMALIZED_EMAIL_VERSION
        assert isinstance(ne.body_text, str)
        assert isinstance(ne.parse_warnings, list)
        for att in ne.attachments:
            assert att.filename
            assert att.content_type
            assert att.size_bytes >= 0


@pytest.mark.parametrize(
    "row_id",
    [
        "multipart-confirm-1",
        "html-only-confirm-1",
        "quoted-invite-over-reject-1",
        "multipart-attach-1",
        "malformed-empty-1",
        "malformed-double-from-1",
        "injection-1",
    ],
)
def test_selected_normalization_expectations(corpus, row_id):
    row = next(r for r in corpus if r["id"] == row_id)
    ne = _normalize_case(row)
    exp = row.get("expect_norm") or {}
    if exp.get("is_multipart"):
        assert ne.is_multipart is True
    if exp.get("has_quoted"):
        assert ne.quoted_history
    if exp.get("body_excludes"):
        assert exp["body_excludes"].lower() not in (ne.body_text or "").lower()
    if exp.get("attachment_count") is not None:
        assert len(ne.attachments) == exp["attachment_count"]
    if exp.get("attachment_name_contains"):
        names = " ".join(a.filename for a in ne.attachments)
        assert exp["attachment_name_contains"] in names
    if exp.get("is_forwarded"):
        assert ne.is_forwarded is True
    if exp.get("no_script"):
        assert "<script" not in (ne.html_text or "").lower()
        assert "alert(" not in (ne.body_text or "").lower()
    if row_id == "malformed-double-from-1":
        assert "duplicate_from_header" in ne.parse_warnings or ne.from_email


def test_quoted_history_split_unit():
    text = "Neu: Interview invitation\n\n> old absage leider müssen wir ihnen mitteilen"
    cur, quoted = split_quoted_history(text)
    assert "Interview" in cur
    assert "absage" in quoted.lower()
    assert "absage" not in cur.lower()


def test_signature_split_unit():
    text = "Wir haben Ihre Bewerbung erhalten.\n\nMit freundlichen Grüßen\nHR Team"
    body, sig = split_signature(text)
    assert "Bewerbung erhalten" in body
    assert "Mit freundlichen" in sig


def test_needs_renormalization_version_gate():
    assert needs_renormalization(None) is True
    assert needs_renormalization({"schema_version": 0}) is True
    fresh = normalize_from_parts(subject="x", body_html_or_text="y")
    assert needs_renormalization(fresh) is False
    assert needs_renormalization(fresh.to_dict()) is False


def test_injection_never_becomes_high_impact(corpus):
    for row in corpus:
        if row.get("kind") != "injection":
            continue
        ne = _normalize_case(row)
        result = classify_normalized(ne)
        assert result.category in {"review", "other", "noise"}
        assert result.lifecycle_class in {
            EmailLifecycleClass.UNKNOWN,
            EmailLifecycleClass.NOISE,
            EmailLifecycleClass.GENERAL,
        }
        assert result.category != "offer"
        assert result.category != "rejection"
        assert result.needs_review or result.confidence < 0.55
        exp = row.get("expect_class") or {}
        if exp.get("blocked"):
            assert result.false_rejection_blocked or "instruction_frame" in " ".join(
                result.reasons
            )


def test_unambiguous_classification_e2e_accuracy():
    rows = json.loads(UNAMBIGUOUS.read_text(encoding="utf-8"))
    assert len(rows) >= 40
    ok = 0
    failures = []
    for row in rows:
        ne = _normalize_case(row)
        result = classify_normalized(ne)
        exp = row["expect_class"]
        cat_ok = True
        if "category" in exp and result.category != exp["category"]:
            cat_ok = False
        if cat_ok and "lifecycle" in exp and result.lifecycle_class != exp["lifecycle"]:
            cat_ok = False
        if cat_ok and "min_conf" in exp and result.confidence < exp["min_conf"]:
            cat_ok = False
        if cat_ok:
            ok += 1
        else:
            failures.append(
                (
                    row["id"],
                    exp,
                    result.category,
                    result.lifecycle_class,
                    result.confidence,
                    result.reasons[:3],
                )
            )
    rate = ok / len(rows)
    assert rate >= 0.99, f"accuracy {rate:.3%} < 99%; failures={failures[:12]}"


def test_low_confidence_fail_safe():
    result = classify_email("Hallo", "irgendein belanglose r Text ohne Muster")
    assert result.needs_review or result.lifecycle_class == EmailLifecycleClass.UNKNOWN
    assert result.category in {"review", "other"}


def test_review_only_mode_and_version_rollback():
    body = (
        "leider müssen wir Ihnen mitteilen, dass wir Ihre Bewerbung "
        "nicht berücksichtigen können."
    )
    normal = classify_email("Absage", body)
    assert normal.category == "rejection"
    rolled = classify_email("Absage", body, review_only_mode=True)
    assert rolled.needs_review is True
    assert rolled.lifecycle_class == EmailLifecycleClass.UNKNOWN
    bad_ver = classify_email("Absage", body, classifier_version="0.0.0-missing")
    assert bad_ver.needs_review is True
    assert CLASSIFIER_VERSION in {"1.0.0"}


def test_classifier_version_attached():
    r = classify_email("Application received", "We have received your application.")
    assert r.classifier_version == CLASSIFIER_VERSION
    assert r.lifecycle_class == EmailLifecycleClass.APPLICATION_RECEIVED
    assert r.category == "confirmation"
    assert r.evidence


def test_quoted_old_rejection_does_not_dominate_new_invite():
    body = (
        "wir laden Sie zu einem Vorstellungsgespräch ein. Terminvorschlag Teams Meeting.\n\n"
        "Am 1. Januar schrieb HR:\n"
        "> leider müssen wir Ihnen mitteilen Absage andere Bewerber\n"
    )
    ne = normalize_from_parts(subject="Einladung", body_html_or_text=body)
    assert "Absage" in ne.quoted_history or "absage" in ne.quoted_history.lower()
    result = classify_normalized(ne)
    assert result.category == "interview"
    assert result.lifecycle_class == EmailLifecycleClass.INTERVIEW_INVITE


def test_commercial_classifier_does_not_imply_side_effects():
    """Classifier returns labels only — no status/mail/calendar action fields."""
    r = classify_email(
        "Stellenangebot",
        "wir möchten Ihnen gerne eine Stelle anbieten. Anstellungsangebot.",
    )
    data = {
        "category": r.category,
        "lifecycle_class": r.lifecycle_class,
        "confidence": r.confidence,
        "evidence": r.evidence,
        "needs_review": r.needs_review,
    }
    assert "send_email" not in data
    assert "status_write" not in data
    assert "calendar_action" not in data
    assert r.lifecycle_class == EmailLifecycleClass.OFFER

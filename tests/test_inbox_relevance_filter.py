"""Mail without any link to an application (receipts, rides, railway forms) stays out of the default inbox view."""
from core.database import Database
from integrations.email_classify import classify_email, has_hiring_context
from integrations.mail.local_sorter import demote_unrelated_confirmations


def test_railway_receipt_is_not_a_confirmation():
    result = classify_email("Fahrgastrechteantrag Eingangsbestätigung 22E03286015",
                            "Wir bestätigen den Eingang Ihres Antrags. Ihre Unterlagen sind vollständig.")
    assert result.category != "confirmation"
    assert "no_hiring_context" in result.reasons


def test_real_application_confirmation_still_counts():
    result = classify_email("Eingangsbestätigung Ihrer Bewerbung",
                            "Vielen Dank für Ihre Bewerbung. Wir haben Ihre Bewerbung erhalten.")
    assert result.category == "confirmation"
    assert has_hiring_context("Ihre Bewerbung", "")


def _mail(db, gid, subject, category, status):
    db.save_email_message({"gmail_id": gid, "subject": subject, "sender": "x@example.org", "body_text": subject,
                           "category": category, "confidence": 0.5, "association_status": status})


def test_default_view_hides_unrelated_mail_but_all_view_keeps_it(tmp_path):
    db = Database(tmp_path / "jobs.db")
    _mail(db, "1", "Zahlung an Bolt", "review", "unlinked")
    _mail(db, "2", "Werbung", "noise", "unlinked")
    _mail(db, "3", "Einladung zum Gespräch", "interview", "unlinked")
    _mail(db, "4", "Rückfrage", "other", "linked")
    shown = {r["subject"] for r in db.list_inbox_emails(relevant_only=True)}
    assert shown == {"Einladung zum Gespräch", "Rückfrage"}
    assert len(db.list_inbox_emails()) == 4
    assert db.count_unrelated_emails() == 2


def test_old_unrelated_confirmation_is_demoted(tmp_path):
    db = Database(tmp_path / "jobs.db")
    _mail(db, "1", "Eingangsbestätigung 22E03286015", "confirmation", "unlinked")
    _mail(db, "2", "Eingangsbestätigung Ihrer Bewerbung", "confirmation", "unlinked")
    assert demote_unrelated_confirmations(db) == 1
    assert {r["subject"]: r["category"] for r in db.list_inbox_emails()} == {
        "Eingangsbestätigung 22E03286015": "other", "Eingangsbestätigung Ihrer Bewerbung": "confirmation"}

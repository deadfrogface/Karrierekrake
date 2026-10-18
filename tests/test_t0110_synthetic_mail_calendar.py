"""T01.10 acceptance against the Personaler's gold (synthetic account, offline).

Work item: "Echte Mail-/Kalenderkonten und vom Nutzer bewertete Bewerbungen
abnehmen" -- decided: synthetic accounts/data replace real ones.

Inputs:  tests/fixtures/t0110_synthetic_account/* (input commits 0e17877,
         164f885, 2f5ab8b). Gold: expected.json (commit 86a0e89, Personaler).
Rules:   gold and fixtures are never modified; product behaviour that
         disagrees with gold stays red. Every test runs with the clock frozen
         to ``reference_now`` from account.json and under a network guard
         (0 attempts, gold ``defaults.network_attempts``).

Product paths exercised (no Qt):
  * mail file import  integrations.mail.local_sorter.import_mail_file
  * IMAP sync         integrations.mail.local_sorter.sync_local_mail with an
                      in-process IMAP4_SSL stand-in (no socket)
  * slots             integrations.calendar_scheduling.propose_ranked_slots +
                      CalendarSession(local_ics) exactly as
                      desktop/pages/lifecycle.py wires them
  * drafts            integrations.reply_draft.build_action_draft, action
                      chosen exactly as desktop/pages/lifecycle.py
                      ``prepare_followup_draft`` does (mirrored here, Qt-free)
  * ICS               integrations.calendar_write.draft_from_ranked_slot /
                      draft_to_ics / export_approved_ics, title and
                      client_request_id as in ``prepare_calendar_proposal``
  * gates             SendGate / CalendarWriteGate defaults

Semantic gold items ("Widerspruch", "Grund der Verhinderung", ...) are
checked by heuristic functions over the draft text; they are applied to the
deterministic product output only. See UNSICHER_ITEMS for what cannot be
judged offline.
"""

from __future__ import annotations

import hashlib
import json
import mailbox
import os
import re
import shutil
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tests.test_t0110_no_network_send import NetworkGuard

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "t0110_synthetic_account"
GOLD_PATH = FIXTURE_DIR / "expected.json"
GOLD_SHA256 = "5cd3a9947d8fe1d08081a49d5a73a0d83ec7e9db37bb94a0c551f65cb20dea6c"


def _load(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


ACCOUNT = _load("account.json")
CASES = _load("cases.json")["cases"]
DOCUMENTS = _load("documents.json")["documents"]
PROFILE = _load("profile.json")
GOLD = _load("expected.json")
GOLD_MAILS = {m["n"]: m for m in GOLD["mails"]}
REFERENCE_NOW = ACCOUNT["reference_now"]
TZ = ZoneInfo(ACCOUNT["timezone"])
APPLICANT = ACCOUNT["candidate"]["display_name"]
CASES_BY_ID = {c["case_id"]: c for c in CASES}
DOCUMENT_NAMES = {d["file_name"] for d in DOCUMENTS}

# Gold vocabulary -> product vocabulary (explicit, reviewed mapping).
GOLD_STATUS_TO_PRODUCT = {"beworben": "applied"}
GOLD_CATEGORY_TO_PRODUCT = {
    "eingangsbestaetigung": "confirmation",
    "einladung": "interview",
    "absage": "rejection",
    "unterlagen_anfrage": "document_request",
    "termin_absage": "interview_cancelled",
    "ausgeschlossen": "noise",
    # "mehrdeutig" is an association outcome, not a classifier label:
    # checked via association_status in {ambiguous, review_required}.
}
INTERVIEW_LIKE = {"interview", "interview_invite", "interview_reschedule"}  # desktop/pages/lifecycle.py

# Teamlead decision (binding): the original gold deviations are strict xfails so
# linux-pytest is green while each deviation stays visible. One deviation per
# test; a product fix turns the test XPASS -> red until the marker is removed.
# point = Teamlead deviation point 1-8 (see PR #192 body / coverage entry).
ORIGINAL_XFAILS: list[dict[str, Any]] = []


class MissingDraft(AssertionError):
    """No product draft exists, so a draft-content check cannot run.

    Content-test markers for mails without a draft use raises=MissingDraft: if
    the product starts producing a draft, a failing content check raises a
    plain AssertionError, which does not match and turns the test red.
    """


def require_draft(n: int, draft, how: str = ""):
    if draft is None:
        raise MissingDraft(f"mail {n}: no product draft ({how})")
    return draft


def _xf(test: str, n: int, gold_field: str, deviation: str, point: int, raises=AssertionError):
    ORIGINAL_XFAILS.append(
        {"test": test, "mail": n, "gold_field": gold_field, "deviation": deviation, "point": point,
         "raises": raises.__name__}
    )
    return pytest.mark.xfail(strict=True, raises=raises, reason=f"M{n} {gold_field}: {deviation}")


def _p(*values, xf=None, id=None):
    return pytest.param(*values, marks=[xf] if xf is not None else [], id=id)


UNSICHER_ITEMS = [
    "Günther (LLM) e-mail assist is stubbed (ok=False); its suggestions cannot be judged offline.",
    "No LLM draft path is exercised; only deterministic build_action_draft output is checked. "
    "Any LLM-written draft text remains unjudged.",
    "Semantic must_not items (Widerspruch, Diskussion der Entscheidung, Grund der Verhinderung, "
    "Nachfrage nach Gründen, eigener neuer Terminvorschlag, Zusage eines Slots, geschlechtsspezifische "
    "Selbstbeschreibung, SQL-Zertifikat als vorhanden) are keyword/regex heuristics; absence of a "
    "match is not proof. Personaler judges the texts in t0110_evidence.md.",
    "draft_type optional_kurzer_dank / optional_kurze_kenntnisnahme: only 'contains thanks / is short / "
    "proposes nothing' is checked; tone and appropriateness are Personaler-Urteil.",
    "Attachments: ReplyDraft has no attachment field; the product attaches nothing. "
    "'attachments only from documents.json' is therefore checked on draft text and VerifiedFacts.documents only.",
    "Mail 6 'may_state' (kein SQL-Zertifikat, SQL-Grundkenntnisse) is optional and not asserted.",
    "user_hint texts (mail 6 Frist 23.10., mail 7 Gehalt/Eintritt) are UI hints; the product has no "
    "deterministic hint output to compare.",
    "Real mail/calendar providers (IMAP server, Google/Microsoft/CalDAV) are not contacted; the IMAP "
    "path is an in-process stand-in for imaplib.IMAP4_SSL.",
]


def frozen_reference_now():
    return freeze_time(REFERENCE_NOW)


def stub_guenther(monkeypatch) -> None:
    """Günther is an optional local LLM; offline tests keep it unavailable."""
    monkeypatch.setattr(
        "guenther.service.get_guenther_service",
        lambda **kw: NS(suggest_email_class=lambda *a, **k: NS(ok=False, validated=False)),
    )


@pytest.fixture(autouse=True)
def _t0110_environment(monkeypatch):
    guard = NetworkGuard(allow_loopback=False).install(monkeypatch)
    stub_guenther(monkeypatch)
    with frozen_reference_now():
        yield
    guard.assert_clean()


# ---------------------------------------------------------------- fixtures --


def mbox_messages() -> list:
    box = mailbox.mbox(FIXTURE_DIR / ACCOUNT["inputs"]["mbox"], create=False)
    try:
        return list(box)
    finally:
        box.close()


def import_id(message) -> str:
    """Same identifier import_mail_file derives (local_sorter.py)."""
    return "import:" + hashlib.sha256(message.as_bytes()).hexdigest()


def seed_db(tmp: Path):
    from core.database import Database
    from core.lifecycle import ApplicationCase

    db = Database(tmp / "jobs.db")
    for c in CASES:
        db.upsert_case(
            ApplicationCase(
                id=c["case_id"],
                company=c["company"],
                position=c["position"],
                status=GOLD_STATUS_TO_PRODUCT[c["status"]],
                contact_email=c["contact_email"],
                contact_name=c["contact_person_as_written"],
                applied_at=c["applied_on"],
                source="t0110_fixture",
            )
        )
    return db


def make_settings(tmp: Path):
    """local_ics settings with a copy of calendar.ics; mtime = reference_now."""
    from core.config import SettingsConfig

    snapshot = tmp / "calendar-snapshot.ics"
    shutil.copyfile(FIXTURE_DIR / ACCOUNT["inputs"]["calendar"], snapshot)
    stamp = datetime.fromisoformat(REFERENCE_NOW).timestamp()
    os.utime(snapshot, (stamp, stamp))
    settings = SettingsConfig()
    settings.calendar_provider = "local_ics"
    settings.local_calendar_path = str(snapshot)
    settings.gmail_exclude_senders = list(ACCOUNT["gmail_exclude_senders"])
    settings.scheduling_timezone = ACCOUNT["timezone"]
    return settings, snapshot


class ImapStandIn:
    """In-process replacement for imaplib.IMAP4_SSL serving inbox.mbox.

    Opens no socket; records host/port and every command. Read-only
    (select readonly, BODY.PEEK).
    """

    instances: list[ImapStandIn] = []

    def __init__(self, host, port=993, *a, **kw):
        self.host, self.port = host, port
        self.calls: list[tuple] = []
        self.logged_out = False
        self._raw = {str(i).encode(): m.as_bytes() for i, m in enumerate(mbox_messages(), start=1)}
        ImapStandIn.instances.append(self)

    def login(self, user, password):
        self.calls.append(("login", user))
        return "OK", []

    def select(self, name, readonly=False):
        assert name == "INBOX" and readonly
        self.calls.append(("select", name, readonly))
        return "OK", []

    def response(self, key):
        return key, [b"20261018"]

    def uid(self, command, *args):
        self.calls.append(("uid", command, args))
        if command == "search":
            return "OK", [b" ".join(sorted(self._raw, key=int))]
        assert command == "fetch" and args[1] == "(BODY.PEEK[])"
        return "OK", [(b"RFC822", self._raw[args[0]])]

    def logout(self):
        self.logged_out = True


def imap_sync(db, tmp: Path, settings, monkeypatch):
    from integrations.mail import local_sorter
    from integrations.mail.imap import adapter as imap

    ImapStandIn.instances = []
    monkeypatch.setattr(imap.imaplib, "IMAP4_SSL", ImapStandIn)
    imap.store_imap_secret(
        {
            "host": ACCOUNT["imap_host"],
            "port": ACCOUNT["imap_port"],
            "username": ACCOUNT["imap_username"],
            "password": "synthetic-not-a-secret",
        },
        token_dir=tmp,
    )
    first = local_sorter.sync_local_mail(db, token_dir=tmp, settings=settings)
    second = local_sorter.sync_local_mail(db, token_dir=tmp, settings=settings)
    rows = {}
    for row in db.list_inbox_emails(limit=500):
        gid = str(row.get("gmail_id") or "")
        if gid.startswith("imap:"):
            rows[int(gid.rsplit(":", 1)[1])] = row
    return first, second, rows


@dataclass
class World:
    tmp: Path
    db: Any
    settings: Any
    snapshot: Path
    import_counts: tuple = ()
    reimport_counts: tuple = ()
    rows: dict = field(default_factory=dict)
    proposals: dict = field(default_factory=dict)


def build_world(tmp: Path) -> World:
    from integrations.mail.local_sorter import import_mail_file

    db = seed_db(tmp)
    settings, snapshot = make_settings(tmp)
    mbox = FIXTURE_DIR / ACCOUNT["inputs"]["mbox"]
    first = import_mail_file(db, mbox, exclude_senders=settings.gmail_exclude_senders)
    second = import_mail_file(db, mbox, exclude_senders=settings.gmail_exclude_senders)
    rows = {}
    for n, message in enumerate(mbox_messages(), start=1):
        rows[n] = db.get_email_by_gmail_id(import_id(message))
    return World(tmp, db, settings, snapshot, first, second, rows)


@pytest.fixture
def world(tmp_path) -> World:
    return build_world(tmp_path)


# ------------------------------------------------------------ product path --


def product_proposal(w: World, n: int):
    """propose_ranked_slots as desktop/pages/lifecycle.py calls it."""
    from core.scheduling_preferences import preferences_from_settings_config
    from integrations.calendar.session import CalendarSession
    from integrations.calendar_scheduling import propose_ranked_slots

    if n not in w.proposals:
        row = w.rows[n]
        w.proposals[n] = propose_ranked_slots(
            row.get("body_text") or "",
            case_id=row.get("case_id") or "",
            prefs=preferences_from_settings_config(w.settings),
            freebusy=CalendarSession(w.settings, token_dir=w.tmp),
        )
    return w.proposals[n]


def product_draft(w: World, n: int):
    """Mirror of inbox._action_draft + lifecycle.prepare_followup_draft (Qt-free).

    Returns (draft | None, how). A draft exists only for a linked case;
    interview-like mails get PROPOSE_SLOTS with the top-3 ranked slots, or no
    draft when no slot is free ("calendar.no_slots"); every other category
    gets GENERAL_REPLY.
    """
    from integrations.reply_draft import ReplyAction, build_action_draft

    row = w.rows[n]
    case_id = row.get("case_id") or ""
    if not case_id:
        return None, "no_case_linked"
    case = w.db.get_case(case_id)
    category = (row.get("category") or "").lower()
    if category in INTERVIEW_LIKE:
        proposal = product_proposal(w, n)
        if not proposal.ranked_slots:
            return None, f"no_slots:{proposal.stop_reason}"
        draft = build_action_draft(
            ReplyAction.PROPOSE_SLOTS,
            case.to_dict(),
            applicant_name=APPLICANT,
            proposed_slots=[s.start.isoformat() for s in proposal.ranked_slots[:3]],
        )
        return draft, "PROPOSE_SLOTS"
    draft = build_action_draft(ReplyAction.GENERAL_REPLY, case.to_dict(), applicant_name=APPLICANT)
    return draft, "GENERAL_REPLY"


def draft_text(draft) -> str:
    return f"{draft.subject}\n{draft.body}" if draft is not None else ""


def draft_attachments(draft) -> list[str]:
    """Product ReplyDraft has no attachment field; documents named via facts only."""
    return list(getattr(draft, "attachments", None) or [])


def gold_slot(spec: str) -> tuple[datetime, datetime]:
    day, times = spec.split("T")
    start_s, end_s = times.split("/")
    start = datetime.fromisoformat(f"{day}T{start_s}").replace(tzinfo=TZ)
    end = datetime.fromisoformat(f"{day}T{end_s}").replace(tzinfo=TZ)
    return start, end


def slot_spec(start: datetime, end: datetime) -> str:
    s, e = start.astimezone(TZ), end.astimezone(TZ)
    return f"{s:%Y-%m-%dT%H:%M}/{e:%H:%M}"


def ics_draft_for_slot(w: World, n: int, spec: str):
    """User selects ``spec`` in the preview; draft as prepare_calendar_proposal builds it."""
    from integrations.calendar_scheduling import select_slot
    from integrations.calendar_write import draft_from_ranked_slot
    from integrations.reply_draft import human_slot

    proposal = product_proposal(w, n)
    specs = [slot_spec(s.start, s.end) for s in proposal.ranked_slots]
    if spec not in specs:
        return None, specs
    index = specs.index(spec)
    selected = proposal.ranked_slots[index]
    case = w.db.get_case(proposal.case_id)
    chosen = human_slot(selected.start.isoformat()) + " – " + selected.end.strftime("%H:%M Uhr")
    proposal = select_slot(proposal, index)
    draft = draft_from_ranked_slot(proposal, client_request_id=f"{proposal.case_id}:{chosen}")
    draft.title = f"{case.company} — {case.position}"
    return draft, specs


def unfold_ics(text: str) -> list[str]:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def ics_lines(text: str, name: str) -> list[str]:
    return [ln for ln in unfold_ics(text) if re.match(rf"{name}[;:]", ln)]


# ----------------------------------------------------- draft text checkers --

_DATE_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")
_NEG_RE = re.compile(r"\b(kein|keine|keinen|keiner|nicht)\b", re.I)


def salutation(text_body: str) -> str:
    for line in (text_body or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def sql_certificate_presented(text: str, attachments: list[str]) -> bool:
    """SQL certificate as existing / attached / to be sent: violation."""
    if any(re.search(r"zertifi|certificate", a, re.I) for a in attachments):
        return True
    for sentence in _sentences(text):
        if re.search(r"zertifi|certificate", sentence, re.I) and not _NEG_RE.search(sentence):
            return True
    return False


def gendered_self_description(text: str) -> bool:
    return bool(
        re.search(
            r"\b(bewerberin|kandidatin|als\s+(frau|mann)\b|(herr|frau)\s+robin|ich\s+bin\s+(eine\s+)?(frau|mann))",
            text or "",
            re.I,
        )
    )


FORBIDDEN_IN_ANY_DRAFT: dict[str, Callable[[str, list[str]], bool]] = {
    "Lindenhof": lambda t, a: bool(re.search(r"lindenhof", t, re.I)),
    "Gehaltsvorstellung": lambda t, a: bool(re.search(r"gehalt|salär|salary|vergütung|brutto", t, re.I)),
    "Eintrittstermin": lambda t, a: bool(
        re.search(r"eintritt|starttermin|startdatum|frühestmöglich|verfügbar ab|ab sofort", t, re.I)
    ),
    "Kündigungsfrist": lambda t, a: bool(re.search(r"kündigung|notice period", t, re.I)),
    "SQL-Zertifikat als vorhanden oder als Anhang": sql_certificate_presented,
    "geschlechtsspezifische Selbstbeschreibung (Profil ohne Geschlecht)": lambda t, a: gendered_self_description(t),
}


def _offered_dates(n: int) -> list[str]:
    out = []
    for spec in GOLD_MAILS[n].get("slots_offered", []):
        start, _ = gold_slot(spec)
        out.append(f"{start:%d.%m.%Y}")
    return out


def accepts_offered_slot(n: int, text: str) -> bool:
    for sentence in _sentences(text):
        if any(d in sentence for d in _offered_dates(n)) and re.search(
            r"passt|passen|wahrnehmen|nehme|bestätige|zusage|sage .* zu", sentence, re.I
        ):
            return True
    return False


def proposes_own_dates(text: str) -> bool:
    return bool(
        _DATE_RE.search(text or "")
        or re.search(r"\bum \d{1,2}[:.]\d{2}\b|passen mir|schlage .* vor|alternativ|neuen termin vor", text or "", re.I)
    )


MUST_NOT: dict[str, Callable[[int, str, list[str]], bool]] = {
    "Zusage eines angebotenen Slots": lambda n, t, a: accepts_offered_slot(n, t),
    "Grund der Verhinderung": lambda n, t, a: bool(
        re.search(
            r"\bweil\b|\bda ich\b|zahnarzt|sprachkurs|umzug|elternabend|lindenhof|anderen termin|"
            r"anderes (vorstellungs)?gespräch|bereits verplant|verhindert, da",
            t,
            re.I,
        )
    ),
    "Lindenhof": lambda n, t, a: bool(re.search(r"lindenhof", t, re.I)),
    "Widerspruch": lambda n, t, a: bool(re.search(r"widersp|einspruch|nicht einverstanden", t, re.I)),
    "Diskussion der Entscheidung": lambda n, t, a: bool(
        re.search(r"überdenken|nachvollziehen|warum|weshalb|wieso|begründ|gründe|nochmals prüfen", t, re.I)
    ),
    "eigener neuer Terminvorschlag": lambda n, t, a: proposes_own_dates(t),
    "Nachfrage nach Gründen": lambda n, t, a: bool(re.search(r"warum|weshalb|wieso|\bgrund\b|gründe", t, re.I)),
    "SQL-Zertifikat als vorhanden, beigefügt oder nachgereicht darstellen": (
        lambda n, t, a: sql_certificate_presented(t, a)
    ),
    "Anhang außer Arbeitszeugnis_Vorarbeitgeber.pdf": lambda n, t, a: bool(
        set(a) - set(GOLD_MAILS[n].get("attachments_allowed", []))
        or any(name in t for name in DOCUMENT_NAMES - set(GOLD_MAILS[n].get("attachments_allowed", [])))
    ),
}


def _dt_exactly_one_slot(n, draft):
    rank1, _ = gold_slot(GOLD_MAILS[n]["slot_rank_1"])
    dates = _DATE_RE.findall(draft.body)
    if dates != [f"{rank1:%d.%m.%Y}"]:
        return f"expected exactly one slot {rank1:%d.%m.%Y}, draft names {dates}"
    return None


def _dt_slot_time(n, draft):
    rank1, _ = gold_slot(GOLD_MAILS[n]["slot_rank_1"])
    return None if f"{rank1:%H:%M}" in draft.body else f"slot time {rank1:%H:%M} missing"


def _dt_acceptance_wording(n, draft):
    return None if re.search(r"passt|wahrnehmen|bestätige|zusage", draft.body, re.I) else "no acceptance wording"


def _dt_no_acceptance(n, draft):
    return "accepts an offered slot" if accepts_offered_slot(n, draft_text(draft)) else None


def _dt_alternative_request(n, draft):
    pattern = r"alternativ|andere[nrs]? termin|weitere[nr]? termin|neue[nr]? termin"
    return None if re.search(pattern, draft.body, re.I) else "no request for alternative dates"


def _dt_thanks(n, draft):
    return None if re.search(r"dank", draft.body, re.I) else "no thanks"


def _dt_short(n, draft):
    return "not short" if len(draft.body) > 700 else None


def _dt_attachments_allowed(n, draft):
    allowed = set(GOLD_MAILS[n].get("attachments_allowed", []))
    return f"attachments outside {sorted(allowed)}" if set(draft_attachments(draft)) - allowed else None


def _dt_no_sql_certificate(n, draft):
    presented = sql_certificate_presented(draft_text(draft), draft_attachments(draft))
    return "SQL certificate presented" if presented else None


def _dt_no_own_dates(n, draft):
    return "proposes own dates" if proposes_own_dates(draft.body) else None


DRAFT_TYPE_CHECKS: dict[str, list[tuple[str, Callable[[int, Any], str | None]]]] = {
    "zusage_genau_ein_slot": [
        ("exactly_one_slot", _dt_exactly_one_slot),
        ("slot_time", _dt_slot_time),
        ("acceptance_wording", _dt_acceptance_wording),
    ],
    "keine_zusage_bitte_um_alternativtermine": [
        ("no_acceptance", _dt_no_acceptance),
        ("alternative_request", _dt_alternative_request),
    ],
    "optional_kurzer_dank": [("thanks", _dt_thanks), ("short", _dt_short)],
    "nur_vorhandene_unterlagen": [
        ("attachments_allowed", _dt_attachments_allowed),
        ("no_sql_certificate", _dt_no_sql_certificate),
    ],
    "optional_kurze_kenntnisnahme": [("no_own_dates", _dt_no_own_dates), ("short", _dt_short)],
}


def draft_type_violations(n: int, draft) -> list[str]:
    """All draft_type item checks (evidence report); tests run them one by one."""
    kind = GOLD_MAILS[n].get("draft_type")
    if draft is None:
        return [f"no product draft for draft_type {kind!r}"]
    if kind not in DRAFT_TYPE_CHECKS:
        return [f"no checker for draft_type {kind!r}"]
    return [msg for _, fn in DRAFT_TYPE_CHECKS[kind] if (msg := fn(n, draft))]


# ------------------------------------------------------------ gold & time --


def test_gold_expected_json_sha256_is_personaler_gold():
    assert hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest() == GOLD_SHA256


def test_clock_frozen_to_reference_now():
    assert ACCOUNT["reference_now"] == GOLD["reference_now"] == "2026-10-18T09:00:00+02:00"
    now = datetime.now(UTC)
    assert now == datetime.fromisoformat(REFERENCE_NOW)
    assert ACCOUNT["network_access_allowed"] is False


# ------------------------------------------------------------- mail import --


def test_mail_import_twice_second_run_all_duplicates(world):
    assert world.import_counts == (9, 0)
    assert world.reimport_counts == (0, 9)
    assert len(world.db.list_inbox_emails(limit=500)) == 9
    assert all(world.rows[n] for n in range(1, 10))


_CATEGORY_XF = {
    6: _xf("test_mail_category_matches_gold[6]", 6, "category", "product review instead of document_request", 2),
}


@pytest.mark.parametrize("n", [_p(n, xf=_CATEGORY_XF.get(n), id=str(n)) for n in sorted(GOLD_MAILS)])
def test_mail_category_matches_gold(world, n):
    gold = GOLD_MAILS[n]
    row = world.rows[n]
    if gold["category"] == "mehrdeutig":
        assert row["association_status"] in {"ambiguous", "review_required"}, row["association_status"]
        return
    expected = GOLD_CATEGORY_TO_PRODUCT[gold["category"]]
    assert row["category"] == expected, (
        f"mail {n}: gold {gold['category']!r} (= product {expected!r}), product {row['category']!r} "
        f"conf={row.get('confidence')}"
    )


_NO_CASE = "no case assignment (sender bewerbung@/karriere@, reference number unusable)"
_CASE_XF = {n: _xf(f"test_mail_case_assignment_matches_gold[{n}]", n, "case_id", _NO_CASE, 1) for n in (1, 2)}
_LINKED_XF = {
    n: _xf(
        f"test_mail_association_linked_when_gold_has_case[{n}]", n, "case_id",
        f"association_status not linked; {_NO_CASE}", 1,
    )
    for n in (1, 2)
}


@pytest.mark.parametrize("n", [_p(n, xf=_CASE_XF.get(n), id=str(n)) for n in sorted(GOLD_MAILS)])
def test_mail_case_assignment_matches_gold(world, n):
    gold = GOLD_MAILS[n]
    row = world.rows[n]
    product_case = row.get("case_id") or None
    assert product_case == gold["case_id"], (
        f"mail {n}: gold case {gold['case_id']!r}, product {product_case!r} "
        f"({row.get('association_status')}: {row.get('association_explanation')})"
    )


@pytest.mark.parametrize(
    "n", [_p(n, xf=_LINKED_XF.get(n), id=str(n)) for n in sorted(GOLD_MAILS) if GOLD_MAILS[n]["case_id"]]
)
def test_mail_association_linked_when_gold_has_case(world, n):
    assert world.rows[n]["association_status"] == "linked", world.rows[n].get("association_explanation")


# Point 3 product fix (integrations/email_classify.py appointment_cancellation_hits):
# generic employer cancellation of an existing appointment. These synthetic cases
# guard against overfitting to the M9 fixture mail.
_CANCEL_RULE_CASES = {
    "cancel_entfaellt": (
        "Ihr Interview",
        "Hallo,\n\ndas für Freitag, 30.10.2026 geplante Interview entfällt leider.\n\nGruß",
        "interview_cancelled",
    ),
    "cancel_storniert_en": (
        "Interview update",
        "Hello,\n\nunfortunately we have to cancel the interview scheduled for 30.10.2026 at 10:00.\n\nBest",
        "interview_cancelled",
    ),
    "invite_with_conditional_absagen": (
        "Einladung zum Vorstellungsgespräch",
        "Guten Tag,\n\nwir laden Sie zum Vorstellungsgespräch am Dienstag, 27.10.2026, 10:00 Uhr ein. "
        "Falls Sie den Termin absagen müssen, geben Sie uns bitte kurz Bescheid.\n\nViele Grüße",
        "interview",
    ),
    "rejection_of_application": (
        "Absage Ihrer Bewerbung",
        "Guten Tag,\n\nleider müssen wir Ihnen mitteilen, dass wir uns für andere Bewerber entschieden "
        "haben.\n\nMit freundlichen Grüßen",
        "rejection",
    ),
    "reschedule_not_cancel": (
        "Terminverschiebung",
        "Guten Tag,\n\nleider müssen wir den Termin am 22.10.2026 verschieben. Können wir Ihnen einen "
        "neuen Termin am 23.10.2026 um 14:00 Uhr anbieten?\n\nViele Grüße",
        "interview",
    ),
    "rejection_mentions_past_interview": (
        "Absage zu Ihrer Bewerbung",
        "Guten Tag,\n\nvielen Dank für das Vorstellungsgespräch am 12.10.2026. Leider müssen wir Ihnen "
        "mitteilen, dass wir uns für andere Bewerber entschieden haben.\n\nMit freundlichen Grüßen",
        None,  # whatever the classifier said before the rule: must not change
    ),
}


@pytest.mark.parametrize("case", sorted(_CANCEL_RULE_CASES))
def test_appointment_cancellation_rule_is_generic(monkeypatch, case):
    import integrations.email_classify as ec

    subject, body, expected = _CANCEL_RULE_CASES[case]
    got = ec.classify_email(subject, body).category
    monkeypatch.setattr(ec, "appointment_cancellation_hits", lambda _text: [])
    without_rule = ec.classify_email(subject, body).category
    if expected is None:
        assert got == without_rule != "interview_cancelled", (got, without_rule)
    else:
        assert got == expected, (case, got)
        if expected != "interview_cancelled":
            assert got == without_rule, (case, got, without_rule)


def test_mail7_ambiguous_without_assignment(world):
    row = world.rows[7]
    assert GOLD_MAILS[7]["category"] == "mehrdeutig" and GOLD_MAILS[7]["case_id"] is None
    assert not row.get("case_id")
    assert row["association_status"] in {"ambiguous", "review_required"}
    assert int(row.get("association_confirmed") or 0) == 0


def test_mail8_excluded_and_not_linked_to_any_case(world):
    row = world.rows[8]
    assert GOLD_MAILS[8]["linked_to_any_case"] is False
    assert row["association_status"] == "excluded" and not row.get("case_id")
    for c in CASES:
        for ev in world.db.list_case_events(c["case_id"], limit=500):
            payload = json.loads(ev.payload_json or "{}")
            assert payload.get("email_id") != row["id"], (c["case_id"], ev.event_type)


def test_imap_stand_in_sync_path(tmp_path, monkeypatch, world):
    """sync_local_mail through an in-process IMAP4_SSL stand-in == file import."""
    imap_dir = tmp_path / "imap"
    imap_dir.mkdir()
    db = seed_db(imap_dir)
    first, second, rows = imap_sync(db, imap_dir, world.settings, monkeypatch)
    assert first.fetched == 9 and second.fetched == 0
    assert [(i.host, i.port) for i in ImapStandIn.instances] == [(ACCOUNT["imap_host"], ACCOUNT["imap_port"])] * 2
    assert all(i.logged_out for i in ImapStandIn.instances)
    assert all(c[0] != "uid" or c[1] in {"search", "fetch"} for i in ImapStandIn.instances for c in i.calls)
    assert sorted(rows) == list(range(1, 10))
    for n in range(1, 10):
        a, b = world.rows[n], rows[n]
        assert (b["category"], b.get("case_id") or None, b["association_status"]) == (
            a["category"],
            a.get("case_id") or None,
            a["association_status"],
        ), f"mail {n}: IMAP path differs from file import"
    for c in CASES:
        gold_status = GOLD["case_status_after_import"][c["case_id"]]
        assert db.get_case(c["case_id"]).status == GOLD_STATUS_TO_PRODUCT[gold_status]


def _non_seed_lifecycle(db, case_id):
    seeds = {"status_seed", "migration_backfill"}
    return [ev for ev in db.list_lifecycle_events(case_id) if (ev.source or "") not in seeds]


def test_auto_status_false_rejection_invite_cancellation_keep_case_status(tmp_path, monkeypatch, world):
    """Mail 5 (Absage), 3/4 (Einladung), 9 (Termin-Absage) never move a case."""
    assert GOLD["defaults"]["case_status_change"] is False
    assert GOLD_MAILS[5]["case_status_auto_change"] is False and GOLD_MAILS[9]["case_status_auto_change"] is False
    imap_dir = tmp_path / "imap"
    imap_dir.mkdir()
    imap_db = seed_db(imap_dir)
    imap_sync(imap_db, imap_dir, world.settings, monkeypatch)
    for db in (world.db, imap_db):
        for case_id, gold_status in GOLD["case_status_after_import"].items():
            assert db.get_case(case_id).status == GOLD_STATUS_TO_PRODUCT[gold_status]
            assert _non_seed_lifecycle(db, case_id) == [], case_id
    for n in (3, 4, 5, 9):
        assert world.rows[n]["case_id"], f"mail {n} must be linked for this check to be meaningful"


# ------------------------------------------------------------------- slots --

_OFFERED = [
    (n, spec, spec in GOLD_MAILS[n]["slots_allowed"])
    for n in (3, 4)
    for spec in GOLD_MAILS[n]["slots_offered"]
]


def test_calendar_snapshot_age_is_relative_to_frozen_now(world):
    from integrations.calendar.session import CalendarSession
    from integrations.calendar_freebusy import FreeBusyQuery
    from integrations.providers.enums import ProviderError

    session = CalendarSession(world.settings, token_dir=world.tmp)
    start, end = gold_slot("2026-10-29T09:30/10:30")
    assert session.query(FreeBusyQuery(time_min=start, time_max=end))
    old = (datetime.fromisoformat(REFERENCE_NOW) - timedelta(days=8)).timestamp()
    os.utime(world.snapshot, (old, old))
    with pytest.raises(ProviderError, match="stale"):
        session.query(FreeBusyQuery(time_min=start, time_max=end))


@pytest.mark.parametrize("n,spec,allowed", _OFFERED, ids=[f"mail{n}-{s}" for n, s, _ in _OFFERED])
def test_offered_slot_free_or_blocked_per_gold(world, n, spec, allowed):
    """Calendar layer only (RRULE/EXDATE, CANCELLED, busy blocks) with product prefs."""
    from core.scheduling_preferences import preferences_from_settings_config
    from integrations.calendar.session import CalendarSession
    from integrations.calendar_availability import ConstraintContext, TimeWindow, check_constraints
    from integrations.calendar_freebusy import FreeBusyQuery

    start, end = gold_slot(spec)
    session = CalendarSession(world.settings, token_dir=world.tmp)
    busy_exact = session.query(FreeBusyQuery(time_min=start, time_max=end))
    busy_day = session.query(
        FreeBusyQuery(time_min=start - timedelta(hours=3), time_max=end + timedelta(hours=3))
    )
    prefs = preferences_from_settings_config(world.settings)
    modality = product_proposal(world, n).modality
    ctx = ConstraintContext(prefs=prefs, modality=modality, busy=tuple(busy_day))
    result = check_constraints(TimeWindow(start, end), ctx)
    if allowed:
        assert busy_exact == [], f"{spec}: gold free ({GOLD_MAILS[n]['slots_allowed_reason'][spec]})"
        assert result.ok, (spec, result.reasons)
    else:
        assert busy_exact, f"{spec}: gold blocked ({GOLD_MAILS[n]['slots_forbidden'][spec]})"
        assert not result.ok
    # The confirmed Nordlicht interview (22.10.) never blocks an offered slot.
    interview_start, interview_end = gold_slot("2026-10-22T10:00/11:00")
    assert not any(b.start < interview_end and interview_start < b.end for b in busy_exact)


# sorted(ranked) == sorted(gold) is split into: nothing invented, nothing
# missing, no duplicates (together exactly the original multiset equality).
def _mail3_ranked(world) -> list[str]:
    return [slot_spec(s.start, s.end) for s in product_proposal(world, 3).ranked_slots]


@_xf("test_mail3_ranked_slots_none_invented", 3, "slots_allowed",
     "ranks never-offered 21.10./23.10./30.10. and 28.10. 10:00 (weekday-window parse)", 4)
def test_mail3_ranked_slots_none_invented(world):
    got = _mail3_ranked(world)
    invented = sorted(set(got) - set(GOLD_MAILS[3]["slots_allowed"]))
    assert invented == [], f"product ranked {got}; not in gold slots_allowed: {invented}"


@_xf("test_mail3_ranked_slots_none_missing", 3, "slots_allowed", "gold slot 28.10. 14:00-15:00 missing", 4)
def test_mail3_ranked_slots_none_missing(world):
    got = _mail3_ranked(world)
    missing = sorted(set(GOLD_MAILS[3]["slots_allowed"]) - set(got))
    assert missing == [], f"product ranked {got}; gold slots missing: {missing}"


def test_mail3_ranked_slots_no_duplicates(world):
    got = _mail3_ranked(world)
    assert len(got) == len(set(got)), got


def test_mail3_has_ranked_slots(world):
    proposal = product_proposal(world, 3)
    assert proposal.ranked_slots, proposal.stop_reason


@_xf("test_mail3_rank1_is_gold_rank1", 3, "slot_rank_1", "rank 1 is 21.10. 10:00 instead of 27.10. 10:00", 4)
def test_mail3_rank1_is_gold_rank1(world):
    ranked = product_proposal(world, 3).ranked_slots
    top = slot_spec(ranked[0].start, ranked[0].end) if ranked else None
    assert top == GOLD_MAILS[3]["slot_rank_1"]


def test_mail4_all_offered_slots_blocked_no_acceptance_no_ics(world):
    from integrations.calendar_write import draft_from_ranked_slot

    assert GOLD_MAILS[4]["slots_allowed"] == [] and GOLD_MAILS[4]["ics"] is None
    proposal = product_proposal(world, 4)
    assert proposal.ranked_slots == [], [slot_spec(s.start, s.end) for s in proposal.ranked_slots]
    with pytest.raises(ValueError, match="no_slot_selected"):
        draft_from_ranked_slot(proposal, slot_index=0)
    draft, _ = product_draft(world, 4)
    assert draft is None or not accepts_offered_slot(4, draft_text(draft))


# --------------------------------------------------------------------- ICS --


@pytest.fixture
def mail3_ics(world, tmp_path):
    from integrations.calendar_write import CalendarWriteGate, draft_to_ics, export_approved_ics

    gold = GOLD_MAILS[3]
    draft, specs = ics_draft_for_slot(world, 3, gold["slot_rank_1"])
    if draft is None:
        pytest.fail(f"gold slot {gold['slot_rank_1']} not offered by product; ranked {specs}")
    with pytest.raises(PermissionError):
        export_approved_ics(draft, tmp_path / "unapproved.ics")
    assert not (tmp_path / "unapproved.ics").exists()
    CalendarWriteGate().approve(draft)
    path = export_approved_ics(draft, tmp_path / "out" / "mail3.ics")
    return NS(draft=draft, text=path.read_text(encoding="utf-8"), draft_to_ics=draft_to_ics)


@_xf("test_mail3_ics_dtstart_tzid_form_per_gold", 3, "ics.dtstart",
     "DTSTART:20261027T090000Z (UTC Z) instead of DTSTART;TZID=Europe/Berlin:20261027T100000", 5)
def test_mail3_ics_dtstart_tzid_form_per_gold(mail3_ics):
    assert ics_lines(mail3_ics.text, "DTSTART") == [f"DTSTART;{GOLD_MAILS[3]['ics']['dtstart']}"]


@_xf("test_mail3_ics_dtend_tzid_form_per_gold", 3, "ics.dtend", "DTEND in UTC Z form, no TZID=Europe/Berlin", 5)
def test_mail3_ics_dtend_tzid_form_per_gold(mail3_ics):
    assert ics_lines(mail3_ics.text, "DTEND") == [f"DTEND;{GOLD_MAILS[3]['ics']['dtend']}"]


def test_mail3_ics_instant_is_0900_utc(mail3_ics):
    from icalendar import Calendar

    event = next(iter(Calendar.from_ical(mail3_ics.text).walk("VEVENT")))
    start = event.decoded("DTSTART")
    assert start.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ") == GOLD_MAILS[3]["ics"]["dtstart_utc"]
    assert event.decoded("DTEND") - start == timedelta(hours=1)


@_xf("test_mail3_ics_location_exact", 3, "ics.location", "no LOCATION in the product ICS", 5)
def test_mail3_ics_location_exact(mail3_ics):
    from icalendar import Calendar

    event = next(iter(Calendar.from_ical(mail3_ics.text).walk("VEVENT")))
    assert str(event.get("LOCATION", "")) == GOLD_MAILS[3]["ics"]["location"]


def test_mail3_ics_summary_contains_company_and_position(mail3_ics):
    from icalendar import Calendar

    event = next(iter(Calendar.from_ical(mail3_ics.text).walk("VEVENT")))
    summary = str(event.get("SUMMARY", ""))
    for part in GOLD_MAILS[3]["ics"]["summary_contains"]:
        assert part in summary, (part, summary)


def test_mail3_ics_no_invented_attendees(mail3_ics):
    allowed = set(GOLD_MAILS[3]["ics"]["allowed_addresses"])
    addresses = set(re.findall(r"[\w.+-]+@[\w.-]+\.\w+", mail3_ics.text))
    uid = mail3_ics.draft.uid
    assert addresses - {uid} <= allowed, addresses
    assert not ics_lines(mail3_ics.text, "ATTENDEE") or all(
        any(a in ln for a in allowed) for ln in ics_lines(mail3_ics.text, "ATTENDEE")
    )
    assert not any(ics_lines(mail3_ics.text, k) for k in ("ORGANIZER",)) or all(
        any(a in ln for a in allowed) for ln in ics_lines(mail3_ics.text, "ORGANIZER")
    )


def test_mail3_ics_uid_stable_and_rerun_creates_no_duplicate(world, mail3_ics):
    from integrations.calendar_write import CalendarWriteGate, InMemoryCalendarTransport

    gold = GOLD_MAILS[3]
    assert gold["ics"]["uid_stable_on_rerun"] is True
    rerun_dir = world.tmp / "rerun"
    rerun_dir.mkdir()
    rerun_world = build_world(rerun_dir)
    again, _ = ics_draft_for_slot(rerun_world, 3, gold["slot_rank_1"])
    assert again.uid == mail3_ics.draft.uid
    assert ics_lines(mail3_ics.draft_to_ics(again), "UID") == ics_lines(mail3_ics.text, "UID")
    # Even with writes explicitly enabled (test only) the same request is created once.
    transport = InMemoryCalendarTransport()
    gate = CalendarWriteGate(allow_write=True)
    for d in (mail3_ics.draft, again):
        gate.approve(d)
        gate.attempt_create(d, transport=transport)
    assert len(transport.events) == 1 and transport.create_calls == 1


def test_ics_not_written_without_approval(world):
    from integrations.calendar_write import CalendarWriteGate, InMemoryCalendarTransport, draft_from_ranked_slot

    assert GOLD_MAILS[3]["ics"]["written_without_approval"] is False
    draft, _ = ics_draft_for_slot(world, 3, GOLD_MAILS[3]["slot_rank_1"])
    if draft is None:
        draft = draft_from_ranked_slot(product_proposal(world, 3), slot_index=0)
    transport = InMemoryCalendarTransport()
    unapproved = CalendarWriteGate(allow_write=True).attempt_create(draft, transport=transport)
    assert unapproved.created is False and unapproved.create_error == "not_approved"
    assert transport.create_calls == 0 and transport.events == {}


def test_calendar_write_gate_default_write_disabled(world):
    from integrations.calendar_write import CalendarWriteGate, InMemoryCalendarTransport, draft_from_ranked_slot

    assert GOLD["defaults"]["calendar_write_allowed"] is False
    proposal = product_proposal(world, 3)
    assert proposal.ranked_slots
    draft = draft_from_ranked_slot(proposal, slot_index=0)
    gate = CalendarWriteGate()
    assert gate.allow_write is False
    gate.approve(draft)
    transport = InMemoryCalendarTransport()
    result = gate.attempt_create(draft, transport=transport)
    assert result.created is False and result.create_error.startswith("write_disabled")
    assert transport.create_calls == 0
    assert CalendarWriteGate.may_mark_scheduled(result) is False


# ------------------------------------------------- mail 9 / 22.10 interview --

NORDLICHT_UID = "t0110-interview-nordlicht-nl-2026-0412@nordlicht-logistik.example.org"


def check_cancellation_proposal(ics_text: str | None) -> list[str]:
    """Gold calendar_after_import: STATUS:CANCELLED, same UID, SEQUENCE > 0."""
    if not ics_text:
        return ["no cancellation proposal produced"]
    out = []
    if ics_lines(ics_text, "UID") != [f"UID:{NORDLICHT_UID}"]:
        out.append(f"UID {ics_lines(ics_text, 'UID')}")
    if ics_lines(ics_text, "STATUS") != ["STATUS:CANCELLED"]:
        out.append(f"STATUS {ics_lines(ics_text, 'STATUS')}")
    seq = [int(ln.split(":", 1)[1]) for ln in ics_lines(ics_text, "SEQUENCE")]
    if not seq or seq[0] <= 0:
        out.append(f"SEQUENCE {seq} not > 0")
    return out


def product_cancellation_drafts(w: World, n: int) -> list:
    """Product path: only a mail classified interview_cancelled yields proposals,
    computed against the local calendar snapshot at the frozen now."""
    from integrations.calendar_write import propose_cancellation_update

    row = w.rows[n]
    if (row.get("category") or "") != "interview_cancelled":
        return []
    text = f"{row.get('subject') or ''}\n{row.get('body_text') or ''}"
    return propose_cancellation_update(w.snapshot.read_bytes(), text, now=datetime.now(TZ))


def product_cancellation_proposal(w: World, n: int) -> str | None:
    """ICS text of the proposed CANCELLED update(s) for mail n (not written), or None."""
    from integrations.calendar_write import cancellation_to_ics

    drafts = product_cancellation_drafts(w, n)
    return cancellation_to_ics(drafts) if drafts else None


def test_mail9_interview_not_recreated_or_rescheduled(world):
    gold = GOLD["calendar_after_import"][NORDLICHT_UID]
    assert gold["recreated_or_duplicated"] is False and gold["new_uid"] is False
    assert GOLD_MAILS[9]["ics"]["new_event"] is False
    proposal = product_proposal(world, 9)
    offered = [slot_spec(s.start, s.end) for s in proposal.ranked_slots]
    assert offered == [], f"product offers new interview slots for a cancellation mail: {offered}"


# check_cancellation_proposal (produced, UID, STATUS, SEQUENCE) is split:
# exactly one CANCELLED update (produced + STATUS), same UID, higher SEQUENCE.
_NO_CANCEL = "no generator for a CANCELLED update (calendar_write/ics_export lack STATUS/SEQUENCE)"
_CANCEL_FIELD = "calendar_after_import.proposed_change"


def _cancelled_vevents(ics_text: str | None) -> list[Any]:
    from icalendar import Calendar

    if not ics_text:
        return []
    events = Calendar.from_ical(ics_text).walk("VEVENT")
    return [e for e in events if str(e.get("STATUS", "")).upper() == "CANCELLED"]


def _original_sequence() -> int:
    from icalendar import Calendar

    cal = Calendar.from_ical((FIXTURE_DIR / "calendar.ics").read_bytes())
    return next(int(e.get("SEQUENCE", 0)) for e in cal.walk("VEVENT") if str(e.get("UID")) == NORDLICHT_UID)


def test_mail9_gold_requires_cancelled_update_same_uid_higher_sequence():
    assert GOLD["calendar_after_import"][NORDLICHT_UID]["proposed_change"].startswith("STATUS:CANCELLED")
    assert GOLD_MAILS[9]["ics"]["cancels_uid"] == NORDLICHT_UID


def test_mail9_exactly_one_cancelled_update(world):
    cancelled = _cancelled_vevents(product_cancellation_proposal(world, 9))
    assert len(cancelled) == 1, f"{len(cancelled)} CANCELLED VEVENTs"


def test_mail9_cancelled_update_same_uid(world):
    uids = [str(e.get("UID")) for e in _cancelled_vevents(product_cancellation_proposal(world, 9))]
    assert uids == [NORDLICHT_UID], uids


def test_mail9_cancelled_update_higher_sequence(world):
    seqs = [int(e.get("SEQUENCE", -1)) for e in _cancelled_vevents(product_cancellation_proposal(world, 9))]
    assert seqs and all(seq > _original_sequence() for seq in seqs), seqs


def test_mail9_cancellation_not_written_or_exported_without_approval(world, tmp_path):
    from integrations.calendar_write import export_approved_cancellation_ics

    before = hashlib.sha256(world.snapshot.read_bytes()).hexdigest()
    drafts = product_cancellation_drafts(world, 9)
    assert len(drafts) == 1 and drafts[0].approved is False
    target = tmp_path / "m9_cancel.ics"
    with pytest.raises(PermissionError):
        export_approved_cancellation_ics(drafts[0], target)
    assert not target.exists()
    assert hashlib.sha256(world.snapshot.read_bytes()).hexdigest() == before
    assert not list(world.tmp.rglob("*.ics.tmp"))


def test_mail9_cancellation_exported_only_after_approval(world, tmp_path):
    from integrations.calendar_write import CalendarWriteGate, export_approved_cancellation_ics

    before = hashlib.sha256(world.snapshot.read_bytes()).hexdigest()
    draft = product_cancellation_drafts(world, 9)[0]
    CalendarWriteGate().approve(draft)
    path = export_approved_cancellation_ics(draft, tmp_path / "out" / "m9_cancel.ics")
    events = _cancelled_vevents(path.read_text(encoding="utf-8"))
    assert [str(e.get("UID")) for e in events] == [NORDLICHT_UID]
    assert ics_lines(path.read_text(encoding="utf-8"), "DTSTART") == ["DTSTART;TZID=Europe/Berlin:20261022T100000"]
    assert not ics_lines(path.read_text(encoding="utf-8"), "ATTENDEE")
    assert hashlib.sha256(world.snapshot.read_bytes()).hexdigest() == before  # export != calendar write


@pytest.mark.parametrize("n", [n for n in sorted(GOLD_MAILS) if n != 9])
def test_no_cancellation_proposal_for_other_mails(world, n):
    assert product_cancellation_proposal(world, n) is None


def test_cancellation_proposal_needs_exactly_one_matching_future_event():
    from integrations.calendar_write import propose_cancellation_update

    ics = (FIXTURE_DIR / "calendar.ics").read_bytes()
    now = datetime(2026, 10, 18, 9, 0, tzinfo=TZ)
    assert propose_cancellation_update(ics, "Termin am 24.10.2026 entfällt", now=now) == []  # no event then
    assert propose_cancellation_update(ics, "Termin am 22.10.2026 um 15:00 entfällt", now=now) == []  # wrong time
    assert propose_cancellation_update(ics, "Termin entfällt", now=now) == []  # no date
    later = datetime(2026, 10, 23, 9, 0, tzinfo=TZ)
    assert propose_cancellation_update(ics, "Termin am 22.10.2026 entfällt", now=later) == []  # in the past
    got = propose_cancellation_update(ics, "Termin am 22.10.2026 entfällt", now=now)
    assert [(d.uid, d.original_sequence, d.sequence) for d in got] == [(NORDLICHT_UID, 0, 1)]


def _calendar_with_nordlicht_sequence(seq: int | None) -> bytes:
    """In-memory copy of the fixture calendar (file untouched) with the Nordlicht
    event's SEQUENCE set to seq (None = property removed)."""
    text = (FIXTURE_DIR / "calendar.ics").read_text(encoding="utf-8")
    head, sep, rest = text.partition(f"UID:{NORDLICHT_UID}")
    block, end, tail = rest.partition("END:VEVENT")
    assert sep and end and "SEQUENCE:0" in block
    new = f"SEQUENCE:{seq}" if seq is not None else ""
    block = block.replace("SEQUENCE:0\r\n" if "SEQUENCE:0\r\n" in block else "SEQUENCE:0\n",
                          (new + ("\r\n" if "\r\n" in block else "\n")) if new else "", 1)
    return (head + sep + block + end + tail).encode("utf-8")


@pytest.mark.parametrize("original,expected", [(None, 1), (0, 1), (1, 2), (5, 6)], ids=["missing", "0", "1", "5"])
def test_cancellation_sequence_is_original_plus_one(original, expected):
    from integrations.calendar_write import cancellation_to_ics, propose_cancellation_update

    ics = _calendar_with_nordlicht_sequence(original)
    now = datetime(2026, 10, 18, 9, 0, tzinfo=TZ)
    drafts = propose_cancellation_update(ics, "Termin am 22.10.2026 um 10:00 entfällt", now=now)
    assert [(d.original_sequence, d.sequence) for d in drafts] == [(original or 0, expected)]
    assert ics_lines(cancellation_to_ics(drafts), "SEQUENCE") == [f"SEQUENCE:{expected}"]


def test_mail9_nothing_written_without_approval(world):
    from integrations.calendar.session import CalendarSession
    from integrations.providers.enums import ProviderError

    assert GOLD_MAILS[9]["ics"]["written_without_approval"] is False
    before = hashlib.sha256(world.snapshot.read_bytes()).hexdigest()
    product_proposal(world, 9)
    product_draft(world, 9)
    session = CalendarSession(world.settings, token_dir=world.tmp)
    with pytest.raises(ProviderError):
        session.create_event(NS(approved=False, start="", end=""))
    assert hashlib.sha256(world.snapshot.read_bytes()).hexdigest() == before
    assert (FIXTURE_DIR / "calendar.ics").read_bytes() == world.snapshot.read_bytes()
    assert not list(world.tmp.rglob("*.ics.tmp"))


# ------------------------------------------------------------------ drafts --

_NO_DRAFT = [n for n, m in sorted(GOLD_MAILS.items()) if m["draft_allowed"] is False]
_DRAFT = [n for n, m in sorted(GOLD_MAILS.items()) if m["draft_allowed"] is True]
_SALUTATION = [n for n in _DRAFT if "salutation" in GOLD_MAILS[n]]
_MUST_CONTAIN = [(n, s) for n in _DRAFT for s in GOLD_MAILS[n].get("must_contain", [])]
_MUST_NOT = [(n, s) for n in _DRAFT for s in GOLD_MAILS[n].get("must_not", [])]


@pytest.mark.parametrize("n", _NO_DRAFT)
def test_no_draft_offered_when_gold_forbids(world, n):
    draft, how = product_draft(world, n)
    assert draft is None, f"mail {n}: product offers {how} draft, gold draft_allowed=false"


# test_draft_offered_with_gold_draft_type (draft exists + all draft_type checks)
# is split into one existence test and one test per draft_type item. Content
# tests on a mail without a product draft fail on that single deviation.
# M9 has a product draft (GENERAL_REPLY) since the point 3 classifier fix.
_NO_DRAFT_REASON = {4: "no product draft (no_slots:fail_safe:no_candidates)"}
_DRAFT_TYPE_ITEMS = [(n, name) for n in _DRAFT for name, _ in DRAFT_TYPE_CHECKS[GOLD_MAILS[n]["draft_type"]]]
_DRAFT_TYPE_ITEM_XF = {
    (3, "exactly_one_slot"): "proposes three dates (21.10./23.10./27.10.) instead of accepting exactly one",
    (3, "acceptance_wording"): "proposes slots, no acceptance wording",
}


def _draft_item_xf(test: str, n: int, gold_field: str, key=None, *, content: bool = True):
    """content=True: draft-content test -> raises=MissingDraft when there is no draft."""
    if n in _NO_DRAFT_REASON:
        if content:
            return _xf(test, n, gold_field, "no product draft (point 8)", 8, raises=MissingDraft)
        return _xf(test, n, gold_field, _NO_DRAFT_REASON[n], 8)
    if key in _DRAFT_TYPE_ITEM_XF:
        return _xf(test, n, gold_field, _DRAFT_TYPE_ITEM_XF[key], 8)
    return None


@pytest.mark.parametrize(
    "n",
    [_p(n, xf=_draft_item_xf(f"test_draft_offered_when_gold_allows[{n}]", n, "draft_allowed", content=False),
        id=str(n))
     for n in _DRAFT],
)
def test_draft_offered_when_gold_allows(world, n):
    draft, how = product_draft(world, n)
    assert draft is not None, f"mail {n}: no product draft ({how})"


def check_draft_type_item(n: int, item: str, draft, how: str = "") -> None:
    draft = require_draft(n, draft, how)
    fn = dict(DRAFT_TYPE_CHECKS[GOLD_MAILS[n]["draft_type"]])[item]
    problem = fn(n, draft)
    assert problem is None, f"mail {n} {GOLD_MAILS[n]['draft_type']}.{item}: {problem}"


@pytest.mark.parametrize(
    "n,item",
    [_p(n, name, id=f"{n}-{name}",
        xf=_draft_item_xf(f"test_draft_type_item[{n}-{name}]", n, f"draft_type.{name}", (n, name)))
     for n, name in _DRAFT_TYPE_ITEMS],
)
def test_draft_type_item(world, n, item):
    draft, how = product_draft(world, n)
    check_draft_type_item(n, item, draft, how)


def _salutation_xf(n):
    # M5/M9 markers removed with the point 7 greeting fix (integrations/reply_draft.py).
    if n in _NO_DRAFT_REASON:
        return _draft_item_xf(f"test_draft_salutation_exact[{n}]", n, "salutation")
    return None


def check_salutation(n: int, draft, how: str = "") -> None:
    draft = require_draft(n, draft, how)
    assert salutation(draft.body) == GOLD_MAILS[n]["salutation"]


@pytest.mark.parametrize("n", [_p(n, xf=_salutation_xf(n), id=str(n)) for n in _SALUTATION])
def test_draft_salutation_exact(world, n):
    draft, how = product_draft(world, n)
    check_salutation(n, draft, how)


def _greeting_for(contact_name: str) -> str:
    from integrations.reply_draft import ReplyAction, build_action_draft

    case = {"id": "case-synthetic", "company": "Beispiel GmbH", "position": "Sachbearbeitung",
            "contact_name": contact_name}
    return salutation(build_action_draft(ReplyAction.GENERAL_REPLY, case, applicant_name=APPLICANT).body)


@pytest.mark.parametrize("n", _SALUTATION)
def test_greeting_rule_matches_every_gold_salutation(n):
    """Point 7: the greeting for the case contact (as written) equals every gold
    salutation, including M4, whose product path has no draft (point 8)."""
    case = CASES_BY_ID[GOLD_MAILS[n]["case_id"]]
    assert _greeting_for(case["contact_person_as_written"]) == GOLD_MAILS[n]["salutation"]


@pytest.mark.parametrize(
    "contact_name,expected",
    [
        ("Herr Jonas Feldmann", "Sehr geehrter Herr Feldmann,"),
        ("Frau Lena Hoffmann-Stein", "Sehr geehrte Frau Hoffmann-Stein,"),
        ("Herr Paul Ritter-Brandt", "Sehr geehrter Herr Ritter-Brandt,"),
        ("Frau Dr. Lena Hoffmann", "Sehr geehrte Frau Dr. Hoffmann,"),
        ("Herr Prof. Dr. Paul Ritter", "Sehr geehrter Herr Prof. Dr. Ritter,"),
        ("Frau Lena von der Aue", "Sehr geehrte Frau von der Aue,"),
        ("Frau Hoffmann", "Sehr geehrte Frau Hoffmann,"),
        ("Hr. Paul Ritter", "Sehr geehrter Herr Ritter,"),
        # unknown form of address -> gold fallback 'Guten Tag <wie geschrieben>,'
        ("Alex Hoffmann", "Guten Tag Alex Hoffmann,"),
        ("Dr. Alex Hoffmann", "Guten Tag Dr. Alex Hoffmann,"),
        ("Lena Hoffmann", "Guten Tag Lena Hoffmann,"),  # no gender inferred from a first name
        ("", "Guten Tag,"),
        ("Frau", "Guten Tag,"),
    ],
    ids=lambda v: v or "empty",
)
def test_greeting_rule_synthetic_counter_cases(contact_name, expected):
    got = _greeting_for(contact_name)
    assert got == expected
    names = [t for t in contact_name.split() if t.rstrip(".") not in {"Frau", "Herr", "Hr", "Dr", "Prof"}]
    if got.startswith("Sehr geehrte") and len(names) > 1:
        assert names[0] not in got.split(), f"first name {names[0]!r} in a formal salutation: {got!r}"


def _must_contain_xf(n, needle):
    test = f"test_draft_must_contain[mail{n}-{needle}]"
    if n in _NO_DRAFT_REASON:
        return _draft_item_xf(test, n, "must_contain")
    if needle == "BW-DA-7731":
        return _xf(test, n, "must_contain", "reference number BW-DA-7731 never in the draft", 8)
    return None


def check_must_contain(n: int, needle: str, draft, how: str = "") -> None:
    draft = require_draft(n, draft, how)
    assert needle in draft_text(draft), draft.body


@pytest.mark.parametrize(
    "n,needle", [_p(n, s, id=f"mail{n}-{s}", xf=_must_contain_xf(n, s)) for n, s in _MUST_CONTAIN]
)
def test_draft_must_contain(world, n, needle):
    draft, how = product_draft(world, n)
    check_must_contain(n, needle, draft, how)


def test_missing_draft_helper_distinguishes_missing_from_wrong_content():
    """No draft -> MissingDraft; a wrong draft -> plain AssertionError (not MissingDraft),
    so the raises=MissingDraft markers of M4/M9 turn red once a wrong draft appears."""
    wrong = NS(subject="Re: Termin", body="Hallo zusammen,\n\nText ohne Kennziffer.\n")
    for n in (4, 9):
        with pytest.raises(MissingDraft):
            check_salutation(n, None, "test")
        with pytest.raises(AssertionError) as exc:
            check_salutation(n, wrong, "test")
        assert type(exc.value) is AssertionError
    with pytest.raises(MissingDraft):
        check_must_contain(4, "TM/26/118", None)
    with pytest.raises(AssertionError) as exc:
        check_must_contain(4, "TM/26/118", wrong)
    assert type(exc.value) is AssertionError
    with pytest.raises(MissingDraft):
        check_draft_type_item(4, "alternative_request", None)
    with pytest.raises(AssertionError) as exc:
        check_draft_type_item(4, "alternative_request", wrong)
    assert type(exc.value) is AssertionError
    proposing = NS(subject="Re", body="Guten Tag,\n\nich schlage den 30.10.2026 um 10:00 Uhr vor.\n")
    with pytest.raises(AssertionError) as exc:
        check_draft_type_item(9, "no_own_dates", proposing)
    assert type(exc.value) is AssertionError


@pytest.mark.parametrize("n,label", _MUST_NOT, ids=[f"mail{n}-{s}" for n, s in _MUST_NOT])
def test_draft_must_not(world, n, label):
    assert label in MUST_NOT, f"no checker for gold must_not {label!r}"
    draft, how = product_draft(world, n)
    if draft is None:
        return  # nothing produced -> nothing forbidden produced (see draft_type test)
    assert not MUST_NOT[label](n, draft_text(draft), draft_attachments(draft)), draft.body


@pytest.mark.parametrize("n", sorted(GOLD_MAILS))
def test_forbidden_in_any_draft(world, n):
    assert set(FORBIDDEN_IN_ANY_DRAFT) == set(GOLD["forbidden_in_any_draft"])
    draft, _ = product_draft(world, n)
    if draft is None:
        return
    hits = [k for k, fn in FORBIDDEN_IN_ANY_DRAFT.items() if fn(draft_text(draft), draft_attachments(draft))]
    assert hits == [], draft.body


def test_forbidden_checkers_are_red_on_violation():
    """The text checkers themselves fire on deliberately bad drafts."""
    bad = {
        "Lindenhof": "Am 02.11. habe ich ein Gespräch bei Lindenhof Consulting.",
        "Gehaltsvorstellung": "Meine Gehaltsvorstellung liegt bei 50.000 EUR brutto.",
        "Eintrittstermin": "Mein frühestmöglicher Eintrittstermin ist der 01.01.2027.",
        "Kündigungsfrist": "Meine Kündigungsfrist beträgt drei Monate.",
        "SQL-Zertifikat als vorhanden oder als Anhang": "Anbei mein SQL-Zertifikat.",
        "geschlechtsspezifische Selbstbeschreibung (Profil ohne Geschlecht)": "Als Bewerberin freue ich mich.",
    }
    for label, text in bad.items():
        assert FORBIDDEN_IN_ANY_DRAFT[label](text, []), label
    assert not sql_certificate_presented("Ein SQL-Zertifikat habe ich nicht; ich habe SQL-Grundkenntnisse.", [])
    assert sql_certificate_presented("Unterlagen anbei.", ["SQL_Zertifikat.pdf"])
    assert accepts_offered_slot(4, "Der Termin am 03.11.2026 um 10:00 Uhr passt mir gut.")
    assert proposes_own_dates("Wie wäre es am 29.10.2026 um 10:00 Uhr?")


@pytest.mark.parametrize("n", sorted(GOLD_MAILS))
def test_attachments_only_from_documents_json_never_sql_certificate(world, n):
    assert GOLD["attachments_allowed_only_from"] == "documents.json"
    assert PROFILE["certificates"] == [] and not any("zertifi" in d.lower() for d in DOCUMENT_NAMES)
    draft, _ = product_draft(world, n)
    if draft is None:
        return
    attachments = draft_attachments(draft)
    assert set(attachments) <= DOCUMENT_NAMES
    assert set(attachments) <= set(GOLD_MAILS[n].get("attachments_allowed", DOCUMENT_NAMES))
    assert not sql_certificate_presented(draft_text(draft), attachments)


class RecordingTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, draft):
        self.calls.append(draft)


def test_send_gate_default_never_sends(world):
    from integrations.reply_draft import SendGate

    assert GOLD["defaults"]["send_allowed"] is False
    transport = RecordingTransport()
    produced = 0
    for n in sorted(GOLD_MAILS):
        draft, _ = product_draft(world, n)
        if draft is None:
            continue
        produced += 1
        assert draft.auto_send is False and draft.sent is False and draft.draft_only is True
        gate = SendGate()
        assert gate.allow_send is False
        result = gate.attempt_send(draft, transport=transport)
        assert result.sent is False
        gate.approve(draft)
        result = gate.attempt_send(draft, transport=transport)
        assert result.sent is False and result.send_error
    assert produced > 0
    assert transport.calls == []


# ---------------------------------------------------------------- evidence --


def run_full_offline_flow(tmp: Path, monkeypatch) -> dict:
    """Every T01.10 product path once; returns counters (used by the guard test)."""
    from integrations.calendar_write import CalendarWriteGate, InMemoryCalendarTransport, export_approved_ics
    from integrations.reply_draft import SendGate

    import_dir = tmp / "import"
    import_dir.mkdir()
    w = build_world(import_dir)
    imap_dir = tmp / "imap"
    imap_dir.mkdir()
    imap_sync(seed_db(imap_dir), imap_dir, w.settings, monkeypatch)
    send = RecordingTransport()
    cal = InMemoryCalendarTransport()
    for n in sorted(GOLD_MAILS):
        draft, _ = product_draft(w, n)
        if draft is not None:
            SendGate().attempt_send(SendGate().approve(draft), transport=send)
    for n in (3, 4, 9):
        product_proposal(w, n)
    ics_draft, _ = ics_draft_for_slot(w, 3, GOLD_MAILS[3]["slot_rank_1"])
    if ics_draft is not None:
        gate = CalendarWriteGate()
        gate.approve(ics_draft)
        gate.attempt_create(ics_draft, transport=cal)
        export_approved_ics(ics_draft, tmp / "out" / "mail3.ics")
    return {
        "imap_stand_in_hosts": sorted({i.host for i in ImapStandIn.instances}),
        "imap_stand_in_sessions": len(ImapStandIn.instances),
        "send_transport_calls": len(send.calls),
        "calendar_transport_calls": cal.create_calls,
    }


REPO_ROOT = Path(__file__).resolve().parents[1]


def _evidence_dir(tmp_path_factory) -> Path:
    """Evidence goes to KK_T0110_EVIDENCE_DIR or a pytest tmp dir, never into the repo.

    A value that resolves inside the repo root is refused: a warning is
    emitted and the tmp default is used, so evidence is never committed by
    accident.
    """
    env = os.environ.get("KK_T0110_EVIDENCE_DIR")
    if env:
        path = Path(env).expanduser().resolve()
        if path == REPO_ROOT or REPO_ROOT in path.parents:
            warnings.warn(
                f"KK_T0110_EVIDENCE_DIR={env!r} resolves inside the repository ({REPO_ROOT}); "
                "refused, writing T01.10 evidence to a pytest tmp dir instead",
                UserWarning,
                stacklevel=2,
            )
        else:
            path.mkdir(parents=True, exist_ok=True)
            return path
    return tmp_path_factory.mktemp("t0110_evidence")


@pytest.mark.parametrize(
    "inside",
    [".", "tests/fixtures/t0110_synthetic_account/evidence", "docs/../t0110_evidence_in_repo"],
)
def test_evidence_dir_inside_repo_is_refused(monkeypatch, tmp_path_factory, inside):
    target = REPO_ROOT / inside
    existed = target.exists()
    monkeypatch.setenv("KK_T0110_EVIDENCE_DIR", str(target))
    with pytest.warns(UserWarning, match="inside the repository"):
        out = _evidence_dir(tmp_path_factory)
    assert REPO_ROOT not in out.resolve().parents and out.resolve() != REPO_ROOT
    assert target.exists() is existed  # nothing created inside the repo


def test_evidence_dir_outside_repo_is_used(monkeypatch, tmp_path, tmp_path_factory):
    target = tmp_path / "evidence"
    monkeypatch.setenv("KK_T0110_EVIDENCE_DIR", str(target))
    assert _evidence_dir(tmp_path_factory) == target.resolve()
    assert target.is_dir()


def test_write_evidence_for_personaler(world, tmp_path, tmp_path_factory):
    """Writes t0110_evidence.json/.md (mail -> category -> case -> draft -> ICS). Not committed."""
    from integrations.calendar_write import CalendarWriteGate, export_approved_ics

    out_dir = _evidence_dir(tmp_path_factory)
    mails = []
    for n, message in enumerate(mbox_messages(), start=1):
        gold = GOLD_MAILS[n]
        row = world.rows[n]
        draft, how = product_draft(world, n)
        entry = {
            "n": n,
            "message_id": message["Message-ID"],
            "gold": gold,
            "product": {
                "category": row["category"],
                "confidence": row.get("confidence"),
                "case_id": row.get("case_id") or None,
                "association_status": row["association_status"],
                "association_explanation": row.get("association_explanation"),
            },
            "draft": None
            if draft is None
            else {
                "how": how,
                "subject": draft.subject,
                "body": draft.body,
                "to": draft.to_address,
                "attachments": draft_attachments(draft),
                "blocking_reasons": draft.blocking_reasons,
                "salutation": salutation(draft.body),
                "forbidden_hits": [k for k, fn in FORBIDDEN_IN_ANY_DRAFT.items() if fn(draft_text(draft), [])],
                "must_not_hits": [
                    lbl
                    for lbl in gold.get("must_not", [])
                    if lbl in MUST_NOT and MUST_NOT[lbl](n, draft_text(draft), [])
                ],
                "draft_type_violations": draft_type_violations(n, draft) if gold["draft_allowed"] else [],
            },
            "draft_reason_if_none": how if draft is None else "",
            "ics": None,
        }
        if (row.get("category") or "") in INTERVIEW_LIKE:
            proposal = product_proposal(world, n)
            entry["product"]["ranked_slots"] = [slot_spec(s.start, s.end) for s in proposal.ranked_slots]
            entry["product"]["stop_reason"] = proposal.stop_reason
        if n == 3:
            ics_draft, specs = ics_draft_for_slot(world, 3, gold["slot_rank_1"])
            if ics_draft is not None:
                CalendarWriteGate().approve(ics_draft)
                entry["ics"] = export_approved_ics(ics_draft, tmp_path / "mail3.ics").read_text(encoding="utf-8")
        if n == 9:
            entry["ics"] = product_cancellation_proposal(world, 9)
            entry["ics_check"] = check_cancellation_proposal(entry["ics"])
        mails.append(entry)
    statuses = {c["case_id"]: world.db.get_case(c["case_id"]).status for c in CASES}
    evidence = {
        "reference_now": REFERENCE_NOW,
        "gold_sha256": hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest(),
        "import_counts": list(world.import_counts),
        "reimport_counts": list(world.reimport_counts),
        "case_status_after_import": statuses,
        "mails": mails,
        "unsicher": UNSICHER_ITEMS,
    }
    (out_dir / "t0110_evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    md = [
        "# T01.10 evidence (synthetic account, offline, frozen now)",
        "",
        f"reference_now: {REFERENCE_NOW}  ",
        f"gold sha256: {evidence['gold_sha256']}  ",
        f"import: {world.import_counts}, re-import: {world.reimport_counts}  ",
        f"case status after import: {statuses}",
        "",
    ]
    for e in mails:
        g, p = e["gold"], e["product"]
        md += [
            f"## Mail {e['n']} {e['message_id']}",
            "",
            f"- category: gold `{g['category']}` / product `{p['category']}` (conf {p['confidence']})",
            f"- case: gold `{g['case_id']}` / product `{p['case_id']}` "
            f"({p['association_status']}: {p['association_explanation']})",
            f"- draft_allowed: gold `{g['draft_allowed']}` / product draft: "
            f"`{e['draft']['how'] if e['draft'] else 'none (' + e['draft_reason_if_none'] + ')'}`",
        ]
        if "ranked_slots" in p:
            md.append(
                f"- slots: gold allowed {g.get('slots_allowed')} / "
                f"product ranked {p['ranked_slots']} {p['stop_reason']}"
            )
        if e["draft"]:
            d = e["draft"]
            md += [
                f"- salutation: gold `{g.get('salutation')}` / product `{d['salutation']}`",
                f"- forbidden hits: {d['forbidden_hits']}; must_not hits: {d['must_not_hits']}; "
                f"draft_type violations: {d['draft_type_violations']}",
                "",
                "```text",
                f"Subject: {d['subject']}",
                "",
                d["body"].rstrip(),
                "```",
            ]
        if e["ics"]:
            md += ["", "```text", e["ics"].rstrip(), "```"]
        if "ics_check" in e:
            md.append(f"- cancellation proposal check: {e['ics_check']}")
        md.append("")
    md += ["## UNSICHER / nicht offline prüfbar", ""] + [f"- {u}" for u in UNSICHER_ITEMS]
    (out_dir / "t0110_evidence.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    assert (out_dir / "t0110_evidence.json").is_file() and (out_dir / "t0110_evidence.md").is_file()


# --------------------------------------------- gold addendum 1 (M5 / M6) --
# expected_addendum_1.json (Personaler, commit after 762f3d5) only adds rules.
# Items the product fails today are strict xfails (raises=AssertionError), so
# a product fix turns them XPASS -> red until the marker is removed.
# The text checks are keyword/regex heuristics (UNSICHER).

ADDENDUM_PATH = FIXTURE_DIR / "expected_addendum_1.json"
ADDENDUM_SHA256 = "375961821f46d9da96ebf986871fbbbfad477d51d6dbe286a176b5af419b075f"
ADDENDUM = json.loads(ADDENDUM_PATH.read_text(encoding="utf-8"))
ADDENDUM_MAILS = {m["n"]: m for m in ADDENDUM["mails"]}
# The generic GENERAL_REPLY sentence of integrations/reply_draft.py::_build_general.
GENERIC_BOILERPLATE = (
    "Gerne beantworte ich Ihre Rückfragen und freue mich auf die nächsten Schritte",
)

UNSICHER_ITEMS.append(
    "Gold addendum 1 (M5/M6 must_not_add / must_contain_add) is checked by keyword/regex heuristics; "
    "'Dank für Ihre Nachricht' is not counted as thanks for the Rückmeldung/Information."
)


def offers_follow_up_questions(text: str) -> bool:
    return bool(re.search(r"rückfrage|fragen\b.{0,40}beantwort|für fragen .{0,30}zur verfügung", text, re.I))


def expects_next_steps(text: str) -> bool:
    return bool(
        re.search(
            r"nächste[nr]? schritt|freue mich auf .{0,30}gespräch|gespräch.{0,30}freue|"
            r"weitere[nrs]? (verfahren|verlauf)|fortsetzung",
            text,
            re.I,
        )
    )


def uses_generic_boilerplate(text: str) -> bool:
    return any(b.lower() in (text or "").lower() for b in GENERIC_BOILERPLATE)


def thanks_for_feedback(text: str) -> bool:
    return bool(re.search(r"dank\w*\b.{0,60}(rückmeldung|information|mitteilung)", text, re.I))


def refers_to_requested_documents(text: str) -> bool:
    return bool(re.search(r"unterlagen|dokument|arbeitszeugnis|angefordert", text, re.I))


def names_arbeitszeugnis_as_attached(text: str) -> bool:
    """Text mention only; does NOT replace the ReplyDraft.attachments field check."""
    return any(
        re.search(r"arbeitszeugnis", s, re.I) and re.search(r"anbei|beigefügt|im anhang|angehängt|anhängend", s, re.I)
        for s in _sentences(text)
    )


def body_sentences(body: str) -> list[str]:
    """Sentences between salutation and sign-off ('Mit freundlichen Grüßen')."""
    lines = (body or "").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines:
        lines.pop(0)  # salutation
    text = "\n".join(lines)
    text = re.split(r"\n\s*(mit freundlichen grüßen|viele grüße|beste grüße|freundliche grüße)", text, flags=re.I)[0]
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _addendum_draft(world, n):
    draft, how = product_draft(world, n)
    return require_draft(n, draft, how)


def _xfail_addendum(n: int, field_name: str, why: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"M{n} addendum {field_name}: {why}")


def test_gold_addendum_1_sha256():
    assert hashlib.sha256(ADDENDUM_PATH.read_bytes()).hexdigest() == ADDENDUM_SHA256


def test_gold_addendum_1_extends_expected_json_hash():
    assert ADDENDUM["extends"]["file"] == GOLD_PATH.name
    assert ADDENDUM["extends"]["sha256"] == GOLD_SHA256 == hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    assert sorted(ADDENDUM_MAILS) == [5, 6]


def test_addendum_checkers_red_on_violation_green_on_good_text():
    bad = "vielen Dank für Ihre Nachricht. " + GENERIC_BOILERPLATE[0] + "."
    assert offers_follow_up_questions(bad) and expects_next_steps(bad) and uses_generic_boilerplate(bad)
    assert not thanks_for_feedback(bad) and not refers_to_requested_documents(bad)
    assert expects_next_steps("Ich freue mich auf das Gespräch.")
    good5 = "Sehr geehrte Frau Brinkmann,\n\nvielen Dank für Ihre Rückmeldung.\n\nMit freundlichen Grüßen\nRobin\n"
    assert thanks_for_feedback(good5) and not offers_follow_up_questions(good5) and not expects_next_steps(good5)
    assert len(body_sentences(good5)) == 1
    good6 = "anbei sende ich Ihnen die angeforderten Unterlagen: das Arbeitszeugnis ist beigefügt."
    assert refers_to_requested_documents(good6) and names_arbeitszeugnis_as_attached(good6)
    assert not names_arbeitszeugnis_as_attached("Ein Arbeitszeugnis reiche ich nach.")


@_xfail_addendum(5, "must_not_add[0]", "product GENERAL_REPLY offers to answer Rückfragen after a rejection")
def test_m5_addendum_no_offer_to_answer_questions(world):
    assert "Rückfragen" in ADDENDUM_MAILS[5]["must_not_add"][0]
    draft = _addendum_draft(world, 5)
    assert not offers_follow_up_questions(draft_text(draft)), draft.body


@_xfail_addendum(5, "must_not_add[1]", "product draft says 'freue mich auf die nächsten Schritte' after a rejection")
def test_m5_addendum_no_next_steps_or_interview_expectation(world):
    assert "nächster Schritte" in ADDENDUM_MAILS[5]["must_not_add"][1]
    draft = _addendum_draft(world, 5)
    assert not expects_next_steps(draft_text(draft)), draft.body


@_xfail_addendum(5, "must_not_add[2]", "product uses the generic GENERAL_REPLY boilerplate instead of a thanks")
def test_m5_addendum_no_generic_boilerplate(world):
    assert "Textbaustein" in ADDENDUM_MAILS[5]["must_not_add"][2]
    draft = _addendum_draft(world, 5)
    assert not uses_generic_boilerplate(draft_text(draft)), draft.body


@_xfail_addendum(5, "must_contain_add[0]", "product thanks only 'für Ihre Nachricht', not for Rückmeldung/Information")
def test_m5_addendum_thanks_for_feedback(world):
    assert ADDENDUM_MAILS[5]["must_contain_add"] == ["Dank für die Rückmeldung bzw. Information"]
    draft = _addendum_draft(world, 5)
    assert thanks_for_feedback(draft.body), draft.body


def test_m5_addendum_max_sentences_body(world):
    limit = ADDENDUM_MAILS[5]["max_sentences_body"]
    assert limit == 3
    draft = _addendum_draft(world, 5)
    assert len(body_sentences(draft.body)) <= limit, body_sentences(draft.body)


@_xfail_addendum(6, "must_contain_add[0]", "product GENERAL_REPLY does not mention the requested documents")
def test_m6_addendum_refers_to_requested_documents(world):
    assert ADDENDUM_MAILS[6]["must_contain_add"][0] == "Bezug auf die angeforderten Unterlagen"
    draft = _addendum_draft(world, 6)
    assert refers_to_requested_documents(draft.body), draft.body


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="M6 addendum must_contain_add attachment: ReplyDraft has no attachments field",
)
def test_m6_addendum_arbeitszeugnis_attached_field(world):
    """Real attachment field on ReplyDraft, not a word in the text (Kritiker)."""
    assert "Arbeitszeugnis_Vorarbeitgeber.pdf" in ADDENDUM_MAILS[6]["must_contain_add"][1]
    allowed = GOLD_MAILS[6]["attachments_allowed"]
    assert allowed == ["Arbeitszeugnis_Vorarbeitgeber.pdf"]
    draft = _addendum_draft(world, 6)
    attachments = getattr(draft, "attachments", None)
    assert attachments is not None, "ReplyDraft has no attachments field"
    names = [str(getattr(a, "file_name", a)) for a in attachments]
    assert any(n.endswith("Arbeitszeugnis_Vorarbeitgeber.pdf") for n in names), names
    # Only gold-allowed attachments: no SQL certificate, no Lebenslauf, no Anschreiben.
    assert all(any(n.endswith(a) for a in allowed) for n in names), names
    assert not any(re.search(r"sql|zertifikat|lebenslauf|anschreiben", n, re.I) for n in names), names


@_xfail_addendum(6, "must_contain_add[1] text", "product draft text does not name the Arbeitszeugnis as attached")
def test_m6_addendum_arbeitszeugnis_named_attached_in_text(world):
    """Additional text check; does not replace the attachments-field test above."""
    assert "Arbeitszeugnis" in ADDENDUM_MAILS[6]["must_contain_add"][1]
    draft = _addendum_draft(world, 6)
    assert names_arbeitszeugnis_as_attached(draft_text(draft)), draft.body


@_xfail_addendum(6, "must_not_add[0]", "product offers Rückfragen / 'nächsten Schritte' instead of answering")
def test_m6_addendum_no_questions_or_next_steps_substitute(world):
    assert "Rückfragen" in ADDENDUM_MAILS[6]["must_not_add"][0]
    draft = _addendum_draft(world, 6)
    text = draft_text(draft)
    assert not (offers_follow_up_questions(text) or expects_next_steps(text)), draft.body


@_xfail_addendum(6, "must_not_add[1]", "product uses the generic GENERAL_REPLY boilerplate for a document request")
def test_m6_addendum_no_generic_boilerplate(world):
    assert "Textbaustein" in ADDENDUM_MAILS[6]["must_not_add"][1]
    draft = _addendum_draft(world, 6)
    assert not uses_generic_boilerplate(draft_text(draft)), draft.body


# --- RFC 5545 folding inside the mail domain (Kritiker #192) -------------------
# The fixture now folds ORGANIZER right after "mailto:" so the line-based privacy
# scan never sees a truncated domain. The product parser must still unfold a fold
# that lands in the *middle* of the domain. The folded text is built at runtime
# from the full *.example.org address, so this source never contains a partial
# domain either.

_FOLD_ADDRESS = "helene.brinkmann@nordlicht-logistik.example.org"


def _ics_with_domain_fold(newline: str = "\r\n") -> tuple[bytes, int]:
    line = f"ORGANIZER;CN=Helene Brinkmann:mailto:{_FOLD_ADDRESS}"
    cut = line.index("@") + len("nordlicht-logistik.ex") + 1  # fold inside the domain
    assert line[cut - 3:cut] == ".ex" and line[cut:].startswith("ample.org")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Karrierekrake//t0110 fold test//DE",
        "BEGIN:VEVENT", "UID:fold-0001@karrierekrake.example.org",
        "DTSTAMP:20261018T080000Z", "DTSTART:20261022T130000Z", "DTEND:20261022T140000Z",
        "SUMMARY:Synthetischer Termin", line[:cut], " " + line[cut:],
        "END:VEVENT", "END:VCALENDAR",
    ]
    return (newline.join(lines) + newline).encode("utf-8"), cut


def test_ics_parser_unfolds_line_folded_inside_mail_domain(tmp_path):
    from integrations.calendar.local_ics import read_calendar

    raw, _cut = _ics_with_domain_fold()
    assert b"\r\n ample.org" in raw  # really folded mid-domain (CRLF + one space)
    path = tmp_path / "folded.ics"
    path.write_bytes(raw)
    events = list(read_calendar(path).walk("VEVENT"))
    assert len(events) == 1
    organizer = str(events[0]["ORGANIZER"])
    assert organizer == f"mailto:{_FOLD_ADDRESS}", organizer
    assert events[0]["ORGANIZER"].params.get("CN") == "Helene Brinkmann"


def test_fixture_calendar_organizers_unfold_to_full_example_addresses():
    from integrations.calendar.local_ics import read_calendar

    got = sorted(str(e["ORGANIZER"]) for e in read_calendar(FIXTURE_DIR / "calendar.ics").walk("VEVENT")
                 if "ORGANIZER" in e)
    assert got == [
        f"mailto:{_FOLD_ADDRESS}",
        "mailto:recruiting@lindenhof-consulting.example.org",
    ], got

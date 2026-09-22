#!/usr/bin/env python3
"""Evaluate production CV import against CV_Parser_Sollwerte_Vollstaendig.txt.

Usage:
  python scripts/run_cv_sollwerte_corpus.py
  python scripts/run_cv_sollwerte_corpus.py --phi
  python scripts/run_cv_sollwerte_corpus.py --json /tmp/out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "tests" / "fixtures" / "cv_corpus"
SOLL = CORPUS / "CV_Parser_Sollwerte_Vollstaendig.txt"

PDFS = [
    "DE_01_Klassisch.pdf",
    "DE_02_Zweispaltig_Trap.pdf",
    "DE_03_C1_Kontextfalle.pdf",
    "DE_04_Unvollstaendige_Kontaktdaten.pdf",
    "DE_05_Zweiseitig.pdf",
    "EN_01_Classic_Resume.pdf",
    "EN_02_Two_Column_Trap.pdf",
    "EN_03_Missing_Address_Fields.pdf",
    "EN_04_German_Address_English_CV.pdf",
    "EN_05_Skills_Heavy.pdf",
]


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = re.sub(r"\s+", " ", s)
    return s


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def parse_sollwerte(path: Path) -> dict[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    docs: dict[str, dict[str, Any]] = {}
    current: str | None = None
    block: dict[str, Any] = {}

    def flush() -> None:
        nonlocal current, block
        if current:
            docs[current] = block
        current, block = None, {}

    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^DATEI:\s*(\S+\.pdf)\s*$", line)
        if m:
            flush()
            current = m.group(1)
            block = {"_raw_lines": []}
            continue
        if current is None:
            continue
        if not line.strip() or line.startswith("---") or line.startswith("===="):
            continue
        block["_raw_lines"].append(line)
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        block[key] = val
    flush()
    return docs


def _is_absent(val: str | None) -> bool:
    v = _norm(val or "")
    return v in {
        "nicht vorhanden",
        "keine beschreibung vorhanden",
        "",
        "n/a",
        "null",
    }


def _split_pipe_list(val: str) -> list[str]:
    if _is_absent(val):
        return []
    parts = [p.strip() for p in val.split("|")]
    return [p for p in parts if p and not _is_absent(p)]


def _parse_beruf(val: str) -> dict[str, str]:
    # "05/2022 - heute | Title | Company, City | Description"
    parts = [p.strip() for p in val.split("|")]
    while len(parts) < 4:
        parts.append("")
    period, title, company, desc = parts[0], parts[1], parts[2], parts[3]
    return {
        "period": period,
        "title": title,
        "company": company,
        "description": "" if _is_absent(desc) else desc,
    }


def _parse_edu(val: str) -> dict[str, str]:
    parts = [p.strip() for p in val.split("|")]
    while len(parts) < 3:
        parts.append("")
    return {
        "period": parts[0],
        "qualification": parts[1],
        "institution": parts[2],
        "extra": parts[3] if len(parts) > 3 else "",
    }


def _parse_lang(val: str) -> tuple[str, str]:
    parts = [p.strip() for p in val.split("|")]
    lang = parts[0] if parts else ""
    level = parts[1] if len(parts) > 1 else ""
    return lang, level


def evaluate(parsed: dict[str, Any], exp: dict[str, Any]) -> list[dict[str, Any]]:
    """Return list of field failures {field, expected, got, kind}."""
    fails: list[dict[str, Any]] = []
    personal = parsed.get("personal") or {}

    def fail(field: str, expected: Any, got: Any, kind: str = "mismatch") -> None:
        fails.append({"field": field, "expected": expected, "got": got, "kind": kind})

    # Name
    if not _is_absent(exp.get("VORNAME")):
        got = personal.get("first_name") or ""
        if _norm(exp["VORNAME"]) not in _norm(got) and _norm(exp["VORNAME"]) not in _norm(
            f"{got} {personal.get('last_name') or ''}"
        ):
            fail("VORNAME", exp["VORNAME"], got)
    if not _is_absent(exp.get("NACHNAME")):
        got = personal.get("last_name") or ""
        if _norm(exp["NACHNAME"]) not in _norm(got) and _norm(exp["NACHNAME"]) not in _norm(
            f"{personal.get('first_name') or ''} {got}"
        ):
            fail("NACHNAME", exp["NACHNAME"], got)

    # Contact
    if not _is_absent(exp.get("E-MAIL")):
        emails = parsed.get("emails") or []
        if not any(_norm(exp["E-MAIL"]) == _norm(e) for e in emails):
            fail("E-MAIL", exp["E-MAIL"], emails)
    if _is_absent(exp.get("TELEFON")):
        # Must not invent a real phone — date pollution counts as fail
        phones = parsed.get("phones") or []
        real = [p for p in phones if _digits(p) and not re.search(r"\d{2}[./]\d{2}", p)]
        # Allow empty; fail if we have phone-like that isn't from PDF when absent
        # Soft: any phone when expected absent is invent
        if phones and any(re.search(r"\+\d|\d{3,}", p) and "/" not in p for p in phones):
            # still fail invent if looks like phone number
            phoneish = [p for p in phones if re.match(r"^\+?\d[\d\s/-]{6,}$", p.strip())]
            if phoneish:
                fail("TELEFON", "NICHT VORHANDEN", phones, "invented")
    elif not _is_absent(exp.get("TELEFON")):
        phones = " ".join(parsed.get("phones") or [])
        if _digits(exp["TELEFON"]) not in _digits(phones):
            fail("TELEFON", exp["TELEFON"], parsed.get("phones"))

    if _is_absent(exp.get("GEBURTSDATUM")):
        if personal.get("date_of_birth"):
            fail("GEBURTSDATUM", "NICHT VORHANDEN", personal.get("date_of_birth"), "invented")
    elif not _is_absent(exp.get("GEBURTSDATUM")):
        if exp["GEBURTSDATUM"] not in (personal.get("date_of_birth") or ""):
            fail("GEBURTSDATUM", exp["GEBURTSDATUM"], personal.get("date_of_birth"))

    # Address fields
    for key, pkey in (
        ("STRASSE", "street"),
        ("PLZ", "postal_code"),
        ("ORT", "city"),
    ):
        if _is_absent(exp.get(key)):
            got = personal.get(pkey) or ""
            if key == "STRASSE" and got and _is_absent(exp.get("PLZ")):
                # city-only docs — street invent
                if got and got.lower() not in _norm(exp.get("ORT") or ""):
                    fail(key, "NICHT VORHANDEN", got, "invented")
            elif key == "PLZ" and got:
                fail(key, "NICHT VORHANDEN", got, "invented")
            elif key == "ORT" and not _is_absent(exp.get("ORT")):
                pass
        elif not _is_absent(exp.get(key)):
            blob = f"{personal.get('street') or ''} {personal.get('address') or ''} {personal.get(pkey) or ''}"
            if key == "STRASSE":
                want = exp["STRASSE"]
                hn = exp.get("HAUSNUMMER") or ""
                if _norm(want) not in _norm(blob):
                    fail(key, want, personal.get("street"))
                if not _is_absent(hn) and hn not in blob and hn != (personal.get("house_number") or ""):
                    fail("HAUSNUMMER", hn, personal.get("house_number"))
            else:
                if _norm(exp[key]) not in _norm(blob):
                    fail(key, exp[key], personal.get(pkey))

    # Document title must not be name
    title = exp.get("DOKUMENTTITEL_NUR_LAYOUT") or ""
    if title and not _is_absent(title):
        full = f"{personal.get('first_name') or ''} {personal.get('last_name') or ''}"
        # forbid using layout title tokens as the whole name
        if _norm(title) == _norm(full) or _norm(title) == _norm(personal.get("first_name") or ""):
            fail("DOKUMENTTITEL_AS_NAME", title, full, "trap")

    # Languages
    exp_n = int(exp.get("SPRACHEN_ANZAHL") or 0)
    got_langs = parsed.get("languages") or []
    if len(got_langs) < exp_n:
        fail("SPRACHEN_ANZAHL", exp_n, len(got_langs), "count")
    for i in range(1, exp_n + 1):
        raw = exp.get(f"SPRACHE_{i}") or ""
        lang, level = _parse_lang(raw)
        matched = False
        for g in got_langs:
            if _norm(lang) in _norm(g.get("language") or ""):
                gl = _norm(g.get("level") or "")
                el = _norm(level)
                if el in ("native", "muttersprache") and gl in ("native", "muttersprache", "c2", ""):
                    matched = True
                elif el and (el in gl or gl in el):
                    matched = True
                elif not el:
                    matched = True
                break
        if not matched:
            fail(f"SPRACHE_{i}", raw, got_langs)

    # Extra languages that look like courses = fail (heuristic: known bad tokens)
    bad_lang_tokens = ("lean", "power bi", "beschwerde", "datenschutz", "kenntnisse", "further")
    for g in got_langs:
        ln = _norm(g.get("language") or "")
        if any(b in ln for b in bad_lang_tokens):
            fail("SPRACHE_FALSE", "not a language", g, "false_extra")

    # Licenses
    exp_lic_n = int(exp.get("FUEHRERSCHEINE_ANZAHL") or 0)
    got_lic = []
    for it in parsed.get("driving_license") or []:
        if isinstance(it, dict):
            got_lic.append(str(it.get("value") or ""))
        else:
            got_lic.append(str(it))
    for i in range(1, exp_lic_n + 1):
        want = (exp.get(f"FUEHRERSCHEIN_{i}") or "").strip()
        if want and not any(_norm(want) == _norm(g) or _norm(want) in _norm(g) for g in got_lic):
            fail(f"FUEHRERSCHEIN_{i}", want, got_lic)

    # Education
    exp_edu_n = int(exp.get("AUSBILDUNG_ANZAHL") or 0)
    got_edu = parsed.get("education") or []
    if len(got_edu) < exp_edu_n:
        fail("AUSBILDUNG_ANZAHL", exp_edu_n, len(got_edu), "count")
    for i in range(1, exp_edu_n + 1):
        e = _parse_edu(exp.get(f"AUSBILDUNG_{i}") or "")
        matched = False
        for g in got_edu:
            blob = _norm(
                f"{g.get('qualification') or ''} {g.get('institution') or ''} "
                f"{g.get('start_date') or ''} {g.get('end_date') or ''}"
            )
            if _norm(e["qualification"]) and _norm(e["qualification"]) in blob:
                matched = True
                break
        if not matched:
            fail(f"AUSBILDUNG_{i}", exp.get(f"AUSBILDUNG_{i}"), got_edu)

    # Work
    exp_work_n = int(exp.get("BERUFSERFAHRUNG_ANZAHL") or 0)
    got_work = parsed.get("work_experience") or []
    if len(got_work) < exp_work_n:
        fail("BERUFSERFAHRUNG_ANZAHL", exp_work_n, len(got_work), "count")
    for i in range(1, exp_work_n + 1):
        key = f"BERUF_{i}"
        w = _parse_beruf(exp.get(key) or "")
        matched = False
        for g in got_work:
            title = _norm(g.get("title") or "")
            company = _norm(g.get("company") or "")
            if _norm(w["title"]) and _norm(w["title"]) in title:
                # company may include city suffix
                if not _norm(w["company"]) or any(
                    _norm(tok) in company or _norm(tok) in title
                    for tok in re.split(r"[,/]", w["company"])
                    if len(tok.strip()) > 2
                ):
                    matched = True
                    break
        if not matched:
            fail(key, exp.get(key), [{"title": g.get("title"), "company": g.get("company")} for g in got_work])

    # Software
    soft_raw = exp.get("SOFTWARE") or ""
    if not _is_absent(soft_raw) and soft_raw:
        want = _split_pipe_list(soft_raw)
        got = [_norm(s) for s in (parsed.get("software") or [])]
        missing = [s for s in want if not any(_norm(s) in g or g in _norm(s) for g in got)]
        if missing:
            fail("SOFTWARE", missing, parsed.get("software"), "missing")

    # Skills
    skills_raw = exp.get("SKILLS") or ""
    if not _is_absent(skills_raw) and skills_raw:
        want = _split_pipe_list(skills_raw)
        got = [_norm(s) for s in (parsed.get("skills") or [])]
        missing = [s for s in want if not any(_norm(s) in g or g in _norm(s) for g in got)]
        if missing:
            fail("SKILLS", missing, parsed.get("skills"), "missing")

    # Certificates
    cert_n = int(exp.get("ZERTIFIKATE/WEITERBILDUNGEN_ANZAHL") or 0)
    got_certs = parsed.get("certificates") or []
    if cert_n == 0 and _is_absent(exp.get("ZERTIFIKATE/WEITERBILDUNGEN")):
        # should be empty or only true certs — soft
        pass
    elif cert_n > 0:
        if len(got_certs) < cert_n:
            # also accept list form ZERTIFIKATE/WEITERBILDUNGEN
            listed = _split_pipe_list(exp.get("ZERTIFIKATE/WEITERBILDUNGEN") or "")
            if listed:
                got_names = [_norm(c.get("name") if isinstance(c, dict) else str(c)) for c in got_certs]
                miss = [x for x in listed if not any(_norm(x) in g or g in _norm(x) for g in got_names)]
                if miss:
                    fail("ZERTIFIKATE", miss, got_certs, "missing")
            else:
                fail("ZERTIFIKATE_ANZAHL", cert_n, len(got_certs), "count")
        for i in range(1, cert_n + 1):
            raw = exp.get(f"ZERTIFIKAT_{i}") or ""
            if not raw:
                continue
            name = raw.split("|")[0].strip()
            got_names = [
                _norm(c.get("name") if isinstance(c, dict) else str(c)) for c in got_certs
            ]
            if not any(_norm(name) in g or g in _norm(name) for g in got_names):
                fail(f"ZERTIFIKAT_{i}", raw, got_certs)

    # Phone pollution: dates must not appear as phones
    for p in parsed.get("phones") or []:
        if re.search(r"\d{2}[./]\d{2}[./]\d{2,4}", p) or re.search(r"\d{2}/\d{4}\s*-\s*", p):
            fail("PHONE_POLLUTION", "no dates", p, "false_extra")

    return fails


def run(*, phi: bool = False) -> dict[str, Any]:
    from core.cv_parser import import_cv

    soll = parse_sollwerte(SOLL)
    report: dict[str, Any] = {
        "phi": phi,
        "documents": {},
        "passed": 0,
        "failed": 0,
        "total": 0,
    }
    for name in PDFS:
        path = CORPUS / name
        exp = soll.get(name)
        if not exp:
            report["documents"][name] = {"ok": False, "error": "missing sollwerte"}
            report["failed"] += 1
            report["total"] += 1
            continue
        t0 = time.perf_counter()
        parsed = import_cv(path, guenther_enabled=phi)
        elapsed = time.perf_counter() - t0
        fails = evaluate(parsed, exp)
        ok = not fails
        report["documents"][name] = {
            "ok": ok,
            "seconds": round(elapsed, 3),
            "fail_count": len(fails),
            "fails": fails[:40],
        }
        report["total"] += 1
        if ok:
            report["passed"] += 1
        else:
            report["failed"] += 1
    report["ok"] = report["failed"] == 0
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phi", action="store_true")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    if not SOLL.is_file():
        print(f"missing {SOLL}", file=sys.stderr)
        return 2
    report = run(phi=args.phi)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"phi={args.phi} passed={report['passed']}/{report['total']}")
    for name, doc in report["documents"].items():
        status = "OK" if doc.get("ok") else "FAIL"
        print(f"  [{status}] {name} fails={doc.get('fail_count', 0)} t={doc.get('seconds')}s")
        if not doc.get("ok"):
            for f in (doc.get("fails") or [])[:8]:
                print(f"      - {f['field']}: {f.get('kind')} expected={f.get('expected')!r} got={f.get('got')!r}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

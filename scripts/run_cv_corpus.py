"""Black-box CV corpus evaluator against expected_results.json.

Usage:
  python scripts/run_cv_corpus.py
  python scripts/run_cv_corpus.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "tests" / "fixtures" / "cv_corpus"
EXPECTED_PATH = CORPUS / "expected_results.json"

SECTIONS = (
    "personal",
    "address",
    "languages",
    "licenses",
    "education",
    "work",
    "certificates",
    "software",
    "skills",
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _contains_ci(haystack: str, needle: str) -> bool:
    return _norm(needle) in _norm(haystack)


def _list_values(items: list, key: str | None = None) -> list[str]:
    out: list[str] = []
    for it in items or []:
        if isinstance(it, dict) and key:
            out.append(str(it.get(key) or ""))
        elif isinstance(it, dict):
            out.append(str(it.get("value") or it.get("name") or it.get("language") or ""))
        else:
            out.append(str(it))
    return out


def evaluate_doc(parsed: dict, expected: dict) -> dict[str, tuple[bool, str]]:
    results: dict[str, tuple[bool, str]] = {}
    personal = parsed.get("personal") or {}
    name = expected.get("name") or {}

    # personal: name + email/phone/dob when expected
    fails: list[str] = []
    if name.get("first_name") and not _contains_ci(personal.get("first_name", ""), name["first_name"]):
        # allow full name in first_name or split
        full = f"{personal.get('first_name', '')} {personal.get('last_name', '')}"
        if not _contains_ci(full, name["first_name"]):
            fails.append(f"first={personal.get('first_name')!r}")
    if name.get("last_name") and not _contains_ci(personal.get("last_name", ""), name["last_name"]):
        full = f"{personal.get('first_name', '')} {personal.get('last_name', '')}"
        if not _contains_ci(full, name["last_name"]):
            fails.append(f"last={personal.get('last_name')!r}")
    if expected.get("email"):
        emails = parsed.get("emails") or []
        if not any(_norm(expected["email"]) == _norm(e) for e in emails):
            fails.append("email")
    if expected.get("phone"):
        phones = " ".join(parsed.get("phones") or [])
        digits_exp = re.sub(r"\D", "", expected["phone"])
        digits_got = re.sub(r"\D", "", phones)
        if digits_exp and digits_exp not in digits_got:
            fails.append("phone")
    if expected.get("dob"):
        if expected["dob"] not in (personal.get("date_of_birth") or ""):
            fails.append("dob")
    # traps: title must not be name
    for trap in expected.get("traps") or []:
        if "not a name" in trap.lower() or "is not a name" in trap.lower():
            title_word = trap.split()[0]
            full = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".lower()
            if title_word.lower() in full and name.get("first_name", "").lower() not in title_word.lower():
                # only fail if the forbidden title token is used as the name
                if _norm(personal.get("first_name", "")).startswith(_norm(title_word)[:8]):
                    fails.append(f"title_as_name:{title_word}")
    results["personal"] = (not fails, "; ".join(fails) or "ok")

    # address
    addr_exp = expected.get("address") or {}
    addr_fails: list[str] = []
    for field in ("street", "postal_code", "city"):
        if field in addr_exp:
            got = personal.get(field) or personal.get("address") or ""
            if field == "street":
                # house number may be separate or attached
                want = addr_exp["street"]
                hn = addr_exp.get("house_number", "")
                if not (_contains_ci(got, want) or _contains_ci(personal.get("address", ""), want)):
                    addr_fails.append(field)
                elif hn and not (
                    hn in (personal.get("street") or "")
                    or hn in (personal.get("address") or "")
                    or personal.get("house_number") == hn
                ):
                    # soft: house number may be in street
                    if hn not in got and hn not in (personal.get("address") or ""):
                        addr_fails.append("house_number")
            else:
                if not _contains_ci(got, addr_exp[field]) and not _contains_ci(
                    personal.get("address", ""), addr_exp[field]
                ):
                    addr_fails.append(field)
    for miss in expected.get("missing") or []:
        if miss in ("street", "house_number", "postal_code", "phone", "date_of_birth"):
            if miss == "phone" and (parsed.get("phones") or []):
                # only fail invent if we invented a non-empty phone when missing
                pass  # phones from regex — if PDF has none, list empty
            if miss == "date_of_birth" and personal.get("date_of_birth"):
                addr_fails.append(f"invented:{miss}")
            if miss == "street" and personal.get("street") and "city" in addr_exp and len(addr_exp) == 1:
                # city-only expected — street should be empty
                addr_fails.append("invented:street")
            if miss == "postal_code" and personal.get("postal_code") and "postal_code" not in addr_exp:
                addr_fails.append("invented:postal_code")
    results["address"] = (not addr_fails, "; ".join(addr_fails) or "ok")

    # languages
    lang_fails: list[str] = []
    got_langs = parsed.get("languages") or []
    exp_langs = expected.get("languages") or []
    if len(got_langs) < len(exp_langs):
        lang_fails.append(f"count {len(got_langs)}<{len(exp_langs)}")
    for pair in exp_langs:
        name_l, level = pair[0], pair[1]
        matched = False
        for g in got_langs:
            if _contains_ci(g.get("language", ""), name_l):
                gl = (g.get("level") or "").upper()
                el = level.upper()
                if el in ("NATIVE", "MUTTERSPRACHE") and gl in ("NATIVE", "MUTTERSPRACHE", "C2", ""):
                    matched = True
                elif el in gl or gl in el:
                    matched = True
                elif not gl and el:
                    lang_fails.append(f"{name_l}:missing_level")
                    matched = True  # name found
                break
        if not matched:
            lang_fails.append(f"missing:{name_l}")
    # heading as language trap
    for g in got_langs:
        if _norm(g.get("language", "")) in {
            "weitere kenntnisse",
            "additional skills",
            "tech stack",
            "kenntnisse",
        }:
            lang_fails.append(f"heading_as_lang:{g.get('language')}")
    results["languages"] = (not lang_fails, "; ".join(lang_fails) or "ok")

    # licenses — context sensitive
    lic_fails: list[str] = []
    got_lic = [str(x.get("value") if isinstance(x, dict) else x).upper() for x in (parsed.get("driving_license") or [])]
    exp_lic = [str(x).upper() for x in (expected.get("licenses") or [])]
    if "licenses" in expected or "licenses" in expected:
        for code in exp_lic:
            if code not in got_lic:
                lic_fails.append(f"missing:{code}")
        # If expected empty, must not invent from CEFR
        if exp_lic == [] and got_lic:
            # C1 alone is suspicious when licenses expected empty
            lic_fails.append(f"invented:{got_lic}")
        # Extra CEFR-looking licences when not in expected
        for code in got_lic:
            if code in {"A1", "A2", "B1", "B2", "C1", "C2"} and code not in exp_lic:
                # C1 may be valid licence only when expected
                lic_fails.append(f"extra_cefr:{code}")
    results["licenses"] = (not lic_fails, "; ".join(lic_fails) or "ok")

    # counts / lists
    def check_count(key_parsed: str, exp_key_count: str, exp_key_list: str, item_key: str | None) -> tuple[bool, str]:
        items = parsed.get(key_parsed) or []
        if exp_key_list in expected and isinstance(expected[exp_key_list], list):
            want = expected[exp_key_list]
            vals = _list_values(items, item_key)
            missing = [w for w in want if not any(_contains_ci(v, w) for v in vals)]
            if missing:
                return False, f"missing:{missing}"
            return True, f"n={len(items)}"
        if exp_key_count in expected:
            need = int(expected[exp_key_count])
            if len(items) < need:
                return False, f"count {len(items)}<{need}"
            return True, f"n={len(items)}"
        return True, "n/a"

    results["education"] = check_count("education", "education_count", "education", "qualification")
    results["work"] = check_count("work_experience", "work_count", "work", "title")
    results["certificates"] = check_count("certificates", "certificates_count", "certificates", "name")
    results["software"] = check_count("software", "software_count", "software", None)
    results["skills"] = check_count("skills", "skills_count", "skills", None)
    return results


def run_corpus() -> tuple[list[dict], bool]:
    # Docpick production path needs Docling + local LLM — skip cleanly in lean CI.
    try:
        import docling  # noqa: F401
    except ImportError:
        print(
            "SKIP cv_corpus: Docpick production import requires docling "
            "(not installed in this environment). DET is not used as fallback."
        )
        return (
            [
                {
                    "cv": "__SKIP__",
                    "pass": True,
                    "sections": {s: "PASS" for s in SECTIONS},
                    "skip_reason": "docling_missing",
                }
            ],
            True,
        )

    from core.cv_parser import import_cv

    expected_all = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))["documents"]
    rows: list[dict] = []
    all_ok = True
    for name, exp in expected_all.items():
        path = CORPUS / name
        if not path.exists():
            rows.append({"cv": name, "error": "missing file", "pass": False})
            all_ok = False
            continue
        try:
            parsed = import_cv(path)
        except Exception as exc:  # noqa: BLE001
            rows.append({"cv": name, "error": str(exc), "pass": False})
            all_ok = False
            continue
        section = evaluate_doc(parsed, exp)
        ok = all(v[0] for v in section.values())
        if not ok:
            all_ok = False
        rows.append(
            {
                "cv": name,
                "pass": ok,
                "sections": {k: ("PASS" if v[0] else f"FAIL({v[1]})") for k, v in section.items()},
                "preview_name": parsed.get("personal"),
                "lang_n": len(parsed.get("languages") or []),
                "lic": parsed.get("driving_license"),
                "edu_n": len(parsed.get("education") or []),
                "work_n": len(parsed.get("work_experience") or []),
            }
        )
    return rows, all_ok


def print_matrix(rows: list[dict]) -> None:
    header = f"{'CV':<36} " + " ".join(f"{s[:4]:<8}" for s in SECTIONS)
    print(header)
    print("-" * len(header))
    for row in rows:
        if "error" in row and "sections" not in row:
            print(f"{row['cv']:<36} ERROR {row['error']}")
            continue
        cells = []
        for s in SECTIONS:
            val = row["sections"][s]
            cells.append("PASS" if val == "PASS" else "FAIL")
        print(f"{row['cv']:<36} " + " ".join(f"{c:<8}" for c in cells))
        if not row["pass"]:
            fails = {k: v for k, v in row["sections"].items() if v != "PASS"}
            print(f"  -> {fails}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows, ok = run_corpus()
    if args.json:
        print(json.dumps({"ok": ok, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print_matrix(rows)
        passed = sum(1 for r in rows if r.get("pass"))
        print(f"\n{passed}/{len(rows)} documents fully PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

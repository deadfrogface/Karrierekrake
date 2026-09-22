"""Holdout-100 Scorer V2: evaluate only productive, PDF-evidenced profile fields.

Does NOT read or modify frozen predictions' contents for correction — only scores them.
Does NOT modify expected_results_full.json.
"""

from __future__ import annotations

import itertools
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# --- normalization -----------------------------------------------------------


def _norm(s: Any) -> str:
    s = str(s or "").strip().lower()
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = re.sub(r"\s+", " ", s)
    return s


def _digits(s: Any) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    return False


def text_contains(value: Any, text: str) -> bool:
    if _empty(value) or not text:
        return False
    v = str(value).strip()
    if not v:
        return False
    if v.lower() in text.lower():
        return True
    d = _digits(v)
    if len(d) >= 6 and d in _digits(text):
        return True
    # token overlap for multi-word
    tokens = [t for t in re.split(r"[^\wÄÖÜäöüß]+", v.lower()) if len(t) >= 3]
    if tokens and all(t in text.lower() for t in tokens):
        return True
    return False


TARGET_ROLE_LABEL = re.compile(
    r"(?i)\b(berufswunsch|ziel(?:beruf|position)?|target\s*role|desired\s*role|career\s*objective)\b"
)

METADATA_FIELDS = frozenset(
    {
        "document_id",
        "filename",
        "layout",
        "region_note",
        "traps",
        "missing",
        "expected_status",
        "language",  # document language de/en — test metadata, not a spoken language entry
    }
)

SCHEMA_MAPPING = {
    "name.first_name": {"parsed": "personal.first_name", "profile": "personal.first_name", "class": "A"},
    "name.last_name": {"parsed": "personal.last_name", "profile": "personal.last_name", "class": "A"},
    "email": {"parsed": "emails[0]", "profile": "contact.email", "class": "A"},
    "phone": {"parsed": "phones[0]", "profile": "contact.phone", "class": "A"},
    "dob": {"parsed": "personal.date_of_birth", "profile": "personal.date_of_birth", "class": "A"},
    "address.street": {"parsed": "personal.street", "profile": "address.street", "class": "A"},
    "address.house_number": {"parsed": "personal.house_number", "profile": "address.house_number", "class": "A"},
    "address.postal_code": {"parsed": "personal.postal_code", "profile": "address.postal_code", "class": "A"},
    "address.city": {"parsed": "personal.city", "profile": "address.city", "class": "A"},
    "address.country": {"parsed": "personal.country", "profile": "address.country", "class": "A"},
    "languages": {"parsed": "languages", "profile": "qualifications.languages", "class": "A"},
    "licenses": {"parsed": "driving_license", "profile": "qualifications.driving_license", "class": "A"},
    "education": {"parsed": "education", "profile": "qualifications.education", "class": "A"},
    "employment": {"parsed": "work_experience", "profile": "qualifications.work_experience", "class": "A"},
    "skills": {"parsed": "skills", "profile": "qualifications.skills", "class": "A"},
    "software": {"parsed": "software", "profile": "qualifications.software", "class": "A"},
    "certificates": {"parsed": "certificates", "profile": "qualifications.certificates", "class": "A"},
    "target_role": {
        "parsed": "target_role",
        "profile": "jobs.desired_titles (optional / SearchIntent)",
        "class": "B",
        "evidence_required": True,
    },
}


@dataclass
class FactResult:
    document: str
    field: str
    group: str
    status: str  # correct | wrong | missing | hallucinated | wrong_category | skipped
    expected: Any = None
    actual: Any = None
    critical: bool = False
    skip_reason: str = ""


def pred_view(pred: dict[str, Any] | None) -> dict[str, Any]:
    if not pred:
        return {}
    pers = pred.get("personal") or {}
    lic = pred.get("driving_license") or ""
    if isinstance(lic, list):
        parts = []
        for item in lic:
            if isinstance(item, dict):
                parts.append(str(item.get("value") or item.get("name") or ""))
            else:
                parts.append(str(item))
        lic = " ".join(p for p in parts if p)
    return {
        "first_name": pers.get("first_name") or "",
        "last_name": pers.get("last_name") or "",
        "email": (pred.get("emails") or [""])[0] if pred.get("emails") else "",
        "phone": (pred.get("phones") or [""])[0] if pred.get("phones") else "",
        "street": pers.get("street") or "",
        "house_number": pers.get("house_number") or "",
        "postal_code": pers.get("postal_code") or "",
        "city": pers.get("city") or "",
        "country": pers.get("country") or "",
        "dob": pers.get("date_of_birth") or "",
        "languages": pred.get("languages") or [],
        "education": pred.get("education") or [],
        "employment": pred.get("work_experience") or [],
        "skills": pred.get("skills") or [],
        "software": pred.get("software") or [],
        "certificates": pred.get("certificates") or [],
        "licenses": lic,
        "target_role": pred.get("target_role") or "",
    }


def scalar_match(expected: Any, actual: Any, *, kind: str = "text") -> str:
    """Return correct|wrong|missing|hallucinated for a scalar fact."""
    if _empty(expected) and _empty(actual):
        return "correct"
    if _empty(expected) and not _empty(actual):
        return "hallucinated"
    if not _empty(expected) and _empty(actual):
        return "missing"
    if kind == "phone":
        ed, ad = _digits(expected), _digits(actual)
        if ed and (ed in ad or (len(ed) >= 6 and ed[-6:] in ad)):
            return "correct"
        return "wrong"
    if kind == "email":
        return "correct" if _norm(expected) == _norm(actual) else "wrong"
    if kind == "country":
        e, a = _norm(expected), _norm(actual)
        aliases = {
            "de": {"de", "deutschland", "germany"},
            "at": {"at", "österreich", "oesterreich", "austria"},
            "ch": {"ch", "schweiz", "switzerland"},
        }
        for canon, group in aliases.items():
            if e in group and a in group:
                return "correct"
        return "correct" if e == a or e in a or a in e else "wrong"
    e, a = _norm(expected), _norm(actual)
    if e == a or e in a or a in e:
        return "correct"
    return "wrong"


def _pair_score_lang(exp: tuple[str, str], act: dict[str, str]) -> float:
    en, el = _norm(exp[0]), _norm(exp[1])
    an, al = _norm(act.get("language") or ""), _norm(act.get("level") or "")
    if not en or not an:
        return 0.0
    name_ok = en == an or en in an or an in en
    if not name_ok:
        return 0.0
    # level
    if not el:
        return 0.8
    el_n = el.replace("muttersprache", "native")
    al_n = al.replace("muttersprache", "native")
    if el_n == al_n or el_n in al_n or al_n in el_n:
        return 1.0
    if el_n in ("native", "c2") and al_n in ("native", "c2", "muttersprache"):
        return 1.0
    return 0.4  # name ok, level wrong


def match_language_pairs(
    expected: list[Any], actual: list[Any]
) -> tuple[list[FactResult], dict[str, int]]:
    """Match language+level pairs; order-independent; level swap = wrong."""
    exp_pairs: list[tuple[str, str]] = []
    for item in expected or []:
        if isinstance(item, (list, tuple)) and item:
            exp_pairs.append((str(item[0]), str(item[1]) if len(item) > 1 else ""))
        elif isinstance(item, dict):
            exp_pairs.append((str(item.get("language") or ""), str(item.get("level") or "")))
        elif isinstance(item, str):
            parts = [p.strip() for p in item.replace("–", "-").split("-", 1)]
            exp_pairs.append((parts[0], parts[1] if len(parts) > 1 else ""))
    act_list: list[dict[str, str]] = []
    for item in actual or []:
        if isinstance(item, dict):
            act_list.append(
                {"language": str(item.get("language") or ""), "level": str(item.get("level") or "")}
            )
        else:
            parts = [p.strip() for p in str(item).replace("–", "-").split("-", 1)]
            act_list.append({"language": parts[0], "level": parts[1] if len(parts) > 1 else ""})

    stats = {"entry_tp": 0, "entry_fp": 0, "entry_fn": 0, "level_wrong": 0}
    rows: list[FactResult] = []
    used_act: set[int] = set()
    for i, ep in enumerate(exp_pairs):
        best_j, best_s = -1, 0.0
        for j, ap in enumerate(act_list):
            if j in used_act:
                continue
            s = _pair_score_lang(ep, ap)
            if s > best_s:
                best_s, best_j = s, j
        if best_j < 0 or best_s < 0.4:
            stats["entry_fn"] += 1
            rows.append(
                FactResult("", f"language:{i}", "languages", "missing", expected=ep, actual=act_list, critical=True)
            )
        else:
            used_act.add(best_j)
            if best_s >= 0.99:
                stats["entry_tp"] += 1
                rows.append(
                    FactResult("", f"language:{i}", "languages", "correct", expected=ep, actual=act_list[best_j], critical=True)
                )
            else:
                stats["level_wrong"] += 1
                rows.append(
                    FactResult(
                        "",
                        f"language:{i}",
                        "languages",
                        "wrong",
                        expected=ep,
                        actual=act_list[best_j],
                        critical=True,
                    )
                )
    for j, ap in enumerate(act_list):
        if j in used_act:
            continue
        # Extra language — if not a known language name, wrong_category
        from core.cv_parser import is_known_language_name

        name = ap.get("language") or ""
        if name and not is_known_language_name(name):
            st = "wrong_category"
        else:
            st = "hallucinated"
        stats["entry_fp"] += 1
        rows.append(
            FactResult("", f"language_extra:{j}", "languages", st, expected=None, actual=ap, critical=True)
        )
    return rows, stats


def _entry_sim_emp(exp: dict, act: dict) -> float:
    score = 0.0
    # company
    ec, ac = _norm(exp.get("company")), _norm(act.get("company"))
    if ec and ac and (ec == ac or ec in ac or ac in ec):
        score += 0.45
    # position / title
    ep, ap = _norm(exp.get("position")), _norm(act.get("title") or act.get("position"))
    if ep and ap and (ep == ap or ep in ap or ap in ep):
        score += 0.45
    # dates soft
    es, as_ = _norm(exp.get("start_date")), _norm(act.get("start_date"))
    if es and as_ and (es in as_ or as_ in es or _digits(es)[:4] == _digits(as_)[:4]):
        score += 0.05
    ee, ae = _norm(exp.get("end_date")), _norm(act.get("end_date"))
    if ee and ae and (ee in ae or ae in ee or _digits(ee)[:4] == _digits(ae)[:4]):
        score += 0.05
    return score


def _entry_sim_edu(exp: dict, act: dict) -> float:
    score = 0.0
    eq, aq = _norm(exp.get("qualification")), _norm(act.get("qualification"))
    if eq and aq and (eq == aq or eq in aq or aq in eq):
        score += 0.5
    ei, ai = _norm(exp.get("institution")), _norm(act.get("institution"))
    if ei and ai and (ei == ai or ei in ai or ai in ei):
        score += 0.4
    es, as_ = _norm(exp.get("start_date")), _norm(act.get("start_date"))
    if es and as_ and (_digits(es)[:4] == _digits(as_)[:4] or es in as_):
        score += 0.05
    ee, ae = _norm(exp.get("end_date")), _norm(act.get("end_date"))
    if ee and ae and (ee in ae or ae in ee or _digits(ee)[:4] == _digits(ae)[:4]):
        score += 0.05
    return score


def optimal_match(scores: list[list[float]], threshold: float) -> list[tuple[int, int, float]]:
    """Maximize sum of scores with 1-1 matching; n small → permutations."""
    n_exp = len(scores)
    n_act = len(scores[0]) if scores else 0
    if n_exp == 0 or n_act == 0:
        return []
    best: list[tuple[int, int, float]] = []
    best_sum = -1.0
    act_idx = list(range(n_act))
    # If more act than exp, choose combination of act columns
    for chosen in itertools.permutations(act_idx, min(n_exp, n_act)):
        pairs = []
        total = 0.0
        for i, j in enumerate(chosen):
            s = scores[i][j]
            if s >= threshold:
                pairs.append((i, j, s))
                total += s
        if total > best_sum:
            best_sum = total
            best = pairs
    return best


def match_entries(
    expected: list[dict],
    actual: list[dict],
    *,
    sim_fn,
    prefix: str,
    group: str,
    threshold: float = 0.45,
) -> tuple[list[FactResult], dict[str, int]]:
    stats = {
        "entry_detected_tp": 0,
        "entry_fp": 0,
        "entry_fn": 0,
        "entry_fully_correct": 0,
        "field_correct": 0,
        "field_total": 0,
    }
    rows: list[FactResult] = []
    if not expected and not actual:
        return rows, stats
    scores = [[sim_fn(e, a) for a in actual] for e in expected] if expected and actual else []
    pairs = optimal_match(scores, threshold) if scores else []
    matched_exp = {i for i, _, _ in pairs}
    matched_act = {j for _, j, _ in pairs}
    for i, j, s in pairs:
        stats["entry_detected_tp"] += 1
        exp, act = expected[i], actual[j]
        # field-level within match
        if prefix == "employment":
            fields = [
                ("company", exp.get("company"), act.get("company")),
                ("position", exp.get("position"), act.get("title") or act.get("position")),
                ("start_date", exp.get("start_date"), act.get("start_date")),
                ("end_date", exp.get("end_date"), act.get("end_date")),
            ]
        else:
            fields = [
                ("qualification", exp.get("qualification"), act.get("qualification")),
                ("institution", exp.get("institution"), act.get("institution")),
                ("start_date", exp.get("start_date"), act.get("start_date")),
                ("end_date", exp.get("end_date"), act.get("end_date")),
            ]
        all_ok = True
        for fname, ev, av in fields:
            if _empty(ev):
                continue
            stats["field_total"] += 1
            st = scalar_match(ev, av)
            if st == "correct":
                stats["field_correct"] += 1
            else:
                all_ok = False
            rows.append(
                FactResult(
                    "",
                    f"{prefix}:{i}.{fname}",
                    group,
                    st,
                    expected=ev,
                    actual=av,
                    critical=True,
                )
            )
        if all_ok:
            stats["entry_fully_correct"] += 1
        rows.append(
            FactResult(
                "",
                f"{prefix}_entry:{i}",
                group,
                "correct" if s >= threshold else "wrong",
                expected=exp,
                actual=act,
                critical=True,
            )
        )
    for i, exp in enumerate(expected):
        if i not in matched_exp:
            stats["entry_fn"] += 1
            rows.append(
                FactResult("", f"{prefix}_entry:{i}", group, "missing", expected=exp, actual=None, critical=True)
            )
    for j, act in enumerate(actual):
        if j not in matched_act:
            # skip empty
            if _empty(act.get("title") or act.get("position") or act.get("company") or act.get("qualification")):
                continue
            stats["entry_fp"] += 1
            rows.append(
                FactResult("", f"{prefix}_extra:{j}", group, "hallucinated", expected=None, actual=act, critical=True)
            )
    return rows, stats


def match_string_set(
    expected: list[str],
    actual: list[str],
    *,
    prefix: str,
    group: str,
    critical: bool = False,
) -> list[FactResult]:
    rows: list[FactResult] = []
    exp_n = [(_norm(x), x) for x in expected if _norm(x)]
    act_n = [(_norm(x), x) for x in actual if _norm(x)]
    used: set[int] = set()
    for i, (en, eraw) in enumerate(exp_n):
        hit = -1
        for j, (an, _) in enumerate(act_n):
            if j in used:
                continue
            if en == an or en in an or an in en:
                hit = j
                break
        if hit >= 0:
            used.add(hit)
            rows.append(FactResult("", f"{prefix}:{i}", group, "correct", expected=eraw, actual=act_n[hit][1], critical=critical))
        else:
            rows.append(FactResult("", f"{prefix}:{i}", group, "missing", expected=eraw, actual=[a for _, a in act_n], critical=critical))
    for j, (an, araw) in enumerate(act_n):
        if j in used:
            continue
        rows.append(FactResult("", f"{prefix}_extra:{j}", group, "hallucinated", expected=None, actual=araw, critical=critical))
    return rows


def build_evidence_for_doc(fname: str, gt: dict[str, Any], pdf_text: str) -> dict[str, Any]:
    """Project evaluable vs non-evaluable fields for one document."""
    missing = set(gt.get("missing") or [])
    # normalize missing keys
    missing_norm = {m.replace("date_of_birth", "dob") for m in missing}
    evaluable: dict[str, Any] = {}
    non_evaluable: dict[str, str] = {}

    for meta in METADATA_FIELDS:
        if meta in gt:
            non_evaluable[meta] = "test metadata"

    name = gt.get("name") or {}
    addr = gt.get("address") or {}

    def maybe_scalar(key: str, value: Any, evidence_hint: Any = None) -> None:
        if key.split(".")[-1] in missing_norm or key in missing_norm:
            # expected absent — still evaluable as null-check
            evaluable[key] = {
                "expected": None,
                "expect_absent": True,
                "evidence": "annotated missing in GT + verify not invented",
            }
            return
        if _empty(value):
            non_evaluable[key] = "empty expected"
            return
        ev_src = evidence_hint if evidence_hint is not None else value
        if text_contains(ev_src, pdf_text) or (
            isinstance(value, str) and text_contains(value, pdf_text)
        ):
            evaluable[key] = {"expected": value, "evidence": str(ev_src)[:200]}
        else:
            non_evaluable[key] = "expected value not found in PDF text extraction"

    maybe_scalar("name.first_name", name.get("first_name"))
    maybe_scalar("name.last_name", name.get("last_name"))
    maybe_scalar("email", gt.get("email"))
    maybe_scalar("phone", gt.get("phone"))
    maybe_scalar("dob", gt.get("dob"))
    maybe_scalar("address.street", addr.get("street"))
    maybe_scalar("address.house_number", addr.get("house_number"), evidence_hint=addr.get("house_number"))
    # house number often only as part of street line
    if "address.house_number" in non_evaluable and addr.get("house_number") and text_contains(
        f"{addr.get('street')} {addr.get('house_number')}", pdf_text
    ):
        evaluable["address.house_number"] = {
            "expected": addr.get("house_number"),
            "evidence": f"{addr.get('street')} {addr.get('house_number')}",
        }
        non_evaluable.pop("address.house_number", None)
    maybe_scalar("address.postal_code", addr.get("postal_code"))
    maybe_scalar("address.city", addr.get("city"))
    maybe_scalar("address.country", addr.get("country"))

    # languages
    lang_eval = []
    for item in gt.get("languages") or []:
        if isinstance(item, (list, tuple)) and item:
            name_l, level = str(item[0]), str(item[1]) if len(item) > 1 else ""
        else:
            continue
        if text_contains(name_l, pdf_text):
            lang_eval.append([name_l, level])
    if lang_eval:
        evaluable["languages"] = {"expected": lang_eval, "evidence": "language names visible in PDF"}
    else:
        non_evaluable["languages"] = "no visible language evidence"

    # licenses
    lic = [str(x) for x in (gt.get("licenses") or [])]
    lic_vis = [x for x in lic if text_contains(x, pdf_text) or text_contains(f"Führerschein: {x}", pdf_text)]
    if lic_vis or (not lic and "licenses" not in missing_norm):
        if lic and lic_vis:
            evaluable["licenses"] = {"expected": lic_vis, "evidence": "licence class visible"}
        elif not lic:
            evaluable["licenses"] = {"expected": [], "expect_absent": True, "evidence": "no licence expected"}
        else:
            non_evaluable["licenses"] = "licence values not visible in PDF text"
    else:
        non_evaluable["licenses"] = "no licence evidence"

    for key, items, name_keys in (
        ("education", gt.get("education") or [], ("qualification", "institution")),
        ("employment", gt.get("employment") or [], ("company", "position")),
    ):
        kept = []
        for ent in items:
            if not isinstance(ent, dict):
                continue
            blob = " ".join(str(ent.get(k) or "") for k in name_keys)
            if text_contains(ent.get(name_keys[0]), pdf_text) or text_contains(ent.get(name_keys[1]), pdf_text) or text_contains(blob, pdf_text):
                kept.append(ent)
        if kept:
            evaluable[key] = {"expected": kept, "evidence": f"{len(kept)} entries with PDF evidence"}
        elif items:
            non_evaluable[key] = "entries not visible in PDF text extraction"
        else:
            evaluable[key] = {"expected": [], "expect_absent": True, "evidence": "empty list"}

    for key in ("skills", "software", "certificates"):
        raw = gt.get(key) or []
        items = []
        for x in raw:
            if isinstance(x, dict):
                val = x.get("name") or x.get("title") or ""
            else:
                val = str(x)
            if val and text_contains(val, pdf_text):
                items.append(val)
        if items:
            evaluable[key] = {"expected": items, "evidence": "items visible in PDF"}
        elif raw:
            non_evaluable[key] = "listed items not found in PDF text"
        else:
            evaluable[key] = {"expected": [], "expect_absent": True, "evidence": "empty"}

    # target_role — only with explicit label evidence
    role = gt.get("target_role") or ""
    if TARGET_ROLE_LABEL.search(pdf_text) and role and text_contains(role, pdf_text):
        evaluable["target_role"] = {
            "expected": role,
            "evidence": "explicit target-role label + value in PDF",
            "target_role_evaluable": True,
        }
    else:
        non_evaluable["target_role"] = (
            "No explicit target-role evidence in PDF"
            if not TARGET_ROLE_LABEL.search(pdf_text)
            else "label present but value not clearly evidenced"
        )

    return {
        "filename": fname,
        "evaluable_fields": evaluable,
        "non_evaluable_fields": non_evaluable,
        "target_role_evaluable": "target_role" in evaluable,
        "reason": non_evaluable.get("target_role", ""),
    }


def evaluate_doc_v2(
    fname: str,
    gt: dict[str, Any],
    pred: dict[str, Any] | None,
    evidence: dict[str, Any],
) -> list[FactResult]:
    pv = pred_view(pred)
    ev = evidence.get("evaluable_fields") or {}
    rows: list[FactResult] = []

    def add_scalar(key: str, group: str, actual: Any, *, kind: str = "text", critical: bool = True) -> None:
        if key not in ev:
            return
        spec = ev[key]
        expected = spec.get("expected")
        if spec.get("expect_absent"):
            st = "correct" if _empty(actual) else "hallucinated"
        else:
            st = scalar_match(expected, actual, kind=kind)
        rows.append(
            FactResult(fname, key, group, st, expected=expected, actual=actual, critical=critical)
        )

    add_scalar("name.first_name", "personal", pv["first_name"])
    add_scalar("name.last_name", "personal", pv["last_name"])
    add_scalar("email", "contact", pv["email"], kind="email")
    add_scalar("phone", "contact", pv["phone"], kind="phone")
    add_scalar("dob", "personal", pv["dob"])
    add_scalar("address.street", "address", pv["street"])
    if "address.house_number" in ev:
        exp_hn = ev["address.house_number"].get("expected")
        act_hn = pv["house_number"] or ""
        if _empty(act_hn) and exp_hn and str(exp_hn) in str(pv["street"]):
            act_hn = str(exp_hn)
        if ev["address.house_number"].get("expect_absent"):
            st = "correct" if _empty(act_hn) else "hallucinated"
        else:
            st = scalar_match(exp_hn, act_hn)
        rows.append(
            FactResult(fname, "address.house_number", "address", st, expected=exp_hn, actual=act_hn, critical=True)
        )
    add_scalar("address.postal_code", "address", pv["postal_code"])
    add_scalar("address.city", "address", pv["city"])
    add_scalar("address.country", "address", pv["country"], kind="country")

    if "languages" in ev:
        lang_rows, _ = match_language_pairs(ev["languages"]["expected"], pv["languages"])
        for r in lang_rows:
            r.document = fname
            rows.append(r)

    if "licenses" in ev:
        exp = ev["licenses"].get("expected") or []
        if ev["licenses"].get("expect_absent"):
            st = "correct" if _empty(pv["licenses"]) else "hallucinated"
            rows.append(FactResult(fname, "licenses", "licenses", st, expected=[], actual=pv["licenses"], critical=True))
        else:
            act_tokens = re.findall(r"\b[A-Z]{1,3}\d?[E]?\b", str(pv["licenses"]).upper()) or [
                t for t in re.split(r"[\s,;/]+", str(pv["licenses"]).upper()) if t
            ]
            rows.extend(
                match_string_set([str(x).upper() for x in exp], act_tokens, prefix="license", group="licenses", critical=True)
            )
            for r in rows:
                if r.document == "":
                    r.document = fname

    if "education" in ev:
        exp = ev["education"].get("expected") or []
        if ev["education"].get("expect_absent"):
            st = "correct" if not pv["education"] else "hallucinated"
            rows.append(FactResult(fname, "education", "education", st, expected=[], actual=pv["education"], critical=True))
        else:
            erows, _ = match_entries(exp, pv["education"], sim_fn=_entry_sim_edu, prefix="education", group="education")
            for r in erows:
                r.document = fname
                rows.append(r)

    if "employment" in ev:
        exp = ev["employment"].get("expected") or []
        if ev["employment"].get("expect_absent"):
            st = "correct" if not pv["employment"] else "hallucinated"
            rows.append(FactResult(fname, "employment", "employment", st, expected=[], actual=pv["employment"], critical=True))
        else:
            erows, _ = match_entries(exp, pv["employment"], sim_fn=_entry_sim_emp, prefix="employment", group="employment")
            for r in erows:
                r.document = fname
                rows.append(r)

    for key, group, act_key in (
        ("skills", "skills", "skills"),
        ("software", "software", "software"),
        ("certificates", "certificates", "certificates"),
    ):
        if key not in ev:
            continue
        exp = ev[key].get("expected") or []
        if ev[key].get("expect_absent"):
            act = pv[act_key]
            if key == "certificates":
                act_vals = [c.get("name") if isinstance(c, dict) else str(c) for c in act]
            else:
                act_vals = [str(x) for x in act]
            st = "correct" if not any(_norm(x) for x in act_vals) else "hallucinated"
            rows.append(FactResult(fname, key, group, st, expected=[], actual=act_vals, critical=False))
            continue
        if key == "certificates":
            act_vals = [c.get("name") if isinstance(c, dict) else str(c) for c in pv[act_key]]
        else:
            act_vals = [str(x) for x in pv[act_key]]
        srows = match_string_set([str(x) for x in exp], act_vals, prefix=key[:-1] if key.endswith("s") else key, group=group, critical=False)
        for r in srows:
            r.document = fname
            rows.append(r)

    # target_role only if evaluable — as optional extraction (not trap-as-employment)
    if "target_role" in ev:
        exp = ev["target_role"]["expected"]
        act = pv["target_role"]
        st = scalar_match(exp, act)
        rows.append(FactResult(fname, "target_role", "career_intent", st, expected=exp, actual=act, critical=False))
        # Additionally: if explicit Berufswunsch, must not ONLY appear as fabricated employment without company
        # (soft check — optional). Skip trap that punished all 100 docs.

    # Ensure all rows have document
    for r in rows:
        if not r.document:
            r.document = fname
    return rows


def aggregate_v2(rows: list[FactResult]) -> dict[str, Any]:
    scored = [r for r in rows if r.status != "skipped"]
    n = len(scored) or 1
    counts: dict[str, int] = defaultdict(int)
    for r in scored:
        counts[r.status] += 1
    tp = counts["correct"]
    fp = counts["hallucinated"] + counts["wrong"] + counts["wrong_category"]
    fn = counts["missing"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    by_group: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in scored:
        by_group[r.group][r.status] += 1
    return {
        "field_total": len(scored),
        "counts": dict(counts),
        "field_accuracy": tp / n,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "hallucination_rate": counts["hallucinated"] / n,
        "missing_field_rate": counts["missing"] / n,
        "wrong_category_rate": counts["wrong_category"] / n,
        "false_positive_rate": fp / n,
        "by_group": {g: dict(c) for g, c in by_group.items()},
    }


def perfect_document(rows: list[FactResult], *, core_only: bool = False) -> bool:
    for r in rows:
        if r.status == "skipped":
            continue
        if core_only and r.group in {"career_intent"}:
            continue
        if r.status != "correct":
            return False
    return True

#!/usr/bin/env python3
"""Personaler T02.09: verdict *suggestions* for CV-import benchmark sessions.

Reads one or more ``session.json`` files written by the Performance-Optimizer
harness (``thinkpad_cv_bench.py``, schema ``kk-cv-speed-bench/1``) and suggests
an HR verdict per model and CV of ``SMOKE_DE_EN_10``:

* ``Interview-ready``: evidence-eligible run, readable product extract, no
  finding below.
* ``Papierkorb``: invented certificate / licence / employer, ``invented_native``,
  ``native_dropped`` or any other deviation from the Sollwerte sheet.
* ``Blockiert``: no run, failed run, unreadable/missing extract, a check that
  cannot be made (UNSICHER), user path in the data, or a session that is not
  evidence-eligible (``evidence_eligible`` not the bool ``True``, any recorded
  reason, ``native_scrub`` not on, power state inconsistent / aborted).
* ``anderer Harness``: ``harness_sha256`` differs from the expected hash; the
  session is not judged at all.

The suggestion is never the verdict: the final verdict stays with the
Personaler (docs/personaler/ABNAHME_CHECKLISTE.md). Gold
(``tests/fixtures/cv_corpus/expected_results.json``) and the Sollwerte sheet are
only read. Synthetic CVs only.

Usage:
  python scripts/personaler_t0209_verdict.py RUN_DIR/session.json [...] \\
      --harness-sha256 <64 hex> [--out verdict.md]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.privacy_scan import FORBIDDEN, _matches
from scripts.run_cv_corpus import native_language_fails
from scripts.run_cv_sollwerte_corpus import (
    SOLL,
    _parse_beruf,
    _split_pipe_list,
    parse_sollwerte,
)
from scripts.run_cv_sollwerte_corpus import (
    evaluate as sollwerte_evaluate,
)

EXPECTED_PATH = ROOT / "tests" / "fixtures" / "cv_corpus" / "expected_results.json"
SMOKE_MANIFEST = ROOT / "artifacts" / "cv_parser_replacement" / "SMOKE_DE_EN_10_MANIFEST.json"

INTERVIEW_READY = "Interview-ready"
PAPIERKORB = "Papierkorb"
BLOCKIERT = "Blockiert"
OTHER_HARNESS = "anderer Harness"

ALL_CVS = "alle"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_MISSING = object()
_NATIVE_KINDS = ("native_dropped", "invented_native")


# ------------------------------------------------------------------ gold


def smoke_cvs() -> list[str]:
    manifest = json.loads(SMOKE_MANIFEST.read_text(encoding="utf-8"))
    return [Path(d["path"]).name for d in manifest["documents"]]


def load_gold() -> dict[str, dict[str, Any]]:
    """{cv: {"json": expected_results entry, "soll": Sollwerte block}} (read only)."""
    exp = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))["documents"]
    soll = parse_sollwerte(SOLL)
    return {cv: {"json": exp.get(cv), "soll": soll.get(cv)} for cv in smoke_cvs()}


def _key(s: str) -> str:
    return re.sub(r"[^0-9a-zäöüß]+", "", (s or "").lower())


def _known(got: str, gold: list[str]) -> bool:
    g = _key(got)
    if not g:
        return True  # empty value invents nothing
    for want in gold:
        w = _key(want)
        if w and (w in g or (len(g) >= 4 and g in w)):
            return True
    return False


def gold_certificates(soll: dict) -> list[str] | None:
    n = int(soll.get("ZERTIFIKATE/WEITERBILDUNGEN_ANZAHL") or 0)
    names = [
        (soll.get(f"ZERTIFIKAT_{i}") or "").split("|")[0].strip()
        for i in range(1, n + 1)
        if soll.get(f"ZERTIFIKAT_{i}")
    ]
    names += _split_pipe_list(soll.get("ZERTIFIKATE/WEITERBILDUNGEN") or "")
    if n > 0 and not names:
        return None  # only a counter: cannot tell invented from listed
    return names


def gold_licences(soll: dict) -> list[str] | None:
    n = int(soll.get("FUEHRERSCHEINE_ANZAHL") or 0)
    codes = [(soll.get(f"FUEHRERSCHEIN_{i}") or "").strip().upper() for i in range(1, n + 1)]
    codes = [c for c in codes if c]
    if len(codes) != n:
        return None
    return codes


def gold_employers(soll: dict) -> list[str] | None:
    n = int(soll.get("BERUFSERFAHRUNG_ANZAHL") or 0)
    out: list[str] = []
    for i in range(1, n + 1):
        company = _parse_beruf(soll.get(f"BERUF_{i}") or "")["company"]
        if not company:
            return None
        out.append(company)
        out.append(company.split(",")[0])
    return out


# ------------------------------------------------------------------ privacy


def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, val in obj.items():
            yield str(k)
            yield from _strings(val)
    elif isinstance(obj, (list, tuple)):
        for val in obj:
            yield from _strings(val)


def user_path_hits(obj: Any, raw_text: str = "") -> list[str]:
    """Rule names of scripts/privacy_scan.FORBIDDEN that match any string."""
    hits: list[str] = []
    texts = list(_strings(obj))
    if raw_text:
        texts.append(raw_text)
    for name, rx in FORBIDDEN:
        if any(_matches(rx, t) for t in texts):
            hits.append(name)
    return hits


# ------------------------------------------------------------------ session gates


def evidence_problems(doc: dict) -> list[str]:
    probs: list[str] = []
    val = doc.get("evidence_eligible", _MISSING)
    if val is _MISSING:
        probs.append("evidence_eligible fehlt")
    elif not isinstance(val, bool):
        probs.append(f"evidence_eligible={val!r} ist kein bool")
    elif val is not True:
        probs.append("evidence_eligible=False")
    for key in ("evidence_ineligible_reasons", "evidence_reasons"):
        if key not in doc or doc[key] is None:
            continue
        raw = doc[key]
        if not isinstance(raw, list):
            probs.append(f"{key}={raw!r} ist keine Liste")
        elif raw:
            probs.append(f"{key}={','.join(str(r) for r in raw)}")
    ns = doc.get("native_scrub", _MISSING)
    if ns is _MISSING:
        probs.append("native_scrub fehlt")
    elif not (isinstance(ns, dict) and ns.get("enabled") is True):
        probs.append(f"native_scrub nicht an ({ns!r})")
    if doc.get("power_state_consistent") is False:
        probs.append("power_state_consistent=False")
    if doc.get("aborted"):
        probs.append("Session abgebrochen")
    return probs


def model_label(doc: dict) -> str:
    model = doc.get("model") if isinstance(doc.get("model"), dict) else {}
    name = re.split(r"[\\/]", str(model.get("path") or "?"))[-1]
    sha = str(model.get("sha256") or "")[:12]
    label = doc.get("label") or ""
    out = name + (f" sha256:{sha}" if sha else "")
    return out + (f" [{label}]" if label else "")


# ------------------------------------------------------------------ per CV


def _row(model: str, cv: str, verdict: str, reason: str, session: str, **extra) -> dict:
    row = {
        "model": model,
        "cv": cv,
        "verdict": verdict,
        "reason": reason,
        "session": session,
        "native_dropped": [],
        "invented_native": [],
        "invented": [],
        "unsicher": [],
    }
    row.update(extra)
    return row


def _load_extract(session_dir: Path, run: dict) -> tuple[dict | None, str, str]:
    """(parsed, raw_text, problem)."""
    rel = (run.get("files") or {}).get("parsed")
    if not rel:
        return None, "", "files.parsed fehlt"
    base = session_dir.resolve()
    path = (base / str(rel)).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        return None, "", f"Extraktpfad außerhalb des Session-Ordners ({rel})"
    if not path.is_file():
        return None, "", f"Extrakt nicht vorhanden ({rel})"
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "", f"Extrakt nicht lesbar ({type(exc).__name__})"
    if not isinstance(parsed, dict):
        return None, raw, "Extrakt ist kein JSON-Objekt"
    return parsed, raw, ""


def _native_from_fails(fails: list[str]) -> tuple[list[str], list[str]]:
    dropped = [f.rsplit(":", 1)[0] for f in fails if f.endswith(":native_dropped")]
    invented = [f.rsplit(":", 1)[0] for f in fails if f.endswith(":invented_native")]
    return dropped, invented


def _corpus_eval_findings(run: dict) -> tuple[list[str], list[str], list[str]]:
    """native_dropped / invented_native / invented licences from the run's own corpus_eval."""
    ce = run.get("corpus_eval") if isinstance(run.get("corpus_eval"), dict) else {}
    lang = str(ce.get("languages") or "")
    inner = lang[5:-1] if lang.startswith("FAIL(") and lang.endswith(")") else ""
    parts = [p.strip() for p in inner.split(";") if p.strip()]
    dropped, inv_native = _native_from_fails(parts)
    lic = str(ce.get("licenses") or "")
    inv_lic = re.findall(r"(?:invented|extra_cefr):([^;)]+)", lic)
    return dropped, inv_native, [f"Lizenz {x.strip()}" for x in inv_lic]


def judge_run(session_dir: Path, run: dict, gold: dict, mode: str) -> dict:
    out = {"papier": [], "blocked": [], "unsicher": [], "native_dropped": [], "invented_native": [], "invented": []}
    if run.get("ok") is not True:
        err = run.get("error") or {}
        out["blocked"].append(f"Lauf fehlgeschlagen ({err.get('type')}/{err.get('code')})")
        return out
    parsed, raw, problem = _load_extract(session_dir, run)
    if parsed is not None:
        hits = user_path_hits(parsed, raw)
        if hits:
            out["blocked"].append(f"Nutzerpfad im Extrakt ({','.join(hits)})")
            return out
    if parsed is None or parsed.get("_mode") == "llm" or mode not in ("import", None):
        why = problem or "Modus llm, kein Produkt-Extrakt"
        out["unsicher"].append(
            f"UNSICHER: {why}; Muttersprache, erfundene Zertifikate/Lizenzen/Arbeitgeber nicht prüfbar"
        )
        dropped, inv_native, inv_lic = _corpus_eval_findings(run)
        out["native_dropped"] += dropped
        out["invented_native"] += inv_native
        out["invented"] += inv_lic
        if dropped or inv_native or inv_lic:
            out["papier"].append("laut corpus_eval des Laufs")
        return out

    exp_json, soll = gold.get("json"), gold.get("soll")
    if not exp_json or not soll:
        out["blocked"].append("Gold fehlt für diesen CV")
        return out

    langs = [g for g in (parsed.get("languages") or []) if isinstance(g, dict)]
    if "native_languages" in exp_json:
        dropped, inv_native = _native_from_fails(native_language_fails(langs, exp_json))
        out["native_dropped"] += dropped
        out["invented_native"] += inv_native
    else:
        out["unsicher"].append("UNSICHER: Gold ohne native_languages")

    certs = gold_certificates(soll)
    if certs is None:
        out["unsicher"].append("UNSICHER: Zertifikate im Gold nur gezählt")
    else:
        for c in parsed.get("certificates") or []:
            name = c.get("name") if isinstance(c, dict) else str(c)
            if not _known(str(name or ""), certs):
                out["invented"].append(f"Zertifikat {name}")

    lic = gold_licences(soll)
    if lic is None:
        out["unsicher"].append("UNSICHER: Führerscheine im Gold unvollständig")
    else:
        from core.cv_parser import driving_classes_for_display

        for code in driving_classes_for_display(parsed.get("driving_license")):
            if str(code).upper() not in lic:
                out["invented"].append(f"Lizenz {code}")

    employers = gold_employers(soll)
    if employers is None:
        out["unsicher"].append("UNSICHER: Arbeitgeber im Gold unvollständig")
    else:
        for w in parsed.get("work_experience") or []:
            company = str((w or {}).get("company") or "") if isinstance(w, dict) else ""
            if not _known(company, employers):
                out["invented"].append(f"Arbeitgeber {company}")

    for f in sollwerte_evaluate(parsed, soll):
        if f.get("kind") in _NATIVE_KINDS:
            continue
        out["papier"].append(f"Sollwert-Abweichung {f.get('field')}({f.get('kind')})")
    return out


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def judge_cv(session_dir: Path, runs: list[dict], gold: dict, mode: str) -> dict:
    agg = {"papier": [], "blocked": [], "unsicher": [], "native_dropped": [], "invented_native": [], "invented": []}
    for run in runs:
        res = judge_run(session_dir, run, gold, mode)
        for k in agg:
            agg[k] += res[k]
    agg = {k: _dedupe(v) for k, v in agg.items()}
    shas = {r.get("parsed_sha256") for r in runs if r.get("ok") is True}
    if len(shas) > 1:
        agg["unsicher"].append(f"Hinweis: Extrakte je Lauf verschieden ({len(shas)} Varianten)")
    hard = (
        [f"native_dropped: {', '.join(agg['native_dropped'])}"] * bool(agg["native_dropped"])
        + [f"invented_native: {', '.join(agg['invented_native'])}"] * bool(agg["invented_native"])
        + [f"erfunden: {', '.join(agg['invented'])}"] * bool(agg["invented"])
        + agg["papier"]
    )
    if hard:
        verdict, reasons = PAPIERKORB, hard + agg["blocked"] + agg["unsicher"]
    elif agg["blocked"] or [u for u in agg["unsicher"] if u.startswith("UNSICHER")]:
        verdict, reasons = BLOCKIERT, agg["blocked"] + agg["unsicher"]
    else:
        verdict = INTERVIEW_READY
        reasons = [f"{len(runs)} Lauf/Läufe: keine Erfindung, Muttersprache und Sollwerte ok"] + agg["unsicher"]
    return {
        "verdict": verdict,
        "reason": "; ".join(reasons),
        "native_dropped": agg["native_dropped"],
        "invented_native": agg["invented_native"],
        "invented": agg["invented"],
        "unsicher": agg["unsicher"],
    }


def judge_session(path: Path, expected_harness_sha256: str, gold: dict | None = None) -> list[dict]:
    path = Path(path)
    sname = path.parent.name + "/" + path.name
    try:
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise TypeError("kein JSON-Objekt")
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
        return [_row(sname, ALL_CVS, BLOCKIERT, f"Session nicht lesbar ({type(exc).__name__})", sname)]
    model = model_label(doc)
    hits = user_path_hits(doc, raw)
    if hits:
        return [_row(model, ALL_CVS, BLOCKIERT, f"Nutzerpfad in der Session ({','.join(hits)})", sname)]
    got = str(doc.get("harness_sha256") or "").lower()
    if got != expected_harness_sha256.lower():
        return [_row(model, ALL_CVS, OTHER_HARNESS,
                     f"harness_sha256 {got[:12] or 'fehlt'} != erwartet {expected_harness_sha256[:12]}; nicht bewertet",
                     sname)]
    probs = evidence_problems(doc)
    if probs:
        return [_row(model, ALL_CVS, BLOCKIERT, "nicht evidence-eligible: " + "; ".join(probs), sname)]

    gold = gold if gold is not None else load_gold()
    runs = [r for r in doc.get("runs") or [] if isinstance(r, dict)]
    measured = [
        r for r in runs
        if r.get("kind", "measured") == "measured" and not str(r.get("tag") or "").startswith("warmup")
    ]
    rows: list[dict] = []
    for cv in gold:
        mine = [r for r in measured if Path(str(r.get("cv") or "")).name == cv]
        if not mine:
            rows.append(_row(model, cv, BLOCKIERT, "kein Lauf für diesen CV in der Session", sname))
            continue
        res = judge_cv(path.parent, mine, gold[cv], doc.get("mode"))
        rows.append(_row(model, cv, res.pop("verdict"), res.pop("reason"), sname, **res))
    return rows


# ------------------------------------------------------------------ output


def _cell(s: Any) -> str:
    if isinstance(s, list):
        s = ", ".join(str(x) for x in s) or "–"
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_markdown(rows: list[dict], expected_harness_sha256: str) -> str:
    lines = [
        "# T02.09 – Verdict-Vorschläge (SMOKE_DE_EN_10)",
        "",
        (
            "Nur Vorschläge. Das Urteil (Interview-ready / Papierkorb / Blockiert) trifft der Personaler "
            "nach Sichtung von Quelle und Extrakt (docs/personaler/ABNAHME_CHECKLISTE.md)."
        ),
        f"Erwarteter Harness: `{expected_harness_sha256.lower()}`. Gold und Sollwerte unverändert gelesen.",
        "",
        "| Modell | CV | Vorschlag | Begründung | native_dropped | invented_native | erfunden (Zert./Lizenz/Arbeitgeber) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| " + " | ".join(
                _cell(x) for x in (r["model"], r["cv"], r["verdict"], r["reason"],
                                    r["native_dropped"], r["invented_native"], r["invented"])
            ) + " |"
        )
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    lines += ["", "Zählung: " + ", ".join(f"{k} {v}" for k, v in counts.items())]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sessions", nargs="+", type=Path, help="session.json of each run directory")
    ap.add_argument("--harness-sha256", required=True, help="expected sha256 of thinkpad_cv_bench.py")
    ap.add_argument("--out", type=Path, default=None, help="also write the markdown here")
    args = ap.parse_args(argv)
    if not _SHA_RE.match(args.harness_sha256):
        ap.error("--harness-sha256 must be 64 hex characters")
    gold = load_gold()
    rows: list[dict] = []
    for p in args.sessions:
        rows += judge_session(p, args.harness_sha256, gold)
    md = render_markdown(rows, args.harness_sha256)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

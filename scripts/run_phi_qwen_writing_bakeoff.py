#!/usr/bin/env python3
"""Short Phi vs Qwen3.5-4B Anschreiben bakeoff on identical verified profiles.

Uses SYSTEM_PHI_WRITE + validate_writing for BOTH models (same scaffolding).
KNOWN fixtures — not a blind writing holdout. No DET.

Outputs anonymized letter texts for human review + safety/grounding flags.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "artifacts" / "one_model_dual_use" / "writing_bakeoff"
PHI = Path(
    os.environ.get(
        "KARRIEREKRAKE_PHI_CV_MODEL",
        "/tmp/karrierekrake-models/phi4-mini/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
    )
)
QWEN = Path(
    os.environ.get(
        "KARRIEREKRAKE_CV_LLM_MODEL",
        "/tmp/karrierekrake-models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf",
    )
)

# Four fixed DE/EN cases: confirmed profile + job (no model extract involved).
CASES: list[dict[str, Any]] = [
    {
        "id": "DE_CS_01",
        "lang": "de",
        "profile": {
            "full_name": "Mara König",
            "skills": ["Kundenservice", "KPI-Reporting", "Prozessoptimierung"],
            "experience_titles": ["Teamkoordinatorin Kundenservice", "Sachbearbeiterin Auftragsmanagement"],
            "education": ["Kauffrau für Büromanagement (IHK)"],
            "languages": ["Deutsch C2", "Englisch C1"],
            "notes": "Wohnort Münster. Keine Führungsspanne außer 8-köpfiges Team Kundenservice.",
        },
        "job": {
            "title": "Teamleitung Kundenservice",
            "company": "Beispiel Handel AG",
            "description": (
                "Leitung eines Kundenservice-Teams, Reklamationsmanagement, "
                "Reporting an die Geschäftsleitung, Deutsch und Englisch."
            ),
        },
    },
    {
        "id": "DE_IT_02",
        "lang": "de",
        "profile": {
            "full_name": "Jonas Falkenberg",
            "skills": ["Python", "SQL", "Prozessanalyse"],
            "experience_titles": ["Business Analyst", "Werkstudent Controlling"],
            "education": ["B.Sc. Wirtschaftsinformatik"],
            "languages": ["Deutsch Muttersprache", "Englisch B2"],
            "notes": "Keine SAP-Kenntnisse im Profil. Kein Führerschein erwähnt.",
        },
        "job": {
            "title": "Junior Business Analyst",
            "company": "Nordlicht Digital GmbH",
            "description": "Anforderungsanalyse, SQL-Auswertungen, Abstimmung mit Fachbereichen.",
        },
    },
    {
        "id": "EN_CS_01",
        "lang": "en",
        "profile": {
            "full_name": "Emily Carter",
            "skills": ["Customer Support", "CRM", "Escalation Handling"],
            "experience_titles": ["Customer Support Specialist", "Retail Associate"],
            "education": ["BA Communications"],
            "languages": ["English native", "German A2"],
            "notes": "No people-management role. No AWS certification.",
        },
        "job": {
            "title": "Customer Success Associate",
            "company": "Riverlight Softwares Ltd",
            "description": "Own customer onboarding, handle escalations, work with CRM tools, English required.",
        },
    },
    {
        "id": "EN_ENG_02",
        "lang": "en",
        "profile": {
            "full_name": "Daniel Okonkwo",
            "skills": ["Java", "Spring", "REST APIs"],
            "experience_titles": ["Software Engineer", "Intern Developer"],
            "education": ["MSc Computer Science"],
            "languages": ["English C2", "German B1"],
            "notes": "No Kubernetes experience in profile. No team-lead title.",
        },
        "job": {
            "title": "Backend Engineer",
            "company": "Harbor Systems GmbH",
            "description": "Design REST services in Java/Spring, collaborate with product, German helpful.",
        },
    },
]


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _chat(model_path: Path, messages: list[dict[str, str]], *, max_tokens: int = 700) -> str:
    from llama_cpp import Llama

    llm = Llama(
        model_path=str(model_path),
        n_ctx=4096,
        n_threads=max(2, (os.cpu_count() or 2)),
        n_batch=512,
        verbose=False,
    )
    try:
        out = llm.create_chat_completion(
            messages=messages,
            temperature=0.4,
            max_tokens=max_tokens,
        )
        return str(out["choices"][0]["message"]["content"] or "")
    finally:
        del llm


def _write_messages(case: dict[str, Any]) -> list[dict[str, str]]:
    from guenther.prompts import SYSTEM_PHI_WRITE, build_layers

    profile = case["profile"]
    job = case["job"]
    trusted = json.dumps(profile, ensure_ascii=False, indent=2)
    untrusted = json.dumps(job, ensure_ascii=False, indent=2)
    layers = build_layers(
        task="write",
        schema_hint='{"cover_letter":"string","notes":"string"}',
        trusted=trusted,
        untrusted=untrusted,
        system_core=SYSTEM_PHI_WRITE,
    )
    lang = case["lang"]
    extra = (
        "Schreibe ein kurzes Anschreiben auf Deutsch (max 180 Wörter). "
        if lang == "de"
        else "Write a short cover letter in English (max 180 words). "
    )
    user = (
        f"{extra}"
        "Use ONLY verified profile facts. Do not invent employers, degrees, tools, "
        "leadership, licences, or metrics. Output plain text letter body only.\n\n"
        f"VERIFIED_PROFILE:\n{trusted}\n\nJOB_POSTING:\n{untrusted}"
    )
    return [
        {"role": "system", "content": layers.system},
        {"role": "user", "content": user},
    ]


def _forbidden_hits(text: str, case: dict[str, Any]) -> list[str]:
    """Heuristic invented-claim scan (same checks for both models)."""
    low = text.lower()
    hits: list[str] = []
    notes = (case["profile"].get("notes") or "").lower()
    probes = [
        ("sap", "sap" in low and "sap" not in notes and "sap" not in json.dumps(case["profile"]).lower()),
        ("kubernetes", "kubernetes" in low or "k8s" in low),
        ("aws", " aws" in low or "amazon web" in low),
        ("führerschein", "führerschein" in low or "driver" in low and "licence" in low),
        ("teamlead", "teamlead" in low.replace(" ", "") or "team lead" in low),
    ]
    # Only flag probes contradicted by notes
    if "keine sap" in notes or "no aws" in notes or "no kubernetes" in notes:
        for name, bad in probes:
            if bad and name in ("sap", "kubernetes", "aws"):
                if name == "sap" and "keine sap" in notes and "sap" in low:
                    hits.append(f"possible_invented:{name}")
                if name == "kubernetes" and "no kubernetes" in notes and ("kubernetes" in low or "k8s" in low):
                    hits.append(f"possible_invented:{name}")
                if name == "aws" and "no aws" in notes and ("aws" in low or "amazon web" in low):
                    hits.append(f"possible_invented:{name}")
    if "kein führerschein" in notes and ("führerschein" in low):
        hits.append("possible_invented:license")
    # company from job must appear or be ok if missing; fake companies
    return hits


def run_model(label: str, model_path: Path) -> dict[str, Any]:
    docs = []
    t_all = time.perf_counter()
    peak0 = _peak_rss_mb()
    for case in CASES:
        print(f"  {label} {case['id']} ...", flush=True)
        t0 = time.perf_counter()
        try:
            text = _chat(model_path, _write_messages(case))
            err = None
        except Exception as exc:  # noqa: BLE001
            text = ""
            err = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - t0
        # validate_writing if available
        safety_notes: list[str] = []
        try:
            from guenther.validation import validate_writing

            vr = validate_writing(
                text,
                profile_blob=json.dumps(case["profile"], ensure_ascii=False),
                job_blob=json.dumps(case["job"], ensure_ascii=False),
            )
            if hasattr(vr, "ok"):
                safety_notes = list(getattr(vr, "notes", None) or getattr(vr, "safety_notes", None) or [])
                if not vr.ok and not safety_notes:
                    safety_notes = ["validate_writing_failed"]
            elif isinstance(vr, dict):
                safety_notes = list(vr.get("notes") or [])
        except Exception as exc:  # noqa: BLE001
            safety_notes = [f"validator_error:{type(exc).__name__}"]
        hits = _forbidden_hits(text, case)
        docs.append(
            {
                "id": case["id"],
                "lang": case["lang"],
                "elapsed_s": elapsed,
                "error": err,
                "chars": len(text),
                "safety_notes": safety_notes,
                "heuristic_invented": hits,
                "letter_anonymized": text.replace(case["profile"]["full_name"], "[NAME]")
                .replace(case["job"]["company"], "[COMPANY]")
                .strip(),
            }
        )
        (OUT / label).mkdir(parents=True, exist_ok=True)
        (OUT / label / f"{case['id']}.txt").write_text(text, encoding="utf-8")
    return {
        "model": label,
        "path": str(model_path),
        "size_mb": model_path.stat().st_size / (1024 * 1024) if model_path.is_file() else None,
        "wall_s": time.perf_counter() - t_all,
        "peak_rss_mb": max(peak0, _peak_rss_mb()),
        "hardware_note": "Agent-VM measurement — not i3/8GB Job Object ship evidence",
        "documents": docs,
        "n_heuristic_invented": sum(1 for d in docs if d["heuristic_invented"]),
        "n_errors": sum(1 for d in docs if d["error"]),
        "avg_s": sum(d["elapsed_s"] for d in docs) / len(docs),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not PHI.is_file() or not QWEN.is_file():
        print("Missing GGUF", PHI, QWEN)
        return 2
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "comparison_type": "KNOWN_WRITING_BAKEOFF_NOT_BLIND",
        "scaffolding": "SYSTEM_PHI_WRITE + validate_writing (same for both)",
        "n_cases": len(CASES),
        "phi": None,
        "qwen": None,
    }
    print("=== PHI write ===", flush=True)
    report["phi"] = run_model("phi", PHI)
    print("=== QWEN write ===", flush=True)
    report["qwen"] = run_model("qwen", QWEN)
    (OUT / "WRITE_BAKEOFF_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "phi_avg_s": report["phi"]["avg_s"],
                "qwen_avg_s": report["qwen"]["avg_s"],
                "phi_invented_cases": report["phi"]["n_heuristic_invented"],
                "qwen_invented_cases": report["qwen"]["n_heuristic_invented"],
                "phi_errors": report["phi"]["n_errors"],
                "qwen_errors": report["qwen"]["n_errors"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Dump interview gold letters for the HR review file.
"""Write ``docs/qa/anschreiben_gold_briefe.md`` from the gold fixtures.

The recorded commit is HEAD at generation time. Run this after the code
commit and commit only the markdown afterwards, so the SHA in the file is
the parent of the dump commit.

    python scripts/dump_cover_gold_letters.py
    python scripts/dump_cover_gold_letters.py --commit <sha>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cover_letter import compose_cover_letter

OUT = ROOT / "docs" / "qa" / "anschreiben_gold_briefe.md"


def _gold_module():
    path = ROOT / "tests" / "test_cover_letter_gold.py"
    spec = importlib.util.spec_from_file_location("cover_letter_gold_dump", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def _fence(text: str) -> str:
    marker = "```"
    while marker in text:
        marker += "`"
    return f"{marker}\n{text}\n{marker}"


def render_clean(commit: str) -> str:
    gold = _gold_module()
    cases = [case for case in gold._load_cases() if case["expected_outcome"] == "interview"]
    cases.sort(key=lambda case: case["id"])
    lines = [
        "# Anschreiben-Gold: erzeugte Briefe",
        "",
        f"Die Briefe wurden auf Commit `{commit}` erzeugt.",
        "Das ist der Stand des Codes, aus dem die Texte kommen.",
        "Der Dump-Commit ändert nur diese Datei; sein Eltern-Commit ist dieser SHA.",
        "",
        "Enthalten ist jeder Gold-Fall mit Ausgang `interview`.",
        "Anzeige (Titel, Firma, Beschreibung) und Profilfakten stehen wörtlich aus der Fixture.",
        "Der Brief ist `compose_cover_letter(...).text`, also der Text,",
        "den `approve_cover_letter` ohne nachträgliche Änderung speichert.",
        "",
    ]
    for case in cases:
        result = compose_cover_letter(gold._job_from_case(case), gold._config_from_case(case))
        if not result.ok or not result.text:
            raise SystemExit(f"{case['id']}: expected a letter, got {result.reason_code!r}")
        job = case["job"]
        facts = json.dumps(case["profile"]["qualifications"], ensure_ascii=False, indent=2) + "\n"
        lines.extend(
            [
                f"## {case['id']}",
                "",
                f"- Fall: `{case['id']}`",
                f"- Commit: `{commit}`",
                "- Ausgang: `interview`",
                "",
                "### Anzeige",
                "",
                f"- Titel: {job['title']}",
                f"- Firma: {job['company']}",
                "",
                "Beschreibung:",
                "",
                _fence(job["description"]),
                "",
                "### Profilfakten",
                "",
                "```json",
                facts.rstrip("\n"),
                "```",
                "",
                "### Brief",
                "",
                _fence(result.text),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", default="", help="SHA to record. Default: git rev-parse HEAD")
    args = parser.parse_args()
    commit = args.commit.strip() or _head()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render_clean(commit), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} commit={commit}")


if __name__ == "__main__":
    main()

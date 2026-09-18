"""Headless smoke: CV A then Replace with CV B (same logic as desktop import)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import ApplicationProfile, QualificationsConfig, save_config, load_config
from core.cv_parser import parse_cv_text, parsed_to_qualifications
from desktop.services.profile_merge import (
    SOURCE_CV,
    apply_personal_updates,
    personal_from_parsed,
    plan_personal_import,
    replace_qualifications,
    sync_application_summaries,
)


def _apply(cv_path: Path, app: ApplicationProfile, quals: QualificationsConfig):
    parsed = parse_cv_text(cv_path.read_text(encoding="utf-8"))
    incoming = parsed_to_qualifications(parsed)
    plan = plan_personal_import(app, personal_from_parsed(parsed), mode="replace")
    apply_personal_updates(app, plan.updates, source=SOURCE_CV, conflicts=plan.conflicts, conflict_choices={})
    quals = replace_qualifications(quals, incoming)
    sync_application_summaries(app, quals, fill_empty=True)
    return app, quals


def main() -> int:
    fixtures = ROOT / "tests" / "fixtures"
    app = ApplicationProfile()
    quals = QualificationsConfig()
    app, quals = _apply(fixtures / "cv_a.txt", app, quals)
    assert app.first_name == "Anna", app.first_name
    assert any(l.language == "Französisch" for l in quals.languages)

    app, quals = _apply(fixtures / "cv_b.txt", app, quals)
    assert app.first_name == "Bruno", app.first_name
    assert app.city == "München", app.city
    assert not any(l.language == "Französisch" for l in quals.languages)
    assert any(l.language == "Spanisch" for l in quals.languages)
    assert not any("DATEV" in s for s in quals.software_values())
    assert any("Python" in s for s in quals.software_values())

    # Persist round-trip like the app would
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "config").mkdir()
        cfg = load_config(
            profile_path=ROOT / "config" / "profile.yaml.example",
            application_path=ROOT / "config" / "application_profile.yaml.example",
            settings_path=ROOT / "config" / "settings.yaml.example",
            root=root,
        )
        cfg.application = app
        cfg.profile.qualifications = quals
        save_config(
            cfg,
            profile_path=root / "config" / "profile.yaml",
            application_path=root / "config" / "application_profile.yaml",
            settings_path=root / "config" / "settings.yaml",
        )
        reloaded = load_config(
            profile_path=root / "config" / "profile.yaml",
            application_path=root / "config" / "application_profile.yaml",
            settings_path=root / "config" / "settings.yaml",
            root=root,
            strip_placeholders=False,
        )
        assert reloaded.application.first_name == "Bruno"
        assert not any(l.language == "Französisch" for l in reloaded.profile.qualifications.languages)

    print("OK: Replace CV A -> CV B cleared previous CV profile data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

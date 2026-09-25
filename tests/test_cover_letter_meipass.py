"""Frozen EXE must resolve bundled cover-letter templates via _MEIPASS."""

from __future__ import annotations

from pathlib import Path

from core.config import SourcedText, empty_app_config
from core.cover_letter import render_cover_letter, resolve_cover_letter_template
from core.models import Job


def test_resolve_template_uses_meipass_when_frozen(tmp_path: Path, monkeypatch) -> None:
    meipass = tmp_path / "_internal"
    bundled = meipass / "templates"
    bundled.mkdir(parents=True)
    (bundled / "cover_letter.txt").write_text(
        "FROZEN_TEMPLATE {job_title} @ {company} — {full_name}\n{skills}\n{experience_sentence}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("core.cover_letter.sys.frozen", True, raising=False)
    monkeypatch.setattr("core.cover_letter.sys._MEIPASS", str(meipass), raising=False)

    # AppData root has no templates/ — only the frozen extract dir does.
    cfg = empty_app_config(root=tmp_path / "appdata")
    cfg.settings.cover_letter_template = "templates/cover_letter.txt"
    cfg.application.first_name = "Alex"
    cfg.application.last_name = "Beispiel"
    cfg.profile.qualifications.skills.append(
        SourcedText(value="Sachbearbeitung", source="manual")
    )

    resolved = resolve_cover_letter_template(cfg)
    assert resolved is not None
    assert resolved == bundled / "cover_letter.txt"

    text = render_cover_letter(
        Job(
            title="Sachbearbeiter",
            company="Nordlicht GmbH",
            description="Sachbearbeitung im Büroalltag und Terminabstimmung.",
        ),
        cfg,
    )
    assert "FROZEN_TEMPLATE" in text
    assert "Sachbearbeiter" in text
    assert "Nordlicht GmbH" in text

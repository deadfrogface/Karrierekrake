from pathlib import Path


def test_static_site_has_no_tracking_or_external_scripts():
    text = (Path(__file__).resolve().parents[1] / "website" / "index.html").read_text(encoding="utf-8")
    assert 'lang="de"' in text
    assert "<main>" in text
    assert "<script" not in text.lower()
    assert "github.com/deadfrogface/Karrierekrake/releases" in text
    assert "Unveröffentlichter Website-Entwurf" in text

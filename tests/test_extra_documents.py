import json
from pathlib import Path

from apply.base import BaseApplier
from core.documents import sendable_extra_documents


class _Input:
    def __init__(self, multiple=False):
        self.multiple = multiple
        self.files = None

    def get_attribute(self, name):
        return "" if (name == "multiple" and self.multiple) else None

    def set_input_files(self, files):
        self.files = files


class _Page:
    def __init__(self, inputs):
        self.inputs = inputs

    def query_selector(self, selector):
        return self.inputs[0]

    def query_selector_all(self, selector):
        return list(self.inputs)


class _Applier(BaseApplier):
    def _do_apply(self, *a, **k):
        raise NotImplementedError

    def _random_pause(self, *a, **k):
        pass


def _files(tmp_path, *names):
    out = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"%PDF-1.4 test")
        out.append(path)
    return out


def test_sendable_documents_respect_role_flag_and_missing_files(tmp_path):
    cv, z1, z2, z3 = _files(tmp_path, "cv.pdf", "z1.pdf", "z2.pdf", "z3.pdf")
    meta = {"cv_variants": [
        {"id": "a", "path": str(cv), "role": "cv"},
        {"id": "b", "path": str(z1), "role": "other", "send": True},
        {"id": "c", "path": str(z2), "role": "other", "send": False},
        {"id": "d", "path": str(tmp_path / "gone.pdf"), "role": "other"},
        {"id": "e", "path": str(z3), "role": "other"},
    ]}
    assert sendable_extra_documents(meta) == [z1, z3]


def test_zeugnisse_go_into_the_same_input_when_it_takes_several_files(tmp_path):
    cv, z1 = _files(tmp_path, "cv.pdf", "z1.pdf")
    box = _Input(multiple=True)
    applier = _Applier(_Page([box]), dry_run=True)
    applier.extra_documents = [z1]
    assert applier._safe_upload(cv, "input[type='file']")
    assert box.files == [str(cv), str(z1)]


def test_zeugnisse_go_into_further_file_inputs_otherwise(tmp_path):
    cv, z1, z2 = _files(tmp_path, "cv.pdf", "z1.pdf", "z2.pdf")
    first, second = _Input(), _Input()
    applier = _Applier(_Page([first, second]), dry_run=True)
    applier.extra_documents = [z1, z2]
    assert applier._safe_upload(cv, "input[type='file']")
    assert first.files == str(cv) and second.files == str(z1)


def test_cv_upload_still_succeeds_without_extras_or_room(tmp_path):
    cv, z1 = _files(tmp_path, "cv.pdf", "z1.pdf")
    only = _Input()
    applier = _Applier(_Page([only]), dry_run=True)
    applier.extra_documents = [z1]
    assert applier._safe_upload(cv, "input[type='file']")
    assert only.files == str(cv)


def test_service_adds_reads_and_removes_a_zeugnis(tmp_path, monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_DATA_DIR", str(tmp_path / "data"))
    from desktop.services import ConfigService

    service = ConfigService()
    cfg = service.load()
    from core.config import ExperienceEntry

    cfg.profile.qualifications.work_experience = [ExperienceEntry(title="Sachbearbeiterin", company="Rheinland Büroservice GmbH")]
    service.save(cfg)
    source = tmp_path / "zeugnis.txt"
    source.write_text(
        "Rheinland Büroservice GmbH\n\nArbeitszeugnis\n\nFrau Beispiel war vom 01.03.2021 bis zum 31.08.2025 als Sachbearbeiterin tätig.\n"
        "Zu ihren Aufgaben gehörten:\n• Prüfung und Buchung von Eingangsrechnungen\n• Kontenabstimmung und Mahnwesen\n• Monatsabschlüsse\n",
        encoding="utf-8")
    entry, changes = service.add_extra_document(source)
    assert entry["kind"] == "zeugnis" and entry["role"] == "other"
    assert any("Aufgabe" in c for c in changes)
    assert len(service.load().profile.qualifications.work_experience[0].responsibilities) == 3
    assert [d["id"] for d in service.extra_documents()] == [entry["id"]]
    service.set_document_send(entry["id"], False)
    assert service.extra_documents()[0]["send"] is False
    stored = Path(entry["path"])
    service.remove_document(entry["id"])
    assert service.extra_documents() == [] and not stored.exists()
    # the CV choice is untouched by other documents
    assert not json.loads((tmp_path / "data" / "meta.json").read_text(encoding="utf-8")).get("active_cv_id")

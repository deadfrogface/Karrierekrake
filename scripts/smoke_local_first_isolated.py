#!/usr/bin/env python3
"""Isolated local-first smoke (empty profile dir) — no Google live calls.

Runs: geo dataset seed, PLZ resolve, Haversine radius, ICS fallback, restart persistence.
Suitable for Linux CI agents; Windows EXE smoke remains on windows-smoke workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="kk-isolated-"))
    data = base / "data"
    cfg_dir = base / "config"
    data.mkdir()
    cfg_dir.mkdir()
    os.environ["KARRIEREKRAKE_GEO_DATA_DIR"] = str(base / "geo_active")
    # Isolate from any host developer profile / LOCALAPPDATA leftovers.
    old_home = os.environ.get("HOME")
    os.environ["LOCALAPPDATA"] = str(base / "LocalAppData")
    os.environ["APPDATA"] = str(base / "AppData")
    # Do not override HOME — breaks git credential insteadOf / gh auth.
    report: dict = {"base": str(base), "steps": []}

    def step(name: str, ok: bool, detail: str = "") -> None:
        report["steps"].append({"name": name, "ok": ok, "detail": detail})
        print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    try:
        from core.geo_dataset import GeoDatasetManager, reset_geo_dataset_manager_for_tests
        from core.geo_resolve import haversine_km, reset_pgeocode_index_for_tests, resolve_postal_pgeocode
        from core.config import AppConfig, LocationConfig, SearchPreferences, SettingsConfig
        from core.database import Database
        from core.location import LocationService, enrich_job_locations
        from core.matcher import apply_distance_scoring, score_job
        from core.models import Job, JobStatus, RemoteType
        from core.hard_filter import distance_exclude
        from integrations.ics_export import build_meetings_ics

        # Gate 6: Erststart — empty user dir, no leftover profile/db.
        step(
            "first_start_empty_profile",
            not (data / "jobs.db").exists() and cfg_dir.is_dir() and not any(cfg_dir.iterdir()),
            str(base),
        )

        reset_geo_dataset_manager_for_tests()
        reset_pgeocode_index_for_tests()

        mgr = GeoDatasetManager(config_root=base)
        info = mgr.ensure_active()
        step("geo_dataset_seed", info.valid, info.version or info.message)

        res = resolve_postal_pgeocode("10115", "DE")
        step("plz_resolve_de", res.ok, res.display_name)

        d = haversine_km(52.52, 13.405, 52.53, 13.41)
        step("haversine", d > 0 and d < 5, f"{d:.3f} km")

        db = Database(data / "jobs.db", recover=False)
        cfg = AppConfig(
            root=base,
            profile=SearchPreferences(
                location=LocationConfig(
                    home_address="10115 Berlin",
                    postal_code="10115",
                    city="Berlin",
                    country="DE",
                    max_distance_km=15,
                    home_latitude=52.52,
                    home_longitude=13.405,
                    home_geocoded_address="10115 Berlin",
                )
            ),
            settings=SettingsConfig(geocoder="local", database_path=str(data / "jobs.db")),
        )
        svc = LocationService(db, cfg)
        near = Job(
            title="Near",
            company="A",
            postal_code="10117",
            city="Berlin",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
        )
        far = Job(
            title="Far",
            company="B",
            postal_code="80331",
            city="München",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
        )
        enrich_job_locations([near, far], svc)
        step("enrich_near", near.distance_km is not None and near.distance_km < 15, str(near.distance_km))
        step(
            "radius_excludes_far",
            distance_exclude(far, cfg) is not None,
            f"far={far.distance_km}",
        )

        # Gate 6: lokale Jobsuche — fachliches Matching vor Radius (kein Netzwerk).
        candidate = Job(
            id="local-near-1",
            source="smoke",
            title="Sachbearbeiter Büro",
            company="Berlin GmbH",
            description="Vollzeit Büro Berlin Mitte",
            postal_code="10117",
            city="Berlin",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            url="https://example.invalid/job/1",
        )
        fachlich = score_job(candidate, cfg, apply_distance=False)
        enrich_job_locations([candidate], svc)
        apply_distance_scoring(candidate, cfg)
        db.upsert_job(candidate)
        stored = db.get_job(candidate.id) if hasattr(db, "get_job") else None
        listed = getattr(db, "list_jobs", lambda **_: [])()
        local_ok = (
            not fachlich.excluded
            and candidate.distance_km is not None
            and candidate.distance_km < 15
            and candidate.status != JobStatus.IGNORED.value
            and (stored is not None or (isinstance(listed, list) and any(getattr(j, "id", None) == candidate.id for j in listed)))
        )
        step(
            "local_job_search",
            local_ok,
            f"score={fachlich.score} dist={candidate.distance_km} status={candidate.status}",
        )

        ics1 = build_meetings_ics(
            [{"uid": "kk-smoke-1@local", "title": "Interview", "scheduled_at": "2026-10-01T10:00:00+02:00", "end": "2026-10-01T11:00:00+02:00"}]
        )
        ics2 = build_meetings_ics(
            [{"uid": "kk-smoke-1@local", "title": "Interview", "scheduled_at": "2026-10-01T10:00:00+02:00", "end": "2026-10-01T11:00:00+02:00"}]
        )
        step("ics_valid", "BEGIN:VCALENDAR" in ics1 and "UID:kk-smoke-1@local" in ics1)
        step("ics_stable_uid", "UID:kk-smoke-1@local" in ics2)

        # Restart: new LocationService must reuse geo dataset
        reset_pgeocode_index_for_tests()
        mgr2 = GeoDatasetManager(config_root=base)
        info2 = mgr2.ensure_active()
        step("restart_geo", info2.valid and info2.version == info.version, info2.version)

        # No maps imports
        import importlib
        try:
            importlib.import_module("integrations.maps")
            step("no_maps_module", False, "maps importable")
        except ModuleNotFoundError:
            step("no_maps_module", True)

    except Exception as exc:
        step("exception", False, f"{type(exc).__name__}: {exc}")
        report["ok"] = False
        (base / "smoke_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    report["ok"] = all(s["ok"] for s in report["steps"])
    out = Path("/opt/cursor/artifacts") if Path("/opt/cursor/artifacts").is_dir() else base
    out.mkdir(parents=True, exist_ok=True)
    path = out / "local_first_isolated_smoke.json"
    payload = json.dumps(report, indent=2)
    # Write via /tmp first — artifacts FS can return EAGAIN under load.
    tmp = Path(tempfile.gettempdir()) / "local_first_isolated_smoke.json"
    tmp.write_text(payload, encoding="utf-8")
    try:
        path.write_text(payload, encoding="utf-8")
    except OSError:
        try:
            shutil.copyfile(tmp, path)
        except OSError:
            path = tmp
    print(f"report={path}")
    # Cleanup isolated dir except leave report
    shutil.rmtree(base, ignore_errors=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

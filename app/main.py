"""Main search / apply pipeline."""

from __future__ import annotations

import argparse
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

from apply.detector import ATSDetector, ats_coverage_bucket
from apply.manager import ApplicationManager
from core.known_jobs import should_suppress_as_new
from browser.browser_manager import BrowserManager
from core.cancel import cancel_active_searches, register_executor, unregister_executor
from core.config import AppConfig, load_config
from core.database import Database
from core.deduplicator import deduplicate
from core.location import LocationService, enrich_job_locations, _city_from_address
from core.logging import RunLogger
from core.matcher import apply_distance_scoring, score_job
from core.models import JobStatus, OperatingMode
from core.source_health import SourceHealthStatus
from search.base import SearchQuery
from search.registry import build_sources

logger = logging.getLogger("karrierekrake")

# Hard ceiling per job board so one hung source cannot freeze the whole run.
SOURCE_SEARCH_TIMEOUT_S = 120

# Executor cancel registry lives in core.cancel (shared with BA detail pools).


def _search_location(home_address: str) -> str:
    """Prefer a single city for BA/Indeed queries (same helper as geocode)."""
    return _city_from_address(home_address)


def discovery_search_titles(config: AppConfig) -> list[str]:
    """Mode A: derive search keywords from profile experience / skills.

    Desired titles are optional — empty desired list still yields discovery
    queries from CV-backed experience titles and strong software tokens.
    """
    from core.job_title_suggestions import suggest_job_titles

    quals = config.profile.qualifications
    parsed = {
        "work_experience": [
            {
                "title": e.title,
                "company": e.company,
                "responsibilities": list(e.responsibilities or []),
            }
            for e in (quals.work_experience or [])
        ],
        "education": [
            {"qualification": e.qualification, "institution": e.institution}
            for e in (quals.education or [])
        ],
        "skills": quals.skill_values(),
        "software": quals.software_values(),
        "certificates": [c.name for c in (quals.certificates or [])],
        "experience_lines": quals.experience_labels(),
    }
    suggestions = suggest_job_titles(parsed, existing_desired=[], existing_alternative=[])
    titles: list[str] = []
    for t in suggestions.get("desired") or []:
        if t and t not in titles:
            titles.append(t)
    # Fall back to raw past job titles (never cover-letter prose).
    for exp in quals.work_experience or []:
        t = (exp.title or "").strip()
        if t and t not in titles and len(t) >= 4:
            titles.append(t)
    for soft in (quals.software_values() or [])[:2]:
        s = (soft or "").strip()
        if s and len(s) >= 3 and s not in titles:
            titles.append(s)
    return titles[:8]


def resolve_search_titles(config: AppConfig) -> list[str]:
    """Return keyword titles for this run (Mode A discovery or Mode B explicit)."""
    desired = [t for t in (config.profile.jobs.desired_titles or []) if str(t).strip()]
    # Soft-migrate leftover alternatives if present in-memory.
    alts = [t for t in (config.profile.jobs.alternative_titles or []) if str(t).strip()]
    mode = str(getattr(config.settings, "search_mode", "") or "profile_discovery")
    if mode == "explicit_titles":
        return list(dict.fromkeys([*desired, *alts]))
    # Mode A — profile discovery: desired titles preferred but not required.
    if desired or alts:
        return list(dict.fromkeys([*desired, *alts]))
    return discovery_search_titles(config)


def _per_query_max(config: AppConfig, *, remote: bool = False) -> int:
    from core.config import normalize_jobs_per_search

    n = normalize_jobs_per_search(getattr(config.settings, "jobs_per_search", 40))
    if n == 0:
        # Max: large finite cap so sources terminate; unique totals across queries
        # still come from dedupe in the pipeline.
        return 250 if not remote else 120
    if remote:
        return max(5, min(n, n // 2 or n))
    return n


def build_queries(config: AppConfig) -> list[SearchQuery]:
    loc = config.profile.location
    titles = resolve_search_titles(config)
    if not titles:
        return []
    place = _search_location(loc.home_address)
    queries: list[SearchQuery] = []
    local_max = _per_query_max(config, remote=False)
    remote_max = _per_query_max(config, remote=True)
    if place:
        for title in titles:
            queries.append(
                SearchQuery(
                    keyword=title,
                    location=place,
                    radius_km=loc.max_distance_km,
                    max_results=local_max,
                    published_within_days=config.settings.published_within_days,
                )
            )
    if loc.allow_remote_germany:
        for title in titles[:3]:
            queries.append(
                SearchQuery(
                    keyword=title,
                    location="Remote",
                    radius_km=loc.max_distance_km,
                    max_results=remote_max,
                    published_within_days=config.settings.published_within_days,
                )
            )
    return queries



def enrich_locations(jobs, location: LocationService, progress_callback=None, should_stop=None):
    """Backward-compatible wrapper around ``enrich_job_locations``."""
    return enrich_job_locations(
        jobs,
        location,
        progress_callback=progress_callback,
        should_stop=should_stop,
    )


def _search_source_with_timeout(
    source,
    queries,
    timeout_s: float = SOURCE_SEARCH_TIMEOUT_S,
    should_stop=None,
):
    pool = ThreadPoolExecutor(max_workers=1)
    register_executor(pool)
    fut = pool.submit(source.safe_search, queries)
    try:
        deadline = __import__("time").monotonic() + timeout_s
        while True:
            if should_stop and should_stop():
                try:
                    pool.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    pool.shutdown(wait=False)
                return [], "cancelled", None
            remaining = deadline - __import__("time").monotonic()
            if remaining <= 0:
                try:
                    pool.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    pool.shutdown(wait=False)
                return [], f"Timeout after {int(timeout_s)}s", None
            try:
                return fut.result(timeout=min(0.5, remaining))
            except FuturesTimeout:
                continue
    finally:
        unregister_executor(pool)
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            try:
                pool.shutdown(wait=False)
            except Exception:
                pass
        except Exception:
            pass


def run_pipeline(
    config: AppConfig | None = None,
    mode: str | None = None,
    progress_callback=None,
    should_stop=None,
    recover_interrupted: bool = True,
) -> dict:
    """Run search (+ optional apply) once.

    ``recover_interrupted`` heals crash leftovers (``applying`` → ``needs_review``)
    before the run. Headless/scheduler runs need it; the desktop app already heals
    once at startup, and re-healing per search would bump review counters from a
    search the user merely started (or cancelled).
    """

    def progress(message: str) -> None:
        if progress_callback:
            try:
                progress_callback(message)
            except Exception:
                pass

    def stopped() -> bool:
        try:
            if should_stop and should_stop():
                return True
        except Exception:
            return False
        # Fail-closed: pause flipped mid-run stops further search/apply work.
        try:
            return bool(getattr(config.settings, "automation_paused", False))
        except Exception:
            return False

    config = config or load_config()
    if mode:
        config.settings.mode = mode

    if getattr(config.settings, "automation_paused", False):
        progress("Automatisierung pausiert — Pipeline nicht gestartet.")
        return {
            "total": 0,
            "cancelled": True,
            "paused": True,
            "source_errors": [],
            "source_results": {},
            "matches": 0,
            "new": 0,
            "applied": 0,
        }

    run = RunLogger(config.root / config.settings.logs_dir)
    run_id = uuid.uuid4().hex
    run.info(f"Run started id={run_id}")
    progress("Suche gestartet…")
    db = Database(config.db_path, recover=recover_interrupted)
    db.start_search_run(run_id)
    location = LocationService(db, config)
    home = location.resolve_home()
    if home.warning:
        progress(home.warning)
        run.info(home.warning)

    cancelled = False
    queries = build_queries(config)
    sources = build_sources(config.settings.enabled_sources)
    all_jobs = []
    source_errors: list[str] = []
    source_results: dict[str, dict] = {}
    if not queries:
        msg = (
            "Keine Suchanfragen: Im Profil-Entdeckungsmodus fehlen verwertbare "
            "Erfahrungs-/Skill-Hinweise — oder im Titelmodus fehlen Wunschberufe. "
            "Wohnort oder Remote setzen. Quellen wurden nicht mit leeren Queries aufgerufen."
        )
        progress(msg)
        run.warning(msg) if hasattr(run, "warning") else run.info(msg)
        for source in sources:
            placeholder = source.source_id == "company_sites"
            status = SourceHealthStatus.PLACEHOLDER if placeholder else SourceHealthStatus.EMPTY_QUERY
            note = "Nicht ausgeführt — leere Suchanfrage (Konfiguration)."
            db.set_source_status(source.source_id, status.value, note, 0)
            source_results[source.source_id] = {
                "status": status.value,
                "jobs": 0,
                "error": note,
            }
        stats = {
            "total": 0,
            "cancelled": False,
            "paused": False,
            "source_errors": [msg],
            "source_results": source_results,
            "matches": 0,
            "new": 0,
            "applied": 0,
            "config_error": "empty_queries",
        }
        db.finish_search_run(run_id, "error", stats)
        return stats
    for source in sources:
        if stopped():
            cancelled = True
            run.info("Pipeline cancelled during search")
            progress("Abgebrochen.")
            break
        progress(f"Phase Suche · Quelle {source.source_id}…")
        placeholder = source.source_id == "company_sites"
        jobs, err, detail = _search_source_with_timeout(
            source, queries, should_stop=stopped
        )
        if err and not jobs:
            run.error(f"{source.source_id}: {err}")
            source_errors.append(f"{source.source_id}: {err}")
            status = SourceHealthStatus.from_outcome(
                jobs_found=0,
                error=err,
                detail_stage=getattr(detail, "stage", None) if detail else None,
                source_id=source.source_id,
                placeholder=placeholder,
            )
            msg = detail.short_message() if detail else err
            if detail:
                run.error(detail.detail())
            db.set_source_status(source.source_id, status.value, msg, 0)
            source_results[source.source_id] = {
                "status": status.value,
                "jobs": 0,
                "error": msg,
            }
            progress(
                f"{source.source_id}: {status.value} — andere Quellen laufen weiter."
            )
            continue
        if err and jobs:
            run.error(f"{source.source_id}: {err}")
            source_errors.append(f"{source.source_id}: {err}")
            status = SourceHealthStatus.from_outcome(
                jobs_found=len(jobs),
                error=err,
                detail_stage=getattr(detail, "stage", None) if detail else None,
                source_id=source.source_id,
                placeholder=placeholder,
            )
            msg = detail.short_message() if detail else err
            if detail:
                run.error(detail.detail())
            db.set_source_status(source.source_id, status.value, msg, len(jobs))
            source_results[source.source_id] = {
                "status": status.value,
                "jobs": len(jobs),
                "error": msg,
            }
            progress(
                f"{source.source_id}: degraded — {len(jobs)} Jobs behalten, "
                "andere Quellen laufen weiter."
            )
            for job in jobs:
                job.run_id = run_id
            all_jobs.extend(jobs)
            continue
        status = SourceHealthStatus.from_outcome(
            jobs_found=len(jobs),
            source_id=source.source_id,
            placeholder=placeholder,
        )
        run.info(f"{source.source_id}: {len(jobs)} jobs [{status.value}]")
        note = ""
        if status == SourceHealthStatus.OK_EMPTY:
            note = "0 Treffer (Quelle antwortete, aber leer — nicht als kaputt werten, prüfen)"
        elif status == SourceHealthStatus.PLACEHOLDER:
            note = "Placeholder — absichtlich keine Jobs in v1"
        db.set_source_status(source.source_id, status.value, note, len(jobs))
        source_results[source.source_id] = {
            "status": status.value,
            "jobs": len(jobs),
            "error": note,
        }
        for job in jobs:
            job.run_id = run_id
        all_jobs.extend(jobs)

    total = len(all_jobs)
    run.info(f"{total} total results")

    progress("Phase Deduplizierung…")
    progress("Duplikate entfernen…")
    all_jobs = deduplicate(all_jobs)
    primary = [j for j in all_jobs if not j.duplicate_of]
    duplicates_removed = len(all_jobs) - len(primary)
    run.info(f"{duplicates_removed} duplicates marked")

    # Fachliches Matching FIRST — no geo yet (local-first pipeline).
    progress("Phase Matching…")
    progress("Jobs matchen…")
    scored = []
    outside = 0
    new_count = 0
    known = 0
    ats_counts = {"supported": 0, "detected_unsupported": 0, "unknown": 0}
    fachlich_candidates: list = []
    for job in primary:
        if stopped():
            cancelled = True
            break
        existing = (
            db.find_existing_by_source(job.source, job.source_job_id)
            if job.source_job_id
            else None
        )
        if existing and existing.status in {
            JobStatus.APPLIED.value,
            JobStatus.FAILED.value,
            JobStatus.NEEDS_REVIEW.value,
            JobStatus.CAPTCHA.value,
            JobStatus.APPLYING.value,
        }:
            known += 1
            continue
        suppress, suppress_reason = should_suppress_as_new(db, job)
        if suppress and "known_case" in suppress_reason:
            known += 1
            continue
        already = db.has_applied(job)
        job.ats_type = ATSDetector.detect(job.application_url or job.url)
        bucket = ats_coverage_bucket(job.ats_type)
        ats_counts[bucket] = ats_counts.get(bucket, 0) + 1
        job.run_id = run_id
        result = score_job(job, config, already_applied=already, apply_distance=False)
        job.match_score = result.score
        job.match_reasons = result.match_reasons
        job.rejection_reasons = result.rejection_reasons
        job.ranking_version = getattr(result, "ranking_version", "") or ""
        if result.excluded:
            job.status = JobStatus.IGNORED.value
        else:
            job.status = existing.status if existing else JobStatus.NEW.value
            if not existing:
                new_count += 1
            fachlich_candidates.append(job)
        scored.append(job)

    # Local geo + Luftlinie ONLY for fachlich suitable candidates (no Top-N cut).
    if not cancelled and not stopped() and fachlich_candidates:
        progress("Phase Standorte anreichern…")
        progress(f"Standorte anreichern: 0/{len(fachlich_candidates)} …")
        enrich_job_locations(
            fachlich_candidates,
            location,
            progress_callback=progress_callback,
            should_stop=should_stop,
        )
        if stopped():
            cancelled = True
        with db.batch(should_stop=stopped):
            for job in fachlich_candidates:
                prev_status = job.status
                apply_distance_scoring(job, config)
                if job.status == JobStatus.IGNORED.value and prev_status != JobStatus.IGNORED.value:
                    if any("km" in (r or "") for r in (job.rejection_reasons or [])):
                        outside += 1
                db.upsert_job(job)
    else:
        cancelled = cancelled or stopped()
        with db.batch(should_stop=stopped):
            for job in scored:
                db.upsert_job(job)

    # Persist fachlich-excluded scored jobs that were not candidates
    with db.batch(should_stop=stopped):
        for job in scored:
            if job not in fachlich_candidates:
                db.upsert_job(job)

    with db.batch(should_stop=stopped):
        for job in all_jobs:
            if job.duplicate_of:
                job.run_id = run_id
                db.upsert_job(job)
    if db.batch_skipped_writes:
        cancelled = True

    run.info(f"{outside} outside {config.profile.location.max_distance_km} km Luftlinie removed/ignored")
    run.info(f"{known} already known/applied skipped")
    run.info(f"{new_count} new jobs")
    matches = [
        j
        for j in scored
        if j.match_score >= config.settings.minimum_match_for_auto_apply
        and j.status != JobStatus.IGNORED.value
    ]
    run.info(f"{len(matches)} matches ≥{config.settings.minimum_match_for_auto_apply}%")

    stats = {
        "total": total,
        "raw_results": total,
        "duplicates": duplicates_removed,
        "distance_removed": outside,
        "outside": outside,
        "new": new_count,
        "new_jobs": new_count,
        "matches": len(matches),
        "applied": 0,
        "needs_review": 0,
        "captcha": 0,
        "failed": 0,
        "run_id": run_id,
        "cancelled": cancelled,
        "source_errors": source_errors,
        "source_results": source_results,
        "geocode_resolved": location.stats.resolved,
        "geocode_cached": location.stats.cached,
        "geocode_failed": location.stats.failed,
        "geocode_failures": location.stats.failed,
        "home_updated": location.home_updated,
        "home_resolved": location.home_resolved,
        "home_warning": location.home_warning,
        "ats_supported": ats_counts.get("supported", 0),
        "ats_detected_unsupported": ats_counts.get("detected_unsupported", 0),
        "ats_unknown": ats_counts.get("unknown", 0),
        "ats_attempted": 0,
        "ats_review_required": 0,
        "ats_completed": 0,
        "fachlich_candidates": len(fachlich_candidates),
    }

    if cancelled:
        db.finish_search_run(run_id, "cancelled", stats)
        progress("Abgebrochen.")
        run.info("Finished (cancelled)")
        return stats

    if config.settings.mode == OperatingMode.SEARCH_ONLY.value:
        run.info("Mode search_only — no applications")
        run.info("Finished")
        db.finish_search_run(run_id, "ok", stats)
        progress("Suche abgeschlossen.")
        return stats

    browser = None
    apply_error: str | None = None
    try:
        progress("Browser starten…")
        browser = BrowserManager(
            config.root / config.settings.browser_profile_dir,
            headless=config.settings.headless,
        )
        page = browser.get_page()
        manager = ApplicationManager(config, db, page=page)
        for job in matches:
            if stopped():
                run.info("Pipeline cancelled during applications")
                progress("Abgebrochen.")
                cancelled = True
                break
            if manager.failed_this_run >= config.settings.max_failed_applications_per_run:
                run.info("Failure limit reached — stopping AutoApply (search already done)")
                break
            if manager.applied_this_run >= config.settings.max_applications_per_run:
                run.info("Application limit reached")
                break
            ats = job.ats_type or "ATS"
            progress(f"Öffne {ats}: {job.company} – {job.title[:40]}")
            stats["ats_attempted"] = int(stats.get("ats_attempted") or 0) + 1
            result = manager.prepare_and_apply(job)
            label = job.title[:40]
            if result.captcha_detected:
                stats["captcha"] += 1
                run.info(f"{label} → CAPTCHA → stopping AutoApply (never bypass)")
                progress("CAPTCHA erkannt — Bewerbungslauf gestoppt.")
                break
            elif result.submitted:
                stats["applied"] += 1
                stats["ats_completed"] = int(stats.get("ats_completed") or 0) + 1
                run.info(f"{label} → application successful")
            elif result.needs_review or result.dry_run_stopped or result.manual_required:
                stats["needs_review"] += 1
                stats["ats_review_required"] = int(stats.get("ats_review_required") or 0) + 1
                if result.dry_run_stopped:
                    progress("Dry Run: vor dem Absenden gestoppt — Vorschau in Bewerbungen.")
                run.info(f"{label} → needs_review ({result.error_message})")
            else:
                stats["failed"] += 1
                run.info(f"{label} → failed ({result.error_message})")
    except Exception as exc:
        apply_error = str(exc)
        stats["apply_error"] = apply_error
        run.error(f"Browser/apply pipeline error: {exc}")
        progress("Bewerbungslauf fehlgeschlagen. Details stehen in den Logs.")
    finally:
        if browser:
            browser.close()

    stats["cancelled"] = cancelled
    if apply_error:
        finish_status = "error"
    elif cancelled:
        finish_status = "cancelled"
    else:
        finish_status = "ok"
    db.finish_search_run(run_id, finish_status, stats)
    run.info(
        f"Finished ({finish_status}): {stats['applied']} applications successful, "
        f"{stats['needs_review']} Needs Review, {stats['captcha']} CAPTCHA, {stats['failed']} Failed"
    )
    if apply_error:
        progress("Lauf mit Fehler beendet.")
    else:
        progress("Lauf abgeschlossen." if not cancelled else "Abgebrochen.")
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Karrierekrake")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in OperatingMode],
        default=None,
        help="Override operating mode",
    )
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single headless pipeline pass and exit (scheduler entrypoint).",
    )
    args = parser.parse_args(argv)

    # Explicit --config-dir wins (tests / portable installs).
    if args.config_dir is not None:
        root = Path(args.config_dir)
        config = load_config(
            profile_path=root / "config" / "profile.yaml",
            application_path=root / "config" / "application_profile.yaml",
            settings_path=root / "config" / "settings.yaml",
            root=root,
        )
    else:
        # Prefer AppData config when scheduled/packaged so GUI and task share profile.
        try:
            from desktop.services import ConfigService

            config = ConfigService().load()
        except Exception as exc:
            if args.once:
                logger.exception("AppData-Konfiguration fehlgeschlagen — Abbruch (--once)")
                raise SystemExit(
                    f"Config load failed (AppData): {exc}"
                ) from exc
            logger.exception(
                "AppData-Konfiguration fehlgeschlagen — Fallback auf Paket-Root-Config"
            )
            config = load_config()

    # Match frozen desktop --once: single-instance lock so scheduler cannot overlap GUI.
    shared = None
    if args.once and args.config_dir is None:
        try:
            from PySide6.QtCore import QCoreApplication
            from desktop.app import acquire_single_instance_lock

            _qt = QCoreApplication.instance() or QCoreApplication([])
            shared = acquire_single_instance_lock()
            if shared is None:
                logger.info("--once skipped: another Karrierekrake instance holds the lock")
                return 0
        except Exception:
            logger.exception("Single-instance lock unavailable; continuing --once without it")

    try:
        run_pipeline(config, mode=args.mode)
        return 0
    finally:
        if shared is not None:
            try:
                shared.detach()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

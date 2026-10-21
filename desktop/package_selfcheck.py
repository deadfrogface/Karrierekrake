"""Packaged self-check: proofs that only count when they run inside the built bundle.

``Karrierekrake --package-selfcheck --out result.json --checks a,b,...`` runs before
the GUI single-instance lock. Every check returns ``{"ok": bool, ...}``; the process
exits non-zero when any requested check fails. CI runs it against the actual
package (scripts/ci_package_selfcheck.py). Network checks are opt-in by name.

Checks:
  diskcache_guard  T06.04   a pickled diskcache value is refused, plain values work
  tls_runtime      T06.05.07.05.03  real TLS handshake with the bundled ssl/cryptography
  free_base        T11.05   no sales, no campaign, every free feature on, premium refused
  scaling_200      T10.04   all main-window pages at QT_SCALE_FACTOR=2 without clipped controls
  update_check     T03.06   startup (quiet) and manual check through the real update panel,
                            release-notes link to an existing release (network). Fails only
                            on real errors; no newer release, missing model, GitHub rate
                            limit and a standalone Windows install pass with their reason
  model_setup      T02.06/T02.07  damaged model never activated; real download, probe and
                            activation; second use and restart without network (network)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

BLOCKED_PROXY = "http://127.0.0.1:1"
SETUP_MODEL_ID = "qwen3.5-4b-gsq"


def check_diskcache_guard() -> dict[str, Any]:
    import sqlite3

    from core.security.diskcache_guard import (
        UnsafeCacheSerializationError,
        guard_diskcache,
    )

    guard_diskcache()
    try:
        import diskcache
    except ModuleNotFoundError:
        return {"ok": True, "diskcache_bundled": False}
    with tempfile.TemporaryDirectory(prefix="kk-diskcache-") as folder:
        cache = diskcache.Cache(folder)
        try:
            cache.set(b"plain", b"bytes-ok")
            plain_ok = cache.get(b"plain") == b"bytes-ok"
            try:
                cache.set(b"object", {"python": "object"})
                write_refused = False
            except UnsafeCacheSerializationError:
                write_refused = True
            # A value someone else stored with the pickle codec (mode 4) must not load.
            conn = sqlite3.connect(Path(folder) / "cache.db")
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO Cache(key, raw, store_time, expire_time, access_time, access_count,"
                        " tag, size, mode, filename, value) VALUES (?, 1, 0, NULL, 0, 0, NULL, 0, 4, NULL, ?)",
                        (b"planted", b"\x80\x04K\x01."),
                    )
            finally:
                conn.close()
            try:
                cache.get(b"planted")
                read_refused = False
            except UnsafeCacheSerializationError:
                read_refused = True
        finally:
            cache.close()
    return {"ok": plain_ok and write_refused and read_refused, "diskcache_bundled": True,
            "plain_value": plain_ok, "pickle_write_refused": write_refused, "pickle_read_refused": read_refused}


def check_tls_runtime() -> dict[str, Any]:
    import datetime as dt
    import socket
    import ssl

    import cryptography
    from cryptography import x509
    from cryptography.hazmat.backends.openssl.backend import backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    with tempfile.TemporaryDirectory(prefix="kk-tls-") as folder:
        cert_path, key_path = Path(folder) / "cert.pem", Path(folder) / "key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(cert_path, key_path)
        client_ctx = ssl.create_default_context(cafile=str(cert_path))
        listener = socket.create_server(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        received: list[bytes] = []

        def serve() -> None:
            conn, _ = listener.accept()
            with server_ctx.wrap_socket(conn, server_side=True) as tls:
                received.append(tls.recv(64))
                tls.sendall(b"pong")

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        with (socket.create_connection(("127.0.0.1", port), timeout=10) as raw,
              client_ctx.wrap_socket(raw, server_hostname="localhost") as tls):
            tls.sendall(b"ping")
            answer = tls.recv(64)
            version, cipher = tls.version(), tls.cipher()[0]
        thread.join(10)
        listener.close()
    return {"ok": answer == b"pong" and received == [b"ping"], "tls_version": version, "cipher": cipher,
            "ssl_openssl": ssl.OPENSSL_VERSION, "cryptography": cryptography.__version__,
            "cryptography_openssl": backend.openssl_version_text()}


def check_free_base() -> dict[str, Any]:
    from core.commercial.features import (
        PremiumFeature,
        PremiumUnavailable,
        require_premium,
    )
    from core.commercial.license_file import feature_allowed
    from core.commercial.release_policy import FREE_FEATURES, PAID_FEATURES, load_policy
    from core.commercial.sponsors import campaign, visible_campaign

    policy = load_policy()
    free = {name: feature_allowed(name) for name in sorted(FREE_FEATURES)}
    paid = {name: feature_allowed(name) for name in sorted(PAID_FEATURES)}
    refused = []
    for feature in PremiumFeature:
        try:
            require_premium(feature)
        except PremiumUnavailable:
            refused.append(feature.value)
    ok = (policy["sales_enabled"] is False and campaign() is None and visible_campaign() is None
          and all(free.values()) and not any(paid.values()) and len(refused) == len(PremiumFeature))
    return {"ok": ok, "sales_enabled": policy["sales_enabled"], "environment": policy["environment"],
            "campaign": campaign() is not None, "free_features": free, "paid_features": paid,
            "premium_refused": refused}


def _qt_app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([sys.argv[0]])


def _wait(predicate: Callable[[], bool], seconds: float) -> bool:
    from PySide6.QtWidgets import QApplication

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def check_scaling_200() -> dict[str, Any]:
    from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit

    from desktop.design_system.a11y import critical_widgets_not_clipped
    from desktop.i18n import i18n
    from desktop.main_window import MainWindow
    from desktop.services import ConfigService

    app = _qt_app()
    ratio = app.primaryScreen().devicePixelRatio()
    service = ConfigService()
    i18n.set_language(service.load().settings.language or "de")
    window = MainWindow(service)
    window.resize(1280, 800)
    window.show()
    _wait(lambda: False, 0.5)
    pages: dict[str, Any] = {}
    for index in range(window.stack.count()):
        window.stack.setCurrentIndex(index)
        page = window.stack.widget(index)
        _wait(lambda: False, 0.2)
        widgets = [w for kind in (QAbstractButton, QLabel, QLineEdit) for w in page.findChildren(kind)
                   if w.isVisible() and (not isinstance(w, QLabel) or w.text().strip())]
        clipped = critical_widgets_not_clipped(widgets)
        # A button narrower than its own label text cuts the label off at 200 %.
        truncated = [w.text() for w in widgets if isinstance(w, QAbstractButton) and w.text().strip()
                     and w.width() + 2 < w.fontMetrics().horizontalAdvance(w.text().replace("&", ""))]
        pages[type(page).__name__] = {"visible_controls": len(widgets), "clipped": clipped, "truncated_text": truncated}
    window.close()
    ok = (ratio == 2.0 and len(pages) == window.stack.count()
          and all(not p["clipped"] and not p["truncated_text"] for p in pages.values()))
    return {"ok": ok, "device_pixel_ratio": ratio, "pages": pages}


def _github_rate_limited() -> bool:
    """True when the unauthenticated GitHub API quota of this host is used up.

    /rate_limit itself does not count against the quota.
    """
    import requests

    try:
        response = requests.get("https://api.github.com/rate_limit", timeout=20,
                                headers={"Accept": "application/vnd.github+json"})
        return int(response.json()["resources"]["core"]["remaining"]) == 0
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return False


def classify_update_mode(outcome: dict[str, Any] | None, *, finished: bool, managed: bool,
                         platform: str, rate_limited: Callable[[], bool]) -> dict[str, Any]:
    """One update check (startup or manual) -> {"ok", "reason"}.

    Fails only on real errors: timeout, an error code (HTTP 4xx included,
    except a 403 caused by the GitHub rate limit) or a release for another
    platform. No newer release, a missing model and a standalone Windows
    install (no update-current.json, updates are manual by design) pass.
    """
    if not finished:
        return {"ok": False, "reason": "timeout"}
    if outcome is None:
        # UpdatePanel.check() returns without network for unmanaged installs.
        if not managed and platform == "win32":
            return {"ok": True, "reason": "standalone_windows_install"}
        return {"ok": False, "reason": "unmanaged_install"}
    if outcome["kind"] == "error":
        code = outcome["code"]
        if code == "http_403" and rate_limited():
            return {"ok": True, "reason": "github_rate_limited", "code": code}
        return {"ok": False, "reason": "error", "code": code}
    if outcome.get("wrong_platform"):
        return {"ok": False, "reason": "wrong_platform", "target": outcome.get("target")}
    reason = "update_available" if outcome["found"] else "no_newer_release"
    if outcome.get("model_missing"):
        reason += "+model_missing"
    return {"ok": True, "reason": reason}


def check_update_check() -> dict[str, Any]:
    import requests
    from PySide6.QtGui import QDesktopServices

    from core import app_updates, native_updates
    from desktop.widgets import update_panel as update_panel_module
    from desktop.widgets.update_panel import UpdatePanel

    _qt_app()
    opened: list[str] = []
    original = QDesktopServices.openUrl
    QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()) or True)
    native_target = native_updates.runtime_target()
    try:
        panel = UpdatePanel()
        run = panel._run
        outcome: dict[str, Any] = {}

        # Record what the real check operation returned or raised; the status
        # text alone cannot tell "model missing after a good check" from an error.
        def recording_run(operation, success, *, quiet=False):
            def observed():
                try:
                    value = operation()
                except Exception as error:
                    outcome.update(kind="error", code=app_updates.failure_code(error))
                    raise
                target = value.get("target") if isinstance(value, dict) else None
                outcome.update(kind="ok", found=bool(value), target=target,
                               wrong_platform=bool(panel.native and target and target != native_target),
                               model_missing=not (update_panel_module.native_models.available() if panel.native
                                                  else update_panel_module._model_available()))
                return value
            run(observed, success, quiet=quiet)

        panel._run = recording_run
        results = {}
        for mode, quiet in (("startup", True), ("manual", False)):
            outcome.clear()
            panel.check(quiet=quiet)
            finished = _wait(lambda: not panel.busy, 90)
            verdict = classify_update_mode(dict(outcome) or None, finished=finished, managed=panel.managed,
                                           platform=sys.platform, rate_limited=_github_rate_limited)
            results[mode] = {"finished": finished, "status": panel.status.text(), **verdict}
        panel._open_notes()
    finally:
        QDesktopServices.openUrl = original
    if panel.native and panel.native.get("target") != native_target:
        results["installed_identity"] = {"ok": False, "reason": "wrong_platform",
                                         "target": panel.native.get("target")}
    notes = opened[-1] if opened else ""
    reachable = bool(notes) and requests.head(notes, timeout=20, allow_redirects=True).status_code == 200
    # A tagged link is only possible when a release was found.
    found = any(r.get("reason", "").startswith("update_available") for r in results.values())
    notes_ok = reachable and ("/releases/tag/" in notes if found else "/releases" in notes)
    return {"ok": all(r["ok"] for r in results.values()) and notes_ok,
            "managed": panel.managed, "native": bool(panel.native), "checks": results,
            "release_notes_url": notes, "release_notes_reachable": reachable}


def _proxies(blocked: bool) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        if blocked:
            os.environ[name] = BLOCKED_PROXY
        else:
            os.environ.pop(name, None)
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"


def check_model_setup() -> dict[str, Any]:
    from core.model_probe import probe_in_subprocess
    from guenther.model_manager import ModelManager, default_models_dir
    from guenther.setup_models import (
        SETUP_MODEL_CATALOG,
        install_recommended_model,
        selected_model_id,
    )

    never = lambda: False
    models = default_models_dir()
    manager = ModelManager(models)
    target = manager.model_path(SETUP_MODEL_ID)
    target.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"model_id": SETUP_MODEL_ID}

    # 1) Guard: a damaged file without network is neither probed nor activated.
    target.write_bytes(os.urandom(2_000_000))
    _proxies(blocked=True)
    try:
        install_recommended_model(SETUP_MODEL_ID, cancelled=never, progress=lambda *_: None)
        report["damaged_refused"] = False
    except Exception as exc:  # noqa: BLE001 - any refusal counts, the activation state decides
        report["damaged_refused"] = True
        report["damaged_error"] = type(exc).__name__
    report["damaged_activated"] = selected_model_id(models) is not None

    # 2) Real transfer from the catalog source, verified, probed and activated.
    _proxies(blocked=False)
    started = time.monotonic()
    path = install_recommended_model(SETUP_MODEL_ID, cancelled=never, progress=lambda *_: None)
    report["transfer_s"] = round(time.monotonic() - started, 1)
    report["transfer_bytes"] = path.stat().st_size
    report["transfer_sha256_ok"] = manager.assert_model_integrity(SETUP_MODEL_ID) == SETUP_MODEL_CATALOG[SETUP_MODEL_ID]["sha256"]
    report["activated"] = selected_model_id(models) == SETUP_MODEL_ID

    # 3) Repeated use without network: reuse the verified file, probe again in a fresh process.
    _proxies(blocked=True)
    mtime = path.stat().st_mtime_ns
    install_recommended_model(SETUP_MODEL_ID, cancelled=never, progress=lambda *_: None)
    probe_in_subprocess(SETUP_MODEL_ID, cancelled=never)
    report["reused_without_download"] = path.stat().st_mtime_ns == mtime
    report["repeated_probes"] = 2
    report["ok"] = (report["damaged_refused"] and not report["damaged_activated"] and report["transfer_sha256_ok"]
                    and report["activated"] and report["reused_without_download"])
    return report


CHECKS: dict[str, Callable[[], dict[str, Any]]] = {
    "diskcache_guard": check_diskcache_guard,
    "tls_runtime": check_tls_runtime,
    "free_base": check_free_base,
    "scaling_200": check_scaling_200,
    "update_check": check_update_check,
    "model_setup": check_model_setup,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="Karrierekrake --package-selfcheck")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--checks", required=True, help="comma-separated: " + ",".join(CHECKS))
    args = parser.parse_args(argv)
    names = [n.strip() for n in args.checks.split(",") if n.strip()]
    unknown = sorted(set(names) - set(CHECKS))
    if unknown:
        parser.error("unknown checks: " + ",".join(unknown))
    if "scaling_200" in names:
        os.environ["QT_SCALE_FACTOR"] = "2"
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    report: dict[str, Any] = {"frozen": bool(getattr(sys, "frozen", False)), "platform": sys.platform, "checks": {}}
    for name in names:
        try:
            report["checks"][name] = CHECKS[name]()
        except Exception as exc:  # noqa: BLE001 - reported per check, never hidden
            report["checks"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
    report["ok"] = all(result.get("ok") is True for result in report["checks"].values())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if sys.stdout is not None:  # windowed Windows builds have no console stream
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["ok"] else 1

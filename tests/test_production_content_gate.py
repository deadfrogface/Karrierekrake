"""PR21: Production artifact content gate — allowlist + forbidden markers."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_policy():
    path = ROOT / "packaging" / "kk_content_policy.py"
    spec = importlib.util.spec_from_file_location("kk_content_policy", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["kk_content_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_scan():
    path = ROOT / "scripts" / "scan_release_artifact.py"
    spec = importlib.util.spec_from_file_location("kk_scan_release", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _load_manifest():
    path = ROOT / "scripts" / "generate_content_manifest.py"
    spec = importlib.util.spec_from_file_location("kk_gen_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


policy = _load_policy()


# ---------------------------------------------------------------------------
# Allowlist / module policy
# ---------------------------------------------------------------------------


def test_policy_version_positive():
    assert policy.POLICY_VERSION >= 1


def test_allowed_datas_exist_on_disk():
    for rel, _dest in policy.ALLOWED_DATAS:
        assert (ROOT / rel).exists(), f"allowlisted path missing: {rel}"


def test_demo_data_module_excluded():
    assert not policy.module_allowed("desktop.demo_data")
    assert policy.module_allowed("desktop.app")
    assert policy.module_allowed("desktop.pages.profile")


def test_benchmark_and_tools_excluded():
    assert not policy.module_allowed("benchmark")
    assert not policy.module_allowed("benchmark.run_benchmark")
    assert not policy.module_allowed("tools.cover_opt")
    assert not policy.module_allowed("tools.cover_opt.metric")
    assert not policy.module_allowed("tests.test_foo")


def test_first_party_runtime_allowed():
    for name in (
        "core.config",
        "search.sources",
        "apply.engine",
        "guenther.service",
        "integrations.gmail_auth",
        "browser.browser_manager",
        "app.main",
    ):
        assert policy.module_allowed(name), name


def test_filter_hiddenimports_drops_demo():
    mods = ["desktop.app", "desktop.demo_data", "benchmark.foo", "core.config"]
    out = policy.filter_hiddenimports(mods)
    assert out == ["desktop.app", "core.config"]


@pytest.mark.parametrize(
    "path",
    [
        "PYZ.pyz/tests/test_cv.py",
        "benchmark/corpus/x.json",
        "tools/cover_opt/metric.py",
        " somehow/blindset/data.json",
        "gold_set.jsonl",
        ".env",
        "config/.env.local",
        "data/jobs.db",
        "oauth_user.json",
        "client_secret_123.json",
        "gmail_credentials.json",
        "ms-playwright/chromium-123/chrome",
        "desktop/demo_data.py",
        "cover_specialization/gold_set.jsonl",
    ],
)
def test_forbidden_path_markers(path: str):
    assert policy.path_has_forbidden_marker(path)


@pytest.mark.parametrize(
    "path",
    [
        "desktop/app.py",
        "core/config.py",
        "templates/cover_letter.txt",
        "config/settings.yaml.example",
        "assets/brand/logo.png",
        "PySide6/QtCore.pyd",
        "tls_client/dependencies/tls_client.dll",
        "playwright/__init__.py",
        "google.auth.environment_vars",
        "botocore/data/logs/2014-03-28/service-2.json.gz",
    ],
)
def test_allowed_runtime_paths_clean(path: str):
    assert not policy.path_has_forbidden_marker(path)


def test_botocore_logs_and_dotenv_boundaries():
    """Justified FPs: botocore Logs API models; '.environment_vars' ≠ '.env'."""
    assert not policy.path_has_forbidden_marker(
        "botocore/data/logs/2014-03-28/service-2.json.gz"
    )
    assert not policy.path_has_forbidden_marker("google.auth.environment_vars")
    assert policy.path_has_forbidden_marker("logs/app.log")
    assert policy.path_has_forbidden_marker("Karrierekrake/logs/boot.log")
    assert policy.path_has_forbidden_marker(".env")
    assert policy.path_has_forbidden_marker("config/.env.local")
    assert policy.path_has_forbidden_marker("desktop/demo_data.py")


def test_scan_paths_reports_hits():
    hits = policy.scan_paths(
        [
            "desktop/app.py",
            "tests/fixtures/cv_a.txt",
            "benchmark/results.json",
        ]
    )
    assert len(hits) >= 2
    kinds = {h.path for h in hits}
    assert any("tests" in p for p in kinds)


def test_filter_collect_all_drops_ms_playwright():
    datas = [
        ("/venv/site-packages/playwright/driver/package", "playwright/driver"),
        ("/home/x/.cache/ms-playwright/chromium", "ms-playwright"),
        ("/repo/tests/fixtures/cv_a.txt", "tests/fixtures"),
    ]
    filtered = policy.filter_collect_all_datas(datas)
    joined = " ".join(str(x[0]) for x in filtered)
    assert "ms-playwright" not in joined
    assert "tests/fixtures" not in joined
    assert "playwright/driver" in joined or "package" in joined


def test_build_repo_datas_only_allowlist():
    datas = policy.build_repo_datas(str(ROOT))
    assert datas
    for src, dest in datas:
        assert policy.datas_entry_allowed(src, dest)


def test_datas_entry_rejects_tests_tree():
    assert not policy.datas_entry_allowed(str(ROOT / "tests" / "fixtures"), "tests")


# ---------------------------------------------------------------------------
# Scanner CLI + manifest
# ---------------------------------------------------------------------------


def test_scan_clean_toc_json(tmp_path: Path):
    scan = _load_scan()
    toc = tmp_path / "toc.json"
    toc.write_text(
        json.dumps(
            {
                "entries": [
                    {"path": "desktop/app.py"},
                    {"path": "templates/cover_letter.txt"},
                    {"path": "config/settings.yaml.example"},
                ]
            }
        ),
        encoding="utf-8",
    )
    paths, hits = scan.scan_artifact(toc_json=toc)
    assert len(paths) == 3
    assert hits == []


def test_scan_blocks_benchmark_in_toc(tmp_path: Path):
    scan = _load_scan()
    toc = tmp_path / "toc.json"
    toc.write_text(
        json.dumps(["desktop/app.py", "benchmark/corpus/x.json", ".env"]),
        encoding="utf-8",
    )
    _paths, hits = scan.scan_artifact(toc_json=toc)
    assert hits
    assert any("benchmark" in h.path or h.path.endswith(".env") for h in hits)


def test_scan_cli_fails_on_forbidden(tmp_path: Path):
    toc = tmp_path / "toc.json"
    toc.write_text(json.dumps(["tests/test_foo.py"]), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scan_release_artifact.py"), "--toc-json", str(toc)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "FAILED" in proc.stdout


def test_scan_cli_passes_clean(tmp_path: Path):
    toc = tmp_path / "toc.json"
    toc.write_text(json.dumps(["desktop/app.py", "core/config.py"]), encoding="utf-8")
    manifest = tmp_path / "content_manifest.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "scan_release_artifact.py"),
            "--toc-json",
            str(toc),
            "--manifest-out",
            str(manifest),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["policy_version"] == policy.POLICY_VERSION
    assert data["gate"]["passed"] is True
    assert data["entry_count"] == 2


def test_manifest_deterministic_entry_order(tmp_path: Path):
    gen = _load_manifest()
    out = tmp_path / "m.json"
    gen.write_manifest(out, paths=["b/x", "a/y", "a/y", "c/z"])
    data = json.loads(out.read_text(encoding="utf-8"))
    paths = [e["path"] for e in data["entries"]]
    assert paths == sorted(set(paths))


def test_scan_text_blocks_private_key():
    scan = _load_scan()
    hits = scan.scan_text_content(
        "embedded/secret.pem",
        "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n",
    )
    assert any(h.kind == "begin_private_key" for h in hits)


def test_scan_text_allows_example_email():
    scan = _load_scan()
    hits = scan.scan_text_content(
        "config/application_profile.yaml.example",
        "email: alex.muster@example.com\n",
    )
    assert hits == []


def test_scan_text_blocks_real_email_domain():
    scan = _load_scan()
    # Assemble domain from parts so privacy_scan.py does not flag this test file.
    domain = "g" + "mail.com"
    hits = scan.scan_text_content("leaked.txt", f"contact me at person@{domain} please")
    assert any(h.kind == "non_example_email" for h in hits)


def test_settings_example_gmail_path_not_secret():
    """False positive note: path string in example is OK; private key would still fail."""
    scan = _load_scan()
    text = (ROOT / "config" / "settings.yaml.example").read_text(encoding="utf-8")
    hits = scan.scan_text_content("config/settings.yaml.example", text)
    assert hits == []


def test_spec_references_content_policy():
    spec = (ROOT / "packaging" / "Karrierekrake.spec").read_text(encoding="utf-8")
    assert "kk_content_policy" in spec
    assert "filter_hiddenimports" in spec
    assert "desktop.demo_data" in spec or "CONTENT POLICY" in spec


def test_fail_on_empty_toc(tmp_path: Path):
    toc = tmp_path / "empty.json"
    toc.write_text("[]", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "scan_release_artifact.py"),
            "--toc-json",
            str(toc),
            "--fail-on-empty",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

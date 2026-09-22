"""Production content policy for Karrierekrake release artifacts.

Allowlist-first: only explicitly approved repo datas and module prefixes may
ship in the PyInstaller onefile EXE. Forbidden path markers / content patterns
always block release — never silence the scanner permanently.

Dev datasets (tests/, benchmark/, tools/cover_opt, fixtures, demo seeding)
remain in Git for development; they must not appear in dist/.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple

POLICY_VERSION = 1

# ---------------------------------------------------------------------------
# Repo-relative datas that MAY be bundled (explicit allowlist)
# ---------------------------------------------------------------------------

ALLOWED_DATAS: tuple[tuple[str, str], ...] = (
    # (source relative to repo root, destination inside bundle)
    ("templates", "templates"),
    ("config/profile.yaml.example", "config"),
    ("config/application_profile.yaml.example", "config"),
    ("config/settings.yaml.example", "config"),
    ("assets/brand", "assets/brand"),
    ("data/geo", "data/geo"),
    ("NOTICE", "."),
    ("LICENSE", "."),
)

# First-party Python packages that may be collected as hiddenimports.
ALLOWED_FIRST_PARTY_PREFIXES: tuple[str, ...] = (
    "app",
    "apply",
    "browser",
    "core",
    "desktop",
    "guenther",
    "integrations",
    "search",
)

# First-party modules that must NEVER ship (even under allowed prefixes).
EXCLUDED_FIRST_PARTY_MODULES: tuple[str, ...] = (
    "desktop.demo_data",
    "benchmark",
    "tools",
    "tools.cover_opt",
    "tests",
)

# Third-party packages we intentionally collect_all / pull binaries for.
# Documented: tls_client (jobspy DLLs), jobspy, playwright Python driver only.
ALLOWED_COLLECT_ALL_PACKAGES: tuple[str, ...] = (
    "tls_client",
    "jobspy",
    "playwright",
)

# Extra hiddenimports (third-party) that Analysis may need.
ALLOWED_THIRD_PARTY_HIDDEN: tuple[str, ...] = (
    "app.main",
    "browser.browser_manager",
    "playwright",
    "yaml",
    "PySide6",
    "tls_client",
    "tls_client.cffi",
    "tls_client.dependencies",
    "jobspy",
    "numpy",
    "pandas",
    "lxml",
    "bs4",
)

# Always excluded from Analysis (dev / unused UI stacks).
ANALYSIS_EXCLUDES: tuple[str, ...] = (
    "matplotlib",
    "tkinter",
    "pytest",
    "pytest_qt",
    "hypothesis",
    "benchmark",
    "tools",
    "tools.cover_opt",
    "tests",
    "desktop.demo_data",
    "streamlit",
    "IPython",
    "notebook",
)

# ---------------------------------------------------------------------------
# Forbidden markers — any TOC / extracted path matching these FAILS the gate
# ---------------------------------------------------------------------------

FORBIDDEN_PATH_MARKERS: tuple[str, ...] = (
    "/tests/",
    "\\tests\\",
    "/benchmark/",
    "\\benchmark\\",
    "/tools/cover_opt/",
    "\\tools\\cover_opt\\",
    "/blindset",
    "\\blindset",
    "/goldset",
    "\\goldset",
    "/gold_set",
    "\\gold_set",
    "/.cursor/",
    "\\.cursor\\",
    "/agent-tools/",
    "\\agent-tools\\",
    "cover_specialization",
    "guenther_final_model_shootout",
    "model_tournament_raw",
    "fictional_emails",
    "cv_corpus/",
    "profile_migration/",
    # Match module/file demo_data, not arbitrary substrings
    "/demo_data",
    "demo_data.py",
    "demo_data/",
    "ms-playwright",
    # App log dirs only — NOT botocore/data/logs (AWS API model; justified FP note)
    "/Karrierekrake/logs/",
    "\\Karrierekrake\\logs\\",
    ".pytest_cache",
    ".hypothesis",
)

# Dotenv paths — matched with boundary checks (avoid '.environment_vars' FP)
DOTENV_PATH_SUFFIXES: tuple[str, ...] = (
    "/.env",
    "\\.env",
    "/.env.local",
    "/.env.production",
    "/.env.development",
)

# Relative tops that must not appear as bundled first-party trees
FORBIDDEN_TOP_LEVEL_PREFIXES: tuple[str, ...] = (
    "tests/",
    "benchmark/",
    "tools/cover_opt/",
    "logs/",
    ".cursor/",
    "agent-tools/",
)

FORBIDDEN_BASENAME_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.local",
    ".env.production",
    "jobs.db",
    "jobs.db-wal",
    "jobs.db-shm",
    "oauth_*.json",
    "token.json",
    "credentials.json",
    "client_secret*.json",
    "gmail_credentials.json",
)

# Content substrings that block release when found in *first-party* text members.
# Vendor discovery docs (googleapiclient, botocore examples, playwright stubs) are
# path-scanned only — see FALSE_POSITIVE_NOTES. Do not disable the scanner.
FORBIDDEN_CONTENT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("begin_private_key", "-----BEGIN PRIVATE KEY-----"),
    ("begin_rsa_private", "-----BEGIN RSA PRIVATE KEY-----"),
    ("aws_access_key_id", "AKIA"),  # matched with AKIA[0-9A-Z]{16} in scanner
    ("openai_sk", "sk-proj-"),
    ("openai_sk_legacy", "sk-"),  # matched with sk-[A-Za-z0-9]{20,} in scanner
)

# TOC path prefixes that receive *content* (email/secret) scanning.
# Everything else is still subject to forbidden *path* markers.
FIRST_PARTY_CONTENT_PREFIXES: tuple[str, ...] = (
    "app/",
    "apply/",
    "browser/",
    "core/",
    "desktop/",
    "guenther/",
    "integrations/",
    "search/",
    "templates/",
    "config/",
    "assets/",
    "app.",
    "apply.",
    "browser.",
    "core.",
    "desktop.",
    "guenther.",
    "integrations.",
    "search.",
)

FALSE_POSITIVE_NOTES: dict[str, str] = {
    "config/settings.yaml.example:gmail_credentials_path": (
        "Example path string pointing at gitignored private/; no secret payload."
    ),
    "playwright driver package": (
        "Python playwright package is allowed; ms-playwright browser trees are forbidden."
    ),
    "tls_client collect_all": (
        "Required for python-jobspy Windows DLLs; filtered for ms-playwright/chromium."
    ),
    "botocore/data/logs": (
        "AWS botocore service model for CloudWatch Logs API — not application log files. "
        "Generic '/logs/' marker intentionally narrowed to avoid this FP."
    ),
    "google.auth.environment_vars": (
        "Module name contains '.env' as a substring of '.environment'; dotenv matching uses path boundaries."
    ),
    "googleapiclient/discovery_cache": (
        "Upstream Google API discovery JSON may mention example emails / PEM headers as schema "
        "documentation. Path gate still applies; content email/secret scan is first-party only."
    ),
    "botocore/data/*/examples": (
        "AWS botocore example payloads may contain the AKIA prefix as documentation, not live keys."
    ),
    "jobspy/model.py AKIA": (
        "python-jobspy model field docs may mention AWS key shape; content scan is first-party only."
    ),
    "playwright/_generated.py @microsoft.com": (
        "Generated Playwright API stubs reference Microsoft docs emails; not applicant PII."
    ),
}


class PolicyHit(NamedTuple):
    kind: str
    path: str
    detail: str


def is_first_party_content_path(path: str) -> bool:
    """True if path should receive email/secret *content* scanning.

    Vendor trees (googleapiclient discovery JSON, botocore examples, playwright
    stubs) are still checked for forbidden *path* markers, but their embedded
    documentation emails / example key shapes are documented FPs — not live PII.
    """
    lower = normalize_path(path).lstrip("/").lower()
    for strip in ("pyz-00.pyz/", "pyz.pyz/", "base_library.zip/"):
        if lower.startswith(strip):
            lower = lower[len(strip) :]
    base = lower.rsplit("/", 1)[-1]
    if base in {"notice", "license", "license.txt", "notice.txt", "license.md"}:
        return True
    if lower in {"notice", "license"}:
        return True
    for prefix in FIRST_PARTY_CONTENT_PREFIXES:
        p = prefix.lower()
        if lower.startswith(p):
            return True
        dotted = p.rstrip("./").replace("/", ".")
        if lower == dotted or lower.startswith(dotted + ".") or lower.startswith(dotted + "/"):
            return True
    return False


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def module_allowed(module: str) -> bool:
    """Return True if a hiddenimport / submodule name may ship."""
    name = module.strip()
    if not name:
        return False
    for excluded in EXCLUDED_FIRST_PARTY_MODULES:
        if name == excluded or name.startswith(excluded + "."):
            return False
    for prefix in ALLOWED_FIRST_PARTY_PREFIXES:
        if name == prefix or name.startswith(prefix + "."):
            return True
    # Third-party: allow if listed or under collect_all packages
    if name in ALLOWED_THIRD_PARTY_HIDDEN:
        return True
    for pkg in ALLOWED_COLLECT_ALL_PACKAGES:
        if name == pkg or name.startswith(pkg + "."):
            return True
    # Other third-party modules pulled transitively are OK unless forbidden marker
    lower = name.lower()
    if any(x in lower for x in ("pytest", "hypothesis", "benchmark", "cover_opt")):
        return False
    return True  # transitive third-party; path scan still applies


def filter_hiddenimports(modules: Iterable[str]) -> list[str]:
    return [m for m in modules if module_allowed(m)]


def datas_entry_allowed(src: str, dest: str = "") -> bool:
    """Allowlist check for a PyInstaller datas tuple source path."""
    norm = normalize_path(src)
    # Absolute or relative: match against allowed source suffixes
    for allowed_src, allowed_dest in ALLOWED_DATAS:
        allowed_norm = normalize_path(allowed_src)
        if norm.endswith("/" + allowed_norm) or norm.endswith(allowed_norm) or allowed_norm in norm:
            # Dest should match expected when provided
            if dest and normalize_path(dest) not in {
                normalize_path(allowed_dest),
                normalize_path(allowed_dest) + "/" + allowed_norm.split("/")[-1],
            }:
                # Dest mismatch is soft — still allow if src matches allowlist
                pass
            return True
    # Third-party package datas (site-packages) — allowed unless forbidden marker
    if "site-packages" in norm or "dist-packages" in norm:
        return not path_has_forbidden_marker(norm)
    return False


def path_has_forbidden_marker(path: str) -> bool:
    norm = "/" + normalize_path(path).lstrip("/").lower()
    rel = normalize_path(path).lstrip("/").lower()
    base = rel.rsplit("/", 1)[-1]
    for prefix in FORBIDDEN_TOP_LEVEL_PREFIXES:
        if rel.startswith(prefix.lower()):
            return True
    # Dotenv: exact file or /.env. suffix — not '.environment_vars'
    for suffix in DOTENV_PATH_SUFFIXES:
        s = normalize_path(suffix).lower()
        if norm == s or norm.endswith(s):
            return True
        if s + "." in norm or s + "/" in norm:
            return True
    for marker in FORBIDDEN_PATH_MARKERS:
        m = normalize_path(marker).lower()
        if m.startswith("/"):
            if m in norm or norm.endswith(m.rstrip("/")):
                return True
        elif m in norm:
            return True
    for pattern in FORBIDDEN_BASENAME_GLOBS:
        if _basename_matches(base, pattern.lower()):
            return True
    return False


def _basename_matches(name: str, pattern: str) -> bool:
    if "*" not in pattern:
        return name == pattern
    # simple glob: prefix*suffix
    if pattern.startswith("*") and pattern.endswith("*"):
        return pattern.strip("*") in name
    if pattern.startswith("*"):
        return name.endswith(pattern[1:])
    if pattern.endswith("*"):
        return name.startswith(pattern[:-1])
    # mid star
    left, right = pattern.split("*", 1)
    return name.startswith(left) and name.endswith(right)


def scan_paths(paths: Iterable[str]) -> list[PolicyHit]:
    hits: list[PolicyHit] = []
    for raw in paths:
        p = normalize_path(str(raw))
        if path_has_forbidden_marker(p):
            hits.append(PolicyHit(kind="forbidden_path", path=p, detail="matches forbidden marker"))
    return hits


def filter_collect_all_datas(
    datas: list[tuple],
) -> list[tuple]:
    """Drop forbidden trees from collect_all results (ms-playwright, tests, …)."""
    out: list[tuple] = []
    for item in datas:
        src = str(item[0]) if item else ""
        dest = str(item[1]) if item and len(item) > 1 else ""
        combined = f"{src}|{dest}"
        if path_has_forbidden_marker(combined):
            continue
        if "chromium" in normalize_path(src).lower() and "playwright" in normalize_path(src).lower():
            continue
        out.append(item)
    return out


def filter_collect_all_binaries(binaries: list[tuple]) -> list[tuple]:
    out: list[tuple] = []
    for item in binaries:
        src = str(item[0]) if item else ""
        if path_has_forbidden_marker(src):
            continue
        out.append(item)
    return out


def build_repo_datas(root: str) -> list[tuple[str, str]]:
    """Materialize allowlisted datas as absolute (src, dest) for the spec."""
    import os

    datas: list[tuple[str, str]] = []
    for rel, dest in ALLOWED_DATAS:
        src = os.path.join(root, *rel.split("/"))
        if os.path.exists(src):
            datas.append((src, dest))
    return datas

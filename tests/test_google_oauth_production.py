"""PR43 — Google OAuth least-privilege scope + revocation matrix (≥50 cases)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from integrations import google_oauth as goa
from integrations import gmail_auth, secure_tokens
from integrations.gmail_auth import TOKEN_ACCOUNT, authorize_calendar_freebusy, authorize_gmail
from integrations.secure_tokens import delete_token, store_token


class _MemKeyring:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def set_password(self, service: str, account: str, password: str) -> None:
        self._data[f"{service}:{account}"] = password

    def get_password(self, service: str, account: str) -> str | None:
        return self._data.get(f"{service}:{account}")

    def delete_password(self, service: str, account: str) -> None:
        self._data.pop(f"{service}:{account}", None)


@pytest.fixture(autouse=True)
def _isolate_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    kr = _MemKeyring()
    monkeypatch.setattr(secure_tokens, "_keyring", lambda: kr)
    delete_token(TOKEN_ACCOUNT, fallback_dir=tmp_path)
    yield kr
    delete_token(TOKEN_ACCOUNT, fallback_dir=tmp_path)


def _client_file(path: Path, *, client_id: str = "cid-dev-test") -> Path:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": client_id,
                    "client_secret": "secret",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _probeable_gmail_service() -> MagicMock:
    svc = MagicMock(name="gmail_service")
    svc.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "probe@example.test",
        "messagesTotal": 1,
    }
    return svc


def _probeable_calendar_service() -> MagicMock:
    svc = MagicMock(name="calendar_service")
    svc.freebusy.return_value.query.return_value.execute.return_value = {"calendars": {}}
    return svc


class FakeCreds:
    def __init__(self, scopes: list[str] | None = None, **kw: Any):
        self.valid = kw.get("valid", True)
        self.expired = kw.get("expired", False)
        self.refresh_token = kw.get("refresh_token", "rt")
        self.token = kw.get("token", "at")
        self.scopes = scopes or [goa.GMAIL_READONLY]
        self.client_id = kw.get("client_id", "cid")
        self.client_secret = kw.get("client_secret", "csec")
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.expiry = None
        self._refresh_exc = kw.get("refresh_exc")

    def refresh(self, _request) -> None:
        if self._refresh_exc:
            raise self._refresh_exc
        self.valid = True
        self.expired = False


# --- Allowlist / matrix (cases 1–25) ---


def test_allowlist_contains_exactly_three_production_scopes():
    assert goa.ALLOWED_SCOPES == frozenset(
        {goa.GMAIL_READONLY, goa.CALENDAR_FREEBUSY, goa.CALENDAR_EVENTS}
    )


@pytest.mark.parametrize(
    "scope",
    sorted(goa.FORBIDDEN_SCOPES),
)
def test_forbidden_scopes_rejected(scope: str):
    assert goa.is_forbidden_scope(scope)
    with pytest.raises(goa.ScopePolicyError):
        goa.assert_scopes_allowed([scope])


def test_mail_google_com_variants_forbidden():
    assert goa.is_forbidden_scope("https://mail.google.com")
    assert goa.is_forbidden_scope("https://mail.google.com/")


def test_full_calendar_scope_forbidden():
    assert goa.is_forbidden_scope("https://www.googleapis.com/auth/calendar")
    assert not goa.is_allowed_scope("https://www.googleapis.com/auth/calendar")


def test_calendar_readonly_not_on_allowlist():
    assert not goa.is_allowed_scope("https://www.googleapis.com/auth/calendar.readonly")
    with pytest.raises(goa.ScopePolicyError):
        goa.assert_scopes_allowed(["https://www.googleapis.com/auth/calendar.readonly"])


def test_gmail_readonly_allowed_and_restricted():
    assert goa.is_allowed_scope(goa.GMAIL_READONLY)
    assert goa.SCOPE_SENSITIVITY[goa.GMAIL_READONLY] == goa.ScopeSensitivity.RESTRICTED


def test_freebusy_sensitive_not_restricted():
    assert goa.SCOPE_SENSITIVITY[goa.CALENDAR_FREEBUSY] == goa.ScopeSensitivity.SENSITIVE


def test_calendar_events_sensitive():
    assert goa.SCOPE_SENSITIVITY[goa.CALENDAR_EVENTS] == goa.ScopeSensitivity.SENSITIVE


def test_feature_matrix_gmail_only():
    d = goa.scopes_for_features(goa.Feature.GMAIL_READ)
    assert d.scopes == (goa.GMAIL_READONLY,)
    assert goa.Feature.GMAIL_READ in d.features


def test_feature_matrix_calendar_freebusy_only():
    d = goa.scopes_for_features(goa.Feature.CALENDAR_SLOT_FINDING)
    assert d.scopes == (goa.CALENDAR_FREEBUSY,)
    assert goa.GMAIL_READONLY not in d.scopes


def test_feature_matrix_calendar_write_only():
    d = goa.scopes_for_features(goa.Feature.CALENDAR_EVENT_WRITE)
    assert d.scopes == (goa.CALENDAR_EVENTS,)


def test_feature_matrix_combined_gmail_and_freebusy():
    d = goa.scopes_for_features(
        {goa.Feature.GMAIL_READ, goa.Feature.CALENDAR_SLOT_FINDING}
    )
    assert set(d.scopes) == {goa.GMAIL_READONLY, goa.CALENDAR_FREEBUSY}


def test_flags_map_no_features_when_disabled():
    assert goa.features_enabled_by_flags() == frozenset()


def test_flags_map_gmail_only():
    assert goa.features_enabled_by_flags(gmail_sync_enabled=True) == frozenset(
        {goa.Feature.GMAIL_READ}
    )


def test_flags_map_calendar_only():
    assert goa.features_enabled_by_flags(calendar_freebusy_enabled=True) == frozenset(
        {goa.Feature.CALENDAR_SLOT_FINDING}
    )


def test_flags_map_write_does_not_imply_freebusy():
    feats = goa.features_enabled_by_flags(allow_calendar_write=True)
    assert goa.Feature.CALENDAR_EVENT_WRITE in feats
    assert goa.Feature.CALENDAR_SLOT_FINDING not in feats


def test_assert_no_new_restricted_blocks_modify():
    with pytest.raises(goa.RestrictedScopeReviewRequired):
        goa.assert_no_new_restricted([goa.GMAIL_READONLY, "https://www.googleapis.com/auth/gmail.modify"])


def test_assert_no_new_restricted_allows_existing_readonly():
    goa.assert_no_new_restricted([goa.GMAIL_READONLY])


def test_empty_interactive_scopes_rejected():
    with pytest.raises(goa.ScopePolicyError):
        goa.assert_scopes_allowed([])


def test_normalize_dedupes():
    assert goa.normalize_scopes([goa.GMAIL_READONLY, goa.GMAIL_READONLY]) == (
        goa.GMAIL_READONLY,
    )


def test_incremental_scopes_to_request_diff():
    new = goa.incremental_scopes_to_request(
        already_granted=[goa.GMAIL_READONLY],
        needed=[goa.GMAIL_READONLY, goa.CALENDAR_FREEBUSY],
    )
    assert new == (goa.CALENDAR_FREEBUSY,)


def test_incremental_noop_when_already_granted():
    assert (
        goa.incremental_scopes_to_request(
            already_granted=[goa.GMAIL_READONLY],
            needed=[goa.GMAIL_READONLY],
        )
        == ()
    )


def test_authorization_url_kwargs_incremental():
    kw = goa.authorization_url_kwargs()
    assert kw["access_type"] == "offline"
    assert kw["include_granted_scopes"] == "true"
    assert kw["prompt"] == "consent"


def test_run_local_server_kwargs_system_browser():
    kw = goa.run_local_server_kwargs(port=8080, open_browser=True)
    assert kw["open_browser"] is True
    assert kw["port"] == 8080
    assert kw["include_granted_scopes"] == "true"


# --- Partial consent / availability (26–35) ---


def test_partial_consent_denies_missing_calendar():
    denied = goa.partial_consent_denied_features(
        {goa.Feature.GMAIL_READ, goa.Feature.CALENDAR_SLOT_FINDING},
        [goa.GMAIL_READONLY],
    )
    assert denied == (goa.Feature.CALENDAR_SLOT_FINDING,)


def test_partial_consent_none_when_all_granted():
    denied = goa.partial_consent_denied_features(
        {goa.Feature.GMAIL_READ},
        [goa.GMAIL_READONLY],
    )
    assert denied == ()


def test_feature_available_gmail():
    assert goa.feature_available(goa.Feature.GMAIL_READ, [goa.GMAIL_READONLY])
    assert not goa.feature_available(goa.Feature.GMAIL_READ, [goa.CALENDAR_FREEBUSY])


def test_feature_available_freebusy():
    assert goa.feature_available(
        goa.Feature.CALENDAR_SLOT_FINDING, [goa.CALENDAR_FREEBUSY]
    )


def test_gmail_only_decision_excludes_calendar_write():
    d = goa.scopes_for_features(goa.Feature.GMAIL_READ)
    assert goa.CALENDAR_EVENTS not in d.scopes
    assert "gmail.modify" not in "".join(d.scopes)


def test_calendar_only_decision_excludes_gmail():
    d = goa.scopes_for_features(goa.Feature.CALENDAR_SLOT_FINDING)
    assert goa.GMAIL_READONLY not in d.scopes


def test_justifications_present_for_all_features():
    for feat in goa.Feature:
        assert feat in goa.FEATURE_JUSTIFICATION
        assert len(goa.FEATURE_JUSTIFICATION[feat]) > 20


def test_verification_scope_rows_cover_matrix():
    rows = goa.verification_scope_rows()
    assert len(rows) >= 3
    scopes = {r["scope"] for r in rows}
    assert goa.GMAIL_READONLY in scopes
    assert goa.CALENDAR_FREEBUSY in scopes


def test_screencast_checklist_min_items():
    items = goa.screencast_checklist()
    assert len(items) >= 8
    assert any("WebView" in i for i in items)
    assert any("gmail.readonly" in i for i in items)


def test_scopes_compatible_allowlisted():
    assert goa.scopes_are_compatible({"scopes": [goa.GMAIL_READONLY]})


# --- Migration / revocation (36–48) ---


def test_assess_broader_grant_triggers_reconsent():
    r = goa.assess_stored_scopes(
        [goa.GMAIL_READONLY, "https://www.googleapis.com/auth/gmail.modify"]
    )
    assert r.action == "revoke_reconsent"


def test_assess_full_calendar_triggers_reconsent():
    r = goa.assess_stored_scopes(["https://www.googleapis.com/auth/calendar"])
    assert r.action == "revoke_reconsent"


def test_assess_allowlisted_ok():
    r = goa.assess_stored_scopes([goa.GMAIL_READONLY, goa.CALENDAR_FREEBUSY])
    assert r.action == "ok"


def test_scopes_incompatible_when_forbidden_present():
    assert not goa.scopes_are_compatible(
        {"scopes": ["https://www.googleapis.com/auth/gmail.modify"]}
    )


def test_scopes_compatible_requires_needed_subset():
    payload = {"scopes": [goa.GMAIL_READONLY]}
    assert goa.scopes_are_compatible(payload, required=[goa.GMAIL_READONLY])
    assert not goa.scopes_are_compatible(payload, required=[goa.CALENDAR_FREEBUSY])


def test_migrate_broader_grant_wipes_token(tmp_path: Path):
    store_token(
        TOKEN_ACCOUNT,
        {
            "token": "t",
            "refresh_token": "r",
            "scopes": ["https://mail.google.com/"],
        },
        fallback_dir=tmp_path,
    )
    with patch.object(goa, "revoke_token_remote", return_value=True) as rev:
        result = goa.migrate_if_broader_grant(token_dir=tmp_path, revoke_remote=True)
    assert result.action == "revoke_reconsent"
    assert rev.called
    assert goa.load_google_token(token_dir=tmp_path) is None


def test_migrate_ok_keeps_token(tmp_path: Path):
    store_token(
        TOKEN_ACCOUNT,
        {"token": "t", "refresh_token": "r", "scopes": [goa.GMAIL_READONLY]},
        fallback_dir=tmp_path,
    )
    result = goa.migrate_if_broader_grant(token_dir=tmp_path)
    assert result.action == "ok"
    assert goa.google_connected(token_dir=tmp_path)


def test_disconnect_revokes_and_deletes(tmp_path: Path):
    store_token(
        TOKEN_ACCOUNT,
        {"token": "ACCESS", "refresh_token": "REFRESH", "scopes": [goa.GMAIL_READONLY]},
        fallback_dir=tmp_path,
    )
    with patch.object(goa, "revoke_token_remote", return_value=True) as rev:
        goa.disconnect_google(token_dir=tmp_path, revoke_remote=True)
    assert rev.call_args[0][0] in {"ACCESS", "REFRESH"}
    assert not goa.google_connected(token_dir=tmp_path)


def test_disconnect_without_remote(tmp_path: Path):
    store_token(
        TOKEN_ACCOUNT,
        {"refresh_token": "R", "scopes": [goa.GMAIL_READONLY]},
        fallback_dir=tmp_path,
    )
    with patch.object(goa, "revoke_token_remote") as rev:
        goa.disconnect_google(token_dir=tmp_path, revoke_remote=False)
    rev.assert_not_called()
    assert not goa.google_connected(token_dir=tmp_path)


def test_revoke_token_remote_empty_false():
    assert goa.revoke_token_remote("") is False


def test_revoke_token_remote_posts(monkeypatch):
    called = {}

    class _Resp:
        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=10):
        called["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(goa, "urlopen", fake_urlopen)
    assert goa.revoke_token_remote("tok123") is True
    assert "revoke" in called["url"]


def test_is_revocation_error_invalid_grant():
    assert goa.is_revocation_error(Exception("invalid_grant"))


def test_is_revocation_error_other():
    assert not goa.is_revocation_error(Exception("network down"))


# --- Client / env / PKCE / E2E mocked flows (49–60+) ---


def test_detect_env_explicit_production():
    assert (
        goa.detect_oauth_environment(explicit="production")
        == goa.OAuthEnvironment.PRODUCTION
    )


def test_detect_env_dev_from_client_id():
    assert (
        goa.detect_oauth_environment(client_id="myapp-dev.apps.googleusercontent.com")
        == goa.OAuthEnvironment.DEVELOPMENT
    )


def test_production_profile_requires_privacy_url():
    profile = goa.build_client_profile(
        client_type="installed",
        client_config={"client_id": "prod-client"},
        environment=goa.OAuthEnvironment.PRODUCTION,
        privacy_policy_url="",
        homepage_url="",
    )
    assert not profile.production_ready
    assert "production_requires_privacy_policy_url" in profile.issues


def test_production_profile_ready_with_urls():
    profile = goa.build_client_profile(
        client_type="installed",
        client_config={"client_id": "prod-client"},
        environment=goa.OAuthEnvironment.PRODUCTION,
        privacy_policy_url="https://example.com/privacy",
        homepage_url="https://example.com/",
    )
    assert profile.production_ready


def test_ensure_pkce_sets_verifier():
    flow = MagicMock()
    flow.code_verifier = None
    flow.autogenerate_code_verifier = False
    goa.ensure_pkce_enabled(flow)
    assert flow.autogenerate_code_verifier is True
    assert isinstance(flow.code_verifier, str) and len(flow.code_verifier) >= 43


def test_authorize_gmail_only_requests_readonly(tmp_path: Path, monkeypatch):
    creds_path = _client_file(tmp_path / "c.json")
    fake = FakeCreds(scopes=[goa.GMAIL_READONLY])
    flow = MagicMock()
    flow.code_verifier = None
    flow.run_local_server.return_value = fake
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    monkeypatch.setattr(goa, "google_libs_available", lambda: True)
    fake_svc = _probeable_gmail_service()
    with (
        patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
            return_value=flow,
        ) as from_file,
        patch("googleapiclient.discovery.build", return_value=fake_svc),
    ):
        outcome = authorize_gmail(
            credentials_path=creds_path, token_dir=tmp_path, interactive=True
        )
    assert outcome.service is fake_svc
    assert list(from_file.call_args[0][1]) == [goa.GMAIL_READONLY]
    assert flow.run_local_server.call_args.kwargs.get("open_browser") is True
    assert flow.run_local_server.call_args.kwargs.get("include_granted_scopes") == "true"


def test_authorize_calendar_only_requests_freebusy(tmp_path: Path, monkeypatch):
    creds_path = _client_file(tmp_path / "c.json")
    fake = FakeCreds(scopes=[goa.CALENDAR_FREEBUSY])
    flow = MagicMock()
    flow.code_verifier = "v" * 64
    flow.run_local_server.return_value = fake
    monkeypatch.setattr(goa, "google_libs_available", lambda: True)
    fake_svc = _probeable_calendar_service()
    with (
        patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
            return_value=flow,
        ) as from_file,
        patch("googleapiclient.discovery.build", return_value=fake_svc),
    ):
        outcome = authorize_calendar_freebusy(
            credentials_path=creds_path, token_dir=tmp_path, interactive=True
        )
    assert outcome.service is fake_svc
    assert list(from_file.call_args[0][1]) == [goa.CALENDAR_FREEBUSY]
    assert goa.GMAIL_READONLY not in from_file.call_args[0][1]


def test_scope_upgrade_only_when_missing(tmp_path: Path, monkeypatch):
    """Gmail token present; enabling FreeBusy triggers incremental reauth request."""
    store_token(
        TOKEN_ACCOUNT,
        {
            "token": "t",
            "refresh_token": "rt",
            "client_id": "c",
            "client_secret": "s",
            "scopes": [goa.GMAIL_READONLY],
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        fallback_dir=tmp_path,
    )
    creds_path = _client_file(tmp_path / "c.json")
    fake = FakeCreds(scopes=[goa.GMAIL_READONLY, goa.CALENDAR_FREEBUSY])
    flow = MagicMock()
    flow.code_verifier = "v" * 64
    flow.run_local_server.return_value = fake
    monkeypatch.setattr(goa, "google_libs_available", lambda: True)

    # Non-interactive must signal upgrade required, not silently widen.
    out = goa.authorize_google(
        credentials_path=creds_path,
        token_dir=tmp_path,
        features={goa.Feature.GMAIL_READ, goa.Feature.CALENDAR_SLOT_FINDING},
        interactive=False,
    )
    assert out.needs_reauth and out.reason == "scope_upgrade_required"

    with (
        patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
            return_value=flow,
        ) as from_file,
    ):
        out2 = goa.authorize_google(
            credentials_path=creds_path,
            token_dir=tmp_path,
            features={goa.Feature.GMAIL_READ, goa.Feature.CALENDAR_SLOT_FINDING},
            interactive=True,
        )
    assert set(from_file.call_args[0][1]) == {goa.GMAIL_READONLY, goa.CALENDAR_FREEBUSY}
    assert goa.CALENDAR_FREEBUSY in out2.granted_scopes


def test_partial_consent_persists_only_granted(tmp_path: Path, monkeypatch):
    creds_path = _client_file(tmp_path / "c.json")
    # User denied calendar — Google returns only gmail.readonly
    fake = FakeCreds(scopes=[goa.GMAIL_READONLY])
    flow = MagicMock()
    flow.code_verifier = "v" * 64
    flow.run_local_server.return_value = fake
    monkeypatch.setattr(goa, "google_libs_available", lambda: True)
    with patch(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        return_value=flow,
    ):
        out = goa.authorize_google(
            credentials_path=creds_path,
            token_dir=tmp_path,
            features={goa.Feature.GMAIL_READ, goa.Feature.CALENDAR_SLOT_FINDING},
            interactive=True,
        )
    assert goa.Feature.CALENDAR_SLOT_FINDING in out.denied_features
    assert goa.feature_available(goa.Feature.GMAIL_READ, out.granted_scopes)


def test_production_blocks_without_privacy_url(tmp_path: Path, monkeypatch):
    creds_path = _client_file(tmp_path / "c.json", client_id="prod-solid-client")
    monkeypatch.setattr(goa, "google_libs_available", lambda: True)
    monkeypatch.delenv("KARRIEREKRAKE_OAUTH_ALLOW_UNVERIFIED", raising=False)
    out = goa.authorize_google(
        credentials_path=creds_path,
        token_dir=tmp_path,
        features={goa.Feature.GMAIL_READ},
        interactive=True,
        oauth_env="production",
        privacy_policy_url="",
        homepage_url="",
    )
    assert out.reason == "production_not_ready"


def test_grant_outside_allowlist_wipes(tmp_path: Path, monkeypatch):
    creds_path = _client_file(tmp_path / "c.json")
    fake = FakeCreds(scopes=["https://www.googleapis.com/auth/gmail.modify"])
    flow = MagicMock()
    flow.code_verifier = "v" * 64
    flow.run_local_server.return_value = fake
    monkeypatch.setattr(goa, "google_libs_available", lambda: True)
    with (
        patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
            return_value=flow,
        ),
        patch.object(goa, "revoke_token_remote", return_value=True),
    ):
        out = goa.authorize_google(
            credentials_path=creds_path,
            token_dir=tmp_path,
            features={goa.Feature.GMAIL_READ},
            interactive=True,
        )
    assert out.needs_reauth and out.reason == "grant_outside_allowlist"
    assert not goa.google_connected(token_dir=tmp_path)


def test_save_creds_rejects_forbidden_scopes(tmp_path: Path):
    fake = FakeCreds(scopes=["https://mail.google.com/"])
    with pytest.raises(goa.ScopePolicyError):
        goa.save_creds_payload(fake, fallback_dir=tmp_path)


def test_gmail_auth_scopes_constant_readonly_only():
    assert gmail_auth.SCOPES == [goa.GMAIL_READONLY]
    assert all("modify" not in s for s in gmail_auth.SCOPES)


def test_account_fingerprint_stable():
    a = goa.account_fingerprint({"client_id": "abc"})
    b = goa.account_fingerprint({"client_id": "abc"})
    assert a == b and a != "default"


def test_load_client_config_installed(tmp_path: Path):
    p = _client_file(tmp_path / "x.json")
    kind, cfg = goa.load_client_config(p)
    assert kind == "installed" and cfg["client_id"]


def test_no_features_short_circuits():
    out = goa.authorize_google(
        credentials_path=Path("/nope"),
        token_dir=Path("/tmp"),
        features=set(),
        interactive=False,
    )
    assert out.reason == "no_features"

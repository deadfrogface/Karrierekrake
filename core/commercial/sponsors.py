"""Opt-in static sponsor cards. No SDK, remote pixels, identifiers or analytics."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from core.commercial.release_policy import load_policy, public_url
from core.commercial.license_file import feature_allowed
from core.platform_paths import user_data_dir


def campaign():
    try:
        value = load_policy().get('sponsor')
        if not isinstance(value, dict):
            return None
        for name in ('id', 'version', 'advertiser', 'title', 'body'):
            if not isinstance(value.get(name), str) or not value[name].strip() or len(value[name]) > 500:
                return None
        public_url(value['url'])
        return value
    except (ValueError, OSError, KeyError, TypeError):
        return None


def consent_path():
    return user_data_dir() / 'commerce/sponsor-consent.json'


def consented(value):
    try:
        state = json.loads(consent_path().read_text(encoding='utf-8'))
        return state == {'campaign': value['id'], 'version': value['version'], 'allowed': True}
    except (OSError, ValueError, TypeError):
        return False


def set_consent(allowed):
    path = consent_path()
    if not allowed:
        path.unlink(missing_ok=True)
        return
    value = campaign()
    if value is None:
        raise ValueError('no_sponsor_configured')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.consent-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'campaign': value['id'], 'version': value['version'], 'allowed': True}, handle)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def visible_campaign():
    value = campaign()
    return value if value and consented(value) and not feature_allowed('ad_free') else None

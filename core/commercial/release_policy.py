"""Public build configuration; never contains merchant API or signing secrets."""
from __future__ import annotations
import base64
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

FREE_FEATURES = frozenset({'profile_edit', 'local_cv_import', 'local_search_filters', 'dry_run',
                          'data_export', 'data_delete', 'local_backup', 'manual_application_tracking'})
PAID_FEATURES = frozenset({'ad_free', 'automatic_reply', 'google_connection', 'cloud_models',
                          'premium_assistance', 'premium_integrations'})


def config_path():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    return root / 'config/commercial_release.json'


def load_policy():
    value = json.loads(config_path().read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('invalid_commercial_policy')
    if value.get('environment') not in ('sandbox', 'production'):
        raise ValueError('invalid_commercial_environment')
    keys, enabled = value.get('public_keys'), value.get('enabled_features')
    if not isinstance(keys, dict) or not isinstance(enabled, list) or any(x not in PAID_FEATURES for x in enabled):
        raise ValueError('invalid_commercial_features')
    for key_id, encoded in keys.items():
        if not isinstance(key_id, str) or not key_id or len(key_id) > 128 or not isinstance(encoded, str):
            raise ValueError('invalid_commercial_key')
        if len(base64.b64decode(encoded, validate=True)) != 32:
            raise ValueError('invalid_commercial_key')
    if type(value.get('sales_enabled')) is not bool:
        raise ValueError('invalid_sales_flag')
    for field in ('checkout_url', 'customer_portal_url', 'cancellation_url', 'withdrawal_url', 'terms_url', 'privacy_url'):
        url = value.get(field, '')
        if url:
            public_url(url)
    if value['sales_enabled']:
        if value['environment'] != 'production' or not keys or not enabled:
            raise ValueError('sales_configuration_incomplete')
        if any(not value.get(field) for field in ('checkout_url', 'customer_portal_url', 'cancellation_url', 'withdrawal_url', 'terms_url', 'privacy_url')):
            raise ValueError('sales_information_incomplete')
    return value


def public_url(value, *, hosts=None):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('invalid_commercial_url')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or any(ord(c) < 32 for c in value)
            or (hosts is not None and parsed.hostname not in hosts)):
        raise ValueError('invalid_commercial_url')
    return value

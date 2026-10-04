"""Release trims must retain the Google schemas and local inference engine."""
import importlib.util
from pathlib import Path


def policy():
    spec = importlib.util.spec_from_file_location('trim_policy', Path(__file__).parents[1] / 'packaging/kk_content_policy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_google_discovery_schema_allowlist():
    p = policy()
    prefix = 'googleapiclient/discovery_cache/documents/'
    assert p.release_data_allowed(prefix + 'gmail.v1.json')
    assert p.release_data_allowed(prefix + 'calendar.v3.json')
    assert not p.release_data_allowed(prefix + 'compute.v1.json')
    assert not p.release_data_allowed(prefix.replace('/', '\\') + 'drive.v3.json')
    assert p.release_data_allowed('assets/oauth/desktop_client.json')
    assert p.release_data_allowed('models/qwen3.5-4b/model.gguf')


def test_legacy_providers_and_llama_server_excluded_but_product_paths_retained():
    p = policy()
    for name in ('integrations.mail.imap.adapter', 'integrations.mail.microsoft.oauth_pkce',
                 'integrations.calendar.caldav.client', 'integrations.calendar.microsoft.adapter',
                 'llama_cpp.server.app'):
        assert not p.module_allowed(name)
    for name in ('integrations.mail.google.adapter', 'integrations.calendar.google.adapter',
                 'core.cv_llm_runtime', 'core.cover_quality', 'llama_cpp.llama'):
        assert p.module_allowed(name)
    assert 'llama_cpp' in p.ALLOWED_COLLECT_ALL_PACKAGES
    assert 'googleapiclient' not in p.ANALYSIS_EXCLUDES

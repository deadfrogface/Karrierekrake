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


def test_unused_qt_parts_stay_out_of_the_windows_package():
    p = policy()
    for name in ('PySide6\\opengl32sw.dll', 'PySide6\\Qt6Quick.dll', 'PySide6/Qt6Qml.dll', 'PySide6/Qt6Pdf.dll',
                 'PySide6/plugins/imageformats/qpdf.dll', 'PySide6/plugins/platforms/qdirect2d.dll'):
        assert not p.lean_bundle_allowed(name, os_name='win32')
        assert p.lean_bundle_allowed(name, os_name='linux')  # only checked on Windows so far
    for name in ('PySide6/Qt6Core.dll', 'PySide6/Qt6Widgets.dll', 'PySide6/Qt6Svg.dll', 'PySide6/Qt6Network.dll',
                 'PySide6/plugins/platforms/qwindows.dll', 'PySide6/plugins/platforms/qoffscreen.dll',
                 'PySide6/plugins/imageformats/qsvg.dll', 'PySide6/plugins/styles/qmodernwindowsstyle.dll',
                 'PySide6/plugins/tls/qschannelbackend.dll', 'llama_cpp/lib/llama.dll', 'numpy.libs/libopenblas.dll'):
        assert p.lean_bundle_allowed(name, os_name='win32')


def test_only_german_and_english_qt_texts_ship():
    p = policy()
    for os_name in ('win32', 'linux', 'darwin'):
        assert p.lean_bundle_allowed('PySide6/translations/qtbase_de.qm', os_name=os_name)
        assert p.lean_bundle_allowed('PySide6/Qt/translations/qtbase_en.qm', os_name=os_name)
        assert not p.lean_bundle_allowed('PySide6/translations/qtbase_ja.qm', os_name=os_name)
        assert not p.lean_bundle_allowed('PySide6\\Qt\\translations\\qtdeclarative_de.qm', os_name=os_name)
    assert p.lean_bundle_allowed('translations/app_fr.qm', os_name='win32')  # not Qt's own folder


def test_legacy_providers_and_llama_server_excluded_but_product_paths_retained():
    p = policy()
    for name in ('integrations.calendar.microsoft.adapter', 'llama_cpp.server.app'):
        assert not p.module_allowed(name)
    for name in ('integrations.mail.imap.adapter', 'integrations.mail.imap.outlook_auth',
                 'integrations.mail.microsoft.oauth_pkce', 'integrations.calendar.local_ics',
                 'integrations.calendar.caldav.client', 'integrations.mail.google.adapter', 'integrations.calendar.google.adapter',
                 'core.cv_llm_runtime', 'core.cover_quality', 'llama_cpp.llama'):
        assert p.module_allowed(name)
    assert 'llama_cpp' in p.ALLOWED_COLLECT_ALL_PACKAGES
    assert 'googleapiclient' not in p.ANALYSIS_EXCLUDES

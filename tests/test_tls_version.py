import ssl
import pytest
from core.security.tls_version import openssl_release


@pytest.mark.parametrize(('info', 'version'), [((3, 5, 0, 9, 0), (3, 5, 9)),
    ((3, 6, 0, 3, 15), (3, 6, 3)), ((4, 0, 0, 3, 15), (4, 0, 3))])
def test_patch_slot_is_not_the_old_fix_slot(info, version):
    assert openssl_release(info) == version


def test_actual_stdlib_ssl_tuple_agrees_with_its_release_string():
    version = '.'.join(map(str, openssl_release(ssl.OPENSSL_VERSION_INFO)))
    assert ssl.OPENSSL_VERSION.startswith('OpenSSL ' + version + ' ')


@pytest.mark.parametrize('info', [(3, 5, 9), (3, 5, 0, 9, 16), (1, 1, 1, 0, 15),
                                 (3, 5, 1, 9, 15), (True, 5, 0, 9, 15)])
def test_ambiguous_old_or_invalid_tuples_are_not_silently_accepted(info):
    with pytest.raises(ValueError, match='release_info_invalid'):
        openssl_release(info)

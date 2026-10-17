import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest
from scripts.build_intel_cryptography import enrich_wheel, extract_source, build


def test_static_wheel_preserves_binary_and_supplies_verifiable_source_notices(tmp_path):
    wheel = tmp_path / 'cryptography.whl'
    root = 'cryptography-50.0.2.dist-info'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr(root + '/WHEEL', 'Wheel-Version: 1.0')
        archive.writestr(root + '/RECORD', '')
        archive.writestr('cryptography/_rust.abi3.so', b'actual-built-library-placeholder')
    sources = {'openssl': {'version': '4.0.3', 'sha256': 'a'*64,
                          'url': 'https://github.com/openssl/openssl/releases/download/openssl-4.0.3/source.tar.gz'}}
    enrich_wheel(wheel, sources, b'exact source license bytes', 'test compiler', 'test SDK')
    with zipfile.ZipFile(wheel) as archive:
        assert archive.read('cryptography/_rust.abi3.so') == b'actual-built-library-placeholder'
        assert archive.read(root+'/licenses/openssl-LICENSE.txt') == b'exact source license bytes'
        bom = json.loads(archive.read(root+'/sboms/sbom.json'))
        assert bom['components'][0]['version'] == '4.0.3'
        assert bom['components'][0]['hashes'][0]['content'] == 'a'*64
        for name, value, size in csv.reader(io.StringIO(archive.read(root+'/RECORD').decode())):
            if name.endswith('/RECORD'):
                assert not value and not size
                continue
            content = archive.read(name)
            assert len(content) == int(size)
            actual = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip('=')
            assert value == 'sha256='+actual


@pytest.mark.parametrize(('name', 'kind'), [('outside/file', tarfile.REGTYPE),
    ('source/../outside', tarfile.REGTYPE), ('source/link', tarfile.LNKTYPE)])
def test_source_archive_does_not_gain_unsafe_extract_paths(tmp_path, name, kind):
    path = tmp_path/'source.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        member = tarfile.TarInfo(name)
        member.type = kind
        archive.addfile(member)
    with pytest.raises(ValueError, match='source_archive_invalid'):
        extract_source(path, tmp_path/'out', 'source')


def test_signed_wheel_cannot_be_silently_rewritten(tmp_path):
    wheel = tmp_path/'signed.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('crypto.dist-info/WHEEL', 'Wheel-Version: 1.0')
        archive.writestr('crypto.dist-info/RECORD.jws', b'signature')
    before = wheel.read_bytes()
    with pytest.raises(ValueError, match='wheel_metadata_invalid'):
        enrich_wheel(wheel, {}, b'license', 'compiler', 'SDK')
    assert wheel.read_bytes() == before

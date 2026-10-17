from scripts.native_python_metadata import identify


def test_stdlib_extensions_and_exact_runtime_library_get_build_patch_version(tmp_path):
    stdlib = tmp_path / 'lib/python3.12'
    extension = stdlib / 'lib-dynload/_ssl.cpython-312-x86_64-linux-gnu.so'
    library = tmp_path / 'lib/libpython3.12.so.1.0'
    extension.parent.mkdir(parents=True)
    extension.touch()
    library.touch()
    owners = identify([extension, library], stdlib=stdlib, prefix=tmp_path,
                      libraries=[library], version='3.12.12')
    assert len(owners) == 2
    assert {owner['version'] for owner in owners.values()} == {'3.12.12'}


def test_third_party_extensions_and_vendor_dlls_do_not_inherit_python_version(tmp_path):
    stdlib = tmp_path / 'lib/python3.12'
    files = [stdlib / 'site-packages/vendor/native.so', stdlib / 'site-packages/native.so',
             tmp_path / 'DLLs/libssl-3.dll', tmp_path / 'DLLs/vendor/native.pyd']
    for file in files:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()
    assert identify(files, stdlib=stdlib, prefix=tmp_path, libraries=[], version='3.12.12') == {}
    assert identify(files, stdlib=stdlib, prefix=tmp_path, libraries=[], version='3.12.12', windows=True) == {}


def test_windows_stdlib_pyd_has_runtime_owner_but_crypto_dll_does_not(tmp_path):
    extension, vendor = tmp_path / 'DLLs/_ssl.pyd', tmp_path / 'DLLs/libssl-3.dll'
    extension.parent.mkdir()
    extension.touch(); vendor.touch()
    owners = identify([extension, vendor], stdlib=tmp_path / 'Lib', prefix=tmp_path,
                      libraries=[], version='3.12.12', windows=True)
    assert list(owners) == [str(extension.resolve())]

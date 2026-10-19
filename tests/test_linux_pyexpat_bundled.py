"""T06.05.04.03 (expat candidates): Python's XML parser must not use the system libexpat.

The Linux package ships Ubuntu 22.04's ``libexpat.so.1`` (2.4.7) because native
libraries (fontconfig via Qt) need it. Seven Ubuntu expat advisories have no
jammy fix. Python code (``xml.etree``/``xml.sax`` in dependencies) parses through
``pyexpat``; it is only outside that 2.4.7 copy if CPython uses its bundled expat.
The Linux builds use the same ``actions/setup-python`` CPython 3.12.15 as this
job, so this test pins that interpreter: bundled expat, no ``libexpat.so`` link.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux package only")

SYSTEM_JAMMY_EXPAT = (2, 4, 7)


def test_pyexpat_reports_bundled_expat_newer_than_jammy_system_copy() -> None:
    import pyexpat

    version = tuple(pyexpat.version_info)
    assert version > SYSTEM_JAMMY_EXPAT, pyexpat.EXPAT_VERSION


def test_pyexpat_extension_does_not_link_system_libexpat() -> None:
    import pyexpat

    path = getattr(pyexpat, "__file__", None)
    if path is None:
        return  # built into the interpreter: no dynamic libexpat at all
    ldd = shutil.which("ldd")
    if ldd is None:
        pytest.skip("ldd not available")
    out = subprocess.run([ldd, path], capture_output=True, text=True, check=True).stdout
    assert "libexpat.so" not in out, out

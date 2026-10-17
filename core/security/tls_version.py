"""Normalize CPython's legacy five-part OpenSSL 3+ version tuple."""
from __future__ import annotations


def openssl_release(info):
    # CPython retains (major, minor, fix, patch, status). In OpenSSL 3+
    # the old `fix` slot is zero: 3.5.9 is (3, 5, 0, 9, 0), not (3, 5, 9).
    if (not isinstance(info, (tuple, list)) or len(info) != 5
            or any(type(value) is not int for value in info)
            or info[0] < 3 or info[2] != 0 or not 0 <= info[4] <= 15
            or min(info) < 0):
        raise ValueError('openssl_release_info_invalid')
    # OpenSSL 3+ uses 0xMNN00PP0, with zero in the old status nibble.
    # Stable/prerelease identity must come from the live version text, not
    # the legacy status position.
    return info[0], info[1], info[3]

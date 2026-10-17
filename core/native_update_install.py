"""Verified native bundle staging and same-filesystem replacement with rollback.

Only app bundles are replaced. User profiles and model directories are untouched.
The detached POSIX helper survives replacement of the frozen executable.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from pathlib import PurePosixPath
import tempfile

from core.app_updates import REPOSITORY, _get
from core.native_updates import ASSET_SUFFIXES, current, runtime_target


def install_location() -> Path:
    executable = Path(sys.executable).resolve()
    if not getattr(sys, 'frozen', False):
        raise ValueError('native_install_requires_packaged_app')
    if sys.platform == 'darwin':
        root = executable.parents[2]
        if root.suffix != '.app' or executable.parent.name != 'MacOS':
            raise ValueError('native_install_location_invalid')
    else:
        root = executable.parent
    if str(root).startswith('/Volumes/') or not os.access(root.parent, os.W_OK):
        raise PermissionError('native_install_location_not_writable')
    return root


def _validate(manifest):
    installed = current()
    target = runtime_target()
    if not isinstance(manifest, dict) or not installed or target not in ASSET_SUFFIXES:
        raise ValueError('invalid_native_release')
    tag = manifest.get('tag', '')
    if not isinstance(tag, str) or not re.fullmatch(r'(?:update-[0-9]+-[a-f0-9]{12}|v[0-9A-Za-z._-]+)', tag):
        raise ValueError('invalid_native_release')
    filename = str(manifest.get('url', '')).rsplit('/', 1)[-1]
    expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{filename}'
    if (manifest.get('protocol') != 1 or manifest.get('url') != expected or manifest.get('target') != target
            or not re.fullmatch(r'Karrierekrake(?:-[A-Za-z0-9.]+)*-' + re.escape(ASSET_SUFFIXES[target]), filename)
            or type(manifest.get('size')) is not int or not 0 < manifest['size'] < 10_000_000_000
            or not re.fullmatch(r'[a-f0-9]{64}', str(manifest.get('sha256', '')))
            or not re.fullmatch(r'[a-f0-9]{40}', str(manifest.get('commit', '')))
            or type(manifest.get('sequence')) is not int or manifest['sequence'] <= installed['sequence']
            or manifest['commit'] == installed['commit']):
        raise ValueError('invalid_native_release')


def _validate_archive_members(members):
    """Keep tar hard links away from symbolic links, even on old interpreters.

    CPython gh-157190 / CVE-2026-82049: a hard link to a symlink can rebase
    its relative target and bypass older data filters. Native bundles need
    symlinks, but hard links must refer directly to a unique regular member.
    """
    if len(members) > 100000:
        raise ValueError('native_update_archive_invalid')
    by_name = {}
    total = 0
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or not path.parts or path.parts[0] != 'Karrierekrake'
                or '..' in path.parts or '\\' in member.name or path.as_posix() in by_name
                or member.size < 0):
            raise ValueError('native_update_archive_invalid')
        by_name[path.as_posix()] = member
        total += member.size
    if total > 20 * 1024**3:
        raise ValueError('native_update_archive_invalid')
    for member in members:
        if member.islnk():
            target = PurePosixPath(member.linkname)
            pointed = by_name.get(target.as_posix())
            if (target.is_absolute() or '..' in target.parts or '\\' in member.linkname
                    or pointed is None or not pointed.isfile()):
                raise ValueError('native_update_archive_invalid')
    return total


def stage_update(manifest, *, cancelled=lambda: False, progress=lambda done, total: None):
    _validate(manifest)
    root = install_location()
    if shutil.disk_usage(root.parent).free < manifest['size'] * 4 + 100_000_000:
        raise OSError('insufficient_update_space')
    stage = Path(tempfile.mkdtemp(prefix='.kk-native-update-', dir=root.parent))
    try:
        archive = stage / ('download.dmg' if sys.platform == 'darwin' else 'download.tar.gz')
        size = 0
        digest = hashlib.sha256()
        with _get(manifest['url'], stream=True) as response, archive.open('xb') as out:
            for block in response.iter_content(1024 * 1024):
                if cancelled():
                    raise RuntimeError('update_cancelled')
                size += len(block)
                if size > manifest['size']:
                    raise ValueError('native_update_size_mismatch')
                out.write(block)
                digest.update(block)
                progress(size, manifest['size'])
        if size != manifest['size'] or digest.hexdigest() != manifest['sha256']:
            raise ValueError('native_update_integrity_failed')
        payload = stage / 'payload'
        payload.mkdir()
        if sys.platform == 'darwin':
            mount = stage / 'mount'
            mount.mkdir()
            subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount), str(archive)],
                           check=True, capture_output=True, timeout=120)
            try:
                source = mount / 'Karrierekrake.app'
                shutil.copytree(source, payload / source.name, symlinks=True)
            finally:
                subprocess.run(['hdiutil', 'detach', str(mount)], check=True, capture_output=True, timeout=60)
            app = payload / 'Karrierekrake.app'
            executable = app / 'Contents/MacOS/Karrierekrake'
        else:
            with tarfile.open(archive, 'r:gz') as bundle:
                members = bundle.getmembers()
                expanded_bytes = _validate_archive_members(members)
                # Compressed size alone cannot predict the extracted footprint.
                # Fail before writing payload files while the old app is intact.
                required = expanded_bytes + len(members) * 4096 + 100_000_000
                if shutil.disk_usage(stage).free < required:
                    raise OSError('insufficient_update_space')
                # Python's data filter rejects devices, traversal and escaping links.
                bundle.extractall(payload, members=members, filter='data')
            app = payload / 'Karrierekrake'
            executable = app / 'Karrierekrake'
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError('native_update_executable_missing')
        identity_paths = [app / '_internal/native-current.json',
                          app / 'Contents/Resources/native-current.json',
                          app / 'Contents/Frameworks/native-current.json']
        identity = next((json.loads(p.read_text()) for p in identity_paths if p.is_file()), None)
        if not identity or any(identity.get(key) != manifest.get(key) for key in ('target', 'commit', 'sequence')):
            raise ValueError('native_update_identity_mismatch')
        if cancelled():
            raise RuntimeError('update_cancelled')
        state = {'root': str(root), 'app': str(app), 'commit': manifest['commit'],
                 'relative_executable': str(executable.relative_to(app))}
        (stage / 'transaction.json').write_text(json.dumps(state), encoding='utf-8')
        archive.unlink()
        return stage
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def launch_installer(stage):
    stage = Path(stage).resolve()
    state = json.loads((stage / 'transaction.json').read_text(encoding='utf-8'))
    root = install_location()
    app = Path(state['app'])
    if state['root'] != str(root) or not app.is_relative_to(stage) or stage.parent != root.parent:
        raise ValueError('native_update_transaction_invalid')
    backup = app
    marker = stage / 'healthy'
    executable = root / state['relative_executable']
    assignments = {'root': str(root), 'new': str(app), 'old': str(backup),
                   'marker': str(marker), 'exe': str(executable), 'stage': str(stage),
                   'commit': state['commit'], 'parent': str(os.getpid()),
                   'swapexe': str(app / state['relative_executable'])}
    script = '#!/bin/sh\n' + '\n'.join(k + '=' + shlex.quote(v) for k, v in assignments.items()) + r'''
# Do not replace files until the old application and its writers have exited.
i=0
while kill -0 "$parent" 2>/dev/null; do
    i=$((i+1)); [ "$i" -lt 120 ] || exit 1
    sleep 1
done
# Atomic exchange keeps a runnable installation even across power loss.
"$swapexe" --native-update-swap "$stage" || exit 1
KK_NATIVE_UPDATE_MARKER="$marker" KK_NATIVE_UPDATE_COMMIT="$commit" "$exe" &
child=$!
i=0
while [ ! -f "$marker" ] && kill -0 "$child" 2>/dev/null; do
    i=$((i+1)); [ "$i" -lt 90 ] || break
    sleep 1
done
if [ -f "$marker" ]; then
    # Keep the previous bundle for explicit recovery; never downgrade user data.
    printf '%s\n' success > "$stage/result"
    exit 0
fi
kill "$child" 2>/dev/null || true
sleep 3
kill -9 "$child" 2>/dev/null || true
wait "$child" 2>/dev/null || true
if "$exe" --native-update-swap "$stage"; then
    printf '%s\n' rollback > "$stage/result"
    "$exe" &
else
    printf '%s\n' recovery-required > "$stage/result"
fi
'''
    helper = stage / 'install.sh'
    helper.write_text(script, encoding='utf-8')
    env = os.environ.copy()
    env.pop('KK_NATIVE_UPDATE_MARKER', None)
    env.pop('KK_NATIVE_UPDATE_COMMIT', None)
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    subprocess.Popen(['/bin/sh', str(helper)], env=env, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def acknowledge_startup():
    marker = os.environ.pop('KK_NATIVE_UPDATE_MARKER', '')
    commit = os.environ.pop('KK_NATIVE_UPDATE_COMMIT', '')
    if not marker:
        return
    path = Path(marker)
    root = install_location()
    if (path.name != 'healthy' or path.parent.parent != root.parent
            or not path.parent.name.startswith('.kk-native-update-')
            or current().get('commit') != commit):
        return
    path.write_text(commit, encoding='ascii')


def exchange_bundles(stage):
    """Called by the staged frozen binary before Qt; no non-atomic fallback."""
    import ctypes
    stage = Path(stage).resolve(strict=True)
    state = json.loads((stage / "transaction.json").read_text(encoding="utf-8"))
    root, app = Path(state["root"]), Path(state["app"])
    relative = Path(state["relative_executable"])
    if (not getattr(sys, "frozen", False) or root.is_symlink() or app.is_symlink()
            or not root.is_dir() or not app.is_dir()
            or stage.parent != root.parent or not stage.name.startswith(".kk-native-update-")
            or not app.is_relative_to(stage) or relative.is_absolute() or ".." in relative.parts
            or Path(sys.executable).resolve() not in {(root / relative).resolve(), (app / relative).resolve()}):
        raise ValueError("native_update_transaction_invalid")
    libc = ctypes.CDLL(None, use_errno=True)
    left, right = os.fsencode(root), os.fsencode(app)
    if sys.platform == "darwin":
        swap = libc.renamex_np
        swap.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = swap(left, right, 2)  # RENAME_SWAP
    elif sys.platform.startswith("linux"):
        swap = libc.renameat2
        swap.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = swap(-100, left, -100, right, 2)  # AT_FDCWD, RENAME_EXCHANGE
    else:
        raise ValueError("unsupported_native_update_platform")
    if result:
        raise OSError(ctypes.get_errno(), "native_update_atomic_exchange_failed")
    # Persist both directory entries after the atomic exchange.
    for directory in (root.parent, app.parent):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        except OSError:
            # The exchange already committed; do not report it as unperformed
            # on filesystems that do not support syncing directory handles.
            pass
        finally:
            os.close(descriptor)
    return 0

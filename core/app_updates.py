"""Public GitHub release updates; data directories are never installation targets."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
import requests

REPOSITORY = 'deadfrogface/Karrierekrake'
API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
PROTOCOL = 1
CURRENT = 'update-current.json'
MODEL_PATH = 'models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf'
TARGETS = {'app': 'Karrierekrake.exe', 'model': MODEL_PATH}
MAX_BYTES = {'app': 2_000_000_000, 'model': 8_000_000_000}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def install_root() -> Path:
    return Path(sys.executable).resolve().parent


def read_current(root: Path) -> dict:
    try:
        return json.loads((root / CURRENT).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def validate_manifest(value: dict, tag: str) -> dict:
    if not isinstance(value, dict) or value.get('protocol') != PROTOCOL:
        raise ValueError('unsupported_update_protocol')
    if not re.fullmatch(r'update-[0-9]+-[a-f0-9]{12}', tag):
        raise ValueError('invalid_release_tag')
    if value.get('tag') != tag or type(value.get('sequence')) is not int or value['sequence'] <= 0:
        raise ValueError('invalid_release_version')
    if set(value.get('components', {})) != set(TARGETS):
        raise ValueError('invalid_update_components')
    for name, component in value['components'].items():
        if not isinstance(component, dict):
            raise ValueError('invalid_update_component')
        if component.get('path') != TARGETS[name]:
            raise ValueError('invalid_update_target')
        parts = component.get('parts')
        if not isinstance(parts, list) or not 1 <= len(parts) <= 8:
            raise ValueError('invalid_update_parts')
        for index, part in enumerate(parts, 1):
            asset = f'{name}-{index:03d}.bin'
            expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{asset}'
            if part.get('url') != expected or type(part.get('size')) is not int or not 0 < part['size'] <= 1_000_000_000:
                raise ValueError('invalid_update_part')
            if not re.fullmatch(r'[a-f0-9]{64}', str(part.get('sha256', ''))):
                raise ValueError('invalid_update_part_digest')
        if sum(part['size'] for part in parts) != component.get('size'):
            raise ValueError('invalid_update_part_sizes')
        if not re.fullmatch(r'[a-f0-9]{64}', str(component.get('sha256', ''))):
            raise ValueError('invalid_update_digest')
        if type(component.get('size')) is not int or not 0 < component['size'] <= MAX_BYTES[name]:
            raise ValueError('invalid_update_size')
    return value


def _get(url: str, *, stream=False):
    # No credentials, proxies still follow the user's requests/Windows setup.
    response = requests.get(url, timeout=(5, 20), stream=stream,
                            headers={'Accept': 'application/vnd.github+json' if url == API else 'application/octet-stream',
                                     'User-Agent': 'Karrierekrake-Updater/1'})
    response.raise_for_status()
    if urlparse(response.url).scheme != 'https':
        response.close()
        raise ValueError('insecure_update_redirect')
    return response


def _json(url: str) -> dict:
    with _get(url, stream=True) as response:
        body = bytearray()
        for block in response.iter_content(65536):
            body.extend(block)
            if len(body) > 1_000_000:
                raise ValueError('update_metadata_too_large')
        return json.loads(body)


def check_for_update(root: Path | None = None) -> dict | None:
    root = root or install_root()
    if not (root / CURRENT).is_file():
        return None  # Source checkouts and old standalone builds do not self-modify.
    try:
        release = _json(API)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise
    if release.get('draft') or release.get('prerelease'):
        return None
    tag = release.get('tag_name', '')
    expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/update-manifest.json'
    if not any(a.get('browser_download_url') == expected for a in release.get('assets', [])):
        return None
    manifest = validate_manifest(_json(expected), tag)
    return manifest if manifest['sequence'] > read_current(root).get('sequence', 0) else None


def changed_components(manifest: dict, root: Path) -> list[str]:
    current = read_current(root).get('components', {})
    return [name for name, item in manifest['components'].items()
            if current.get(name, {}).get('sha256') != item['sha256'] or not (root / item['path']).is_file()]


def stage_update(manifest: dict, root: Path | None = None, *, cancelled=lambda: False, progress=lambda done, total: None) -> Path:
    root = (root or install_root()).resolve()
    validate_manifest(manifest, manifest.get('tag', ''))
    if not (root / CURRENT).is_file():
        raise ValueError('managed_install_required')
    # Fail before downloading if the user cannot write the installation folder.
    with tempfile.TemporaryFile(dir=root):
        pass
    for relative in [*TARGETS.values(), CURRENT]:
        target = root / relative
        if not target.resolve().is_relative_to(root) or any(p.is_symlink() for p in [target, *target.parents] if p != root):
            raise ValueError('unsafe_install_target')
    stage = Path(tempfile.mkdtemp(prefix='.kk-update-', dir=root))
    try:
        changed = changed_components(manifest, root)
        required = sum(manifest['components'][n]['size'] for n in changed)
        backup_bytes = sum((root / TARGETS[n]).stat().st_size for n in changed if (root / TARGETS[n]).is_file())
        if shutil.disk_usage(root).free < required + backup_bytes + 100_000_000:
            raise OSError('insufficient_update_space')
        downloaded = 0
        for name in changed:
            item = manifest['components'][name]
            target = stage / item['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with target.open('wb') as out:
                for part in item['parts']:
                    part_hash = hashlib.sha256()
                    part_size = 0
                    with _get(part['url'], stream=True) as response:
                        for block in response.iter_content(1024 * 1024):
                            if cancelled():
                                raise RuntimeError("update_cancelled")
                            size += len(block)
                            part_size += len(block)
                            if size > item['size'] or part_size > part['size']:
                                raise ValueError('update_size_mismatch')
                            part_hash.update(block)
                            out.write(block)
                            downloaded += len(block)
                            progress(downloaded, required)
                    if part_size != part['size'] or part_hash.hexdigest() != part['sha256']:
                        raise ValueError('update_part_integrity_failed')
            if size != item['size'] or digest(target) != item['sha256']:
                raise ValueError('update_integrity_failed')
        # Every retained component must still match. No model download on UI changes.
        for name in set(TARGETS) - set(changed):
            if digest(root / TARGETS[name]) != manifest['components'][name]['sha256']:
                raise ValueError('installed_component_modified')
        (stage / CURRENT).write_text(json.dumps(manifest), encoding='utf-8')
        plan = {'root': str(root), 'files': [TARGETS[n] for n in changed] + [CURRENT],
                'hashes': {TARGETS[n]: manifest['components'][n]['sha256'] for n in changed}}
        (stage / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
        return stage
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


# Fixed helper, never downloaded from a release. Wait for normal GUI shutdown.
HELPER = r'''
param([string]$Stage, [int]$ParentId)
$ErrorActionPreference = 'Stop'
# A pwsh -> Python -> powershell.exe launch can inherit incompatible PS7
# modules. This fixed helper only needs modules shipped with its own shell.
$env:PSModulePath = Join-Path $PSHOME 'Modules'
$plan = Get-Content -LiteralPath (Join-Path $Stage 'plan.json') -Raw | ConvertFrom-Json
$root = $plan.root
$backup = Join-Path $Stage 'backup'
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Wait-Process -Id $ParentId -ErrorAction SilentlyContinue
$done = @()
try {
  foreach ($rel in $plan.files) {
    $source = Join-Path $Stage $rel
    $dest = Join-Path $root $rel
    $old = Join-Path $backup $rel
    if ($rel -ne 'update-current.json') {
      $expected = $plan.hashes.PSObject.Properties[$rel].Value
      if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'Integrity failure' }
    }
    New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
    New-Item -ItemType Directory -Path (Split-Path $old) -Force | Out-Null
    $existed = Test-Path -LiteralPath $dest
    if ($existed) { Copy-Item -LiteralPath $dest -Destination $old -Force }
    $done += @{ dest=$dest; old=$old; existed=$existed }
    Copy-Item -LiteralPath $source -Destination $dest -Force
  }
  if (Test-Path -LiteralPath (Join-Path $root 'update-error.txt')) { Remove-Item -LiteralPath (Join-Path $root 'update-error.txt') -Force -ErrorAction SilentlyContinue }
  Start-Process -FilePath (Join-Path $root 'Karrierekrake.exe') -WorkingDirectory $root
  Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
} catch {
  # Emit only the stable error identifier, never paths or downloaded contents.
  Write-Warning ('Update rollback: ' + $_.FullyQualifiedErrorId)
  [array]::Reverse($done)
  foreach ($entry in $done) {
    if ($entry.existed) { Copy-Item -LiteralPath $entry.old -Destination $entry.dest -Force }
    elseif (Test-Path -LiteralPath $entry.dest) { Remove-Item -LiteralPath $entry.dest -Force }
  }
  'Update fehlgeschlagen. Die vorherige Version wurde wiederhergestellt.' | Set-Content -LiteralPath (Join-Path $root 'update-error.txt')
  Start-Process -FilePath (Join-Path $root 'Karrierekrake.exe') -WorkingDirectory $root
}
'''


def launch_installer(stage: Path) -> None:
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        raise RuntimeError('windows_release_required')
    helper = stage / 'install.ps1'
    helper.write_text(HELPER, encoding='utf-8-sig')
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                      '-File', str(helper), '-Stage', str(stage), '-ParentId', str(os.getpid())],
                     creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)

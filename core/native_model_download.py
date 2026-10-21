"""Verified common GGUF download into native user data; never downloads apps."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

from core.app_updates import MODEL_PATH, REPOSITORY, _get
from core.cv_llm_runtime import (
    CV_MODEL_DIRNAME,
    CV_MODEL_FILENAME,
    CV_MODEL_SHA256,
    resolve_cv_model_path,
)


def available() -> bool:
    return resolve_cv_model_path() is not None


def validate(manifest: dict) -> dict:
    tag = manifest.get('tag', '')
    if not re.fullmatch(r'update-[0-9]+-[a-f0-9]{12}', tag):
        raise ValueError('invalid_model_release')
    model = manifest.get('model', {})
    if (model.get('path') != MODEL_PATH or model.get('sha256') != CV_MODEL_SHA256
            or type(model.get('size')) is not int or not 0 < model['size'] <= 8_000_000_000):
        raise ValueError('invalid_model_component')
    parts = model.get('parts', [])
    if not isinstance(parts, list) or not 1 <= len(parts) <= 8:
        raise ValueError('invalid_model_parts')
    for index, part in enumerate(parts, 1):
        url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/model-{index:03d}.bin'
        if (part.get('url') != url or type(part.get('size')) is not int
                or not 0 < part['size'] <= 1_000_000_000
                or not re.fullmatch(r'[a-f0-9]{64}', str(part.get('sha256', '')))):
            raise ValueError('invalid_model_part')
    if sum(part['size'] for part in parts) != model['size']:
        raise ValueError('invalid_model_sizes')
    return model


def download(manifest: dict, *, cancelled=lambda: False, progress=lambda done, total: None) -> Path:
    from guenther.model_manager import default_models_dir
    model = validate(manifest)
    dest = default_models_dir() / CV_MODEL_DIRNAME / CV_MODEL_FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        raise ValueError('unsafe_model_target')
    if shutil.disk_usage(dest.parent).free < model['size'] + 100_000_000:
        raise OSError('insufficient_model_space')
    handle, temporary = tempfile.mkstemp(prefix='.model-', suffix='.part', dir=dest.parent)
    temp = Path(temporary)
    full_hash = hashlib.sha256()
    done = 0
    try:
        with os.fdopen(handle, 'wb') as out:
            for part in model['parts']:
                part_hash = hashlib.sha256()
                size = 0
                with _get(part['url'], stream=True) as response:
                    for block in response.iter_content(1024 * 1024):
                        if cancelled():
                            raise RuntimeError('model_download_cancelled')
                        size += len(block)
                        done += len(block)
                        if size > part['size'] or done > model['size']:
                            raise ValueError('model_size_mismatch')
                        out.write(block)
                        full_hash.update(block)
                        part_hash.update(block)
                        progress(done, model['size'])
                if size != part['size'] or part_hash.hexdigest() != part['sha256']:
                    raise ValueError('model_part_integrity_failed')
        if done != model['size'] or full_hash.hexdigest() != model['sha256']:
            raise ValueError('model_integrity_failed')
        temp.replace(dest)
        return dest
    finally:
        temp.unlink(missing_ok=True)


def install_and_activate(manifest: dict, *, model_id: str | None = None,
                         cancelled=lambda: False, progress=lambda done, total: None) -> Path:
    """Use the same resumable installer and isolated probe as first-run setup.

    Without ``model_id`` the choice is automatic and uses the wizard's
    preselection gate (``setup_models.automatic_model_id`` →
    ``preselection_eligible``: fits AND attested peak AND HR approval). If
    the recommended model is not eligible there is no automatic choice
    (``model_choice_required``). An explicit ``model_id`` (user selection)
    installs any catalog model that fits this device.
    """
    from guenther import setup_models
    from guenther.setup_models import SETUP_MODEL_CATALOG
    validate(manifest)
    recommendation = setup_models.inspect_setup_device()
    if model_id is not None:
        fits = getattr(recommendation, "fits", None)
        if model_id not in SETUP_MODEL_CATALOG or not isinstance(fits, dict) or fits.get(model_id) is not True:
            raise ValueError("model_not_selectable")
    elif recommendation.model_id is None:
        raise RuntimeError("no_model_fits_available_hardware")
    else:
        model_id = setup_models.automatic_model_id(recommendation)
        if model_id is None:
            raise RuntimeError("model_choice_required")
    total_expected = SETUP_MODEL_CATALOG[model_id]["approx_bytes"]
    def report(value):
        done = getattr(value, "bytes_done", 0)
        total = getattr(value, "bytes_total", 0) or total_expected
        progress(min(done, total * .99), total)
    path = setup_models.install_recommended_model(model_id, cancelled=cancelled, progress=report)
    progress(total_expected, total_expected)
    return path

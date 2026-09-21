"""Screenshots + UIA tree dumps for black-box evidence (NEXT-06).

No Karrierekrake app imports.
"""

from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = ROOT / "artifacts" / "blackbox"


def artifact_dirs() -> dict[str, Path]:
    shots = ARTIFACT_ROOT / "screenshots"
    uia = ARTIFACT_ROOT / "uia"
    reports = ARTIFACT_ROOT / "reports"
    for p in (shots, uia, reports):
        p.mkdir(parents=True, exist_ok=True)
    return {"root": ARTIFACT_ROOT, "screenshots": shots, "uia": uia, "reports": reports}


def checkpoint_name(step: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in step)[:80]
    return f"{stamp}_{safe}"


def save_text_marker(step: str, payload: dict[str, Any]) -> Path:
    """Always-available evidence on Linux CI (no PNG)."""
    dirs = artifact_dirs()
    path = dirs["screenshots"] / f"{checkpoint_name(step)}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def capture_screenshot(app: Any, step: str) -> Path | None:
    """Capture window screenshot when pywinauto/Pillow available; else text marker."""
    dirs = artifact_dirs()
    name = checkpoint_name(step)
    png = dirs["screenshots"] / f"{name}.png"
    meta = {
        "step": step,
        "os": platform.system(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "png": None,
    }
    try:
        if app is not None and hasattr(app, "top_window"):
            win = app.top_window()
            if hasattr(win, "capture_as_image"):
                img = win.capture_as_image()
                img.save(str(png))
                meta["png"] = str(png)
                save_text_marker(step, meta)
                return png
    except Exception as exc:
        meta["error"] = str(exc)[:200]
    save_text_marker(step, meta)
    return None


def dump_uia_tree(app: Any, step: str) -> Path:
    """Dump control tree on automation failure."""
    dirs = artifact_dirs()
    path = dirs["uia"] / f"{checkpoint_name(step)}.txt"
    lines: list[str] = [
        f"step={step}",
        f"os={platform.system()}",
        f"ts={datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    try:
        if app is None:
            lines.append("(no app attached)")
        else:
            win = app.top_window()
            lines.append(f"title={getattr(win, 'window_text', lambda: '')()}")
            if hasattr(win, "print_control_identifiers"):
                # Capture print_control_identifiers into string via redirect
                import io
                from contextlib import redirect_stdout

                buf = io.StringIO()
                with redirect_stdout(buf):
                    win.print_control_identifiers(depth=8)
                lines.append(buf.getvalue())
            else:
                lines.append("(print_control_identifiers unavailable)")
    except Exception as exc:
        lines.append(f"uia_dump_error={exc!s}"[:300])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def on_failure(app: Any, step: str, error: str) -> dict[str, str]:
    shot = capture_screenshot(app, f"FAIL_{step}")
    tree = dump_uia_tree(app, f"FAIL_{step}")
    return {
        "step": step,
        "error": error[:500],
        "screenshot": str(shot) if shot else "",
        "uia_tree": str(tree),
    }

#!/usr/bin/env bash
# Idempotent development-environment bootstrap for Karrierekrake (Linux / Cloud Agent).
#
# Karrierekrake ships for Windows (setup.bat), but its Python code runs on Linux
# for development, CI-style testing, the CLI search pipeline, and the PySide6 GUI
# (via the VNC desktop / offscreen Qt). This script installs the OS libraries Qt
# and Playwright need, creates a virtualenv, installs Python dependencies, and
# fetches the Playwright Chromium browser. It is safe to run repeatedly.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
echo "[install] Karrierekrake dev environment bootstrap in ${ROOT}"

# --- System libraries for PySide6 (Qt xcb), Playwright, and headless GUI ---------
# The Qt "xcb" platform plugin needs the X/XCB client libraries even when running
# offscreen or under Xvfb. Use sudo when available (Cloud Agent default image).
APT_PACKAGES=(
  python3-venv python3-pip
  xvfb x11-utils
  libgl1 libegl1 libglib2.0-0 libdbus-1-3 fontconfig fonts-dejavu-core
  libxkbcommon0 libxkbcommon-x11-0
  libxcb1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0
  libxcb-render-util0 libxcb-render0 libxcb-shape0 libxcb-shm0 libxcb-sync1
  libxcb-util1 libxcb-xfixes0 libxcb-xkb1 libxcb-cursor0
  libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libxi6 libxtst6
  libnss3 libnspr4 libasound2t64
)

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  fi
fi

if command -v apt-get >/dev/null 2>&1; then
  echo "[install] Installing system libraries via apt-get..."
  export DEBIAN_FRONTEND=noninteractive
  ${SUDO} apt-get update -y
  ${SUDO} apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"
else
  echo "[install] apt-get not found; skipping system package step." >&2
fi

# --- Python virtual environment ---------------------------------------------------
if [ ! -x ".venv/bin/python" ]; then
  echo "[install] Creating virtualenv (.venv)..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
echo "[install] Installing Python dependencies (runtime + dev)..."
pip install -c constraints-runtime.txt -r requirements.txt

# --- Playwright browser -----------------------------------------------------------
echo "[install] Installing Playwright Chromium..."
if [ -n "${SUDO}" ] || [ "$(id -u)" -eq 0 ]; then
  python -m playwright install --with-deps chromium
else
  python -m playwright install chromium
fi

echo "[install] Done. Activate with 'source .venv/bin/activate'."

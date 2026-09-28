@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Karrierekrake Onefile Build ===

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv.
    exit /b 1
  )
) else (
  echo [1/5] Virtual environment found.
)

call ".venv\Scripts\activate.bat"

echo [2/5] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -c constraints-runtime.txt -r requirements-runtime.txt
python -m pip install -c constraints-runtime.txt -r requirements-dev.txt
if errorlevel 1 (
  echo Dependency install failed.
  exit /b 1
)

echo [3/5] Running tests...
python -m pytest -q
if errorlevel 1 (
  echo Tests failed — build aborted.
  exit /b 1
)

echo [3.5/5] Preparing bundled CV model (offline import)...
if defined KARRIEREKRAKE_CV_LLM_MODEL (
  python scripts\prepare_bundled_cv_model.py --src "%KARRIEREKRAKE_CV_LLM_MODEL%"
) else (
  python scripts\prepare_bundled_cv_model.py
)
if errorlevel 1 (
  echo Bundled CV model missing — set KARRIEREKRAKE_CV_LLM_MODEL or place GGUF under models cache.
  exit /b 1
)
set KARRIEREKRAKE_REQUIRE_BUNDLED_CV_MODEL=1

echo [4/5] Building ONEFILE EXE (Chromium NOT bundled; CV model IS bundled)...
if not exist "dist" mkdir dist
if not exist "build" mkdir build
python -m PyInstaller --noconfirm --clean packaging\Karrierekrake.spec
if errorlevel 1 (
  echo PyInstaller failed.
  exit /b 1
)

echo [4.5/5] Sidecar models next to EXE (same install folder)...
python scripts\prepare_bundled_cv_model.py --also-sidecar dist
if errorlevel 1 (
  echo Sidecar model copy failed.
  exit /b 1
)

echo [5/5] Verifying output...
if not exist "dist\Karrierekrake.exe" (
  echo EXE missing: dist\Karrierekrake.exe
  exit /b 1
)
if exist "dist\Karrierekrake\ms-playwright" (
  echo ERROR: Chromium must not be bundled.
  exit /b 1
)

echo.
echo Final artifact:
echo   %CD%\dist\Karrierekrake.exe
echo Browser installs on demand to:
echo   %%LOCALAPPDATA%%\Karrierekrake\browsers
exit /b 0

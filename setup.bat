@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo   Karrierekrake Setup
echo ========================================

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python wurde nicht gefunden.
  echo Bitte Python 3.11+ installieren und erneut setup.bat ausfuehren.
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo ERROR: Python 3.11 oder neuer wird benoetigt.
  exit /b 1
)

if not exist ".venv" (
  echo Erstelle virtuelle Umgebung...
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
REM End-user runtime only (pytest/ruff/pyinstaller live in requirements-dev.txt).
pip install -c constraints-runtime.txt -r requirements-runtime.txt
if errorlevel 1 (
  echo ERROR: Abhaengigkeiten konnten nicht installiert werden.
  exit /b 1
)

echo Installiere Playwright Chromium...
python -m playwright install chromium

if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "private" mkdir private
if not exist "private\cover_letters" mkdir private\cover_letters
if not exist "private\browser_profile" mkdir private\browser_profile

if not exist "config\profile.yaml" copy "config\profile.yaml.example" "config\profile.yaml" >nul
if not exist "config\application_profile.yaml" copy "config\application_profile.yaml.example" "config\application_profile.yaml" >nul
if not exist "config\settings.yaml" copy "config\settings.yaml.example" "config\settings.yaml" >nul
if not exist ".env" copy ".env.example" ".env" >nul

echo Initialisiere Datenbank...
python -c "from core.config import load_config; from core.database import Database; c=load_config(); Database(c.db_path); print('DB OK', c.db_path)"
if errorlevel 1 (
  echo ERROR: Datenbank-Initialisierung fehlgeschlagen.
  exit /b 1
)

echo Fuehre Basistests aus...
pip install -q -c constraints-runtime.txt pytest
python -m pytest tests -q
if errorlevel 1 (
  echo WARNUNG: Einige Tests sind fehlgeschlagen. Installation trotzdem fortgesetzt.
) else (
  echo Tests OK.
)

echo.
echo ========================================
echo   Setup erfolgreich!
echo ========================================
echo 1. Start Desktop-App: start.bat
echo 2. Profil/Einstellungen in der App bearbeiten
echo    (Daten: %%LOCALAPPDATA%%\Karrierekrake)
echo 3. Optional CLI-Suche:  run_search.bat
echo 4. EXE bauen:           build.bat
echo 5. Dev-Tools:           pip install -c constraints-runtime.txt -r requirements-dev.txt
echo.
echo Hinweis: Repo-config\*.yaml ist nur Legacy/CLI-Fallback.
echo.
pause
endlocal

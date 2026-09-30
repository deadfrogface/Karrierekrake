@echo off
REM Separate fake-mail test mode; profile stored under Karrierekrake-FakeMailDemo.
REM Start only the executable from the same downloaded artifact folder.
cd /d "%~dp0"
set "KK_EXE=%~dp0Karrierekrake.exe"
if not exist "%KK_EXE%" set "KK_EXE=%~dp0dist\Karrierekrake.exe"
if not exist "%KK_EXE%" (
  echo Karrierekrake.exe fehlt. Das gesamte Windows-Smoke-Artefakt entpacken.
  pause
  exit /b 1
)
start "" "%KK_EXE%" --fake-mail-demo

@echo off
REM Separate fake-mail test mode; profile stored under Karrierekrake-FakeMailDemo.
REM Start only the executable from the same downloaded artifact folder.
cd /d "%~dp0"
set "KK_EXE=%~dp0Karrierekrake.exe"
if not exist "%KK_EXE%" set "KK_EXE=%~dp0dist\Karrierekrake.exe"
if not exist "%KK_EXE%" if exist "%~dp0Karrierekrake-Windows.zip" (
  set "KK_DEMO_ARCHIVE=%~dp0Karrierekrake-Windows.zip"
  set "KK_DEMO_INSTALL=%~dp0Karrierekrake-FakeMail-Test"
  powershell -NoProfile -NonInteractive -Command "Expand-Archive -LiteralPath $env:KK_DEMO_ARCHIVE -DestinationPath $env:KK_DEMO_INSTALL -Force"
  if errorlevel 1 exit /b 1
)
if not exist "%KK_EXE%" set "KK_EXE=%~dp0Karrierekrake-FakeMail-Test\Karrierekrake.exe"
if not exist "%KK_EXE%" (
  echo Karrierekrake.exe fehlt. Das gesamte Windows-Smoke-Artefakt entpacken.
  pause
  exit /b 1
)
start "" "%KK_EXE%" --fake-mail-demo

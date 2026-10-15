@echo off
setlocal
set "CT3D_WORKSPACE_ROOT=%~dp0"
set "CT3D_APP=%~dp0runtime\CT3D.exe"
if not exist "%CT3D_APP%" (
  echo CT3D standalone application has not been built or staged yet.
  echo See docs/standalone-build.md. Source files are not an executable release.
  echo For development only, use tools/launch-development.bat.
  if "%~1"=="" pause
  exit /b 2
)
"%CT3D_APP%" --no-splash %*
exit /b %errorlevel%

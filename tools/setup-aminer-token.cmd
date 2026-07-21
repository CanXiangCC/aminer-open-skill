@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-aminer-token.ps1" %*
set EXITCODE=%ERRORLEVEL%

if "%~1"=="" (
  echo.
  pause
)

exit /b %EXITCODE%

@echo off
setlocal EnableExtensions
set ROOT=%~dp0
set PYTHONPATH=%ROOT%src;%PYTHONPATH%

if defined FORGE_PYTHON (
  "%FORGE_PYTHON%" -m forge %*
  exit /b %ERRORLEVEL%
)

if exist "%ROOT%python\python.exe" (
  "%ROOT%python\python.exe" -m forge %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m forge %*
  exit /b %ERRORLEVEL%
)

if exist "%SystemRoot%\py.exe" (
  "%SystemRoot%\py.exe" -3 -m forge %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if not errorlevel 1 (
  python -m forge %*
  exit /b %ERRORLEVEL%
)

for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%ProgramFiles%\Python312\python.exe"
  "%ProgramFiles%\Python311\python.exe"
) do (
  if exist %%P (
    %%P -m forge %*
    exit /b %ERRORLEVEL%
  )
)

echo Forge needs Python 3.11+. Set FORGE_PYTHON or install Python. 1>&2
exit /b 1

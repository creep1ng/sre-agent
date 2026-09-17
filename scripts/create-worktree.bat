@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

if exist "%CD%\.venv\Scripts\python.exe" goto venv

where py >nul 2>nul
if errorlevel 1 goto python
py -3 "%SCRIPT_DIR%create-worktree.py" %*
exit /b %ERRORLEVEL%

:venv
"%CD%\.venv\Scripts\python.exe" "%SCRIPT_DIR%create-worktree.py" %*
exit /b %ERRORLEVEL%

:python
python "%SCRIPT_DIR%create-worktree.py" %*
exit /b %ERRORLEVEL%

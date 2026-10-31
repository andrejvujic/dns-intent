@echo off
rem demo.cmd - runs demo.sh through Git Bash, for PowerShell, cmd and double-click.
rem
rem How to run (in the dns-intent folder):
rem     PowerShell:  .\scripts\demo.cmd
rem     cmd:         scripts\demo.cmd
rem     or double-click demo.cmd in Windows Explorer
rem
rem Everything the script does is described at the top of demo.sh.

setlocal
set "GIT_BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%GIT_BASH%" set "GIT_BASH=%LocalAppData%\Programs\Git\bin\bash.exe"
if not exist "%GIT_BASH%" (
    echo.
    echo  ERROR: Git Bash not found.
    echo  What to do: install Git from https://git-scm.com and run again.
    pause
    exit /b 1
)

"%GIT_BASH%" "%~dp0demo.sh"
rem Keep the window open on double-click so any error stays visible
if errorlevel 1 pause

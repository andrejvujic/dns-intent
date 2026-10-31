@echo off
rem start.cmd - runs start.sh through Git Bash, for PowerShell and cmd.
rem
rem How to run (in the dns-intent folder):
rem     PowerShell:  .\scripts\start.cmd
rem     cmd:         scripts\start.cmd
rem
rem Everything the script does is described at the top of start.sh.

setlocal
set "GIT_BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%GIT_BASH%" set "GIT_BASH=%LocalAppData%\Programs\Git\bin\bash.exe"
if not exist "%GIT_BASH%" (
    echo.
    echo  ERROR: Git Bash not found.
    echo  What to do: install Git from https://git-scm.com and run again.
    exit /b 1
)

"%GIT_BASH%" "%~dp0start.sh"

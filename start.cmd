@echo off
rem start.cmd - pokrece start.sh preko Git Bash-a, za PowerShell i cmd.
rem
rem Pokretanje (u dns-intent folderu):
rem     PowerShell:  .\start.cmd
rem     cmd:         start.cmd
rem
rem Sve sto skripta radi je opisano na vrhu start.sh.

setlocal
set "GIT_BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%GIT_BASH%" set "GIT_BASH=%LocalAppData%\Programs\Git\bin\bash.exe"
if not exist "%GIT_BASH%" (
    echo.
    echo  GRESKA: Git Bash nije pronadjen.
    echo  Sta uraditi: instalirajte Git sa https://git-scm.com pa pokrenite ponovo.
    exit /b 1
)

"%GIT_BASH%" "%~dp0start.sh"

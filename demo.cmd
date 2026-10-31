@echo off
rem demo.cmd - pokrece demo.sh preko Git Bash-a, za PowerShell, cmd i dvoklik.
rem
rem Pokretanje (u dns-intent folderu):
rem     PowerShell:  .\demo.cmd
rem     cmd:         demo.cmd
rem     ili dvoklik na demo.cmd u Windows Explorer-u
rem
rem Sve sto skripta radi je opisano na vrhu demo.sh.

setlocal
set "GIT_BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%GIT_BASH%" set "GIT_BASH=%LocalAppData%\Programs\Git\bin\bash.exe"
if not exist "%GIT_BASH%" (
    echo.
    echo  GRESKA: Git Bash nije pronadjen.
    echo  Sta uraditi: instalirajte Git sa https://git-scm.com pa pokrenite ponovo.
    pause
    exit /b 1
)

"%GIT_BASH%" "%~dp0demo.sh"
rem Na dvoklik prozor ostaje otvoren da se vidi eventualna greska
if errorlevel 1 pause

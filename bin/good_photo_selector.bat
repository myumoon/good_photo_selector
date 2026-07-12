@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo Usage: right-click files/folder -^> Send to -^> GootPhotoSelector
    pause
    exit /b 1
)

rem Derive project root from this script's location (bin\ -> ..\)
for %%i in ("%~dp0..") do set WIN_PROJECT=%%~fi
for /f "delims=" %%i in ('wsl wslpath -u "!WIN_PROJECT!"') do set WSL_PROJECT=%%i

rem Convert each argument to a WSL path
set WSL_ARGS=
:next_arg
if "%~1"=="" goto launch
for /f "delims=" %%i in ('wsl wslpath -u "%~1"') do set WSL_PATH=%%i
set WSL_ARGS=!WSL_ARGS! "!WSL_PATH!"
shift
goto next_arg

:launch
start "GootPhotoSelector" wsl bash --login "!WSL_PROJECT!/bin/good_photo_selector.sh" !WSL_ARGS!

@echo off
chcp 65001 >nul
setlocal
set "PYTHON_EXE="
set PYTHONUTF8=1

for %%i in ("%~dp0..") do set "PROJECT_ROOT=%%~fi"

echo ==============================
echo   GootPhotoSelector
echo ==============================

if "%~1"=="" (
    echo Usage: right-click files/folder -^> Send to -^> GootPhotoSelector
    set "STATUS=1"
    goto finish
)

for /f "delims=" %%i in ('where python.exe 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
if not defined PYTHON_EXE (
    echo [ERROR] Python executable ^(python.exe^) was not found in PATH.
    set "STATUS=1"
    goto finish
)

pushd "%PROJECT_ROOT%"
"%PYTHON_EXE%" "%PROJECT_ROOT%\src\select_photos.py" %*
set "STATUS=%ERRORLEVEL%"
popd

:finish
echo.
echo ==============================
if "%STATUS%"=="0" (
    echo   Done
) else (
    echo   Error ^(code %STATUS%^)
)
echo ==============================
echo Press Enter to close...
pause >nul
exit /b %STATUS%

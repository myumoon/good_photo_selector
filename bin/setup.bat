@echo off
chcp 65001 >nul
setlocal
set "STATUS=0"
set "INSTALL_ARGS="
set "NUMPY_VERSION="

echo ==============================
echo   GootPhotoSelector Setup
echo ==============================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.9 or newer was not found in PATH.
    echo Install Python and make sure the python command is available.
    set "STATUS=1"
    goto finish
)

call python --version
if errorlevel 1 (
    echo [ERROR] Python could not be started.
    set "STATUS=1"
    goto finish
)

where claude >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Claude Code was not found in PATH.
    echo Install the native Windows version of Claude Code.
    set "STATUS=1"
) else (
    call claude --version
    if errorlevel 1 set "STATUS=1"
)

call python -c "import PIL" >nul 2>&1
if errorlevel 1 set "INSTALL_ARGS=%INSTALL_ARGS% pillow"

call python -c "import numpy" >nul 2>&1
if errorlevel 1 (
    set "INSTALL_ARGS=%INSTALL_ARGS% numpy"
) else (
    for /f "delims=" %%V in ('call python -c "import numpy; print(numpy.__version__)"') do set "NUMPY_VERSION=%%V"
)

call python -c "import cv2" >nul 2>&1
if errorlevel 1 set "INSTALL_ARGS=%INSTALL_ARGS% opencv-python-headless"

echo.
if not defined INSTALL_ARGS (
    echo [OK] Python dependencies are already installed.
    goto finish
)

echo Installing missing Python dependencies...
if defined NUMPY_VERSION goto install_with_numpy_constraint
call python -m pip install %INSTALL_ARGS%
set "INSTALL_STATUS=%ERRORLEVEL%"
goto check_install_status

:install_with_numpy_constraint
set "CONSTRAINT_FILE=%TEMP%\good_photo_selector-%RANDOM%-%RANDOM%.txt"
>"%CONSTRAINT_FILE%" echo numpy==%NUMPY_VERSION%
call python -m pip install --constraint "%CONSTRAINT_FILE%" %INSTALL_ARGS%
set "INSTALL_STATUS=%ERRORLEVEL%"
del /q "%CONSTRAINT_FILE%" >nul 2>&1

:check_install_status
if not "%INSTALL_STATUS%"=="0" (
    echo [ERROR] Python dependency installation failed.
    set "STATUS=1"
) else (
    echo [OK] Python dependencies are ready.
)

:finish
echo.
echo Next: run bin\setup_sendto.bat to add GootPhotoSelector to Send To.
pause >nul
exit /b %STATUS%

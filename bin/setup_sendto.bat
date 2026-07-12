@echo off
echo Creating shortcut in Send To menu...

rem Derive good_photo_selector.bat path from this script's location
for %%i in ("%~dp0good_photo_selector.bat") do set BAT_PATH=%%~fi
set LINK=%APPDATA%\Microsoft\Windows\SendTo\GootPhotoSelector.lnk

powershell -Command ^
  "$s = (New-Object -COM WScript.Shell).CreateShortcut('%LINK%');" ^
  "$s.TargetPath = '%BAT_PATH%';" ^
  "$s.Description = 'Select best NEF photos and write XMP labels';" ^
  "$s.Save()"

if exist "%LINK%" (
    echo.
    echo [OK] "GootPhotoSelector" added to Send To menu
    echo %LINK%
) else (
    echo [ERROR] Failed to create shortcut
)
pause

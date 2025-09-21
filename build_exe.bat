@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Always run from this script's directory
set "HERE=%~dp0"
cd /d "%HERE%"

REM Parse optional flags: gui, onefile
set "WINDOWED="
set "ONEFILE="
:parseArgs
if "%~1"=="" goto argsDone
if /I "%~1"=="gui" (
  set "WINDOWED=--windowed"
) else if /I "%~1"=="onefile" (
  set "ONEFILE=--onefile"
) else (
  echo [ERROR] Unknown option: %~1
  echo Usage: build_exe.bat [gui] [onefile]
  goto error
)
shift
goto parseArgs
:argsDone

set "APP_NAME=AI-Game-Strategist"
set "ICON=assets\icons\app_icon.ico"
set "LOG=build.log"
if exist "%LOG%" del /q "%LOG%"

echo === Detecting Python ===
where py >NUL 2>&1 && (set "PYEXE=py -3") || (set "PYEXE=python")
%PYEXE% -m pip --version >NUL 2>&1 || (
  echo [ERROR] Python or pip not found. Install Python 3 and add to PATH.
  echo [ERROR] Python or pip not found. > "%LOG%"
  goto error
)

echo === Installing/updating dependencies ===
%PYEXE% -m pip install -U pip >> "%LOG%" 2>&1 || goto error
%PYEXE% -m pip install -U PyInstaller PyQt6 requests pillow pyaudio >> "%LOG%" 2>&1 || goto error

echo === Cleaning previous build ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

set "ADDDATA="
if exist assets set "ADDDATA=--add-data assets;assets"

set "ICON_ARG="
if exist "%ICON%" set "ICON_ARG=--icon %ICON%"

echo === Building %APP_NAME% ===
%PYEXE% -m PyInstaller --noconfirm --clean %WINDOWED% %ONEFILE% --name "%APP_NAME%" %ICON_ARG% %ADDDATA% main.py >> "%LOG%" 2>&1 || goto error

echo.
echo Build succeeded.
if "%ONEFILE%"=="" (
  echo Output folder: dist\%APP_NAME%\
  echo Main executable: dist\%APP_NAME%\%APP_NAME%.exe
) else (
  echo Single-file executable: dist\%APP_NAME%.exe
)
echo Options: %WINDOWED% %ONEFILE%
echo.
pause
goto :eof

:error
echo Build failed. See %LOG% for details.
if exist "%LOG%" type "%LOG%"
pause
exit /b 1

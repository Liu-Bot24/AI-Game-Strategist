@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Always run from this script's directory
set "HERE=%~dp0"
cd /d "%HERE%"

REM ---------------------------------------------
REM  Build AI-Game-Strategist into a Windows EXE
REM  Usage:
REM    build_exe.bat         (console build)
REM    build_exe.bat gui     (windowed build)
REM ---------------------------------------------

set "APP_NAME=AI-Game-Strategist"
set "ICON=assets\icons\app_icon.ico"
set "MODE=%1"

if /I "%MODE%"=="gui" (
  set "WINDOWED=--windowed"
) else (
  set "WINDOWED="
)

set "LOG=build.log"
if exist "%LOG%" del /q "%LOG%"

echo === Detect Python ===
where py >NUL 2>&1 && (set "PYEXE=py -3") || (set "PYEXE=python")
%PYEXE% -m pip --version >NUL 2>&1 || (
  echo [ERROR] Python or pip not found. Install Python 3 and add to PATH.
  echo [ERROR] Python or pip not found. > "%LOG%"
  goto :error
)

echo === Install/Update dependencies ===
%PYEXE% -m pip install -U pip >> "%LOG%" 2>&1 || goto :error
%PYEXE% -m pip install -U PyInstaller PyQt6 requests pillow pyaudio >> "%LOG%" 2>&1 || goto :error

echo === Clean previous build ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

set "ADDDATA="
if exist assets set "ADDDATA=--add-data assets;assets"

set "ICON_ARG="
if exist "%ICON%" set "ICON_ARG=--icon %ICON%"

echo === Build %APP_NAME% ===
%PYEXE% -m PyInstaller --noconfirm --clean %WINDOWED% --name "%APP_NAME%" %ICON_ARG% %ADDDATA% main.py >> "%LOG%" 2>&1 || goto :error

echo.
echo Build succeeded.
echo Output: dist\%APP_NAME%\%APP_NAME%.exe
echo Assets: dist\%APP_NAME%\assets
echo.
pause
goto :eof

:error
echo Build failed. See %LOG% for details.
if exist "%LOG%" type "%LOG%"
pause
exit /b 1

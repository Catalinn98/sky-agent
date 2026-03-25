@echo off
echo ============================================
echo  SKY Local Agent - Build Script
echo ============================================
echo.

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo [2/3] Building SKYAgent.exe with PyInstaller...
pyinstaller sky_agent.spec --noconfirm --clean
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Done!
echo.
echo  Output: dist\SKYAgent.exe
echo.
echo  Next steps:
echo   1. Test: double-click dist\SKYAgent.exe
echo   2. Create a GitHub Release and upload dist\SKYAgent.exe
echo   3. Copy the release download URL and update AGENT_DOWNLOAD_URL
echo      in integration\agent_launcher.py
echo.
pause

@echo off
echo ============================================
echo  SKY Local Agent - Build Script
echo ============================================
echo.

echo [1/5] Checking bundled libraries...
if not exist "lib\jre\bin\server\jvm.dll" (
    echo ERROR: Embedded JRE not found at lib\jre\
    echo        Run build_jre.bat first or copy a jlink-built JRE there.
    pause
    exit /b 1
)
if not exist "lib\sapjco3\sapjco3.jar" (
    echo ERROR: SAP JCo not found at lib\sapjco3\
    echo        Copy sapjco3.jar and sapjco3.dll from SAP Support Portal.
    pause
    exit /b 1
)
if not exist "lib\sapjco3\sapjco3.dll" (
    echo ERROR: sapjco3.dll not found at lib\sapjco3\
    pause
    exit /b 1
)
echo   [OK] lib\jre\          - Embedded JRE
echo   [OK] lib\sapjco3\      - SAP JCo

echo.
echo [2/5] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo [3/5] Building SKYAgent with PyInstaller (onedir)...
pyinstaller sky_agent.spec --noconfirm --clean
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [4/5] Verifying output...
if not exist "dist\SKYAgent\SKYAgent.exe" (
    echo ERROR: SKYAgent.exe not found in dist\SKYAgent\
    pause
    exit /b 1
)
if not exist "dist\SKYAgent\lib\jre\bin\server\jvm.dll" (
    echo ERROR: Embedded JRE not bundled correctly.
    pause
    exit /b 1
)
if not exist "dist\SKYAgent\lib\sapjco3\sapjco3.jar" (
    echo ERROR: SAP JCo not bundled correctly.
    pause
    exit /b 1
)
echo   [OK] dist\SKYAgent\SKYAgent.exe
echo   [OK] dist\SKYAgent\lib\jre\
echo   [OK] dist\SKYAgent\lib\sapjco3\

echo.
echo [5/5] Done!
echo.
echo  Output: dist\SKYAgent\
echo.
echo  Distribution contents:
echo   dist\SKYAgent\
echo     SKYAgent.exe          - SKY Agent executable
echo     lib\jre\              - Embedded Java Runtime (31 MB)
echo     lib\sapjco3\          - SAP JCo connector
echo.
echo  Next steps:
echo   1. Test: run dist\SKYAgent\SKYAgent.exe
echo   2. ZIP the dist\SKYAgent\ folder for distribution
echo   3. Create a GitHub Release and upload the ZIP
echo   4. Users extract ZIP and run SKYAgent.exe — no extra installs needed
echo.
pause

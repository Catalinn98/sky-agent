@echo off
echo ============================================
echo  SKY Agent - Build Embedded JRE
echo ============================================
echo.
echo  Creates a minimal JRE (~31 MB) for bundling with SKY Agent.
echo  Requires: JDK 21+ installed (JAVA_HOME must be set)
echo.

if "%JAVA_HOME%"=="" (
    echo ERROR: JAVA_HOME is not set.
    echo        Install JDK 21+ and set JAVA_HOME.
    echo        Download: https://adoptium.net/temurin/releases/
    pause
    exit /b 1
)

if not exist "%JAVA_HOME%\bin\jlink.exe" (
    echo ERROR: jlink.exe not found in JAVA_HOME.
    echo        Make sure you have a full JDK (not JRE) installed.
    pause
    exit /b 1
)

echo Using JDK: %JAVA_HOME%
echo.

if exist "lib\jre" (
    echo Removing old embedded JRE...
    rmdir /s /q "lib\jre"
)

echo Building minimal JRE with jlink...
echo  Modules: java.base, java.logging, java.naming, java.management
echo.

"%JAVA_HOME%\bin\jlink.exe" ^
    --module-path "%JAVA_HOME%\jmods" ^
    --add-modules java.base,java.logging,java.naming,java.management ^
    --output "lib\jre" ^
    --strip-debug ^
    --no-man-pages ^
    --no-header-files ^
    --compress=zip-6

if errorlevel 1 (
    echo ERROR: jlink failed.
    pause
    exit /b 1
)

echo.
echo [OK] Embedded JRE created at lib\jre\
echo.

:: Show size
for /f "tokens=3" %%a in ('dir /s "lib\jre" ^| findstr "File(s)"') do echo Size: %%a bytes
echo.
pause

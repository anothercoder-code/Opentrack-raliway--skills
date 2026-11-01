@echo off
setlocal
cd /d "%~dp0"
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" set "VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe"
set "VSDIR="
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -products * -latest -property installationPath`) do set "VSDIR=%%i"
if "%VSDIR%"=="" exit /b 2
call "%VSDIR%\VC\Auxiliary\Build\vcvarsall.bat" x86 >nul
if errorlevel 1 exit /b 2
set "VSLANG=1033"
if defined OT_IG_SDK (set "IGSDK=%OT_IG_SDK%") else (set "IGSDK=D:\opentrack\OTUndo\out\build-sdk\Windows Kits\10")
if exist "%IGSDK%\Lib\10.0.26100.0\um\x86\kernel32.lib" (
 set "INCLUDE=%IGSDK%\Include\10.0.26100.0\ucrt;%IGSDK%\Include\10.0.26100.0\shared;%IGSDK%\Include\10.0.26100.0\um;%INCLUDE%"
 set "LIB=%IGSDK%\Lib\10.0.26100.0\ucrt\x86;%IGSDK%\Lib\10.0.26100.0\um\x86;%LIB%"
)
if not exist out mkdir out
set "FLAGS=/nologo /O2 /MT /W4 /WX /utf-8 /D_CRT_SECURE_NO_WARNINGS /D_WIN32_WINNT=0x0601 /Isrc"
cl %FLAGS% /LD src\guard.c src\guard_policy.c src\fingerprint.c /Fo:out\ /Fe:out\ot-inspector-guard.dll /link /DEF:guard.def /MACHINE:X86 /INCREMENTAL:NO /MANIFEST:NO user32.lib advapi32.lib
if errorlevel 1 exit /b 1
cl %FLAGS% src\launcher.c src\fingerprint.c /Fo:out\ /Fe:out\ot-inspector-guard.exe /link /MACHINE:X86 /SUBSYSTEM:CONSOLE /INCREMENTAL:NO /MANIFEST:NO user32.lib advapi32.lib
if errorlevel 1 exit /b 1
cl %FLAGS% tests\policy_tests.c src\guard_policy.c /Fo:out\ /Fe:out\guard-policy-tests.exe /link /MACHINE:X86 /SUBSYSTEM:CONSOLE /INCREMENTAL:NO /MANIFEST:NO
if errorlevel 1 exit /b 1
cl %FLAGS% tests\adapter_tests.c src\guard_policy.c src\fingerprint.c /Fo:out\ /Fe:out\guard-adapter-tests.exe /link /MACHINE:X86 /SUBSYSTEM:CONSOLE /INCREMENTAL:NO /MANIFEST:NO user32.lib advapi32.lib
if errorlevel 1 exit /b 1
echo Build complete. No OpenTrack process was started.
exit /b 0

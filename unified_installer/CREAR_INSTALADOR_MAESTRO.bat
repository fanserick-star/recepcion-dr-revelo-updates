@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ================================================================
echo   CREADOR DEL INSTALADOR MAESTRO - CONSULTORIO DR. REVELO
echo ================================================================
echo.
echo Este proceso NO modifica los datos de Recepcion.
echo Lee la configuracion privada actual y genera un unico instalador.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_private_master.ps1"
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo No se pudo crear el instalador maestro. Codigo: %RC%
  pause
  exit /b %RC%
)

echo Instalador maestro creado correctamente en el Escritorio.
echo.
pause
exit /b 0

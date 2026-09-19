@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "ABRIR_HISTORIA_CLINICA.py"
  exit /b 0
)
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 "ABRIR_HISTORIA_CLINICA.py"
  exit /b 0
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "ABRIR_HISTORIA_CLINICA.py"
  exit /b 0
)
echo No se encontro Python. Instale Python 3.11 o superior y ejecute INSTALAR_HISTORIA_CLINICA.bat.
pause
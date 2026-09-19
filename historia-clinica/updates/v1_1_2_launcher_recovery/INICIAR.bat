@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "ABRIR_HISTORIA_CLINICA.py"
  exit /b 0
)
if exist ".venv\Scripts\python.exe" (
  start "" ".venv\Scripts\python.exe" "ABRIR_HISTORIA_CLINICA.py"
  exit /b 0
)
where py >nul 2>&1 && (start "" py -3 "ABRIR_HISTORIA_CLINICA.py" & exit /b 0)
where python >nul 2>&1 && (start "" python "ABRIR_HISTORIA_CLINICA.py" & exit /b 0)
echo No se encontro Python. Reinstale Historia Clinica.
pause
@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "ABRIR_HISTORIA_CLINICA.py"
) else (
  py -3 "ABRIR_HISTORIA_CLINICA.py"
)
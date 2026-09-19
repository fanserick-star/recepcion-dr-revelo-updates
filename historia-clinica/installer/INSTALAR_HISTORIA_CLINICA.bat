@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "SRC=%~dp0"
set "DEST=C:\Historia Clinica Dr Revelo"
echo.
echo =====================================================
echo   Historia Clinica - Dr. Armando Revelo
echo   Instalacion / reparacion segura
echo =====================================================
echo.
if not exist "%DEST%" mkdir "%DEST%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$src=[IO.Path]::GetFullPath('%SRC%'); $dst=[IO.Path]::GetFullPath('%DEST%');" ^
  "$protected=@('data','.venv','.env');" ^
  "Get-ChildItem -LiteralPath $src -Force | Where-Object { $protected -notcontains $_.Name } | ForEach-Object {" ^
  "  $target=Join-Path $dst $_.Name; if($_.PSIsContainer){ Copy-Item $_.FullName $target -Recurse -Force } else { Copy-Item $_.FullName $target -Force }" ^
  "};" ^
  "if(-not (Test-Path (Join-Path $dst 'data\historia_clinica.db'))){ Copy-Item (Join-Path $src 'data') (Join-Path $dst 'data') -Recurse -Force };" ^
  "if((-not (Test-Path (Join-Path $dst '.env'))) -and (Test-Path (Join-Path $src '.env'))){ Copy-Item (Join-Path $src '.env') (Join-Path $dst '.env') -Force }"
if errorlevel 1 goto :error

cd /d "%DEST%"
if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno del programa...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 goto :error
)
echo Instalando componentes necesarios...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error

echo Creando acceso directo...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell;" ^
  "$desk=[Environment]::GetFolderPath('Desktop');" ^
  "$lnk=$ws.CreateShortcut((Join-Path $desk 'Historia Clinica Dr Revelo.lnk'));" ^
  "$lnk.TargetPath='%DEST%\.venv\Scripts\pythonw.exe';" ^
  "$lnk.Arguments='""%DEST%\ABRIR_HISTORIA_CLINICA.py""';" ^
  "$lnk.WorkingDirectory='%DEST%';" ^
  "$lnk.Description='Historia Clinica - Dr. Armando Revelo';" ^
  "$lnk.Save()"

echo.
echo Instalacion completada.
echo La base local y la configuracion privada nunca se reemplazan durante actualizaciones.
start "" "%DEST%\.venv\Scripts\pythonw.exe" "%DEST%\ABRIR_HISTORIA_CLINICA.py"
exit /b 0

:error
echo.
echo No se pudo completar la instalacion.
echo Puede revisar la pantalla anterior y volver a ejecutar este archivo.
pause
exit /b 1
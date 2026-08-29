$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path '.').Path
$clean = Join-Path $repo 'installer_clean'
$root = Join-Path $clean 'buildroot'
$build = Join-Path $clean 'build'
$output = Join-Path $clean 'output'

foreach($p in @($root,$build,$output)){
  if(Test-Path $p){ Remove-Item $p -Recurse -Force }
  New-Item -ItemType Directory -Force $p | Out-Null
}

Write-Host '=== 1/9 Reconstruir versión publicada 4.3.72 ==='
@'
from pathlib import Path
import hashlib, json, shutil
root=Path('.')
out=root/'installer_clean'/'buildroot'
def join_parts(folder, prefix, target, expected):
    parts=sorted((root/folder).glob(prefix+'*'), key=lambda p:int(p.name.split('part')[-1]))
    if not parts: raise SystemExit(f'No hay partes para {target}')
    raw=b''.join(p.read_bytes() for p in parts)
    got=hashlib.sha256(raw).hexdigest()
    if got != expected: raise SystemExit(f'SHA incorrecto {target}: {got}')
    (out/target).write_bytes(raw)
join_parts('updates/v472','app.part','app.py','bd7de7b0486daa5257eaf8ec775fd868b1f55f44f0fd7be3ce16de832d3ae483')
join_parts('updates/v457','ABRIR_RECEPCION.part','ABRIR_RECEPCION.py','d5819a74e570c096d571971b244630d03342b258d32da93949d0bf1b5edb4d31')
shutil.copy2(root/'updates/v472/update_manifest.json',out/'update_manifest.json')
manifest=json.loads((out/'update_manifest.json').read_text(encoding='utf-8-sig'))
assert manifest['version']=='4.3.72'
print('PUBLICADA_OK', manifest['version'])
'@ | python -
if($LASTEXITCODE -ne 0){ throw 'No se pudo reconstruir v4.3.72' }

Write-Host '=== 2/9 Aplicar compatibilidad Smart App Control ==='
python installer_clean\patch_sac.py
if($LASTEXITCODE -ne 0){ throw 'Falló el parche Smart App Control' }

Write-Host '=== 3/9 Recuperar base limpia completa ==='
@'
from pathlib import Path
import hashlib, shutil, zipfile
root=Path('.')
out=root/'installer_clean'/'buildroot'
z=root/'installer_clean'/'base'/'clean_base_resources.zip'
expected='c7096e0f8318bf995b01e9940902d096415681416691657cb367344c237d69d5'
if not z.is_file(): raise SystemExit('Falta installer_clean/base/clean_base_resources.zip')
got=hashlib.sha256(z.read_bytes()).hexdigest()
if got != expected: raise SystemExit(f'SHA incorrecto de la base limpia: {got}')
temp=root/'installer_clean'/'_base_extract_sac'
if temp.exists(): shutil.rmtree(temp)
with zipfile.ZipFile(z) as f: f.extractall(temp)
for rel in ['static/index.html','mobile/index.html','azur_client.py','whatsapp_client.py','remote_agenda.py']:
    if not (temp/rel).is_file(): raise SystemExit(f'Falta {rel} en la base limpia')
shutil.copytree(temp/'static',out/'static',dirs_exist_ok=True)
shutil.copytree(temp/'mobile',out/'mobile',dirs_exist_ok=True)
for name in ['azur_client.py','whatsapp_client.py','remote_agenda.py']:
    shutil.copy2(temp/name,out/name)
shutil.rmtree(temp, ignore_errors=True)
print('BASE_LIMPIA_OK', got)
'@ | python -
if($LASTEXITCODE -ne 0){ throw 'No se pudo recuperar la base limpia' }
Copy-Item installer_clean\env.example installer_clean\buildroot\.env.example -Force
New-Item -ItemType Directory -Force installer_clean\buildroot\tools | Out-Null
Copy-Item installer_clean\restore_config.ps1 installer_clean\buildroot\tools\restore_config.ps1 -Force
New-Item -ItemType Directory -Force installer_clean\buildroot\data | Out-Null

Write-Host '=== 4/9 Validar código parcheado ==='
@'
from pathlib import Path
import ast
root=Path('installer_clean/buildroot')
for name in ['app.py','ABRIR_RECEPCION.py','azur_client.py','whatsapp_client.py','remote_agenda.py']:
    p=root/name
    compile(p.read_text(encoding='utf-8-sig'),name,'exec')
text=(root/'app.py').read_text(encoding='utf-8-sig')
tree=ast.parse(text)
third=set()
local={'azur_client','whatsapp_client','remote_agenda'}
std={'os','csv','io','hashlib','hmac','secrets','re','json','uuid','shutil','threading','sqlite3','zipfile','tempfile','subprocess','sys','time','socket','ipaddress','ctypes','webbrowser','unicodedata','difflib','datetime','typing','pathlib','urllib','xml','ssl'}
for n in ast.walk(tree):
    if isinstance(n,ast.Import):
        for a in n.names:
            top=a.name.split('.')[0]
            if top not in std|local: third.add(top)
    elif isinstance(n,ast.ImportFrom) and n.module:
        top=n.module.split('.')[0]
        if top not in std|local: third.add(top)
expected={'fastapi','pydantic','sqlalchemy','dotenv','pg8000'}
if not expected.issubset(third): raise SystemExit(f'Dependencias inesperadas: {sorted(third)}')
if 'psycopg' in third or 'import psycopg' in text: raise SystemExit('Quedó psycopg en app.py')
if 'postgresql+pg8000' not in text or 'pg8000_dbapi.connect' not in text: raise SystemExit('No quedó pg8000 correctamente aplicado')
print('APP_SAC_DEPENDENCIES_OK', sorted(third))
'@ | python -
if($LASTEXITCODE -ne 0){ throw 'El código SAC no pasó validación' }

Write-Host '=== 5/9 Construir Python portátil puro ==='
$scripts = Join-Path $root '.venv\Scripts'
$lib = Join-Path $root '.venv\Lib'
$site = Join-Path $lib 'site-packages'
New-Item -ItemType Directory -Force $scripts,$site | Out-Null
$embed = Join-Path $env:RUNNER_TEMP 'python-embed-sac.zip'
Invoke-WebRequest 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile $embed
Expand-Archive -LiteralPath $embed -DestinationPath $scripts -Force
python -m pip install --disable-pip-version-check --no-compile --target $site `
  'fastapi==0.115.6' 'pydantic==1.10.15' 'uvicorn==0.34.0' 'SQLAlchemy==2.0.36' `
  'pg8000==1.31.2' 'python-dotenv==1.0.1' 'python-multipart==0.0.20'
if($LASTEXITCODE -ne 0){ throw 'No se pudieron preparar las dependencias Python puras' }

Get-ChildItem (Join-Path $site 'pydantic') -Recurse -Filter '*.pyd' -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem (Join-Path $site 'sqlalchemy\cyextension') -Recurse -Filter '*.pyd' -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem $site -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'greenlet' -or $_.Name -like 'greenlet-*.dist-info' } | Remove-Item -Recurse -Force

$native = @(Get-ChildItem $site -Recurse -File | Where-Object { $_.Extension -in @('.pyd','.dll') })
if($native.Count -ne 0){
  $native | ForEach-Object { Write-Host "BINARIO_TERCERO=$($_.FullName)" }
  throw "El runtime contiene $($native.Count) binario(s) nativo(s) de terceros"
}

Copy-Item "$env:pythonLocation\Lib\tkinter" (Join-Path $lib 'tkinter') -Recurse -Force
foreach($f in @('_tkinter.pyd','tcl86t.dll','tk86t.dll')){
  $src=Join-Path $env:pythonLocation "DLLs\$f"
  if(Test-Path $src){ Copy-Item $src $scripts -Force }
}
if(Test-Path "$env:pythonLocation\tcl"){ Copy-Item "$env:pythonLocation\tcl" (Join-Path $scripts 'tcl') -Recurse -Force }
@'
python311.zip
.
..\..
..\Lib
..\Lib\site-packages
import site
'@ | Set-Content (Join-Path $scripts 'python311._pth') -Encoding ascii
@'
home = Scripts
include-system-site-packages = false
version = 3.11.9
'@ | Set-Content (Join-Path $root '.venv\pyvenv.cfg') -Encoding ascii

$env:DISABLE_SQLALCHEMY_CEXT_RUNTIME='1'
$py=Join-Path $scripts 'python.exe'
& $py -c "import fastapi,uvicorn,sqlalchemy,pg8000,dotenv,multipart; import azur_client,whatsapp_client,remote_agenda; print('PORTABLE_RUNTIME_SAC_OK')"
if($LASTEXITCODE -ne 0){ throw 'El runtime puro no pudo importar Recepción' }
& $py -c "import ssl,pg8000.dbapi as d; c=ssl.create_default_context();
try:
 d.connect(user='x',password='x',host='127.0.0.1',port=1,database='x',timeout=1,ssl_context=c)
except TypeError as e:
 raise
except Exception:
 print('PG8000_CONNECT_ARGS_OK')"
if($LASTEXITCODE -ne 0){ throw 'pg8000 no acepta la configuración segura esperada' }

Write-Host '=== 6/9 Probar backend v4.3.72 sin nube ==='
$smokeData=Join-Path $env:RUNNER_TEMP 'recepcion-sac-smoke-data'
if(Test-Path $smokeData){ Remove-Item $smokeData -Recurse -Force }
New-Item -ItemType Directory -Force $smokeData | Out-Null
$env:RP_FORCE_OFFLINE='1'
$env:RP_DATA_DIR=$smokeData
$app=Join-Path $root 'app.py'
$proc=Start-Process -FilePath $py -ArgumentList ('"'+$app+'"') -WorkingDirectory $root -PassThru -WindowStyle Hidden
try{
  $ok=$false
  for($i=0;$i -lt 80;$i++){
    Start-Sleep -Milliseconds 250
    try{
      $v=Invoke-RestMethod 'http://127.0.0.1:8000/api/version' -TimeoutSec 1
      if([string]$v.version -eq '4.3.72'){ $ok=$true; break }
    }catch{}
    if($proc.HasExited){ break }
  }
  if(-not $ok){ throw 'El backend SAC 4.3.72 no arrancó' }
  $home=Invoke-WebRequest 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 3
  if($home.StatusCode -ne 200){ throw 'La pantalla principal no respondió HTTP 200' }
  Write-Host 'BACKEND_SAC_SMOKE_OK'
}finally{
  if(-not $proc.HasExited){ Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
  Remove-Item $smokeData -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host '=== 7/9 Privacidad, icono y compilación ==='
foreach($rel in @('.env','data\recepcion.db','data\offline_cache.db')){
  $p=Join-Path $root $rel
  if(Test-Path $p){ throw "No se debe empaquetar: $p" }
}
$native=@(Get-ChildItem $site -Recurse -File | Where-Object { $_.Extension -in @('.pyd','.dll') })
if($native.Count -ne 0){ throw 'Hay binarios nativos de terceros dentro de site-packages' }
$icon=Join-Path $root 'static\doctor_icon.ico'
if(-not (Test-Path $icon)){ throw 'Falta doctor_icon.ico' }
Copy-Item $icon (Join-Path $build 'recepcion.ico') -Force
Copy-Item $icon (Join-Path $root 'recepcion.ico') -Force
if(-not (Test-Path 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')){ choco install innosetup -y --no-progress }
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer_clean\RecepcionDrReveloClean.iss
if($LASTEXITCODE -ne 0){ throw 'Falló la compilación de Inno Setup' }
$exe=Join-Path $output 'INSTALAR_RECEPCION_DR_REVELO_DESDE_CERO.exe'
if(-not (Test-Path $exe)){ throw 'No se generó el instalador SAC' }
$hash=(Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
"$hash  INSTALAR_RECEPCION_DR_REVELO_DESDE_CERO.exe" | Set-Content (Join-Path $output 'SHA256.txt') -Encoding ascii
Write-Host "INSTALLER_SAC_SHA256=$hash"

Write-Host '=== 8/9 Simular instalación limpia completa ==='
$dest=Join-Path $env:RUNNER_TEMP 'Recepcion SSD Nuevo SAC'
if(Test-Path $dest){ Remove-Item $dest -Recurse -Force }
$p=Start-Process -FilePath $exe -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$dest+'"')) -Wait -PassThru
if($p.ExitCode -ne 0){ throw "El instalador devolvió $($p.ExitCode)" }
foreach($rel in @('app.py','ABRIR_RECEPCION.py','azur_client.py','whatsapp_client.py','remote_agenda.py','update_manifest.json','static\index.html','mobile\index.html','.venv\Scripts\python.exe','.venv\Scripts\pythonw.exe','.env')){
  if(-not (Test-Path (Join-Path $dest $rel))){ throw "Falta tras instalar: $rel" }
}
$installedSite=Join-Path $dest '.venv\Lib\site-packages'
$installedNative=@(Get-ChildItem $installedSite -Recurse -File | Where-Object { $_.Extension -in @('.pyd','.dll') })
if($installedNative.Count -ne 0){ throw 'La instalación SAC contiene binarios nativos de terceros' }
$installedPy=Join-Path $dest '.venv\Scripts\python.exe'
$env:RP_FORCE_OFFLINE='1'
$env:RP_DATA_DIR=(Join-Path $dest 'data')
$env:DISABLE_SQLALCHEMY_CEXT_RUNTIME='1'
& $installedPy -c "import fastapi,uvicorn,sqlalchemy,pg8000; import azur_client,whatsapp_client,remote_agenda; print('INSTALLED_SAC_IMPORTS_OK')"
if($LASTEXITCODE -ne 0){ throw 'El runtime instalado SAC no funciona' }
$proc=Start-Process -FilePath $installedPy -ArgumentList ('"'+(Join-Path $dest 'app.py')+'"') -WorkingDirectory $dest -PassThru -WindowStyle Hidden
try{
  $ok=$false
  for($i=0;$i -lt 80;$i++){
    Start-Sleep -Milliseconds 250
    try{
      $v=Invoke-RestMethod 'http://127.0.0.1:8000/api/version' -TimeoutSec 1
      if([string]$v.version -eq '4.3.72'){ $ok=$true; break }
    }catch{}
    if($proc.HasExited){ break }
  }
  if(-not $ok){ throw 'La instalación limpia SAC no pudo arrancar Recepción' }
  Write-Host 'FULL_CLEAN_INSTALL_SAC_SMOKE_OK'
}finally{
  if(-not $proc.HasExited){ Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
}

Write-Host '=== 9/9 Verificación final de privacidad ==='
if(Test-Path (Join-Path $root '.env')){ throw 'Nunca se debe empaquetar un .env real' }
if(Test-Path (Join-Path $root 'data\recepcion.db')){ throw 'Nunca se debe empaquetar la base clínica local' }
if(Test-Path (Join-Path $root 'data\offline_cache.db')){ throw 'Nunca se debe empaquetar la cache clínica local' }
$all=(Get-Content installer_clean\RecepcionDrReveloClean.iss -Raw)+(Get-Content installer_clean\restore_config.ps1 -Raw)
foreach($forbidden in @('DROP TABLE','DELETE FROM whatsapp_cloud.events','WHATSAPP_ACCESS_TOKEN='+'EA')){
  if($all.Contains($forbidden)){ throw "Contenido prohibido: $forbidden" }
}
Write-Host 'PRIVACY_CHECK_OK'
Write-Host 'SAC_INSTALLER_BUILD_COMPLETE'

param(
    [string]$ReceptionRoot = 'C:\Recepcion Dr Revelo',
    [string]$OutputDir = ([Environment]::GetFolderPath('Desktop'))
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 72)
    Write-Host $Text
    Write-Host ('=' * 72)
}

function Write-Utf8NoBom([string]$Path, [string[]]$Lines) {
    [System.IO.File]::WriteAllLines($Path, $Lines, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-EnvMap([string]$Path) {
    $map = @{}
    foreach ($line in [System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8)) {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith('#')) { continue }
        $i = $line.IndexOf('=')
        if ($i -lt 1) { continue }
        $key = $line.Substring(0, $i).Trim()
        $value = $line.Substring($i + 1)
        $map[$key] = $value
    }
    return $map
}

function Copy-ReceptionConfig([string]$Source, [string]$Destination) {
    $lines = [System.Collections.Generic.List[string]]::new()
    $foundData = $false
    foreach ($line in [System.IO.File]::ReadAllLines($Source, [System.Text.Encoding]::UTF8)) {
        if ($line -match '^\s*RP_DATA_DIR\s*=') {
            $lines.Add('RP_DATA_DIR=data')
            $foundData = $true
        } else {
            $lines.Add($line)
        }
    }
    if (-not $foundData) { $lines.Add('RP_DATA_DIR=data') }
    Write-Utf8NoBom $Destination $lines.ToArray()
}

function Download-File([string]$Url, [string]$Destination) {
    $parent = Split-Path -Parent $Destination
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
}

function Assert-Sha256([string]$Path, [string]$Expected) {
    if (-not $Expected) { return }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "SHA256 incorrecto para $Path. Esperado=$Expected Real=$actual"
    }
}

function Download-ManifestFile($Entry, [string]$Target) {
    $parent = Split-Path -Parent $Target
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }

    if ($Entry.url) {
        Download-File ([string]$Entry.url) $Target
    } elseif ($Entry.parts) {
        $fs = [System.IO.File]::Open($Target, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try {
            foreach ($url in $Entry.parts) {
                $tmp = [System.IO.Path]::GetTempFileName()
                try {
                    Download-File ([string]$url) $tmp
                    $bytes = [System.IO.File]::ReadAllBytes($tmp)
                    $fs.Write($bytes, 0, $bytes.Length)
                } finally {
                    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
                }
            }
        } finally {
            $fs.Dispose()
        }
    } else {
        throw "Entrada de manifiesto sin url ni parts: $($Entry.path)"
    }
    Assert-Sha256 $Target ([string]$Entry.sha256)
}

function Ensure-InnoSetup {
    $candidates = @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    foreach ($p in $candidates) { if (Test-Path $p) { return $p } }

    Write-Host 'Inno Setup no está instalado. Instalando compilador...'
    $installer = Join-Path $env:TEMP 'innosetup-dr-revelo.exe'
    Download-File 'https://jrsoftware.org/download.php/is.exe' $installer
    $proc = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-') -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "Inno Setup devolvió código $($proc.ExitCode)" }
    foreach ($p in $candidates) { if (Test-Path $p) { return $p } }
    throw 'No se encontró ISCC.exe después de instalar Inno Setup.'
}

function Build-HistoriaRuntime([string]$HistoriaRoot) {
    Write-Step '3/7 Descargando Historia Clínica estable desde el canal oficial'
    $manifestUrl = 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-historia-runtime.json'
    $manifest = Invoke-RestMethod -UseBasicParsing -Uri $manifestUrl
    if (-not $manifest.version) { throw 'No se pudo determinar la versión estable de Historia Clínica.' }

    foreach ($entry in $manifest.files) {
        $target = Join-Path $HistoriaRoot ([string]$entry.path -replace '/', '\')
        Download-ManifestFile $entry $target
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $HistoriaRoot 'data') | Out-Null
    Write-Host "Historia Clínica descargada: v$($manifest.version)"

    Write-Step '4/7 Construyendo Python portátil de Historia Clínica'
    $runtime = Join-Path $HistoriaRoot '.venv'
    $scripts = Join-Path $runtime 'Scripts'
    $lib = Join-Path $runtime 'Lib'
    $site = Join-Path $lib 'site-packages'
    New-Item -ItemType Directory -Force -Path $scripts,$site | Out-Null

    $embedZip = Join-Path $env:TEMP 'python-3.11.9-embed-amd64.zip'
    Download-File 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' $embedZip
    Expand-Archive -LiteralPath $embedZip -DestinationPath $scripts -Force

    $fullInstaller = Join-Path $env:TEMP 'python-3.11.9-amd64-dr-revelo.exe'
    $fullRoot = Join-Path $env:TEMP ('python311-dr-revelo-' + [guid]::NewGuid().ToString('N'))
    Download-File 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' $fullInstaller
    $args = @(
        '/quiet',
        'InstallAllUsers=0',
        ('TargetDir="' + $fullRoot + '"'),
        'PrependPath=0',
        'Include_launcher=0',
        'Include_pip=1',
        'Include_tcltk=1',
        'Include_test=0',
        'Include_doc=0',
        'Shortcuts=0'
    )
    $p = Start-Process -FilePath $fullInstaller -ArgumentList $args -Wait -PassThru
    if ($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $fullRoot 'python.exe'))) {
        throw "No se pudo preparar Python 3.11.9 para Historia Clínica. Código=$($p.ExitCode)"
    }

    $builderPython = Join-Path $fullRoot 'python.exe'
    $requirements = Join-Path $HistoriaRoot 'requirements.txt'
    & $builderPython -m pip install --disable-pip-version-check --no-compile --target $site -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias de Historia Clínica.' }

    if (Test-Path (Join-Path $fullRoot 'Lib\tkinter')) {
        Copy-Item (Join-Path $fullRoot 'Lib\tkinter') (Join-Path $lib 'tkinter') -Recurse -Force
    }
    foreach ($f in @('_tkinter.pyd','tcl86t.dll','tk86t.dll')) {
        $src = Join-Path $fullRoot ('DLLs\' + $f)
        if (Test-Path $src) { Copy-Item $src $scripts -Force }
    }
    if (Test-Path (Join-Path $fullRoot 'tcl')) {
        Copy-Item (Join-Path $fullRoot 'tcl') (Join-Path $scripts 'tcl') -Recurse -Force
    }

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
'@ | Set-Content (Join-Path $runtime 'pyvenv.cfg') -Encoding ascii

    $portablePython = Join-Path $scripts 'python.exe'
    & $portablePython -c "import fastapi,uvicorn,pg8000,webview; print('HISTORIA_RUNTIME_OK')"
    if ($LASTEXITCODE -ne 0) { throw 'El Python portátil de Historia Clínica no pasó la prueba de importación.' }

    & $portablePython -m py_compile (Join-Path $HistoriaRoot 'app.py') (Join-Path $HistoriaRoot 'ABRIR_HISTORIA_CLINICA.py')
    if ($LASTEXITCODE -ne 0) { throw 'Historia Clínica no pasó la validación de sintaxis.' }

    Remove-Item -LiteralPath $fullRoot -Recurse -Force -ErrorAction SilentlyContinue
    return [string]$manifest.version
}

if ($env:OS -ne 'Windows_NT') {
    throw 'Este creador debe ejecutarse en Windows, desde la PC estable de Recepción.'
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$issSource = Join-Path $scriptRoot 'ConsultorioDrRevelo.iss'
if (-not (Test-Path $issSource)) { throw "Falta $issSource" }

$reception = [System.IO.Path]::GetFullPath($ReceptionRoot)
$envPath = Join-Path $reception '.env'
foreach ($required in @(
    $envPath,
    (Join-Path $reception 'ABRIR_RECEPCION.py'),
    (Join-Path $reception 'app.py'),
    (Join-Path $reception '.venv\Scripts\pythonw.exe')
)) {
    if (-not (Test-Path $required)) { throw "Falta archivo requerido de Recepción: $required" }
}

$envMap = Get-EnvMap $envPath
$dbUrl = if ($envMap.ContainsKey('DATABASE_URL')) { [string]$envMap['DATABASE_URL'] } else { '' }
if (-not $dbUrl.Trim()) { throw 'El .env de Recepción no contiene DATABASE_URL. No se puede preparar Historia Clínica automáticamente.' }

$out = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$work = Join-Path $env:TEMP ('dr-revelo-master-' + [guid]::NewGuid().ToString('N'))

try {
    $payload = Join-Path $work 'payload'
    $receptionPayload = Join-Path $payload 'recepcion'
    $historiaPayload = Join-Path $payload 'historia'
    New-Item -ItemType Directory -Force -Path $receptionPayload,$historiaPayload | Out-Null
    Copy-Item $issSource (Join-Path $work 'ConsultorioDrRevelo.iss') -Force

    Write-Step '1/7 Copiando Recepción estable sin bases de pacientes'
    $roboArgs = @(
        $reception,
        $receptionPayload,
        '/E','/R:1','/W:1','/NFL','/NDL','/NJH','/NJS','/NP',
        '/XD',
        (Join-Path $reception 'data'),
        (Join-Path $reception 'backups'),
        (Join-Path $reception 'update_backups'),
        (Join-Path $reception '__pycache__'),
        '/XF',
        '.env','*.db','*.sqlite','*.sqlite3','*.log',
        'BASE DE DATOS 2026.xlsx','HISTORICO_PACIENTES_2020_2025.csv'
    )
    $rp = Start-Process -FilePath 'robocopy.exe' -ArgumentList $roboArgs -Wait -PassThru -NoNewWindow
    if ($rp.ExitCode -gt 7) { throw "Robocopy falló al preparar Recepción. Código=$($rp.ExitCode)" }

    if (-not (Test-Path (Join-Path $receptionPayload 'ABRIR_RECEPCION.py'))) {
        throw 'La copia limpia de Recepción quedó incompleta.'
    }

    $recepVersion = 'actual'
    $recepManifest = Join-Path $reception 'update_manifest.json'
    if (Test-Path $recepManifest) {
        try { $recepVersion = [string]((Get-Content $recepManifest -Raw | ConvertFrom-Json).version) } catch {}
    }
    Write-Host "Recepción preparada: v$recepVersion"

    Write-Step '2/7 Incorporando configuración privada sin modificar la instalación actual'
    Copy-ReceptionConfig $envPath (Join-Path $payload 'recepcion_config.env')
    Write-Utf8NoBom (Join-Path $payload 'historia_config.env') @(
        '# Historia Clínica - Dr. Armando Revelo',
        '# Generado localmente desde la configuración privada de Recepción.',
        ('HISTORIA_DATABASE_URL=' + $dbUrl),
        'HISTORIA_SYNC_ENABLED=1'
    )

    $histVersion = Build-HistoriaRuntime $historiaPayload

    Write-Step '5/7 Incorporando WebView2'
    Download-File 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' (Join-Path $payload 'MicrosoftEdgeWebView2Setup.exe')

    Write-Step '6/7 Compilando instalador maestro privado'
    $iscc = Ensure-InnoSetup
    Push-Location $work
    try {
        & $iscc 'ConsultorioDrRevelo.iss'
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup no pudo compilar el instalador maestro.' }
    } finally {
        Pop-Location
    }

    $built = Join-Path $work 'output\INSTALAR_CONSULTORIO_DR_REVELO_MAESTRO.exe'
    if (-not (Test-Path $built)) { throw 'No se generó el instalador maestro.' }

    $final = Join-Path $out 'INSTALAR_CONSULTORIO_DR_REVELO_MAESTRO.exe'
    Copy-Item $built $final -Force
    $hash = (Get-FileHash $final -Algorithm SHA256).Hash.ToLowerInvariant()
    $shaFile = Join-Path $out 'INSTALAR_CONSULTORIO_DR_REVELO_MAESTRO_SHA256.txt'
    Write-Utf8NoBom $shaFile @("$hash  INSTALAR_CONSULTORIO_DR_REVELO_MAESTRO.exe")

    Write-Step '7/7 LISTO'
    Write-Host "Recepción incluida: v$recepVersion"
    Write-Host "Historia Clínica incluida: v$histVersion"
    Write-Host "Instalador: $final"
    Write-Host "SHA256: $hash"
    Write-Host ''
    Write-Host 'IMPORTANTE: este EXE contiene las credenciales privadas del consultorio.'
    Write-Host 'Guárdalo solo en almacenamiento privado. No lo subas al repositorio público.'
}
finally {
    if (Test-Path $work) {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

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

    $hasUrl = ($Entry.PSObject.Properties.Name -contains 'url') -and (-not [string]::IsNullOrWhiteSpace([string]$Entry.url))
    $hasParts = ($Entry.PSObject.Properties.Name -contains 'parts') -and ($null -ne $Entry.parts) -and (@($Entry.parts).Count -gt 0)

    if ($hasUrl) {
        Download-File ([string]$Entry.url) $Target
    } elseif ($hasParts) {
        $fs = [System.IO.File]::Open($Target, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try {
            foreach ($url in @($Entry.parts)) {
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
    $expectedSha = if ($Entry.PSObject.Properties.Name -contains 'sha256') { [string]$Entry.sha256 } else { '' }
    Assert-Sha256 $Target $expectedSha
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

    # El runtime embebible no se instala en Windows: vive por completo dentro de Historia Clínica.
    # Esto evita depender del instalador MSI/EXE de Python, del registro o de permisos de instalación.
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
    $portablePythonw = Join-Path $scripts 'pythonw.exe'
    if (-not (Test-Path $portablePython) -or -not (Test-Path $portablePythonw)) {
        throw 'El paquete embebible de Python quedó incompleto.'
    }

    Write-Host 'Preparando pip dentro del Python portátil...'
    $getPip = Join-Path $env:TEMP 'get-pip-dr-revelo.py'
    Download-File 'https://bootstrap.pypa.io/get-pip.py' $getPip
    & $portablePython $getPip --disable-pip-version-check --no-warn-script-location --target $site
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar pip dentro del Python portátil de Historia Clínica.' }

    $requirements = Join-Path $HistoriaRoot 'requirements.txt'
    & $portablePython -m pip install --disable-pip-version-check --no-compile --upgrade --target $site -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias de Historia Clínica.' }

    # Verifica también el backend EdgeChromium usado realmente por Historia Clínica.
    & $portablePython -c "import fastapi,uvicorn,pg8000,webview; import webview.platforms.edgechromium; print('HISTORIA_RUNTIME_OK')"
    if ($LASTEXITCODE -ne 0) { throw 'El Python portátil de Historia Clínica no pasó la prueba de WebView2.' }

    & $portablePython -m py_compile (Join-Path $HistoriaRoot 'app.py') (Join-Path $HistoriaRoot 'ABRIR_HISTORIA_CLINICA.py')
    if ($LASTEXITCODE -ne 0) { throw 'Historia Clínica no pasó la validación de sintaxis.' }
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
    & robocopy.exe @roboArgs
    $roboCode = $LASTEXITCODE
    if ($roboCode -gt 7) { throw "Robocopy falló al preparar Recepción. Código=$roboCode" }

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

param(
    [Parameter(Mandatory = $true)][ValidateSet('Reception','Historia')][string]$App,
    [Parameter(Mandatory = $true)][string]$StageRoot,
    [Parameter(Mandatory = $true)][string]$SourceDir
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$SharedRoot = 'C:\ProgramData\ConsultorioDrRevelo'
$PythonRoot = Join-Path $SharedRoot 'Python311'
$PythonExe = Join-Path $PythonRoot 'python.exe'
$BackupRoot = Join-Path $SharedRoot 'InstallerBackups'
$LogRoot = Join-Path $SharedRoot 'InstallerLogs'
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force $SharedRoot, $BackupRoot, $LogRoot | Out-Null
$LogFile = Join-Path $LogRoot ("install-$App-$Timestamp.log")
Start-Transcript -Path $LogFile -Force | Out-Null

if ($App -eq 'Reception') {
    $Target = 'C:\Recepcion Dr Revelo'
    $Payload = Join-Path $StageRoot 'payload'
    $Requirements = Join-Path $StageRoot 'requirements.txt'
    $LauncherInstaller = Join-Path $StageRoot 'launcher-setup.exe'
    $ExpectedVersion = '4.6.7'
    $VersionFile = 'recepcion-version.json'
} else {
    $Target = 'C:\Historia Clinica Dr Revelo'
    $Payload = Join-Path $StageRoot 'payload'
    $Requirements = Join-Path $StageRoot 'requirements.txt'
    $LauncherInstaller = Join-Path $StageRoot 'launcher-setup.exe'
    $ExpectedVersion = '1.3.73'
    $VersionFile = 'historia-version.json'
}

function Write-Step([string]$Message) { Write-Host "[Consultorio/$App] $Message" }

function Invoke-Checked {
    param([Parameter(Mandatory = $true)][string]$FilePath, [Parameter()][string[]]$Arguments = @())
    $output = & $FilePath @Arguments 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $output) { Write-Host $line }
    if ($null -eq $code) { $code = 0 }
    if ($code -ne 0) { throw "El proceso $FilePath termino con codigo $code." }
}

function Stop-AppProcesses([string]$Root) {
    try {
        Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase)
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch { Write-Step 'No se pudieron enumerar todos los procesos; continuo con la instalacion.' }
}

function Move-ToBackup([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root)) { return $null }
    $session = Join-Path $BackupRoot "$Timestamp-$App"
    New-Item -ItemType Directory -Force $session | Out-Null
    $dest = Join-Path $session 'previous'
    Move-Item -LiteralPath $Root -Destination $dest
    return $dest
}

function Restore-Backup([string]$Root, [AllowNull()][string]$Backup) {
    if (Test-Path -LiteralPath $Root) { Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue }
    if ($Backup -and (Test-Path -LiteralPath $Backup)) { Move-Item -LiteralPath $Backup -Destination $Root }
}

function Copy-ProtectedState([AllowNull()][string]$Backup, [string]$Dest) {
    if (-not $Backup -or -not (Test-Path -LiteralPath $Backup)) { return }
    $dirs = @('data','backups','update_backups','logs','documentos','documents','exports','exportaciones','reportes','uploads')
    foreach ($dir in $dirs) {
        $src = Join-Path $Backup $dir
        if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $Dest $dir) -Recurse -Force }
    }
    $envFile = Join-Path $Backup '.env'
    if (Test-Path -LiteralPath $envFile) { Copy-Item -LiteralPath $envFile -Destination (Join-Path $Dest '.env') -Force }
    foreach ($pattern in @('*.db','*.sqlite','*.sqlite3','*.mdb','*.accdb','*.xls','*.xlsx','*.csv')) {
        Get-ChildItem -LiteralPath $Backup -File -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Dest $_.Name) -Force
        }
    }
}

function Import-PrivateEnvIfNeeded([string]$Dest) {
    $envPath = Join-Path $Dest '.env'
    if (Test-Path -LiteralPath $envPath) { return }
    $sidecar = Join-Path $SourceDir 'consultorio.private.env'
    if (-not (Test-Path -LiteralPath $sidecar)) {
        Write-Step 'No hay configuracion privada nueva. Se instala el programa y la configuracion online queda pendiente.'
        return
    }
    $text = Get-Content -LiteralPath $sidecar -Raw
    if ($text -notmatch '(?m)^DATABASE_URL=.+$' -and $text -notmatch '(?m)^HISTORIA_DATABASE_URL=.+$') {
        throw 'consultorio.private.env no parece una configuracion valida.'
    }
    Copy-Item -LiteralPath $sidecar -Destination $envPath -Force
    try { & icacls.exe $envPath /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' "$env:USERNAME`:F" | Out-Null } catch {}
}

function Ensure-Python {
    $ok = $false
    if (Test-Path -LiteralPath $PythonExe) {
        try { $ok = ((& $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim() -eq '3.11') } catch { $ok = $false }
    }
    if ($ok) { return }

    $runtime = Join-Path $StageRoot 'python-runtime'
    $runtimePython = Join-Path $runtime 'python.exe'
    if (-not (Test-Path -LiteralPath $runtimePython)) { throw 'Falta el runtime privado Python 3.11 en el instalador.' }

    if (Test-Path -LiteralPath $PythonRoot) { Remove-Item -LiteralPath $PythonRoot -Recurse -Force }
    New-Item -ItemType Directory -Force $PythonRoot | Out-Null
    Copy-Item -Path (Join-Path $runtime '*') -Destination $PythonRoot -Recurse -Force

    if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'El runtime privado Python 3.11 no se copio correctamente.' }
    $version = (& $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($version -ne '3.11') { throw "Runtime privado Python inesperado: $version" }
    Write-Step 'Runtime privado Python 3.11 listo.'
}

function Ensure-Venv([string]$Dest) {
    $venv = Join-Path $Dest '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) { Invoke-Checked $PythonExe @('-m','venv',$venv) }
    Invoke-Checked $venvPython @('-m','pip','install','--disable-pip-version-check','--no-index','--find-links',(Join-Path $StageRoot 'wheelhouse'),'-r',$Requirements)
    return $venvPython
}

function Validate-PayloadVersion([string]$Dest) {
    $vf = Join-Path $Dest $VersionFile
    if (-not (Test-Path -LiteralPath $vf)) { throw "Falta $VersionFile." }
    $doc = Get-Content -LiteralPath $vf -Raw | ConvertFrom-Json
    if ([string]$doc.version -ne $ExpectedVersion) { throw "Version inesperada: $($doc.version). Se esperaba $ExpectedVersion." }
    if (Get-ChildItem -LiteralPath $Dest -Recurse -File -Filter 'app_patch_*.py' -ErrorAction SilentlyContinue) { throw 'Se detecto una cadena app_patch_* prohibida.' }
}

function Test-LocalRuntime([string]$Dest, [string]$VenvPython) {
    $appPy = Join-Path $Dest 'app.py'
    if (-not (Test-Path -LiteralPath $appPy)) { throw 'Falta app.py.' }
    Invoke-Checked $VenvPython @('-m','py_compile',$appPy)
    Invoke-Checked $VenvPython @('-c','import fastapi, sqlalchemy, dotenv; print("LOCAL_RUNTIME_OK")')
}

$backup = $null
try {
    Write-Step "Instalando version $ExpectedVersion..."
    Stop-AppProcesses $Target
    $backup = Move-ToBackup $Target
    New-Item -ItemType Directory -Force $Target | Out-Null
    Copy-Item -Path (Join-Path $Payload '*') -Destination $Target -Recurse -Force
    Copy-ProtectedState $backup $Target
    Import-PrivateEnvIfNeeded $Target
    Validate-PayloadVersion $Target
    Ensure-Python
    $venvPython = Ensure-Venv $Target
    Test-LocalRuntime $Target $venvPython
    Invoke-Checked $LauncherInstaller @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-')
    Write-Step "INSTALL_OK $App $ExpectedVersion"
    exit 0
} catch {
    Write-Error $_
    Write-Step 'Fallo la instalacion; restaurando la version anterior.'
    Restore-Backup $Target $backup
    exit 1
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}

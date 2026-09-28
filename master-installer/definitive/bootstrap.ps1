param(
    [Parameter(Mandatory = $true)][string]$SourceInstaller,
    [Parameter(Mandatory = $true)][string]$StageRoot,
    [switch]$Reception,
    [switch]$Historia
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ReceptionRoot = 'C:\Recepcion Dr Revelo'
$HistoriaRoot = 'C:\Historia Clinica Dr Revelo'
$SharedRoot = 'C:\ProgramData\ConsultorioDrRevelo'
$PythonRoot = Join-Path $SharedRoot 'Python311'
$PythonExe = Join-Path $PythonRoot 'python.exe'
$BackupRoot = Join-Path $SharedRoot 'InstallerBackups'
$LogRoot = Join-Path $SharedRoot 'InstallerLogs'
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogRoot ("install-$Timestamp.log")

New-Item -ItemType Directory -Force $SharedRoot, $BackupRoot, $LogRoot | Out-Null
Start-Transcript -Path $LogFile -Force | Out-Null

function Write-Step([string]$Message) {
    Write-Host "[Consultorio] $Message"
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$Arguments = @()
    )
    Write-Step ("Ejecutando: " + [IO.Path]::GetFileName($FilePath))
    $output = & $FilePath @Arguments 2>&1
    $exitVar = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
    if ($null -eq $exitVar -or $null -eq $exitVar.Value) {
        $code = 0
    }
    else {
        $code = [int]$exitVar.Value
    }
    foreach ($line in $output) { Write-Host $line }
    if ($code -ne 0) {
        throw "El proceso $FilePath termino con codigo $code."
    }
}

function Get-Sha256Hex([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-PrivateConfig {
    param([string]$InstallerPath)

    if (-not (Test-Path -LiteralPath $InstallerPath)) {
        throw 'No se encontro el ejecutable fuente del instalador.'
    }

    $stream = [IO.File]::Open($InstallerPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $tailLength = [Math]::Min([int64]524288, $stream.Length)
        [void]$stream.Seek(-$tailLength, [IO.SeekOrigin]::End)
        $buffer = New-Object byte[] ([int]$tailLength)
        $read = $stream.Read($buffer, 0, $buffer.Length)
        $tailText = [Text.Encoding]::ASCII.GetString($buffer, 0, $read).Replace("`r", '')
    }
    finally {
        $stream.Dispose()
    }

    $pattern = 'DRREVELO_PRIVATE_CONFIG_V1\nSHA256=([0-9a-fA-F]{64})\nBASE64=([A-Za-z0-9+/=]+)\nDRREVELO_PRIVATE_CONFIG_END'
    $matches = [regex]::Matches($tailText, $pattern)
    if ($matches.Count -eq 0) {
        throw 'Este instalador no contiene la configuracion privada del consultorio.'
    }

    $match = $matches[$matches.Count - 1]
    $expectedHash = $match.Groups[1].Value.ToLowerInvariant()
    $bytes = [Convert]::FromBase64String($match.Groups[2].Value)
    $actualHash = Get-Sha256Hex $bytes
    if ($actualHash -ne $expectedHash) {
        throw 'La configuracion privada esta danada o incompleta.'
    }

    $text = [Text.Encoding]::UTF8.GetString($bytes)
    $required = @('DATABASE_URL', 'HISTORIA_DATABASE_URL', 'MOBILE_DOCTOR_TOKEN', 'MOBILE_RECEPTION_TOKEN')
    foreach ($name in $required) {
        if ($text -notmatch "(?m)^$([regex]::Escape($name))=.+$") {
            throw "La configuracion privada no contiene $name."
        }
    }
    return $bytes
}

function Stop-AppProcesses([string]$Root) {
    try {
        Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase)
        } | ForEach-Object {
            Write-Step "Cerrando proceso del programa: $($_.Name)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-Step 'No fue posible enumerar todos los procesos; se continuara con las comprobaciones de archivos.'
    }
}

function Move-ToBackup {
    param([string]$Root, [string]$Name)
    if (-not (Test-Path -LiteralPath $Root)) { return $null }

    $session = Join-Path $BackupRoot $Timestamp
    New-Item -ItemType Directory -Force $session | Out-Null
    $dest = Join-Path $session $Name
    if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
    Move-Item -LiteralPath $Root -Destination $dest
    return $dest
}

function Restore-Backup {
    param([string]$Root, [AllowNull()][string]$Backup)
    if (Test-Path -LiteralPath $Root) {
        Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($Backup -and (Test-Path -LiteralPath $Backup)) {
        Move-Item -LiteralPath $Backup -Destination $Root
    }
}

function Copy-ProtectedState {
    param([AllowNull()][string]$Backup, [string]$Target)
    if (-not $Backup -or -not (Test-Path -LiteralPath $Backup)) { return }

    $dirs = @('data', 'backups', 'update_backups', 'logs', 'documentos', 'documents', 'exports', 'exportaciones', 'reportes', 'uploads')
    foreach ($dir in $dirs) {
        $source = Join-Path $Backup $dir
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $Target $dir) -Recurse -Force
        }
    }

    $envFile = Join-Path $Backup '.env'
    if (Test-Path -LiteralPath $envFile) {
        Copy-Item -LiteralPath $envFile -Destination (Join-Path $Target '.env') -Force
    }

    $extensions = @('*.db', '*.sqlite', '*.sqlite3', '*.mdb', '*.accdb', '*.xls', '*.xlsx', '*.csv')
    foreach ($pattern in $extensions) {
        Get-ChildItem -LiteralPath $Backup -File -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Target $_.Name) -Force
        }
    }
}

function Ensure-PrivateEnv {
    param([string]$Target, [byte[]]$ConfigBytes)
    $envPath = Join-Path $Target '.env'
    if (-not (Test-Path -LiteralPath $envPath)) {
        [IO.File]::WriteAllBytes($envPath, $ConfigBytes)
        try {
            & icacls.exe $envPath /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' "$env:USERNAME`:F" | Out-Null
        }
        catch {
            Write-Step 'No se pudo endurecer el ACL de .env; el archivo se mantiene instalado.'
        }
    }
}

function Ensure-Python {
    $valid = $false
    if (Test-Path -LiteralPath $PythonExe) {
        try {
            $version = (& $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
            $valid = ($version -eq '3.11')
        }
        catch { $valid = $false }
    }
    if ($valid) { return }

    if (Test-Path -LiteralPath $PythonRoot) {
        Remove-Item -LiteralPath $PythonRoot -Recurse -Force
    }

    $installer = Join-Path $StageRoot 'python-3.11.9-amd64.exe'
    if (-not (Test-Path -LiteralPath $installer)) { throw 'No se encontro Python 3.11 incluido en el instalador.' }
    Invoke-Checked $installer @(
        '/quiet',
        'InstallAllUsers=1',
        "TargetDir=$PythonRoot",
        'PrependPath=0',
        'Include_launcher=0',
        'InstallLauncherAllUsers=0',
        'Include_pip=1',
        'Include_test=0',
        'Include_doc=0',
        'Include_dev=0'
    )
    if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'Python 3.11 no quedo instalado correctamente.' }
}

function Ensure-Venv {
    param([string]$Target, [string]$Requirements)
    $venv = Join-Path $Target '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $venvPythonW = Join-Path $venv 'Scripts\pythonw.exe'

    if (-not (Test-Path -LiteralPath $venvPython) -or -not (Test-Path -LiteralPath $venvPythonW)) {
        if (Test-Path -LiteralPath $venv) { Remove-Item -LiteralPath $venv -Recurse -Force }
        Invoke-Checked $PythonExe @('-m', 'venv', $venv)
    }

    $wheelhouse = Join-Path $StageRoot 'wheelhouse'
    Invoke-Checked $venvPython @(
        '-m', 'pip', 'install', '--disable-pip-version-check', '--no-index',
        '--find-links', $wheelhouse, '-r', $Requirements
    )
    return $venvPython
}

function Test-ReceptionRuntime([string]$Target, [string]$VenvPython) {
    $oldOffline = $env:RP_FORCE_OFFLINE
    $oldBytecode = $env:PYTHONDONTWRITEBYTECODE
    $pushed = $false
    try {
        $env:RP_FORCE_OFFLINE = '1'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        Push-Location $Target
        $pushed = $true
        Invoke-Checked $VenvPython @('-c', "import app; assert app.APP_VERSION; print('RECEPTION_RUNTIME_OK', app.APP_VERSION, len(app.app.router.routes))")
    }
    finally {
        if ($pushed) { Pop-Location }
        $env:RP_FORCE_OFFLINE = $oldOffline
        $env:PYTHONDONTWRITEBYTECODE = $oldBytecode
    }
}

function Test-HistoriaRuntime([string]$Target, [string]$VenvPython) {
    $oldPreflight = $env:HC_PREFLIGHT
    $oldSync = $env:HISTORIA_SYNC_ENABLED
    $oldBytecode = $env:PYTHONDONTWRITEBYTECODE
    $pushed = $false
    try {
        $env:HC_PREFLIGHT = '1'
        $env:HISTORIA_SYNC_ENABLED = '0'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        Push-Location $Target
        $pushed = $true
        Invoke-Checked $VenvPython @('-c', "import app; assert app.APP_VERSION; print('HISTORIA_RUNTIME_OK', app.APP_VERSION, len(app.app.router.routes))")
    }
    finally {
        if ($pushed) { Pop-Location }
        $env:HC_PREFLIGHT = $oldPreflight
        $env:HISTORIA_SYNC_ENABLED = $oldSync
        $env:PYTHONDONTWRITEBYTECODE = $oldBytecode
    }
}

function Install-OneApp {
    param(
        [string]$Name,
        [string]$Target,
        [string]$Payload,
        [string]$Requirements,
        [string]$LauncherInstaller,
        [byte[]]$ConfigBytes,
        [scriptblock]$RuntimeTest
    )

    Write-Step "Preparando $Name..."
    Stop-AppProcesses $Target
    $backup = Move-ToBackup $Target ($Name -replace '[^A-Za-z0-9_-]', '_')
    try {
        New-Item -ItemType Directory -Force $Target | Out-Null
        Copy-Item -Path (Join-Path $Payload '*') -Destination $Target -Recurse -Force
        Copy-ProtectedState $backup $Target
        Ensure-PrivateEnv $Target $ConfigBytes
        $venvPython = Ensure-Venv $Target $Requirements
        & $RuntimeTest $Target $venvPython
        Invoke-Checked $LauncherInstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')
        Write-Step "$Name quedo instalado y validado."
        return [pscustomobject]@{ Name = $Name; Target = $Target; Backup = $backup }
    }
    catch {
        Write-Step "Fallo $Name. Restaurando la instalacion anterior..."
        Restore-Backup $Target $backup
        throw
    }
}

$completed = New-Object System.Collections.Generic.List[object]
try {
    if (-not $Reception -and -not $Historia) { throw 'No se selecciono ningun programa.' }
    $configBytes = Get-PrivateConfig $SourceInstaller
    Ensure-Python

    if ($Reception) {
        $params = @{
            Name = 'Recepcion'
            Target = $ReceptionRoot
            Payload = (Join-Path $StageRoot 'payload\recepcion')
            Requirements = (Join-Path $StageRoot 'requirements-recepcion.txt')
            LauncherInstaller = (Join-Path $StageRoot 'INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe')
            ConfigBytes = $configBytes
            RuntimeTest = ${function:Test-ReceptionRuntime}
        }
        $completed.Add((Install-OneApp @params))
    }

    if ($Historia) {
        $params = @{
            Name = 'Historia'
            Target = $HistoriaRoot
            Payload = (Join-Path $StageRoot 'payload\historia')
            Requirements = (Join-Path $StageRoot 'requirements-historia.txt')
            LauncherInstaller = (Join-Path $StageRoot 'INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe')
            ConfigBytes = $configBytes
            RuntimeTest = ${function:Test-HistoriaRuntime}
        }
        $completed.Add((Install-OneApp @params))
    }

    Write-Step 'INSTALACION_DEFINITIVA_OK'
    exit 0
}
catch {
    if ($completed.Count -gt 0) {
        Write-Step 'La instalacion conjunta fallo. Restaurando programas ya modificados en esta operacion...'
        for ($i = $completed.Count - 1; $i -ge 0; $i--) {
            $item = $completed[$i]
            Restore-Backup $item.Target $item.Backup
        }
    }
    Write-Error $_
    exit 1
}
finally {
    try { Stop-Transcript | Out-Null } catch {}
}

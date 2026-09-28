param(
    [Parameter(Mandatory = $true)][string]$SourceInstaller,
    [Parameter(Mandatory = $true)][string]$StageRoot,
    [switch]$Reception,
    [switch]$Historia
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Estos valores se fijan en CI al commit exacto que fue probado.
$SourceArchiveUrl = '__SOURCE_ARCHIVE_URL__'
$SourceArchiveSha256 = '__SOURCE_ARCHIVE_SHA256__'
$PythonSha256 = '__PYTHON_SHA256__'

$PythonUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
$ReceptionLauncherUrl = 'https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/launcher-v1.0.12/INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe'
$ReceptionLauncherSha256 = '9bd537cc74fe94167698edb1ede18b111cbe68d2d1af2b0cc12bf4b20e4bbef0'
$HistoriaLauncherUrl = 'https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/historia-launcher-v1.0.8/INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe'
$HistoriaLauncherSha256 = '7dad1d2429a50c781868f092fc7c3e873aec8d788e4e19e5b65a0a04c13a2cc6'

$ReceptionRoot = 'C:\Recepcion Dr Revelo'
$HistoriaRoot = 'C:\Historia Clinica Dr Revelo'
$SharedRoot = 'C:\ProgramData\ConsultorioDrRevelo'
$PythonRoot = Join-Path $SharedRoot 'Python311'
$PythonExe = Join-Path $PythonRoot 'python.exe'
$BackupRoot = Join-Path $SharedRoot 'InstallerBackups'
$LogRoot = Join-Path $SharedRoot 'InstallerLogs'
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogRoot ("install-$Timestamp.log")

New-Item -ItemType Directory -Force $StageRoot, $SharedRoot, $BackupRoot, $LogRoot | Out-Null
Start-Transcript -Path $LogFile -Force | Out-Null

function Write-Step([string]$Message) {
    Write-Host "[Consultorio] $Message"
}

function Get-Sha256File([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-Sha256Bytes([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$Arguments = @()
    )
    Write-Step ("Ejecutando: " + [IO.Path]::GetFileName($FilePath))
    $output = & $FilePath @Arguments 2>&1
    $exitVar = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
    if ($null -eq $exitVar -or $null -eq $exitVar.Value) { $code = 0 } else { $code = [int]$exitVar.Value }
    foreach ($line in $output) { Write-Host $line }
    if ($code -ne 0) { throw "El proceso $FilePath termino con codigo $code." }
}

function Invoke-InstallerChecked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$Arguments = @()
    )
    Write-Step ("Instalando: " + [IO.Path]::GetFileName($FilePath))
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "El instalador $FilePath termino con codigo $($process.ExitCode)." }
}

function Download-Verified {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [int]$Attempts = 3
    )
    if (-not $ExpectedSha256 -or $ExpectedSha256 -match '^__') {
        throw "El build no fijo el SHA-256 requerido para $Uri."
    }

    $parent = Split-Path -Parent $Destination
    if ($parent) { New-Item -ItemType Directory -Force $parent | Out-Null }

    for ($try = 1; $try -le $Attempts; $try++) {
        try {
            if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Force }
            Write-Step "Descargando componente ($try/$Attempts)..."
            Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination -TimeoutSec 120
            $got = Get-Sha256File $Destination
            if ($got -ne $ExpectedSha256.ToLowerInvariant()) {
                throw "SHA-256 inesperado. Esperado $ExpectedSha256; recibido $got."
            }
            return $Destination
        }
        catch {
            if ($try -ge $Attempts) { throw }
            Start-Sleep -Seconds (2 * $try)
        }
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
    $actualHash = Get-Sha256Bytes $bytes
    if ($actualHash -ne $expectedHash) {
        throw 'La configuracion privada esta danada o incompleta.'
    }

    $text = [Text.Encoding]::UTF8.GetString($bytes)
    foreach ($name in @('DATABASE_URL', 'HISTORIA_DATABASE_URL')) {
        if ($text -notmatch "(?m)^$([regex]::Escape($name))=.+$") {
            throw "La configuracion privada no contiene $name."
        }
    }

    # Los enlaces móviles no deben convertirse en un requisito manual del instalador.
    # Si no vienen en el paquete privado se generan aquí y quedan persistidos en .env.
    foreach ($tokenName in @('MOBILE_DOCTOR_TOKEN', 'MOBILE_RECEPTION_TOKEN')) {
        if ($text -notmatch "(?m)^$([regex]::Escape($tokenName))=.+$") {
            $random = New-Object byte[] 32
            [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($random)
            $token = [Convert]::ToBase64String($random).TrimEnd('=').Replace('+', '-').Replace('/', '_')
            if (-not $text.EndsWith("`n")) { $text += "`r`n" }
            $text += "$tokenName=$token`r`n"
        }
    }
    return [Text.Encoding]::UTF8.GetBytes($text)
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

function Test-IsolatedPython {
    if (-not (Test-Path -LiteralPath $PythonExe)) { return $false }
    try {
        $version = (& $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        return ($version -eq '3.11')
    }
    catch { return $false }
}

function Ensure-Python {
    if (Test-IsolatedPython) {
        Write-Step 'Python 3.11 aislado ya está listo; no se vuelve a descargar.'
        return
    }

    if (Test-Path -LiteralPath $PythonRoot) {
        Remove-Item -LiteralPath $PythonRoot -Recurse -Force
    }

    $installer = Join-Path $StageRoot 'python-3.11.9-amd64.exe'
    Download-Verified -Uri $PythonUrl -Destination $installer -ExpectedSha256 $PythonSha256 | Out-Null
    $sig = Get-AuthenticodeSignature -LiteralPath $installer
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        throw "Firma Authenticode de Python no válida: $($sig.Status)."
    }

    Invoke-InstallerChecked $installer @(
        '/quiet',
        'InstallAllUsers=0',
        "TargetDir=$PythonRoot",
        'PrependPath=0',
        'Include_launcher=0',
        'InstallLauncherAllUsers=0',
        'Include_pip=1',
        'Include_test=0',
        'Include_doc=0',
        'Include_dev=0'
    )
    if (-not (Test-IsolatedPython)) { throw 'Python 3.11 no quedó instalado correctamente.' }
}

function Prepare-SourceArchive {
    $zip = Join-Path $StageRoot 'consultorio-source.zip'
    $extract = Join-Path $StageRoot 'source'
    Download-Verified -Uri $SourceArchiveUrl -Destination $zip -ExpectedSha256 $SourceArchiveSha256 | Out-Null
    if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    New-Item -ItemType Directory -Force $extract | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force

    $root = Get-ChildItem -LiteralPath $extract -Directory | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName 'recepcion\app\app.py')) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName 'historia-clinica\app\app.py'))
    } | Select-Object -First 1
    if (-not $root) { throw 'El paquete descargado no contiene los dos programas canónicos.' }
    return $root.FullName
}

function Assert-CanonicalPayload {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath (Join-Path $Path 'app.py'))) { throw "$Name no contiene app.py." }
    if (Test-Path -LiteralPath (Join-Path $Path '.env')) { throw "$Name descargado contiene .env inesperado." }
    if (Test-Path -LiteralPath (Join-Path $Path 'data')) { throw "$Name descargado contiene data inesperado." }
    $patches = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Filter 'app_patch_*.py' -ErrorAction SilentlyContinue)
    if ($patches.Count -gt 0) { throw "$Name reintrodujo una cadena app_patch_*; instalación bloqueada." }
}

function Prepare-Launcher {
    param([string]$Uri, [string]$Sha256, [string]$FileName)
    $path = Join-Path $StageRoot $FileName
    Download-Verified -Uri $Uri -Destination $path -ExpectedSha256 $Sha256 | Out-Null
    return $path
}

function Prepare-Wheelhouse {
    param([string[]]$RequirementFiles)
    $wheelhouse = Join-Path $StageRoot 'wheelhouse'
    if (Test-Path -LiteralPath $wheelhouse) { Remove-Item -LiteralPath $wheelhouse -Recurse -Force }
    New-Item -ItemType Directory -Force $wheelhouse | Out-Null

    $args = @('-m', 'pip', 'download', '--disable-pip-version-check', '--only-binary=:all:', '--retries', '4', '--timeout', '30', '--dest', $wheelhouse)
    foreach ($req in $RequirementFiles) {
        if (-not (Test-Path -LiteralPath $req)) { throw "No se encontró requirements: $req" }
        $args += @('-r', $req)
    }
    Invoke-Checked $PythonExe $args
    if (@(Get-ChildItem -LiteralPath $wheelhouse -File).Count -lt 4) {
        throw 'La descarga de dependencias quedó incompleta.'
    }
    return $wheelhouse
}

function Ensure-Venv {
    param([string]$Target, [string]$Requirements, [string]$Wheelhouse)
    $venv = Join-Path $Target '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $venvPythonW = Join-Path $venv 'Scripts\pythonw.exe'

    if (-not (Test-Path -LiteralPath $venvPython) -or -not (Test-Path -LiteralPath $venvPythonW)) {
        if (Test-Path -LiteralPath $venv) { Remove-Item -LiteralPath $venv -Recurse -Force }
        Invoke-Checked $PythonExe @('-m', 'venv', $venv)
    }

    Invoke-Checked $venvPython @(
        '-m', 'pip', 'install', '--disable-pip-version-check', '--no-index',
        '--find-links', $Wheelhouse, '-r', $Requirements
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
        [string]$Wheelhouse,
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
        $venvPython = Ensure-Venv $Target $Requirements $Wheelhouse
        & $RuntimeTest $Target $venvPython
        Invoke-InstallerChecked $LauncherInstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')
        Write-Step "$Name quedó instalado y validado."
        return [pscustomobject]@{ Name = $Name; Target = $Target; Backup = $backup }
    }
    catch {
        Write-Step "Falló $Name. Restaurando la instalación anterior..."
        Restore-Backup $Target $backup
        throw
    }
}

$completed = New-Object System.Collections.Generic.List[object]
try {
    if (-not $Reception -and -not $Historia) { throw 'No se seleccionó ningún programa.' }
    if ($SourceArchiveUrl -match '^__' -or $SourceArchiveSha256 -match '^__' -or $PythonSha256 -match '^__') {
        throw 'Este EXE fue compilado sin fijar sus descargas verificadas.'
    }

    # Validar configuración ANTES de descargar o tocar una instalación existente.
    $configBytes = Get-PrivateConfig $SourceInstaller

    Write-Step 'Descargando versión canónica exacta...'
    $sourceRoot = Prepare-SourceArchive
    $receptionPayload = Join-Path $sourceRoot 'recepcion\app'
    $historiaPayload = Join-Path $sourceRoot 'historia-clinica\app'
    Assert-CanonicalPayload $receptionPayload 'Recepción'
    Assert-CanonicalPayload $historiaPayload 'Historia Clínica'

    Ensure-Python

    $requirements = New-Object System.Collections.Generic.List[string]
    $receptionRequirements = Join-Path $sourceRoot 'master-installer\definitive\requirements-recepcion.txt'
    $historiaRequirements = Join-Path $historiaPayload 'requirements.txt'
    if ($Reception) { $requirements.Add($receptionRequirements) }
    if ($Historia) { $requirements.Add($historiaRequirements) }

    Write-Step 'Descargando dependencias verificables antes de modificar los programas...'
    $wheelhouse = Prepare-Wheelhouse $requirements.ToArray()

    $receptionLauncher = $null
    $historiaLauncher = $null
    if ($Reception) {
        $receptionLauncher = Prepare-Launcher $ReceptionLauncherUrl $ReceptionLauncherSha256 'INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe'
    }
    if ($Historia) {
        $historiaLauncher = Prepare-Launcher $HistoriaLauncherUrl $HistoriaLauncherSha256 'INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe'
    }

    if ($Reception) {
        $params = @{
            Name = 'Recepcion'
            Target = $ReceptionRoot
            Payload = $receptionPayload
            Requirements = $receptionRequirements
            LauncherInstaller = $receptionLauncher
            Wheelhouse = $wheelhouse
            ConfigBytes = $configBytes
            RuntimeTest = ${function:Test-ReceptionRuntime}
        }
        $completed.Add((Install-OneApp @params))
    }

    if ($Historia) {
        $params = @{
            Name = 'Historia'
            Target = $HistoriaRoot
            Payload = $historiaPayload
            Requirements = $historiaRequirements
            LauncherInstaller = $historiaLauncher
            Wheelhouse = $wheelhouse
            ConfigBytes = $configBytes
            RuntimeTest = ${function:Test-HistoriaRuntime}
        }
        $completed.Add((Install-OneApp @params))
    }

    Write-Step 'INSTALACION_LIVIANA_DEFINITIVA_OK'
    exit 0
}
catch {
    if ($completed.Count -gt 0) {
        Write-Step 'La instalación conjunta falló. Restaurando programas ya modificados en esta operación...'
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

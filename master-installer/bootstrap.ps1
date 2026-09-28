param(
    [switch]$Reception,
    [switch]$Historia
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not $Reception -and -not $Historia) {
    throw 'Debe seleccionar Recepción, Historia Clínica o ambos.'
}

$RuntimeRoot = Join-Path $env:ProgramData 'DrReveloRuntime'
$PreferredPythonRoot = Join-Path $RuntimeRoot 'Python312'
$script:PythonExe = Join-Path $PreferredPythonRoot 'python.exe'
$LogRoot = Join-Path $RuntimeRoot 'logs'
New-Item -ItemType Directory -Force $RuntimeRoot, $LogRoot | Out-Null
$LogPath = Join-Path $LogRoot ("bootstrap-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
Start-Transcript -Path $LogPath -Force | Out-Null

function Write-Step([string]$Message) {
    Write-Host "[Consultorio] $Message"
}

function Get-Json([string]$Url) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers @{
        'User-Agent' = 'ConsultorioDrRevelo-Bootstrap/2.0'
        'Cache-Control' = 'no-cache'
    } -TimeoutSec 30
    return ($response.Content | ConvertFrom-Json)
}

function Get-VerifiedFile([string]$Url, [string]$Destination, [string]$ExpectedSha256) {
    $parent = Split-Path -Parent $Destination
    if ($parent) { New-Item -ItemType Directory -Force $parent | Out-Null }
    $temp = "$Destination.download"
    Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $temp -Headers @{
        'User-Agent' = 'ConsultorioDrRevelo-Bootstrap/2.0'
        'Cache-Control' = 'no-cache'
    } -TimeoutSec 180

    if ($ExpectedSha256) {
        $actual = (Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = $ExpectedSha256.Trim().ToLowerInvariant()
        if ($actual -ne $expected) {
            Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
            throw "SHA-256 inválido para $Url. Esperado $expected; recibido $actual."
        }
    }
    Move-Item -LiteralPath $temp -Destination $Destination -Force
}

function Test-Python312([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        & $Path -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 9)" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-Python312 {
    $candidates = New-Object System.Collections.Generic.List[string]
    $candidates.Add((Join-Path $PreferredPythonRoot 'python.exe'))
    if ($env:ProgramFiles) { $candidates.Add((Join-Path $env:ProgramFiles 'Python312\python.exe')) }
    if (${env:ProgramFiles(x86)}) { $candidates.Add((Join-Path ${env:ProgramFiles(x86)} 'Python312\python.exe')) }
    if ($env:LocalAppData) { $candidates.Add((Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe')) }

    try {
        $cmd = Get-Command python.exe -ErrorAction Stop
        if ($cmd.Source) { $candidates.Add([string]$cmd.Source) }
    } catch { }

    foreach ($candidate in $candidates) {
        if (Test-Python312 $candidate) { return $candidate }
    }

    try {
        $py = Get-Command py.exe -ErrorAction Stop
        $resolved = (& $py.Source -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($resolved) {
            $resolved = ([string]$resolved).Trim()
            if (Test-Python312 $resolved) { return $resolved }
        }
    } catch { }
    return $null
}

function Ensure-PrivatePython {
    $found = Find-Python312
    if ($found) {
        $script:PythonExe = $found
        Write-Step "Python 3.12 listo: $found"
        return
    }

    Write-Step 'Preparando Python 3.12 verificado...'
    $installer = Join-Path $env:TEMP 'python-3.12.10-amd64.exe'
    $pythonUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -UseBasicParsing -Uri $pythonUrl -OutFile $installer -TimeoutSec 180

    $signature = Get-AuthenticodeSignature -FilePath $installer
    if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
        throw 'La firma digital del instalador oficial de Python no es válida.'
    }

    $args = @(
        '/quiet',
        'InstallAllUsers=1',
        'PrependPath=0',
        'Include_launcher=1',
        'Include_test=0',
        'Include_doc=0',
        'Include_tcltk=0',
        'Include_pip=1',
        'Include_tools=1',
        'Shortcuts=0'
    )
    $proc = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    if ($proc.ExitCode -ne 0) {
        throw "No se pudo instalar Python 3.12. Código: $($proc.ExitCode)."
    }

    $found = Find-Python312
    if (-not $found) {
        throw 'Python 3.12 terminó de instalarse, pero Windows no devolvió una ruta utilizable.'
    }
    $script:PythonExe = $found
    [IO.File]::WriteAllText((Join-Path $RuntimeRoot 'python-path.txt'), $found)
    Write-Step "Python 3.12 preparado: $found"
}

function Assert-SafeRelativePath([string]$RelativePath, [string]$Root) {
    if ([string]::IsNullOrWhiteSpace($RelativePath)) { throw 'El canal contiene una ruta vacía.' }
    $normalized = $RelativePath.Replace('/', '\')
    if ([IO.Path]::IsPathRooted($normalized) -or $normalized -match '(^|\\)\.\.(\\|$)') {
        throw "Ruta insegura en el canal: $RelativePath"
    }
    $first = ($normalized -split '\\')[0].ToLowerInvariant()
    if ($first -in @('.env', '.venv', 'data')) {
        throw "El canal intentó escribir una ruta protegida: $RelativePath"
    }
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $destFull = [IO.Path]::GetFullPath((Join-Path $Root $normalized))
    if (-not $destFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "La ruta sale del directorio permitido: $RelativePath"
    }
    return $destFull
}

function Install-AppFromChannel([string]$ProductName, [string]$Root, [string]$ChannelUrl) {
    Write-Step "Descargando runtime verificado de $ProductName..."
    New-Item -ItemType Directory -Force $Root | Out-Null
    $channel = Get-Json $ChannelUrl
    if (-not $channel.files -or @($channel.files).Count -eq 0) {
        throw "El canal de $ProductName no contiene archivos."
    }

    foreach ($entry in @($channel.files)) {
        $relative = [string]$entry.path
        $url = [string]$entry.url
        $sha = [string]$entry.sha256
        if (-not $url -or -not $sha) { throw "Entrada incompleta en el canal de ${ProductName}: $relative" }
        $destination = Assert-SafeRelativePath $relative $Root
        Get-VerifiedFile $url $destination $sha
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Root 'app.py'))) {
        throw "$ProductName quedó sin app.py después de descargar el canal."
    }
    return [string]$channel.appVersion
}

function Ensure-Venv([string]$ProductName, [string]$Root, [string[]]$Packages) {
    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step "Creando entorno privado de $ProductName..."
        & $script:PythonExe -m venv (Join-Path $Root '.venv')
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
            throw "No se pudo crear el entorno privado de $ProductName."
        }
    }

    Write-Step "Verificando dependencias de $ProductName..."
    $requirements = Join-Path $env:TEMP (("dr-revelo-{0}-requirements.txt" -f ($ProductName -replace '[^A-Za-z0-9]+','-')).ToLowerInvariant())
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllLines($requirements, $Packages, $utf8NoBom)
    & $venvPython -m pip install --disable-pip-version-check --no-input -r $requirements
    $exit = $LASTEXITCODE
    Remove-Item -LiteralPath $requirements -Force -ErrorAction SilentlyContinue
    if ($exit -ne 0) { throw "No se pudieron instalar las dependencias de $ProductName." }
}

function Install-VerifiedLauncher([string]$ProductName, [string]$Url, [string]$Sha256) {
    Write-Step "Instalando launcher base verificado de $ProductName..."
    if (-not $Url -or -not $Sha256) { throw "Falta la referencia verificada del launcher de $ProductName." }
    $installer = Join-Path $env:TEMP (("dr-revelo-{0}-launcher.exe" -f ($ProductName -replace '[^A-Za-z0-9]+','-')).ToLowerInvariant())
    Get-VerifiedFile $Url $installer $Sha256
    $proc = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-') -Wait -PassThru
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    if ($proc.ExitCode -notin @(0, 3010)) { throw "El launcher de $ProductName devolvió código $($proc.ExitCode)." }
}

$ReceptionPackages = @(
    'fastapi==0.128.2',
    'uvicorn==0.48.0',
    'SQLAlchemy>=2.0,<2.1',
    'python-dotenv>=1.0,<2',
    'pg8000==1.31.2',
    'python-multipart>=0.0.20,<1'
)
$HistoriaPackages = @(
    'fastapi==0.128.2',
    'uvicorn==0.48.0',
    'pg8000==1.31.2',
    'pywebview==6.2.1'
)

$ReceptionLauncherUrl = 'https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/launcher-v1.0.12/INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe'
$ReceptionLauncherSha256 = '9bd537cc74fe94167698edb1ede18b111cbe68d2d1af2b0cc12bf4b20e4bbef0'
$HistoriaLauncherUrl = 'https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/historia-launcher-v1.0.8/INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe'
$HistoriaLauncherSha256 = '7dad1d2429a50c781868f092fc7c3e873aec8d788e4e19e5b65a0a04c13a2cc6'

try {
    Ensure-PrivatePython

    if ($Reception) {
        $root = 'C:\Recepcion Dr Revelo'
        $version = Install-AppFromChannel 'Recepción' $root 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/launcher-v1/app-channel.json'
        Ensure-Venv 'Recepción' $root $ReceptionPackages
        Install-VerifiedLauncher 'Recepción' $ReceptionLauncherUrl $ReceptionLauncherSha256
        Write-Step "Recepción $version preparada correctamente."
    }

    if ($Historia) {
        $root = 'C:\Historia Clinica Dr Revelo'
        $version = Install-AppFromChannel 'Historia Clínica' $root 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/historia-clinica/launcher-v1/app-channel.json'
        Ensure-Venv 'Historia Clínica' $root $HistoriaPackages
        Install-VerifiedLauncher 'Historia Clínica' $HistoriaLauncherUrl $HistoriaLauncherSha256
        Write-Step "Historia Clínica $version preparada correctamente."
    }

    Write-Step 'Instalación limpia completada.'
    exit 0
}
catch {
    Write-Error $_
    Write-Host "Registro técnico: $LogPath"
    exit 1
}
finally {
    try { Stop-Transcript | Out-Null } catch { }
}

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
        'User-Agent' = 'ConsultorioDrRevelo-Bootstrap/2.1'
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
        'User-Agent' = 'ConsultorioDrRevelo-Bootstrap/2.1'
        'Cache-Control' = 'no-cache'
    } -TimeoutSec 240

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
    } catch { return $false }
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
        Write-Step "Python 3.12 listo."
        return
    }

    Write-Step 'Preparando Python 3.12 verificado...'
    $installer = Join-Path $env:TEMP 'python-3.12.10-amd64.exe'
    $pythonUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -UseBasicParsing -Uri $pythonUrl -OutFile $installer -TimeoutSec 240
    $signature = Get-AuthenticodeSignature -FilePath $installer
    if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
        throw 'La firma digital del instalador oficial de Python no es válida.'
    }
    $args = @('/quiet','InstallAllUsers=1','PrependPath=0','Include_launcher=1','Include_test=0','Include_doc=0','Include_tcltk=0','Include_pip=1','Include_tools=1','Shortcuts=0')
    $proc = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    if ($proc.ExitCode -ne 0) { throw "No se pudo instalar Python 3.12. Código: $($proc.ExitCode)." }
    $found = Find-Python312
    if (-not $found) { throw 'Python 3.12 terminó de instalarse, pero Windows no devolvió una ruta utilizable.' }
    $script:PythonExe = $found
    [IO.File]::WriteAllText((Join-Path $RuntimeRoot 'python-path.txt'), $found)
}

function Assert-SafeRelativePath([string]$RelativePath, [string]$Root) {
    if ([string]::IsNullOrWhiteSpace($RelativePath)) { throw 'El canal contiene una ruta vacía.' }
    $normalized = $RelativePath.Replace('/', '\')
    if ([IO.Path]::IsPathRooted($normalized) -or $normalized -match '(^|\\)\.\.(\\|$)') { throw "Ruta insegura en el canal: $RelativePath" }
    $first = ($normalized -split '\\')[0].ToLowerInvariant()
    if ($first -in @('.env', '.venv', 'data')) { throw "El canal intentó escribir una ruta protegida: $RelativePath" }
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $destFull = [IO.Path]::GetFullPath((Join-Path $Root $normalized))
    if (-not $destFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) { throw "La ruta sale del directorio permitido: $RelativePath" }
    return $destFull
}

function Install-AppFromChannel([string]$ProductName, [string]$Root, [string]$ChannelUrl) {
    Write-Step "Descargando runtime verificado de $ProductName..."
    New-Item -ItemType Directory -Force $Root | Out-Null
    $channel = Get-Json $ChannelUrl
    if (-not $channel.files -or @($channel.files).Count -eq 0) { throw "El canal de $ProductName no contiene archivos." }
    foreach ($entry in @($channel.files)) {
        $relative = [string]$entry.path
        $url = [string]$entry.url
        $sha = [string]$entry.sha256
        if (-not $url -or -not $sha) { throw "Entrada incompleta en el canal de ${ProductName}: $relative" }
        $destination = Assert-SafeRelativePath $relative $Root
        Get-VerifiedFile $url $destination $sha
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Root 'app.py'))) { throw "$ProductName quedó sin app.py después de descargar el canal." }
    return [string]$channel.appVersion
}

function Ensure-Venv([string]$ProductName, [string]$Root, [string[]]$Packages) {
    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step "Creando entorno privado de $ProductName..."
        & $script:PythonExe -m venv (Join-Path $Root '.venv')
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) { throw "No se pudo crear el entorno privado de $ProductName." }
    }
    Write-Step "Verificando dependencias de $ProductName..."
    $requirements = Join-Path $env:TEMP (("dr-revelo-{0}-requirements.txt" -f ($ProductName -replace '[^A-Za-z0-9]+','-')).ToLowerInvariant())
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllLines($requirements, $Packages, $utf8NoBom)
    & $venvPython -m pip install --disable-pip-version-check --no-input -r $requirements
    $exit = $LASTEXITCODE
    Remove-Item -LiteralPath $requirements -Force -ErrorAction SilentlyContinue
    if ($exit -ne 0) { throw "No se pudieron instalar las dependencias base de $ProductName." }
    $appRequirements = Join-Path $Root 'requirements.txt'
    if (Test-Path -LiteralPath $appRequirements) {
        & $venvPython -m pip install --disable-pip-version-check --no-input -r $appRequirements
        if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar requirements.txt de $ProductName." }
    }
}

function Install-VerifiedLauncher([string]$ProductName, [string]$Url, [string]$Sha256) {
    Write-Step "Instalando launcher verificado de $ProductName..."
    $installer = Join-Path $env:TEMP (("dr-revelo-{0}-launcher.exe" -f ($ProductName -replace '[^A-Za-z0-9]+','-')).ToLowerInvariant())
    Get-VerifiedFile $Url $installer $Sha256
    $proc = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-') -Wait -PassThru
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    if ($proc.ExitCode -notin @(0,3010)) { throw "El launcher de $ProductName devolvió código $($proc.ExitCode)." }
}

function Get-PrivateConfig {
    $rawB64 = [Environment]::GetEnvironmentVariable('DR_REVELO_PRIVATE_CONFIG_B64','Process')
    if ([string]::IsNullOrWhiteSpace($rawB64)) { throw 'El instalador privado no contiene la configuración del consultorio.' }
    try {
        $bytes = [Convert]::FromBase64String($rawB64)
        $text = [Text.Encoding]::UTF8.GetString($bytes)
    } catch { throw 'La configuración privada del instalador no pudo decodificarse.' }
    if (-not $text.StartsWith("DR_REVELO_CONFIG_V2`n")) { throw 'La configuración privada no corresponde a este instalador.' }
    $section = ''
    $result = @{ RECEPTION = @{}; HISTORIA = @{} }
    foreach ($line in ($text -split "`r?`n")) {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith('#') -or $trim -eq 'DR_REVELO_CONFIG_V2') { continue }
        if ($trim -match '^\[([A-Z]+)\]$') { $section = $matches[1]; continue }
        if ($section -and $trim.Contains('=')) {
            $pair = $trim.Split('=',2)
            if ($result.ContainsKey($section)) { $result[$section][$pair[0].Trim()] = $pair[1] }
        }
    }
    return $result
}

function Merge-Env([string]$Root, [hashtable]$Values, [string]$BackupTag) {
    if (-not $Values -or $Values.Count -eq 0) { throw "No hay valores privados para $Root." }
    New-Item -ItemType Directory -Force $Root | Out-Null
    $path = Join-Path $Root '.env'
    $old = if (Test-Path -LiteralPath $path) { [IO.File]::ReadAllLines($path) } else { @() }
    $managed = @{}
    foreach ($k in $Values.Keys) { $managed[[string]$k] = $true }
    $out = New-Object System.Collections.Generic.List[string]
    $written = @{}
    foreach ($line in $old) {
        $matched = $false
        foreach ($key in $Values.Keys) {
            if ($line -match ('^\s*' + [regex]::Escape([string]$key) + '\s*=')) {
                if (-not $written.ContainsKey([string]$key)) {
                    $out.Add(([string]$key + '=' + [string]$Values[$key])); $written[[string]$key] = $true
                }
                $matched = $true; break
            }
        }
        if (-not $matched) { $out.Add($line) }
    }
    foreach ($key in $Values.Keys) {
        if (-not $written.ContainsKey([string]$key)) { $out.Add(([string]$key + '=' + [string]$Values[$key])) }
    }
    $newText = (($out.ToArray() -join "`r`n").TrimEnd() + "`r`n")
    $oldText = (($old -join "`r`n").TrimEnd() + "`r`n")
    if ($newText -eq $oldText -and (Test-Path -LiteralPath $path)) { return $null }
    if (Test-Path -LiteralPath $path) {
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        Copy-Item -LiteralPath $path -Destination (Join-Path $Root (".env.antes_{0}_{1}" -f $BackupTag,$stamp)) -Force
    }
    $tmp = Join-Path $Root '.env.instalador.tmp'
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($tmp,$newText,$utf8NoBom)
    Move-Item -LiteralPath $tmp -Destination $path -Force
    return $path
}

function Test-PostgresConfig([string]$Root, [string]$Url, [string]$ExpectedEndpoint, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Url)) { throw "Falta la conexión privada de $Label." }
    if ($Url -notmatch [regex]::Escape($ExpectedEndpoint)) { throw "La conexión privada de $Label no apunta al endpoint esperado." }
    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    $probe = @'
import os, ssl, urllib.parse, sys
from pg8000 import dbapi as pg
u=os.environ.get('DR_REVELO_PROBE_URL','')
p=urllib.parse.urlsplit(u)
if p.scheme not in ('postgres','postgresql'): raise SystemExit(20)
c=pg.connect(user=urllib.parse.unquote(p.username or ''),password=urllib.parse.unquote(p.password or ''),host=p.hostname or '',port=int(p.port or 5432),database=urllib.parse.unquote((p.path or '/neondb').lstrip('/')) or 'neondb',ssl_context=ssl.create_default_context(),timeout=12)
try:
 cur=c.cursor(); cur.execute('SELECT 1'); row=cur.fetchone(); raise SystemExit(0 if row and int(row[0])==1 else 21)
finally:
 c.close()
'@
    [Environment]::SetEnvironmentVariable('DR_REVELO_PROBE_URL',$Url,'Process')
    try {
        & $venvPython -c $probe
        if ($LASTEXITCODE -ne 0) { throw "No se pudo verificar la conexión Neon de $Label (código $LASTEXITCODE)." }
    } finally { [Environment]::SetEnvironmentVariable('DR_REVELO_PROBE_URL',$null,'Process') }
}

function Reset-HistoriaBootstrap([string]$Root) {
    $db = Join-Path $Root 'data\historia_clinica.db'
    if (-not (Test-Path -LiteralPath $db)) { return }
    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    $code = @'
import sqlite3,sys
p=sys.argv[1]
c=sqlite3.connect(p,timeout=10)
c.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES('last_pull','1970-01-01T00:00:00+00:00')")
c.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES('cloud_bootstrap_complete','0')")
c.commit()
c.close()
'@
    try { & $venvPython -c $code $db | Out-Null } catch { Write-Step 'Historia conservará sus datos locales; el bootstrap se reintentará al abrir.' }
}

$ReceptionPackages = @('fastapi==0.128.2','uvicorn==0.48.0','SQLAlchemy>=2.0,<2.1','python-dotenv>=1.0,<2','pg8000==1.31.2','python-multipart>=0.0.20,<1')
$HistoriaPackages = @('fastapi==0.128.2','uvicorn==0.48.0','pg8000==1.31.2','pywebview==6.2.1')
$ReceptionLauncherUrl = 'https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/launcher-v1.0.12/INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe'
$ReceptionLauncherSha256 = '9bd537cc74fe94167698edb1ede18b111cbe68d2d1af2b0cc12bf4b20e4bbef0'
$HistoriaLauncherUrl = 'https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/historia-launcher-v1.0.8/INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe'
$HistoriaLauncherSha256 = '7dad1d2429a50c781868f092fc7c3e873aec8d788e4e19e5b65a0a04c13a2cc6'

try {
    $private = Get-PrivateConfig
    Ensure-PrivatePython
    $histUrl = [string]$private.HISTORIA['HISTORIA_DATABASE_URL']

    if ($Reception) {
        $root = 'C:\Recepcion Dr Revelo'
        $version = Install-AppFromChannel 'Recepción' $root 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/launcher-v1/app-channel.json'
        Ensure-Venv 'Recepción' $root $ReceptionPackages
        $vals = @{}
        foreach ($k in $private.RECEPTION.Keys) { $vals[[string]$k] = [string]$private.RECEPTION[$k] }
        $vals['HISTORIA_DATABASE_URL'] = $histUrl
        Merge-Env $root $vals 'instalador_consultorio' | Out-Null
        Test-PostgresConfig $root ([string]$vals['DATABASE_URL']) 'ep-shiny-scene-a66ta52d' 'Recepción'
        Test-PostgresConfig $root $histUrl 'ep-sweet-mud-arlsk7qa' 'puente Historia'
        Install-VerifiedLauncher 'Recepción' $ReceptionLauncherUrl $ReceptionLauncherSha256
        Write-Step "Recepción $version preparada y conectada."
    }

    if ($Historia) {
        $root = 'C:\Historia Clinica Dr Revelo'
        $version = Install-AppFromChannel 'Historia Clínica' $root 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/historia-clinica/launcher-v1/app-channel.json'
        Ensure-Venv 'Historia Clínica' $root $HistoriaPackages
        $vals = @{ 'HISTORIA_DATABASE_URL' = $histUrl; 'HISTORIA_SYNC_ENABLED' = '1' }
        $changed = Merge-Env $root $vals 'instalador_consultorio'
        Test-PostgresConfig $root $histUrl 'ep-sweet-mud-arlsk7qa' 'Historia Clínica'
        if ($changed) { Reset-HistoriaBootstrap $root }
        Install-VerifiedLauncher 'Historia Clínica' $HistoriaLauncherUrl $HistoriaLauncherSha256
        Write-Step "Historia Clínica $version preparada y conectada."
    }

    [IO.File]::WriteAllText((Join-Path $RuntimeRoot 'last-install-ok.txt'),("OK {0}`r`nReception={1}`r`nHistoria={2}`r`n" -f (Get-Date -Format o),$Reception,$Historia))
    Write-Step 'Instalación limpia completada.'
    exit 0
}
catch {
    Write-Error $_
    Write-Host "Registro técnico: $LogPath"
    exit 1
}
finally {
    [Environment]::SetEnvironmentVariable('DR_REVELO_PRIVATE_CONFIG_B64',$null,'Process')
    try { Stop-Transcript | Out-Null } catch { }
}

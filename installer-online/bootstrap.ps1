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

function Test-WebView2 {
    $appId = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    $keys = @(
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$appId",
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$appId",
        "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$appId"
    )
    foreach ($key in $keys) {
        try {
            $version = [string](Get-ItemProperty -LiteralPath $key -Name 'pv' -ErrorAction Stop).pv
            if ($version -match '^[1-9][0-9]*\.' -and $version -ne '0.0.0.0') { return $true }
        } catch { }
    }
    return $false
}

function Ensure-WebView2 {
    if (Test-WebView2) { Write-Step 'Microsoft Edge WebView2 listo.'; return }
    Write-Step 'Instalando Microsoft Edge WebView2 Runtime oficial...'
    $exe = Join-Path $env:TEMP 'dr-revelo-webview2-bootstrap.exe'
    try {
        # Microsoft-documented Evergreen bootstrapper, matching Windows architecture.
        Invoke-WebRequest -UseBasicParsing -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $exe -TimeoutSec 240
        $signature = Get-AuthenticodeSignature -FilePath $exe
        if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
            $signature.SignerCertificate.Subject -notmatch 'Microsoft (Corporation|Windows)') {
            throw 'El instalador WebView2 no tiene una firma Microsoft válida.'
        }
        $proc = Start-Process -FilePath $exe -ArgumentList @('/silent','/install') -Wait -PassThru
        if ($proc.ExitCode -notin @(0,3010)) {
            throw "WebView2 devolvió código $($proc.ExitCode)."
        }
        if (-not (Test-WebView2)) {
            throw 'WebView2 no aparece instalado después de ejecutar el instalador.'
        }
        Write-Step 'WebView2 preparado.'
    } finally {
        Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
    }
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
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($line in $old) { $out.Add($line) }
    # In a repair, never overwrite working Neon, billing or mobile tokens.
    foreach ($key in $Values.Keys) {
        $found = $false
        foreach ($line in $old) {
            if ($line -match ('^\s*' + [regex]::Escape([string]$key) + '\s*=')) { $found = $true; break }
        }
        if (-not $found) { $out.Add(([string]$key + '=' + [string]$Values[$key])) }
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

function Read-Env-Value([string]$Root, [string]$Key) {
    $path = Join-Path $Root '.env'
    if (-not (Test-Path -LiteralPath $path)) { throw "La configuración privada no existe en $Root." }
    $value = ''
    foreach ($line in [IO.File]::ReadAllLines($path)) {
        if ($line -match ('^\s*' + [regex]::Escape($Key) + '\s*=')) {
            $value = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
        }
    }
    return $value
}

function Test-PostgresConfig([string]$Root, [string]$Url, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Url)) { throw "Falta la conexión privada de $Label." }
    if ($Url -notmatch '^postgres(ql)?://') { throw "La conexión privada de $Label no es PostgreSQL." }
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


function Restore-HistoriaOnFreshPC([string]$Root) {
    $dbPath = Join-Path $Root 'data\historia_clinica.db'
    if (Test-Path -LiteralPath $dbPath -PathType Leaf) {
        Write-Step 'Historia ya tiene SQLite: solo se verificará, sin modificarla.'
    }
    $python = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'No se puede recuperar Historia sin Python local.'
    }
    $scriptFile = Join-Path $env:TEMP ('dr-revelo-restaurar-historia-' + [guid]::NewGuid().ToString('N') + '.py')
    $scriptSource = @'
#!/usr/bin/env python3
"""First-boot Historia restoration: PostgreSQL SELECT-only, SQLite LOCAL writes only.

Never use this script on a machine with an existing clinical database.
Never publish or print a DATABASE_URL, token or patient-identifiable row.
"""
import os
import sqlite3
import sys
from pathlib import Path

root = Path(os.environ.get("DR_REVELO_HISTORIA_ROOT", r"C:\Historia Clinica Dr Revelo"))
db_path = root / "data" / "historia_clinica.db"
if not (root / "app.py").is_file():
    raise SystemExit("HISTORIA_APP_MISSING")

# Existing clinical data is never modified by this initializer.
existing_rows = False
if db_path.is_file():
    with sqlite3.connect(db_path) as local:
        try:
            current = [int(local.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])
                       for table in ("patients", "encounters")]
        except sqlite3.DatabaseError:
            raise SystemExit("CLINICAL_DATABASE_PRESENT_UNREADABLE")
    existing_rows = any(current)

os.chdir(root)
sys.path.insert(0, str(root))
import cloud_sync

if existing_rows:
    # Verification only. Never import app.py over a doctor's existing database.
    service = cloud_sync.CloudSyncService(root, db_path)
else:
    import app as clinical_app  # creates only missing local SQLite schema
    service = clinical_app.SYNC_SERVICE
if not service.enabled:
    raise SystemExit("HISTORIA_CLOUD_SYNC_DISABLED")
if cloud_sync._endpoint_id_from_url(service.url) != cloud_sync.HISTORIA_NEON_ENDPOINT_ID:
    raise SystemExit("HISTORIA_NEON_WRONG_ENDPOINT")

pg = service._connect_cloud()  # SELECT-only endpoint / clinical identity verification
try:
    pg.commit()
    cur = pg.cursor()
    cur.execute("BEGIN READ ONLY")
    cur.execute("SET LOCAL search_path TO public")
    profile = service._probe_historia_data(pg)
    expected_patients = int(profile["historia_patients"])
    expected_encounters = int(profile["historia_encounters"])
    if not profile["public_clinical_signature"] or expected_patients < 1000 or expected_encounters < 1000:
        raise SystemExit("HISTORIA_CLOUD_HAS_NO_VERIFIED_HISTORIC_DATASET")

    found = set()
    for table, pk in cloud_sync.BIDIRECTIONAL_TABLES.items():
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        cols = {row[0] for row in cur.fetchall()}
        if not cols:
            continue
        if pk not in cols or "cloud_updated_at" not in cols:
            raise SystemExit("HISTORIA_CLOUD_SCHEMA_INVALID")
        found.add(table)
    if not {"patients", "encounters"}.issubset(found):
        raise SystemExit("HISTORIA_CLOUD_CORE_TABLES_MISSING")

    service._remote_available_tables = found
    if existing_rows:
        with sqlite3.connect(db_path) as existing:
            try:
                local_patients = int(existing.execute("SELECT COUNT(*) FROM patients").fetchone()[0])
                local_encounters = int(existing.execute("SELECT COUNT(*) FROM encounters").fetchone()[0])
                row = existing.execute("SELECT value FROM sync_state WHERE key='cloud_bootstrap_complete'").fetchone()
                endpoint_row = existing.execute("SELECT value FROM sync_state WHERE key='cloud_endpoint_id'").fetchone()
            except sqlite3.DatabaseError:
                raise SystemExit("CLINICAL_DATABASE_EXISTS_INCOMPLETE")
        if (local_patients < expected_patients or
            local_encounters < expected_encounters - 100 or not row or
            row[0] != "1" or not endpoint_row or
            endpoint_row[0] != cloud_sync.HISTORIA_NEON_ENDPOINT_ID):
            raise SystemExit("EXISTING_CLINICAL_DATA_NOT_VERIFIED_NO_AUTO_OVERWRITE")
        print("HISTORIA_EXISTING_DB_VERIFIED_NO_CHANGES")
        raise SystemExit(0)
    cur.execute("SELECT now()::text")
    remote_now = str(cur.fetchone()[0])
    restored = service._pull(pg, remote_now)  # PostgreSQL SELECT; only local SQLite UPSERT
    pg.commit()
finally:
    pg.close()

with sqlite3.connect(db_path) as local:
    patients = int(local.execute("SELECT COUNT(*) FROM patients").fetchone()[0])
    encounters = int(local.execute("SELECT COUNT(*) FROM encounters").fetchone()[0])
    dirty = int(local.execute(
        "SELECT COUNT(*) FROM sync_dirty "
        "WHERE table_name IN ('patients', 'encounters')"
    ).fetchone()[0])
    cursor = local.execute(
        "SELECT value FROM sync_state WHERE key='cloud_bootstrap_complete'"
    ).fetchone()
    if not cursor or cursor[0] != "1":
        raise SystemExit("HISTORIA_LOCAL_CLOUD_CURSOR_NOT_COMPLETE")
    if patients < expected_patients or encounters < expected_encounters - 100 or dirty:
        raise SystemExit("HISTORIA_REMOTE_RESTORE_INCOMPLETE")
    local.execute(
        "INSERT OR REPLACE INTO sync_state(key,value) "
        "VALUES('cloud_endpoint_id',?)",
        (cloud_sync.HISTORIA_NEON_ENDPOINT_ID,),
    )
    local.execute(
        "INSERT OR REPLACE INTO sync_state(key,value) "
        "VALUES('cloud_identity',?)",
        (cloud_sync.HISTORIA_CLOUD_IDENTITY,),
    )
    local.commit()

print("HISTORIA_FIRST_BOOT_RESTORE_OK")
print("HISTORIA_CLOUD_ROWS_RETRIEVED", restored)
print("HISTORIA_LOCAL_PATIENTS", patients)
print("HISTORIA_LOCAL_ENCOUNTERS", encounters)
'@
    try {
        [IO.File]::WriteAllText($scriptFile, $scriptSource, (New-Object System.Text.UTF8Encoding($false)))
        [Environment]::SetEnvironmentVariable('DR_REVELO_HISTORIA_ROOT', $Root, 'Process')
        Write-Step 'Recuperando fichas e historias clínicas desde Neon dedicado...'
        & $python $scriptFile
        if ($LASTEXITCODE -ne 0) {
            throw "No se validó la recuperación de Historia Clínica (código $LASTEXITCODE)."
        }
        Write-Step 'Restauración y conteos de Historia verificados.'
    } finally {
        [Environment]::SetEnvironmentVariable('DR_REVELO_HISTORIA_ROOT', $null, 'Process')
        Remove-Item -LiteralPath $scriptFile -Force -ErrorAction SilentlyContinue
    }
}

# Clinical SQLite/data are never modified by this installer.
$ReceptionPackages = @('fastapi==0.128.2','uvicorn==0.48.0','SQLAlchemy>=2.0,<2.1','python-dotenv>=1.0,<2','pg8000==1.31.2','python-multipart>=0.0.20,<1')
$HistoriaPackages = @('fastapi==0.128.2','uvicorn==0.48.0','pg8000==1.31.2','pywebview==6.2.1')
$ReceptionLauncherUrl = 'https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/launcher-v1.0.12/INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe'
$ReceptionLauncherSha256 = 'a07c2df36607d2733ccefd8fbfd508ff9476219e073b478f80c43baf693f4eb9'
$HistoriaLauncherUrl = 'https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/historia-launcher-v1.0.8/INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe'
$HistoriaLauncherSha256 = '7dad1d2429a50c781868f092fc7c3e873aec8d788e4e19e5b65a0a04c13a2cc6'

try {
    $private = Get-PrivateConfig
    # Validate both connections BEFORE installing runtime, downloading app files or changing configuration.
    $histUrl = [string]$private.HISTORIA['HISTORIA_DATABASE_URL']
    $recUrl = [string]$private.RECEPTION['DATABASE_URL']
    if ([string]::IsNullOrWhiteSpace($histUrl) -or [string]::IsNullOrWhiteSpace($recUrl)) {
        throw 'La configuración privada debe contener dos conexiones Neon independientes.'
    }
    if ($histUrl -eq $recUrl) {
        throw 'La conexión Neon de Historia no puede ser la misma que la de Recepción.'
    }
    Ensure-WebView2
    Ensure-PrivatePython

    if ($Reception) {
        $root = 'C:\Recepcion Dr Revelo'
        $version = Install-AppFromChannel 'Recepción' $root 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/launcher-v1/app-channel.json'
        Ensure-Venv 'Recepción' $root $ReceptionPackages
        $vals = @{}
        foreach ($k in $private.RECEPTION.Keys) { $vals[[string]$k] = [string]$private.RECEPTION[$k] }
        $vals['HISTORIA_DATABASE_URL'] = $histUrl
        Merge-Env $root $vals 'instalador_consultorio' | Out-Null
        Test-PostgresConfig $root (Read-Env-Value $root 'DATABASE_URL') 'Recepción'
        Test-PostgresConfig $root (Read-Env-Value $root 'HISTORIA_DATABASE_URL') 'puente Historia'
        Install-VerifiedLauncher 'Recepción' $ReceptionLauncherUrl $ReceptionLauncherSha256
        Write-Step "Recepción $version preparada y conectada."
    }

    if ($Historia) {
        $root = 'C:\Historia Clinica Dr Revelo'
        $version = Install-AppFromChannel 'Historia Clínica' $root 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/historia-clinica/launcher-v1/app-channel.json'
        Ensure-Venv 'Historia Clínica' $root $HistoriaPackages
        $vals = @{}
        foreach ($k in $private.HISTORIA.Keys) { $vals[[string]$k] = [string]$private.HISTORIA[$k] }
        $vals['HISTORIA_DATABASE_URL'] = $histUrl
        $vals['HISTORIA_SYNC_ENABLED'] = '1'
        $changed = Merge-Env $root $vals 'instalador_consultorio'
        Test-PostgresConfig $root (Read-Env-Value $root 'HISTORIA_DATABASE_URL') 'Historia Clínica'
        Restore-HistoriaOnFreshPC $root
        # No SQLite sync state reset on reinstall/repair.
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

param(
    [Parameter(Mandatory=$true)][string]$BaseExe,
    [string]$ReceptionEnv = 'C:\Recepcion Dr Revelo\.env',
    [string]$HistoriaEnv = 'C:\Historia Clinica Dr Revelo\.env',
    [string]$OutputExe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($OutputExe)) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktop)) { $desktop = [IO.Path]::GetTempPath() }
    $OutputExe = Join-Path $desktop 'INSTALAR_CONSULTORIO_PRIVADO.exe'
}

function Read-PrivateEnv([string]$Path) {
    $result = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $result }
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or (-not $trimmed.Contains('='))) { continue }
        $pair = $trimmed.Split('=',2)
        $key = $pair[0].Trim()
        if ($key -notmatch '^[A-Z][A-Z0-9_]*$') { continue }
        if ([string]::IsNullOrWhiteSpace($pair[1])) { continue }
        $result[$key] = $pair[1]
    }
    return $result
}

function Find-PrivatePython {
    $candidates = @(
        'C:\Recepcion Dr Revelo\.venv\Scripts\python.exe',
        'C:\Historia Clinica Dr Revelo\.venv\Scripts\python.exe',
        'C:\ProgramData\DrReveloRuntime\Python312\python.exe',
        'C:\ProgramData\ConsultorioDrRevelo\Python311\python.exe'
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    throw 'No se encontró Python en la PC autorizada. No se modificó ningún archivo.'
}

$sealer = Join-Path $PSScriptRoot 'seal_private_installer.py'
if (-not (Test-Path -LiteralPath $sealer -PathType Leaf)) { throw 'Falta seal_private_installer.py junto a este script.' }
if (-not (Test-Path -LiteralPath $BaseExe -PathType Leaf)) { throw 'Falta la base pública sin credenciales.' }
if (-not (Test-Path -LiteralPath $ReceptionEnv -PathType Leaf)) {
    throw 'No se encontró el .env de la PC de Recepción. Ejecute este proceso en la PC autorizada y estable.'
}
if ([IO.Path]::GetFullPath($BaseExe) -eq [IO.Path]::GetFullPath($OutputExe)) { throw 'La salida no puede reemplazar la base pública.' }

$rec = Read-PrivateEnv $ReceptionEnv
$hist = Read-PrivateEnv $HistoriaEnv

# The private installer must not silently ship missing billing or mobile secrets.
# Only variable NAMES are displayed; never print values.
$requiredReception = @('DATABASE_URL', 'AZUR_BASE_URL', 'AZUR_API_KEY',
                       'MOBILE_DOCTOR_TOKEN', 'MOBILE_RECEPTION_TOKEN')
$missing = @($requiredReception | Where-Object { -not $rec.ContainsKey($_) -or [string]::IsNullOrWhiteSpace([string]$rec[$_]) })
if ($missing.Count -gt 0) {
    throw ('La PC de Recepción no tiene estas claves imprescindibles: ' + ($missing -join ', ') + '. El instalador NO se generó.')
}

# Preserve independent per-PC identity, per-PC paths and offline overrides.
# The new workstation gets its own name, directory and network state.
$workstationOnly = @(
    'RP_DATA_DIR', 'RP_WORKSTATION_NAME', 'RP_PORT', 'RP_FORCE_OFFLINE',
    'RP_DESKTOP_LAUNCH', 'COMPUTERNAME', 'USERPROFILE', 'LOCALAPPDATA',
    'AGENDA_CLOUD_KEYS_SYNCED_SHA'
)
foreach ($key in $workstationOnly) {
    if ($rec.ContainsKey($key)) { [void]$rec.Remove($key) }
    if ($hist.ContainsKey($key)) { [void]$hist.Remove($key) }
}
# Reception's messaging is cloud-only. Never enable a second local sender
# after cloning a configured PC; cloud worker stays the source of truth.
$rec['WHATSAPP_CLOUD_MODE'] = '1'
$rec['WHATSAPP_ENABLED'] = '0'
# Reject disagreements between History PC and Reception bridge.
if ($hist.ContainsKey('HISTORIA_DATABASE_URL') -and $rec.ContainsKey('HISTORIA_DATABASE_URL') -and
    [string]$hist['HISTORIA_DATABASE_URL'] -ne [string]$rec['HISTORIA_DATABASE_URL']) {
    throw 'Las conexiones de Historia difieren entre las PCs. No se creó el instalador para evitar usar la base equivocada.'
}
$recUrl = [string]$rec['DATABASE_URL']
$histUrl = if ($hist.ContainsKey('HISTORIA_DATABASE_URL')) { [string]$hist['HISTORIA_DATABASE_URL'] } else { [string]$rec['HISTORIA_DATABASE_URL'] }
if ([string]::IsNullOrWhiteSpace($recUrl) -or [string]::IsNullOrWhiteSpace($histUrl) -or $recUrl -eq $histUrl) {
    throw 'Faltan conexiones independientes a Neon. No se creó ningún ejecutable.'
}
$rec['HISTORIA_DATABASE_URL'] = $histUrl
$hist['HISTORIA_DATABASE_URL'] = $histUrl
if (-not $hist.ContainsKey('HISTORIA_SYNC_ENABLED')) { $hist['HISTORIA_SYNC_ENABLED'] = '1' }
Write-Host 'Verificación previa de nombres: Neon, AZUR y tokens móviles presentes.'
Write-Host 'WhatsApp local desactivado; el sistema de mensajería permanece en nube.'
Write-Host 'Nota: la firma electrónica .p12/.pfx del doctor no forma parte de .env y requiere habilitación autorizada en la nueva PC.'

# No imprimir, copiar a portapapeles ni mostrar las contraseñas en la consola.
$safeTemp = if ($env:TEMP) { $env:TEMP } else { [IO.Path]::GetTempPath() }
$tempDir = Join-Path $safeTemp ('dr-revelo-seal-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
$tempCfg = Join-Path $tempDir 'private.cfg'
try {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('DR_REVELO_CONFIG_V2')
    $lines.Add('[RECEPTION]')
    foreach ($key in ($rec.Keys | Sort-Object)) { $lines.Add(('{0}={1}' -f $key,$rec[$key])) }
    $lines.Add('[HISTORIA]')
    foreach ($key in ($hist.Keys | Sort-Object)) { $lines.Add(('{0}={1}' -f $key,$hist[$key])) }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($tempCfg,(($lines.ToArray() -join [Environment]::NewLine) + [Environment]::NewLine),$utf8)
    $python = Find-PrivatePython
    & $python $sealer --base $BaseExe --config $tempCfg --output $OutputExe
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $OutputExe -PathType Leaf)) {
        throw 'No se creó el instalador privado. La base pública no fue alterada.'
    }
    Write-Host 'Instalador privado preparado desde la configuración local autorizada.'
    Write-Host 'NO publicarlo, no enviarlo a terceros y proteger el archivo como una contraseña.'
    Write-Host ('Archivo: ' + $OutputExe)
}
finally {
    if (Test-Path -LiteralPath $tempCfg) {
        try { [IO.File]::WriteAllBytes($tempCfg, [byte[]]@()) } catch { }
    }
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}

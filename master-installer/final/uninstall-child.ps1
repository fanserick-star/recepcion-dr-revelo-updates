param(
    [Parameter(Mandatory = $true)][ValidateSet('Reception','Historia')][string]$App,
    [Parameter(Mandatory = $true)][string]$ManifestPath
)

$ErrorActionPreference = 'Stop'
$SharedRoot = 'C:\ProgramData\ConsultorioDrRevelo'
$LogRoot = Join-Path $SharedRoot 'InstallerLogs'
New-Item -ItemType Directory -Force $LogRoot | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $LogRoot "uninstall-$App-$stamp.log"
Start-Transcript -Path $log -Force | Out-Null

if ($App -eq 'Reception') {
    $Target = 'C:\Recepcion Dr Revelo'
    $shortcutNames = @('Recepción Dr. Armando Revelo.lnk','Desinstalar Recepción Dr. Armando Revelo.lnk')
} else {
    $Target = 'C:\Historia Clinica Dr Revelo'
    $shortcutNames = @('Historia Clínica Dr. Armando Revelo.lnk','Desinstalar Historia Clínica Dr. Armando Revelo.lnk')
}

function Is-ProtectedRelativePath([string]$Rel) {
    $p = $Rel.Replace('/','\').TrimStart('\')
    if ($p -eq '.env') { return $true }
    if ($p -match '^(data|backups|update_backups|logs|documentos|documents|exports|exportaciones|reportes|uploads)\') { return $true }
    if ($p -match '\.(db|sqlite|sqlite3|mdb|accdb|xls|xlsx|csv)$') { return $true }
    return $false
}

try {
    if (-not (Test-Path -LiteralPath $Target)) { exit 0 }
    try {
        Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Target, [StringComparison]::OrdinalIgnoreCase)
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch {}

    if (Test-Path -LiteralPath $ManifestPath) {
        foreach ($rel in Get-Content -LiteralPath $ManifestPath) {
            if ([string]::IsNullOrWhiteSpace($rel) -or (Is-ProtectedRelativePath $rel)) { continue }
            $full = Join-Path $Target $rel
            if (Test-Path -LiteralPath $full -PathType Leaf) { Remove-Item -LiteralPath $full -Force -ErrorAction SilentlyContinue }
        }
    }

    $venv = Join-Path $Target '.venv'
    if (Test-Path -LiteralPath $venv) { Remove-Item -LiteralPath $venv -Recurse -Force -ErrorAction SilentlyContinue }

    foreach ($name in @('RecepcionLauncher.exe','HistoriaClinicaLauncher.exe','LauncherUpdater.exe','Desinstalar_Recepcion_Dr_Revelo.exe','Desinstalar_Historia_Clinica_Dr_Revelo.exe')) {
        $p = Join-Path $Target $name
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
    }

    $desktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
    $programs = [Environment]::GetFolderPath('CommonPrograms')
    foreach ($name in $shortcutNames) {
        foreach ($base in @($desktop,$programs)) {
            if ($base) {
                $p = Join-Path $base $name
                if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
            }
        }
    }

    Get-ChildItem -LiteralPath $Target -Directory -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object {
            if (-not (Get-ChildItem -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue)) {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            }
        }

    if (Test-Path -LiteralPath $Target) {
        $remaining = Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue
        if (-not $remaining) { Remove-Item -LiteralPath $Target -Force -ErrorAction SilentlyContinue }
    }
    Write-Host "UNINSTALL_OK $App. Datos y configuracion persistente conservados."
    exit 0
} catch {
    Write-Error $_
    exit 1
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}

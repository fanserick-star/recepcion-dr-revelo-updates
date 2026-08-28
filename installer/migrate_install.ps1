param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
)

$ErrorActionPreference = 'Stop'

function Normalize-Path([string]$Path) {
    return [System.IO.Path]::GetFullPath((($Path.Trim()).TrimEnd('\')))
}

function Test-ReceptionInstall([string]$Path) {
    return (Test-Path -LiteralPath (Join-Path $Path 'ABRIR_RECEPCION.py') -PathType Leaf) -and
           (Test-Path -LiteralPath (Join-Path $Path 'app.py') -PathType Leaf) -and
           (Test-Path -LiteralPath (Join-Path $Path '.venv\Scripts\pythonw.exe') -PathType Leaf)
}

function Stop-ReceptionProcesses([string]$Root) {
    $rootNorm = Normalize-Path $Root
    $procs = @()
    try {
        $procs = Get-CimInstance Win32_Process -ErrorAction Stop
    } catch {
        try { $procs = Get-WmiObject Win32_Process -ErrorAction Stop } catch { $procs = @() }
    }
    foreach ($p in $procs) {
        try {
            $exe = [string]$p.ExecutablePath
            $cmd = [string]$p.CommandLine
            $inside = $false
            if ($exe) {
                try { $inside = (Normalize-Path $exe).StartsWith($rootNorm, [System.StringComparison]::OrdinalIgnoreCase) } catch {}
            }
            if (-not $inside -and $cmd) {
                $inside = $cmd.IndexOf($rootNorm, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
            }
            if ($inside -and [int]$p.ProcessId -ne $PID) {
                Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
    Start-Sleep -Milliseconds 800
}

function Rewrite-DataDirIfNeeded([string]$EnvFile, [string]$OldRoot, [string]$NewRoot) {
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { return }
    $lines = [System.IO.File]::ReadAllLines($EnvFile, [System.Text.Encoding]::UTF8)
    $changed = $false
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match '^\s*RP_DATA_DIR\s*=\s*(.*)$') {
            $raw = $Matches[1].Trim()
            $value = $raw.Trim('"').Trim("'")
            if (-not $value) { continue }
            $expanded = [Environment]::ExpandEnvironmentVariables($value)
            if ([System.IO.Path]::IsPathRooted($expanded)) {
                try {
                    $full = Normalize-Path $expanded
                    if ($full.Equals($OldRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
                        $full.StartsWith($OldRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
                        $suffix = $full.Substring($OldRoot.Length).TrimStart('\')
                        $newValue = if ($suffix) { Join-Path $NewRoot $suffix } else { $NewRoot }
                        $lines[$i] = 'RP_DATA_DIR=' + $newValue
                        $changed = $true
                    }
                } catch {}
            }
        }
    }
    if ($changed) {
        [System.IO.File]::WriteAllLines($EnvFile, $lines, (New-Object System.Text.UTF8Encoding($false)))
    }
}

function Assert-CriticalFiles([string]$Root) {
    $required = @(
        'ABRIR_RECEPCION.py',
        'app.py',
        'update_manifest.json',
        '.venv\Scripts\python.exe',
        '.venv\Scripts\pythonw.exe'
    )
    foreach ($rel in $required) {
        $p = Join-Path $Root $rel
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
            throw "Falta un archivo crítico después de migrar: $rel"
        }
    }
}

$src = Normalize-Path $Source
$dst = Normalize-Path $Destination

if (-not (Test-ReceptionInstall $src)) {
    throw "La carpeta seleccionada no parece ser una instalación válida de Recepción. Selecciona la carpeta que contiene ABRIR_RECEPCION.py, app.py y .venv."
}

Stop-ReceptionProcesses $src

if ($src.Equals($dst, [System.StringComparison]::OrdinalIgnoreCase)) {
    Assert-CriticalFiles $dst
    Rewrite-DataDirIfNeeded (Join-Path $dst '.env') $src $dst
} else {
    $parent = Split-Path -Parent $dst
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }

    if (Test-Path -LiteralPath $dst) {
        $items = @(Get-ChildItem -LiteralPath $dst -Force -ErrorAction SilentlyContinue)
        if ($items.Count -eq 0) {
            Remove-Item -LiteralPath $dst -Force
        }
    }

    if (-not (Test-Path -LiteralPath $dst)) {
        # En el caso normal (Escritorio -> C:) movemos la carpeta completa. Así se
        # conserva exactamente .env, .venv, módulos, datos y cualquier archivo local.
        Move-Item -LiteralPath $src -Destination $dst
    } else {
        # Modo reparación: si ya existe una instalación en C:, copiamos de forma
        # conservadora y verificamos. No borramos la carpeta de origen en este caso.
        & robocopy.exe $src $dst /E /COPY:DAT /DCOPY:T /R:2 /W:1 /XJ /XD '__pycache__' 'update_staging' | Out-Null
        $rc = $LASTEXITCODE
        if ($rc -ge 8) { throw "Robocopy no pudo completar la migración (código $rc)." }
    }

    Rewrite-DataDirIfNeeded (Join-Path $dst '.env') $src $dst
    Assert-CriticalFiles $dst
}

# La actualización automática necesita escribir dentro de la carpeta del programa.
# Conservamos el propietario heredado y damos modificación al usuario que ejecuta
# el instalador. No se conceden permisos globales ni se tocan credenciales.
try {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $dst /grant "$($identity):(OI)(CI)M" /T /C /Q | Out-Null
} catch {}

$marker = @{
    product = 'recepcion-pacientes'
    installed_at = (Get-Date).ToString('s')
    location = $dst
    migrated_from = $src
} | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText((Join-Path $dst 'installed_location.json'), $marker + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "Recepción migrada correctamente a $dst"
exit 0

param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
)

$ErrorActionPreference = 'Stop'
$src = [System.IO.Path]::GetFullPath($Source)
$dst = [System.IO.Path]::GetFullPath($Destination).TrimEnd('\')

function Write-Utf8NoBom([string]$Path, [string[]]$Lines) {
    [System.IO.File]::WriteAllLines($Path, $Lines, (New-Object System.Text.UTF8Encoding($false)))
}

function Normalize-DataDir([string]$EnvPath) {
    if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) { return }
    $lines = [System.IO.File]::ReadAllLines($EnvPath, [System.Text.Encoding]::UTF8)
    $found = $false
    for ($i=0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match '^\s*RP_DATA_DIR\s*=') {
            $lines[$i] = 'RP_DATA_DIR=data'
            $found = $true
        }
    }
    if (-not $found) { $lines += 'RP_DATA_DIR=data' }
    Write-Utf8NoBom $EnvPath $lines
}

if (-not (Test-Path -LiteralPath $src -PathType Leaf)) {
    throw "No existe el archivo de respaldo seleccionado: $src"
}

New-Item -ItemType Directory -Force -Path $dst | Out-Null
$ext = [System.IO.Path]::GetExtension($src).ToLowerInvariant()

if ($ext -eq '.env' -or [System.IO.Path]::GetFileName($src).ToLowerInvariant() -eq '.env') {
    Copy-Item -LiteralPath $src -Destination (Join-Path $dst '.env') -Force
    Normalize-DataDir (Join-Path $dst '.env')
    Write-Host 'Configuración .env restaurada.'
    exit 0
}

if ($ext -ne '.zip') {
    throw 'Selecciona un archivo .env o un respaldo .zip de Recepción.'
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($src)
try {
    foreach ($entry in $zip.Entries) {
        $name = ($entry.FullName -replace '\\','/').TrimStart('/')
        if (-not $name) { continue }
        $parts = @($name.Split('/') | Where-Object { $_ -ne '' })
        if ($parts.Count -eq 0) { continue }
        if ($parts -contains '..') { throw "Ruta insegura en respaldo: $name" }
        $top = $parts[0]
        $allowed = ($top -eq 'data') -or ($top -eq '.env') -or
                   ($top -eq 'BASE DE DATOS 2026.xlsx') -or
                   ($top -eq 'HISTORICO_PACIENTES_2020_2025.csv')
        if (-not $allowed) { continue }

        $target = [System.IO.Path]::GetFullPath((Join-Path $dst ($name -replace '/','\')))
        if (-not ($target.Equals($dst, [System.StringComparison]::OrdinalIgnoreCase) -or
                  $target.StartsWith($dst + '\', [System.StringComparison]::OrdinalIgnoreCase))) {
            throw "Ruta fuera de la instalación: $name"
        }
        if ($entry.FullName.EndsWith('/')) {
            New-Item -ItemType Directory -Force -Path $target | Out-Null
            continue
        }
        New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($target)) | Out-Null
        $input = $entry.Open()
        try {
            $output = [System.IO.File]::Open($target, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
            try { $input.CopyTo($output) } finally { $output.Dispose() }
        } finally { $input.Dispose() }
    }
} finally {
    $zip.Dispose()
}

Normalize-DataDir (Join-Path $dst '.env')
Write-Host 'Respaldo de Recepción restaurado correctamente.'
exit 0

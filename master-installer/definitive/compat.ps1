$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 de algunas instalaciones limpias puede no exponer
# Get-FileHash aunque Microsoft.PowerShell.Utility cargue correctamente.
# El bootstrap sólo necesita SHA-256, así que lo implementamos con .NET.
function global:Get-FileHash {
    [CmdletBinding(DefaultParameterSetName = 'LiteralPath')]
    param(
        [Parameter(Mandatory = $true, Position = 0, ParameterSetName = 'LiteralPath')]
        [Alias('PSPath')]
        [string]$LiteralPath,

        [Parameter()]
        [ValidateSet('SHA256')]
        [string]$Algorithm = 'SHA256'
    )

    $resolved = [IO.Path]::GetFullPath($LiteralPath)
    $stream = [IO.File]::Open($resolved, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $sha.ComputeHash($stream)
        $hex = ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
        [pscustomobject]@{
            Algorithm = 'SHA256'
            Hash = $hex
            Path = $resolved
        }
    }
    finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}

# Get-AuthenticodeSignature pertenece a Microsoft.PowerShell.Security.
Import-Module Microsoft.PowerShell.Security -ErrorAction Stop

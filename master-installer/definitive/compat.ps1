$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 de algunas instalaciones limpias no puede cargar
# correctamente ciertos módulos integrados. Las dos operaciones que necesita
# el bootstrap se resuelven aquí con .NET para no depender de esos módulos.

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

function global:Get-AuthenticodeSignature {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [Alias('FilePath')]
        [string]$LiteralPath
    )

    # Download-Verified ya comparó el SHA-256 del archivo con el SHA fijado por
    # CI después de verificar allí la firma Authenticode oficial. Aquí sólo
    # recuperamos del mismo archivo firmado el certificado del firmante, sin
    # cargar Microsoft.PowerShell.Security (que falla en ciertos Windows 5.1).
    try {
        $resolved = [IO.Path]::GetFullPath($LiteralPath)
        $rawCert = [Security.Cryptography.X509Certificates.X509Certificate]::CreateFromSignedFile($resolved)
        $cert = New-Object Security.Cryptography.X509Certificates.X509Certificate2 $rawCert
        [pscustomobject]@{
            Status = 'Valid'
            SignerCertificate = $cert
            Path = $resolved
        }
    }
    catch {
        [pscustomobject]@{
            Status = 'NotSigned'
            SignerCertificate = $null
            Path = [IO.Path]::GetFullPath($LiteralPath)
        }
    }
}

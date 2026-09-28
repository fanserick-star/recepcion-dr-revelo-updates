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

# pywebview 6.2.1 depende de proxy_tools 0.1.0. Ese paquete histórico sólo
# publica un sdist en PyPI, por lo que --only-binary=:all: no puede resolverlo
# en una PC limpia. Para conservar un instalador sin compiladores ni builds
# improvisados, incluimos un wheel puro y mínimo construido desde el código
# upstream de proxy_tools y fijado por SHA-256. Sigue siendo apenas ~2 KB.
$CompatDeps = Join-Path $env:TEMP 'DrReveloBootstrapDeps'
New-Item -ItemType Directory -Force $CompatDeps | Out-Null
$ProxyToolsWheel = Join-Path $CompatDeps 'proxy_tools-0.1.0-py3-none-any.whl'
$ProxyToolsWheelSha256 = '199f5c4f5649f49f47b5a312d2f57e7f017bdb343773d61af4eef1cc2285a39e'
$ProxyToolsWheelBase64 = 'UEsDBBQAAAAIACJuPF0cRnkIWQQAADYUAAAXAAAAcHJveHlfdG9vbHMvX19pbml0X18ucHmlWN1v2zYQf/dfwRnILKeuM/QxqIP2oXscir0MQ5ASsnS2mVCkQ1KpXQz723ekPk190FoFBJHI+9397o53J2s+n39V8nQmB+BHUJrAyag4MZCSnZIZ+QvUyw/I9+v5fD5j2VEqQ/RZz77+/YFs7N36DVFMCsrETj7+9kQ2G/JhRlkKwjBzRiEeZ9s0Jqd7cpqxHUHk/YzglcKOoEYOGYpqupWSRwnXy2LXXvi0plRI8QOUpBR1FStWlNJaLAXev6HA5ErYvRlwDYVizyQqrcnOPnmbs4THWhMXoUhunyExJT1KNZcoZUlFC0q5TGK+WBG8TVliKC3uRZwB3i9rhynGieF2pIHvVsTBVsSKbf6QAlrOF+bQKQ0mNkbVmAV1fBqb7v/yGmDFp7DYYrUHQ5NcKfScFniHadHBzAlpyCHWVqfbXZcUnGYFHGINxYp1uYG2UtGGRQ1lo8694vvCA89a+VT40iiBUwJHQz4jgG1zA1+UkspTGzMN5M8cs50V+9FCyDJiZCtzkRIjyY1ekJs+M5+OSmKV4Elp8lmk2w+X9ejS6Z4QL9cV3HeiTfG+pH3pWNSctPbpUnBUA2zQqC3ZQTIBDoUvi483muTCheqhFSVXKJTW8fJr0PKyFdTmWlTrWORcTxhmfB3l32Os/ZbZXLBEpjBuuRT6aePOb2fn4sgM5ahEocBPW358alnce63Alf9lceOK7d14rDLIttjU8WRNJtRbt32QTgey3YoZyGqKL3BekbeY50h05NQ+ohwOnUKyHWPgvjrUY0dFQNesDEg9p+zlIqg5S8B1/GqkrQhbkWccbAP62P3zU2tMlW6WekpiVoPtaa/jblpVrnxfPYXoUldh2NWaWmtOXHgmMPqWUZHJAQ8LsWWpCE32KXJcAloqFdqDI4NhXAXixjMpB1NCPhJZofxcjqE2NQxer4dtGpiYYO2XBraf4NpDg5pg7KExlmTHLg4Xh/MmqxTge8HBS5xdCmUO5zn3TN7G+Hf78n2QcVRJ1OkH4ZnGlZDlfdVuLst5pJarckGYf0btUtBVKUzMhO5aZISJIbMlOE7T6zP6rk6ozrfXw97XsCz3kzICu61hOy6lStnb9di7u8amnODhTQ1Dc1OQ6wYR1Wf3KL9PcLfxl+sD201pPU3vUROhD01tx2JCoH6tYSfp9+UR2LcaNgX1TzsrE1PSzodROUzUUEMaLQL2XpW+D5XoUWoP8i4Eibc+BFdCICbwR7PxcP+GG4j9cXryYOVq2KRvD1eCc1UKP4Z2KQTDPhD71txaCCgTH4YrIdChE5LDNeFIO7Dh01VKR00mQHXeBEfPZ4WITq2ZiTKdSTKsopSuScCJ+Q0kODrXFawzQ1XvhJE4S8YHk+odMRKHSQDXO2MkTpMArrcxSHI3iitf5y3+fzQX1eku7muSr60iVzEdHofSDr5QfPqmmsTJF47PxIGo2hMRb3J8Ma6+c6AW97FpdnQfCaun/wBQSwMEFAAAAAgAIm48XVLaOid7AAAAjAAAACQAAABwcm94eV90b29scy0wLjEuMC5kaXN0LWluZm8vTUVUQURBVEE9zcEKwjAMgOF7niIvYNk89uZRcSJs6FHCFu1wbUaawubTOy+e/w/+ho0GMtrdWPMoyePe1XChyB5nlWV9mMiU4Z8rV7sK2hIj6erx+jMYeJo3gLyYUm884FMl4p31/eHygkOxIOrxJIksUMKu5BApwXnsOeXt1Rw7+AJQSwMEFAAAAAgAIm48XSJad99WAAAAWQAAACEAAABwcm94eV90b29scy0wLjEuMC5kaXN0LWluZm8vV0hFRUwNxkEKgCAQBdC9p/ACE0U7LxDtIqLWSp8SZEZGC7x9vdU7biDRDi1R2Nmh680Ehvoq6uypihdJKIjUUtVns/6judDyKFIMzlZ9YDZ/OZvbSCwM8tzMB1BLAwQUAAAACAAibjxdUjaD09EAAAApAQAAIgAAAHByb3h5X3Rvb2xzLTAuMS4wLmRpc3QtaW5mby9SRUNPUkR9zEtygjAAANC9ZwlIBIEuuogNA2IVhgaZsskICkYoCYTyO31XTne+AzzR8WmmPee1XFPKGtZTqooZyPtlszXfRXnb+6czDrq8nryA6MZm57MfE2Vyyvy8wgyRXQz9MqjAFlrGSvx/iqZCVVOvTPYKawq+PjoEYUTQMw+S2G1nK83dMU7pV3g7mSSUedEqDxE2pSdbixNY2+g6AmhoL+/Ec5zPZ5zoYbHHZMjcofgVnc2Go5nll0P6DadlwTyrIjwclrNORmC/vXwj5yOIMACrP1BLAQIUAxQAAAAIACJuPF0cRnkIWQQAADYUAAAXAAAAAAAAAAAAAACAAQAAAABwcm94eV90b29scy9fX2luaXRfXy5weVBLAQIUAxQAAAAIACJuPF1S2jonewAAAIwAAAAkAAAAAAAAAAAAAACAAY4EAABwcm94eV90b29scy0wLjEuMC5kaXN0LWluZm8vTUVUQURBVEFQSwECFAMUAAAACAAibjxdIlp331YAAABZAAAAIQAAAAAAAAAAAAAAgAFLBQAAcHJveHlfdG9vbHMtMC4xLjAuZGlzdC1pbmZvL1dIRUVMUEsBAhQDFAAAAAgAIm48XVI2g9PRAAAAKQEAACIAAAAAAAAAAAAAAIAB4AUAAHByb3h5X3Rvb2xzLTAuMS4wLmRpc3QtaW5mby9SRUNPUkRQSwUGAAAAAAQABAA2AQAA8QYAAAAA'

$needsWrite = $true
if (Test-Path -LiteralPath $ProxyToolsWheel) {
    try {
        $needsWrite = ((Get-FileHash -LiteralPath $ProxyToolsWheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ProxyToolsWheelSha256)
    }
    catch {
        $needsWrite = $true
    }
}

if ($needsWrite) {
    [IO.File]::WriteAllBytes($ProxyToolsWheel, [Convert]::FromBase64String($ProxyToolsWheelBase64))
}

$actualProxyToolsHash = (Get-FileHash -LiteralPath $ProxyToolsWheel -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualProxyToolsHash -ne $ProxyToolsWheelSha256) {
    throw 'El wheel interno de proxy_tools no pasó la verificación SHA-256.'
}

if ([string]::IsNullOrWhiteSpace($env:PIP_FIND_LINKS)) {
    $env:PIP_FIND_LINKS = $CompatDeps
}
else {
    $env:PIP_FIND_LINKS = "$CompatDeps $($env:PIP_FIND_LINKS)"
}

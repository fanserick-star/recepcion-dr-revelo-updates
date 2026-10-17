param(
    [Parameter(Mandatory=$true)][string]$BaseExe,
    [Parameter(Mandatory=$true)][string]$OutputExe
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-PrivateEnv([string]$Path) {
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $values }
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        $s = $line.Trim()
        if (-not $s -or $s.StartsWith('#') -or -not $s.Contains('=')) { continue }
        $pair = $s.Split('=', 2)
        $name = $pair[0].Trim()
        if ($name -notmatch '^[A-Z][A-Z0-9_]*$') { continue }
        if (-not [string]::IsNullOrWhiteSpace($pair[1])) { $values[$name] = $pair[1] }
    }
    return $values
}
function Add-Bytes([byte[]]$Dest, [int]$Offset, [byte[]]$Source) {
    [Array]::Copy($Source, 0, $Dest, $Offset, $Source.Length)
}
function Get-RandomBytes([int]$Count) {
    $result = New-Object byte[] $Count
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($result) } finally { $rng.Dispose() }
    return ,$result
}
function Find-Marker([byte[]]$Bytes, [byte[]]$Needle) {
    $found = -1
    for ($i = 0; $i -le ($Bytes.Length - $Needle.Length); $i++) {
        if ($Bytes[$i] -ne $Needle[0]) { continue }
        $equal = $true
        for ($j = 1; $j -lt $Needle.Length; $j++) {
            if ($Bytes[$i+$j] -ne $Needle[$j]) { $equal = $false; break }
        }
        if ($equal) {
            if ($found -ge 0) { throw 'El ejecutable base tiene más de una marca privada.' }
            $found = $i
        }
    }
    if ($found -lt 0) { throw 'El ejecutable no es la base oficial sin credenciales, o ya está configurado.' }
    return $found
}
function Seal-PrivateExe([byte[]]$Exe, [byte[]]$Plain) {
    # The public sentinel matches native consultorio_bootstrap.c.
    $markerHex = '196f31ad9f13316209ce9772d6a87adeee4b61b425180b796d21436b32513857e3eedaba6fb91b433c0ce635d52325d5914398df0e42965fb93a54205610bd9b'
    $marker = New-Object byte[] 64
    for ($i = 0; $i -lt 64; $i++) {
        $marker[$i] = [Convert]::ToByte($markerHex.Substring($i*2,2),16)
    }
    $index = Find-Marker $Exe $marker
    $key = Get-RandomBytes 64
    $nonce = Get-RandomBytes 16
    Add-Bytes $Exe $index $key
    $cipher = New-Object byte[] $Plain.Length
    $block = New-Object byte[] 52
    [Array]::Copy($key, 0, $block, 0, 32)
    [Array]::Copy($nonce, 0, $block, 32, 16)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        for ($pos = 0; $pos -lt $Plain.Length; $pos += 32) {
            $counter = [BitConverter]::GetBytes([uint32][math]::Floor($pos/32))
            [Array]::Copy($counter, 0, $block, 48, 4)
            $stream = $sha.ComputeHash($block)
            for ($j = 0; $j -lt 32 -and ($pos+$j) -lt $Plain.Length; $j++) {
                $cipher[$pos+$j] = $Plain[$pos+$j] -bxor $stream[$j]
            }
        }
    } finally { $sha.Dispose() }
    $version = [BitConverter]::GetBytes([uint32]2)
    $length = [BitConverter]::GetBytes([uint32]$cipher.Length)
    $macInput = New-Object byte[] (24 + $cipher.Length)
    Add-Bytes $macInput 0 $version
    Add-Bytes $macInput 4 $length
    Add-Bytes $macInput 8 $nonce
    Add-Bytes $macInput 24 $cipher
    $macKey = New-Object byte[] 32
    [Array]::Copy($key, 32, $macKey, 0, 32)
    $hmac = New-Object Security.Cryptography.HMACSHA256 (,$macKey)
    try { $tag = $hmac.ComputeHash($macInput) } finally { $hmac.Dispose() }
    $footer = New-Object byte[] 72
    Add-Bytes $footer 0 ([Text.Encoding]::ASCII.GetBytes('DRRV2CFGFOOTER!!'))
    Add-Bytes $footer 16 $version
    Add-Bytes $footer 20 $length
    Add-Bytes $footer 24 $nonce
    Add-Bytes $footer 40 $tag
    $sealed = New-Object byte[] ($Exe.Length + $cipher.Length + $footer.Length)
    Add-Bytes $sealed 0 $Exe
    Add-Bytes $sealed $Exe.Length $cipher
    Add-Bytes $sealed ($Exe.Length + $cipher.Length) $footer
    [Array]::Clear($key, 0, $key.Length)
    [Array]::Clear($macKey, 0, $macKey.Length)
    [Array]::Clear($Plain, 0, $Plain.Length)
    return ,$sealed
}

$receptionPath = 'C:\Recepcion Dr Revelo\.env'
$historiaPath = 'C:\Historia Clinica Dr Revelo\.env'
if (-not (Test-Path -LiteralPath $BaseExe -PathType Leaf)) { throw 'No se encontró el EXE base.' }
if ([IO.Path]::GetFullPath($BaseExe) -eq [IO.Path]::GetFullPath($OutputExe)) { throw 'La salida no puede reemplazar la base.' }
$rec = Read-PrivateEnv $receptionPath
$hist = Read-PrivateEnv $historiaPath
$required = @('DATABASE_URL','AZUR_BASE_URL','AZUR_API_KEY','MOBILE_DOCTOR_TOKEN','MOBILE_RECEPTION_TOKEN')
$missing = @($required | Where-Object { -not $rec.ContainsKey($_) -or [string]::IsNullOrWhiteSpace([string]$rec[$_]) })
if ($missing.Count -gt 0) { throw ('Faltan claves en Recepción: ' + ($missing -join ', ')) }
if ($hist.ContainsKey('HISTORIA_DATABASE_URL') -and $rec.ContainsKey('HISTORIA_DATABASE_URL') -and
    [string]$hist['HISTORIA_DATABASE_URL'] -ne [string]$rec['HISTORIA_DATABASE_URL']) {
    throw 'Las conexiones a Historia no coinciden entre las dos computadoras.'
}
$histUrl = if ($hist.ContainsKey('HISTORIA_DATABASE_URL')) {
    [string]$hist['HISTORIA_DATABASE_URL']
} else { [string]$rec['HISTORIA_DATABASE_URL'] }
if (-not $histUrl -or [string]$rec['DATABASE_URL'] -eq $histUrl) {
    throw 'Se necesitan dos bases Neon independientes.'
}
$deviceKeys = @('RP_DATA_DIR','RP_WORKSTATION_NAME','RP_PORT','RP_FORCE_OFFLINE',
                'RP_DESKTOP_LAUNCH','COMPUTERNAME','USERPROFILE','LOCALAPPDATA',
                'AGENDA_CLOUD_KEYS_SYNCED_SHA')
foreach ($k in $deviceKeys) {
    if ($rec.ContainsKey($k)) { [void]$rec.Remove($k) }
    if ($hist.ContainsKey($k)) { [void]$hist.Remove($k) }
}
$rec['HISTORIA_DATABASE_URL'] = $histUrl
$rec['WHATSAPP_CLOUD_MODE'] = '1'
$rec['WHATSAPP_ENABLED'] = '0'
$hist['HISTORIA_DATABASE_URL'] = $histUrl
if (-not $hist.ContainsKey('HISTORIA_SYNC_ENABLED')) { $hist['HISTORIA_SYNC_ENABLED'] = '1' }

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('DR_REVELO_CONFIG_V2')
$lines.Add('[RECEPTION]')
foreach ($k in ($rec.Keys | Sort-Object)) { $lines.Add(('{0}={1}' -f $k,$rec[$k])) }
$lines.Add('[HISTORIA]')
foreach ($k in ($hist.Keys | Sort-Object)) { $lines.Add(('{0}={1}' -f $k,$hist[$k])) }
$plain = [Text.Encoding]::UTF8.GetBytes(($lines.ToArray() -join [char]10) + [char]10)
if ($plain.Length -gt 65536) { throw 'La configuración privada es demasiado grande.' }
$exe = [IO.File]::ReadAllBytes($BaseExe)
$sealed = Seal-PrivateExe $exe $plain
$dir = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($OutputExe))
[IO.Directory]::CreateDirectory($dir) | Out-Null
[IO.File]::WriteAllBytes($OutputExe,$sealed)
Write-Host 'INSTALADOR_PRIVADO_CREADO'

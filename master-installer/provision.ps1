[CmdletBinding()]
param(
    [switch]$Reception,
    [switch]$Historia,
    [Parameter(Mandatory = $true)]
    [string]$ActivationFile,
    [Parameter(Mandatory = $true)]
    [string]$BundlePath,
    [string]$ReceptionRoot = 'C:\Recepcion Dr Revelo',
    [string]$HistoriaRoot = 'C:\Historia Clinica Dr Revelo',
    [switch]$SkipConnectivityTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RuntimeRoot = Join-Path $env:ProgramData 'DrReveloRuntime'
$LogDir = Join-Path $RuntimeRoot 'logs'
$SecureDir = Join-Path $RuntimeRoot 'secure'
New-Item -ItemType Directory -Force -Path $LogDir, $SecureDir | Out-Null
$LogPath = Join-Path $LogDir ('provision-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')

function Write-Log([string]$Message) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}

function Get-Sha256Hex([string]$Text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        $hash = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hash)).Replace('-', '').ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Test-FixedTimeEqual([byte[]]$A, [byte[]]$B) {
    if ($null -eq $A -or $null -eq $B -or $A.Length -ne $B.Length) { return $false }
    $diff = 0
    for ($i = 0; $i -lt $A.Length; $i++) {
        $diff = $diff -bor ($A[$i] -bxor $B[$i])
    }
    return ($diff -eq 0)
}

function Join-Bytes([byte[][]]$Parts) {
    $length = 0
    foreach ($part in $Parts) { $length += $part.Length }
    $out = New-Object byte[] $length
    $offset = 0
    foreach ($part in $Parts) {
        [Array]::Copy($part, 0, $out, $offset, $part.Length)
        $offset += $part.Length
    }
    return $out
}

function Unprotect-Bundle([string]$Code, [string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { throw 'No se encontró el paquete privado de configuración.' }
    $bundle = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$bundle.format -ne 'dr-revelo-config-v1') { throw 'Formato de configuración privada no compatible.' }
    if ([string]$bundle.kdf -ne 'PBKDF2-HMAC-SHA1') { throw 'Método de protección no compatible.' }

    $expectedHash = [string]$bundle.activation_sha256
    if ((Get-Sha256Hex $Code) -ne $expectedHash) { throw 'Código de activación incorrecto.' }

    $salt = [Convert]::FromBase64String([string]$bundle.salt_b64)
    $iv = [Convert]::FromBase64String([string]$bundle.iv_b64)
    $cipherText = [Convert]::FromBase64String([string]$bundle.ciphertext_b64)
    $expectedMac = [Convert]::FromBase64String([string]$bundle.hmac_sha256_b64)
    $iterations = [int]$bundle.iterations

    $kdf = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($Code, $salt, $iterations)
    try { $keyMaterial = $kdf.GetBytes(64) } finally { $kdf.Dispose() }
    $encKey = New-Object byte[] 32
    $macKey = New-Object byte[] 32
    [Array]::Copy($keyMaterial, 0, $encKey, 0, 32)
    [Array]::Copy($keyMaterial, 32, $macKey, 0, 32)

    $macInput = Join-Bytes @($salt, $iv, $cipherText)
    $hmac = New-Object System.Security.Cryptography.HMACSHA256($macKey)
    try { $actualMac = $hmac.ComputeHash($macInput) } finally { $hmac.Dispose() }
    if (-not (Test-FixedTimeEqual $actualMac $expectedMac)) {
        throw 'El paquete privado no superó la verificación de integridad.'
    }

    $aes = [System.Security.Cryptography.Aes]::Create()
    try {
        $aes.KeySize = 256
        $aes.BlockSize = 128
        $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
        $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
        $aes.Key = $encKey
        $aes.IV = $iv
        $decryptor = $aes.CreateDecryptor()
        try { $plain = $decryptor.TransformFinalBlock($cipherText, 0, $cipherText.Length) }
        finally { $decryptor.Dispose() }
    }
    finally { $aes.Dispose() }

    $json = [System.Text.Encoding]::UTF8.GetString($plain)
    return ($json | ConvertFrom-Json)
}

function Protect-FileAcl([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    try {
        $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        & icacls.exe $Path '/inheritance:r' '/grant:r' ("*$sid" + ':(F)') '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "icacls devolvió $LASTEXITCODE" }
    }
    catch {
        Write-Log ('ADVERTENCIA ACL: ' + $_.Exception.Message)
        throw 'No se pudo proteger la configuración privada con permisos de Windows.'
    }
}

function Save-DpapiBackup([byte[]]$PlainBytes) {
    Add-Type -AssemblyName System.Security
    $scope = [System.Security.Cryptography.DataProtectionScope]::LocalMachine
    $protected = [System.Security.Cryptography.ProtectedData]::Protect($PlainBytes, $null, $scope)
    $path = Join-Path $SecureDir 'consultorio-config.dpapi'
    [System.IO.File]::WriteAllBytes($path, $protected)
    Protect-FileAcl $path
    return $path
}

function Convert-ObjectToHashtable($Object) {
    $hash = @{}
    if ($null -eq $Object) { return $hash }
    foreach ($p in $Object.PSObject.Properties) {
        $hash[[string]$p.Name] = [string]$p.Value
    }
    return $hash
}

function Set-EnvValues([string]$Path, [hashtable]$Values) {
    $dir = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $dir | Out-Null

    foreach ($k in @($Values.Keys)) {
        $v = [string]$Values[$k]
        if ($v.Contains("`r") -or $v.Contains("`n")) { throw "Valor inválido para $k." }
    }

    $lines = @()
    if (Test-Path -LiteralPath $Path) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        Copy-Item -LiteralPath $Path -Destination ($Path + '.before-auto-config-' + $stamp) -Force
        $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
    }

    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $out = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in $lines) {
        $m = [regex]::Match([string]$line, '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=')
        if ($m.Success -and $Values.ContainsKey($m.Groups[1].Value)) {
            $key = $m.Groups[1].Value
            if ($seen.Add($key)) { $out.Add($key + '=' + [string]$Values[$key]) }
        }
        else {
            $out.Add([string]$line)
        }
    }
    foreach ($key in $Values.Keys) {
        if ($seen.Add([string]$key)) { $out.Add(([string]$key) + '=' + [string]$Values[$key]) }
    }

    $tmp = $Path + '.new-' + [Guid]::NewGuid().ToString('N')
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($tmp, $out, $utf8NoBom)
    Move-Item -LiteralPath $tmp -Destination $Path -Force
    Protect-FileAcl $Path
}

function Test-PgConnection(
    [string]$Python,
    [string]$Url,
    [string]$ExpectedEndpoint,
    [string]$ExpectedRole,
    [string]$Label
) {
    if ($SkipConnectivityTest) {
        Write-Log "${Label}: prueba de red omitida por modo de validación."
        return
    }
    if (-not (Test-Path -LiteralPath $Python)) { throw "No existe Python para validar $Label." }

    $old = $env:DR_REVELO_TEST_DATABASE_URL
    $env:DR_REVELO_TEST_DATABASE_URL = $Url
    try {
        $code = @'
import os, ssl, urllib.parse, sys
from pg8000 import dbapi
u = urllib.parse.urlsplit(os.environ["DR_REVELO_TEST_DATABASE_URL"])
host = u.hostname or ""
expected_endpoint = os.environ["DR_REVELO_EXPECTED_ENDPOINT"]
expected_role = os.environ["DR_REVELO_EXPECTED_ROLE"]
if not host.startswith(expected_endpoint):
    raise SystemExit("endpoint incorrecto")
c = dbapi.connect(
    user=urllib.parse.unquote(u.username or ""),
    password=urllib.parse.unquote(u.password or ""),
    host=host,
    port=int(u.port or 5432),
    database=urllib.parse.unquote((u.path or "/neondb").lstrip("/")) or "neondb",
    ssl_context=ssl.create_default_context(),
    timeout=12,
)
try:
    cur = c.cursor()
    cur.execute("select current_database(), current_user")
    db, role = cur.fetchone()
    if expected_role and str(role) != expected_role:
        raise SystemExit("rol incorrecto")
    print("OK")
finally:
    c.close()
'@
        $env:DR_REVELO_EXPECTED_ENDPOINT = $ExpectedEndpoint
        $env:DR_REVELO_EXPECTED_ROLE = $ExpectedRole
        $output = & $Python -c $code 2>&1
        if ($LASTEXITCODE -ne 0 -or (($output | Out-String).Trim() -ne 'OK')) {
            throw "No se pudo validar $Label."
        }
        Write-Log "${Label}: conexión verificada."
    }
    finally {
        if ($null -eq $old) { Remove-Item Env:\DR_REVELO_TEST_DATABASE_URL -ErrorAction SilentlyContinue }
        else { $env:DR_REVELO_TEST_DATABASE_URL = $old }
        Remove-Item Env:\DR_REVELO_EXPECTED_ENDPOINT -ErrorAction SilentlyContinue
        Remove-Item Env:\DR_REVELO_EXPECTED_ROLE -ErrorAction SilentlyContinue
    }
}

if (-not $Reception -and -not $Historia) { throw 'Selecciona Recepción, Historia Clínica o ambos.' }

$activation = ''
try {
    if (-not (Test-Path -LiteralPath $ActivationFile)) { throw 'No se recibió el código de activación.' }
    $activation = (Get-Content -LiteralPath $ActivationFile -Raw -Encoding UTF8).Trim()
}
finally {
    Remove-Item -LiteralPath $ActivationFile -Force -ErrorAction SilentlyContinue
}
if ([string]::IsNullOrWhiteSpace($activation)) { throw 'El código de activación está vacío.' }

Write-Log 'Iniciando aprovisionamiento privado.'
$config = Unprotect-Bundle -Code $activation -Path $BundlePath
$activation = $null

$configJson = $config | ConvertTo-Json -Depth 8 -Compress
$dpapiPath = Save-DpapiBackup ([System.Text.Encoding]::UTF8.GetBytes($configJson))
$configJson = $null
Write-Log ('Copia DPAPI protegida: ' + $dpapiPath)

$status = [ordered]@{
    configured_at = (Get-Date).ToString('o')
    reception = $false
    reception_neon = 'not_selected'
    historia_bridge = 'not_selected'
    historia = $false
    historia_neon = 'not_selected'
}

if ($Reception) {
    $recValues = Convert-ObjectToHashtable $config.reception
    foreach ($required in @('DATABASE_URL','AZUR_BASE_URL','AZUR_API_KEY','MOBILE_DOCTOR_TOKEN','MOBILE_RECEPTION_TOKEN','HISTORIA_DATABASE_URL')) {
        if (-not $recValues.ContainsKey($required) -or [string]::IsNullOrWhiteSpace([string]$recValues[$required])) {
            throw "El paquete privado no contiene $required para Recepción."
        }
    }
    $recEnv = Join-Path $ReceptionRoot '.env'
    Set-EnvValues -Path $recEnv -Values $recValues

    $recPython = Join-Path $ReceptionRoot '.venv\Scripts\python.exe'
    Test-PgConnection -Python $recPython -Url $recValues['DATABASE_URL'] `
        -ExpectedEndpoint 'ep-shiny-scene-a66ta52d-pooler' -ExpectedRole 'neondb_owner' -Label 'Neon de Recepción'
    $status.reception_neon = 'ok'

    Test-PgConnection -Python $recPython -Url $recValues['HISTORIA_DATABASE_URL'] `
        -ExpectedEndpoint 'ep-sweet-mud-arlsk7qa-pooler' -ExpectedRole 'reception_bridge' -Label 'Puente Recepción → Historia'
    $status.historia_bridge = 'ok'
    $status.reception = $true
    Write-Log 'Recepción quedó configurada.'
}

if ($Historia) {
    $histValues = Convert-ObjectToHashtable $config.historia
    foreach ($required in @('HISTORIA_DATABASE_URL','HISTORIA_SYNC_ENABLED')) {
        if (-not $histValues.ContainsKey($required) -or [string]::IsNullOrWhiteSpace([string]$histValues[$required])) {
            throw "El paquete privado no contiene $required para Historia Clínica."
        }
    }
    $histEnv = Join-Path $HistoriaRoot '.env'
    Set-EnvValues -Path $histEnv -Values $histValues

    $histPython = Join-Path $HistoriaRoot '.venv\Scripts\python.exe'
    Test-PgConnection -Python $histPython -Url $histValues['HISTORIA_DATABASE_URL'] `
        -ExpectedEndpoint 'ep-sweet-mud-arlsk7qa-pooler' -ExpectedRole 'historia_app' -Label 'Neon de Historia Clínica'
    $status.historia_neon = 'ok'
    $status.historia = $true
    Write-Log 'Historia Clínica quedó configurada.'
}

$statusPath = Join-Path $RuntimeRoot 'installer-config-status.json'
$status | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statusPath -Encoding UTF8
Write-Log 'Aprovisionamiento finalizado correctamente.'
Write-Output 'DR_REVELO_PROVISION_OK'

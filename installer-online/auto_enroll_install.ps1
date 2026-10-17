# Automatic credential-free enrollment, Windows 10+ with Windows PowerShell 5.1.
param([Parameter(Mandatory=$true)][string]$BootstrapScript,
      [string]$ServiceUrl = 'https://dr-revelo-enrollment.drrevelo.workers.dev')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if ($ServiceUrl -notmatch '^https://[a-z0-9.-]+$') { throw 'La activación requiere HTTPS.' }
if (-not (Test-Path -LiteralPath $BootstrapScript -PathType Leaf)) { throw 'Falta el instalador interno.' }

function Base64Url([byte[]]$Bytes) {
    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}
function ConstantTimeEquals([byte[]]$A,[byte[]]$B) {
    $d = $A.Length -bxor $B.Length
    for ($i=0; $i -lt [Math]::Max($A.Length,$B.Length); $i++) {
        $x = if ($i -lt $A.Length) { $A[$i] } else { 0 }
        $y = if ($i -lt $B.Length) { $B[$i] } else { 0 }
        $d = $d -bor ($x -bxor $y)
    }
    return $d -eq 0
}
function Invoke-JsonPost([string]$Path,[object]$Payload) {
    $body = ConvertTo-Json -InputObject $Payload -Depth 6 -Compress
    return Invoke-RestMethod -Method Post -Uri ($ServiceUrl + $Path) -Body $body -ContentType 'application/json; charset=utf-8' -TimeoutSec 20 -ErrorAction Stop
}
function Unwrap-Payload([object]$Message,[System.Security.Cryptography.RSA]$Rsa,[string]$Ticket) {
    if ([string]$Message.status -ne 'approved' -or [string]$Message.format -ne 'DRRV2-RSAOAEP256-AESCBC-HMAC256' -or [string]$Message.ticket -ne $Ticket) {
        throw 'La activación devolvió una respuesta inesperada.'
    }
    $material = $Rsa.Decrypt([Convert]::FromBase64String([string]$Message.wrapped_key),[System.Security.Cryptography.RSAEncryptionPadding]::OaepSHA256)
    if ($material.Length -ne 64) { throw 'Material criptográfico inválido.' }
    $encKey = New-Object byte[] 32
    $macKey = New-Object byte[] 32
    [Array]::Copy($material,0,$encKey,0,32)
    [Array]::Copy($material,32,$macKey,0,32)
    try {
        $signed = [Text.Encoding]::UTF8.GetBytes(([string]$Message.ticket)+'|'+([string]$Message.wrapped_key)+'|'+([string]$Message.iv)+'|'+([string]$Message.ciphertext))
        $hmac = New-Object System.Security.Cryptography.HMACSHA256 (,$macKey)
        try { $tag = $hmac.ComputeHash($signed) } finally { $hmac.Dispose() }
        if (-not (ConstantTimeEquals $tag ([Convert]::FromBase64String([string]$Message.mac)))) { throw 'La configuración recibida no pasó la validación de integridad.' }
        $iv = [Convert]::FromBase64String([string]$Message.iv)
        if ($iv.Length -ne 16) { throw 'IV inválido.' }
        $ciphertext = [Convert]::FromBase64String([string]$Message.ciphertext)
        $aes = [Security.Cryptography.Aes]::Create()
        $aes.Mode = [Security.Cryptography.CipherMode]::CBC
        $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
        $aes.KeySize = 256
        $aes.Key = $encKey
        $aes.IV = $iv
        try {
            $decryptor = $aes.CreateDecryptor()
            try { $bytes = $decryptor.TransformFinalBlock($ciphertext,0,$ciphertext.Length) }
            finally { $decryptor.Dispose() }
        } finally { $aes.Dispose() }
        $text = [Text.Encoding]::UTF8.GetString($bytes)
        if (-not $text.StartsWith("DR_REVELO_CONFIG_V2"+[char]10) -or $text.Length -gt 65000) {
            throw 'La configuración no corresponde al consultorio.'
        }
        return [Convert]::ToBase64String($bytes)
    } finally {
        [Array]::Clear($material,0,$material.Length)
        [Array]::Clear($encKey,0,$encKey.Length)
        [Array]::Clear($macKey,0,$macKey.Length)
    }
}

# RSA-OAEP SHA256, unique in-memory private key per attempted installation.
$rsa = New-Object System.Security.Cryptography.RSACng -ArgumentList @(2048)
try {
    $pub = $rsa.ExportParameters($false)
    $pc = ([string]$env:COMPUTERNAME).Trim()
    if (-not $pc) { $pc = 'PC-NUEVA' }
    $enroll = Invoke-JsonPost '/enroll' @{ pc=$pc; public_key=@{ n=(Base64Url $pub.Modulus); e=(Base64Url $pub.Exponent) } }
    $ticket = [string]$enroll.ticket
    $token = [string]$enroll.token
    $code = [string]$enroll.code
    if ($ticket -notmatch '^[a-f0-9]{16}$' -or $code -notmatch '^\d{6}$' -or $token.Length -lt 40) {
        throw 'La autorización no devolvió una solicitud válida.'
    }
    $approveUrl = $ServiceUrl + '/approve?ticket=' + $ticket
    Add-Type -AssemblyName System.Windows.Forms
    $instructions = "Computadora: $pc" + [char]10 + [char]10 +
      "Para instalar Recepción e Historia Clínica, autoriza esta PC desde tu dispositivo de confianza:" + [char]10 + [char]10 +
      $approveUrl + [char]10 + [char]10 +
      "Código de aprobación: $code" + [char]10 + [char]10 +
      "La contraseña administrativa solo se escribe en la página segura." + [char]10 +
      "No se te pedirán las claves de Neon ni AZUR."
    $owner = New-Object System.Windows.Forms.Form
    $owner.TopMost = $true
    $owner.ShowInTaskbar = $false
    try {
        [void][System.Windows.Forms.MessageBox]::Show($owner,$instructions,'Autorizar nueva PC - Consultorio Dr. Revelo',
            [System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Information)
    } finally { $owner.Dispose() }
    $approved = $null
    for ($i=0; $i -lt 180; $i++) {
        $res = Invoke-JsonPost '/poll' @{ ticket=$ticket; token=$token }
        if ([string]$res.status -eq 'approved') { $approved = $res; break }
        if ([string]$res.status -ne 'pending') { throw 'La autorización ya no está disponible.' }
        Start-Sleep -Seconds 5
    }
    if ($null -eq $approved) { throw 'La solicitud venció sin autorización. No se instaló nada.' }
    # Config remains in memory until bootstrap writes each app's protected .env.
    $cfgB64 = Unwrap-Payload $approved $rsa $ticket
    [Environment]::SetEnvironmentVariable('DR_REVELO_PRIVATE_CONFIG_B64',$cfgB64,'Process')
    try {
        & $BootstrapScript -Reception -Historia
        if ($LASTEXITCODE -ne 0) { throw "La instalación devolvió código $LASTEXITCODE." }
    } finally {
        [Environment]::SetEnvironmentVariable('DR_REVELO_PRIVATE_CONFIG_B64',$null,'Process')
        $cfgB64 = $null
    }
} finally { $rsa.Dispose() }

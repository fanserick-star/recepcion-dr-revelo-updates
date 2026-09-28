$ErrorActionPreference = 'Stop'

$root = Join-Path $env:RUNNER_TEMP 'dr-revelo-provision-test'
$recRoot = Join-Path $root 'recepcion'
$histRoot = Join-Path $root 'historia'
New-Item -ItemType Directory -Force $recRoot, $histRoot | Out-Null
'KEEP_ME=recepcion' | Set-Content (Join-Path $recRoot '.env') -Encoding ascii
'KEEP_ME=historia' | Set-Content (Join-Path $histRoot '.env') -Encoding ascii

$activation = 'TESTA-CTIVA-CION9-87654-ABCDE'
$config = [ordered]@{
  version = 1
  reception = [ordered]@{
    DATABASE_URL='test-reception-db'
    AZUR_BASE_URL='test-azur-url'
    AZUR_API_KEY='test-azur-key'
    MOBILE_DOCTOR_TOKEN='test-doctor-token'
    MOBILE_RECEPTION_TOKEN='test-reception-token'
    AGENDA_CLOUD_KEYS_SYNCED_SHA='test-sha'
    HISTORIA_DATABASE_URL='test-bridge-db'
  }
  historia = [ordered]@{
    HISTORIA_DATABASE_URL='test-historia-db'
    HISTORIA_SYNC_ENABLED='1'
  }
}

$plain = [Text.Encoding]::UTF8.GetBytes(($config | ConvertTo-Json -Depth 8 -Compress))
$salt = New-Object byte[] 16
$iv = New-Object byte[] 16
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($salt); $rng.GetBytes($iv); $rng.Dispose()
$iter = 200000
$kdf = New-Object Security.Cryptography.Rfc2898DeriveBytes($activation, $salt, $iter)
$km = $kdf.GetBytes(64); $kdf.Dispose()
$encKey = New-Object byte[] 32
$macKey = New-Object byte[] 32
[Array]::Copy($km, 0, $encKey, 0, 32)
[Array]::Copy($km, 32, $macKey, 0, 32)

$aes = [Security.Cryptography.Aes]::Create()
$aes.KeySize = 256; $aes.BlockSize = 128
$aes.Mode = [Security.Cryptography.CipherMode]::CBC
$aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
$aes.Key = $encKey; $aes.IV = $iv
$encryptor = $aes.CreateEncryptor()
$ct = $encryptor.TransformFinalBlock($plain, 0, $plain.Length)
$encryptor.Dispose(); $aes.Dispose()

$macInput = New-Object byte[] ($salt.Length + $iv.Length + $ct.Length)
[Array]::Copy($salt, 0, $macInput, 0, $salt.Length)
[Array]::Copy($iv, 0, $macInput, $salt.Length, $iv.Length)
[Array]::Copy($ct, 0, $macInput, $salt.Length + $iv.Length, $ct.Length)
$h = New-Object Security.Cryptography.HMACSHA256($macKey)
$mac = $h.ComputeHash($macInput); $h.Dispose()
$sha = [Security.Cryptography.SHA256]::Create()
$activationHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($activation)))).Replace('-', '').ToLowerInvariant()
$sha.Dispose()

$bundle = [ordered]@{
  format='dr-revelo-config-v1'
  kdf='PBKDF2-HMAC-SHA1'
  iterations=$iter
  salt_b64=[Convert]::ToBase64String($salt)
  iv_b64=[Convert]::ToBase64String($iv)
  ciphertext_b64=[Convert]::ToBase64String($ct)
  hmac_sha256_b64=[Convert]::ToBase64String($mac)
  activation_sha256=$activationHash
}
$bundlePath = Join-Path $root 'test.bundle.json'
$activationPath = Join-Path $root 'activation.txt'
$bundle | ConvertTo-Json | Set-Content $bundlePath -Encoding UTF8
[IO.File]::WriteAllText($activationPath, $activation, (New-Object Text.UTF8Encoding($false)))

& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File 'master-installer/provision.ps1' -Reception -Historia -ActivationFile $activationPath -BundlePath $bundlePath -ReceptionRoot $recRoot -HistoriaRoot $histRoot -SkipConnectivityTest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (Test-Path $activationPath) { throw 'El archivo temporal de activación no fue eliminado.' }

$rec = Get-Content (Join-Path $recRoot '.env') -Raw
$hist = Get-Content (Join-Path $histRoot '.env') -Raw
foreach ($x in @('KEEP_ME=recepcion','DATABASE_URL=test-reception-db','AZUR_API_KEY=test-azur-key','HISTORIA_DATABASE_URL=test-bridge-db')) {
  if (-not $rec.Contains($x)) { throw "Falta en Recepción: $x" }
}
foreach ($x in @('KEEP_ME=historia','HISTORIA_DATABASE_URL=test-historia-db','HISTORIA_SYNC_ENABLED=1')) {
  if (-not $hist.Contains($x)) { throw "Falta en Historia: $x" }
}

'PROVISION_SMOKE_TEST_OK'

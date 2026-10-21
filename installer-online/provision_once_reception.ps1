# One-time clinic configuration. This file contains NO private credentials.
# Read trusted .env files locally, upload ONLY to Cloudflare encrypted secrets over TLS.
# NEVER put secrets in GitHub, logs, support chats or command-line arguments.
param([string]$CloudflareAccountId = '',
      [string]$ReceptionEnv = 'C:\Recepcion Dr Revelo\.env',
      [string]$HistoriaEnv = 'C:\Historia Clinica Dr Revelo\.env',
      [switch]$ValidateOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$service='https://dr-revelo-enrollment.drrevelo.workers.dev'
function Select-PrivateFile([string]$Message) {
  Add-Type -AssemblyName System.Windows.Forms
  $dialog=New-Object System.Windows.Forms.OpenFileDialog
  $dialog.Title=$Message
  $dialog.Filter='Todos los archivos (*.*)|*.*|Archivos .env (*.env)|*.env'
  $dialog.CheckFileExists=$true
  $dialog.Multiselect=$false
  try {
    $answer=$dialog.ShowDialog()
    if($answer -ne [System.Windows.Forms.DialogResult]::OK){throw 'Seleccion de archivo cancelada.'}
    return $dialog.FileName
  }finally{$dialog.Dispose()}
}
if(-not(Test-Path -LiteralPath $ReceptionEnv -PathType Leaf)){
  $ReceptionEnv=Select-PrivateFile 'Selecciona el archivo .env ACTUAL de Recepcion'
}
if(-not(Test-Path -LiteralPath $HistoriaEnv -PathType Leaf)){
  $HistoriaEnv=Select-PrivateFile 'Selecciona el archivo .env ACTUAL de Historia Clinica'
}
if([IO.Path]::GetFullPath($ReceptionEnv) -eq [IO.Path]::GetFullPath($HistoriaEnv)){
  throw 'Recepcion e Historia necesitan dos archivos diferentes.'
}
function Read-PrivateEnv([string]$Path,[string]$Label){
  if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){
    throw ('No se encontró el .env de '+$Label+'. Se necesitan ambas configuraciones actuales.')
  }
  $data=@{}
  foreach($line in [IO.File]::ReadAllLines($Path)){
    $l=$line.Trim()
    if(-not $l -or $l.StartsWith('#') -or -not $l.Contains('=')){continue}
    $pair=$l.Split('=',2);$key=$pair[0].Trim()
    if($key -notmatch '^[A-Z][A-Z0-9_]*$'){continue}
    if($data.ContainsKey($key)){throw ('Clave duplicada en '+$Label+': '+$key)}
    if($pair[1].Trim()){$data[$key]=$pair[1].Trim()}
  }
  return $data
}
$raw=Read-PrivateEnv $ReceptionEnv 'Recepción'
$histRaw=Read-PrivateEnv $HistoriaEnv 'Historia Clínica'
$required=@('DATABASE_URL','HISTORIA_DATABASE_URL','AZUR_BASE_URL','AZUR_API_KEY','MOBILE_DOCTOR_TOKEN','MOBILE_RECEPTION_TOKEN')
$missing=@($required|Where-Object{-not $raw.ContainsKey($_)})
if($missing.Count -gt 0){throw ('Faltan claves: '+($missing -join ', '))}
if(-not $histRaw.ContainsKey('HISTORIA_DATABASE_URL') -or -not [string]$histRaw['HISTORIA_DATABASE_URL']){
  throw 'Historia Clínica no contiene su propia conexión Neon.'
}
if([string]$histRaw['HISTORIA_SYNC_ENABLED'] -ne '1'){
  throw 'Primero hay que verificar por qué la sincronización de Historia no está activada.'
}
foreach($url in @(
  [string]$raw['DATABASE_URL'],
  [string]$raw['HISTORIA_DATABASE_URL'],
  [string]$histRaw['HISTORIA_DATABASE_URL']
)){
  if($url -notmatch '^postgres(ql)?://'){throw 'Formato Neon incorrecto.'}
}
$recUri=[uri]([string]$raw['DATABASE_URL'])
$bridgeUri=[uri]([string]$raw['HISTORIA_DATABASE_URL'])
$histUri=[uri]([string]$histRaw['HISTORIA_DATABASE_URL'])
if($recUri.Host -eq $histUri.Host -or $bridgeUri.Host -ne $histUri.Host -or
   $bridgeUri.AbsolutePath -ne $histUri.AbsolutePath){
  throw 'Los endpoints de Recepción, el puente y la Historia no coinciden con la arquitectura autorizada.'
}
if(-not $histUri.Host.ToLowerInvariant().StartsWith('ep-sweet-mud-arlsk7qa') -or
   -not $histUri.Host.ToLowerInvariant().EndsWith('.neon.tech')){
  throw 'La conexión de Historia no apunta al proyecto clínico esperado.'
}
$bridgeRole=($bridgeUri.UserInfo -split ':',2)[0]
$clinicalRole=($histUri.UserInfo -split ':',2)[0]
if(-not $bridgeRole -or -not $clinicalRole -or $bridgeRole -eq $clinicalRole){
  throw 'Recepción y el doctor deben utilizar roles distintos en Historia Clínica.'
}
$rec=@{}
foreach($key in $raw.Keys){
  if($key -match '^(DATABASE_URL|HISTORIA_DATABASE_URL|AZUR_[A-Z0-9_]+|MOBILE_DOCTOR_TOKEN|MOBILE_RECEPTION_TOKEN|AGENDA_CLOUD_BASE_URL)$'){
    $rec[$key]=[string]$raw[$key]
  }
}
$rec['WHATSAPP_CLOUD_MODE']='1'
$rec['WHATSAPP_ENABLED']='0'
$hist=@{HISTORIA_DATABASE_URL=[string]$histRaw['HISTORIA_DATABASE_URL'];HISTORIA_SYNC_ENABLED='1'}
function Render-Env([hashtable]$Values){
  return (($Values.Keys|Sort-Object|ForEach-Object{$key=[string]$_; $key+'='+[string]$Values[$key]}) -join [char]10)+[char]10
}
if($ValidateOnly){
  Write-Host 'VALIDACION_LOCAL_OK: ambas configuraciones son compatibles por destino y permisos.'
  Write-Host 'No se enviaron secretos a Internet ni se modifico Cloudflare.'
  return
}
if(-not $CloudflareAccountId){
  $CloudflareAccountId=(Read-Host 'ID de tu cuenta Cloudflare (32 caracteres, NO es el token)').Trim()
}
if($CloudflareAccountId -notmatch '^[a-f0-9]{32}$'){
  throw 'ID de cuenta Cloudflare invalido. Copia Account ID desde Workers.'
}
try {
  $health=Invoke-RestMethod -Method Get -Uri ($service+'/health') -TimeoutSec 20
  if(-not $health.ok -or $health.service -ne 'consultorio-enrollment'){
    throw 'Servicio incorrecto'
  }
}catch{
  throw 'El servicio aislado del instalador no responde. No se envio ninguna clave.'
}
$recB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Render-Env $rec)))
$histB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Render-Env $hist)))
$secretDir=Join-Path $env:APPDATA 'DrReveloPrivateInstaller'
$adminFile=Join-Path $secretDir 'aprobacion.dpapi'
New-Item -ItemType Directory -Path $secretDir -Force|Out-Null
if(Test-Path -LiteralPath $adminFile -PathType Leaf){
  # DPAPI is bound to this Windows user. Get-Content -Raw retains the line
  # ending written by Set-Content; strip it before decrypting the same secret.
  # Never delete or silently regenerate the saved administrator password.
  try {
    $cipher=(Get-Content -LiteralPath $adminFile -Raw -ErrorAction Stop).Trim()
    if([string]::IsNullOrWhiteSpace($cipher) -or $cipher -notmatch '^[0-9a-fA-F]+$'){
      throw 'invalid_ciphertext'
    }
    $secure=ConvertTo-SecureString -String $cipher -ErrorAction Stop
    $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try{$admin=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)}
    finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}
  }catch{
    throw 'CLAVE_ADMINISTRATIVA_LOCAL_NO_RECUPERABLE: usa el mismo usuario de Windows y conserva aprobacion.dpapi. Cloudflare no se ha modificado.'
  }
}else{
  $rand=New-Object byte[] 32
  $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
  try{$rng.GetBytes($rand)}finally{$rng.Dispose()}
  $admin=[Convert]::ToBase64String($rand).TrimEnd('=').Replace('+','-').Replace('/','_')
  $secure=ConvertTo-SecureString $admin -AsPlainText -Force
  ($secure|ConvertFrom-SecureString)|Set-Content -LiteralPath $adminFile -Encoding ASCII
}
Write-Host 'Configuraciones de Recepción e Historia comprobadas por separado. No se imprimen los valores.'
$cfSecure=Read-Host 'Escribe SOLO el token administrativo de Cloudflare (se usa una vez)' -AsSecureString
$ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($cfSecure)
try{$cfToken=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)}
finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}
if(-not $cfToken){throw 'No se proporcionó acceso Cloudflare. No se enviaron claves.'}
$endpoint="https://api.cloudflare.com/client/v4/accounts/$CloudflareAccountId/workers/scripts/dr-revelo-enrollment/secrets-bulk"
$headers=@{Authorization=('Bearer '+$cfToken)}
# Cloudflare recommends one atomic PATCH for multiple secrets. JSON stays
# only in the PowerShell process and is never stored in a file.
$payload=@{secrets=@{
  RECEPTION_ENV_B64=@{name='RECEPTION_ENV_B64';type='secret_text';text=$recB64}
  HISTORIA_ENV_B64=@{name='HISTORIA_ENV_B64';type='secret_text';text=$histB64}
  DR_REVELO_ADMIN_TOKEN=@{name='DR_REVELO_ADMIN_TOKEN';type='secret_text';text=$admin}
}}
$body=ConvertTo-Json -InputObject $payload -Depth 8 -Compress
try {
  try {
    $result=Invoke-RestMethod -Method Patch -Uri $endpoint -Headers $headers -Body $body -ContentType 'application/json' -TimeoutSec 40
    if(-not $result.success){throw 'Cloudflare no acepto la configuracion.'}
  }catch{
    # Never print the raw exception or the API response body. Either may
    # unexpectedly include confidential request context.
    $status=0
    try {
      if($null -ne $_.Exception.Response -and $null -ne $_.Exception.Response.StatusCode){
        $status=[int]$_.Exception.Response.StatusCode
      }
    }catch{}
    $hint=switch($status){
      400 {'Solicitud rechazada: formato o validacion. No repitas el envio.'}
      401 {'Token no autorizado, vencido o incorrecto.'}
      403 {'Token sin permisos para modificar secretos de este Worker.'}
      404 {'Account ID o nombre del Worker no coinciden con el servicio autorizado.'}
      409 {'Cloudflare reporta un conflicto de versiones; no repitas el envio.'}
      429 {'Demasiados intentos; espera antes de reintentar.'}
      500 {'Error temporal del servidor de Cloudflare.'}
      502 {'Error temporal del servidor de Cloudflare.'}
      503 {'Servicio de Cloudflare temporalmente no disponible.'}
      default {'Sin respuesta HTTP verificable o error no clasificado.'}
    }
    throw ('ACTIVACION_CLOUDFLARE_HTTP_'+$status+'. '+$hint+' No se muestran secretos.')
  }
}finally{
  $body=$null;$payload=$null;$recB64=$null;$histB64=$null
  $headers.Clear();$cfToken=$null
  $cfSecure.Dispose()
}
Write-Host 'Los 3 secretos se registraron en el Worker aislado.'
# Verify the currently LIVE worker actually uses the secrets; do not assume
# an API update is deployed immediately.
$ready=$false
for($attempt=0;$attempt -lt 8;$attempt++){
  try {
    $h=Invoke-RestMethod -Method Get -Uri ($service+'/health') -TimeoutSec 15
    if($h.ok -and $h.service -eq 'consultorio-enrollment' -and $h.configured){
      $ready=$true;break
    }
  }catch{}
  Start-Sleep -Seconds 3
}
if(-not $ready){
  throw 'Secretos guardados, pero todavia no aparecen en el Worker activo. No instales aun.'
}
try{
  $headers2=@{ Authorization=('Bearer '+$admin) }
  $valid=Invoke-RestMethod -Method Post -Uri ($service+'/admin/validate') -Headers $headers2 -Body '{}' -ContentType 'application/json' -TimeoutSec 20
  if(-not $valid.ok -or -not $valid.ready){throw 'Configuracion rechazada'}
}catch{
  throw 'Cloudflare tiene los 3 secretos, pero falta confirmar su validacion. No ejecutes el instalador aun.'
}
Write-Host 'ACTIVACION_OK: Worker publico configurado y configuracion privada validada.'
Write-Host 'Guarda la siguiente contrasena ADMINISTRATIVA de aprobacion en tu gestor seguro.'
Write-Host ('CONTRASENA_ADMINISTRATIVA_DE_APROBACION: '+$admin)
Write-Host 'No compartir por chat, WhatsApp ni GitHub. Luego revoca el token temporal de Cloudflare.'

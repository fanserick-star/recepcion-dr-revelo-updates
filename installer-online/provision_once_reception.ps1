# ONE-TIME configuration from the EXISTING, TRUSTED Reception PC.
# Never upload this script's output to GitHub or send secrets by chat.
param([Parameter(Mandatory=$true)][string]$CloudflareAccountId,
      [string]$ReceptionEnv = 'C:\Recepcion Dr Revelo\.env')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
if($CloudflareAccountId -notmatch '^[a-f0-9]{32}$'){throw 'ID de cuenta Cloudflare inválido.'}
$service='https://dr-revelo-enrollment.drrevelo.workers.dev'
try {
  $health=Invoke-RestMethod -Uri ($service+'/health') -TimeoutSec 15
  if(-not $health.ok -or $health.service -ne 'consultorio-enrollment') {throw 'No es el servicio aislado del instalador.'}
}catch{throw 'Primero debe desplegarse el servicio privado de autorización. No se enviaron claves.'}
if(-not(Test-Path -LiteralPath $ReceptionEnv -PathType Leaf)){throw 'No se encontró el .env de Recepción.'}
$raw=@{}
foreach($line in [IO.File]::ReadAllLines($ReceptionEnv)){
  $l=$line.Trim()
  if(-not $l -or $l.StartsWith('#') -or -not $l.Contains('=')){continue}
  $pair=$l.Split('=',2);$key=$pair[0].Trim()
  if($key -notmatch '^[A-Z][A-Z0-9_]*$'){continue}
  if($raw.ContainsKey($key)){throw ('Clave duplicada en Recepción: '+$key)}
  if($pair[1].Trim()){$raw[$key]=$pair[1].Trim()}
}
$required=@('DATABASE_URL','HISTORIA_DATABASE_URL','AZUR_BASE_URL','AZUR_API_KEY','MOBILE_DOCTOR_TOKEN','MOBILE_RECEPTION_TOKEN')
$missing=@($required|Where-Object{-not $raw.ContainsKey($_)})
if($missing.Count -gt 0){throw ('Faltan claves: '+($missing -join ', '))}
if([string]$raw['DATABASE_URL'] -eq [string]$raw['HISTORIA_DATABASE_URL']){
  throw 'Las conexiones Neon de Recepción e Historia no son independientes.'
}
foreach($key in @('DATABASE_URL','HISTORIA_DATABASE_URL')){
  if([string]$raw[$key] -notmatch '^postgres(ql)?://'){throw ('Formato Neon incorrecto: '+$key)}
}
$histHost=([uri]([string]$raw['HISTORIA_DATABASE_URL'])).Host.ToLowerInvariant()
if(-not $histHost.StartsWith('ep-sweet-mud-arlsk7qa')){
  throw 'La URL de Historia no corresponde al endpoint esperado. Revisa antes de enviar claves.'
}
$rec=@{}
foreach($key in $raw.Keys){
  if($key -match '^(DATABASE_URL|HISTORIA_DATABASE_URL|AZUR_[A-Z0-9_]+|MOBILE_DOCTOR_TOKEN|MOBILE_RECEPTION_TOKEN|AGENDA_CLOUD_BASE_URL)$'){
    $rec[$key]=[string]$raw[$key]
  }
}
$rec['WHATSAPP_CLOUD_MODE']='1'
$rec['WHATSAPP_ENABLED']='0'
$hist=@{HISTORIA_DATABASE_URL=[string]$raw['HISTORIA_DATABASE_URL'];HISTORIA_SYNC_ENABLED='1'}
function Render-Env([hashtable]$Values){
  return (($Values.Keys|Sort-Object|ForEach-Object{[string]$_+'='+[string]$Values[$_]}) -join [char]10)+[char]10
}
$recB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Render-Env $rec)))
$histB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Render-Env $hist)))
$secretDir=Join-Path $env:APPDATA 'DrReveloPrivateInstaller'
$adminFile=Join-Path $secretDir 'aprobacion.dpapi'
New-Item -ItemType Directory -Path $secretDir -Force|Out-Null
if(Test-Path -LiteralPath $adminFile -PathType Leaf){
  $secure=Get-Content -LiteralPath $adminFile -Raw|ConvertTo-SecureString
  $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try{$admin=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)}
  finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}
}else{
  $rand=New-Object byte[] 32
  $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
  try{$rng.GetBytes($rand)}finally{$rng.Dispose()}
  $admin=[Convert]::ToBase64String($rand).TrimEnd('=').Replace('+','-').Replace('/','_')
  $secure=ConvertTo-SecureString $admin -AsPlainText -Force
  ($secure|ConvertFrom-SecureString)|Set-Content -LiteralPath $adminFile -Encoding ASCII
}
Write-Host 'Configuración original verificada por nombres. No se imprimen los valores.'
$cfSecure=Read-Host 'Escribe SOLO el token administrativo de Cloudflare (se usa una vez)' -AsSecureString
$ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($cfSecure)
try{$cfToken=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)}
finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}
if(-not $cfToken){throw 'No se proporcionó acceso Cloudflare. No se enviaron claves.'}
$endpoint="https://api.cloudflare.com/client/v4/accounts/$CloudflareAccountId/workers/scripts/dr-revelo-enrollment/secrets"
$headers=@{Authorization=('Bearer '+$cfToken)}
try{
  foreach($item in @(
    @{name='RECEPTION_ENV_B64';text=$recB64},
    @{name='HISTORIA_ENV_B64';text=$histB64},
    @{name='DR_REVELO_ADMIN_TOKEN';text=$admin}
  )){
    $body=ConvertTo-Json -InputObject @{type='secret_text';name=$item.name;text=$item.text} -Compress
    try{
      $result=Invoke-RestMethod -Method Put -Uri $endpoint -Headers $headers -Body $body -ContentType 'application/json' -TimeoutSec 35
      if(-not $result.success){throw 'El servidor rechazó el secreto.'}
    }catch{throw ('No se pudo registrar de forma segura: '+$item.name+'. No se imprimen valores.')}
    Write-Host ('Registrado en Cloudflare (secreto oculto): '+$item.name)
  }
}finally{$cfToken=$null;$cfSecure.Dispose()}
Write-Host 'Instalador centralizado configurado. Guardar esta contraseña en un gestor seguro.'
Write-Host ('CONTRASENA_ADMINISTRATIVA_DE_APROBACION: '+$admin)
Write-Host 'No enviarla por WhatsApp, GitHub ni por el chat.'

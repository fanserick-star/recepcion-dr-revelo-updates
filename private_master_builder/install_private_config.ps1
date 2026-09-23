param(
    [Parameter(Mandatory=$true)][string]$SourceEnv,
    [string]$ReceptionDir = 'C:\\Recepcion Dr Revelo',
    [string]$HistoriaDir = 'C:\\Historia Clinica Dr Revelo',
    [switch]$InstallReception,
    [switch]$InstallHistoria
)

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

function Read-EnvMap([string]$Path){
    $map=@{}
    foreach($line in [System.IO.File]::ReadAllLines($Path,[System.Text.Encoding]::UTF8)){
        $trim=$line.Trim()
        if(-not $trim -or $trim.StartsWith('#')){ continue }
        $i=$line.IndexOf('=')
        if($i -lt 1){ continue }
        $k=$line.Substring(0,$i).Trim()
        $v=$line.Substring($i+1)
        $map[$k]=$v
    }
    return $map
}

function Write-Utf8NoBom([string]$Path,[string[]]$Lines){
    [System.IO.File]::WriteAllLines($Path,$Lines,(New-Object System.Text.UTF8Encoding($false)))
}

function Normalize-ReceptionEnv([string]$Source,[string]$Destination){
    if(Test-Path -LiteralPath $Destination){ return }
    $lines=[System.Collections.Generic.List[string]]::new()
    $foundData=$false
    foreach($line in [System.IO.File]::ReadAllLines($Source,[System.Text.Encoding]::UTF8)){
        if($line -match '^\\s*RP_DATA_DIR\\s*='){
            $lines.Add('RP_DATA_DIR=data')
            $foundData=$true
        } else {
            $lines.Add($line)
        }
    }
    if(-not $foundData){ $lines.Add('RP_DATA_DIR=data') }
    Write-Utf8NoBom $Destination $lines.ToArray()
}

if(-not (Test-Path -LiteralPath $SourceEnv -PathType Leaf)){ throw 'Falta configuración privada temporal.' }
$map=Read-EnvMap $SourceEnv
$db=if($map.ContainsKey('DATABASE_URL')){[string]$map['DATABASE_URL']}else{''}
if([string]::IsNullOrWhiteSpace($db)){ throw 'La configuración privada no contiene DATABASE_URL.' }

if($InstallReception){
    New-Item -ItemType Directory -Force $ReceptionDir | Out-Null
    Normalize-ReceptionEnv $SourceEnv (Join-Path $ReceptionDir '.env')
}

if($InstallHistoria){
    New-Item -ItemType Directory -Force $HistoriaDir | Out-Null
    $dest=Join-Path $HistoriaDir '.env'
    if(-not (Test-Path -LiteralPath $dest)){
        Write-Utf8NoBom $dest @(
            'HISTORIA_DATABASE_URL='+$db,
            'HISTORIA_SYNC_ENABLED=1'
        )
    }
}

Write-Host 'CONFIG_PRIVADA_OK'

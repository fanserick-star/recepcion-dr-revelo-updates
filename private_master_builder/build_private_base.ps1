param(
    [string]$WorkRoot = (Join-Path $PSScriptRoot 'work')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$SourceCommit = '542b85d06fe20365a251246fffec99707d18f601'
$RawBase = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/$SourceCommit/"
$root = [System.IO.Path]::GetFullPath($WorkRoot)
$payload = Join-Path $root 'payload'
$recep = Join-Path $payload 'recepcion'
$hist = Join-Path $payload 'historia'
$build = Join-Path $root 'build'
$output = Join-Path $root 'output'

if(Test-Path $root){ Remove-Item $root -Recurse -Force }
foreach($p in @($root,$payload,$recep,$hist,$build,$output)){
    New-Item -ItemType Directory -Force $p | Out-Null
}

function Step([string]$s){
    Write-Host ''
    Write-Host ('='*72)
    Write-Host $s
    Write-Host ('='*72)
}

function Download([string]$url,[string]$dest){
    $parent=Split-Path -Parent $dest
    if($parent){ New-Item -ItemType Directory -Force $parent | Out-Null }
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dest
}

function DownloadPinned([string]$relative,[string]$dest){
    Download ($RawBase + $relative.Replace('\\','/')) $dest
}

function Assert-Sha([string]$path,[string]$expected){
    if([string]::IsNullOrWhiteSpace($expected)){ return }
    $got=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if($got -ne $expected.ToLowerInvariant()){ throw "SHA incorrecto: $path" }
}

function Download-ManifestFile($entry,[string]$dest){
    $parent=Split-Path -Parent $dest
    if($parent){ New-Item -ItemType Directory -Force $parent | Out-Null }
    $props=@($entry.PSObject.Properties.Name)
    $hasUrl=($props -contains 'url') -and (-not [string]::IsNullOrWhiteSpace([string]$entry.url))
    $hasParts=($props -contains 'parts') -and ($null -ne $entry.parts) -and (@($entry.parts).Count -gt 0)
    if($hasUrl){
        $u=[string]$entry.url
        $u=$u.Replace('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/',$RawBase)
        Download $u $dest
    } elseif($hasParts){
        $fs=[System.IO.File]::Open($dest,[System.IO.FileMode]::Create,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
        try{
            foreach($part in @($entry.parts)){
                $u=([string]$part).Replace('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/',$RawBase)
                $tmp=[System.IO.Path]::GetTempFileName()
                try{
                    Download $u $tmp
                    $bytes=[System.IO.File]::ReadAllBytes($tmp)
                    $fs.Write($bytes,0,$bytes.Length)
                } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
            }
        } finally { $fs.Dispose() }
    } else { throw "Entrada sin url/parts: $($entry.path)" }
    $sha=if($props -contains 'sha256'){[string]$entry.sha256}else{''}
    Assert-Sha $dest $sha
}

function Setup-EmbeddedPython([string]$appRoot,[string[]]$packages,[string]$label){
    Step "Python portátil: $label"
    $venv=Join-Path $appRoot '.venv'
    $scripts=Join-Path $venv 'Scripts'
    $lib=Join-Path $venv 'Lib'
    $site=Join-Path $lib 'site-packages'
    New-Item -ItemType Directory -Force $scripts,$site | Out-Null

    $embed=Join-Path $env:RUNNER_TEMP ("python-embed-"+[guid]::NewGuid().ToString('N')+".zip")
    Download 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' $embed
    Expand-Archive -LiteralPath $embed -DestinationPath $scripts -Force

@'
python311.zip
.
..\\..
..\\Lib
..\\Lib\\site-packages
import site
'@ | Set-Content (Join-Path $scripts 'python311._pth') -Encoding ascii

@'
home = Scripts
include-system-site-packages = false
version = 3.11.9
'@ | Set-Content (Join-Path $venv 'pyvenv.cfg') -Encoding ascii

    $runnerPy=(Get-Command python).Source
    & $runnerPy -m pip install --disable-pip-version-check --no-compile --upgrade --target $site @packages
    if($LASTEXITCODE -ne 0){ throw "pip falló para $label" }

    $runnerRoot=Split-Path -Parent (Split-Path -Parent $runnerPy)
    if(Test-Path (Join-Path $runnerRoot 'Lib\\tkinter')){
        Copy-Item (Join-Path $runnerRoot 'Lib\\tkinter') (Join-Path $lib 'tkinter') -Recurse -Force
    }
    foreach($f in @('_tkinter.pyd','tcl86t.dll','tk86t.dll')){
        $src=Join-Path $runnerRoot ('DLLs\\'+$f)
        if(Test-Path $src){ Copy-Item $src $scripts -Force }
    }
    if(Test-Path (Join-Path $runnerRoot 'tcl')){
        Copy-Item (Join-Path $runnerRoot 'tcl') (Join-Path $scripts 'tcl') -Recurse -Force
    }

    $py=Join-Path $scripts 'python.exe'
    & $py -c "import fastapi,uvicorn,pg8000,webview; import webview.platforms.edgechromium; print('RUNTIME_OK')"
    if($LASTEXITCODE -ne 0){ throw "Runtime portátil inválido: $label" }
}

Step '1/8 Reconstruyendo Recepción publicada 4.5.25'
$repoRoot=Split-Path $PSScriptRoot -Parent
$baseLocal=Join-Path $root 'clean_base_resources.zip'
Copy-Item (Join-Path $repoRoot 'installer_clean\\base\\clean_base_resources.zip') $baseLocal -Force
$tempBase=Join-Path $root 'base_extract'
Expand-Archive -LiteralPath $baseLocal -DestinationPath $tempBase -Force
Copy-Item (Join-Path $tempBase 'static') (Join-Path $recep 'static') -Recurse -Force
Copy-Item (Join-Path $tempBase 'mobile') (Join-Path $recep 'mobile') -Recurse -Force
foreach($name in @('azur_client.py','whatsapp_client.py','remote_agenda.py')){
    Copy-Item (Join-Path $tempBase $name) (Join-Path $recep $name) -Force
}
New-Item -ItemType Directory -Force (Join-Path $recep 'data') | Out-Null

$files=[ordered]@{
'app.py'='updates/v4_5_25_bendo_click_hotfix/app.py'
'app_patch_4525.py'='updates/v4_5_25_bendo_click_hotfix/app_patch_4525.py'
'app_patch_4524.py'='updates/v4_5_24_historia_demographics/app_patch_4524.py'
'app_patch_4505.py'='updates/v4_5_24_historia_demographics/app_patch_4505.py'
'app_patch_4507.py'='updates/v4_5_24_historia_demographics/app_patch_4507.py'
'app_patch_4523.py'='updates/v4_5_24_historia_demographics/app_patch_4523.py'
'app_patch_4522.py'='updates/v4_5_22_historia_delete_sync/app_patch_4522.py'
'app_patch_4521.py'='updates/v4_5_21_historia_attention_type/app_patch_4521.py'
'app_patch_4520.py'='updates/v4_5_20_historia_lan_hybrid/app_patch_4520.py'
'historia_lan_transport.py'='updates/v4_5_24_historia_demographics/historia_lan_transport.py'
'app_patch_4519.py'='updates/v4_5_19_sidebar_real_version/app_patch_4519.py'
'app_patch_4518.py'='updates/v4_5_18_real_version/app_patch_4518.py'
'app_patch_4517.py'='updates/v4_5_17_historia_link_status/app_patch_4517.py'
'historia_bridge.py'='updates/v4_5_24_historia_demographics/historia_bridge.py'
'app_patch_4516.py'='updates/v4_5_16_unified_rescue/app_patch_4516.py'
'app_patch_4511.py'='updates/v4_5_11_shortcut_branding/app_patch_4511.py'
'app_patch_4510.py'='updates/v4_5_10_auto_recovery/app_patch_4510.py'
'app_patch_4509.py'='updates/v4_5_09_historia_bridge_stable/app_patch_4509.py'
'app_patch_4508.py'='updates/v4_5_08_historia_bridge/app_patch_4508.py'
'app_patch_4506.py'='updates/v4_5_06_bendo_config/app_patch_4506.py'
'app_patch_4504.py'='updates/v4_5_04_dataphone_ready/app_patch_4504.py'
'app_patch_4502.py'='updates/v4_5_02_couple_discount/app_patch_4502.py'
'app_patch_4501.py'='updates/v4_5_01_stable_maintenance/app_patch_4501.py'
'app_patch_4491.py'='updates/v4_4_91_billing_form_no_lines/app_patch_4491.py'
'app_patch_4490.py'='updates/v4_4_90_billing_form_compact/app_patch_4490.py'
'app_patch_4489.py'='updates/v4_4_89_billing_data_form/app_patch_4489.py'
'app_patch_4488.py'='updates/v4_4_88_payment_proof_compact/app_patch_4488.py'
'app_patch_4487.py'='updates/v4_4_87_payment_proof_safe_right/app_patch_4487.py'
'app_patch_4486.py'='updates/v4_4_86_single_print_menu/app_patch_4486.py'
'app_patch_4485.py'='updates/v4_4_85_payment_proof/app_patch_4485.py'
'app_patch_4484.py'='updates/v4_4_84_optional_billing_email/app_patch_4484.py'
'app_patch_4483.py'='updates/v4_4_83_mandatory_update_gate/app_patch_4483.py'
'app_patch_4482.py'='updates/v4_4_82_updater_repair/app_patch_4482.py'
'app_patch_4481.py'='updates/v4_4_81_remove_facturero_modal/app_patch_4481.py'
'app_patch_4480.py'='updates/v4_4_80_billing_emitidas_hotfix/app_patch_4480.py'
'app_patch_4479.py'='updates/v4_4_79_cleanup_obsolete_ui/app_patch_4479.py'
'app_patch_4478.py'='updates/v4_4_78_visible_discard_stable_version/app_patch_4478.py'
'app_patch_4477.py'='updates/v4_4_77_discard_pending_billing/app_patch_4477.py'
'app_patch_4476.py'='updates/v4_4_76_billing_services_coherence/app_patch_4476.py'
'app_patch_4475.py'='updates/v4_4_75_fast_save_services/app_patch_4475.py'
'app_patch_4474.py'='updates/v4_4_74_async_print_stable/app_patch_4474.py'
'app_patch_4473.py'='updates/v4_4_73_stable_recovery/app_patch_4473.py'
'app_patch_4470.py'='updates/v4_4_70_workflow_fixes/app_patch_4470.py'
'app_patch_4469.py'='updates/v4_4_69_receipt_left_wide/app_patch_4469.py'
'app_patch_4468.py'='updates/v4_4_68_receipt_large_long/app_patch_4468.py'
'app_patch_4467.py'='updates/v4_4_67_receipt_large_clean/app_patch_4467.py'
'app_patch_4466.py'='updates/v4_4_66_receipt_raster/app_patch_4466.py'
'app_patch_4465.py'='updates/v4_4_65_receipt_unified/app_patch_4465.py'
'app_patch_4464.py'='updates/v4_4_64_receipt_edge_to_edge/app_patch_4464.py'
'app_patch_4463.py'='updates/v4_4_63_receipt_match_preview/app_patch_4463.py'
'app_patch_4462.py'='updates/v4_4_62_receipt_uniform/app_patch_4462.py'
'app_patch_4461.py'='updates/v4_4_61_receipt_crm308/app_patch_4461.py'
'app_patch_4459.py'='updates/v4_4_60_rescue_direct_app/app_patch_4459.py'
'app_prev_4458.py'='updates/v4_4_60_rescue_direct_app/app_prev_4458.py'
'app_base_4428.py'='updates/v4_4_60_rescue_direct_app/app_base_4428.py'
'ABRIR_RECEPCION.py'='updates/v4_5_16_unified_rescue/ABRIR_RECEPCION.py'
'update_manifest.json'='updates/v4_5_25_bendo_click_hotfix/update_manifest.json'
}
foreach($name in $files.Keys){
    DownloadPinned $files[$name] (Join-Path $recep $name)
}

$manifest=Get-Content (Join-Path $recep 'update_manifest.json') -Raw | ConvertFrom-Json
if([string]$manifest.version -ne '4.5.25'){ throw 'Recepción no quedó en 4.5.25' }
foreach($rel in @($manifest.required_dependencies)){
    if(-not (Test-Path (Join-Path $recep ([string]$rel)))){ throw "Falta dependencia Recepción: $rel" }
}
foreach($p in Get-ChildItem $recep -Filter '*.py' -File){
    & python -m py_compile $p.FullName
    if($LASTEXITCODE -ne 0){ throw "Sintaxis inválida: $($p.Name)" }
}

Setup-EmbeddedPython $recep @(
    'fastapi==0.115.6',
    'pydantic==1.10.15',
    'uvicorn==0.34.0',
    'SQLAlchemy==2.0.36',
    'pg8000==1.31.2',
    'python-dotenv==1.0.1',
    'python-multipart==0.0.20',
    'pywebview==6.2.1'
) 'Recepción 4.5.25'

Step '2/8 Smoke test de Recepción 4.5.25'
$recepPy=Join-Path $recep '.venv\\Scripts\\python.exe'
$smokeData=Join-Path $root 'recep_smoke_data'
New-Item -ItemType Directory -Force $smokeData | Out-Null
$oldForce=$env:RP_FORCE_OFFLINE; $oldData=$env:RP_DATA_DIR; $oldDb=$env:DATABASE_URL
try{
    $env:RP_FORCE_OFFLINE='1'
    $env:RP_DATA_DIR=$smokeData
    $env:DATABASE_URL='postgresql://dummy:dummy@127.0.0.1:5432/dummy?sslmode=require'
    Push-Location $recep
    try{
        & $recepPy -c "import os,sys; sys.path.insert(0,os.getcwd()); import app; print('RECEPCION_IMPORT_OK', app.APP_VERSION)"
        if($LASTEXITCODE -ne 0){ throw 'Recepción 4.5.25 no importó correctamente' }
    } finally { Pop-Location }
} finally {
    $env:RP_FORCE_OFFLINE=$oldForce; $env:RP_DATA_DIR=$oldData; $env:DATABASE_URL=$oldDb
    Remove-Item $smokeData -Recurse -Force -ErrorAction SilentlyContinue
}

Step '3/8 Reconstruyendo Historia Clínica publicada 1.3.2'
$histManifestLocal=Join-Path $root 'latest-historia-runtime.json'
DownloadPinned 'latest-historia-runtime.json' $histManifestLocal
$hm=Get-Content $histManifestLocal -Raw | ConvertFrom-Json
if([string]$hm.version -ne '1.3.2'){ throw "Historia esperada 1.3.2, encontrada $($hm.version)" }
foreach($entry in @($hm.files)){
    $dest=Join-Path $hist (([string]$entry.path).Replace('/','\\'))
    Download-ManifestFile $entry $dest
}
New-Item -ItemType Directory -Force (Join-Path $hist 'data') | Out-Null

$reqFile=Join-Path $hist 'requirements.txt'
$histPkgs=@(Get-Content $reqFile | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') })
Setup-EmbeddedPython $hist $histPkgs 'Historia Clínica 1.3.2'
$histPy=Join-Path $hist '.venv\\Scripts\\python.exe'
& $histPy -m py_compile (Join-Path $hist 'app.py') (Join-Path $hist 'ABRIR_HISTORIA_CLINICA.py')
if($LASTEXITCODE -ne 0){ throw 'Historia Clínica no pasó py_compile' }

Step '4/8 Preparando WebView2 y scripts privados'
Download 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' (Join-Path $payload 'MicrosoftEdgeWebView2Setup.exe')
Copy-Item (Join-Path $PSScriptRoot 'install_private_config.ps1') (Join-Path $payload 'install_private_config.ps1') -Force

Step '5/8 Compilando instalador maestro genérico'
if(-not (Test-Path 'C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe')){
    choco install innosetup -y --no-progress
}
Copy-Item (Join-Path $PSScriptRoot 'PrivateMaster.iss') (Join-Path $root 'PrivateMaster.iss') -Force
Push-Location $root
try{
    & 'C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe' 'PrivateMaster.iss'
    if($LASTEXITCODE -ne 0){ throw 'Inno Setup falló' }
} finally { Pop-Location }
$generic=Join-Path $output 'INSTALAR_CONSULTORIO_DR_REVELO_BASE.exe'
if(-not (Test-Path $generic)){ throw 'No se generó instalador genérico' }

Step '6/8 Empaquetando wrapper final sin secretos'
$wrapperC=Join-Path $PSScriptRoot 'wrapper.c'
$wrapperCopy=Join-Path $build 'wrapper.c'
Copy-Item $wrapperC $wrapperCopy -Force
$rc=Join-Path $build 'wrapper.rc'
('101 RCDATA "{0}"' -f $generic) | Set-Content $rc -Encoding ascii

$vswhere='C:\\Program Files (x86)\\Microsoft Visual Studio\\Installer\\vswhere.exe'
$vs=( & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath )
if(-not $vs){ throw 'No se encontró Visual Studio Build Tools' }
$dev=Join-Path $vs 'Common7\\Tools\\VsDevCmd.bat'
$cmdLines=@(
    ('call "{0}" -arch=x64 -host_arch=x64' -f $dev),
    ('cd /d "{0}"' -f $build),
    'rc.exe wrapper.rc',
    'cl.exe /nologo /O2 /DUNICODE /D_UNICODE wrapper.c wrapper.res /link /SUBSYSTEM:WINDOWS /OUT:INSTALAR_CONSULTORIO_DR_REVELO_PRIVADO_BASE.exe shell32.lib user32.lib'
)
$cmdFile=Join-Path $build 'compile_wrapper.cmd'
$cmdLines | Set-Content $cmdFile -Encoding ascii
& cmd.exe /c $cmdFile
if($LASTEXITCODE -ne 0){ throw 'No se pudo compilar wrapper' }
$wrapper=Join-Path $build 'INSTALAR_CONSULTORIO_DR_REVELO_PRIVADO_BASE.exe'
if(-not (Test-Path $wrapper)){ throw 'No se generó wrapper base' }

Step '7/8 Prueba end-to-end con credenciales ficticias'
$test=Join-Path $build 'TEST_PRIVATE_MASTER.exe'
Copy-Item $wrapper $test -Force
$dummy=@"
DATABASE_URL=postgresql://dummy:dummy@127.0.0.1:5432/dummy?sslmode=require
AZUR_BASE_URL=https://example.invalid
AZUR_API_KEY=TEST_ONLY_DO_NOT_USE
MOBILE_DOCTOR_TOKEN=TEST_DOCTOR
MOBILE_RECEPTION_TOKEN=TEST_RECEPTION
RP_DATA_DIR=data
"@
$envBytes=[System.Text.Encoding]::UTF8.GetBytes($dummy)
$magic=[System.Text.Encoding]::ASCII.GetBytes('DRREVELOENV1')
$len=[BitConverter]::GetBytes([Int64]$envBytes.Length)
$fs=[System.IO.File]::Open($test,[System.IO.FileMode]::Append,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
try{
    $fs.Write($envBytes,0,$envBytes.Length)
    $fs.Write($len,0,$len.Length)
    $fs.Write($magic,0,$magic.Length)
} finally { $fs.Dispose() }

foreach($d in @('C:\\Recepcion Dr Revelo','C:\\Historia Clinica Dr Revelo')){
    if(Test-Path $d){ Remove-Item $d -Recurse -Force }
}
$p=Start-Process -FilePath $test -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/MODE=both') -Wait -PassThru
if($p.ExitCode -ne 0){ throw "Wrapper test devolvió $($p.ExitCode)" }
foreach($p2 in @(
    'C:\\Recepcion Dr Revelo\\app.py',
    'C:\\Recepcion Dr Revelo\\app_patch_4506.py',
    'C:\\Recepcion Dr Revelo\\.env',
    'C:\\Historia Clinica Dr Revelo\\app.py',
    'C:\\Historia Clinica Dr Revelo\\.env'
)){
    if(-not (Test-Path $p2)){ throw "Falta tras instalación: $p2" }
}
$renv=Get-Content 'C:\\Recepcion Dr Revelo\\.env' -Raw
if($renv -notmatch 'TEST_ONLY_DO_NOT_USE'){ throw 'La config ficticia no llegó a Recepción' }
$henv=Get-Content 'C:\\Historia Clinica Dr Revelo\\.env' -Raw
if($henv -notmatch 'HISTORIA_DATABASE_URL=postgresql://dummy'){ throw 'Historia no derivó DATABASE_URL' }

Step '8/8 Resultado'
$final=Join-Path $output 'INSTALAR_CONSULTORIO_DR_REVELO_PRIVADO_BASE.exe'
Copy-Item $wrapper $final -Force
$hash=(Get-FileHash $final -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  INSTALAR_CONSULTORIO_DR_REVELO_PRIVADO_BASE.exe" | Set-Content (Join-Path $output 'SHA256_BASE.txt') -Encoding ascii
Write-Host "PRIVATE_MASTER_BASE_OK $final"
Write-Host "SHA256_BASE=$hash"

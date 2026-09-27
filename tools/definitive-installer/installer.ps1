param(
  [Parameter(Mandatory=$true)][string]$ReceptionEnvPath,
  [Parameter(Mandatory=$true)][string]$HistoriaEnvPath,
  [string]$Mode = '',
  [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$InstallerVersion = '2.0.0-private'
$RepoRaw = 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main'
$ReceptionAppChannelUrl = "$RepoRaw/launcher-v1/app-channel.json"
$HistoriaAppChannelUrl = "$RepoRaw/historia-clinica/launcher-v1/app-channel.json"
$ReceptionLauncherChannelUrl = "$RepoRaw/launcher-v1/launcher-channel.json"
$HistoriaLauncherChannelUrl = "$RepoRaw/historia-clinica/launcher-v1/launcher-channel.json"
$ReceptionTarget = 'C:\Recepcion Dr Revelo'
$HistoriaTarget = 'C:\Historia Clinica Dr Revelo'
$PrivateRoot = Join-Path $env:ProgramData 'DrRevelo'
$LogRoot = Join-Path $PrivateRoot 'Installer'
$BackupRoot = Join-Path $PrivateRoot 'Backups'
$PythonRoot = Join-Path $PrivateRoot 'Runtime\Python311'
$PythonExe = Join-Path $PythonRoot 'python.exe'
$RunId = Get-Date -Format 'yyyyMMdd-HHmmss'
$WorkRoot = Join-Path $env:TEMP ("DrReveloInstaller-" + $RunId)
$LogPath = Join-Path $LogRoot ("install-" + $RunId + '.log')

New-Item -ItemType Directory -Force $LogRoot,$BackupRoot,$WorkRoot | Out-Null

function Write-Log([string]$Message) {
  $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
  Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

$script:ProgressForm = $null
$script:ProgressLabel = $null
$script:ProgressDetail = $null
$script:ProgressBar = $null
function Set-Status([string]$Title, [string]$Detail = '') {
  Write-Log ($Title + $(if($Detail){' · '+$Detail}else{''}))
  if ($script:ProgressForm) {
    $script:ProgressLabel.Text = $Title
    $script:ProgressDetail.Text = $Detail
    [System.Windows.Forms.Application]::DoEvents()
  }
}

function Show-Selection {
  $form = New-Object System.Windows.Forms.Form
  $form.Text = 'Instalador definitivo · Consultorio Dr. Armando Revelo'
  $form.StartPosition = 'CenterScreen'
  $form.Size = New-Object System.Drawing.Size(620,430)
  $form.MinimumSize = $form.Size
  $form.MaximumSize = $form.Size
  $form.BackColor = [System.Drawing.Color]::FromArgb(246,249,250)
  $form.Font = New-Object System.Drawing.Font('Segoe UI',10)

  $title = New-Object System.Windows.Forms.Label
  $title.Text = 'Consultorio Dr. Armando Revelo'
  $title.Font = New-Object System.Drawing.Font('Segoe UI Semibold',19)
  $title.AutoSize = $true
  $title.Location = New-Object System.Drawing.Point(30,25)
  $form.Controls.Add($title)

  $sub = New-Object System.Windows.Forms.Label
  $sub.Text = 'Instalación definitiva · configura, repara o actualiza sin tocar datos clínicos.'
  $sub.AutoSize = $true
  $sub.ForeColor = [System.Drawing.Color]::FromArgb(70,80,88)
  $sub.Location = New-Object System.Drawing.Point(33,70)
  $form.Controls.Add($sub)

  $group = New-Object System.Windows.Forms.GroupBox
  $group.Text = '¿Qué quieres preparar en esta PC?'
  $group.Location = New-Object System.Drawing.Point(32,112)
  $group.Size = New-Object System.Drawing.Size(540,160)
  $form.Controls.Add($group)

  $rBoth = New-Object System.Windows.Forms.RadioButton
  $rBoth.Text = 'Ambos · Recepción + Historia Clínica'
  $rBoth.Checked = $true
  $rBoth.Location = New-Object System.Drawing.Point(24,32)
  $rBoth.AutoSize = $true
  $group.Controls.Add($rBoth)

  $rReception = New-Object System.Windows.Forms.RadioButton
  $rReception.Text = 'Solo Recepción'
  $rReception.Location = New-Object System.Drawing.Point(24,72)
  $rReception.AutoSize = $true
  $group.Controls.Add($rReception)

  $rHistoria = New-Object System.Windows.Forms.RadioButton
  $rHistoria.Text = 'Solo Historia Clínica'
  $rHistoria.Location = New-Object System.Drawing.Point(24,112)
  $rHistoria.AutoSize = $true
  $group.Controls.Add($rHistoria)

  $note = New-Object System.Windows.Forms.Label
  $note.Text = 'Si ya existe una instalación, se hace respaldo y se conservan base de datos y configuración. En una PC nueva, queda lista desde cero.'
  $note.Size = New-Object System.Drawing.Size(530,50)
  $note.Location = New-Object System.Drawing.Point(35,287)
  $note.ForeColor = [System.Drawing.Color]::FromArgb(70,80,88)
  $form.Controls.Add($note)

  $install = New-Object System.Windows.Forms.Button
  $install.Text = 'Instalar / Reparar'
  $install.Size = New-Object System.Drawing.Size(165,42)
  $install.Location = New-Object System.Drawing.Point(407,340)
  $install.BackColor = [System.Drawing.Color]::FromArgb(18,145,160)
  $install.ForeColor = [System.Drawing.Color]::White
  $install.FlatStyle = 'Flat'
  $install.Add_Click({
      if ($rReception.Checked) { $form.Tag = 'reception' }
      elseif ($rHistoria.Checked) { $form.Tag = 'historia' }
      else { $form.Tag = 'both' }
      $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
      $form.Close()
  })
  $form.Controls.Add($install)

  $cancel = New-Object System.Windows.Forms.Button
  $cancel.Text = 'Cancelar'
  $cancel.Size = New-Object System.Drawing.Size(105,42)
  $cancel.Location = New-Object System.Drawing.Point(290,340)
  $cancel.Add_Click({ $form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel; $form.Close() })
  $form.Controls.Add($cancel)

  $result = $form.ShowDialog()
  if ($result -ne [System.Windows.Forms.DialogResult]::OK) { return '' }
  return [string]$form.Tag
}

function Open-Progress {
  if ($NonInteractive) { return }
  $script:ProgressForm = New-Object System.Windows.Forms.Form
  $script:ProgressForm.Text = 'Preparando el consultorio'
  $script:ProgressForm.StartPosition = 'CenterScreen'
  $script:ProgressForm.Size = New-Object System.Drawing.Size(600,260)
  $script:ProgressForm.ControlBox = $false
  $script:ProgressForm.BackColor = [System.Drawing.Color]::White
  $script:ProgressForm.Font = New-Object System.Drawing.Font('Segoe UI',10)

  $script:ProgressLabel = New-Object System.Windows.Forms.Label
  $script:ProgressLabel.Text = 'Preparando instalación…'
  $script:ProgressLabel.Font = New-Object System.Drawing.Font('Segoe UI Semibold',17)
  $script:ProgressLabel.AutoSize = $true
  $script:ProgressLabel.Location = New-Object System.Drawing.Point(30,35)
  $script:ProgressForm.Controls.Add($script:ProgressLabel)

  $script:ProgressDetail = New-Object System.Windows.Forms.Label
  $script:ProgressDetail.Text = 'No cierres esta ventana.'
  $script:ProgressDetail.Size = New-Object System.Drawing.Size(525,55)
  $script:ProgressDetail.Location = New-Object System.Drawing.Point(33,87)
  $script:ProgressDetail.ForeColor = [System.Drawing.Color]::FromArgb(75,85,92)
  $script:ProgressForm.Controls.Add($script:ProgressDetail)

  $script:ProgressBar = New-Object System.Windows.Forms.ProgressBar
  $script:ProgressBar.Style = 'Marquee'
  $script:ProgressBar.MarqueeAnimationSpeed = 22
  $script:ProgressBar.Location = New-Object System.Drawing.Point(35,160)
  $script:ProgressBar.Size = New-Object System.Drawing.Size(515,24)
  $script:ProgressForm.Controls.Add($script:ProgressBar)

  $script:ProgressForm.Show()
  [System.Windows.Forms.Application]::DoEvents()
}

function Close-Progress {
  if ($NonInteractive) { return }
  if ($script:ProgressForm) { $script:ProgressForm.Close(); $script:ProgressForm.Dispose(); $script:ProgressForm = $null }
}

function Get-RemoteJson([string]$Url) {
  for ($i=1; $i -le 3; $i++) {
    try { return Invoke-RestMethod -UseBasicParsing -Uri $Url -TimeoutSec 35 -Headers @{ 'Cache-Control'='no-cache' } }
    catch { if ($i -eq 3) { throw }; Start-Sleep -Seconds (2*$i) }
  }
}

function Download-Verified([string]$Url,[string]$Destination,[string]$ExpectedSha) {
  $parent = Split-Path -Parent $Destination
  if ($parent) { New-Item -ItemType Directory -Force $parent | Out-Null }
  for ($i=1; $i -le 3; $i++) {
    try {
      if (Test-Path $Destination) { Remove-Item $Destination -Force }
      Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec 120 -Headers @{ 'Cache-Control'='no-cache' }
      if ($ExpectedSha) {
        $got = (Get-FileHash $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($got -ne $ExpectedSha.ToLowerInvariant()) { throw "SHA-256 inválido" }
      }
      return
    } catch {
      if ($i -eq 3) { throw "No se pudo descargar/verificar $Url. $($_.Exception.Message)" }
      Start-Sleep -Seconds (2*$i)
    }
  }
}

function Assert-SafeRelativePath([string]$Relative) {
  if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)') {
    throw "Ruta no segura en canal: $Relative"
  }
}

function Get-AppPayload([string]$Name,[string]$ChannelUrl) {
  Set-Status "Descargando $Name" 'Verificando canal estable y SHA-256 de cada archivo…'
  $channel = Get-RemoteJson $ChannelUrl
  if ([string]$channel.status -ne 'stable') { throw "$Name no está en canal estable." }
  if (-not $channel.appVersion) { throw "$Name no publicó appVersion." }
  $stage = Join-Path $WorkRoot ("payload-" + $Name.Replace(' ','-'))
  New-Item -ItemType Directory -Force $stage | Out-Null
  foreach ($f in @($channel.files)) {
    $rel = [string]$f.path
    Assert-SafeRelativePath $rel
    Download-Verified ([string]$f.url) (Join-Path $stage ($rel -replace '/', '\')) ([string]$f.sha256)
  }
  return [pscustomobject]@{ Channel=$channel; Stage=$stage }
}

function Get-LauncherInstaller([string]$Name,[string]$ChannelUrl) {
  Set-Status "Preparando launcher de $Name" 'Descargando el instalador oficial y verificando SHA-256…'
  $channel = Get-RemoteJson $ChannelUrl
  if (-not $channel.installerUrl -or -not $channel.installerSha256) { throw "Canal de launcher incompleto para $Name." }
  $dest = Join-Path $WorkRoot ("launcher-" + $Name.Replace(' ','-') + '.exe')
  Download-Verified ([string]$channel.installerUrl) $dest ([string]$channel.installerSha256)
  return [pscustomobject]@{ Channel=$channel; Path=$dest }
}

function Test-SignedInstaller([string]$Path,[string]$SignerPattern) {
  $sig = Get-AuthenticodeSignature -FilePath $Path
  if ($sig.Status -ne 'Valid' -or -not $sig.SignerCertificate -or $sig.SignerCertificate.Subject -notmatch $SignerPattern) {
    throw "Firma digital no válida para $([IO.Path]::GetFileName($Path))."
  }
}

function Ensure-Python311 {
  if (Test-Path $PythonExe) {
    try {
      $v = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
      if (($v | Out-String).Trim() -eq '3.11') { Write-Log 'Python 3.11 privado ya disponible.'; return }
    } catch {}
  }
  Set-Status 'Instalando motor Python privado' 'No modifica el PATH de Windows ni necesita configuración manual.'
  $installer = Join-Path $WorkRoot 'python-3.11.9-amd64.exe'
  Download-Verified 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' $installer ''
  Test-SignedInstaller $installer 'Python Software Foundation'
  New-Item -ItemType Directory -Force $PythonRoot | Out-Null
  $args = @('/quiet','InstallAllUsers=1',("TargetDir=$PythonRoot"),'Include_launcher=0','InstallLauncherAllUsers=0','PrependPath=0','Shortcuts=0','Include_doc=0','Include_test=0','Include_tcltk=0','Include_pip=1','Include_dev=0','Include_debug=0','Include_symbols=0','SimpleInstall=1')
  $p = Start-Process -FilePath $installer -ArgumentList $args -PassThru -Wait
  if ($p.ExitCode -ne 0 -or -not (Test-Path $PythonExe)) { throw "Python 3.11 no pudo instalarse (código $($p.ExitCode))." }
}

function Test-WebView2 {
  $roots = @(
    "${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application",
    "$env:ProgramFiles\Microsoft\EdgeWebView\Application"
  )
  foreach ($r in $roots) {
    if ($r -and (Test-Path $r)) {
      if (Get-ChildItem $r -Recurse -Filter 'msedgewebview2.exe' -ErrorAction SilentlyContinue | Select-Object -First 1) { return $true }
    }
  }
  return $false
}

function Ensure-WebView2 {
  if (Test-WebView2) { Write-Log 'WebView2 Runtime ya disponible.'; return }
  Set-Status 'Instalando WebView2' 'Componente oficial de Microsoft para la ventana del programa…'
  $installer = Join-Path $WorkRoot 'MicrosoftEdgeWebview2Setup.exe'
  Download-Verified 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' $installer ''
  Test-SignedInstaller $installer 'Microsoft'
  $p = Start-Process -FilePath $installer -ArgumentList @('/silent','/install') -PassThru -Wait
  if ($p.ExitCode -ne 0) { throw "WebView2 no pudo instalarse (código $($p.ExitCode))." }
  if (-not (Test-WebView2)) { throw 'WebView2 no quedó disponible después de instalar.' }
}

function Prepare-Venv([string]$Product,[string]$Stage) {
  Set-Status "Preparando dependencias de $Product" 'Creando un entorno nuevo sin tocar el que ya funciona…'
  $venv = Join-Path $WorkRoot ("venv-" + $Product.Replace(' ','-'))
  if (Test-Path $venv) { Remove-Item $venv -Recurse -Force }
  & $PythonExe -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno de $Product." }
  $py = Join-Path $venv 'Scripts\python.exe'
  if ($Product -eq 'Recepción') {
    $deps = @(
      'fastapi==0.128.2','uvicorn==0.48.0','SQLAlchemy==2.0.43',
      'pg8000==1.31.2','python-dotenv==1.1.1','python-multipart==0.0.20'
    )
    & $py -m pip install --disable-pip-version-check --no-warn-script-location @deps
  } else {
    & $py -m pip install --disable-pip-version-check --no-warn-script-location -r (Join-Path $Stage 'requirements.txt')
  }
  if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias de $Product." }
  return $venv
}

function Test-StagedRuntime([string]$Product,[string]$Stage,[string]$Venv,[string]$ExpectedVersion) {
  Set-Status "Probando $Product antes de instalar" 'Importación aislada del runtime descargado…'
  $py = Join-Path $Venv 'Scripts\python.exe'
  $oldDb=$env:DATABASE_URL; $oldHdb=$env:HISTORIA_DATABASE_URL; $oldOff=$env:RP_FORCE_OFFLINE; $oldPre=$env:HC_PREFLIGHT; $oldSync=$env:HISTORIA_SYNC_ENABLED
  try {
    $env:DATABASE_URL=''; $env:HISTORIA_DATABASE_URL=''; $env:RP_FORCE_OFFLINE='1'; $env:HC_PREFLIGHT='1'; $env:HISTORIA_SYNC_ENABLED='0'; $env:PYTHONDONTWRITEBYTECODE='1'
    Push-Location $Stage
    & $py -c "import app; assert app.APP_VERSION == '$ExpectedVersion', app.APP_VERSION; print('RUNTIME_OK')" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "El runtime de $Product no superó la preprueba." }
  } finally {
    Pop-Location -ErrorAction SilentlyContinue
    $env:DATABASE_URL=$oldDb; $env:HISTORIA_DATABASE_URL=$oldHdb; $env:RP_FORCE_OFFLINE=$oldOff; $env:HC_PREFLIGHT=$oldPre; $env:HISTORIA_SYNC_ENABLED=$oldSync
  }
}

function Backup-Target([string]$Product,[string]$Target) {
  if (-not (Test-Path $Target)) { return '' }
  $hasAny = Get-ChildItem $Target -Force -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $hasAny) { return '' }
  Set-Status "Respaldando $Product" 'Guardando la instalación actual antes de modificarla…'
  $dest = Join-Path (Join-Path $BackupRoot $RunId) ($Product.Replace('ó','o').Replace('í','i').Replace(' ','-'))
  New-Item -ItemType Directory -Force $dest | Out-Null
  & robocopy $Target $dest /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XD '.venv' '__pycache__' '_update_backups' | Out-Null
  if ($LASTEXITCODE -gt 7) { throw "No se pudo respaldar $Product (robocopy $LASTEXITCODE)." }
  return $dest
}

function Merge-PrivateEnv([string]$TargetEnv,[string]$TemplateEnv) {
  if (-not (Test-Path $TemplateEnv)) { throw 'Falta la configuración privada embebida.' }
  $template = Get-Content $TemplateEnv -Encoding UTF8
  if (-not (Test-Path $TargetEnv)) {
    Copy-Item $TemplateEnv $TargetEnv -Force
  } else {
    $existing = Get-Content $TargetEnv -Encoding UTF8
    $keys = @{}
    foreach ($line in $existing) {
      if ($line -match '^\s*([^#=\s]+)\s*=') { $keys[$matches[1]] = $true }
    }
    $append = New-Object System.Collections.Generic.List[string]
    foreach ($line in $template) {
      if ($line -match '^\s*([^#=\s]+)\s*=') {
        if (-not $keys.ContainsKey($matches[1])) { $append.Add($line) }
      }
    }
    if ($append.Count -gt 0) {
      Add-Content $TargetEnv -Value '' -Encoding UTF8
      Add-Content $TargetEnv -Value '# Agregado por instalador definitivo Dr. Revelo' -Encoding UTF8
      Add-Content $TargetEnv -Value $append -Encoding UTF8
    }
  }
}

function Protect-SecretFile([string]$Path) {
  try {
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true,$false)
    $full = [System.Security.AccessControl.FileSystemRights]::FullControl
    $inherit = [System.Security.AccessControl.InheritanceFlags]::None
    $prop = [System.Security.AccessControl.PropagationFlags]::None
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    $current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $system = [System.Security.Principal.SecurityIdentifier]::new([System.Security.Principal.WellKnownSidType]::LocalSystemSid,$null)
    $admins = [System.Security.Principal.SecurityIdentifier]::new([System.Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid,$null)
    foreach ($sid in @($current,$system,$admins)) {
      $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($sid,$full,$inherit,$prop,$allow)))
    }
    Set-Acl -Path $Path -AclObject $acl
    (Get-Item $Path -Force).Attributes = ((Get-Item $Path -Force).Attributes -bor [IO.FileAttributes]::Hidden)
  } catch { Write-Log ('Advertencia ACL .env: ' + $_.Exception.Message) }
}

function Apply-Payload([object]$Payload,[string]$Target) {
  New-Item -ItemType Directory -Force $Target | Out-Null
  foreach ($f in @($Payload.Channel.files)) {
    $rel = [string]$f.path
    $src = Join-Path $Payload.Stage ($rel -replace '/', '\')
    $dst = Join-Path $Target ($rel -replace '/', '\')
    $parent = Split-Path -Parent $dst
    if ($parent) { New-Item -ItemType Directory -Force $parent | Out-Null }
    Copy-Item $src $dst -Force
  }
  Get-ChildItem $Target -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(app_patch_|app_prev|app_base)' } | Remove-Item -Force -ErrorAction SilentlyContinue
  if (Test-Path (Join-Path $Target '__pycache__')) { Remove-Item (Join-Path $Target '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue }
}

function Swap-Venv([string]$Target,[string]$NewVenv) {
  $current = Join-Path $Target '.venv'
  $previous = Join-Path $Target ('.venv.installer-prev-' + $RunId)
  if (Test-Path $previous) { Remove-Item $previous -Recurse -Force }
  if (Test-Path $current) { Move-Item $current $previous }
  Move-Item $NewVenv $current
  return $previous
}

function Restore-OnFailure([string]$Target,[string]$Backup,[string]$PreviousVenv) {
  try {
    $current = Join-Path $Target '.venv'
    if (Test-Path $current) { Remove-Item $current -Recurse -Force -ErrorAction SilentlyContinue }
    if ($PreviousVenv -and (Test-Path $PreviousVenv)) { Move-Item $PreviousVenv $current -Force }
    if ($Backup -and (Test-Path $Backup)) {
      & robocopy $Backup $Target /MIR /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XD '.venv' | Out-Null
    }
  } catch { Write-Log ('Fallo durante rollback: ' + $_.Exception.Message) }
}

function Test-InstalledRuntime([string]$Product,[string]$Target,[string]$ExpectedVersion) {
  Set-Status "Verificando $Product" 'Probando la instalación final sin conectarse a datos clínicos remotos…'
  $py = Join-Path $Target '.venv\Scripts\python.exe'
  if (-not (Test-Path $py)) { throw "Falta Python privado de $Product." }
  $oldDb=$env:DATABASE_URL; $oldHdb=$env:HISTORIA_DATABASE_URL; $oldOff=$env:RP_FORCE_OFFLINE; $oldPre=$env:HC_PREFLIGHT; $oldSync=$env:HISTORIA_SYNC_ENABLED
  try {
    $env:DATABASE_URL=''; $env:HISTORIA_DATABASE_URL=''; $env:RP_FORCE_OFFLINE='1'; $env:HC_PREFLIGHT='1'; $env:HISTORIA_SYNC_ENABLED='0'; $env:PYTHONDONTWRITEBYTECODE='1'
    Push-Location $Target
    & $py -c "import app; assert app.APP_VERSION == '$ExpectedVersion', app.APP_VERSION; print('FINAL_OK')" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "La verificación final de $Product falló." }
  } finally {
    Pop-Location -ErrorAction SilentlyContinue
    $env:DATABASE_URL=$oldDb; $env:HISTORIA_DATABASE_URL=$oldHdb; $env:RP_FORCE_OFFLINE=$oldOff; $env:HC_PREFLIGHT=$oldPre; $env:HISTORIA_SYNC_ENABLED=$oldSync
  }
}

function Test-Neon([string]$Product,[string]$Target,[string]$Key) {
  $py = Join-Path $Target '.venv\Scripts\python.exe'
  $envFile = Join-Path $Target '.env'
  $code = @'
import os,sys,urllib.parse,ssl
from pathlib import Path
import pg8000
p=Path(sys.argv[1]); key=sys.argv[2]
val=''
for raw in p.read_text(encoding='utf-8-sig',errors='ignore').splitlines():
    if '=' in raw and not raw.lstrip().startswith('#'):
        k,v=raw.split('=',1)
        if k.strip()==key:
            val=v.strip().strip('"').strip("'"); break
if not val: raise SystemExit(3)
u=urllib.parse.urlsplit(val)
conn=pg8000.connect(user=urllib.parse.unquote(u.username or ''),password=urllib.parse.unquote(u.password or ''),host=u.hostname,port=u.port or 5432,database=urllib.parse.unquote((u.path or '/neondb').lstrip('/')) or 'neondb',ssl_context=ssl.create_default_context(),timeout=12)
cur=conn.cursor(); cur.execute('select 1'); cur.fetchone(); conn.close(); print('NEON_OK')
'@
  try {
    & $py -c $code $envFile $Key 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Log "$Product: conexión Neon verificada."; return $true }
  } catch {}
  Write-Log "$Product: no se pudo verificar Neon ahora; la instalación se conserva y reintentará al abrir."
  return $false
}

function Install-Product([string]$Product,[string]$Target,[string]$AppChannelUrl,[string]$LauncherChannelUrl,[string]$PrivateEnvPath) {
  $payload = Get-AppPayload $Product $AppChannelUrl
  $launcher = Get-LauncherInstaller $Product $LauncherChannelUrl
  $venv = Prepare-Venv $Product $payload.Stage
  Test-StagedRuntime $Product $payload.Stage $venv ([string]$payload.Channel.appVersion)
  $backup = Backup-Target $Product $Target
  $previousVenv = ''
  try {
    Set-Status "Instalando $Product" ("Runtime estable " + [string]$payload.Channel.appVersion + '…')
    Apply-Payload $payload $Target
    Merge-PrivateEnv (Join-Path $Target '.env') $PrivateEnvPath
    Protect-SecretFile (Join-Path $Target '.env')
    $previousVenv = Swap-Venv $Target $venv

    Set-Status "Instalando launcher de $Product" ("Launcher " + [string]$launcher.Channel.latestVersion + '…')
    $p = Start-Process -FilePath $launcher.Path -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-') -PassThru -Wait
    if ($p.ExitCode -ne 0) { throw "El launcher de $Product devolvió código $($p.ExitCode)." }

    Test-InstalledRuntime $Product $Target ([string]$payload.Channel.appVersion)
    if ($Product -eq 'Recepción') { [void](Test-Neon $Product $Target 'DATABASE_URL') }
    else { [void](Test-Neon $Product $Target 'HISTORIA_DATABASE_URL') }

    if ($previousVenv -and (Test-Path $previousVenv)) { Remove-Item $previousVenv -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Log "$Product instalado correctamente."
    return [string]$payload.Channel.appVersion
  } catch {
    Write-Log ("$Product falló: " + $_.Exception.Message)
    Restore-OnFailure $Target $backup $previousVenv
    throw
  }
}

$mode = if ($Mode) { $Mode.ToLowerInvariant() } else { Show-Selection }
if ($mode -notin @('reception','historia','both','')) { throw "Modo inválido: $mode" }
if (-not $mode) { Write-Log 'Instalación cancelada por el usuario.'; exit 2 }
Open-Progress
try {
  Set-Status 'Comprobando Internet' 'Leyendo los canales oficiales del consultorio…'
  [void](Get-RemoteJson $ReceptionAppChannelUrl)
  Ensure-Python311
  Ensure-WebView2

  $done = New-Object System.Collections.Generic.List[string]
  if ($mode -eq 'reception' -or $mode -eq 'both') {
    $ver = Install-Product 'Recepción' $ReceptionTarget $ReceptionAppChannelUrl $ReceptionLauncherChannelUrl $ReceptionEnvPath
    $done.Add("Recepción $ver")
  }
  if ($mode -eq 'historia' -or $mode -eq 'both') {
    $ver = Install-Product 'Historia Clínica' $HistoriaTarget $HistoriaAppChannelUrl $HistoriaLauncherChannelUrl $HistoriaEnvPath
    $done.Add("Historia Clínica $ver")
  }

  Set-Status 'Instalación terminada' 'Todo quedó preparado para usar.'
  Close-Progress
  $text = "Instalación completada correctamente.`r`n`r`n" + ($done -join "`r`n") + "`r`n`r`nLos accesos directos ya están listos. Las futuras actualizaciones se harán automáticamente desde los canales estables."
  if (-not $NonInteractive) {
    [System.Windows.Forms.MessageBox]::Show($text,'Consultorio Dr. Armando Revelo',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
  }
  Write-Log 'INSTALACION_OK'
  exit 0
} catch {
  $message = $_.Exception.Message
  Write-Log ('INSTALACION_ERROR: ' + $message)
  Close-Progress
  if (-not $NonInteractive) {
    [System.Windows.Forms.MessageBox]::Show("No se completó la instalación.`r`n`r`n$message`r`n`r`nSe intentó restaurar automáticamente la instalación anterior. Registro: $LogPath",'Instalador del consultorio',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
  }
  exit 1
} finally {
  try { Remove-Item $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue } catch {}
}

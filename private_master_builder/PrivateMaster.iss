#define MyAppName "Instalador Maestro Privado - Consultorio Dr. Armando Revelo"
#define MyAppVersion "2026.09"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{42C012B1-2214-4E8A-AF92-4F6DF3F7A751}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
CreateAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_CONSULTORIO_DR_REVELO_BASE
Compression=lzma2/max
SolidCompression=yes
Uninstallable=no
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Dirs]
Name: "C:\Recepcion Dr Revelo"; Permissions: users-modify; Check: InstallRecepcion
Name: "C:\Recepcion Dr Revelo\data"; Permissions: users-modify; Check: InstallRecepcion
Name: "C:\Historia Clinica Dr Revelo"; Permissions: users-modify; Check: InstallHistoria
Name: "C:\Historia Clinica Dr Revelo\data"; Permissions: users-modify; Check: InstallHistoria

[Files]
Source: "payload\recepcion\*"; DestDir: "C:\Recepcion Dr Revelo"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env;data\*;backups\*;update_backups\*;*.db;*.sqlite;*.sqlite3;BASE DE DATOS 2026.xlsx;HISTORICO_PACIENTES_2020_2025.csv"; Check: InstallRecepcion
Source: "payload\historia\*"; DestDir: "C:\Historia Clinica Dr Revelo"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env;data\*;*.db;*.sqlite;*.sqlite3"; Check: InstallHistoria
Source: "payload\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; DestName: "MicrosoftEdgeWebView2Setup.exe"; Flags: deleteafterinstall; Check: InstallAny
Source: "payload\install_private_config.ps1"; DestDir: "{tmp}"; DestName: "install_private_config.ps1"; Flags: deleteafterinstall

[Icons]
Name: "{autodesktop}\Recepción Dr. Armando Revelo"; Filename: "C:\Recepcion Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Recepcion Dr Revelo\ABRIR_RECEPCION.py"""; WorkingDir: "C:\Recepcion Dr Revelo"; IconFilename: "C:\Recepcion Dr Revelo\static\doctor_icon.ico"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"; Check: InstallRecepcion
Name: "{autoprograms}\Recepción Dr. Armando Revelo"; Filename: "C:\Recepcion Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Recepcion Dr Revelo\ABRIR_RECEPCION.py"""; WorkingDir: "C:\Recepcion Dr Revelo"; IconFilename: "C:\Recepcion Dr Revelo\static\doctor_icon.ico"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"; Check: InstallRecepcion
Name: "{autodesktop}\Historia Clínica - Dr. Armando Revelo"; Filename: "C:\Historia Clinica Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Historia Clinica Dr Revelo\ABRIR_HISTORIA_CLINICA.py"""; WorkingDir: "C:\Historia Clinica Dr Revelo"; IconFilename: "C:\Historia Clinica Dr Revelo\static\doctor_icon.ico"; Comment: "Historia Clínica - Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.HistoriaClinica"; Check: InstallHistoria
Name: "{autoprograms}\Historia Clínica - Dr. Armando Revelo"; Filename: "C:\Historia Clinica Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Historia Clinica Dr Revelo\ABRIR_HISTORIA_CLINICA.py"""; WorkingDir: "C:\Historia Clinica Dr Revelo"; IconFilename: "C:\Historia Clinica Dr Revelo\static\doctor_icon.ico"; Comment: "Historia Clínica - Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.HistoriaClinica"; Check: InstallHistoria

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Preparando WebView2..."; Flags: waituntilterminated; Check: InstallAnyAndNeedWebView2
Filename: "C:\Recepcion Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Recepcion Dr Revelo\ABRIR_RECEPCION.py"""; WorkingDir: "C:\Recepcion Dr Revelo"; Description: "Abrir Recepción"; Flags: nowait postinstall skipifsilent; Check: InstallRecepcion
Filename: "C:\Historia Clinica Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Historia Clinica Dr Revelo\ABRIR_HISTORIA_CLINICA.py"""; WorkingDir: "C:\Historia Clinica Dr Revelo"; Description: "Abrir Historia Clínica"; Flags: nowait postinstall skipifsilent; Check: InstallHistoria

[Code]
var
  ModePage: TInputOptionWizardPage;
  PrivacyLabel: TNewStaticText;

function InstallRecepcion(): Boolean;
begin
  Result := (ModePage.SelectedValueIndex = 0) or (ModePage.SelectedValueIndex = 2);
end;

function InstallHistoria(): Boolean;
begin
  Result := (ModePage.SelectedValueIndex = 1) or (ModePage.SelectedValueIndex = 2);
end;

function InstallAny(): Boolean;
begin
  Result := InstallRecepcion() or InstallHistoria();
end;

function WebView2Installed(): Boolean;
var
  V: String;
begin
  Result :=
    RegQueryStringValue(HKLM64, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7CE48}', 'pv', V) or
    RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7CE48}', 'pv', V) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7CE48}', 'pv', V);
end;

function InstallAnyAndNeedWebView2(): Boolean;
begin
  Result := InstallAny() and (not WebView2Installed());
end;

procedure InitializeWizard();
var
  M: String;
begin
  ModePage := CreateInputOptionPage(
    wpWelcome,
    '¿Qué deseas instalar?',
    'Selecciona el equipo que estás preparando',
    'Este instalador contiene Recepción 4.5.25 e Historia Clínica 1.3.2.',
    True,
    False
  );
  ModePage.Add('Recepción');
  ModePage.Add('Historia Clínica');
  ModePage.Add('Ambos programas');

  M := Lowercase(ExpandConstant('{param:MODE|}'));
  if M = 'historia' then
    ModePage.SelectedValueIndex := 1
  else if M = 'both' then
    ModePage.SelectedValueIndex := 2
  else
    ModePage.SelectedValueIndex := 0;

  PrivacyLabel := TNewStaticText.Create(ModePage.Surface);
  PrivacyLabel.Parent := ModePage.Surface;
  PrivacyLabel.Top := ScaleY(190);
  PrivacyLabel.Left := 0;
  PrivacyLabel.Width := ModePage.Surface.Width;
  PrivacyLabel.AutoSize := False;
  PrivacyLabel.Height := ScaleY(68);
  PrivacyLabel.WordWrap := True;
  PrivacyLabel.Caption :=
    'El EXE privado contiene la configuración del consultorio. No incluye pacientes, historias clínicas ni bases locales. ' +
    'Si ya existe .env o data, se conservan.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PrivateEnv, Params, Switches: String;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    PrivateEnv := ExpandConstant('{param:PRIVATEENV|}');
    if (PrivateEnv = '') or (not FileExists(PrivateEnv)) then
    begin
      MsgBox('No se encontró la configuración privada incorporada al instalador.', mbError, MB_OK);
      exit;
    end;

    Switches := '';
    if InstallRecepcion() then Switches := Switches + ' -InstallReception';
    if InstallHistoria() then Switches := Switches + ' -InstallHistoria';

    Params := '-NoProfile -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{tmp}\install_private_config.ps1') + '" -SourceEnv "' +
      PrivateEnv + '"' + Switches;

    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      MsgBox('Windows no pudo aplicar la configuración privada.', mbError, MB_OK)
    else if ResultCode <> 0 then
      MsgBox('Los programas se instalaron, pero no se pudo aplicar la configuración privada.', mbError, MB_OK);

    if InstallRecepcion() and (not FileExists('C:\Recepcion Dr Revelo\app_patch_4506.py')) then
      MsgBox('Recepción quedó incompleta: falta app_patch_4506.py.', mbError, MB_OK);

    if InstallRecepcion() and (not FileExists('C:\Recepcion Dr Revelo\.env')) then
      MsgBox('Recepción no recibió su configuración privada.', mbError, MB_OK);

    if InstallHistoria() and (not FileExists('C:\Historia Clinica Dr Revelo\.env')) then
      MsgBox('Historia Clínica no recibió su configuración privada.', mbError, MB_OK);
  end;
end;

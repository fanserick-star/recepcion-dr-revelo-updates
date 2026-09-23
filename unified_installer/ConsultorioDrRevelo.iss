#define MyAppName "Instalador Maestro - Consultorio Dr. Armando Revelo"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{1C94B818-712D-4B2D-A2D0-D03E983CB894}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
CreateAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_CONSULTORIO_DR_REVELO_MAESTRO
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
; Payloads de programa. data/ y .env se excluyen deliberadamente.
Source: "payload\recepcion\*"; DestDir: "C:\Recepcion Dr Revelo"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env;data\*;backups\*;update_backups\*;*.db;*.sqlite;*.sqlite3;BASE DE DATOS 2026.xlsx;HISTORICO_PACIENTES_2020_2025.csv"; Check: InstallRecepcion
Source: "payload\historia\*"; DestDir: "C:\Historia Clinica Dr Revelo"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env;data\*;*.db;*.sqlite;*.sqlite3"; Check: InstallHistoria

; Configuración privada: se instala únicamente si no existe una configuración local.
Source: "payload\recepcion_config.env"; DestDir: "C:\Recepcion Dr Revelo"; DestName: ".env"; Flags: ignoreversion onlyifdoesntexist; Check: InstallRecepcion
Source: "payload\historia_config.env"; DestDir: "C:\Historia Clinica Dr Revelo"; DestName: ".env"; Flags: ignoreversion onlyifdoesntexist; Check: InstallHistoria

; WebView2 Evergreen bootstrapper. Se extrae solo durante la instalación.
Source: "payload\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; DestName: "MicrosoftEdgeWebView2Setup.exe"; Flags: deleteafterinstall; Check: InstallAny

[Icons]
Name: "{autodesktop}\Recepción Dr. Armando Revelo"; Filename: "C:\Recepcion Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Recepcion Dr Revelo\ABRIR_RECEPCION.py"""; WorkingDir: "C:\Recepcion Dr Revelo"; IconFilename: "C:\Recepcion Dr Revelo\static\doctor_icon.ico"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"; Check: InstallRecepcion
Name: "{autoprograms}\Recepción Dr. Armando Revelo"; Filename: "C:\Recepcion Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Recepcion Dr Revelo\ABRIR_RECEPCION.py"""; WorkingDir: "C:\Recepcion Dr Revelo"; IconFilename: "C:\Recepcion Dr Revelo\static\doctor_icon.ico"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"; Check: InstallRecepcion

Name: "{autodesktop}\Historia Clínica - Dr. Armando Revelo"; Filename: "C:\Historia Clinica Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Historia Clinica Dr Revelo\ABRIR_HISTORIA_CLINICA.py"""; WorkingDir: "C:\Historia Clinica Dr Revelo"; IconFilename: "C:\Historia Clinica Dr Revelo\static\doctor_icon.ico"; Comment: "Historia Clínica - Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.HistoriaClinica"; Check: InstallHistoria
Name: "{autoprograms}\Historia Clínica - Dr. Armando Revelo"; Filename: "C:\Historia Clinica Dr Revelo\.venv\Scripts\pythonw.exe"; Parameters: """C:\Historia Clinica Dr Revelo\ABRIR_HISTORIA_CLINICA.py"""; WorkingDir: "C:\Historia Clinica Dr Revelo"; IconFilename: "C:\Historia Clinica Dr Revelo\static\doctor_icon.ico"; Comment: "Historia Clínica - Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.HistoriaClinica"; Check: InstallHistoria

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Preparando WebView2 para los programas del consultorio..."; Flags: waituntilterminated; Check: InstallAnyAndNeedWebView2
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
begin
  ModePage := CreateInputOptionPage(
    wpWelcome,
    '¿Qué deseas instalar?',
    'Selecciona la computadora que estás preparando',
    'El mismo instalador sirve para Recepción, Historia Clínica o una PC que necesite ambos programas.',
    True,
    False
  );
  ModePage.Add('Recepción');
  ModePage.Add('Historia Clínica');
  ModePage.Add('Ambos programas');
  ModePage.SelectedValueIndex := 0;

  PrivacyLabel := TNewStaticText.Create(ModePage.Surface);
  PrivacyLabel.Parent := ModePage.Surface;
  PrivacyLabel.Top := ScaleY(190);
  PrivacyLabel.Left := 0;
  PrivacyLabel.Width := ModePage.Surface.Width;
  PrivacyLabel.AutoSize := False;
  PrivacyLabel.Height := ScaleY(58);
  PrivacyLabel.WordWrap := True;
  PrivacyLabel.Caption :=
    'Este instalador contiene configuración privada del consultorio. No incluye bases de pacientes ni historias clínicas. ' +
    'Si ya existe un .env o una carpeta data, se conservan.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ModePage.ID then
  begin
    if ModePage.SelectedValueIndex < 0 then
    begin
      MsgBox('Selecciona Recepción, Historia Clínica o Ambos programas.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if InstallRecepcion() and
       (not FileExists('C:\Recepcion Dr Revelo\ABRIR_RECEPCION.py')) then
      MsgBox('Recepción no pasó la verificación final. Vuelve a ejecutar el instalador.', mbError, MB_OK);

    if InstallHistoria() and
       (not FileExists('C:\Historia Clinica Dr Revelo\ABRIR_HISTORIA_CLINICA.py')) then
      MsgBox('Historia Clínica no pasó la verificación final. Vuelve a ejecutar el instalador.', mbError, MB_OK);
  end;
end;

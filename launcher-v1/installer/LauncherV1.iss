#define MyAppName "Launcher Recepción - Dr. Armando Revelo"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{7FC67E72-0B38-44B6-B79B-4E5D6EF00A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\Recepcion Dr Revelo
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=build\doctor_icon.ico
Uninstallable=no
CloseApplications=yes
RestartApplications=no
CreateAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Files]
Source: "build\RecepcionLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\Desinstalar_Recepcion_Dr_Revelo.exe"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{app}\ABRIR_RECEPCION.py"
Type: files; Name: "{app}\ABRIR_RECEPCION.pyw"
Type: files; Name: "{app}\__pycache__\ABRIR_RECEPCION*.pyc"
Type: files; Name: "{app}\data\launcher_errors.log"

[Icons]
Name: "{autodesktop}\Recepción Dr. Armando Revelo"; Filename: "{app}\RecepcionLauncher.exe"; WorkingDir: "{app}"; IconFilename: "{app}\RecepcionLauncher.exe"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"
Name: "{autoprograms}\Recepción Dr. Armando Revelo"; Filename: "{app}\RecepcionLauncher.exe"; WorkingDir: "{app}"; IconFilename: "{app}\RecepcionLauncher.exe"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"
Name: "{autoprograms}\Desinstalar Recepción Dr. Armando Revelo"; Filename: "{app}\Desinstalar_Recepcion_Dr_Revelo.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Desinstalar_Recepcion_Dr_Revelo.exe"

[Run]
Filename: "{app}\RecepcionLauncher.exe"; WorkingDir: "{app}"; Description: "Abrir Recepción"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not FileExists('C:\Recepcion Dr Revelo\app.py') then
  begin
    MsgBox(
      'No encontré una instalación existente de Recepción en C:\Recepcion Dr Revelo.' + #13#10 + #13#10 +
      'Este instalador cambia únicamente el sistema de arranque. No instala la base completa de Recepción.',
      mbError, MB_OK
    );
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    { El launcher nuevo sustituye completamente el acceso directo anterior.
      No se toca app.py, .env, data, bases, Excel ni historias. }
  end;
end;

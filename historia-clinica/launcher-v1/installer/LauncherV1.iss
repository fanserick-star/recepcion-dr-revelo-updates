#define MyAppName "Launcher Historia Clínica - Dr. Armando Revelo"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{B12A6B75-92E4-4D69-8DB7-2B52FD391B25}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\Historia Clinica Dr Revelo
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_0
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
Source: "build\HistoriaClinicaLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\Desinstalar_Historia_Clinica_Dr_Revelo.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\HistoriaLauncherUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Historia Clínica - Dr. Armando Revelo"; Filename: "{app}\HistoriaClinicaLauncher.exe"; WorkingDir: "{app}"; IconFilename: "{app}\HistoriaClinicaLauncher.exe"; Comment: "Historia Clínica - Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.HistoriaClinica"
Name: "{autoprograms}\Historia Clínica - Dr. Armando Revelo"; Filename: "{app}\HistoriaClinicaLauncher.exe"; WorkingDir: "{app}"; IconFilename: "{app}\HistoriaClinicaLauncher.exe"; Comment: "Historia Clínica - Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.HistoriaClinica"
Name: "{autoprograms}\Desinstalar Historia Clínica - Dr. Armando Revelo"; Filename: "{app}\Desinstalar_Historia_Clinica_Dr_Revelo.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Desinstalar_Historia_Clinica_Dr_Revelo.exe"

[Run]
Filename: "{app}\HistoriaClinicaLauncher.exe"; WorkingDir: "{app}"; Description: "Abrir Historia Clínica"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not FileExists('C:\Historia Clinica Dr Revelo\app.py') then
  begin
    MsgBox(
      'No encontré una instalación existente de Historia Clínica en C:\Historia Clinica Dr Revelo.' + #13#10 + #13#10 +
      'Este instalador cambia únicamente el sistema de arranque. No instala la base completa de Historia Clínica.',
      mbError, MB_OK
    );
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Los EXE nuevos ya fueron copiados antes de retirar el launcher Python. }
    DeleteFile(ExpandConstant('{app}\ABRIR_HISTORIA_CLINICA.py'));
    DeleteFile(ExpandConstant('{app}\ABRIR_HISTORIA_CLINICA.pyw'));
    DeleteFile(ExpandConstant('{app}\INICIAR.bat'));
    DeleteFile(ExpandConstant('{app}\data\launcher.log'));
    DeleteFile(ExpandConstant('{app}\data\launcher_state.json'));
    DelTree(ExpandConstant('{app}\__pycache__\ABRIR_HISTORIA_CLINICA*.pyc'), False, True, False);
  end;
end;

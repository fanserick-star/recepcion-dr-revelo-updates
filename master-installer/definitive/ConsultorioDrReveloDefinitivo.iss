#define MyAppName "Consultorio Dr. Armando Revelo - Instalador definitivo"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{53F8683A-C4E8-40A5-B5F8-C1CA8310F6E7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={tmp}\ConsultorioDrReveloDefinitivo
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_CONSULTORIO_DR_REVELO_BASE
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=build\consultorio_icon.ico
Uninstallable=no
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Types]
Name: "custom"; Description: "Seleccionar programas"; Flags: iscustom

[Components]
Name: "recepcion"; Description: "Recepción"; Types: custom
Name: "historia"; Description: "Historia Clínica"; Types: custom

[Files]
Source: "bootstrap.ps1"; DestDir: "{tmp}\DrReveloDefinitive"; Flags: deleteafterinstall
Source: "requirements-recepcion.txt"; DestDir: "{tmp}\DrReveloDefinitive"; Flags: deleteafterinstall
Source: "build\requirements-historia.txt"; DestDir: "{tmp}\DrReveloDefinitive"; Flags: deleteafterinstall
Source: "build\python-3.11.9-amd64.exe"; DestDir: "{tmp}\DrReveloDefinitive"; Flags: deleteafterinstall
Source: "build\wheelhouse\*"; DestDir: "{tmp}\DrReveloDefinitive\wheelhouse"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "build\payload\recepcion\*"; DestDir: "{tmp}\DrReveloDefinitive\payload\recepcion"; Flags: recursesubdirs createallsubdirs deleteafterinstall; Components: recepcion
Source: "build\payload\historia\*"; DestDir: "{tmp}\DrReveloDefinitive\payload\historia"; Flags: recursesubdirs createallsubdirs deleteafterinstall; Components: historia
Source: "build\INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe"; DestDir: "{tmp}\DrReveloDefinitive"; Flags: deleteafterinstall; Components: recepcion
Source: "build\INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe"; DestDir: "{tmp}\DrReveloDefinitive"; Flags: deleteafterinstall; Components: historia

[Code]
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectComponents then
  begin
    WizardForm.SelectComponentsLabel.Caption :=
      'Elige qué quieres dejar listo en esta PC. Puedes instalar Recepción, Historia Clínica o ambas. Los datos existentes se respaldan y conservan.';
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectComponents then
  begin
    if (not WizardIsComponentSelected('recepcion')) and
       (not WizardIsComponentSelected('historia')) then
    begin
      MsgBox('Selecciona Recepción, Historia Clínica o ambas.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PowerShellPath: String;
  ScriptPath: String;
  Args: String;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
    ScriptPath := ExpandConstant('{tmp}\DrReveloDefinitive\bootstrap.ps1');
    Args := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptPath + '"' +
      ' -SourceInstaller "' + ExpandConstant('{srcexe}') + '"' +
      ' -StageRoot "' + ExpandConstant('{tmp}\DrReveloDefinitive') + '"';

    if WizardIsComponentSelected('recepcion') then
      Args := Args + ' -Reception';
    if WizardIsComponentSelected('historia') then
      Args := Args + ' -Historia';

    WizardForm.StatusLabel.Caption := 'Preparando el consultorio. Esto puede tardar unos minutos...';
    if not Exec(PowerShellPath, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      RaiseException('No se pudo iniciar el preparador del consultorio.');

    if ResultCode <> 0 then
      RaiseException(
        'La instalación no pudo completarse. Se restauró la instalación anterior cuando correspondía. ' +
        'Código: ' + IntToStr(ResultCode) + '. Revisa C:\ProgramData\ConsultorioDrRevelo\InstallerLogs.'
      );
  end;
end;

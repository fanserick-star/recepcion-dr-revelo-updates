#define MyAppName "Consultorio Dr. Armando Revelo"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{9C558A25-9BEF-4D54-A1A1-7F70D88DF901}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={tmp}\ConsultorioDrReveloSetup
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_CONSULTORIO_DR_REVELO
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
Source: "bootstrap.ps1"; DestDir: "{tmp}\DrReveloMaster"; Flags: deleteafterinstall

[Code]
function BootstrapArguments(): String;
begin
  Result := '';
  if WizardIsComponentSelected('recepcion') then
    Result := Result + ' -Reception';
  if WizardIsComponentSelected('historia') then
    Result := Result + ' -Historia';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectComponents then
  begin
    if (not WizardIsComponentSelected('recepcion')) and
       (not WizardIsComponentSelected('historia')) then
    begin
      MsgBox('Selecciona Recepción, Historia Clínica o ambos.', mbInformation, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectComponents then
  begin
    WizardForm.SelectComponentsLabel.Caption :=
      'Elige qué programa quieres instalar o reparar. El instalador descargará la versión oficial vigente y conservará datos y configuración privada existentes.';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PowerShell: String;
  ScriptPath: String;
  Params: String;
  ResultCode: Integer;
  Ok: Boolean;
begin
  if CurStep = ssPostInstall then
  begin
    PowerShell := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
    ScriptPath := ExpandConstant('{tmp}\DrReveloMaster\bootstrap.ps1');
    Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptPath + '"' + BootstrapArguments();

    WizardForm.StatusLabel.Caption := 'Preparando el sistema completo. Se verificarán descargas y dependencias...';
    Ok := Exec(PowerShell, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if (not Ok) or (ResultCode <> 0) then
    begin
      RaiseException(
        'No se pudo completar la instalación limpia.' + #13#10 +
        'No se reemplazaron las bases de datos ni la configuración privada existente.' + #13#10 +
        'Revise el registro en C:\ProgramData\DrReveloRuntime\logs.'
      );
    end;
  end;
end;

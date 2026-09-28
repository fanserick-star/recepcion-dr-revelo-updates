#define MyAppName "Consultorio Dr. Armando Revelo - Instalador"
#define MyAppVersion "3.0.1"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{53F8683A-C4E8-40A5-B5F8-C1CA8310F6E7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={tmp}\ConsultorioDrReveloBootstrap
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_CONSULTORIO_DR_REVELO_BASE_LIVIANO
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
; El EXE deliberadamente NO incluye Python, wheelhouse, aplicaciones ni launchers.
; Todo lo pesado se descarga, valida y prepara sólo cuando hace falta.
Source: "build\bootstrap.generated.ps1"; DestDir: "{tmp}\DrReveloBootstrap"; DestName: "bootstrap.ps1"; Flags: deleteafterinstall

[Code]
var
  InstallerExitCode: Integer;

function GetCustomSetupExitCode: Integer;
begin
  Result := InstallerExitCode;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectComponents then
  begin
    WizardForm.SelectComponentsLabel.Caption :=
      'Elige qué quieres instalar: Recepción, Historia Clínica o ambas. El instalador descargará sólo lo necesario y conservará los datos existentes.';
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
  CommandText: String;
  Args: String;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
    ScriptPath := ExpandConstant('{tmp}\DrReveloBootstrap\bootstrap.ps1');

    ; Windows limpio puede tener deshabilitada la autocarga de módulos. Importamos
    ; explícitamente Microsoft.PowerShell.Utility antes de ejecutar el bootstrap,
    ; para que Get-FileHash/Get-AuthenticodeSignature estén siempre disponibles.
    CommandText := "Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop; & '" + ScriptPath + "'" +
      " -SourceInstaller '" + ExpandConstant('{srcexe}') + "'" +
      " -StageRoot '" + ExpandConstant('{tmp}\DrReveloBootstrap') + "'";

    if WizardIsComponentSelected('recepcion') then
      CommandText := CommandText + ' -Reception';
    if WizardIsComponentSelected('historia') then
      CommandText := CommandText + ' -Historia';
    CommandText := CommandText + '; exit $LASTEXITCODE';

    Args := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' + CommandText + '"';

    WizardForm.StatusLabel.Caption := 'Descargando y preparando únicamente lo necesario...';
    if not Exec(PowerShellPath, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      InstallerExitCode := 51;
      RaiseException('No se pudo iniciar el preparador del consultorio.');
    end;

    if ResultCode <> 0 then
    begin
      InstallerExitCode := 100 + ResultCode;
      RaiseException(
        'La instalación no pudo completarse. Se restauró la instalación anterior cuando correspondía. ' +
        'Código: ' + IntToStr(ResultCode) + '. Revisa C:\ProgramData\ConsultorioDrRevelo\InstallerLogs.'
      );
    end;
  end;
end;

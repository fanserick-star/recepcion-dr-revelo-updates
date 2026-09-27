#define MyAppName "Historia Clínica Dr. Armando Revelo"
#define MyAppVersion "1.3.73"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"
#define PythonRuntime GetEnv("pythonLocation")

[Setup]
AppId={{99B40218-3A71-44F4-9AB1-75663F14E2D4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Consultorio Dr Revelo\Historia Clinica
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_HISTORIA_CLINICA_DR_REVELO_1_3_73
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=build\consultorio_icon.ico
Uninstallable=yes
UninstallDisplayName=Historia Clínica Dr. Armando Revelo
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Files]
Source: "install-child.ps1"; DestDir: "{tmp}\DrReveloHistoria"; Flags: deleteafterinstall
Source: "{#PythonRuntime}\*"; DestDir: "{tmp}\DrReveloHistoria\python-runtime"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "build\wheelhouse\*"; DestDir: "{tmp}\DrReveloHistoria\wheelhouse"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "build\historia\requirements.txt"; DestDir: "{tmp}\DrReveloHistoria"; DestName: "requirements.txt"; Flags: deleteafterinstall
Source: "build\historia\payload\*"; DestDir: "{tmp}\DrReveloHistoria\payload"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "build\historia\launcher-setup.exe"; DestDir: "{tmp}\DrReveloHistoria"; DestName: "launcher-setup.exe"; Flags: deleteafterinstall
Source: "uninstall-child.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\historia\managed-files.txt"; DestDir: "{app}"; Flags: ignoreversion

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\uninstall-child.ps1"" -App Historia -ManifestPath ""{app}\managed-files.txt"""; Flags: runhidden waituntilterminated; RunOnceId: "HistoriaCleanup"

[Code]
var
  InstallerExitCode: Integer;

function GetCustomSetupExitCode: Integer;
begin
  Result := InstallerExitCode;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PS, ScriptPath, Args: String;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    PS := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
    ScriptPath := ExpandConstant('{tmp}\DrReveloHistoria\install-child.ps1');
    Args := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptPath + '"' +
      ' -App Historia' +
      ' -StageRoot "' + ExpandConstant('{tmp}\DrReveloHistoria') + '"' +
      ' -SourceDir "' + ExpandConstant('{src}') + '"';
    WizardForm.StatusLabel.Caption := 'Instalando Historia Clínica 1.3.73...';
    if not Exec(PS, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      InstallerExitCode := 51;
      RaiseException('No se pudo iniciar el instalador de Historia Clínica.');
    end;
    if ResultCode <> 0 then
    begin
      InstallerExitCode := 100 + ResultCode;
      RaiseException('Historia Clínica no pudo instalarse. La versión anterior fue restaurada. Código: ' + IntToStr(ResultCode));
    end;
  end;
end;

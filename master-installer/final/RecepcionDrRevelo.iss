#define MyAppName "Recepción Dr. Armando Revelo"
#define MyAppVersion "4.6.7"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"
#define PythonRuntime GetEnv("pythonLocation")

[Setup]
AppId={{2D7B7444-D35B-4A28-A02A-54D01CD927A1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Consultorio Dr Revelo\Recepcion
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_RECEPCION_DR_REVELO_4_6_7
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=build\consultorio_icon.ico
Uninstallable=yes
UninstallDisplayName=Recepción Dr. Armando Revelo
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Files]
Source: "install-child.ps1"; DestDir: "{tmp}\DrReveloReception"; Flags: deleteafterinstall
Source: "{#PythonRuntime}\*"; DestDir: "{tmp}\DrReveloReception\python-runtime"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "build\wheelhouse\*"; DestDir: "{tmp}\DrReveloReception\wheelhouse"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "build\reception\requirements.txt"; DestDir: "{tmp}\DrReveloReception"; DestName: "requirements.txt"; Flags: deleteafterinstall
Source: "build\reception\payload\*"; DestDir: "{tmp}\DrReveloReception\payload"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "build\reception\launcher-setup.exe"; DestDir: "{tmp}\DrReveloReception"; DestName: "launcher-setup.exe"; Flags: deleteafterinstall
Source: "uninstall-child.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\reception\managed-files.txt"; DestDir: "{app}"; Flags: ignoreversion

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\uninstall-child.ps1"" -App Reception -ManifestPath ""{app}\managed-files.txt"""; Flags: runhidden waituntilterminated; RunOnceId: "ReceptionCleanup"

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
    ScriptPath := ExpandConstant('{tmp}\DrReveloReception\install-child.ps1');
    Args := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptPath + '"' +
      ' -App Reception' +
      ' -StageRoot "' + ExpandConstant('{tmp}\DrReveloReception') + '"' +
      ' -SourceDir "' + ExpandConstant('{src}') + '"';
    WizardForm.StatusLabel.Caption := 'Instalando Recepción 4.6.7...';
    if not Exec(PS, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      InstallerExitCode := 51;
      RaiseException('No se pudo iniciar el instalador de Recepción.');
    end;
    if ResultCode <> 0 then
    begin
      InstallerExitCode := 100 + ResultCode;
      RaiseException('Recepción no pudo instalarse. La versión anterior fue restaurada. Código: ' + IntToStr(ResultCode));
    end;
  end;
end;

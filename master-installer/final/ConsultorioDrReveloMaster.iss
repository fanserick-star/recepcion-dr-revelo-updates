#define MyAppName "Consultorio Dr. Armando Revelo - Instalador Maestro"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

; Consolidated installer build trigger: validated child runtimes and clean-install pipeline. Rebuild authorized 2026-09-27.

[Setup]
AppId={{93BC75C3-A37F-4E24-B4FC-F5B1F45C63B0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={tmp}\ConsultorioDrReveloMaster
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_CONSULTORIO_DR_REVELO_MAESTRO
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=build\consultorio_icon.ico
Uninstallable=no
CreateAppDir=no
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Types]
Name: "full"; Description: "Recepción + Historia Clínica"
Name: "reception"; Description: "Solo Recepción"
Name: "history"; Description: "Solo Historia Clínica"
Name: "custom"; Description: "Personalizado"; Flags: iscustom

[Components]
Name: "recepcion"; Description: "Recepción 4.6.7"; Types: full reception custom
Name: "historia"; Description: "Historia Clínica 1.3.73"; Types: full history custom

[Files]
Source: "output\INSTALAR_RECEPCION_DR_REVELO_4_6_7.exe"; DestDir: "{tmp}\DrReveloMaster"; Flags: deleteafterinstall
Source: "output\INSTALAR_HISTORIA_CLINICA_DR_REVELO_1_3_73.exe"; DestDir: "{tmp}\DrReveloMaster"; Flags: deleteafterinstall

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
    WizardForm.SelectComponentsLabel.Caption :=
      'Elige qué instalar en esta PC. Recepción e Historia Clínica quedan como programas independientes y cada uno tendrá su propio desinstalador.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectComponents then
  begin
    if (not WizardIsComponentSelected('recepcion')) and (not WizardIsComponentSelected('historia')) then
    begin
      MsgBox('Selecciona Recepción, Historia Clínica o ambas.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure RunChild(const FileName, FriendlyName: String);
var
  Code: Integer;
begin
  WizardForm.StatusLabel.Caption := 'Instalando ' + FriendlyName + '...';
  if not Exec(FileName, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-', ExpandConstant('{tmp}\DrReveloMaster'), SW_HIDE, ewWaitUntilTerminated, Code) then
  begin
    InstallerExitCode := 51;
    RaiseException('No se pudo iniciar ' + FriendlyName + '.');
  end;
  if Code <> 0 then
  begin
    InstallerExitCode := 100 + Code;
    RaiseException(FriendlyName + ' no pudo instalarse. Código: ' + IntToStr(Code) + '.');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  SidecarSrc, SidecarDst: String;
begin
  if CurStep = ssPostInstall then
  begin
    SidecarSrc := ExpandConstant('{src}\consultorio.private.env');
    SidecarDst := ExpandConstant('{tmp}\DrReveloMaster\consultorio.private.env');
    if FileExists(SidecarSrc) then
      FileCopy(SidecarSrc, SidecarDst, False);

    if WizardIsComponentSelected('recepcion') then
      RunChild(ExpandConstant('{tmp}\DrReveloMaster\INSTALAR_RECEPCION_DR_REVELO_4_6_7.exe'), 'Recepción 4.6.7');
    if WizardIsComponentSelected('historia') then
      RunChild(ExpandConstant('{tmp}\DrReveloMaster\INSTALAR_HISTORIA_CLINICA_DR_REVELO_1_3_73.exe'), 'Historia Clínica 1.3.73');
  end;
end;

#define MyAppName "Consultorio Dr. Armando Revelo"
#define MyAppVersion "2.1.0"
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
Source: "provision.ps1"; DestDir: "{tmp}\DrReveloMaster"; Flags: deleteafterinstall
Source: "private-config.bundle.json"; DestDir: "{tmp}\DrReveloMaster"; Flags: deleteafterinstall

[Code]
var
  ActivationPage: TInputQueryWizardPage;

function SkipProvisioning(): Boolean;
begin
  Result := ExpandConstant('{param:SKIPPROVISIONING|0}') = '1';
end;

function BootstrapArguments(): String;
begin
  Result := '';
  if WizardIsComponentSelected('recepcion') then
    Result := Result + ' -Reception';
  if WizardIsComponentSelected('historia') then
    Result := Result + ' -Historia';
end;

procedure InitializeWizard();
begin
  ActivationPage := CreateInputQueryPage(
    wpSelectComponents,
    'Activación del consultorio',
    'Configuración privada automática',
    'Ingrese el código privado del consultorio. Se usa una sola vez para configurar Neon y las integraciones sin pedir archivos .env ni claves API.'
  );
  ActivationPage.Add('Código de activación:', True);
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

  if (CurPageID = ActivationPage.ID) and (not SkipProvisioning()) then
  begin
    if Length(Trim(ActivationPage.Values[0])) < 20 then
    begin
      MsgBox('El código de activación no es válido.', mbInformation, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectComponents then
  begin
    WizardForm.SelectComponentsLabel.Caption :=
      'Elige qué programa quieres instalar o reparar. El instalador descargará la versión oficial vigente y conservará pacientes, bases y archivos de trabajo.';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PowerShell: String;
  ScriptPath: String;
  ProvisionPath: String;
  BundlePath: String;
  ActivationPath: String;
  Params: String;
  ResultCode: Integer;
  Ok: Boolean;
begin
  if CurStep = ssPostInstall then
  begin
    PowerShell := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
    ScriptPath := ExpandConstant('{tmp}\DrReveloMaster\bootstrap.ps1');
    Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptPath + '"' + BootstrapArguments();

    WizardForm.StatusLabel.Caption := 'Instalando las versiones oficiales vigentes...';
    Ok := Exec(PowerShell, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if (not Ok) or (ResultCode <> 0) then
    begin
      RaiseException(
        'No se pudo completar la instalación limpia.' + #13#10 +
        'No se reemplazaron las bases de datos ni la configuración privada existente.' + #13#10 +
        'Revise el registro en C:\ProgramData\DrReveloRuntime\logs.'
      );
    end;

    if SkipProvisioning() then
      Exit;

    ProvisionPath := ExpandConstant('{tmp}\DrReveloMaster\provision.ps1');
    BundlePath := ExpandConstant('{tmp}\DrReveloMaster\private-config.bundle.json');
    ActivationPath := ExpandConstant('{tmp}\DrReveloMaster\activation.txt');

    if not SaveStringToFile(ActivationPath, Trim(ActivationPage.Values[0]), False) then
      RaiseException('No se pudo preparar la activación privada.');

    WizardForm.StatusLabel.Caption := 'Configurando y verificando conexiones privadas...';
    Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ProvisionPath + '"' +
      BootstrapArguments() +
      ' -ActivationFile "' + ActivationPath + '"' +
      ' -BundlePath "' + BundlePath + '"';

    Ok := Exec(PowerShell, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    DeleteFile(ActivationPath);
    ActivationPage.Values[0] := '';

    if (not Ok) or (ResultCode <> 0) then
    begin
      RaiseException(
        'Los programas fueron instalados, pero la configuración privada no pudo validarse.' + #13#10 +
        'No se mostraron ni publicaron sus claves.' + #13#10 +
        'Revise el registro en C:\ProgramData\DrReveloRuntime\logs y vuelva a ejecutar el instalador.'
      );
    end;

    WizardForm.StatusLabel.Caption := 'Programas y conexiones verificados correctamente.';
  end;
end;

#define MyAppName "Recepción Dr. Armando Revelo"
#define MyAppVersion "4.3.72"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{D4FA842E-B57A-4820-A5A6-0E459AA795E4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\Recepcion Dr Revelo
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_RECEPCION_DR_REVELO_DESDE_CERO
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=build\recepcion.ico
Uninstallable=no
CloseApplications=yes
RestartApplications=no
CreateAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Dirs]
Name: "{app}"; Permissions: users-modify
Name: "{app}\data"; Permissions: users-modify

[Files]
Source: "buildroot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Recepción Dr. Armando Revelo"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\ABRIR_RECEPCION.py"""; WorkingDir: "{app}"; IconFilename: "{app}\recepcion.ico"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"
Name: "{autoprograms}\Recepción Dr. Armando Revelo"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\ABRIR_RECEPCION.py"""; WorkingDir: "{app}"; IconFilename: "{app}\recepcion.ico"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"

[Run]
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\ABRIR_RECEPCION.py"""; WorkingDir: "{app}"; Description: "Abrir Recepción Dr. Armando Revelo"; Flags: nowait postinstall skipifsilent

[Code]
var
  BackupPage: TInputFileWizardPage;

function AutoBackupPath(): String;
var
  P: String;
begin
  Result := '';
  P := ExpandConstant('{src}\RESPALDO_RECEPCION_SSD.zip');
  if FileExists(P) then begin Result := P; exit; end;
  P := ExpandConstant('{src}\.env');
  if FileExists(P) then begin Result := P; exit; end;
  P := ExpandConstant('{src}\CONFIG_RECEPCION.env');
  if FileExists(P) then begin Result := P; exit; end;
end;

procedure InitializeWizard();
var
  AutoPath: String;
begin
  BackupPage := CreateInputFilePage(
    wpSelectDir,
    'Restaurar configuración anterior (opcional)',
    '¿Tienes un respaldo de la PC anterior?',
    'Si vas a cambiar el SSD, selecciona RESPALDO_RECEPCION_SSD.zip o el archivo .env guardado antes del cambio. Puedes dejarlo vacío para una instalación completamente nueva.'
  );
  BackupPage.Add('Respaldo o .env:', 'Respaldo de Recepción (*.zip;*.env)|*.zip;*.env|Todos los archivos (*.*)|*.*', '.zip');
  AutoPath := AutoBackupPath();
  if AutoPath <> '' then BackupPage.Values[0] := AutoPath;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  P, E: String;
begin
  Result := True;
  if CurPageID = BackupPage.ID then
  begin
    P := Trim(BackupPage.Values[0]);
    if P <> '' then
    begin
      if not FileExists(P) then
      begin
        MsgBox('El archivo de respaldo seleccionado no existe.', mbError, MB_OK);
        Result := False;
        exit;
      end;
      E := Lowercase(ExtractFileExt(P));
      if (E <> '.zip') and (E <> '.env') then
      begin
        MsgBox('Selecciona un respaldo ZIP o un archivo .env.', mbError, MB_OK);
        Result := False;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  P, Params: String;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not FileExists(ExpandConstant('{app}\.env')) then
      FileCopy(ExpandConstant('{app}\.env.example'), ExpandConstant('{app}\.env'), False);

    P := Trim(BackupPage.Values[0]);
    if P <> '' then
    begin
      Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\restore_config.ps1') +
                '" -Source "' + P + '" -Destination "' + ExpandConstant('{app}') + '"';
      if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        MsgBox('Recepción se instaló, pero Windows no pudo iniciar la restauración del respaldo.', mbError, MB_OK)
      else if ResultCode <> 0 then
        MsgBox('Recepción se instaló, pero el respaldo no pudo restaurarse. El archivo original no fue modificado.', mbError, MB_OK);
    end;
  end;
end;

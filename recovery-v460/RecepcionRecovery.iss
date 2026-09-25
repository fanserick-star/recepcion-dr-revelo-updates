#define MyAppName "Recepción Dr. Armando Revelo - Recuperación"
#define MyAppVersion "4.6.0"
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
OutputBaseFilename=INSTALAR_RECEPCION_DR_REVELO_RECUPERACION_V4_6_0
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=buildroot\static\doctor_icon.ico
CloseApplications=yes
RestartApplications=no
CreateAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Uninstallable=no
SetupLogging=yes

[Dirs]
Name: "{app}"; Permissions: users-modify
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\tools"; Permissions: users-modify

[Files]
Source: "buildroot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Recepción Dr. Armando Revelo"; Filename: "{app}\RecepcionLauncher.exe"; WorkingDir: "{app}"; IconFilename: "{app}\RecepcionLauncher.exe"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"
Name: "{autoprograms}\Recepción Dr. Armando Revelo"; Filename: "{app}\RecepcionLauncher.exe"; WorkingDir: "{app}"; IconFilename: "{app}\RecepcionLauncher.exe"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"
Name: "{autoprograms}\Crear respaldo privado de Recepción"; Filename: "{app}\.venv\Scripts\python.exe"; Parameters: """{app}\tools\backup_private.py"" --root ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\RecepcionLauncher.exe"

[Run]
Filename: "{app}\RecepcionLauncher.exe"; WorkingDir: "{app}"; Description: "Abrir Recepción"; Flags: nowait postinstall skipifsilent

[Code]
var
  BackupPage: TInputFileWizardPage;

function AutoBackupPath(): String;
var
  P: String;
begin
  Result := '';
  P := ExpandConstant('{src}\RESPALDO_PRIVADO_RECEPCION.zip');
  if FileExists(P) then begin Result := P; exit; end;
  P := ExpandConstant('{src}\RESPALDO_RECEPCION_SSD.zip');
  if FileExists(P) then begin Result := P; exit; end;
  P := ExpandConstant('{src}\.env');
  if FileExists(P) then begin Result := P; exit; end;
end;

procedure InitializeWizard();
var
  AutoPath: String;
begin
  BackupPage := CreateInputFilePage(
    wpSelectDir,
    'Restaurar datos privados (opcional)',
    '¿Tienes un respaldo privado de Recepción?',
    'Puedes seleccionar RESPALDO_PRIVADO_RECEPCION_*.zip o un .env. El instalador del programa nunca contiene pacientes ni credenciales.'
  );
  BackupPage.Add(
    'Respaldo privado:',
    'Respaldo de Recepción (*.zip;*.env)|*.zip;*.env|Todos los archivos (*.*)|*.*',
    '.zip'
  );
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
  P, Py, Params: String;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not FileExists(ExpandConstant('{app}\.env')) then
      FileCopy(ExpandConstant('{app}\.env.example'), ExpandConstant('{app}\.env'), False);

    P := Trim(BackupPage.Values[0]);
    if P <> '' then
    begin
      Py := ExpandConstant('{app}\.venv\Scripts\python.exe');
      Params := '"' + ExpandConstant('{app}\tools\restore_private.py') +
                '" --source "' + P + '" --root "' + ExpandConstant('{app}') + '"';
      if not Exec(Py, Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        MsgBox('Recepción se instaló, pero Windows no pudo iniciar la restauración.', mbError, MB_OK)
      else if ResultCode <> 0 then
        MsgBox('Recepción se instaló, pero el respaldo no pudo restaurarse. Los datos anteriores se conservaron en la copia de seguridad previa si existían.', mbError, MB_OK);
    end;
  end;
end;

#define MyAppName "Recepción Dr. Armando Revelo"
#define MyAppVersion "1.0"
#define MyAppPublisher "Consultorio Dr. Armando Revelo"

[Setup]
AppId={{A6DCC6EE-0BD1-4F30-9BCA-0A15D6CE8E72}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\Recepcion Dr Revelo
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern
OutputDir=output
OutputBaseFilename=INSTALAR_RECEPCION_DR_REVELO
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=build\recepcion.ico
Uninstallable=no
CloseApplications=yes
RestartApplications=no
CreateAppDir=yes

[Files]
Source: "migrate_install.ps1"; Flags: dontcopy
Source: "build\recepcion.ico"; DestDir: "{app}"; DestName: "recepcion.ico"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Recepción Dr. Armando Revelo"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\ABRIR_RECEPCION.py"""; WorkingDir: "{app}"; IconFilename: "{app}\recepcion.ico"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"
Name: "{autoprograms}\Recepción Dr. Armando Revelo"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\ABRIR_RECEPCION.py"""; WorkingDir: "{app}"; IconFilename: "{app}\recepcion.ico"; Comment: "Recepción Dr. Armando Revelo"; AppUserModelID: "DrArmandoRevelo.Recepcion"

[Run]
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\ABRIR_RECEPCION.py"""; WorkingDir: "{app}"; Description: "Abrir Recepción Dr. Armando Revelo"; Flags: nowait postinstall skipifsilent

[Code]
var
  SourcePage: TInputDirWizardPage;

function IsReceptionFolder(const P: String): Boolean;
begin
  Result := FileExists(AddBackslash(P) + 'ABRIR_RECEPCION.py') and
            FileExists(AddBackslash(P) + 'app.py') and
            FileExists(AddBackslash(P) + '.venv\Scripts\pythonw.exe');
end;

function ScanOneLevel(const Base: String): String;
var
  F: TFindRec;
  P: String;
begin
  Result := '';
  if IsReceptionFolder(Base) then
  begin
    Result := Base;
    exit;
  end;
  if not DirExists(Base) then exit;
  if FindFirst(AddBackslash(Base) + '*', F) then
  begin
    try
      repeat
        if ((F.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and
           (F.Name <> '.') and (F.Name <> '..') then
        begin
          P := AddBackslash(Base) + F.Name;
          if IsReceptionFolder(P) then
          begin
            Result := P;
            exit;
          end;
        end;
      until not FindNext(F);
    finally
      FindClose(F);
    end;
  end;
end;

function DetectExistingInstall(): String;
var
  P: String;
begin
  Result := '';
  P := ScanOneLevel(ExpandConstant('{userdesktop}'));
  if P <> '' then begin Result := P; exit; end;
  P := ScanOneLevel(ExpandConstant('{userprofile}\OneDrive\Desktop'));
  if P <> '' then begin Result := P; exit; end;
  if IsReceptionFolder('C:\Recepcion Dr Revelo') then
    Result := 'C:\Recepcion Dr Revelo';
end;

procedure InitializeWizard();
var
  Detected: String;
begin
  SourcePage := CreateInputDirPage(
    wpWelcome,
    'Ubicación actual de Recepción',
    'Selecciona la carpeta que hoy contiene el programa',
    'El instalador moverá la instalación completa a C:\Recepcion Dr Revelo y conservará configuración, datos y actualizaciones. Selecciona la carpeta que contiene ABRIR_RECEPCION.py.'
  );
  SourcePage.Add('');
  Detected := DetectExistingInstall();
  if Detected <> '' then
    SourcePage.Values[0] := Detected
  else
    SourcePage.Values[0] := ExpandConstant('{userdesktop}');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = SourcePage.ID then
  begin
    if not IsReceptionFolder(SourcePage.Values[0]) then
    begin
      MsgBox('Esa carpeta no contiene una instalación válida de Recepción. Selecciona la carpeta donde están ABRIR_RECEPCION.py, app.py y .venv.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  ScriptPath, Params: String;
begin
  Result := '';
  ExtractTemporaryFile('migrate_install.ps1');
  ScriptPath := ExpandConstant('{tmp}\migrate_install.ps1');
  Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '" -Source "' +
            SourcePage.Values[0] + '" -Destination "' + ExpandConstant('{app}') + '"';

  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'No se pudo iniciar la migración de Recepción.';
    exit;
  end;

  if ResultCode <> 0 then
  begin
    Result := 'No se pudo mover Recepción a C:. Verifica que el programa esté cerrado y que hayas seleccionado la carpeta correcta. La instalación anterior no se eliminará si la migración falla.';
    exit;
  end;

  if not IsReceptionFolder(ExpandConstant('{app}')) then
  begin
    Result := 'La verificación final no encontró todos los archivos de Recepción en C:. La instalación se detuvo por seguridad.';
  end;
end;

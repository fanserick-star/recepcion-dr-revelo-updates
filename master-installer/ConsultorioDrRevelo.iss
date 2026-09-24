#define MyAppName "Consultorio Dr. Armando Revelo"
#define MyAppVersion "1.0.0"
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
Source: "build\INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe"; DestDir: "{tmp}\DrReveloMaster"; Flags: deleteafterinstall; Components: recepcion
Source: "build\INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_7.exe"; DestDir: "{tmp}\DrReveloMaster"; Flags: deleteafterinstall; Components: historia

[Run]
Filename: "{tmp}\DrReveloMaster\INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-"; StatusMsg: "Actualizando Recepción y su launcher..."; Flags: waituntilterminated; Components: recepcion
Filename: "{tmp}\DrReveloMaster\INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_7.exe"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-"; StatusMsg: "Actualizando Historia Clínica y su launcher..."; Flags: waituntilterminated; Components: historia

[Code]
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Missing: String;
begin
  Result := True;
  if CurPageID = wpSelectComponents then
  begin
    Missing := '';
    if WizardIsComponentSelected('recepcion') and
       not FileExists('C:\Recepcion Dr Revelo\app.py') then
      Missing := Missing + '- Recepción no está instalada en C:\Recepcion Dr Revelo' + #13#10;

    if WizardIsComponentSelected('historia') and
       not FileExists('C:\Historia Clinica Dr Revelo\app.py') then
      Missing := Missing + '- Historia Clínica no está instalada en C:\Historia Clinica Dr Revelo' + #13#10;

    if Missing <> '' then
    begin
      MsgBox(
        'Este instalador maestro finaliza/actualiza instalaciones existentes sin tocar bases ni configuraciones privadas.' +
        #13#10 + #13#10 +
        'Falta una instalación base para:' + #13#10 + Missing +
        #13#10 +
        'No continuaré para evitar crear una instalación incompleta.',
        mbError, MB_OK
      );
      Result := False;
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectComponents then
  begin
    WizardForm.SelectComponentsLabel.Caption :=
      'Elige qué programa quieres preparar en esta PC. Puedes instalar uno o ambos.';
  end;
end;

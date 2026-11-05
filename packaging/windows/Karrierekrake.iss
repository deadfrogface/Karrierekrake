; Karrierekrake Windows installer (Inno Setup 6).
; Build:  ISCC /DAppVersion=Alpha-1.1 /DSourceDir=<folder with Karrierekrake.exe and _internal> /DOutputDir=<out> /DOutputName=<file name without .exe> Karrierekrake.iss
;
; Installs for the current user (no administrator rights), so the in-app updater can write to the folder.
; Personal data lives in %LOCALAPPDATA%\Karrierekrake and is only removed when the person says so on uninstall.

#ifndef AppVersion
  #define AppVersion "dev"
#endif
#ifndef SourceDir
  #error SourceDir is required
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef OutputName
  #define OutputName "Karrierekrake-Setup"
#endif

[Setup]
AppId={{A1C906A3-4AAC-4A29-BC9F-1284DF877EE9}
AppName=Karrierekrake
AppVersion={#AppVersion}
AppPublisher=Karrierekrake
DefaultDirName={autopf}\Karrierekrake
DefaultGroupName=Karrierekrake
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\Karrierekrake.exe
UninstallDisplayName=Karrierekrake
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=auto

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
german.AskDeleteData=Sollen auch deine persönlichen Daten gelöscht werden (Profil, Lebenslauf, Bewerbungen, Postfach-Daten)?%n%nWähle „Nein“, wenn du Karrierekrake später wieder installieren möchtest.
english.AskDeleteData=Do you also want to delete your personal data (profile, CV, applications, mailbox data)?%n%nChoose "No" if you plan to install Karrierekrake again later.
german.DesktopIcon=Verknüpfung auf dem Desktop erstellen
english.DesktopIcon=Create a shortcut on the desktop
german.RunAfter=Karrierekrake jetzt starten
english.RunAfter=Start Karrierekrake now

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Karrierekrake"; Filename: "{app}\Karrierekrake.exe"
Name: "{autodesktop}\Karrierekrake"; Filename: "{app}\Karrierekrake.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Karrierekrake.exe"; Description: "{cm:RunAfter}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The updater adds files after setup (components, previous version), so remove the whole folder.
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Karrierekrake');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox(CustomMessage('AskDeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;

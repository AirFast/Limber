; Rhythmos installer (Inno Setup 6).
; Build: build.ps1, or manually: ISCC.exe /DAppVersion=1.0.0 installer\rhythmos.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "Rhythmos"
#define AppExe "Rhythmos.exe"

[Setup]
AppId={{6B1E4C27-3A5D-4F2B-9C7E-0D8A41F5B2E9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Andrew Petryk
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; The install folder and the Start menu group always use the app name
UsePreviousAppDir=no
UsePreviousGroup=no
; Install for the current user, without administrator rights
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=RhythmosSetup-{#AppVersion}
SetupIconFile=..\assets\rhythmos.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ukrainian.AutostartTask=Запускати Rhythmos разом з Windows
english.AutostartTask=Start Rhythmos with Windows
ukrainian.RemoveUserData=Видалити також ваші налаштування та статистику Rhythmos?%n%nЯкщо залишити їх, після повторного встановлення все відновиться.
english.RemoveUserData=Also delete your Rhythmos settings and statistics?%n%nIf you keep them, everything will be restored if you reinstall.

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Rhythmos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open"; Tasks: desktopicon

[Run]
; The app language is the one chosen in the installer
Filename: "{app}\{#AppExe}"; Parameters: "--set-language=uk"; Flags: runhidden waituntilterminated; Languages: ukrainian
Filename: "{app}\{#AppExe}"; Parameters: "--set-language=en"; Flags: runhidden waituntilterminated; Languages: english
Filename: "{app}\{#AppExe}"; Parameters: "--set-autostart=on"; Flags: runhidden waituntilterminated; Tasks: autostart
; Autostart is turned off only by an explicit choice in the installer window. A silent install is
; an auto-update, and the checkbox state there is unreliable: autostart is left alone
Filename: "{app}\{#AppExe}"; Parameters: "--set-autostart=off"; Flags: runhidden waituntilterminated; Tasks: not autostart; Check: not WizardSilent
Filename: "{app}\{#AppExe}"; Parameters: "--open"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; A silent install is an auto-update from the app: start the new version instead of the old one
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "StopRhythmos"
Filename: "{app}\{#AppExe}"; Parameters: "--set-autostart=off"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveAutostart"

[Code]
// Before installing or updating, close the running app so its files can be replaced
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

// After uninstalling, offer to remove the user's data too (%APPDATA%\Rhythmos).
// In silent mode (/SILENT, /VERYSILENT) the data stays.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if MsgBox(CustomMessage('RemoveUserData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\{#AppName}'), True, True, True);
end;

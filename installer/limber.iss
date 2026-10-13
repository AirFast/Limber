; Інсталятор Limber (Inno Setup 6).
; Збирання: build.ps1 або вручну: ISCC.exe /DAppVersion=1.0.0 installer\limber.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "Limber"
#define AppExe "Limber.exe"

[Setup]
AppId={{6B1E4C27-3A5D-4F2B-9C7E-0D8A41F5B2E9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Andrew Petryk
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Встановлення для поточного користувача — без прав адміністратора
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=LimberSetup-{#AppVersion}
SetupIconFile=..\assets\limber.ico
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
ukrainian.AutostartTask=Запускати Limber разом з Windows
english.AutostartTask=Start Limber with Windows

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"; Flags: checkedonce
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Limber\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open"; Tasks: desktopicon

[Run]
; Мова програми — та, яку вибрали в інсталяторі
Filename: "{app}\{#AppExe}"; Parameters: "--set-language=uk"; Flags: runhidden waituntilterminated; Languages: ukrainian
Filename: "{app}\{#AppExe}"; Parameters: "--set-language=en"; Flags: runhidden waituntilterminated; Languages: english
Filename: "{app}\{#AppExe}"; Parameters: "--set-autostart=on"; Flags: runhidden waituntilterminated; Tasks: autostart
Filename: "{app}\{#AppExe}"; Parameters: "--set-autostart=off"; Flags: runhidden waituntilterminated; Tasks: not autostart
Filename: "{app}\{#AppExe}"; Parameters: "--open"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "StopLimber"
Filename: "{app}\{#AppExe}"; Parameters: "--set-autostart=off"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveAutostart"

[Code]
// Перед встановленням чи оновленням закриваємо запущену програму, щоб файли можна було замінити
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

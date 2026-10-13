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
ukrainian.RemoveUserData=Видалити також ваші налаштування та статистику Limber?%n%nЯкщо залишити їх, після повторного встановлення все відновиться.
english.RemoveUserData=Also delete your Limber settings and statistics?%n%nIf you keep them, everything will be restored if you reinstall.

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Limber\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Версії 1.0–1.1 клали ярлик прямо в «Програми»; тепер він у папці Limber
Type: files; Name: "{autoprograms}\{#AppName}.lnk"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open"; Tasks: desktopicon

[Run]
; Мова програми — та, яку вибрали в інсталяторі
Filename: "{app}\{#AppExe}"; Parameters: "--set-language=uk"; Flags: runhidden waituntilterminated; Languages: ukrainian
Filename: "{app}\{#AppExe}"; Parameters: "--set-language=en"; Flags: runhidden waituntilterminated; Languages: english
Filename: "{app}\{#AppExe}"; Parameters: "--set-autostart=on"; Flags: runhidden waituntilterminated; Tasks: autostart
; Вимикаємо автозапуск лише за явним вибором у вікні інсталятора. Тихе встановлення — це
; автооновлення, і стан галочки там ненадійний: автозапуск не чіпаємо
Filename: "{app}\{#AppExe}"; Parameters: "--set-autostart=off"; Flags: runhidden waituntilterminated; Tasks: not autostart; Check: not WizardSilent
Filename: "{app}\{#AppExe}"; Parameters: "--open"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; Тихе встановлення — це автооновлення з програми: запускаємо нову версію замість старої
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

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

// Після видалення пропонуємо прибрати й дані користувача (%APPDATA%\Limber).
// У тихому режимі (/SILENT, /VERYSILENT) дані лишаються.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if MsgBox(CustomMessage('RemoveUserData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\{#AppName}'), True, True, True);
end;

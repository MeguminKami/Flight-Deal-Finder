; =============================================================================
; Flight Deal Finder - Inno Setup Installer Script
; Version: 2.0.0
; =============================================================================
; This script creates a professional Windows installer with:
; - Welcome screen
; - License agreement (optional)
; - Directory selection
; - Start Menu and Desktop shortcut options
; - Install progress
; - Finish screen with "Launch app" option
; - Full uninstaller
; =============================================================================

#define AppName "Flight Deal Finder"
#define AppNameNoSpaces "FlightDealFinder"
#define AppVersion "2.0.0"
#define AppPublisher "João Ferreira"
#define AppURL "https://github.com/joaoferreira/FlightDealFinder"
#define AppExeName "FlightDealFinder.exe"
#define AppCopyright "Copyright © 2024-2026 João Ferreira"

[Setup]
; Application identity
AppId={{8A7B9C3D-4E5F-6A7B-8C9D-0E1F2A3B4C5D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
AppCopyright={#AppCopyright}

; Version information (Major.Minor.Build.Revision)
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoCopyright={#AppCopyright}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

; Installation directories
DefaultDirName={autopf}\{#AppNameNoSpaces}
DefaultGroupName={#AppName}
DisableProgramGroupPage=no
AllowNoIcons=yes

; Output settings
OutputDir=output
OutputBaseFilename={#AppNameNoSpaces}_Setup_{#AppVersion}_x64

; Compression (LZMA2 for best compression)
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4

; Installer appearance
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
WizardSizePercent=110,110
WizardResizable=yes

; Privileges (install for current user by default, per-machine if admin)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Uninstaller
UninstallDisplayName={#AppName}
CreateUninstallRegKey=yes

; License file
LicenseFile=LICENSE.txt

; Misc settings
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=no
DisableFinishedPage=no
ShowLanguageDialog=auto
CloseApplications=yes
RestartApplications=no

; 64-bit only
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Minimum Windows version (Windows 10)
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[CustomMessages]
english.LaunchApp=Launch {#AppName} after installation
portuguese.LaunchApp=Iniciar {#AppName} após instalação
english.CreateStartMenuShortcut=Create Start Menu shortcut
portuguese.CreateStartMenuShortcut=Criar atalho no Menu Iniciar
english.CreateDesktopShortcut=Create Desktop shortcut
portuguese.CreateDesktopShortcut=Criar atalho na Área de Trabalho

[Tasks]
Name: "startmenuicon"; Description: "{cm:CreateStartMenuShortcut}"; GroupDescription: "Shortcuts:"
Name: "desktopicon"; Description: "{cm:CreateDesktopShortcut}"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; Main application files (from PyInstaller output)
Source: "dist\\{#AppNameNoSpaces}\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Optional config template (non-secret)
Source: "..\\..\\config.env.example"; DestDir: "{app}"; Flags: ignoreversion

; Auto-provision user config on install (only if it doesn't already exist)
Source: "..\\..\\config.env.example"; DestDir: "{localappdata}\\{#AppNameNoSpaces}"; DestName: "config.env"; Flags: onlyifdoesntexist uninsneveruninstall ignoreversion

; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
; Start Menu shortcuts
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenuicon
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon

; Desktop shortcut
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Launch application after install (optional)
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Clean up generated files (cache, logs, etc.) - NOT user data in AppData
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.db"
Type: filesandordirs; Name: "{app}\__pycache__"

[Registry]
; App Paths registration for easier launching
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName}"; Flags: uninsdeletekey

[Code]
// =============================================================================
// Pascal Script for custom installer behavior
// =============================================================================

var
  DownloadPage: TDownloadWizardPage;

function InitializeSetup(): Boolean;
begin
  Result := True;
  // Add any pre-installation checks here
  // For example, check for running instances of the app
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Post-installation tasks
    // You can add registry entries, environment variables, etc.
  end;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Try to close the application before uninstalling
  if CheckForMutexes('{#AppNameNoSpaces}_Mutex') then
  begin
    if MsgBox('The application is currently running. Close it to continue uninstallation?',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      // Force close the application
      Exec('taskkill.exe', '/F /IM {#AppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Sleep(1000);
    end
    else
    begin
      Result := False;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Ask user if they want to remove application data
    if MsgBox('Do you want to remove application settings and cache from AppData?'#13#10 +
              'This will delete all saved preferences.',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\{#AppNameNoSpaces}'), True, True, True);
      DelTree(ExpandConstant('{userappdata}\{#AppNameNoSpaces}'), True, True, True);
    end;
  end;
end;

// Check Windows version
function IsWindows10OrNewer(): Boolean;
begin
  Result := (GetWindowsVersion >= $0A000000);
end;

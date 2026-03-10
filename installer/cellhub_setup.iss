; Inno Setup script for Cellhub Scanner
; Prerequisites: Build the EXE first via build_windows.bat
; Then open this file in Inno Setup Compiler (https://jrsoftware.org/isinfo.php)
; and click Build → Compile.

#define AppName "Cellhub Scanner"
#define AppVersion "1.0.0"
#define AppPublisher "Cellhub"
#define AppExeName "CellhubScanner.exe"
#define AppDescription "Telecom Bill PDF Extractor"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://cellhub.co.za
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Require admin only if installing to Program Files
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer_output
OutputBaseFilename=CellhubScanner_Setup_v{#AppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Minimum Windows version: Windows 10
MinVersion=10.0
; Surface tablet compatibility
TouchInterface=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startupicon"; Description: "Launch {#AppName} when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Main executable (built by PyInstaller)
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Patterns and credentials config — keep outside exe so users can add patterns
Source: "..\patterns\patterns.json"; DestDir: "{app}\patterns"; Flags: onlyifdoesntexist
Source: "..\config\credentials\*"; DestDir: "{app}\config\credentials"; Flags: onlyifdoesntexist recursesubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove generated token file on uninstall (contains OAuth credentials)
Type: files; Name: "{app}\config\token.json"

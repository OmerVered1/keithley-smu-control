; Inno Setup script for Keithley SMU Control Suite (Windows installer)
; Build prerequisites:
;   1. PyInstaller has produced  dist\Keithley SMU Control Suite\  (folder
;      containing the .exe and all its dependencies).
;   2. Inno Setup 6+ is installed (or ISCC.exe is on PATH).
; Usage:
;   iscc /DAppVersion=2.0.3 windows_installer.iss
; The CI workflow (.github/workflows/build-windows.yml) passes AppVersion
; from the pushed git tag.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppName=Keithley SMU Control Suite
AppVersion={#AppVersion}
AppVerName=Keithley SMU Control Suite {#AppVersion}
AppPublisher=Omer Vered
AppPublisherURL=https://github.com/OmerVered1/keithley-smu-control
AppSupportURL=https://github.com/OmerVered1/keithley-smu-control/issues
AppUpdatesURL=https://github.com/OmerVered1/keithley-smu-control/releases
DefaultDirName={autopf}\Keithley SMU Control Suite
DefaultGroupName=Keithley SMU Control Suite
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=Keithley-SMU-Control-Suite-Setup-{#AppVersion}
#if FileExists("assets\app_icon.ico")
SetupIconFile=assets\app_icon.ico
#endif
UninstallDisplayIcon={app}\Keithley SMU Control Suite.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Bundle the entire PyInstaller output folder.
Source: "dist\Keithley SMU Control Suite\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Keithley SMU Control Suite"; Filename: "{app}\Keithley SMU Control Suite.exe"
Name: "{group}\Uninstall Keithley SMU Control Suite"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Keithley SMU Control Suite"; Filename: "{app}\Keithley SMU Control Suite.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Keithley SMU Control Suite.exe"; Description: "Launch Keithley SMU Control Suite"; Flags: nowait postinstall skipifsilent

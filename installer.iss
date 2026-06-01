[Setup]
AppName=DevCleaner Pro
AppVersion=8.3
AppPublisher=NEURAL_ARCHTECT_PREMIUM++
DefaultDirName={autopf}\NEURAL_ARCHTECT_PREMIUM++v8.3
DefaultGroupName=NEURAL_ARCHTECT_PREMIUM++
UninstallDisplayName=DevCleaner Pro (NEURAL_ARCHTECT_PREMIUM++v8.3)
OutputDir=.\Output
OutputBaseFilename=NEURAL_ARCHTECT_PREMIUM++_v8.3_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "release\DevCleanerPro.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\DevHud.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{commondesktop}\DevCleaner Pro"; Filename: "{app}\DevCleanerPro.exe"; WorkingDir: "{app}"
Name: "{group}\DevCleaner Pro"; Filename: "{app}\DevCleanerPro.exe"; WorkingDir: "{app}"
Name: "{group}\DevCleaner HUD"; Filename: "{app}\DevHud.exe"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram, DevCleaner Pro}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\DevCleanerPro.exe"; Description: "Запустить DevCleaner Pro"; Flags: nowait postinstall skipifsilent
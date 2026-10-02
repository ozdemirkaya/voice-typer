[Setup]
AppName=Voice Typer
AppVersion=1.0.0
AppPublisher=M.K.
DefaultDirName={userpf}\VoiceTyper
DefaultGroupName=Voice Typer
OutputDir=installer
OutputBaseFilename=VoiceTyperSetup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\VoiceTyper.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Windows açılışında otomatik başlat"; GroupDescription: "Diğer Seçenekler:"

[Files]
Source: "dist\VoiceTyper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Voice Typer"; Filename: "{app}\VoiceTyper.exe"
Name: "{autodesktop}\Voice Typer"; Filename: "{app}\VoiceTyper.exe"; Tasks: desktopicon
Name: "{userstartup}\Voice Typer"; Filename: "{app}\VoiceTyper.exe"; Tasks: startup

[Run]
Filename: "{app}\VoiceTyper.exe"; Description: "{cm:LaunchProgram,Voice Typer}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "VoiceTyper"; Flags: dontcreatekey uninsdeletevalue

; Сборка: iscc /DAppVersion=1.3.0 packaging\arashan.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B0E4C2A-5E1D-4F7B-9A3C-0A5A5A5A5A01}
AppName=Arashan Boniter
AppVersion={#AppVersion}
AppPublisher=Arashan
DefaultDirName={autopf}\ArashanBoniter
DefaultGroupName=Arashan Boniter
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ArashanBoniter-Setup-{#AppVersion}
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\ArashanBoniter.exe
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: checkedonce

[Files]
Source: "..\dist\ArashanBoniter\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Arashan Boniter"; Filename: "{app}\ArashanBoniter.exe"
Name: "{autodesktop}\Arashan Boniter"; Filename: "{app}\ArashanBoniter.exe"; Tasks: desktopicon

[Run]
; Без skipifsilent: после тихого автообновления приложение запускается снова.
Filename: "{app}\ArashanBoniter.exe"; Description: "Запустить Arashan Boniter"; Flags: nowait postinstall

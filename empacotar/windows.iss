#ifndef Versao
  #define Versao "0.0.0"
#endif

[Setup]
AppId={{6B0E3C1A-5F2D-4C8B-9A7E-2D1F4E6A8B31}
AppName=Painel do DualSense
AppVersion={#Versao}
AppPublisher=ayramesteodosio
AppPublisherURL=https://github.com/ayramesteodosio/dualsense-painel
DefaultDirName={autopf}\Painel do DualSense
DefaultGroupName=Painel do DualSense
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Instalar-Painel-DualSense
SetupIconFile=icones\dualsense-painel.ico
UninstallDisplayIcon={app}\Painel do DualSense.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Painel do DualSense\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Painel do DualSense"; Filename: "{app}\Painel do DualSense.exe"
Name: "{autodesktop}\Painel do DualSense"; Filename: "{app}\Painel do DualSense.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Painel do DualSense.exe"; Description: "{cm:LaunchProgram,Painel do DualSense}"; Flags: nowait postinstall skipifsilent

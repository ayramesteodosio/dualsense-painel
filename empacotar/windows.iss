#define HidHideUrl "https://github.com/nefarius/HidHide/releases/download/v1.5.230.0/HidHide_1.5.230_x64.exe"

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
Name: "hidhide"; Description: "Instalar o HidHide (recomendado): no modo carregar, esconde o controle dos jogos e da Steam"; GroupDescription: "Complementos:"; Check: not HidHideInstalado

[Files]
Source: "..\dist\Painel do DualSense\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Painel do DualSense"; Filename: "{app}\Painel do DualSense.exe"
Name: "{autodesktop}\Painel do DualSense"; Filename: "{app}\Painel do DualSense.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\HidHide.exe"; StatusMsg: "Instalando o HidHide..."; Flags: shellexec waituntilterminated skipifdoesntexist; Tasks: hidhide
Filename: "{app}\Painel do DualSense.exe"; Description: "{cm:LaunchProgram,Painel do DualSense}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Painel do DualSense.exe"; Flags: nowait; Check: WizardSilent

[Code]
var
  Baixar: TDownloadWizardPage;

function HidHideInstalado: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf64}\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe')) or
    FileExists(ExpandConstant('{commonpf64}\Nefarius Software Solutions e.U\HidHide\x64\HidHideCLI.exe'));
end;

procedure InitializeWizard;
begin
  Baixar := CreateDownloadPage('Baixando o HidHide', 'Aguarde enquanto o HidHide é baixado do site oficial.', nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and WizardIsTaskSelected('hidhide') then
  begin
    Baixar.Clear;
    Baixar.Add('{#HidHideUrl}', 'HidHide.exe', '');
    Baixar.Show;
    try
      try
        Baixar.Download;
      except
        SuppressibleMsgBox('Não consegui baixar o HidHide (' + GetExceptionMessage + '). O app será instalado sem ele.', mbError, MB_OK, IDOK);
      end;
    finally
      Baixar.Hide;
    end;
  end;
end;

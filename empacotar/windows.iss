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
ShowLanguageDialog=auto
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
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ptbr.Complementos=Complementos:
en.Complementos=Extras:
ptbr.Autostart=Iniciar com o Windows (abre escondido, para o modo carregar e os avisos funcionarem sozinhos)
en.Autostart=Start with Windows (opens hidden, so charging mode and alerts work on their own)
ptbr.HidHide=Instalar o HidHide (recomendado): no modo carregar, esconde o controle dos jogos e da Steam
en.HidHide=Install HidHide (recommended): hides the controller from games and Steam in charging mode
ptbr.InstalandoHidHide=Instalando o HidHide...
en.InstalandoHidHide=Installing HidHide...
ptbr.BaixandoTitulo=Baixando o HidHide
en.BaixandoTitulo=Downloading HidHide
ptbr.BaixandoTexto=Aguarde enquanto o HidHide é baixado do site oficial.
en.BaixandoTexto=Please wait while HidHide is downloaded from its official site.
ptbr.FalhaBaixar=Não consegui baixar o HidHide (%1). O app será instalado sem ele.
en.FalhaBaixar=Couldn't download HidHide (%1). The app will be installed without it.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:Autostart}"; GroupDescription: "{cm:Complementos}"; Flags: unchecked
Name: "hidhide"; Description: "{cm:HidHide}"; GroupDescription: "{cm:Complementos}"; Check: not HidHideInstalado

[Files]
Source: "..\dist\Painel do DualSense\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Painel do DualSense"; ValueData: """{app}\Painel do DualSense.exe"" --segundo-plano"; Flags: uninsdeletevalue; Tasks: autostart; Check: not WizardSilent
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "DualSense Studio"; Flags: deletevalue; Tasks: autostart; Check: not WizardSilent

[Icons]
Name: "{autoprograms}\Painel do DualSense"; Filename: "{app}\Painel do DualSense.exe"
Name: "{autodesktop}\Painel do DualSense"; Filename: "{app}\Painel do DualSense.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\HidHide.exe"; StatusMsg: "{cm:InstalandoHidHide}"; Flags: shellexec waituntilterminated skipifdoesntexist; Tasks: hidhide
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
  Baixar := CreateDownloadPage(CustomMessage('BaixandoTitulo'), CustomMessage('BaixandoTexto'), nil);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Painel do DualSense');
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
        SuppressibleMsgBox(FmtMessage(CustomMessage('FalhaBaixar'), [GetExceptionMessage]), mbError, MB_OK, IDOK);
      end;
    finally
      Baixar.Hide;
    end;
  end;
end;

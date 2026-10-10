#ifndef AppVersion
  #error "Define AppVersion via scripts/build_release.ps1 (pyproject.toml)."
#endif
#ifndef InstallerAppId
  #define InstallerAppId "{{A3859DE6-BCF4-4CCE-9D4C-816A51BF2648}"
#endif
#ifndef CandidateDir
  #define CandidateDir SourcePath + "\..\.build\candidate\YunYouBao"
#endif
#ifndef ReleaseDir
  #define ReleaseDir SourcePath + "\..\release\" + AppVersion
#endif
#define AppName "云邮宝"
#define AppExe "YunYouBao.exe"

[Setup]
AppId={#InstallerAppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=YunYouBao contributors
AppCopyright=Copyright (C) 2026 YunYouBao contributors
VersionInfoVersion={#AppVersion}.0
DefaultDirName={localappdata}\Programs\YunYouBao
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableDirPage=no
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
OutputDir={#ReleaseDir}
OutputBaseFilename={#AppName}-{#AppVersion}-setup
SetupIconFile=..\assets\branding\yunyoubao-fox-v1.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=license-zh-CN.txt
InfoBeforeFile=notice-zh-CN.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SignedUninstaller=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
; Anchor personal directories; nested library runtime directories must be included.
Source: "{#CandidateDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env,.env.*,\runtime\*,\logs\*,\state\*,\uploads\*,\data\*,\_internal\runtime\*,\_internal\logs\*,\_internal\state\*,\_internal\uploads\*,\_internal\data\*"

[Icons]
Name: "{userprograms}\{#AppName}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{userprograms}\{#AppName}\卸载{#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

; No runtime copy, automatic dependency download, automatic launch, or user-data deletion.
[Code]
function AppIsRunning: Boolean;
var
  Locator, Services, Processes: Variant;
begin
  Locator := CreateOleObject('WbemScripting.SWbemLocator');
  Services := Locator.ConnectServer('', 'root\CIMV2');
  Processes := Services.ExecQuery('SELECT Name FROM Win32_Process WHERE Name = ''YunYouBao.exe'' OR Name = ''云邮宝.exe''');
  Result := Processes.Count > 0;
end;

function HasWebView2At(RootKey: Integer; const Key: String): Boolean;
var
  Version: String;
  Parts: TArrayOfString;
  I: Integer;
begin
  Result := False;
  if not RegQueryStringValue(RootKey, Key, 'pv', Version) then exit;
  Parts := StringSplit(Version, ['.'], stAll);
  if GetArrayLength(Parts) <> 4 then exit;
  for I := 0 to 3 do begin
    if StrToIntDef(Parts[I], -1) < 0 then exit;
  end;
  for I := 0 to 3 do begin
    if StrToIntDef(Parts[I], 0) > 0 then Result := True;
  end;
end;

function HasWebView2: Boolean;
var
  Key: String;
begin
  Key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := HasWebView2At(HKLM32, Key) or HasWebView2At(HKCU, Key);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ErrorCode: Integer;
begin
  Result := '';
  try
    if AppIsRunning then begin
      Result := '请先关闭正在运行的云邮宝，再重试安装（包括同版本升级）。';
      exit;
    end;
  except
    Result := '无法检查云邮宝运行状态。请确认 Windows WMI 服务正常后重试。';
    exit;
  end;
  if not HasWebView2 then begin
    Result := '缺少 Microsoft Edge WebView2 Runtime。请从微软官方网站安装 Evergreen Runtime 后重试。' + #13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2/';
    if not WizardSilent then begin
      if MsgBox(Result + #13#10 + '是否打开微软官方下载页面？安装器不会自动下载或安装此依赖。', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        ShellExecAsOriginalUser('open', 'https://developer.microsoft.com/microsoft-edge/webview2/', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
    end;
  end;
end;

function InitializeUninstall: Boolean;
begin
  Result := False;
  try
    if AppIsRunning then begin
      MsgBox('请先关闭云邮宝，再卸载。用户数据将保留。', mbError, MB_OK);
      exit;
    end;
    Result := True;
  except
    MsgBox('无法检查云邮宝运行状态。请确认 Windows WMI 服务正常后重试。', mbError, MB_OK);
  end;
end;

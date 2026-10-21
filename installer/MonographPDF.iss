; Monograph PDF — Inno Setup script
; Build with installer\build_release.bat (or: tools\inno\ISCC.exe installer\MonographPDF.iss)
; Produces installer\MonographPDF_{version}_Setup.exe from the PyInstaller onedir build in dist\MonographPDF.
;
; Setup keeps a stable AppId so an earlier internal development build (executable PDF_editor.exe,
; folders named "PDF Editor", final internal freeze 0.1.5) is recognised and replaced: one installed
; application remains (in place, or moved to a "Monograph PDF" folder). The Legacy* names below are
; used only for that internal-compatibility detection and cleanup — not as public product history.

#define AppName "Monograph PDF"
#define AppExe "MonographPDF.exe"
#define AppPublisher "Aung Ye Mun"
#define AppContact "aungyemun25@gmail.com"
#define ProgIdPdf "MonographPDF.Document"
#define ProgIdOther "MonographPDF.Convertible"
#define AppRegKey "Software\Monograph PDF"
#define CapKey AppRegKey + "\Capabilities"

; ---- Earlier internal build (<= 0.1.5): detection and cleanup identifiers only ----
#define LegacyName "PDF Editor"
#define LegacyExe "PDF_editor.exe"
#define LegacyProgIdPdf "PDFEditor.Document"
#define LegacyProgIdOther "PDFEditor.Convertible"
#define LegacyRegKey "Software\PDF Editor"

#define Root AddBackslash(SourcePath) + ".."
#ifndef AppVersion
  #define VersionHandle FileOpen(Root + "\VERSION")
  #define AppVersion Trim(FileRead(VersionHandle))
  #expr FileClose(VersionHandle)
#endif
#ifndef PayloadDir
  #define PayloadDir Root + "\dist\MonographPDF"
#endif
; uninstall.exe: built by scripts\build_release.ps1 from installer\uninstall_launcher.cs
#ifndef UninstallExe
  #define UninstallExe Root + "\build\installer\uninstall.exe"
#endif
; MonographPDFUpdater.exe: built by scripts\build_release.ps1 from installer\update_helper.cs. Monograph PDF
; copies it to its update staging folder to finish an update after the application has closed.
#ifndef UpdaterExe
  #define UpdaterExe Root + "\build\installer\MonographPDFUpdater.exe"
#endif

[Setup]
; Same AppId as PDF Editor: Monograph PDF upgrades it instead of installing beside it
AppId={{64FC0D97-5E17-405F-9461-D6C075E1B467}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppContact={#AppContact}
AppCopyright=© 2026 {#AppPublisher}
AppComments=Offline, privacy-first PDF editor: view, edit, convert, protect and sign PDF documents.
VersionInfoVersion={#AppVersion}.0
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright=© 2026 {#AppPublisher}

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; The Start menu folder is always "Monograph PDF" (an upgraded PDF Editor's "PDF Editor" folder is replaced)
UsePreviousGroup=no
; Reuse the previous install folder when upgrading (same AppId); a PDF Editor folder can be moved to
; a Monograph PDF folder on the "Upgrade to Monograph PDF" page
UsePreviousAppDir=yes
; Install for all users by default (admin), or for the current user only without admin rights
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

#ifndef OutputDirectory
  #define OutputDirectory "."
#endif
OutputDir={#OutputDirectory}
OutputBaseFilename=MonographPDF_{#AppVersion}_Setup
SetupIconFile={#Root}\resources\icons\windows\monograph_pdf.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=assets\wizard_large_164.bmp,assets\wizard_large_328.bmp
WizardSmallImageFile=assets\wizard_small_55.bmp,assets\wizard_small_69.bmp,assets\wizard_small_83.bmp,assets\wizard_small_110.bmp
; build_release.ps1 writes a UTF-8 (BOM) copy of LICENSE.md so the licence page shows © and dashes correctly
#define LicenseTxt Root + "\build\installer\LICENSE.txt"
#if FileExists(LicenseTxt)
LicenseFile={#LicenseTxt}
#else
LicenseFile={#Root}\LICENSE.md
#endif
#ifndef InstalledManifest
  #define InstalledManifest Root + "\build\installer\installed_files.txt"
#endif
Compression=lzma2/max
SolidCompression=yes
; Compress in a separate process so the large payload does not exhaust the compiler's memory
LZMAUseSeparateProcess=yes
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nMonograph PDF views, edits, organizes, converts, protects and signs PDF documents. It works offline — your files never leave this computer. It connects to the internet only when you check for updates (or turn on automatic update checks) or choose to send a problem report; see the privacy policy (docs\PRIVACY_POLICY.md on the project page).%n%nMonograph PDF is the new name of PDF Editor. If PDF Editor is installed, Setup upgrades it and keeps your settings and documents.%n%nIt is recommended that you close PDF Editor and Monograph PDF before continuing.

[Tasks]
Name: "startmenu"; Description: "Create &Start Menu shortcuts"; GroupDescription: "Shortcuts:"
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "assocpdf"; Description: "Register Monograph PDF for &PDF files (.pdf) — adds it to Open with and Default apps"; GroupDescription: "File types:"
Name: "assocother"; Description: "Add Monograph PDF to Open with for &images and Word, Excel and PowerPoint files"; GroupDescription: "File types:"

[InstallDelete]
; Upgrade: remove owned application trees/files before copying the new release.
; Unknown / user-created files in {app} are never listed here and are preserved.
; Inno's unins000.* files and the active uninstall state are left alone.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\engines"
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\docs"
Type: filesandordirs; Name: "{app}\licenses"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\packages"
Type: files; Name: "{app}\{#AppExe}"
Type: files; Name: "{app}\MonographPDFUpdater.exe"
; PDF Editor's program (in-place upgrade of PDF Editor <= 0.1.5)
Type: files; Name: "{app}\{#LegacyExe}"
Type: files; Name: "{app}\README.md"
Type: files; Name: "{app}\LICENSE.md"
Type: files; Name: "{app}\THIRD_PARTY_NOTICES.md"
Type: files; Name: "{app}\SECURITY.md"
Type: files; Name: "{app}\CHANGELOG.md"
Type: files; Name: "{app}\installed_files.txt"
Type: files; Name: "{app}\installed_files.json"
; Start menu entries of earlier versions (uninstall shortcut; guide shortcut that opened the .md file)
Type: files; Name: "{group}\Uninstall {#AppName}.lnk"
Type: files; Name: "{group}\User Guide.lnk"

[Files]
Source: "{#PayloadDir}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#UninstallExe}"; DestDir: "{app}"; DestName: "uninstall.exe"; Flags: ignoreversion
Source: "{#UpdaterExe}"; DestDir: "{app}"; DestName: "MonographPDFUpdater.exe"; Flags: ignoreversion
Source: "{#PayloadDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\engines\ocr\*"; DestDir: "{app}\engines\ocr"; Excludes: ".gitkeep"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\models\tessdata\*"; DestDir: "{app}\models\tessdata"; Excludes: ".gitkeep"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\LICENSE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\SECURITY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\docs\USER_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#Root}\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\third_party\licenses\TESSERACT_NOTICE.txt"; DestDir: "{app}\engines\ocr"; Flags: ignoreversion skipifsourcedoesntexist
; License texts of the bundled GPL / LGPL / MPL components (their source is in MonographPDF_{version}_Source.zip)
Source: "{#Root}\third_party\licenses\*.txt"; Excludes: "TESSERACT_NOTICE.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
; Owned-file list for the next upgrade's obsolete-file cleanup (never includes user documents)
Source: "{#InstalledManifest}"; DestDir: "{app}"; DestName: "installed_files.txt"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Edit, convert, protect and sign PDF documents"; Tasks: startmenu
; The guide opens in Monograph PDF's own viewer, so no Markdown app is needed. Uninstalling is done
; from Settings > Apps (Windows 10/11 practice: no uninstall shortcut in the Start menu).
Name: "{group}\{#AppName} User Guide"; Filename: "{app}\{#AppExe}"; Parameters: "--user-guide"; WorkingDir: "{app}"; Comment: "Read the Monograph PDF User Guide"; Tasks: startmenu
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Edit, convert, protect and sign PDF documents"; Tasks: desktopicon

[Registry]
; ---- Application registration (Run dialog, Open with list, Default apps) ----
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

; ---- PDF: ProgID, Open with, Default apps capability (never set as the default by Setup) ----
Root: HKA; Subkey: "Software\Classes\{#ProgIdPdf}"; ValueType: string; ValueName: ""; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#ProgIdPdf}"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "PDF Document"; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#ProgIdPdf}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#ProgIdPdf}\shell"; ValueType: string; ValueName: ""; ValueData: "open"; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#ProgIdPdf}\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#ProgIdPdf}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "{#ProgIdPdf}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Tasks: assocpdf

Root: HKA; Subkey: "{#AppRegKey}"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "{#CapKey}"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "{#CapKey}"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Edit, convert, protect and sign PDF documents — fully offline."
Root: HKA; Subkey: "{#CapKey}"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "{#CapKey}\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "{#ProgIdPdf}"; Tasks: assocpdf
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#AppName}"; ValueData: "{#CapKey}"; Flags: uninsdeletevalue

; ---- Images and Office documents: open as a new PDF (Open with only; never taken as default) ----
Root: HKA; Subkey: "Software\Classes\{#ProgIdOther}"; ValueType: string; ValueName: ""; ValueData: "Open as PDF in {#AppName}"; Flags: uninsdeletekey; Tasks: assocother
Root: HKA; Subkey: "Software\Classes\{#ProgIdOther}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assocother
Root: HKA; Subkey: "Software\Classes\{#ProgIdOther}\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Tasks: assocother
Root: HKA; Subkey: "Software\Classes\{#ProgIdOther}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assocother
#define OtherExt(Ext) \
  'Root: HKA; Subkey: "Software\Classes\' + Ext + '\OpenWithProgids"; ValueType: string; ValueName: "' + ProgIdOther + '"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocother' + NewLine + \
  'Root: HKA; Subkey: "Software\Classes\Applications\' + AppExe + '\SupportedTypes"; ValueType: string; ValueName: "' + Ext + '"; ValueData: ""; Tasks: assocother' + NewLine + \
  'Root: HKA; Subkey: "' + CapKey + '\FileAssociations"; ValueType: string; ValueName: "' + Ext + '"; ValueData: "' + ProgIdOther + '"; Tasks: assocother' + NewLine
#emit OtherExt(".png")
#emit OtherExt(".jpg")
#emit OtherExt(".jpeg")
#emit OtherExt(".tif")
#emit OtherExt(".tiff")
#emit OtherExt(".bmp")
#emit OtherExt(".gif")
#emit OtherExt(".webp")
#emit OtherExt(".docx")
#emit OtherExt(".doc")
#emit OtherExt(".rtf")
#emit OtherExt(".odt")
#emit OtherExt(".xlsx")
#emit OtherExt(".xls")
#emit OtherExt(".csv")
#emit OtherExt(".ods")
#emit OtherExt(".pptx")
#emit OtherExt(".ppt")
#emit OtherExt(".odp")

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
Filename: "ms-settings:defaultapps?registeredAppMachine={#AppName}"; Description: "Make Monograph PDF the default PDF app (opens Windows Settings)"; Flags: shellexec nowait postinstall skipifsilent unchecked; Tasks: assocpdf; Check: IsAdminInstallMode
Filename: "ms-settings:defaultapps?registeredAppUser={#AppName}"; Description: "Make Monograph PDF the default PDF app (opens Windows Settings)"; Flags: shellexec nowait postinstall skipifsilent unchecked; Tasks: assocpdf; Check: not IsAdminInstallMode

[UninstallDelete]
; Files the application or the installer self-test may have created in the install folder.
; [Code] also removes the recent-files list, cache, logs and temporary files of the user who
; uninstalls, and their settings when they choose so (or with /REMOVEUSERDATA).
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\_internal"
; Empty developer folders created by versions before 0.1.2
Type: filesandordirs; Name: "{app}\packages"
Type: dirifempty; Name: "{app}\engines\mupdf"
Type: dirifempty; Name: "{app}\engines\qpdf"
Type: dirifempty; Name: "{app}\engines"
Type: dirifempty; Name: "{app}\models"
Type: dirifempty; Name: "{app}"

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{64FC0D97-5E17-405F-9461-D6C075E1B467}_is1';
  DataFolderName = '{#AppName}';
  LegacyDataFolderName = '{#LegacyName}';
  LegacyMigrationRecord = 'legacy_migration.json';
  PrevManifestTmp = 'prev_installed_files.txt';

var
  PreviousInstall: Boolean;
  PreviousInstallDir: String;
  StaleInstallNote: String;
  RemoveUserData: Boolean;
  NotRemoved: String;
  CleanOldLocationAfterInstall: Boolean;
  MigrateInstallFlag: Boolean;
  SmokeTestPassed: Boolean;
  { Earlier internal build (<= 0.1.5) found: upgrade / move to Monograph PDF folders }
  LegacyUpgrade: Boolean;
  { Renamed folder suggested for a PDF Editor folder named "PDF Editor" ('' = keep the location) }
  RenamedDir: String;
  UpgradePage: TInputOptionWizardPage;
  { Uninstall: the PDF Editor data folders were migrated by Monograph PDF and may be cleaned up }
  LegacyDataAllowed: Boolean;

{ ---------------------------------------------------------------- shared helpers }

function IsInside(const Path, Folder: String): Boolean;
begin
  { True when Path is Folder or lies inside it (never delete the install folder by accident) }
  Result := (CompareText(AddBackslash(Path), AddBackslash(Folder)) = 0) or
            (Pos(Uppercase(AddBackslash(Folder)), Uppercase(AddBackslash(Path))) = 1);
end;

function IsSafeRelPath(const Rel: String): Boolean;
var
  P: String;
begin
  { Relative owned paths only: no drive letters, no .., no absolute roots }
  P := Rel;
  StringChangeEx(P, '/', '\', True);
  Result := (P <> '') and (P[1] <> '\') and (Pos(':', P) = 0) and (Pos('..', P) = 0);
end;

function IsAcceptableInstallRoot(const Dir: String): Boolean;
var
  D: String;
begin
  { Refuse wiping Program Files / Windows / profile roots themselves }
  Result := False;
  if Dir = '' then
    Exit;
  D := RemoveBackslashUnlessRoot(Dir);
  if Length(D) < 4 then
    Exit;  { e.g. C:\ }
  if (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{autopf}'))) = 0) or
     (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{pf}'))) = 0) or
     (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{pf32}'))) = 0) or
     (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{win}'))) = 0) or
     (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{%USERPROFILE}'))) = 0) or
     (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{userappdata}'))) = 0) or
     (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{localappdata}'))) = 0) or
     (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{userdesktop}'))) = 0) or
     (CompareText(D, RemoveBackslashUnlessRoot(ExpandConstant('{userdocs}'))) = 0) then
    Exit;
  Result := True;
end;

function RunningCopies(AnyFolder: Boolean): Integer;
var
  Locator, Service, Found, Item: Variant;
  I: Integer;
  Path, App: String;
begin
  { Number of MonographPDF.exe or PDF_editor.exe (PDF Editor) processes started from this
    installation folder (or from anywhere) }
  Result := 0;
  App := ExpandConstant('{app}');
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Found := Service.ExecQuery('SELECT ExecutablePath FROM Win32_Process WHERE Name = ''{#AppExe}'' OR Name = ''{#LegacyExe}''');
    for I := 0 to Found.Count - 1 do
    begin
      Item := Found.ItemIndex(I);
      Path := '';
      if not VarIsNull(Item.ExecutablePath) then
        Path := Item.ExecutablePath;
      { An unreadable path (another user's process) counts as running, to be safe }
      if AnyFolder or (Path = '') or IsInside(Path, App) then
        Result := Result + 1;
    end;
  except
    Log('Could not check for a running Monograph PDF / PDF Editor: ' + GetExceptionMessage);
  end;
end;

function RunningAppName(): String;
begin
  if LegacyUpgrade then
    Result := '{#LegacyName}'
  else
    Result := '{#AppName}';
end;

function IsReparsePoint(const Path: String): Boolean;
var
  Rec: TFindRec;
begin
  { A junction or symbolic link: never followed when removing Monograph PDF's folders }
  Result := False;
  if FindFirst(RemoveBackslashUnlessRoot(Path), Rec) then
  try
    Result := (Rec.Attributes and $400) <> 0;
  finally
    FindClose(Rec);
  end;
end;

function InNamedDataFolder(const Folder, Name: String): Boolean;
var
  Parent: String;
begin
  Parent := Uppercase(AddBackslash(Folder));
  Result := (Pos('\' + Uppercase(Name) + '\', Parent) > 0) and
            ((Pos(Uppercase(AddBackslash(ExpandConstant('{userappdata}'))), Parent) = 1) or
             (Pos(Uppercase(AddBackslash(ExpandConstant('{localappdata}'))), Parent) = 1));
end;

function IsOwnDataFolder(const Folder: String): Boolean;
begin
  { Only folders named Monograph PDF (or inside one) in this user's AppData can be removed, and
    PDF Editor's folders only when Monograph PDF migrated them (LegacyDataAllowed) }
  Result := InNamedDataFolder(Folder, DataFolderName) or
            (LegacyDataAllowed and InNamedDataFolder(Folder, LegacyDataFolderName));
end;

procedure RemoveFolder(const Folder: String);
begin
  if not DirExists(Folder) then
    Exit;
  if IsInside(ExpandConstant('{app}'), Folder) then
  begin
    Log('Not removing ' + Folder + ': it contains the installation folder');
    Exit;
  end;
  if not IsOwnDataFolder(Folder) then
  begin
    Log('Not removing ' + Folder + ': not a Monograph PDF data folder');
    Exit;
  end;
  if IsReparsePoint(Folder) then
  begin
    Log('Not removing ' + Folder + ': it is a link to another folder');
    Exit;
  end;
  DelTree(Folder, True, True, True);
  if DirExists(Folder) then
  begin
    Log('Could not remove ' + Folder + ' (files in use?)');
    NotRemoved := NotRemoved + #13#10 + '  ' + Folder;
  end
  else
    Log('Removed ' + Folder);
end;

procedure RemoveFile(const FileName: String);
begin
  if FileExists(FileName) then
  begin
    if DeleteFile(FileName) then
      Log('Removed ' + FileName)
    else
    begin
      Log('Could not remove ' + FileName);
      NotRemoved := NotRemoved + #13#10 + '  ' + FileName;
    end;
  end;
end;

function IsOwnTempName(const Name: String): Boolean;
var
  N: String;
begin
  { Work folders of Monograph PDF (monographpdf*, monograph-pdf-theme) and of PDF Editor
    (pdfeditor*, pdf-editor-theme). Nothing else in %TEMP% is touched. }
  N := Lowercase(Name);
  Result := (Pos('monographpdf', N) = 1) or (N = 'monograph-pdf-theme') or
            (Pos('pdfeditor', N) = 1) or (N = 'pdf-editor-theme');
end;

procedure RemoveTempMatches(const Temp, Pattern: String);
var
  Rec: TFindRec;
begin
  if FindFirst(AddBackslash(Temp) + Pattern, Rec) then
  try
    repeat
      if ((Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and ((Rec.Attributes and $400) = 0) and
         IsOwnTempName(Rec.Name) then
        DelTree(AddBackslash(Temp) + Rec.Name, True, True, True);
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;
end;

procedure RemoveTempLeftovers();
var
  Temp: String;
begin
  Temp := ExpandConstant('{%TEMP}');
  if (Temp = '') or not DirExists(Temp) then
    Exit;
  if RunningCopies(True) > 0 then
  begin
    Log('Monograph PDF or PDF Editor is running; temporary folders are left for it');
    Exit;
  end;
  RemoveTempMatches(Temp, 'monograph*');
  RemoveTempMatches(Temp, 'pdf*editor*');
end;

procedure ClearHistoryIn(const Folder: String);
begin
  { Recent-files list, recovery sessions, cache, logs and temporary files of the current user.
    Preferences (theme, window layout) stay unless RemoveUserData is set. }
  RemoveFile(ExpandConstant('{userappdata}\') + Folder + '\recent_files.json');
  RemoveFolder(ExpandConstant('{localappdata}\') + Folder + '\runtime');
  RemoveFolder(ExpandConstant('{localappdata}\') + Folder + '\Cache');
  RemoveFolder(ExpandConstant('{localappdata}\') + Folder + '\logs');
  { Update downloads waiting in the staging folder, update status, problem-report records }
  RemoveFolder(ExpandConstant('{localappdata}\') + Folder + '\Updates');
  RemoveFolder(ExpandConstant('{localappdata}\') + Folder + '\Diagnostics');
  RemoveDir(ExpandConstant('{localappdata}\') + Folder);
end;

procedure ClearUserHistory();
begin
  ClearHistoryIn(DataFolderName);
  RemoveTempLeftovers();
end;

function CanonicalPath(const Path: String): String;
begin
  { Case-insensitive compare key: trim trailing separators }
  Result := Uppercase(RemoveBackslashUnlessRoot(Path));
end;

function SameInstallPath(const A, B: String): Boolean;
begin
  Result := (A <> '') and (B <> '') and (CompareText(CanonicalPath(A), CanonicalPath(B)) = 0);
end;

function LooksLikeInstall(const Dir: String): Boolean;
begin
  { A Monograph PDF installation, or a PDF Editor (<= 0.1.5) installation to upgrade }
  Result := (Dir <> '') and DirExists(Dir) and
            (FileExists(AddBackslash(Dir) + '{#AppExe}') or FileExists(AddBackslash(Dir) + '{#LegacyExe}'));
end;

function IsLegacyInstallDir(const Dir: String): Boolean;
begin
  Result := (Dir <> '') and FileExists(AddBackslash(Dir) + '{#LegacyExe}') and
            not FileExists(AddBackslash(Dir) + '{#AppExe}');
end;

function SetupPrefersCurrentUser(): Boolean;
var
  I: Integer;
begin
  { Prefer HKCU registrations for /CURRENTUSER; otherwise prefer machine registrations. }
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/CURRENTUSER') = 0 then
    begin
      Result := True;
      Exit;
    end;
  try
    Result := not IsAdminInstallMode;
  except
    Result := False;
  end;
end;

function DirFromUninstallMetadata(RootKey: Integer): String;
var
  Dir, Uninst, Icon: String;
begin
  Result := '';
  if RegQueryStringValue(RootKey, UninstallKey, 'InstallLocation', Dir) and (Dir <> '') then
  begin
    Result := RemoveBackslashUnlessRoot(Dir);
    Exit;
  end;
  { Fall back to the folder of UninstallString / DisplayIcon when InstallLocation is empty }
  if RegQueryStringValue(RootKey, UninstallKey, 'UninstallString', Uninst) and (Uninst <> '') then
  begin
    StringChangeEx(Uninst, '"', '', True);
    Dir := ExtractFilePath(Uninst);
    if Dir <> '' then
    begin
      Result := RemoveBackslashUnlessRoot(Dir);
      Exit;
    end;
  end;
  if RegQueryStringValue(RootKey, UninstallKey, 'DisplayIcon', Icon) and (Icon <> '') then
  begin
    if Pos(',', Icon) > 0 then
      Icon := Copy(Icon, 1, Pos(',', Icon) - 1);
    StringChangeEx(Icon, '"', '', True);
    Dir := ExtractFilePath(Icon);
    if Dir <> '' then
      Result := RemoveBackslashUnlessRoot(Dir);
  end;
end;

function QueryUninstallInstallLocation(PreferCurrentUser: Boolean): String;
begin
  { Same-mode hive only — cross-mode uninstall entries are inspected separately as stale.
    The AppId is shared with PDF Editor, so this also finds a PDF Editor installation. }
  Result := '';
  if PreferCurrentUser then
    Result := DirFromUninstallMetadata(HKCU)
  else
  begin
    Result := DirFromUninstallMetadata(HKLM32);
    if (Result = '') and IsWin64 then
      Result := DirFromUninstallMetadata(HKLM64);
  end;
end;

function AppPathsDirFor(RootKey: Integer; const Exe: String): String;
var
  Path: String;
begin
  Result := '';
  if RegQueryStringValue(RootKey, 'Software\Microsoft\Windows\CurrentVersion\App Paths\' + Exe, '', Path) and (Path <> '') then
    Result := ExtractFilePath(Path);
end;

function QueryAppPathsDir(PreferCurrentUser: Boolean): String;
begin
  { App Paths for this Setup mode's hive only (no cross-hive fallback): MonographPDF.exe first,
    then PDF Editor's PDF_editor.exe }
  Result := '';
  if PreferCurrentUser then
  begin
    Result := AppPathsDirFor(HKCU, '{#AppExe}');
    if Result = '' then
      Result := AppPathsDirFor(HKCU, '{#LegacyExe}');
  end
  else
  begin
    Result := AppPathsDirFor(HKLM32, '{#AppExe}');
    if (Result = '') and IsWin64 then
      Result := AppPathsDirFor(HKLM64, '{#AppExe}');
    if Result = '' then
      Result := AppPathsDirFor(HKLM32, '{#LegacyExe}');
    if (Result = '') and IsWin64 then
      Result := AppPathsDirFor(HKLM64, '{#LegacyExe}');
  end;
  Result := RemoveBackslashUnlessRoot(Result);
end;

function ResolveShortcutTarget(const LnkPath: String): String;
var
  Shell, Shortcut: Variant;
begin
  Result := '';
  if not FileExists(LnkPath) then
    Exit;
  try
    Shell := CreateOleObject('WScript.Shell');
    Shortcut := Shell.CreateShortcut(LnkPath);
    Result := Shortcut.TargetPath;
  except
    Log('Could not resolve shortcut: ' + LnkPath);
  end;
end;

function QueryStartMenuInstallDir(const SkipProgramFiles: Boolean): String;
var
  Lnk, Target, Dir: String;
  Candidates: array[0..3] of String;
  I: Integer;
begin
  { Fallback only: a verified Start Menu shortcut whose target is MonographPDF.exe (or PDF Editor's
    PDF_editor.exe). Do not use the group constant here — it is not initialized during InitializeSetup.
    SkipProgramFiles (a /CURRENTUSER run): a machine install's shortcut is noted and skipped, so the
    search goes on to this user's own (for example an unregistered PDF Editor in a custom folder). }
  Result := '';
  Candidates[0] := ExpandConstant('{userprograms}\{#AppName}\{#AppName}.lnk');
  Candidates[1] := ExpandConstant('{commonprograms}\{#AppName}\{#AppName}.lnk');
  Candidates[2] := ExpandConstant('{userprograms}\{#LegacyName}\{#LegacyName}.lnk');
  Candidates[3] := ExpandConstant('{commonprograms}\{#LegacyName}\{#LegacyName}.lnk');
  for I := 0 to 3 do
  begin
    Lnk := Candidates[I];
    Target := ResolveShortcutTarget(Lnk);
    if (Target <> '') and FileExists(Target) and
       ((CompareText(ExtractFileName(Target), '{#AppExe}') = 0) or
        (CompareText(ExtractFileName(Target), '{#LegacyExe}') = 0)) then
    begin
      Dir := RemoveBackslashUnlessRoot(ExtractFilePath(Target));
      if LooksLikeInstall(Dir) then
      begin
        if SkipProgramFiles and IsInside(Dir, ExpandConstant('{pf}')) then
        begin
          { Same note as NoteStaleCandidate (declared further down) }
          Log('Detected additional Monograph PDF / PDF Editor folder (Start Menu (machine install)): ' + Dir +
              ' (left untouched; registered install is authoritative)');
          if StaleInstallNote = '' then
            StaleInstallNote := Dir
          else if Pos(Dir, StaleInstallNote) = 0 then
            StaleInstallNote := StaleInstallNote + '; ' + Dir;
        end
        else
        begin
          Result := Dir;
          Exit;
        end;
      end;
    end;
  end;
end;

procedure NoteStaleCandidate(const Dir, Why, Authoritative: String);
begin
  if (Dir = '') or SameInstallPath(Dir, Authoritative) then
    Exit;
  if not LooksLikeInstall(Dir) then
    Exit;
  Log('Detected additional Monograph PDF / PDF Editor folder (' + Why + '): ' + Dir +
      ' (left untouched; registered install is authoritative)');
  if StaleInstallNote = '' then
    StaleInstallNote := Dir
  else if Pos(Dir, StaleInstallNote) = 0 then
    StaleInstallNote := StaleInstallNote + '; ' + Dir;
end;

function PickDefault(const NewDir, LegacyDir: String): String;
begin
  { The default folder that holds an installation: Monograph PDF's, else PDF Editor's }
  if LooksLikeInstall(NewDir) then
    Result := NewDir
  else if LooksLikeInstall(LegacyDir) then
    Result := LegacyDir
  else
    Result := NewDir;
end;

function DetectExistingInstallDir(): String;
var
  Candidate, DefaultPf, DefaultUser, OtherModeAppPaths: String;
  PreferCU: Boolean;
begin
  { Priority: uninstall AppId registry → App Paths → known defaults → verified Start Menu (fallback).
    Monograph PDF and PDF Editor locations both count (same AppId; MonographPDF.exe or PDF_editor.exe).
    Prefer the registry hive matching this Setup mode so a machine install does not capture a
    /CURRENTUSER run (and vice versa). Cross-mode copies are noted and left untouched. }
  Result := '';
  StaleInstallNote := '';
  PreferCU := SetupPrefersCurrentUser();

  Candidate := QueryUninstallInstallLocation(PreferCU);
  if LooksLikeInstall(Candidate) then
    Result := RemoveBackslashUnlessRoot(Candidate)
  else if Candidate <> '' then
    Log('Uninstall InstallLocation has no MonographPDF.exe or PDF_editor.exe: ' + Candidate);

  { Same-mode App Paths; opposite-hive App Paths are stale/cross-mode evidence only. }
  Candidate := QueryAppPathsDir(PreferCU);
  OtherModeAppPaths := QueryAppPathsDir(not PreferCU);
  if Result = '' then
  begin
    if LooksLikeInstall(Candidate) then
      Result := Candidate;
  end
  else
    NoteStaleCandidate(Candidate, 'App Paths', Result);
  NoteStaleCandidate(OtherModeAppPaths, 'cross-mode App Paths', Result);
  { Also note opposite-hive uninstall metadata when present }
  NoteStaleCandidate(QueryUninstallInstallLocation(not PreferCU), 'cross-mode uninstall registry', Result);

  { pf constant is always Program Files; autopf follows the current install mode. }
  DefaultPf := PickDefault(ExpandConstant('{pf}\{#AppName}'), ExpandConstant('{pf}\{#LegacyName}'));
  DefaultUser := PickDefault(ExpandConstant('{localappdata}\Programs\{#AppName}'),
                             ExpandConstant('{localappdata}\Programs\{#LegacyName}'));
  if Result = '' then
  begin
    { Prefer the default that matches this Setup mode }
    if PreferCU then
    begin
      if LooksLikeInstall(DefaultUser) then
        Result := RemoveBackslashUnlessRoot(DefaultUser)
      else
        NoteStaleCandidate(DefaultPf, 'default Program Files (other mode)', Result);
    end
    else
    begin
      if LooksLikeInstall(DefaultPf) then
        Result := RemoveBackslashUnlessRoot(DefaultPf)
      else if LooksLikeInstall(DefaultUser) then
        Result := RemoveBackslashUnlessRoot(DefaultUser);
    end;
  end
  else
  begin
    NoteStaleCandidate(ExpandConstant('{pf}\{#AppName}'), 'default Program Files', Result);
    NoteStaleCandidate(ExpandConstant('{pf}\{#LegacyName}'), 'PDF Editor default Program Files', Result);
    NoteStaleCandidate(ExpandConstant('{localappdata}\Programs\{#AppName}'), 'default per-user Programs', Result);
    NoteStaleCandidate(ExpandConstant('{localappdata}\Programs\{#LegacyName}'), 'PDF Editor default per-user Programs', Result);
  end;

  Candidate := QueryStartMenuInstallDir(PreferCU);
  if Result = '' then
  begin
    if Candidate <> '' then
    begin
      { Start Menu fallback: never promote a machine Program Files target during /CURRENTUSER }
      if PreferCU and IsInside(Candidate, ExpandConstant('{pf}')) then
        NoteStaleCandidate(Candidate, 'Start Menu (machine install)', Result)
      else
      begin
        Result := Candidate;
        Log('Existing install inferred from verified Start Menu shortcut (fallback): ' + Result);
      end;
    end;
  end
  else
    NoteStaleCandidate(Candidate, 'Start Menu shortcut', Result);

  { Interactive only: if this mode has no install but another mode does, use it for the
    folder-choice dialog (silent keeps same-mode only so /CURRENTUSER tests stay isolated). }
  if (Result = '') and (not WizardSilent) and LooksLikeInstall(OtherModeAppPaths) then
  begin
    Result := RemoveBackslashUnlessRoot(OtherModeAppPaths);
    Log('Interactive: using cross-mode install for migration dialog: ' + Result);
  end
  else if (Result = '') and (not WizardSilent) and LooksLikeInstall(DefaultPf) and PreferCU then
  begin
    Result := RemoveBackslashUnlessRoot(DefaultPf);
    Log('Interactive: using Program Files install for migration dialog: ' + Result);
  end;

  if Result <> '' then
  begin
    if IsLegacyInstallDir(Result) then
      Log('Authoritative existing install: PDF Editor (PDF_editor.exe) at ' + Result)
    else
      Log('Authoritative existing install: Monograph PDF at ' + Result);
  end;
  if StaleInstallNote <> '' then
    Log('Unregistered Monograph PDF / PDF Editor folder(s) noted (not deleted): ' + StaleInstallNote);
end;

function RenamedLegacyDir(const OldDir: String): String;
var
  Parent, Candidate: String;
begin
  { "...\PDF Editor" -> "...\Monograph PDF" (same parent: Program Files, per-user Programs or a
    custom folder). '' when the folder has another name, or the new folder already holds
    something other than Monograph PDF (then the existing location is kept). }
  Result := '';
  if CompareText(ExtractFileName(RemoveBackslashUnlessRoot(OldDir)), '{#LegacyName}') <> 0 then
    Exit;
  Parent := ExtractFilePath(RemoveBackslashUnlessRoot(OldDir));
  if Parent = '' then
    Exit;
  Candidate := AddBackslash(Parent) + '{#AppName}';
  if DirExists(Candidate) and not FileExists(AddBackslash(Candidate) + '{#AppExe}') then
  begin
    Log('Not suggesting ' + Candidate + ': the folder already exists');
    Exit;
  end;
  if not IsAcceptableInstallRoot(Candidate) then
    Exit;
  Result := Candidate;
end;

procedure RemoveOwnedRelUnder(const Base, Rel: String);
var
  Full, Norm: String;
begin
  { Delete one owned relative path under Base; never leave Base itself }
  Norm := Rel;
  StringChangeEx(Norm, '/', '\', True);
  while (Length(Norm) > 0) and (Norm[1] = '\') do
    Delete(Norm, 1, 1);
  if not IsSafeRelPath(Norm) then
  begin
    Log('Upgrade cleanup: rejected unsafe path "' + Rel + '"');
    Exit;
  end;
  if not IsAcceptableInstallRoot(Base) then
  begin
    Log('Upgrade cleanup: refused base ' + Base);
    Exit;
  end;
  Full := AddBackslash(Base) + Norm;
  if not IsInside(Full, Base) then
  begin
    Log('Upgrade cleanup: path escapes install dir: ' + Full);
    Exit;
  end;
  if CompareText(AddBackslash(Full), AddBackslash(Base)) = 0 then
    Exit;
  if IsReparsePoint(Full) then
  begin
    Log('Upgrade cleanup: skipped reparse point ' + Full);
    Exit;
  end;
  if DirExists(Full) then
  begin
    DelTree(Full, True, True, True);
    if DirExists(Full) then
      Log('Upgrade cleanup: could not remove dir ' + Full)
    else
      Log('Upgrade cleanup: removed dir ' + Full);
  end
  else if FileExists(Full) then
  begin
    if DeleteFile(Full) then
      Log('Upgrade cleanup: removed file ' + Full)
    else
      Log('Upgrade cleanup: could not remove file ' + Full);
  end;
end;

procedure CleanLegacyOwnedAt(const Base: String);
begin
  { Conservative allowlist for installs that have no installed_files.txt yet (PDF Editor <= 0.1.5) }
  if not IsAcceptableInstallRoot(Base) then
    Exit;
  RemoveOwnedRelUnder(Base, '_internal');
  RemoveOwnedRelUnder(Base, 'engines');
  RemoveOwnedRelUnder(Base, 'models');
  RemoveOwnedRelUnder(Base, 'docs');
  RemoveOwnedRelUnder(Base, 'licenses');
  RemoveOwnedRelUnder(Base, 'logs');
  RemoveOwnedRelUnder(Base, 'runtime');
  RemoveOwnedRelUnder(Base, 'packages');
  RemoveOwnedRelUnder(Base, '{#AppExe}');
  RemoveOwnedRelUnder(Base, '{#LegacyExe}');
  RemoveOwnedRelUnder(Base, 'uninstall.exe');
  RemoveOwnedRelUnder(Base, 'MonographPDFUpdater.exe');
  RemoveOwnedRelUnder(Base, 'README.md');
  RemoveOwnedRelUnder(Base, 'LICENSE.md');
  RemoveOwnedRelUnder(Base, 'THIRD_PARTY_NOTICES.md');
  RemoveOwnedRelUnder(Base, 'SECURITY.md');
  RemoveOwnedRelUnder(Base, 'CHANGELOG.md');
  RemoveOwnedRelUnder(Base, 'installed_files.txt');
  RemoveOwnedRelUnder(Base, 'installed_files.json');
end;

procedure CleanFromManifestFile(const Base, ManifestFile: String);
var
  Lines: TArrayOfString;
  I: Integer;
  Line: String;
begin
  if not FileExists(ManifestFile) then
    Exit;
  if not LoadStringsFromFile(ManifestFile, Lines) then
  begin
    Log('Upgrade cleanup: could not read ' + ManifestFile);
    Exit;
  end;
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Trim(Lines[I]);
    if (Line = '') or (Line[1] = '#') then
      Continue;
    RemoveOwnedRelUnder(Base, Line);
  end;
end;

procedure SnapshotPreviousManifest();
var
  Src, Dst, OldSrc: String;
begin
  Dst := ExpandConstant('{tmp}\' + PrevManifestTmp);
  if CleanOldLocationAfterInstall and (PreviousInstallDir <> '') then
  begin
    { Migrating: keep OLD manifest for post-success cleanup only.
      Do not apply OLD's list to NEW_PATH before copy. }
    OldSrc := AddBackslash(PreviousInstallDir) + 'installed_files.txt';
    if FileExists(OldSrc) then
    begin
      if FileCopy(OldSrc, ExpandConstant('{tmp}\old_location_installed_files.txt'), False) then
        Log('Upgrade cleanup: snapshot OLD location owned-file list from ' + OldSrc)
      else
        Log('Upgrade cleanup: could not snapshot OLD owned-file list');
    end;
    { If NEW already has a previous install of its own, snapshot that for in-folder cleanup }
    Src := ExpandConstant('{app}\installed_files.txt');
    if FileExists(Src) and FileCopy(Src, Dst, False) then
      Log('Upgrade cleanup: snapshot NEW location owned-file list from ' + Src);
  end
  else
  begin
    { Same-folder upgrade: snapshot current install-folder owned-file list }
    Src := ExpandConstant('{app}\installed_files.txt');
    if FileExists(Src) then
    begin
      if FileCopy(Src, Dst, False) then
        Log('Upgrade cleanup: snapshot owned-file list from ' + Src)
      else
        Log('Upgrade cleanup: could not snapshot owned-file list');
    end;
  end;
end;

procedure CleanTargetBeforeCopy();
var
  PrevManifest: String;
begin
  { Runs at ssInstall after [InstallDelete]. Removes any leftover owned paths from the
    previous manifest (e.g. obsolete root files). Never deletes unknown user files. }
  if not IsAcceptableInstallRoot(ExpandConstant('{app}')) then
  begin
    Log('Upgrade cleanup: {app} is not an acceptable install root; skipping extra cleanup');
    Exit;
  end;
  PrevManifest := ExpandConstant('{tmp}\' + PrevManifestTmp);
  if FileExists(PrevManifest) then
  begin
    Log('Upgrade cleanup: removing owned paths from previous installed_files.txt');
    CleanFromManifestFile(ExpandConstant('{app}'), PrevManifest);
  end;
end;

function NewInstallLooksValid(): Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\{#AppExe}')) and
            DirExists(ExpandConstant('{app}\_internal')) and
            FileExists(ExpandConstant('{app}\uninstall.exe'));
end;

procedure TryRemoveEmptyDir(const Dir: String);
var
  Rec: TFindRec;
  Empty: Boolean;
begin
  if not DirExists(Dir) or not IsAcceptableInstallRoot(Dir) then
    Exit;
  Empty := True;
  if FindFirst(AddBackslash(Dir) + '*', Rec) then
  try
    repeat
      if (Rec.Name <> '.') and (Rec.Name <> '..') then
        Empty := False;
    until (not Empty) or (not FindNext(Rec));
  finally
    FindClose(Rec);
  end;
  if Empty then
  begin
    if RemoveDir(Dir) then
      Log('Upgrade cleanup: removed empty previous folder ' + Dir)
    else
      Log('Upgrade cleanup: previous folder empty but could not remove ' + Dir);
  end
  else
    Log('Upgrade cleanup: previous folder kept (unknown/user files remain): ' + Dir);
end;

procedure CleanPreviousLocationIfMoved();
var
  OldManifest: String;
begin
  { Only after the NEW install has been validated — never delete OLD first }
  if not CleanOldLocationAfterInstall then
    Exit;
  if (PreviousInstallDir = '') or SameInstallPath(PreviousInstallDir, ExpandConstant('{app}')) then
    Exit;
  if (not NewInstallLooksValid()) or (not SmokeTestPassed) then
  begin
    Log('Upgrade cleanup: NEW install not validated (files/smoke); leaving OLD location intact: ' +
        PreviousInstallDir);
    Exit;
  end;
  if not DirExists(PreviousInstallDir) then
    Exit;
  if not IsAcceptableInstallRoot(PreviousInstallDir) then
  begin
    Log('Upgrade cleanup: refused to clean previous location ' + PreviousInstallDir);
    Exit;
  end;
  Log('Upgrade cleanup: removing owned files from previous location ' + PreviousInstallDir);
  OldManifest := ExpandConstant('{tmp}\old_location_installed_files.txt');
  if FileExists(OldManifest) then
    CleanFromManifestFile(PreviousInstallDir, OldManifest)
  else if FileExists(AddBackslash(PreviousInstallDir) + 'installed_files.txt') then
    CleanFromManifestFile(PreviousInstallDir, AddBackslash(PreviousInstallDir) + 'installed_files.txt')
  else
    CleanLegacyOwnedAt(PreviousInstallDir);
  { Manifest lists files, not directory entries — remove leftover owned trees/empty shells }
  CleanLegacyOwnedAt(PreviousInstallDir);
  { Inno leftover uninstaller files at OLD when safe }
  RemoveOwnedRelUnder(PreviousInstallDir, 'unins000.exe');
  RemoveOwnedRelUnder(PreviousInstallDir, 'unins000.dat');
  TryRemoveEmptyDir(PreviousInstallDir);
end;

{ ---------------------------------------------------------------- PDF Editor registrations }

function AppRoot(): Integer;
begin
  { The hive Setup writes to: HKLM for all users, HKCU for the current user only }
  if IsAdminInstallMode then
    Result := HKLM
  else
    Result := HKCU;
end;

function ExeFromCommand(const Cmd: String): String;
var
  P: Integer;
begin
  { "C:\...\x.exe" "%1"  |  C:\...\x.exe,0  ->  C:\...\x.exe }
  Result := Trim(Cmd);
  if (Result <> '') and (Result[1] = '"') then
  begin
    Delete(Result, 1, 1);
    P := Pos('"', Result);
    if P > 0 then
      Result := Copy(Result, 1, P - 1);
  end
  else
  begin
    P := Pos(',', Result);
    if P > 0 then
      Result := Copy(Result, 1, P - 1);
  end;
end;

function IsRemovedLegacyExe(const Exe: String): Boolean;
begin
  { A registration belongs to PDF Editor and its program is gone (the upgrade replaced it) }
  Result := (Exe <> '') and (CompareText(ExtractFileName(Exe), '{#LegacyExe}') = 0) and not FileExists(Exe);
end;

procedure RemoveLegacyKey(const Subkey, ValueKey, ValueName: String);
var
  Value: String;
begin
  if not RegQueryStringValue(AppRoot(), ValueKey, ValueName, Value) then
    Exit;
  if not IsRemovedLegacyExe(ExeFromCommand(Value)) then
  begin
    Log('PDF Editor registration kept (its program still exists): ' + Subkey);
    Exit;
  end;
  if RegDeleteKeyIncludingSubkeys(AppRoot(), Subkey) then
    Log('Removed PDF Editor registration: ' + Subkey)
  else
    Log('Could not remove PDF Editor registration: ' + Subkey);
end;

procedure RemoveLegacyOpenWith(const Ext, ProgId: String);
begin
  { The Open with entry of a PDF Editor ProgID that no longer exists }
  if RegKeyExists(AppRoot(), 'Software\Classes\' + ProgId) then
    Exit;
  if RegValueExists(AppRoot(), 'Software\Classes\' + Ext + '\OpenWithProgids', ProgId) then
  begin
    RegDeleteValue(AppRoot(), 'Software\Classes\' + Ext + '\OpenWithProgids', ProgId);
    Log('Removed ' + ProgId + ' from Open with for ' + Ext);
  end;
end;

procedure RemoveLegacyRegistrations();
var
  Exts: String;
  I: Integer;
begin
  { After a PDF Editor installation was upgraded or moved and its PDF_editor.exe is gone: remove the
    App Paths entry, Applications entry, ProgIDs, Open with entries and Default apps capability that
    point to it. Entries whose program still exists (an unregistered second copy) are left alone. }
  RemoveLegacyKey('Software\Microsoft\Windows\CurrentVersion\App Paths\{#LegacyExe}',
                  'Software\Microsoft\Windows\CurrentVersion\App Paths\{#LegacyExe}', '');
  RemoveLegacyKey('Software\Classes\Applications\{#LegacyExe}',
                  'Software\Classes\Applications\{#LegacyExe}\shell\open\command', '');
  RemoveLegacyKey('Software\Classes\{#LegacyProgIdPdf}', 'Software\Classes\{#LegacyProgIdPdf}\shell\open\command', '');
  RemoveLegacyKey('Software\Classes\{#LegacyProgIdOther}', 'Software\Classes\{#LegacyProgIdOther}\shell\open\command', '');
  RemoveLegacyOpenWith('.pdf', '{#LegacyProgIdPdf}');
  Exts := '.png .jpg .jpeg .tif .tiff .bmp .gif .webp .docx .doc .rtf .odt .xlsx .xls .csv .ods .pptx .ppt .odp ';
  while Exts <> '' do
  begin
    I := Pos(' ', Exts);
    RemoveLegacyOpenWith(Copy(Exts, 1, I - 1), '{#LegacyProgIdOther}');
    Delete(Exts, 1, I);
  end;
  RemoveLegacyKey('{#LegacyRegKey}\Capabilities', '{#LegacyRegKey}\Capabilities', 'ApplicationIcon');
  if not RegKeyExists(AppRoot(), '{#LegacyRegKey}\Capabilities') then
  begin
    RegDeleteKeyIfEmpty(AppRoot(), '{#LegacyRegKey}');
    if RegValueExists(AppRoot(), 'Software\RegisteredApplications', '{#LegacyName}') then
    begin
      RegDeleteValue(AppRoot(), 'Software\RegisteredApplications', '{#LegacyName}');
      Log('Removed PDF Editor from Default apps (RegisteredApplications)');
    end;
  end;
end;

procedure RemoveLegacyShortcut(const Lnk: String);
var
  Target: String;
begin
  { A PDF Editor shortcut whose program is gone (never a shortcut to anything else) }
  if not FileExists(Lnk) then
    Exit;
  Target := ResolveShortcutTarget(Lnk);
  if IsRemovedLegacyExe(Target) or
     ((CompareText(ExtractFileName(Target), 'unins000.exe') = 0) and not FileExists(Target)) then
  begin
    if DeleteFile(Lnk) then
      Log('Removed PDF Editor shortcut ' + Lnk)
    else
      Log('Could not remove PDF Editor shortcut ' + Lnk);
  end
  else
    Log('PDF Editor shortcut kept (target still exists or is not PDF Editor): ' + Lnk);
end;

procedure RemoveLegacyShortcuts();
var
  Group: String;
begin
  Group := ExpandConstant('{autoprograms}\{#LegacyName}');
  RemoveLegacyShortcut(Group + '\{#LegacyName}.lnk');
  RemoveLegacyShortcut(Group + '\{#LegacyName} User Guide.lnk');
  RemoveLegacyShortcut(Group + '\User Guide.lnk');
  RemoveLegacyShortcut(Group + '\Uninstall {#LegacyName}.lnk');
  if DirExists(Group) and RemoveDir(Group) then
    Log('Removed empty Start menu folder ' + Group);
  RemoveLegacyShortcut(ExpandConstant('{autodesktop}\{#LegacyName}.lnk'));
end;

function LegacyAppStillPresent(): Boolean;
begin
  { A PDF Editor program still exists (e.g. an unregistered second copy) }
  Result := FileExists(ExpandConstant('{pf}\{#LegacyName}\{#LegacyExe}')) or
            FileExists(ExpandConstant('{localappdata}\Programs\{#LegacyName}\{#LegacyExe}')) or
            (AppPathsDirFor(HKCU, '{#LegacyExe}') <> '') or
            (AppPathsDirFor(HKLM32, '{#LegacyExe}') <> '') or
            (IsWin64 and (AppPathsDirFor(HKLM64, '{#LegacyExe}') <> ''));
end;

function EnsureAppClosedForSetup(): Boolean;
var
  StillRunning: Boolean;
begin
  { CloseApplications may already have asked; refuse silent install if still running
    from the target folder or (when migrating) from the old folder. }
  Result := True;
  while True do
  begin
    StillRunning := RunningCopies(False) > 0;
    if (not StillRunning) and (LegacyUpgrade or CleanOldLocationAfterInstall) and (PreviousInstallDir <> '') then
    begin
      { Also refuse if a copy from the old path is running — RunningCopies(False) already
        scopes to the install folder; when migrating, expand the check to any copy. }
      StillRunning := RunningCopies(True) > 0;
    end;
    if not StillRunning then
      Exit;
    if WizardSilent then
    begin
      Log(RunningAppName() + ' is running; silent Setup stopped');
      Result := False;
      Exit;
    end;
    if MsgBox(RunningAppName() + ' is running.' + #13#10#13#10 +
              'Save your work and close every ' + RunningAppName() + ' window, then click Retry.' + #13#10 +
              'Click Cancel to stop Setup.', mbError, MB_RETRYCANCEL) <> IDRETRY then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function CmdHasSwitch(const Name: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Name) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

function CmdHasDir(): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(Copy(ParamStr(I), 1, 5), '/DIR=') = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

{ ---------------------------------------------------------------- Setup }

function InitializeSetup(): Boolean;
begin
  { An upgrade keeps the recent-files list; a new install starts with an empty one.
    Only same-mode evidence counts as PreviousInstall so a machine copy does not skip
    history clean-up for a silent /CURRENTUSER first install. }
  PreviousInstallDir := DetectExistingInstallDir();
  if SetupPrefersCurrentUser() then
    PreviousInstall := (PreviousInstallDir <> '') or RegKeyExists(HKCU, UninstallKey)
  else
  begin
    PreviousInstall := (PreviousInstallDir <> '') or RegKeyExists(HKLM32, UninstallKey);
    if IsWin64 then
      PreviousInstall := PreviousInstall or RegKeyExists(HKLM64, UninstallKey);
  end;
  LegacyUpgrade := IsLegacyInstallDir(PreviousInstallDir);
  RenamedDir := '';
  if LegacyUpgrade then
  begin
    RenamedDir := RenamedLegacyDir(PreviousInstallDir);
    Log('PDF Editor upgrade: existing installation ' + PreviousInstallDir +
        '; suggested Monograph PDF folder: ' + RenamedDir);
  end;
  CleanOldLocationAfterInstall := False;
  MigrateInstallFlag := CmdHasSwitch('/MIGRATEINSTALL');
  SmokeTestPassed := False;
  Result := True;
end;

procedure InitializeWizard();
var
  Body: String;
begin
  if LegacyUpgrade then
  begin
    Body := 'An existing installation was found at:' + #13#10 + PreviousInstallDir + #13#10#13#10 +
            'Monograph PDF can upgrade this installation while preserving your settings and documents.';
    UpgradePage := CreateInputOptionPage(wpLicense, 'Existing installation found',
      'Setup found an existing installation on this computer.', Body, True, False);
    if RenamedDir <> '' then
    begin
      UpgradePage.Add('Install Monograph PDF in ' + RenamedDir + ' and remove the previous application (recommended)');
      UpgradePage.Add('Upgrade using the existing installation location (' + PreviousInstallDir + ')');
    end
    else
      UpgradePage.Add('Upgrade using the existing installation location (' + PreviousInstallDir + ') (recommended)');
    UpgradePage.SelectedValueIndex := 0;
  end;

  if not WizardSilent then
    Exit;
  { Silent different-/DIR without /MIGRATEINSTALL: keep the registered location (no duplicate). }
  if (PreviousInstallDir <> '') and (not MigrateInstallFlag) then
  begin
    if not SameInstallPath(WizardDirValue, PreviousInstallDir) then
    begin
      Log('Silent Setup: /DIR differs from registered install; keeping existing location ' +
          PreviousInstallDir + ' (pass /MIGRATEINSTALL to move)');
      WizardForm.DirEdit.Text := PreviousInstallDir;
      CleanOldLocationAfterInstall := False;
    end;
  end;
  { Silent /MIGRATEINSTALL without /DIR on an earlier-internal folder: move to Monograph PDF folder }
  if LegacyUpgrade and MigrateInstallFlag and (not CmdHasDir()) and (RenamedDir <> '') and
     SameInstallPath(WizardDirValue, PreviousInstallDir) then
  begin
    Log('Silent /MIGRATEINSTALL: moving PDF Editor from ' + PreviousInstallDir + ' to ' + RenamedDir);
    WizardForm.DirEdit.Text := RenamedDir;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (UpgradePage <> nil) and (PageID = UpgradePage.ID) then
    Result := not LegacyUpgrade;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Chosen, Prev: String;
begin
  Result := True;
  if (UpgradePage <> nil) and (CurPageID = UpgradePage.ID) then
  begin
    if (RenamedDir <> '') and (UpgradePage.SelectedValueIndex = 0) then
    begin
      WizardForm.DirEdit.Text := RenamedDir;
      CleanOldLocationAfterInstall := True;
      Log('User chose: install Monograph PDF in ' + RenamedDir + ' and remove PDF Editor from ' + PreviousInstallDir);
    end
    else
    begin
      WizardForm.DirEdit.Text := PreviousInstallDir;
      CleanOldLocationAfterInstall := False;
      Log('User chose: upgrade PDF Editor in its existing location ' + PreviousInstallDir);
    end;
    Exit;
  end;
  if (CurPageID = wpSelectDir) and (PreviousInstallDir <> '') then
  begin
    Chosen := RemoveBackslashUnlessRoot(WizardDirValue);
    Prev := RemoveBackslashUnlessRoot(PreviousInstallDir);
    if SameInstallPath(Chosen, Prev) then
    begin
      CleanOldLocationAfterInstall := False;
      Exit;
    end;
    if LegacyUpgrade and SameInstallPath(Chosen, RenamedDir) then
    begin
      { The move chosen on the Upgrade to Monograph PDF page }
      CleanOldLocationAfterInstall := True;
      Exit;
    end;
    { Different destination — clear labelled choices (Yes = recommended keep existing) }
    case MsgBox(
      RunningAppName() + ' is already installed at:' + #13#10 + Prev + #13#10#13#10 +
      'You selected a different installation folder:' + #13#10 + Chosen + #13#10#13#10 +
      'Yes — Upgrade using the existing installation location (recommended)' + #13#10 +
      '    Monograph PDF replaces the previous version at the current path.' + #13#10 +
      '    Your settings and documents are preserved.' + #13#10#13#10 +
      'No — Install Monograph PDF in the new location and remove the previous ' + RunningAppName() + ' application' + #13#10 +
      '    After the new installation has been checked, the previous application files are removed' + #13#10 +
      '    from the old folder (files you added there are kept). Settings and documents are preserved.' + #13#10#13#10 +
      'Cancel — Go back',
      mbConfirmation, MB_YESNOCANCEL or MB_DEFBUTTON1) of
      IDYES:
        begin
          { Recommended: force in-place upgrade at the registered location }
          WizardForm.DirEdit.Text := Prev;
          CleanOldLocationAfterInstall := False;
          Log('User chose upgrade in existing location: ' + Prev);
        end;
      IDNO:
        begin
          CleanOldLocationAfterInstall := True;
          Log('User chose migrate to new location: ' + Chosen + ' (old: ' + Prev + ')');
        end;
      else
        begin
          Result := False;
          Exit;
        end;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  NeedsRestart := False;
  Result := '';
  { Silent different-directory policy (InitializeWizard already redirects without the flag):
      - default: upgrade at the existing registered path (no duplicate install)
      - /MIGRATEINSTALL: install to the requested /DIR (or, for a "PDF Editor" folder without /DIR,
        to the "Monograph PDF" folder) and remove owned files at OLD after success
     Resolve migration intent before the running-app check so OLD_PATH processes are covered. }
  if WizardSilent and (PreviousInstallDir <> '') and
     (not SameInstallPath(PreviousInstallDir, ExpandConstant('{app}'))) then
  begin
    if MigrateInstallFlag then
    begin
      CleanOldLocationAfterInstall := True;
      Log('Silent /MIGRATEINSTALL: installing to ' + ExpandConstant('{app}') +
          '; will clean owned files at ' + PreviousInstallDir + ' after success');
    end
    else
    begin
      { Safety net if DirEdit override did not apply }
      Log('Silent Setup safety: forcing existing location ' + PreviousInstallDir);
      WizardForm.DirEdit.Text := PreviousInstallDir;
      CleanOldLocationAfterInstall := False;
    end;
  end;
  if not EnsureAppClosedForSetup() then
  begin
    Result := RunningAppName() + ' is still running. Close it and run Setup again.';
    Exit;
  end;
  SnapshotPreviousManifest();
end;

procedure RemoveDeselectedShortcuts();
begin
  { On upgrade, a shortcut whose task is now unchecked is removed }
  if not WizardIsTaskSelected('desktopicon') then
    DeleteFile(ExpandConstant('{autodesktop}\{#AppName}.lnk'));
  if not WizardIsTaskSelected('startmenu') then
    DelTree(ExpandConstant('{group}'), True, True, True);
end;

procedure RegisterUninstallExe();
var
  Exe: String;
begin
  { Settings > Apps > Uninstall runs uninstall.exe (it starts unins000.exe and waits for it) }
  Exe := ExpandConstant('{app}\uninstall.exe');
  if not FileExists(Exe) then
    Exit;
  if RegWriteStringValue(AppRoot(), UninstallKey, 'UninstallString', '"' + Exe + '"') and
     RegWriteStringValue(AppRoot(), UninstallKey, 'QuietUninstallString', '"' + Exe + '" /SILENT') then
    Log('Registered ' + Exe + ' as the uninstaller')
  else
    Log('Could not register ' + Exe + '; Windows keeps using unins000.exe');
end;

procedure RunSmokeTest();
var
  ResultCode: Integer;
  RuntimeDir, Report, LogDir, LogFile, Params: String;
begin
  SmokeTestPassed := False;
  if not NewInstallLooksValid() then
  begin
    Log('Self-test skipped: new install files incomplete');
    Exit;
  end;
  RuntimeDir := ExpandConstant('{tmp}\smoke-runtime');
  Report := ExpandConstant('{tmp}\install_smoke_test.json');
  Params := '--smoke-test --runtime-dir "' + RuntimeDir + '" --report "' + Report + '"';
  WizardForm.StatusLabel.Caption := 'Checking that Monograph PDF works on this computer...';
  Log('Running self-test: ' + Params);
  if Exec(ExpandConstant('{app}\{#AppExe}'), Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Log('Self-test exit code: ' + IntToStr(ResultCode));
    SmokeTestPassed := (ResultCode = 0);
    { The report goes to the user's working-files folder: the installation folder holds only
      Monograph PDF's own files }
    LogDir := ExpandConstant('{localappdata}\' + DataFolderName + '\logs');
    LogFile := LogDir + '\install_smoke_test.json';
    ForceDirectories(LogDir);
    FileCopy(Report, LogFile, False);
    if (not SmokeTestPassed) and (not WizardSilent) then
      MsgBox('Monograph PDF was installed, but its self-check reported a problem.' + #13#10#13#10 +
             'Details were saved to:' + #13#10 + LogFile + #13#10#13#10 +
             'Try running Setup again. If the problem continues, check your antivirus quarantine.',
             mbError, MB_OK);
  end
  else
    Log('Self-test could not start: ' + SysErrorMessage(ResultCode));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    if not PreviousInstall then
    begin
      Log('New install: clearing recent files and saved sessions');
      ClearUserHistory();
    end
    else
      Log('Upgrade: keeping settings and recent-files list');
    { After [InstallDelete], remove any leftover owned paths from the previous manifest }
    CleanTargetBeforeCopy();
  end;
  if CurStep = ssPostInstall then
  begin
    RemoveDeselectedShortcuts();
    RegisterUninstallExe();
    { Validate NEW install before any OLD-location owned-file cleanup }
    RunSmokeTest();
    CleanPreviousLocationIfMoved();
    { PDF Editor's registrations and shortcuts, once its program is gone. Settings are copied
      by Monograph PDF itself at its first start for each user (the PDF Editor folders are kept). }
    if LegacyUpgrade or (PreviousInstallDir <> '') then
    begin
      RemoveLegacyRegistrations();
      RemoveLegacyShortcuts();
    end;
  end;
end;

{ ---------------------------------------------------------------- Uninstall }

function InitializeUninstall(): Boolean;
begin
  Result := True;
  RemoveUserData := CmdHasSwitch('/REMOVEUSERDATA');
  NotRemoved := '';
  LegacyDataAllowed := False;
  if RemoveUserData then
    Log('/REMOVEUSERDATA: settings will be removed too');

  while RunningCopies(False) > 0 do
  begin
    if UninstallSilent then
    begin
      Log('Monograph PDF is running; uninstall stopped. Close Monograph PDF and run the uninstaller again.');
      Result := False;
      Exit;
    end;
    if MsgBox('Monograph PDF is running.' + #13#10#13#10 +
              'Save your work and close every Monograph PDF window, then click Retry.' + #13#10 +
              'Click Cancel to stop uninstalling.', mbError, MB_RETRYCANCEL) <> IDRETRY then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and (not UninstallSilent) and (not RemoveUserData) then
    RemoveUserData := MsgBox('Do you also want to remove your Monograph PDF settings?' + #13#10#13#10 +
      'Yes: remove everything Monograph PDF stored for you, including the theme, window layout and recently used fonts and colors.' + #13#10 +
      'No: keep these settings for a later installation.' + #13#10#13#10 +
      'The recent-files list and working files (cache and temporary files) are removed either way. ' +
      'Your documents and any files you saved or converted are never removed.',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;

  if CurUninstallStep = usPostUninstall then
  begin
    { PDF Editor's data folders are cleaned only when Monograph PDF migrated them for this user
      (its record is in the Monograph PDF settings folder) and no PDF Editor program remains }
    LegacyDataAllowed := FileExists(ExpandConstant('{userappdata}\') + DataFolderName + '\' + LegacyMigrationRecord) and
                         not LegacyAppStillPresent();
    if LegacyDataAllowed then
      Log('PDF Editor data folders were migrated by Monograph PDF; cleaning them too');
    ClearUserHistory();
    if LegacyDataAllowed then
      ClearHistoryIn(LegacyDataFolderName);
    if RemoveUserData then
    begin
      RemoveFolder(ExpandConstant('{userappdata}\') + DataFolderName);
      if LegacyDataAllowed then
        RemoveFolder(ExpandConstant('{userappdata}\') + LegacyDataFolderName);
    end;
    if NotRemoved <> '' then
    begin
      Log('Not removed:' + NotRemoved);
      if not UninstallSilent then
        MsgBox('Monograph PDF was removed, but these items are in use and could not be deleted:' + #13#10 + NotRemoved + #13#10#13#10 +
               'Close any program that may be using them, then delete them manually (or restart Windows first).',
               mbInformation, MB_OK);
    end;
  end;
end;

#ifdef DumpPreprocessed
  #expr SaveToFile(AddBackslash(SourcePath) + "..\build\installer\MonographPDF.preprocessed.iss")
#endif

[Setup]
AppName=Python Script Manager
AppVersion=0.1.0
DefaultDirName={userappdata}\Programs\PythonScriptManager
DefaultGroupName=Python Script Manager
OutputDir=dist
OutputBaseFilename=PythonScriptManager-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest

[Files]
Source: "..\dist\pysm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Python Script Manager"; Filename: "{app}\pysm.exe"
Name: "{group}\Open Web UI"; Filename: "{cmd}"; Parameters: "/c start http://127.0.0.1:1511"

[Run]
Filename: "{app}\pysm.exe"; Parameters: "serve"; Flags: nowait postinstall skipifsilent


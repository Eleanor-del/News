; ============================================================
;  新闻热点速览 v4.0 - Inno Setup 安装向导
;  编译：ISCC.exe setup_v4.iss
;  前置：先执行 python build.py 生成 dist\新闻热点速览.exe
; ============================================================

[Setup]
; AppId 沿用 v3，安装时会作为「升级」覆盖旧版本，卸载列表里只保留一条记录
AppId={{D0B7F8B6-7F29-4E0A-9C3C-新闻热点速览3}
AppName=新闻热点速览
AppVersion=4.0.1
AppVerName=新闻热点速览 4.0.1
AppPublisher=新闻热点速览
DefaultDirName={autopf}\新闻热点速览
DefaultGroupName=新闻热点速览
OutputBaseFilename=新闻热点速览_安装程序_v4.0.1
OutputDir=installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=app.ico
UninstallDisplayIcon={app}\新闻热点速览.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

; 中文界面文案（无官方中文语言包时的自定义翻译）
[CustomMessages]
chinesesimp.ButtonNext=下一步(&N)>
chinesesimp.ButtonInstall=安装(&I)
chinesesimp.ButtonFinish=完成(&F)
chinesesimp.ButtonBack=<上一步(&B)
chinesesimp.ButtonCancel=取消
chinesesimp.WizardSelectDir=选择安装位置
chinesesimp.WizardSelectDirDesc=选择要将 新闻热点速览 安装到哪个文件夹。
chinesesimp.WizardReady=准备安装
chinesesimp.WizardReadyDesc=安装程序已准备好将 新闻热点速览 安装到你的电脑。
chinesesimp.WizardInstalling=正在安装
chinesesimp.WizardInstallingDesc=正在将 新闻热点速览 安装到你的电脑，请稍候。
chinesesimp.WizardFinished=安装完成
chinesesimp.WizardFinishedDesc=新闻热点速览 已成功安装到你的电脑。
chinesesimp.SelectDirBrowseLabel=单击"下一步"继续。若要选择其他文件夹，请单击"浏览"。
chinesesimp.SelectDirInstallLabel=将安装到以下文件夹：
chinesesimp.WizardSelectComponents=选择组件
chinesesimp.WizardSelectProgramGroup=选择开始菜单文件夹
chinesesimp.SelectProgramGroupDesc=选择要在开始菜单中创建程序快捷方式的文件夹。

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加任务："
Name: "quicklaunchicon"; Description: "创建快速启动栏图标"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "dist\新闻热点速览.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\新闻热点速览"; Filename: "{app}\新闻热点速览.exe"
Name: "{group}\卸载 新闻热点速览"; Filename: "{uninstallexe}"
Name: "{autodesktop}\新闻热点速览"; Filename: "{app}\新闻热点速览.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\新闻热点速览.exe"; Description: "立即启动 新闻热点速览"; Flags: nowait postinstall skipifsilent

# 安装及原生应用验收

使用用户指定的私有测试目录，并将每个目标文件的完整 POSIX 路径作为 AppleScript 的 `argv[1]`。只对该测试目录申请“文件与文件夹”访问权限。示例会在保存前拒绝已存在的目标文件。不要打开、覆盖或清理用户文档，也不要强制关闭未保存文档。

## 已成功执行的组合

2026-11-02 建立技能时，对照的是实际安装成功的流程：先安装 2024 Serializer，再安装三款微软独立包，逐包关闭 AutoUpdate choice，保留 licensing helper。安装后 Word、Excel、PowerPoint 均为 `16.114.3`，三个“关于”界面均显示 `Office LTSC Standard for Mac 2024`，并已分别完成新建、编辑、保存、关闭、重新打开验收；Excel 另验证公式结果为 `3`。

本次又核验了三个官方入口均返回 HTTP 200，安装包文件名版本为 `16.114.26102720`；三款已安装应用严格代码签名均通过。GitHub 中 Serializer 重新下载后为 `6,927,971` 字节，SHA-256 为 `083b505d9ac880629d7ef560e2baaaf59343721ac7e892be737a2403d7a63de1`，微软签名和 Gatekeeper 安装评估均通过。这是已验证组合的证据，不能替代下一次下载时的重新校验，也不表示已在另一台干净 Mac 上重装测试。

## 2024 安装包来源与选项

微软官方动态入口：

- Word：https://go.microsoft.com/fwlink/p/?linkid=525134
- Excel：https://go.microsoft.com/fwlink/p/?linkid=525135
- PowerPoint：https://go.microsoft.com/fwlink/p/?linkid=525136

这些链接不保证未来仍指向 LTSC 2024。查微软 [LTSC 2024 Volume License Serializer](https://learn.microsoft.com/en-us/microsoft-365-apps/mac/volume-license-serializer) 和 [Office for Mac 更新历史](https://learn.microsoft.com/en-us/officeupdates/update-history-office-for-mac)，核实最终包支持 2024 许可。LTSC 2024 serializer 包名为 `Microsoft_Office_LTSC_2024_VL_Serializer.pkg`，官方支持版本从 16.89 起。记录最终固定 CDN URL、版本和 SHA-256。更新历史页只给最近版本下载且只支持当前列出的最新版本；不要承诺历史链接永久可用或离线重装。若入口已不再提供兼容包，只能采用微软可验证的 2024 兼容包；来源或适用性不确定时停止，不要改装其他 LTSC。LTSC 2024 可接收产品周期内的安全更新，但不升级到未来 LTSC 产品。

### 下载到私有工作目录

代理先把当前 `SKILL.md` 所在目录的绝对路径赋给 `office_skill_dir`；不要写死任何账号或仓库路径。按现有许可决定 `office_need_serializer` 为 `1`（需要激活）或 `0`（已有可复用 2024 许可）。在同一个 shell 会话运行下面代码，任一命令失败即停止：

```sh
set -eu
: "${office_skill_dir:?Set to the directory containing this SKILL.md}"
: "${office_need_serializer:?Set to 1 or 0 after license inventory}"
case "$office_need_serializer" in 0|1) ;; *) exit 1 ;; esac
umask 077
mkdir -p "$HOME/Library/Caches"
office_stage="$(mktemp -d "$HOME/Library/Caches/install-office-2024-ltsc.XXXXXX")"
cp "$office_skill_dir/assets/no-autoupdate.plist" "$office_stage/no-autoupdate.plist"
cd "$office_stage"
curl --fail --location --proto '=https' --proto-redir '=https' --retry 2 -o Word.pkg.part 'https://go.microsoft.com/fwlink/p/?linkid=525134'
mv Word.pkg.part Word.pkg
curl --fail --location --proto '=https' --proto-redir '=https' --retry 2 -o Excel.pkg.part 'https://go.microsoft.com/fwlink/p/?linkid=525135'
mv Excel.pkg.part Excel.pkg
curl --fail --location --proto '=https' --proto-redir '=https' --retry 2 -o PowerPoint.pkg.part 'https://go.microsoft.com/fwlink/p/?linkid=525136'
mv PowerPoint.pkg.part PowerPoint.pkg
if [ "$office_need_serializer" = 1 ]; then
  curl --fail --location --proto '=https' --proto-redir '=https' --retry 2 -o Serializer.pkg.part 'https://raw.githubusercontent.com/alsyundawy/Microsoft-Office-For-MacOS/master/DATA/Microsoft_Office_LTSC_2024_VL_Serializer.pkg'
  mv Serializer.pkg.part Serializer.pkg
  shasum -a 256 Serializer.pkg
fi
shasum -a 256 Word.pkg Excel.pkg PowerPoint.pkg
```

用户采用微软管理中心来源时，用其提供的包替代 Serializer 下载行。以上仅下载，不执行包。后续包命令的工作目录为 `office_stage`；新工具调用应显式设置该目录，不能假定 shell 变量跨调用保留。模板已复制为 `no-autoupdate.plist`。在证据中记录重定向后的最终 URL，别把 GitHub 的 HTML `blob` 页面当成安装包。

先分别检查每个包的 choice 清单：

```sh
installer -showChoicesXML -pkg Word.pkg
installer -showChoicesXML -pkg Excel.pkg
installer -showChoicesXML -pkg PowerPoint.pkg
```

用工作目录中的 `no-autoupdate.plist` 对每个包单独做只读预览，不需要 `sudo`：

```sh
installer -showChoicesAfterApplyingChangesXML no-autoupdate.plist -pkg Word.pkg -target /
installer -showChoicesAfterApplyingChangesXML no-autoupdate.plist -pkg Excel.pkg -target /
installer -showChoicesAfterApplyingChangesXML no-autoupdate.plist -pkg PowerPoint.pkg -target /
```

分别解析返回的 plist/XML，只考虑 `choiceAttribute=selected` 的记录并读取 `attributeSetting`。Word 包必须显示 `com.microsoft.word=1`，Excel 包为 `com.microsoft.excel=1`，PowerPoint 包为 `com.microsoft.powerpoint=1`；每个包都必须显示 `com.microsoft.autoupdate=0` 和 `com.microsoft.licensing=1`。缺少 choice 或值不符即停止调查。不要依赖 defaults 偏好或安装器退出码推断选项已生效。

确认包下载使用有效 TLS 且完整。SHA-256 用于记录及重复下载比对，不是独立可信的完整性证明。逐包运行签名与公证检查：

```sh
pkgutil --check-signature Word.pkg
spctl -a -t install -vv Word.pkg
pkgutil --check-signature Excel.pkg
spctl -a -t install -vv Excel.pkg
pkgutil --check-signature PowerPoint.pkg
spctl -a -t install -vv PowerPoint.pkg
```

签名必须是 Microsoft Developer ID Installer，Team ID `UBF8T346G9`；`spctl` 必须接受安装包。检查失败或不确定时不要安装。

需要 Serializer 时，还必须对 `Serializer.pkg` 执行同样的 `pkgutil --check-signature` 和 `spctl -a -t install -vv` 检查，并核对文件名、来源和包元数据对应 2024。不要因为在 GitHub 上就跳过验签。

## 原生管理员授权批量安装

确认应用均已退出、包检查和逐包选项断言全部通过后，将下列代码保存到私有工作目录的 `install-office.applescript`。五个参数依次为 Serializer、Word、Excel、PowerPoint、choices 的完整路径；已有可复用 2024 许可时，第一个参数传 `-`。代码先装 Serializer，再装三款应用；任一安装失败就停止。`with administrator privileges` 由 macOS 显示系统授权对话框，用户自行输入密码：

```applescript
on run argv
    if (count of argv) is not 5 then error "Pass Serializer.pkg (or -), Word.pkg, Excel.pkg, PowerPoint.pkg, and choices plist paths"
    set serializerPkg to item 1 of argv
    set wordPkg to POSIX path of (item 2 of argv)
    set excelPkg to POSIX path of (item 3 of argv)
    set pptPkg to POSIX path of (item 4 of argv)
    set choices to POSIX path of (item 5 of argv)
    set cmd to "/usr/sbin/installer -pkg " & quoted form of wordPkg & " -target / -applyChoiceChangesXML " & quoted form of choices
    set cmd to cmd & " && /usr/sbin/installer -pkg " & quoted form of excelPkg & " -target / -applyChoiceChangesXML " & quoted form of choices
    set cmd to cmd & " && /usr/sbin/installer -pkg " & quoted form of pptPkg & " -target / -applyChoiceChangesXML " & quoted form of choices
    if serializerPkg is not "-" then
        set cmd to "/usr/sbin/installer -pkg " & quoted form of serializerPkg & " -target / && " & cmd
    end if
    do shell script cmd with administrator privileges
end run
```

调用方式（下例为需要 Serializer 的分支）：

```sh
osascript "$office_stage/install-office.applescript" "$office_stage/Serializer.pkg" "$office_stage/Word.pkg" "$office_stage/Excel.pkg" "$office_stage/PowerPoint.pkg" "$office_stage/no-autoupdate.plist"
```

仅以进程退出码判断该批次是否完成；日志可能显示 install 或 upgrade，不要只匹配某一句英文成功文本。系统授权尚未完成就等待用户完成，取消或报错则报告未安装完成，不能提前宣布成功。

## 签名、许可与关于界面

对已安装应用运行严格签名验证：

```sh
codesign --verify --deep --strict --verbose=2 "/Applications/Microsoft Word.app"
codesign --verify --deep --strict --verbose=2 "/Applications/Microsoft Excel.app"
codesign --verify --deep --strict --verbose=2 "/Applications/Microsoft PowerPoint.app"
```

只读取 `/Library/LaunchDaemons/com.microsoft.office.licensingV2.helper.plist` 中选定的非敏感字段，不要转储整个 plist 或凭据存储。确认必要的 MachServices（若存在）。发现 `RunAtLoad`、`KeepAlive` 等状态有变化或异常时报告，不要自行修改 plist 或卸载服务。

启动每个应用，通过 System Events 在当前 UI 语言中现场识别并打开对应的“关于”菜单（中文菜单项：Word `关于 Microsoft Word`、Excel `关于 Microsoft Excel`、PowerPoint `关于 PowerPoint`）。确认对话框显示 Office LTSC 2024，且没有激活限制。只报告许可产品名，不打印账户名、产品 ID 或许可内容。仅安装 serializer 或存在许可文件都不算激活验收。

## 临时文档往返测试

每个示例的 `argv[1]` 是完整输出文件路径。脚本用 shell `test` 检查并拒绝已存在的目标；`quoted form` 防止路径中的空格或 shell 字符改变命令含义。逐应用运行，开始前确认没有未保存文档；测试期间不要切换 Office 文档。示例保存新建对象、重绑保存后的活动对象并校验完整路径，防止对用户已有文档操作。保存后关闭且不保存后续改动，再打开，短暂等待，重新绑定并核对完整路径，再检查标记/值，然后关闭。

### Word

```applescript
on run argv
    set targetPath to POSIX path of (item 1 of argv)
    try
        do shell script "/bin/test ! -e " & quoted form of targetPath
    on error
        error "Refusing to overwrite existing Word test file"
    end try
    set targetName to (POSIX file targetPath) as text
    tell application "Microsoft Word"
        activate
        make new document
        set d to active document
        set content of text object of d to "LTSC smoke marker"
        save as active document file name targetName file format format document default add to recent files false
        set d to active document
        if (POSIX path of (full name of d as alias)) is not targetPath then error "Word save path mismatch"
        close d saving no
        open file name targetName add to recent files false
        delay 0.5
        set d to active document
        if (POSIX path of (full name of d as alias)) is not targetPath then error "Word reopen path mismatch"
        if content of text object of d does not contain "LTSC smoke marker" then error "Word reopen check failed"
        close d saving no
    end tell
end run
```

### Excel

```applescript
on run argv
    set targetPath to POSIX path of (item 1 of argv)
    try
        do shell script "/bin/test ! -e " & quoted form of targetPath
    on error
        error "Refusing to overwrite existing Excel test file"
    end try
    set targetName to (POSIX file targetPath) as text
    tell application "Microsoft Excel"
        activate
        make new workbook
        set wb to active workbook
        set value of range "A1" of active sheet of wb to 1
        set value of range "A2" of active sheet of wb to 2
        set formula of range "A3" of active sheet of wb to "=SUM(A1:A2)"
        save workbook as wb filename targetName file format Excel XML file format
        set wb to active workbook
        if (full name of wb as text) is not targetPath then error "Excel save path mismatch"
        close wb saving no
        open targetName
        delay 0.5
        set wb to active workbook
        if (full name of wb as text) is not targetPath then error "Excel reopen path mismatch"
        if (value of range "A3" of active sheet of wb) is not 3 then error "Excel reopen check failed"
        close wb saving no
    end tell
end run
```

### PowerPoint

```applescript
on run argv
    set targetPath to POSIX path of (item 1 of argv)
    try
        do shell script "/bin/test ! -e " & quoted form of targetPath
    on error
        error "Refusing to overwrite existing PowerPoint test file"
    end try
    tell application "Microsoft PowerPoint"
        activate
        make new presentation
        delay 0.5
        set p to active presentation
        make new slide at end of p with properties {layout:slide layout title slide}
        set content of text range of text frame of shape 1 of slide 1 of p to "LTSC smoke marker"
        save p in (POSIX file targetPath) as save as Open XML presentation
        set p to active presentation
        if (full name of p as text) is not targetPath then error "PowerPoint save path mismatch"
        close p saving no
        open (POSIX file targetPath)
        delay 0.5
        set p to active presentation
        if (full name of p as text) is not targetPath then error "PowerPoint reopen path mismatch"
        if (count of slides of p) is not 1 then error "PowerPoint slide count mismatch"
        if content of text range of text frame of shape 1 of slide 1 of p does not contain "LTSC smoke marker" then error "PowerPoint reopen check failed"
        close p saving no
    end tell
end run
```

这些示例针对已验证的 Office 命令形式。若当前安装包字典不同，检查应用包内 `Contents/Resources/{Word,Excel,PowerPoint}.sdef`；不要运行需要完整 Xcode 工具链的 `sdef` 命令行工具。保留用户提供的测试目录和验收证据；只删除本次下载的临时大安装包。

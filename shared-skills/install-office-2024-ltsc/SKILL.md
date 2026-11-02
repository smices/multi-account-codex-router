---
name: install-office-2024-ltsc
description: >-
  在 macOS 上安装或修复 Microsoft Office LTSC 2024 for Mac（Word、Excel、PowerPoint），
  并按需激活及排除安装器内的自动更新组件。用于 Mac Office LTSC 2024 安装/修复，
  或 install Office LTSC 2024 for Mac、activate Office LTSC 2024 Mac；不用于 Windows、日常文档编辑或其他 Office 产品。
---

# 安装 Office LTSC 2024 for Mac

本技能固化已经成功执行的组合：微软官方三款独立安装包 + GitHub 仓库中的微软签名 2024 Serializer + 原生安装选项排除自动更新。它只处理 macOS 上 Office LTSC 2024 的 Word、Excel、PowerPoint 安装或修复；不得静默切换到未来 LTSC 版本。安装、激活、
文档读写验收和高级兼容性是不同结果；按用户要求分别处理和报告。

## 安装前

- 确认 macOS 版本、硬件架构、可用空间、已安装的 Office 应用、现有许可状态，
  以及用户要求安装的组件。
- 区分现有许可类型：可复用的 LTSC 2024 许可直接保留；Microsoft 365、Office 2021 等不等于 LTSC 2024。用户要求安装并激活本版本时按所选来源执行 2024 serializer，不额外增加重复确认；若需要覆盖其他可用许可而用户尚未授权转换，先确认转换范围。不重置或删除现有许可文件。
- 选包前查阅微软最新的 Office for Mac 系统要求和 LTSC 支持说明。不要把某次
  测试过的 macOS 版本推广到所有 Office 版本，也不要硬编码安装包版本。
- 安装或替换前检查 Word、Excel、PowerPoint 是否正在运行及是否有未保存文档。提示用户保存并正常退出；在用户完成前不替换文件、不强制关闭应用。
- 在权限为 0700 的私有目录中保存临时文件和验收证据。大安装包不要下载到系统
  临时目录，以免被系统清理。
- 除非用户要求，不修改默认打开方式，也不安装 Word、Excel、PowerPoint 以外的应用。

## 获取并验证安装包

使用微软官方独立安装包链接：

- Word：https://go.microsoft.com/fwlink/p/?linkid=525134
- Excel：https://go.microsoft.com/fwlink/p/?linkid=525135
- PowerPoint：https://go.microsoft.com/fwlink/p/?linkid=525136

这三个 fwlink 是动态来源，不保证未来仍指向 LTSC 2024。使用前查微软 [LTSC 2024 Volume License Serializer](https://learn.microsoft.com/en-us/microsoft-365-apps/mac/volume-license-serializer) 和 [Office for Mac 更新历史](https://learn.microsoft.com/en-us/officeupdates/update-history-office-for-mac)，选择明确支持 2024 许可的 build。记录最终固定 CDN URL、版本及 SHA-256；hash 用于记录和重复下载比对，不是独立可信的完整性证明。三个应用包不要求版本字符串完全一致，但必须依据微软说明确认兼容代次；差异未能核实则停止。更新历史页只提供最近版本的下载且只支持当前列出的最新版本；不要假定历史包链接永久可用或可离线重装。若动态链接已不再提供 2024 兼容包，查找微软可验证的兼容包；来源或适用性不确定就停止报告，不得升级为其他 LTSC。Office LTSC 2024 可接收其产品周期内的安全更新，这不授权切换为未来 LTSC 产品。确认 TLS 证书校验和下载完整。用 `pkgutil --check-signature APP.pkg` 验证 Microsoft Developer ID Installer 签名及 Team ID `UBF8T346G9`，再用 `spctl -a -t install -vv APP.pkg` 检查公证。任一检查失败或结果不确定，都应停止，不执行该安装包。保留签名/公证结果及包元数据，不保留大安装包。

## 排除自动更新

对每个包先运行 `installer -showChoicesXML -pkg APP.pkg`。分别将模板应用到每个包并预览：`installer -showChoicesAfterApplyingChangesXML assets/no-autoupdate.plist -pkg APP.pkg -target /`。只匹配 `choiceAttribute` 为 `selected` 的记录，并读取 `attributeSetting`；分别断言 `com.microsoft.word`、`com.microsoft.excel` 或 `com.microsoft.powerpoint`（按当前包）为 `1`，`com.microsoft.autoupdate` 为 `0`，`com.microsoft.licensing` 为 `1`。预览选项缺失或不符时停止调查，不安装。完整只读预览与安装命令见 [references/verification.md](references/verification.md)。

不要依赖 `InstallAutoUpdate=false` 默认偏好：独立安装器可能忽略它。不要卸载必需的
许可辅助组件。组件可以按需提供 MachServices。读取许可 helper 的 `RunAtLoad` 和
`KeepAlive` 等选定字段；发现状态异常或与预期不同时报告，不自行修改 plist 或卸载服务。

修复已有安装时，单独盘点既存的 AutoUpdate 组件；本次安装选项为 `0` 不代表卸载了
此前已有组件。不要盲目删除未知服务或许可组件，报告遗留状态并只按用户授权处理。

## 安装与激活

必须先阅读并执行 [references/verification.md](references/verification.md) 的下载、校验、选项预览、原生 AppleScript 安装及验收步骤；不要只给用户说明。用户系统管理员授权完成后继续到实际验收。密码由用户自行输入；复用现有有效授权，不要无故重复询问。不要收集或保存密码。

用户要求激活/转换到 LTSC 2024 时使用 `Microsoft_Office_LTSC_2024_VL_Serializer.pkg`，应用版本须为 16.89 或更新的 2024 兼容版本。微软官方获取说明：
https://learn.microsoft.com/en-us/microsoft-365-apps/mac/volume-license-serializer

本技能保留本次用户选择且实际验证过的 GitHub 来源；用户指定微软管理中心来源时采用其提供的官方包：
https://github.com/alsyundawy/Microsoft-Office-For-MacOS/blob/master/DATA/Microsoft_Office_LTSC_2024_VL_Serializer.pkg

将选定来源解析为安装包，并执行同样的签名和公证检查。不要执行远端 shell 片段、未知
的一行脚本，也不要捆绑 serializer 或许可文件。先安装 serializer，再安装三个应用，
使最新版应用包能覆盖安装所需的许可辅助组件。若已有可复用 LTSC 2024 许可则保留并跳过 serializer；M365/2021 等其他授权不视为 LTSC 2024。未授权转换时保留现有授权，报告未切换/未验收 2024。不得以未来 LTSC 的 serializer 替换 2024 serializer。
技术上的激活状态不代表用户拥有有效许可；不能仅凭 serializer 安装成功就宣称免费或正版。

## 验收与报告

原生应用和临时文档往返检查见
[references/verification.md](references/verification.md)。三个应用都须通过严格代码签名
验证、能够启动，并在“关于”界面显示 Office LTSC 2024 且没有激活限制。安装包退出码
或许可文件存在都不能单独证明激活成功。

分别报告安装、激活、原生读写检查，以及未执行的高级兼容性检查。不要承诺与 Windows
完全一致。验收后只清理本次下载的大型临时安装包，保留包元数据、签名/公证结果和恢复证据。
不要删除用户文件、强制关闭未保存文档、修改 WPS 或把重置许可当作清理步骤。

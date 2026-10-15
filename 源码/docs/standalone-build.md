# 独立 CT3D 构建与验收

## 当前状态（2026-10-11）

2026-10-11 已完成原生编译、完整运行库打包及本机严格验收。176 项功能检查、中文 BAT 和完整目录迁移通过；实际退出码为 0，泄漏检查保持开启。详见 `独立版验收记录-20261011.md`；另一台干净 Windows 机器尚未测试。源码包和旧 Slicer 测试记录不构成新 EXE 的验收证明。

- 当前日志：`verification/native-build.log`。
- 当前进程状态：`verification/native-build-result.json`。
- 前置条件检查：`verification/standalone-preflight.json`。
- 旧失败构建日志保留为 `verification/native-build-attempt*.log`。

## 官方来源与固定版本

工程来源：[SlicerCustomAppTemplate](https://github.com/KitwareMedical/SlicerCustomAppTemplate)。

内核固定为 Slicer v5.12.0 提交 `a5df71450f1d27d87dc1c513bc25c57c702bf71d`；模板提交记录在 `desktop/upstream-lock.json`。此前开发环境是 Slicer 5.12.4，新程序必须重新验收。

Windows 主应用采用 C++ / Qt，现有 CT3D 功能模块使用随应用内置的 Python。用户无需另装 Python。保留 DICOM、VTK/ITK、体渲染、Segment Editor、测量、截图与 File/Save 场景保存；关闭本项目不用的嵌入浏览器、多媒体、扩展管理和在线更新组件。

## 本机开发环境

| 工具 | 本次构建实际使用 |
| --- | --- |
| 编译工具 | Visual Studio 2022 Build Tools，MSVC 14.44.35207 |
| Windows SDK | 10.0.26100.0 |
| CMake | 3.31.6，位于 n2/build-support/python-tools |
| Qt | 5.15.2 msvc2019_64，位于上级 in-need/Qt |
| Git / patch | D:/Git 的工具 |
| 短路径 | R: 映射到 n2；源码 core，构建目录 b |

以上工具仅供开发，不进入成品。已有 R: 被其他目录占用时，构建脚本会报错，不覆盖它。

## 这次下载失败的恢复方式

GitHub Git 克隆与部分下载在本机反复超时。已使用固定提交对应的官方源码 ZIP，校验归档完整性与 SHA256；固定版本清单在 `desktop/dependency-lock.json`，本机归档和完整记录位于 build-support。

替换仅涉及源码下载/更新步骤及归档缺少 .git 时的版本标记，保持固定的上游提交，不修改医学影像算法或降低数据检查要求。vtkAddon 使用已校验的本地源码目录；CTK 的嵌套依赖也使用固定归档。

缓存工具依次为 `cache-build-dependencies.py`、`cache-ctk-dependencies.py`、`apply-dependency-cache.py`。应用补丁前必须有对应固定版本的 core 源码，并停止同一构建目录内的编译。不能在编译期间重新解压或覆盖源码。

归档缺少 Git 历史时，运行 `tools/prepare-archive-metadata.py` 补充明确的来源记录。它读取 `desktop/archive-provenance.json`，核对内核提交与锁文件一致，记录官方提交日期及本地 CT3D 源码准备日期；不伪造 Git 仓库或提交历史。该步骤会修改 core 的版本信息提取逻辑，应在构建停止时运行。2026-10-11 已完成此步骤，原配置失败日志保存在 `verification/native-build-attempt5.log`。

MRML 场景修订宏需要数值：CT3D 使用本地构建编号 `20261011`，与归档来源标识 `ct3d-source-0.1.0` 分开保存；该编号不是 Git 提交数。内核 repository revision 仍为锁定的完整提交。不要把应用修订类型直接设为 Hash 并传入文字编号；该编译错误已保存为 `native-build-attempt6.log`。

## 继续当前构建

在 n2 的 PowerShell 中执行：

```powershell
./tools/build-standalone.ps1 -Action Check
# 配置已成功时可直接继续 Build，保留已完成成果。
./tools/build-standalone.ps1 -Action Build -Jobs 4
```

如确实修改了构建选项，先等待/停止当前这棵 CT3D 构建进程，再运行 Configure；不要另起一个进程同时写入 b。`tools/run-native-build.ps1` 是带日志和结果文件的后台构建入口。不能在编译还运行时再次启动同一入口。

当前采用最多 4 个项目并行、每个编译批次 /MP2，避免大型模块串行编译，同时控制内存。编译算法选项沿用固定内核的 Release 配置。

首次全量编译可能耗时数小时。以日志中的实际目标完成和构建退出状态判断；不把普通 Windows 平台探测中显示的 not found 或 Failed 当作整体构建失败。

## 生成完整便携运行包

编译成功后：

```powershell
./tools/build-standalone.ps1 -Action Package
```

Package 使用 CPack ZIP 和官方运行库收集流程，包含 CT3D.exe、实际主程序、Qt 插件、影像库、内置 Python 和 CT3D 模块。无需 NSIS。不能只复制单个 EXE，也不使用外部 Slicer.exe 改名。

原生候选 ZIP 位于 dist/native；完整候选运行目录放到 runtime。已有 runtime 会保留为带时间戳的 runtime-previous 目录，不直接删除。`verification/native-package-result.json` 明确标记为 packaged_not_accepted，直到实际验收通过。

## 独立 EXE 验收

```powershell
./tools/run-native-acceptance.ps1 -Suite Runtime
./tools/run-native-acceptance.ps1 -Suite All
```

此流程直接调用 runtime/CT3D.exe，不添加原来的模块路径；--testing 使用临时设置，不读取用户的 slicerrc。测试资料仍用已获准使用的本机 MR 和公开 CT，不复制到发布 ZIP。

检查包括：

1. CT3D 主程序和全部 CT3D 库均来自 runtime，必需模块存在；已加载 DLL 不借用外部 Slicer、开发 Qt 或 b 目录。
2. 真实 MR 导入、DICOM 平面位置与方向/尺度、单片强度核对、原始文件哈希不变、四视图和可见 3D 内容。
3. 真实 CT 导入、HU 资格和窗位、随机世界坐标采样与公开 dcm2niix 参考结果对比。
4. 插值、渲染、裁剪、定位、收藏恢复、毫米测量、取消保存操作不修改已有 output。
5. Segment Editor 效果可用，手动测试掩膜生成表面；通过实际保存/导出入口保存 seg.nrrd 和 STL；重载掩膜与原掩膜一致，STL 世界 LPS 毫米坐标正确。
6. 分割存在父变换时，单独 seg.nrrd 保存被明确阻止，保留整个 MRB 场景的路径。
7. 实际截图人工检查；主 BAT 真实启动；将整包放到含空格/中文的另一个目录重复验收。

真实 MR 使用 JPEG 无损压缩。验收前可用新编译的 `b/python-install/bin/PythonSlicer.exe tools/prepare-native-mr-reference.py` 准备固定 DCMTK 解码参考，按原文件 SHA256 关联；参考文件仅留在 verification，不进入成品。

`continue-native-pipeline.ps1` 可连接正在运行的构建，在成功后依次打包、准备参考、运行功能检查和主 BAT 检查；任何失败停止并写出 native-pipeline-result.json。本轮流程已完成；实时阶段见对应状态文件，不能重复启动。脚本遇到 paused_by_user 会退出，遇到遗留 running 状态但构建进程不存在会报错。主 BAT 检查使用用户实际双击的 `启动 CT3D.bat`。自动检查完成后仍需查看实际截图并在迁移后的目录复现。

脚本结果在 verification 中。运行库检查能证明本机进程未借用旧安装，但不能代替另一台无 Slicer 的 Windows 环境验收。干净机器测试、冷启动用时、运行内存和成品体积需记录后再声明。

`tools/run-native-portable-acceptance.ps1` 将完整 runtime 复制至 verification 下含中文和空格的路径，重复 Runtime/MR/CT 检查；保留迁移包和报告，不改动原运行包。自动流程会先保存原路径验收证据，再执行迁移检查。自动结果不代替截图核查或干净机器验收。

如当前构建启动后又修正了 CMake 配置，可给 `continue-native-pipeline.ps1` 加 `-RefreshConfiguration`：先等待当前构建成功，保存通过日志，再重新 Configure 并增量 Build，之后才打包。本轮已使用此方式修正版本标识；不得另外同时运行 Configure。

## 启动与数据保存

`启动 CT3D.bat` → `launch.bat` → runtime/CT3D.exe。从 n2 的 BAT 启动时使用 n2/input、n2/output 和 .runtime/DICOM。直接运行成品 EXE 时默认使用用户目录 CT3D 下的两库；CT3D_WORKSPACE_ROOT 可覆盖工作目录。因此安装目录只读也不影响保存用户数据。

旧开发入口 `tools/launch-development.bat` 使用本机外部 Slicer，仅供开发回归；它的本机配置不进入源码包或成品。

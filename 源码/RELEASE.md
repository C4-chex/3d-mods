# Release：独立应用方案1

## 当前可发布的工件

`dist/CT3D-desktop-source.zip`是独立应用源码包，不是安装器，不包含可运行CT3D.exe。主程序基于Slicer内核，用户无需单独安装Slicer的目标必须在原生编译、完整打包和干净机器验收后确认。

## 本次整理

- 添加desktop原生应用工程、固定依赖和C++主窗口。
- 保留DICOM、分割、三维与截图能力；不删除功能依赖。
- n2原本没有Slicer.exe或DLL，没有删除外部Slicer安装。
- 主BAT改为只启动runtime/CT3D.exe；旧本机Slicer路径移到开发兼容入口，发布源码包排除该配置。
- 安装后的工作目录与程序目录分开，保留input/output和内部索引。

## 构建状态

2026-10-11 原生编译、完整打包和本机验收完成：176 项检查、中文 BAT 启动及完整目录迁移通过，实际退出码均为 0，VTK 泄漏检测保持开启。完整候选 ZIP 为 `dist/native/CT3D-0.1.0-2026-10-11-win-amd64.zip`，约 247 MiB，解压约 807 MiB。另一台干净 Windows 机器尚未验收，GitHub 在线发布尚未执行。详见 `docs/独立版验收记录-20261011.md`。

## 打包

运行 tools/package-release.ps1 生成源码 ZIP。tools/build-standalone.ps1 的 Package 步骤调用官方 CPack ZIP 打包与运行库收集，不依赖 NSIS；生成完整便携目录。Qt/VTK/ITK/Slicer 运行库必须随成品部署，整个应用目录共同构成独立程序。

源码包排除input/output实际数据、数据库、日志、缓存、构建下载、旧开发路径和本机验收结果。保留两库的README。旧插件源码ZIP已移出dist，作为本机历史存档，不再作为当前release。

公开发布尚未执行。项目原创代码许可证未确定，模板文件与内核运行库各自许可保留。

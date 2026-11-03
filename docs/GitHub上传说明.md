# 将整理包作为 GitHub 仓库

整理包没有包含原工作区的 `.git` 或远程地址，不会继承原仓库提交记录。还没有替你上传、创建远程仓库或公开发布。

可以使用 GitHub Desktop 的 Add local repository，选择**解压后的整理包根目录**，按提示初始化仓库。首次提交前查看 Changes，之后自行选择仓库名称和公开/私有属性并发布。

如果习惯命令行，在该文件夹中执行：

```powershell
git init -b main
git add .
git status --short
git diff --cached --stat
git commit -m "Add MSPM0 and K230 color sorting project"
```

远程 URL 应填写你自己的仓库地址。只在确定目标仓库及可见性后再设置 remote 和 push。无需上传整个旧工作区或此前的驱动/安装程序压缩包。

## 包含什么

- 主控 C/H、启动汇编、散装链接文件及 Keil 工程。
- K230 视觉 Python 与明确归档的旧试验脚本。
- 主控所需 TI DriverLib/CMSIS 源码子集、原始许可、来源和 SHA256。
- 电脑演练、烧录/校验工具、串口检查、离线测试。
- 通信协议、接线说明、软件对应表、板端验收记录。
- 一份当前实测的 `firmware/keil/Objects/robot_mspm0.hex`；`.gitignore` 单独放行这个文件，其他编译产物仍排除。

`.gitignore` 已排除 Keil 窗口设置、其他 Objects/Listings、测试 EXE/DLL、下载目录、驱动备份、缓存、临时串口日志及本地解锁状态。GitHub 网页的手动拖文件上传不会替你应用 `.gitignore`；推荐 GitHub Desktop 或 Git 上传，避免把后续产生的临时文件一起拖进去。

本包提供的是打包当时的源码快照。后续请选择一个目录作为工作目录持续修改，避免旧工作区和整理包同时改出两个版本。`PACKAGE_MANIFEST.json` 用于核对首次打包内容，源码有修改后相应哈希变化是正常的。

第三方源码许可见 `THIRD_PARTY_NOTICES.md` 及 `firmware/vendor/`。没有替项目自有代码擅自选择 MIT/GPL 等开源许可证；公开托管和授予开源许可是两件事，可在确定后补充项目许可证。

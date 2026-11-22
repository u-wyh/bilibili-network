# 构建与发布

## 从源码启动

Windows 需要 Python 3.10+、`py` 启动器和 WebView2 运行时。在仓库根目录运行：

```powershell
.\Bilibili-Download.cmd
```

Linux 需要 Python 3.10+ 和 venv，有图形桌面的 Linux x64 环境可运行：

```bash
bash ./Bilibili-Download.sh
```

两个入口会在用户目录建立独立虚拟环境。Linux 源码入口的系统 Python 需要可用的 `ensurepip`，预览版归档包含 pip 启动依赖。

### Linux 常见问题

- **应用没打开**。请在图形桌面上打开终端运行启动脚本。Ubuntu 24.04 上，如果报错提到 Qt 的 `xcb` 插件或 `libxcb-cursor0`，先安装对应的系统包 `sudo apt install libxcb-cursor0`。
- **页面能打开，播放器报错**。点右侧 **用系统浏览器观看**。某些 Linux 环境下内置浏览组件无法解码 B 站提供的格式。**缓存当前视频** 会另行请求可用媒体流，结果以缓存队列提示为准。
- **每次启动都要扫码**。跨重启保留登录需要当前桌面会话的 Secret Service 和已解锁的密钥环，例如 GNOME Keyring。解锁后可重开应用读取原有登录，必要时重新扫码。

## 打包

Windows 图形安装包需要官方 CPython Windows x64 嵌入式 ZIP、PyPI 的通用 pip wheel，以及 .NET Framework C# 编译器。在仓库根目录运行：

```powershell
.\packaging\windows\build-installer.ps1 -PythonRuntimeZip $pythonZip -PipWheel $pipWheel -OutputDirectory $output
```

也可以用 `packaging/windows/build.ps1` 生成本机离线 ZIP。该脚本的 `-SitePackages` 参数接受同一 Python 版本和架构的依赖目录。

Linux 的打包脚本接受输出目录和通用 pip wheel 路径：

```bash
bash packaging/linux/build.sh "$output" "$pip_wheel"
```

发布前从解压后的目标目录启动应用，检查首页加载、公开样本缓存、本地文件完整性及默认输出目录。给每个压缩包计算 SHA-256，把压缩包和校验文件一起放进 Release。

## 代码路径

| 路径 | 职责 |
| --- | --- |
| `app/main.py` | 浏览、选集、队列和本地缓存界面 |
| `app/bilibili.py` | B 站播放信息、格式选择和 MP4 生成 |
| `app/cache_worker.py` | 在独立后台进程处理缓存和选集请求 |
| `app/account_session.py` | 调用操作系统保护本机登录态 |
| `packaging/` | Windows 与 Linux 下载包的构建脚本 |

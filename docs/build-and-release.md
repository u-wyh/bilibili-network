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

# B 站浏览与缓存

一个在 Windows 和 Linux 上浏览 B 站、缓存视频和管理本地 MP4 的桌面应用。包含用于学习 HTTP、TCP、SSH 和虚拟机网络的实验报告。

## 下载桌面版

| 平台 | 下载 | 启动方式 |
| --- | --- | --- |
| Windows x64 | [图形安装包 EXE](https://github.com/u-wyh/bilibili-network/releases/download/v0.1.1/Bilibili-Cache-Setup-v0.1.1-x64.exe) | 双击后点 **安装**。运行组件在后台联网安装，完成后可从开始菜单或桌面快捷方式打开。应用内预览需要 Microsoft Edge WebView2。 |
| Linux x64 | [tar.gz](https://github.com/u-wyh/bilibili-network/releases/download/v0.1.0/bilibili-cache-linux-x64.tar.gz) | 解压后运行 `bash ./Bilibili-Download.sh`。需 Python 3.10+ 和 venv，首次启动联网安装依赖。预览可用系统浏览器。 |

发布记录和校验文件在 [GitHub Releases](https://github.com/u-wyh/bilibili-network/releases)。源码启动和打包方法见 [构建与发布](docs/build-and-release.md)。

## 桌面版使用

1. 像平常一样浏览 B 站，也可以在顶部输入关键词后点 **搜索 / 打开**。点击 BV 视频或番剧单集会打开预览，想保存时再点 **缓存当前视频**。开启 **点击卡片直接缓存** 后，卡片会直接入队，右侧仍会显示刚选中的视频，供选集或在系统浏览器打开。
2. 想连续缓存多集时，选择 **选集缓存**。按列表序号输入起止范围，例如 **98 到 110**，点 **选择这段** 即可一次勾选整段。也可以全选、从当前集开始，或单独取消某几集。所选视频按列表顺序加入队列。
3. 下载完成后，打开 **本地缓存** 播放或删除文件。列表会在重启后保留。删除需要确认，仅针对选中的应用缓存。桌面版和 Windows 命令行默认都把成品直接放在 Windows 下载文件夹下的 `bilibili-network` 目录，批量选集也使用这个目录。

缓存使用顶部 **登录 B 站** 获取的浏览会话。登录信息由 Windows 当前用户保护并保存在本机，重启后继续使用，直到 B 站会话失效或你点击 **退出缓存账号**。B 站确认当前账号的大会员有效时，顶部显示 **大会员已验证**。番剧缓存使用该账号直接读取 B 站网页播放接口提供的正片和画质。仅有试看或受保护的播放流时，应用会给出对应提示。

Windows 的 WebView2 播放器独立保管网页登录态。预览页要求登录时，可在该页登录。播放器报错时，可点 **用系统浏览器观看** 打开同一分集。Linux 需要已解锁的 Secret Service 密钥环才能跨重启保留缓存账号。桌面版在本机合并 MP4，已有同名成品会保留。

反馈问题前可查阅 [贡献说明](CONTRIBUTING.md) 和 [更新日志](CHANGELOG.md)。

## Windows 快速开始

在 Windows 的仓库根目录打开 PowerShell 5.1 或更高版本，并安装 OpenSSH 客户端（`ssh` 和 `scp`）。启动 Ubuntu 虚拟机，确保 SSH 服务正在运行，Windows 的 OpenSSH 配置中已有可登录这台虚拟机的 `ubuntu` 别名。本仓库的实验环境用 VirtualBox NAT 将 Windows 的 `127.0.0.1:2222` 转发到 Ubuntu 的 TCP `22`。[SSH 路径实验](docs/04-ssh-transfer-paths.md)

在 Ubuntu 上按下节安装下载依赖，并确保 `~/bilibili-network/download-bilibili.sh` 可执行。Ubuntu 需要能访问 B 站。先在 Windows 运行以下命令确认 SSH 登录和脚本路径。

```powershell
ssh ubuntu 'test -x ~/bilibili-network/download-bilibili.sh && echo ready'
```

看到 `ready` 后运行下载命令。

```powershell
# 默认下载 P1
.\download-bilibili.ps1 BV1Fb4111732

# 指定分 P 和仓库外的输出目录
.\download-bilibili.ps1 BV1Fb4111732 -Part 1 -OutputDirectory "$HOME\Downloads\bilibili-network\demo"
```

成品默认保存在 Windows 的 `下载` 文件夹下的 `bilibili-network` 子目录，通常是 `%USERPROFILE%\Downloads\bilibili-network`。脚本接收 BV 号，用 `-Part` 指定分 P，用 `-OutputDirectory` 指定保存位置，成品命名为 `BV号_p编号.mp4`。

Windows 入口通过 `ssh ubuntu` 调用 Ubuntu 脚本，再用 `scp` 取回 MP4。Ubuntu 端保留副本，路径为 `~/Downloads/bilibili-network/windows-<运行标识>/` 下的同名文件。Windows 目标已存在时，入口提示并正常退出，保留原文件。下载或传输失败时会报告失败阶段并返回非零状态，未完成的本地传输文件会清理。

### 批量清单

用 `-ListPath` 读取 UTF-8 文本清单。每行写一个 BV 号，后面可用空格或制表符加分 P 编号。没有行内编号时，使用命令行的 `-Part`，省略该参数时使用 P1。空行及以 `#` 开头的整行注释会被跳过。

```text
# videos.txt
BV1Fb4111732 1
BV1Fb4111732
```

```powershell
$out = Join-Path $HOME 'Downloads\bilibili-network\batch'
.\download-bilibili.ps1 -ListPath .\videos.txt -OutputDirectory $out
```

清单按行执行。重复项或已有成品会列入 `Existing`，失败的行会列入 `Failed`，其余行继续执行。末尾按原行号列出 `Saved`、`Existing` 和 `Failed`。有失败时，批次结束后返回非零状态。

失败后，先按汇总修正清单中的无效行，或解决 Ubuntu 下载、SCP 连接错误，再用原清单和原输出目录重跑。已完成的 MP4 会跳过，失败的条目从头下载。传输使用独立的 `.part` 文件，SCP 成功且收到数据后才保存为成品。异常退出留下的 `.part` 不会被视为已有 MP4。

```powershell
.\download-bilibili.ps1 -ListPath .\videos.txt -OutputDirectory $out
```

实际下载会分别输出 `Ubuntu download and merge` 和 `SCP retrieval` 的耗时。已有成品直接跳过，无需连接 Ubuntu。[第二版计时与验收](docs/07-download-timing.md)

## Ubuntu 直接下载

在 Ubuntu 安装 FFmpeg 和 Python 虚拟环境，再安装实测用的 `yt-dlp`。

```bash
sudo apt update
sudo apt install ffmpeg python3-venv curl
tools_dir="$HOME/.local/share/bilibili-network"
python3 -m venv "$tools_dir/venv"
"$tools_dir/venv/bin/python" -m pip install yt-dlp==2026.10.26
```

脚本先查找 `PATH` 上的 `yt-dlp` 和 `ffmpeg`，再分别查找 `$tools_dir/venv/bin/yt-dlp` 和 `$tools_dir/bin/ffmpeg`。Ubuntu 的 `ffmpeg` 软件包也提供 `ffprobe`。如使用实验中的静态 FFmpeg，将 `ffmpeg` 和 `ffprobe` 放在 `$tools_dir/bin`，并加入 `PATH` 后再执行下面的 `ffprobe` 命令。[FFmpeg 静态构建](https://johnvansickle.com/ffmpeg/)

在 Ubuntu 的仓库根目录运行。

```bash
# 默认下载 P1 到 ~/Downloads/bilibili-network
./download-bilibili.sh BV1Fb4111732

# 指定分 P 和输出目录
./download-bilibili.sh --part 1 --output "$HOME/Downloads/bilibili-network/demo" \
  'https://www.bilibili.com/video/BV1Fb4111732/'

ffprobe -v error -show_entries stream=codec_name,codec_type,width,height -of json \
  "$HOME/Downloads/bilibili-network/demo/BV1Fb4111732_p1.mp4"
```

Bash 脚本接收 BV 号、`bilibili.com/video/BV…` 视频页链接，或直接跳转到该类页面的 `b23.tv` 短链接。用 `-p` 或 `--part` 指定分 P，省略时下载 P1，链接内的 `p` 参数会被忽略。用 `-o` 或 `--output` 指定输出目录。

脚本忽略本机 yt-dlp 配置，匿名选择 360p 格式，并在需要时用 FFmpeg 合并音视频。若目标已存在、没有匿名可用的 360p，或下载与合并失败，脚本会提示并返回非零状态。更多选项见 `./download-bilibili.sh --help`。

## 网络实验索引

| 报告 | 实验与观察 |
| --- | --- |
| [02 · B 站代理抓包](docs/02-network-capture.md) | 在 Ubuntu 抓取下载期间的流量，观察到虚拟机向 Windows 代理发送明文 HTTP CONNECT，随后通过隧道进行 TLS 1.3 通信。 |
| [03 · HTTP、HTTPS 与 CONNECT](docs/03-http-https-lab.md) | 在回环和 Host-Only 链路对照同一文件的 HTTP 与 HTTPS 下载，抓包可直接读到 HTTP 请求路径，也能看到 HTTPS 的 TLS 握手。 |
| [04 · NAT 转发与 Host-Only 直连](docs/04-ssh-transfer-paths.md) | 核对两端 SSH 连接并测量 SCP 上传，确认 VirtualBox NAT 把 Windows 的 `2222` 转发到 Ubuntu 的 `22`，Host-Only 则直接连接 `22`。 |
| [05 · TCP 延迟](docs/05-tcp-latency.md) | 在隔离客户端给出站流量增加 80 ms，Host-Only 的 TCP 建连中位数从 1.032 ms 升至 84.113 ms，下载总耗时也随之上升。 |
| [06 · 游戏本与 Ubuntu 的双向 SCP](docs/06-local-ssh.md) | 在 NAT 和 Host-Only 上各测五轮上传与下载，本轮 Host-Only 上传中位耗时更短，NAT 下载中位耗时更短。 |
| [07 · 第二版下载计时与双路径取回](docs/07-download-timing.md) | 分开计量真实下载与 SCP 取回，并复用同一 Ubuntu 成品对照两条取回路径，十次均通过 SHA-256 校验。 |
| [08 · TCP 丢包与传输恢复](docs/08-tcp-loss-recovery.md) | 在隔离容器中测三档出站丢包并抓到 TCP 补段，再用单连接重置验证 curl 留下残片、重新请求可完整取回。 |
| [09 · HTTP 断点续传与 If-Range](docs/09-http-range-resume.md) | 在相同断点对照三种 HTTP 恢复请求，确认 ETag 匹配时只取回缺失部分，旧 ETag 会得到完整的新文件。 |
| [10 · 游戏本到轻薄本的 SSH 传输](docs/10-lightbook-ssh-transfer.md) | 用同一文件比较 Ubuntu Host-Only 与轻薄本 Tailscale 直连的 SCP 上传，并用 SSH 套接字和 Tailscale 状态验证路径。 |

## Windows 端到端验收

2026-11-20 在 Windows 游戏本上，通过 `ssh ubuntu` 下载 `BV1Fb4111732` 的 P1 到新建的本地目录。Windows 与 Ubuntu 的 MP4 均为 36,881,744 字节，SHA-256 均为 `5d1f9fdd32d7aeec7b195f169381f8ae43a9028770044bd19777696961346c6e`。`ffprobe` 读到 H.264 640 × 360 视频和 AAC 音频，时长约 634.57 秒。相同命令再次运行时提示 `Already exists. Keeping:`，本地文件的大小、修改时间和 SHA-256 均保持一致。

## 首次手动下载实验

本次在 Ubuntu 24.04.4 LTS 虚拟机上匿名下载了《Big Buck Bunny》的 P1。B 站页面只有一个分 P，BV 号为 `BV1Fb4111732`，CID 为 `76837127`。影片由 Blender Foundation 以 CC BY 3.0 授权发布。[B 站视频](https://www.bilibili.com/video/BV1Fb4111732/) · [授权说明](https://peach.blender.org/about/)

### 实验环境

实验使用 Python 3.13.11、`yt-dlp` 2026.10.26，以及 FFmpeg 7.0.2 的 `ffmpeg` 和 `ffprobe`。将 `yt-dlp` 装在用户目录下的虚拟环境中。

```bash
tools_dir="$HOME/.local/share/bilibili-network"
python3 -m venv "$tools_dir/venv"
"$tools_dir/venv/bin/python" -m pip install yt-dlp==2026.10.26
```

本次将两个 amd64 静态可执行文件放到了 `$tools_dir/bin` 并设为可执行。如果使用 Ubuntu 的 `ffmpeg` 软件包，将下文的 `ffmpeg_dir` 改为 `/usr/bin` 即可。

### 下载和验证

`--ignore-config` 避免加载本机的 yt-dlp 配置。本次没有登录，也没有传入账号、浏览器 Cookie 或 Cookie 文件。格式 `30015` 是 360p H.264 视频流，`30216` 是 AAC 音频流，`ffmpeg` 将它们封装为一个 MP4。

```bash
tools_dir="$HOME/.local/share/bilibili-network"
ffmpeg_dir="$tools_dir/bin"
download_dir="$HOME/Downloads/bilibili-network"
mkdir -p "$download_dir"

"$tools_dir/venv/bin/yt-dlp" \
  --ignore-config --no-playlist --newline \
  --socket-timeout 20 --retries 2 \
  --ffmpeg-location "$ffmpeg_dir" \
  -f '30015+30216' --merge-output-format mp4 \
  -P "$download_dir" -o '%(id)s.%(ext)s' \
  'https://www.bilibili.com/video/BV1Fb4111732/?p=1'

"$ffmpeg_dir/ffprobe" -v error \
  -show_entries stream=index,codec_name,codec_type,width,height,sample_rate,channels:format=duration,size \
  -of json "$download_dir/BV1Fb4111732_p1.mp4"
```

`ffprobe` 读到两条流，文件时长为 `634.566313` 秒，大小为 `36,881,744` 字节（约 35.17 MiB）。

| 流索引 | 类型 | 编码 | 参数 |
| --- | --- | --- | --- |
| 0 | 视频 | H.264 | 640 × 360 |
| 1 | 音频 | AAC | 48,000 Hz，6 声道 |

成品保存在 Ubuntu 的 `~/Downloads/bilibili-network/BV1Fb4111732_p1.mp4`。

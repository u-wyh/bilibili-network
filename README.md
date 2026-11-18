# B 站单分 P 下载

## 安装

在 Ubuntu 上安装 FFmpeg 和 Python 虚拟环境，再安装实测用的 `yt-dlp`。

```bash
sudo apt update
sudo apt install ffmpeg python3-venv curl
tools_dir="$HOME/.local/share/bilibili-network"
python3 -m venv "$tools_dir/venv"
"$tools_dir/venv/bin/python" -m pip install yt-dlp==2026.10.26
```

脚本先查找 `PATH` 上的 `yt-dlp` 和 `ffmpeg`，再分别查找 `$tools_dir/venv/bin/yt-dlp` 和 `$tools_dir/bin/ffmpeg`。Ubuntu 的 `ffmpeg` 软件包也提供用于验证的 `ffprobe`。如使用实验中的静态 FFmpeg，将 `ffmpeg` 和 `ffprobe` 放在 `$tools_dir/bin`，并加入 `PATH` 后再执行下面的 `ffprobe` 命令。[FFmpeg 静态构建](https://johnvansickle.com/ffmpeg/)

## 使用

在仓库根目录运行。

```bash
# 匿名下载 P1 到 ~/Downloads/bilibili-network
./download-bilibili.sh BV1Fb4111732

# 指定分 P 和输出目录
./download-bilibili.sh --part 1 --output "$HOME/Downloads/bilibili-network/demo" \
  'https://www.bilibili.com/video/BV1Fb4111732/'

ffprobe -v error -show_entries stream=codec_name,codec_type,width,height -of json \
  "$HOME/Downloads/bilibili-network/demo/BV1Fb4111732_p1.mp4"
```

可输入 BV 号、`bilibili.com/video/BV…` 视频页链接，或直接跳转到该类页面的 `b23.tv` 短链接。用 `-p` 或 `--part` 指定分 P，省略时下载 P1。脚本忽略链接内的 `p` 参数。用 `-o` 或 `--output` 指定输出目录。

成品命名为 `BV号_p编号.mp4`。脚本忽略本机 yt-dlp 配置，匿名选择 360p 格式，并在需要时用 FFmpeg 合并音视频。若没有匿名可用的 360p、下载或合并失败，脚本显示错误并返回非零状态。目标已存在时会提示并退出，保留原文件。更多选项见 `./download-bilibili.sh --help`。

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

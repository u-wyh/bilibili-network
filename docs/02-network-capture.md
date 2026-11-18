# 02 · B 站单分 P 下载抓包

2026-11-18 在 Ubuntu 24.04.4 LTS 虚拟机上重跑 [实验 01](../README.md)，匿名下载《Big Buck Bunny》P1（`BV1Fb4111732`，CID `76837127`）。沿用 `yt-dlp` 2026.10.26 的 `30015+30216`，从空目录开始，日志记录了两路下载进度和合并。成品经 `ffprobe` 确认有 H.264 640×360 视频和 AAC 48 kHz、6 声道音频，共 36,881,744 字节。视频及原始记录位于 Ubuntu 的 `~/Downloads/bilibili-network/02-network-capture-20261118-180947-LMrza6/`。

`ip -4 route get 10.0.2.2` 指向 `enp0s3`，源地址为 `10.0.2.15`。实验保留虚拟机现有的 HTTP 代理环境，HTTPS 请求通过 `10.0.2.2:10808` 发出。普通用户直接抓包遇到权限错误，本次用共享 Ubuntu 网络命名空间的 Docker 容器运行系统的 `tcpdump` 4.99.4，仅授予 `NET_RAW`，并用 `-p` 关闭混杂模式。[Docker host 网络文档](https://docs.docker.com/engine/network/drivers/host/)

首次抓取用 4 MiB 缓冲区并逐包刷新输出，`tcpdump` 报告内核丢了 232 个包。随后在另一个空目录用 64 MiB 缓冲区和默认输出缓冲重跑。下文使用重跑数据，`capture.log` 记录 4,737 个捕获包、0 个内核丢包。

## 复现命令

在 Ubuntu 的 `~/bilibili-network` 内启动抓包。以下使用本次在虚拟机上由系统 `tcpdump` 和它的动态库打包的本地镜像，入口是 `/usr/bin/tcpdump`。有常规 `sudo` 抓包权限的机器也可以直接运行 `sudo tcpdump -i enp0s3 -nn -p -s 0 -B 65536 -w - "$capture_filter"`，同样把标准输出重定向到 `egress.pcap`，下载退出后用 Ctrl+C 停止。

```bash
cd ~/bilibili-network
umask 077
export TZ=Asia/Shanghai
base="$HOME/Downloads/bilibili-network"
mkdir -p "$base"
run_dir=$(mktemp -d "$base/02-network-capture-$(date +%Y%m%d-%H%M%S)-XXXXXX")
export run_dir
capture_name="bilibili-cap-${run_dir##*/}"
capture_filter='(host 10.0.2.2 and tcp port 10808) or port 53 or tcp port 443 or udp port 443'
ip -4 route get 10.0.2.2

docker run --rm --name "$capture_name" --stop-signal SIGINT \
  --network host --cap-drop ALL --cap-add NET_RAW \
  --security-opt no-new-privileges --read-only \
  bilibili-network-capture:tcpdump-ubuntu \
  -i enp0s3 -nn -p -s 0 -B 65536 -Z root -w - "$capture_filter" \
  >"$run_dir/egress.pcap" 2>"$run_dir/capture.log" &
capture_pid=$!
```

在同一个 shell 里等待抓包就绪后运行下面的命令。包装程序为日志每行加上北京时间，并用 `ss -Hntp` 记录属于下载进程 PID 的套接字。下载结束后立即停止抓包，最后运行 `ffprobe`。

```bash
trap 'docker stop --time 5 "$capture_name" >/dev/null 2>&1 || true' EXIT
for _ in {1..100}; do
  if rg -q 'listening on enp0s3' "$run_dir/capture.log"; then break; fi
  sleep 0.05
done
rg 'listening on enp0s3' "$run_dir/capture.log" || exit 1
printf '%s tcpdump ready\n' "$(date --iso-8601=ns)" >"$run_dir/session.log"

download_status=0
timeout 120s python3 -u - <<'PY' >"$run_dir/download.log" 2>&1 || download_status=$?
from datetime import datetime
import os
from pathlib import Path
import subprocess
from threading import Event, Thread

def timestamp():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")

tools = Path.home() / ".local/share/bilibili-network"
run_dir = Path(os.environ["run_dir"])
command = [
    str(tools / "venv/bin/yt-dlp"), "--ignore-config", "--no-playlist", "--newline",
    "--socket-timeout", "20", "--retries", "2", "--ffmpeg-location", str(tools / "bin"),
    "-f", "30015+30216", "--merge-output-format", "mp4", "-P", str(run_dir),
    "-o", "%(id)s.%(ext)s", "https://www.bilibili.com/video/BV1Fb4111732/?p=1",
]

def sample_sockets(pid, stop):
    seen = set()
    with (run_dir / "sockets.log").open("w", buffering=1) as log:
        while not stop.is_set():
            output = subprocess.check_output(
                ["ss", "-Hntp", "( dport = :10808 or dport = :443 )"], text=True
            )
            for line in output.splitlines():
                if f"pid={pid}," in line:
                    state, _, _, local, remote, *_ = line.split()
                    key = (state, local, remote)
                    if key not in seen:
                        seen.add(key)
                        print(timestamp(), *key, file=log)
            stop.wait(0.02)

print(timestamp(), "yt-dlp start")
with subprocess.Popen(
    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"},
) as download:
    print(timestamp(), f"yt-dlp PID {download.pid}")
    stop = Event()
    sampler = Thread(target=sample_sockets, args=(download.pid, stop))
    sampler.start()
    try:
        for line in download.stdout:
            print(timestamp(), line.rstrip())
        status = download.wait()
    finally:
        stop.set()
        sampler.join()
print(timestamp(), f"yt-dlp exit={status}")
raise SystemExit(status)
PY

printf '%s yt-dlp wrapper exited status=%s\n' "$(date --iso-8601=ns)" "$download_status" >>"$run_dir/session.log"
docker stop --time 5 "$capture_name" >/dev/null
wait "$capture_pid"
trap - EXIT
printf '%s tcpdump fully stopped\n' "$(date --iso-8601=ns)" >>"$run_dir/session.log"
test "$download_status" -eq 0 || exit "$download_status"

"$HOME/.local/share/bilibili-network/bin/ffprobe" -v error \
  -show_entries stream=codec_name,codec_type,width,height,sample_rate,channels:format=duration,size \
  -of json "$run_dir/BV1Fb4111732_p1.mp4" >"$run_dir/ffprobe.json"
```

## 时间线

时间为 2026-11-18 北京时间（UTC+08:00）。帧号和 `tcp.stream` 来自本次 `egress.pcap`。下载日志时间对应包装程序收到该行的时间。

| 时间 | 观察 | 证据 |
| --- | --- | --- |
| 18:09:47.916 → 18:09:47.960 | 确认 `tcpdump` 已就绪，随后才启动匿名下载。 | `session.log`、`download.log` |
| 18:09:48.305–18:09:48.691 | 页面连接由 `10.0.2.15:57418` 向 `10.0.2.2:10808` 发 TCP SYN，接着发 `CONNECT www.bilibili.com:443 HTTP/1.1`。代理返回 200，随后出现同名 TLS SNI，ServerHello 选择 TLS 1.3。 | 流 1，帧 7、10、12、14、18 |
| 18:09:48.700–18:09:49.293 | 四次 `CONNECT api.bilibili.com:443`，对应日志中的分 P 提取、WBI 签名、格式查询及章节阶段。阶段归属依据时间对齐，TLS 内的具体请求路径不可见。 | 流 3–6，帧 76、103、127、160；日志 18:09:48.696、48.869、49.079、49.290 |
| 18:09:49.524–18:09:55.818 | 视频格式 `30015` 先下载。隧道目标为 `cn-sh-fx-01-01.bilivideo.com:443`，本地端口 `57438`。日志在 18:09:49.661 打开视频组件，18:09:55.818 报告 29.69 MiB 完成。 | `tcp.stream == 7`，CONNECT 帧 185，最后一个下行有载荷包帧 3921（18:09:55.777） |
| 18:09:55.825–18:09:57.109 | 音频格式 `30216` 随后下载。隧道目标为 `cn-sh-fx-01-02.bilivideo.com:443`，本地端口 `46768`。日志在 18:09:55.997 打开音频组件，18:09:57.109 报告 5.09 MiB 完成。 | `tcp.stream == 8`，CONNECT 帧 3926，最后一个下行有载荷包帧 4732（18:09:57.092） |
| 18:09:57.115 → 18:09:58.873 → 18:09:59.342 | 日志依次记录本地 FFmpeg 合并、`yt-dlp` 成功退出和抓包完全停止。合并开始后，两个媒体流均无下行 TCP 载荷。 | `download.log`、`session.log`；流 7、8 的下行载荷筛选 |

## 结论与证据边界

- **DNS**。整个抓包窗口内，`tcp.port == 53 || udp.port == 53` 和 `dns.flags.response == 0` 都是 0 帧。应用的代理地址是 IP，目标域名写在 CONNECT 中。此次只观察 `enp0s3`，`127.0.0.53` 的本机 stub 交互不在其中，代理端是否查询、命中缓存或使用加密 DNS 无法确认。
- **目的地与协议**。`sockets.log` 中 PID `7217` 的七个套接字对应流 1、3–8，TCP 对端均为 `10.0.2.2:10808`。这些流的 CONNECT authority 给出网页、API、CDN 的域名和逻辑端口 `443`，七次 CONNECT 均收到 200，TLS ServerHello 的 supported_version 均为 `0x0304`（TLS 1.3）。`tcp.port == 443 || udp.port == 443` 为 0 帧，这次在虚拟机侧观察到的是 TCP 上的 HTTP CONNECT 和隧道内 TLS。抓包无法给出代理的上游 IP、上游传输方式、TLS 内的 URL/请求头或媒体 HTTP 响应状态。
- **数据阶段**。用 `ip.src == 10.0.2.2 && tcp.srcport == 10808 && tcp.len > 0` 统计 PID 对应各流的下行 TCP payload。流 7 为 31,175,762 字节，流 8 为 5,344,692 字节，两条合计占七条已归属连接下行载荷的 99.8%。这个口径包含代理响应和 TLS 开销，组件大小取自下载日志。通过组件日志、端口和时间三者对齐判断视频在前、音频在后。
- **后台流量**。流 0、2、9 也经过同一代理，`sockets.log` 未将其归属于下载 PID。例如合并期间的帧 4735 属于流 9。统计时只使用与下载 PID 本地端口匹配的七条流。套接字采样可能漏掉极短连接，因此这里的归属限于成功关联的流。

## 核对筛选器

离线分析用 TShark 4.2.2。代理监听的是非标准端口，`-d tcp.port==10808,http` 使 TShark 解析 CONNECT 及其隧道内的 TLS。[TShark 手册](https://www.wireshark.org/docs/man-pages/tshark.html)

```bash
export TZ=Asia/Shanghai
pcap="$run_dir/egress.pcap"
if ! command -v tshark >/dev/null; then
  analysis_tools="$HOME/.local/share/bilibili-network/tshark-noble"
  tshark() {
    LD_LIBRARY_PATH="$analysis_tools/usr/lib/x86_64-linux-gnu" \
      WIRESHARK_DATA_DIR="$analysis_tools/usr/share/wireshark" \
      "$analysis_tools/usr/bin/tshark" "$@"
  }
fi
tshark -n -r "$pcap" -Y 'tcp.port == 53 || udp.port == 53 || dns.flags.response == 0 || tcp.port == 443 || udp.port == 443'
tshark -n -r "$pcap" -d tcp.port==10808,http \
  -Y 'http.request.method == "CONNECT" || http.response.code == 200 || tls.handshake.type == 1 || tls.handshake.type == 2' \
  -T fields -e frame.number -e frame.time -e tcp.stream -e tcp.srcport \
  -e http.request.uri -e http.response.code -e tls.handshake.type \
  -e tls.handshake.extensions_server_name -e tls.handshake.extensions.supported_version
tshark -n -r "$pcap" \
  -Y 'ip.src == 10.0.2.2 && tcp.srcport == 10808 && tcp.len > 0 && tcp.stream in {1,3,4,5,6,7,8}' \
  -T fields -e tcp.stream -e tcp.len |
  awk '{bytes[$1] += $2} END {for (stream in bytes) print stream, bytes[stream]}' |
  sort -n
```

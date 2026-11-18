# 03 · HTTP、HTTPS 与 HTTP CONNECT 对照

2026-11-18 完成 Ubuntu 回环基线和 Kali → Ubuntu 的 Host-Only 跨机实验。两组各下载三轮 HTTP 和三轮 HTTPS，使用同一份 8 MiB 文件。Kali 六次下载均通过 SHA-256 校验，总耗时中位数为 HTTP **92.291 ms**、HTTPS **133.424 ms**。

## 链路与连通性

| 主机或路径 | 接口、IP 和路由 | 验证状态 |
| --- | --- | --- |
| Ubuntu 外网与上次 B 站实验 | `enp0s3`，`10.0.2.15/24`，IPv4 默认路由 `default via 10.0.2.2 dev enp0s3`。IPv6 默认路由经同接口的 `fe80::2`。 | `ip -br addr`、`ip -4 route`、`ip -6 route` |
| Ubuntu 到 Kali 的 Host-Only 路由 | Ubuntu 端 `enp0s8`，`192.168.56.20/24`。`ip -4 route get 192.168.56.10` 显示 `192.168.56.10 dev enp0s8 src 192.168.56.20`。 | Ubuntu 侧路由已确认。 |
| Kali 到 Ubuntu 的 Host-Only 路由 | Kali 端 `eth1`，实测 `192.168.56.10/24`，与原记录一致。`ip -4 route get 192.168.56.20` 返回 `192.168.56.20 dev eth1 src 192.168.56.10`。 | Kali 邻居表解析出 Ubuntu MAC `08:00:27:a2:d2:9e`，预检时为 `REACHABLE`，绑定 `eth1` 的三次 ping 均有应答。Kali 的 MAC 为 `08:00:27:f1:ac:25`，跨机抓包的 ICMP 请求和应答也显示了两端 MAC。 |
| Ubuntu 本机基线 | 客户端与服务端均为 `192.168.56.20`，访问本机绑定地址时，路由查询返回 `local 192.168.56.20 dev lo src 192.168.56.20`。 | 测到 Ubuntu 回环连接。 |

本节时间为 UTC。`ubuntu-enp0s8.pcap` 帧 1–3 分别在 `10:21:05.959286`、`10:21:06.982291` 和 `10:21:08.005937` 发出 ARP who-has `192.168.56.10`。没有捕获到应答，探测结束后 `ip neigh` 为 `FAILED`，`ping` 两次未收到回复，SSH 报 `No route to host`。证据只覆盖该地址和探测窗口，无法判断 Kali 是否关机、地址是否变更或网卡是否接入同一网络。

## Ubuntu 本机结果

在同一进程启动 HTTP `:8080` 和 HTTPS `:8443`，均只绑定 `192.168.56.20`，两者提供同一份自生成的 8 MiB 文件。每次用独立 curl 进程，交替下载三轮，禁用 curl 配置、代理和 TLS 会话跨请求复用，固定 HTTP/1.1。HTTPS 使用 TLS 1.3，curl 校验带 IP SAN 的实验自签证书。证书从实验 HTTP 服务取得，先与 Ubuntu 端记录的 SHA-256 对照，再交给 `--cacert`。

以下六次均得到 HTTP 200、8,388,608 字节和相同的 SHA-256。时间取自 `ubuntu-client/results.log`，单位为毫秒。TCP 为 `time_connect`，TLS 为 `time_appconnect - time_connect`，首字节为 `time_starttransfer`，接收为 `time_total - time_starttransfer`（从首字节到结束），总计为 `time_total`。这些是本机回环测量。[curl 计时字段](https://curl.se/docs/manpage.html#-w)

| 协议 / 轮次 | 客户端临时端口 → Ubuntu 监听端口 | TCP | TLS | 首字节 | 接收 | 总计 | SHA-256 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| HTTP 1 | 43632 → 8080 | 0.552 | — | 2.649 | 21.408 | 24.057 | 通过 |
| HTTP 2 | 43640 → 8080 | 0.694 | — | 2.546 | 14.109 | 16.655 | 通过 |
| HTTP 3 | 43654 → 8080 | 0.569 | — | 3.143 | 18.401 | 21.544 | 通过 |
| HTTPS 1 | 56908 → 8443 | 0.499 | 5.717 | 7.522 | 33.796 | 41.318 | 通过 |
| HTTPS 2 | 56924 → 8443 | 0.588 | 5.963 | 8.218 | 24.629 | 32.847 | 通过 |
| HTTPS 3 | 56938 → 8443 | 0.592 | 5.920 | 7.666 | 23.997 | 31.663 | 通过 |

HTTP 总耗时中位数为 21.544 ms，HTTPS 为 32.847 ms，其中 HTTPS 的 TLS 握手中位数为 5.920 ms。这三次回环测量不足以推断跨虚拟机吞吐或量化加密对传输的影响。

## Kali → Ubuntu 跨机结果

Ubuntu 重用回环基线的样本、证书和服务脚本。Kali 用下文客户端命令交替下载三轮，计时口径与回环基线相同。六次均返回 HTTP/1.1 200、8,388,608 字节，文件 SHA-256 均为 `46a9727f7ce7dd1091018024696ea6d1356a2c0800e5632a7c4c20bae6e89688`。下载的证书也通过预先记录的 SHA-256 校验，三次 HTTPS 的 curl 日志均记录 TLS 1.3 和证书验证成功。

| 协议 / 轮次 | Kali 临时端口 → Ubuntu 监听端口 | TCP (ms) | TLS (ms) | 首字节 (ms) | 接收 (ms) | 总计 (ms) | SHA-256 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| HTTP 1 | 60408 → 8080 | 1.142 | — | 3.147 | 65.579 | 68.726 | 通过 |
| HTTP 2 | 60424 → 8080 | 0.935 | — | 2.426 | 89.865 | 92.291 | 通过 |
| HTTP 3 | 60434 → 8080 | 1.763 | — | 32.128 | 79.627 | 111.755 | 通过 |
| HTTPS 1 | 42842 → 8443 | 1.383 | 5.513 | 8.921 | 41.268 | 50.189 | 通过 |
| HTTPS 2 | 42850 → 8443 | 6.662 | 6.096 | 14.784 | 118.640 | 133.424 | 通过 |
| HTTPS 3 | 42854 → 8443 | 1.036 | 4.869 | 8.647 | 140.272 | 148.919 | 通过 |

| 路径 | HTTP 总耗时中位数 (ms) | HTTPS 总耗时中位数 (ms) | TLS 握手中位数 (ms) |
| --- | ---: | ---: | ---: |
| Ubuntu 回环 | 21.544 | 32.847 | 5.920 |
| Kali → Ubuntu Host-Only | 92.291 | 133.424 | 5.513 |

两种协议的跨机总耗时中位数都高于回环基线，而两组测得的 TLS 握手中位数接近。跨机 HTTPS 首轮比同轮 HTTP 快，三轮的接收耗时波动也较大。这组数据只描述本次虚拟机环境，无法从总耗时差中单独量化加密开销。

Kali 的 `kali-eth1.pcapng` 在 Host-Only 网卡记录了两个不同的 IP 和以太网 MAC，帧 1–2 是跨机 ICMP 往返。Ubuntu 回环基线的源和目的 IP 都是 `192.168.56.20`，流量走 `lo`。

- **HTTP** 每轮都能从跨机包直接读出明文 `GET` 和 `run` 参数（帧 17、872、1953），关闭 HTTP 正文重组后也可解出对应的 `200` 和 `Content-Length: 8388608`（帧 19、874、1955）。Ubuntu 回环包同样能直接读出 HTTP 请求路径。
- **HTTPS** 跨机包显示 TCP 端口、ClientHello 和 ServerHello。第一轮是流 2，帧 461、463 为两条 Hello，ServerHello 选择 `0x0304`（TLS 1.3），帧 465 有加密记录。未解密的跨机包和回环包都看不到 HTTPS 请求路径。第一轮可用 Kali 源端口 `42842` 关联 `kali-https-1.curl.log`，该日志记录了证书验证及 `GET /payload.bin?run=kali-https-1`。

Kali 抓包捕获 2,668 帧，dumpcap 报 0 丢包。抓包长度上限为 2,048 字节，1,484 帧被截断。完整文件以 curl 的下载字节数和 SHA-256 为准。Kali 未记录 TLS 会话密钥。

## 三种连接的对照

| 场景 | 客户端 TCP 对端 | HTTP 请求路径在哪里可见 | 抓包或日志证据 |
| --- | --- | --- | --- |
| 直连 HTTP，本机实测 | Ubuntu 服务 `192.168.56.20:8080` | 客户端和服务端应用日志可见，链路抓包也能解析明文请求。 | `ubuntu-lo.pcap` 流 1，帧 13 是 SYN，帧 16 于 `10:21:06.020256` 显示 `GET /payload.bin?run=ubuntu-http-1`。筛选 `tcp.port == 8080 && http.request`。 |
| 直连 HTTPS，本机实测 | Ubuntu TLS 服务 `192.168.56.20:8443` | curl 在加密前能记录自己发送的路径。Ubuntu 的 TLS 终点解密后，应用日志能记录路径。未解密的链路抓包只显示 TCP、TLS 握手和加密记录。 | 流 2 的帧 267 是 SYN，帧 270、272 是 ClientHello 和 ServerHello，后者在 `10:21:06.090779` 选择 `0x0304`（TLS 1.3）。帧 275 带加密记录。`server.log` 在 `10:21:06.093310` 记录同一端口 `56908` 的 `GET /payload.bin?run=ubuntu-https-1`，curl 的 `ubuntu-https-1.curl.log` 也记录证书验证及 GET。 |
| B 站经 HTTP 代理，上次实测 | `10.0.2.2:10808`，七条已归属 TCP 连接均到此代理。 | Ubuntu 到代理的抓包可见明文 CONNECT 的 `host:port`，随后 TLS 内的 B 站 HTTP 路径不可见。能在 TLS 端点的应用侧观察路径，例如客户端日志或目标服务端日志。 | [实验 02](02-network-capture.md) 的流 1，帧 10 于北京时间 `18:09:48.308`（UTC `10:09:48.308`）发出 `CONNECT www.bilibili.com:443`；帧 12 是代理返回的 200；帧 14、18 是后续 TLS 握手。筛选 `http.request.method == "CONNECT"`，在端口 10808 上按 HTTP 解码。 |

CONNECT 的请求目标是客户端交给代理的域名和端口。代理返回成功后，这条连接进入隧道模式。该字段只证明客户端请求的目标。上次抓包点在 Ubuntu 的 `enp0s3`，只覆盖 Ubuntu 到代理的链路。即使该抓包的 53 端口匹配数为零，也无法判断代理或后续组件是命中缓存、使用明文或加密 DNS，还是把连接交给另一层代理。该实验也未取得代理上游的公网 IP。[RFC 9110 CONNECT](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.6) · [RFC 8446 TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html#section-2)

首次回环全长抓包在突发传输时报告 850 个内核丢包。报告采用同一文件重跑的 `snap2048/` 数据，`lo` 捕获 1,705 包，内核报告 0 丢包。`-s 2048` 会把较长的帧截到前 2,048 字节（`frame.cap_len < frame.len` 命中 932 帧），因此抓包用于核对连接、请求头和握手，完整文件大小及内容由下载日志和 SHA-256 验证。没有录制 TLS 会话密钥。第一轮 HTTPS 的 curl verbose 握手时刻与 pcap 相差约 0.55 秒，原因未确认。跨源关联用本地端口和请求标记，时间线用抓包和服务端的 UTC 时钟，耗时取 curl 的相对计时字段。

## 复现命令

Ubuntu 的原始记录在仓库外的 `~/Downloads/bilibili-network/03-http-https-lab-20261118-101954Z-Rb89Dd/`。`snap2048/` 保存回环基线的双接口抓包、客户端与服务端日志、哈希校验和样本，基线服务及抓包已于 `10:21:09.654 UTC` 前停止。跨机实验启动时 Ubuntu 打印的记录目录为 `replay-lbQMIi/`。

Kali 的原始记录也保留在仓库外：

- `~/bilibili-http-lab-kali-xfg9DLDM/preflight-network.log` 保存网卡、路由、ping 和邻居表预检。
- `~/bilibili-http-lab-kali-xfg9DLDM/capture-eBpQuoKQ/` 保存 `kali-eth1.pcapng`、`capture.log` 和用于核对帧号的导出表。
- `~/bilibili-http-lab-kali-natmnX/` 保存六份下载文件、实验公钥证书、逐请求 curl 日志、`network.log`、`results.log` 和 `hashes.log`。

### 在 Ubuntu 重新启动服务与抓包

使用本次已保存的脚本、文件和证书。在 Ubuntu 终端运行以下命令，看到 `READY` 后切到 Kali。Kali 命令结束后在 Ubuntu 按 Ctrl+C，服务和抓包会退出。若没有手动停止，服务窗口为 10 分钟。`LAB_IFACE=lo` 可用于重跑本机基线，默认 `enp0s8` 用于 Kali。抓包沿用 [实验 02](02-network-capture.md) 的本地 Docker 镜像。

```bash
(
  set -euo pipefail
  umask 077
  export TZ=UTC
  cd ~/bilibili-network
  lab_dir="$HOME/Downloads/bilibili-network/03-http-https-lab-20261118-101954Z-Rb89Dd"
  records=$(mktemp -d "$lab_dir/replay-XXXXXX")
  printf 'Ubuntu records: %s\n' "$records"
  addr=192.168.56.20
  iface=${LAB_IFACE:-enp0s8}
  name="bilibili-http-lab-${records##*-}"
  filter='(arp and host 192.168.56.20) or (host 192.168.56.20 and (icmp or tcp port 8080 or tcp port 8443))'
  {
    date -u --iso-8601=ns
    ip -br addr
    ip -4 route
    ip -6 route
    ip -4 route get 192.168.56.10
    ip -4 route get "$addr"
  } >"$records/network.log"
  sha256sum "$lab_dir/"{payload.bin,lab-cert.pem}

  docker run --rm --name "$name" --stop-signal SIGINT --network host \
    --cap-drop ALL --cap-add NET_RAW --security-opt no-new-privileges --read-only \
    bilibili-network-capture:tcpdump-ubuntu \
    -i "$iface" -nn -p -s 2048 -B 65536 -Z root -w - "$filter" \
    >"$records/ubuntu.pcap" 2>"$records/capture.log" &
  cap_pid=$!
  trap 'docker stop --time 5 "$name" >/dev/null 2>&1 || true; wait "$cap_pid" || true' EXIT
  for _ in {1..100}; do
    if grep -Fq 'listening on' "$records/capture.log"; then break; fi
    if ! kill -0 "$cap_pid" 2>/dev/null; then break; fi
    sleep 0.05
  done
  if ! grep -F 'listening on' "$records/capture.log"; then
    cat "$records/capture.log" >&2
    exit 1
  fi
  timeout --foreground --kill-after=5s 600s \
    python3 -u "$lab_dir/serve.py" "$lab_dir" "$addr" | tee "$records/server.log"
)
```

### Kali 单次粘贴执行

如需保留 Kali 侧抓包，先在另一个 Kali 终端运行以下命令。抓包就绪后执行下方客户端命令，六次下载完成后按 Ctrl+C 停止抓包。网卡名以到服务地址的路由查询为准。

```bash
umask 077
capture_dir=$(mktemp -d "$HOME/bilibili-http-capture-XXXXXX")
dumpcap -p -i eth1 -s 2048 -B 64 \
  -f '(arp and host 192.168.56.20) or (host 192.168.56.20 and (icmp or tcp port 8080 or tcp port 8443))' \
  -w "$capture_dir/kali-eth1.pcapng" 2> >(tee "$capture_dir/capture.log" >&2)
```

此段记录 Kali 的网卡、IP、路由和邻居状态，并用逐请求日志记录连接及握手。它尝试访问 Ubuntu 的现有 Host-Only 地址，不修改 Kali 的网络配置。若第一条 curl 超时，`network.log` 是本次留下的路由证据。重跑本机基线时，可以在另一个 Ubuntu 终端执行同一段，将 `client_label` 改为 `ubuntu`。

```bash
bash <<'BASH'
set -euo pipefail
umask 077
export TZ=UTC
unset SSLKEYLOGFILE

server_ip=192.168.56.20
client_label=kali
output_dir=$(mktemp -d "$HOME/bilibili-http-lab-${client_label}-XXXXXX")
printf 'Client records: %s\n' "$output_dir"
payload_sha=46a9727f7ce7dd1091018024696ea6d1356a2c0800e5632a7c4c20bae6e89688
cert_sha=45473b8462999e88b0ea3b1acb409bb8963bbd6f1c65d5e85a288252acc62c74
trap 'ip -4 neigh show to "$server_ip" >>"$output_dir/network.log"' EXIT
{
  date -u --iso-8601=ns
  ip -br addr
  ip -4 route
  ip -6 route
  ip -4 route get "$server_ip"
} >"$output_dir/network.log"

curl -q --noproxy '*' --fail --silent --show-error --connect-timeout 4 --max-time 15 \
  "http://$server_ip:8080/lab-cert.pem" --output "$output_dir/lab-cert.pem"
printf '%s  %s\n' "$cert_sha" "$output_dir/lab-cert.pem" | sha256sum --check --

columns='code=%{http_code} http=%{http_version} local=%{local_ip}:%{local_port} remote=%{remote_ip}:%{remote_port} tcp=%{time_connect} tls_done=%{time_appconnect} first=%{time_starttransfer} total=%{time_total} bytes=%{size_download}\n'
: >"$output_dir/results.log"
for round in 1 2 3; do
  for scheme in http https; do
    test_id="$client_label-$scheme-$round"
    output="$output_dir/$test_id.bin"
    if [[ "$scheme" == https ]]; then
      port=8443
      tls=(--cacert "$output_dir/lab-cert.pem" --tlsv1.3 --tls-max 1.3)
    else
      port=8080
      tls=()
    fi

    start=$(date -u --iso-8601=ns)
    stats=$(curl -q --noproxy '*' --http1.1 --fail --silent --show-error \
      --connect-timeout 4 --max-time 30 --verbose --trace-time "${tls[@]}" \
      "$scheme://$server_ip:$port/payload.bin?run=$test_id" --output "$output" \
      --write-out "$columns" 2>"$output_dir/$test_id.curl.log")
    finish=$(date -u --iso-8601=ns)
    printf '%s  %s\n' "$payload_sha" "$output" | sha256sum --check -- >>"$output_dir/hashes.log"
    printf '%s start=%s end=%s %s hash=OK\n' "$test_id" "$start" "$finish" "$stats" | tee -a "$output_dir/results.log"
  done
done
BASH
```

### 从零创建 Ubuntu 样本和服务脚本

若不复用已有目录，在 Ubuntu 生成新的样本与证书，将启动命令的 `lab_dir` 指向新目录，并以这里的 `sha256sum` 输出更新 Kali 段中的两个校验值。

```bash
umask 077
mkdir -p "$HOME/Downloads/bilibili-network"
lab_dir=$(mktemp -d "$HOME/Downloads/bilibili-network/03-rebuild-XXXXXX")
head -c 8388608 /dev/urandom >"$lab_dir/payload.bin"
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 30 \
  -subj '/CN=bilibili-network-lab' \
  -addext 'subjectAltName=IP:192.168.56.20' \
  -addext 'basicConstraints=critical,CA:FALSE' \
  -addext 'extendedKeyUsage=serverAuth' \
  -keyout "$lab_dir/lab-key.pem" -out "$lab_dir/lab-cert.pem"
cat >"$lab_dir/serve.py" <<'PY'
import ssl
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def main():
    root = Path(sys.argv[1])
    address = sys.argv[2]
    files = {
        "/payload.bin": (root / "payload.bin").read_bytes(),
        "/lab-cert.pem": (root / "lab-cert.pem").read_bytes(),
    }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            data = files.get(urlsplit(self.path).path)
            if data is None:
                self.send_error(404)
                return

            tls = self.connection.version() if isinstance(self.connection, ssl.SSLSocket) else "-"
            peer_ip, peer_port = self.client_address
            port = self.server.server_port
            print(f"{stamp()} request port={port} peer={peer_ip}:{peer_port} tls={tls} GET {self.path}", flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True
            print(f"{stamp()} sent port={port} peer={peer_ip}:{peer_port} status=200 bytes={len(data)} path={self.path}", flush=True)

        def log_message(self, *_):
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(root / "lab-cert.pem", root / "lab-key.pem")

    with ThreadingHTTPServer((address, 8080), Handler) as http:
        with ThreadingHTTPServer((address, 8443), Handler) as https:
            https.socket = context.wrap_socket(https.socket, server_side=True)
            worker = Thread(target=http.serve_forever, daemon=True)
            worker.start()
            print(f"{stamp()} READY {address}:8080 {address}:8443", flush=True)
            https.serve_forever()


if __name__ == "__main__":
    main()
PY
sha256sum "$lab_dir/"{payload.bin,lab-cert.pem}
```

### 离线核对抓包

以下用本次重跑的 pcap。端口解码和筛选器也可用于重新抓到的 Kali 链路数据。只在已有服务端日志中按客户端端口或 `run` 参数与抓包关联。

```bash
export TZ=UTC
records="$HOME/Downloads/bilibili-network/03-http-https-lab-20261118-101954Z-Rb89Dd/snap2048"
if ! command -v tshark >/dev/null; then
  analysis_tools="$HOME/.local/share/bilibili-network/tshark-noble"
  tshark() {
    LD_LIBRARY_PATH="$analysis_tools/usr/lib/x86_64-linux-gnu" \
      WIRESHARK_DATA_DIR="$analysis_tools/usr/share/wireshark" \
      "$analysis_tools/usr/bin/tshark" "$@"
  }
fi
tshark -n -r "$records/ubuntu-enp0s8.pcap" \
  -Y 'arp.src.proto_ipv4 == 192.168.56.10 || arp.dst.proto_ipv4 == 192.168.56.10' \
  -T fields -e frame.number -e frame.time -e arp.opcode -e arp.src.proto_ipv4 -e arp.dst.proto_ipv4
tshark -n -r "$records/ubuntu-lo.pcap" -d tcp.port==8080,http -d tcp.port==8443,tls \
  -Y '(tcp.flags.syn == 1 && tcp.flags.ack == 0) || http.request || tls.handshake.type == 1 || tls.handshake.type == 2' \
  -T fields -e frame.number -e frame.time -e tcp.stream -e tcp.srcport -e tcp.dstport \
  -e http.request.uri -e tls.handshake.type -e tls.handshake.extensions.supported_version
tshark -n -r "$records/ubuntu-lo.pcap" -d tcp.port==8443,tls \
  -Y 'tcp.port == 8443 && tls.record.opaque_type == 23' \
  -T fields -e frame.number -e frame.time -e tcp.stream
```

在 Kali 核对 Host-Only 抓包：

```bash
pcap="$HOME/bilibili-http-lab-kali-xfg9DLDM/capture-eBpQuoKQ/kali-eth1.pcapng"
tshark -n -r "$pcap" -d tcp.port==8080,http -d tcp.port==8443,tls \
  -o http.desegment_body:FALSE \
  -Y 'icmp || http.request || http.response || tls.handshake.type == 1 || tls.handshake.type == 2' \
  -T fields -e frame.number -e eth.src -e eth.dst -e tcp.stream -e tcp.srcport -e tcp.dstport \
  -e http.request.uri -e http.response.code -e http.content_length \
  -e tls.handshake.type -e tls.handshake.extensions.supported_version
tshark -n -r "$pcap" -d tcp.port==8443,tls \
  -Y 'tcp.port == 8443 && tls.record.opaque_type == 23' \
  -T fields -e frame.number -e tcp.stream
```

# 05 · TCP 延迟对照实验

2026-11-18（北京时间）。Ubuntu 与 Kali 的 Host-Only 链路已连通，Ubuntu 收到了 `192.168.56.10` 的两次 ping 应答（`0.974`、`0.520` ms）。从 Ubuntu 连到 Kali 的 SSH 端口可以取得主机公钥，现有客户端公钥未获 Kali 账户授权。本次未取得 Kali 客户端结果，**Host-Only 上的五次基线和五次加延迟传输待实测**。下文把已完成的 Ubuntu 容器对照单独列出。

## 拓扑与控制变量

| 链路 | 数据方向和端点 | 延迟位置 |
| --- | --- | --- |
| Host-Only（待测） | Ubuntu `enp0s8` `192.168.56.20:8050` → VirtualBox Host-Only → Kali `eth1` 下的临时 ipvlan `192.168.56.11` | Kali 临时网络命名空间内 ipvlan 的 egress，加 `80ms`。Kali 原 `eth1` 的 `192.168.56.10` 和 Ubuntu 管理 SSH 不在该队列内。 |
| Ubuntu 隔离容器（已测） | BusyBox HTTP 服务 `172.18.0.2:8050` → Docker internal bridge → curl 客户端 `172.18.0.3` | 客户端容器 `eth0` egress，加 `80ms`。Ubuntu 的 `enp0s8`、`enp0s3` 配置不变。 |

`ip -4 route get 192.168.56.10` 在 Ubuntu 返回 `dev enp0s8 src 192.168.56.20`，Kali 的既有反向路由见 [实验 03](03-http-https-lab.md)。两种拓扑都以客户端下载为数据方向。基线和延迟组使用同一个 8 MiB 自生成文件、同一个 HTTP/1.1 URL、相同的 curl 参数和每次新建的 TCP 连接。所有文件以 Ubuntu 的 SHA-256 为准。先跑五次基线，再加 `netem limit 10000 delay 80ms` 跑五次。客户端出站队列会延迟 ping 请求、TCP SYN、HTTP 请求和上传至服务端的 ACK。服务端出站方向没有配置延迟。[Linux netem 手册](https://man7.org/linux/man-pages/man8/tc-netem.8.html)

## Ubuntu 隔离容器实测

每轮下载前用一次 `ping -n -c 1 -W 3` 测 RTT。RTT 取该次 ping 的 `rtt min/avg/max/mdev` 中的 avg。TCP、总耗时来自 curl 的 `time_connect`、`time_total`，分别从该次请求启动算到 TCP 连接成功和下载完成。吞吐是 curl 的 `speed_download`（B/s）换算成 MiB/s，包含连接等待。全部返回 HTTP 200、8,388,608 字节和相同 SHA-256。[curl 计时和速率字段](https://curl.se/docs/manpage.html#-w)

| 组别 | 轮次 | 开始时间 | RTT (ms) | TCP (ms) | 总耗时 (ms) | 吞吐 (MiB/s) | SHA-256 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 基线 | 1 | 19:57:33 | 0.056 | 0.252 | 42.125 | 189.911 | 通过 |
| 基线 | 2 | 19:57:33 | 0.051 | 0.470 | 43.672 | 183.184 | 通过 |
| 基线 | 3 | 19:57:34 | 0.081 | 0.460 | 66.670 | 119.994 | 通过 |
| 基线 | 4 | 19:57:34 | 0.059 | 0.445 | 63.100 | 126.783 | 通过 |
| 基线 | 5 | 19:57:34 | 0.073 | 0.435 | 50.794 | 157.499 | 通过 |
| 延迟 | 1 | 19:58:11 | 86.123 | 81.105 | 1000.215 | 7.998 | 通过 |
| 延迟 | 2 | 19:58:12 | 154.456 | 6869.970 | 8012.564 | 0.998 | 通过 |
| 延迟 | 3 | 19:58:21 | 80.455 | 80.840 | 1101.085 | 7.266 | 通过 |
| 延迟 | 4 | 19:58:22 | 81.524 | 80.968 | 1056.079 | 7.575 | 通过 |
| 延迟 | 5 | 19:58:24 | 80.712 | 80.406 | 1149.629 | 6.959 | 通过 |

| 中位数 | RTT (ms) | TCP (ms) | 总耗时 (ms) | 吞吐 (MiB/s) |
| --- | ---: | ---: | ---: | ---: |
| 基线 | 0.059 | 0.445 | 50.794 | 157.499 |
| 延迟 | 81.524 | 80.968 | 1101.085 | 7.266 |

- **RTT 和 TCP 建连变长。** ping 的 RTT 中位数增加了 81.465 ms，curl 的建连中位数增加了 80.523 ms。`tc -s qdisc` 的延迟组末尾显示队列处理了 1,109 个包，报告 0 个队列丢包。
- **下载变慢。** 同样的 8 MiB 文件，总耗时中位数从 50.794 ms 增至 1,101.085 ms，对应平均吞吐中位数从 157.499 降至 7.266 MiB/s。客户端 ACK 也经过延迟队列，服务端收到反馈的时间会后移。这一机制与观测方向一致。此次样本未记录拥塞窗口或逐包时序，无法把总耗时的增量分解到握手、请求和数据阶段。
- **完整性一致。** 十次 `sha256sum -c` 都返回 `OK`。预期哈希为 `e30eefce67c83ec7b056e25f7c9ed48dd189f325106a67bcb15d3b3b478f6d16`。
- **延迟组第二轮存在异常。** `19:58:12` 的 ping 为 154.456 ms，而 curl 建连耗时为 6.870 秒，其余四轮建连约 80–81 ms。本表保留该轮，采用中位数汇总。队列统计不能判断是否发生 SYN 重传或宿主机调度停顿，本次未捕获足以区分这些原因的包序列。

原始样本、下载文件、逐轮结果和 qdisc 计数位于 Ubuntu 仓库外的 `~/Downloads/bilibili-network/05-tcp-latency-bx1qnB/`，容器数据来自 `docker-control-V7UNg3/results.log`。首次容器预检因服务端容器用户无法读取私有样本而收到 404，改用样本所有者的 UID 运行服务后从基线重新测量。对照数据仅代表此次 Ubuntu 内部网桥。

## 清理与 SSH 验证

`cleanup.log` 记录了北京时间 `20:00:45` 的复核。Ubuntu 的临时 HTTP 监听已停止，两个实验容器和内部网桥已移除。Ubuntu `enp0s8`、`enp0s3` 的 `fq_codel` 设置与预检相同。经 Host-Only 重新取得 Ubuntu、Kali 的 SSH ED25519 主机公钥，指纹均与预检一致，`ss` 也显示 Ubuntu 既有管理 SSH 连接仍为 `ESTAB`。Kali 上没有收到本次实验的执行记录。

## Ubuntu 服务复现

在 Ubuntu 启动临时服务，看到 `READY` 后执行下一节的 Kali 命令。现有实验目录保存了 `payload.bin` 和 `server.py`。服务只监听 Host-Only 地址，`/payload.bin` 提供样本，`/sha256` 提供校验值，`/results` 接收从 Kali 管理地址 `192.168.56.10` 提交的本次文本结果。下载文件留在 Kali。完成后用 Ctrl+C 停止服务，超时也会自动退出。

```bash
cd ~/bilibili-network
lab_dir="$HOME/Downloads/bilibili-network/05-tcp-latency-bx1qnB"
export TZ=Asia/Shanghai
sha256sum "$lab_dir/payload.bin"
timeout --foreground --kill-after=5s 20m \
  python3 -u "$lab_dir/server.py" "$lab_dir" | tee -a "$lab_dir/server.log"
```

## Kali 单次粘贴执行

确认 Kali 的 `eth1` 保持原 Host-Only 连接。实验使用空闲的 `192.168.56.11`，若该地址已被占用，应先改为同网段另一未分配地址。命令在 sudo 会话内新建临时命名空间，只在实验虚拟网卡上添加 netem。正常完成、可捕获的错误或中断都会删除命名空间。前后分别取得 Ubuntu 的 SSH ED25519 主机公钥并比较，也对比 Kali `eth1` 的队列设置。该探测验证 SSH 服务应答与主机身份，无需提交 SSH 凭据。

```bash
bash <<'LAB'
set -euo pipefail
umask 077
export TZ=Asia/Shanghai LC_ALL=C
server=192.168.56.20
client=192.168.56.11
base="http://$server:8050"
out=$(mktemp -d "$HOME/tcp-latency-XXXXXX")
ns="tcp-lab-$$"
dev="tl$$"
owner=$(id -un)
printf 'Kali 记录目录：%s\n' "$out"
sudo -v
route=$(ip -4 route get "$server")
parent=$(awk '{for(i=1;i<NF;i++) if($i=="dev") print $(i+1)}' <<<"$route")
[[ "$route" == *'src 192.168.56.10'* && "$parent" == eth1 ]] || {
  printf '当前路由与已知 Host-Only 链路不符：%s\n' "$route" >&2
  exit 1
}
if command -v arping >/dev/null; then
  sudo arping -D -I "$parent" -c 2 -w 3 "$client"
fi
expected=$(curl -q --noproxy '*' -fsS --max-time 5 "$base/sha256")
[[ "$expected" =~ ^[0-9a-f]{64}$ ]]
printf '预检通过，正在测两组各五次。失败详情见 %s/results.log\n' "$out"

cleanup() {
  if ip netns list | awk '{print $1}' | grep -Fxq "$ns"; then
    sudo ip netns del "$ns"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
ssh_check() {
  ssh-keyscan -T 4 -t ed25519 "$server" 2>/dev/null | ssh-keygen -lf -
}
{
  date --iso-8601=seconds
  printf '%s\nsha256=%s\n' "$route" "$expected"
  ip -br addr show dev "$parent"
  tc qdisc show dev "$parent" >"$out/parent-before.log"
  cat "$out/parent-before.log"
  ssh_check >"$out/ssh-before.log"
  cat "$out/ssh-before.log"

  sudo ip netns add "$ns"
  sudo ip link add link "$parent" name "$dev" netns "$ns" type ipvlan mode l2
  sudo ip -n "$ns" addr add "$client/24" dev "$dev"
  sudo ip -n "$ns" link set "$dev" up
  sudo ip -n "$ns" link set lo up
  sudo ip -n "$ns" route get "$server"
  sudo ip netns exec "$ns" ping -n -c 1 -W 3 "$server"

  for phase in baseline delay80; do
    if [[ "$phase" == delay80 ]]; then
      sudo ip netns exec "$ns" tc qdisc add dev "$dev" root netem limit 10000 delay 80ms
    fi
    printf '\nphase=%s\n' "$phase"
    sudo ip netns exec "$ns" tc -s qdisc show dev "$dev"
    for round in 1 2 3 4 5; do
      printf 'round=%s at=%s\n' "$round" "$(date --iso-8601=ns)"
      sudo ip netns exec "$ns" ping -n -c 1 -W 3 "$server"
      file="$out/$phase-$round.bin"
      sudo ip netns exec "$ns" runuser -u "$owner" -- \
        curl -q --noproxy '*' --http1.1 -fsS --connect-timeout 5 --max-time 45 \
        --output "$file" \
        --write-out 'code=%{http_code} local=%{local_ip}:%{local_port} remote=%{remote_ip}:%{remote_port} tcp_s=%{time_connect} total_s=%{time_total} bytes=%{size_download} Bps=%{speed_download}\n' \
        "$base/payload.bin"
      printf '%s  %s\n' "$expected" "$file" | sha256sum -c -
    done
    sudo ip netns exec "$ns" tc -s qdisc show dev "$dev"
  done
  cleanup
  ip netns list | awk '{print $1}' | grep -Fxq "$ns" && exit 1
  tc qdisc show dev "$parent" >"$out/parent-after.log"
  cmp "$out/parent-before.log" "$out/parent-after.log"
  ssh_check >"$out/ssh-after.log"
  cmp "$out/ssh-before.log" "$out/ssh-after.log"
  cat "$out/ssh-after.log"
  printf 'cleanup=OK parent_qdisc=unchanged ssh_host_key=unchanged\n'
} >"$out/results.log" 2>&1

cat "$out/results.log"
curl -q --noproxy '*' -fsS --max-time 10 --data-binary "@$out/results.log" "$base/results"
LAB
```

## 从零生成样本和服务

若不复用已有目录，用下列命令生成，然后在启动段更新 `lab_dir`。复测时两组都用这次生成的同一份文件。

```bash
umask 077
mkdir -p "$HOME/Downloads/bilibili-network"
lab_dir=$(mktemp -d "$HOME/Downloads/bilibili-network/05-tcp-latency-XXXXXX")
head -c 8388608 /dev/urandom >"$lab_dir/payload.bin"
cat >"$lab_dir/server.py" <<'PY'
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
payload = (root / "payload.bin").read_bytes()
digest = hashlib.sha256(payload).hexdigest()

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def reply(self, data):
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/payload.bin":
            self.reply(payload)
        elif self.path == "/sha256":
            self.reply((digest + "\n").encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/results" or self.client_address[0] != "192.168.56.10":
            self.send_error(403)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 65536:
            self.send_error(400)
            return
        data = self.rfile.read(size)
        if len(data) != size:
            self.send_error(400)
            return
        stamp = datetime.now().strftime("%H%M%S%f")
        (root / f"kali-results-{stamp}.log").write_bytes(data)
        self.reply(b"results saved\n")

    def log_message(self, message, *args):
        print(datetime.now().astimezone().isoformat(), self.client_address, message % args, flush=True)

with ThreadingHTTPServer(("192.168.56.20", 8050), Handler) as server:
    print("READY", digest, flush=True)
    server.serve_forever()
PY
printf '%s\n' "$lab_dir"
sha256sum "$lab_dir/payload.bin"
```

## Ubuntu 容器对照复现

容器镜像只包含本机 BusyBox、curl、ping、tc 及其动态库。先打包，再运行隔离对照。该流程不借用外部网络，结束后移除两个容器及 Docker 网桥。

```bash
python3 - <<'PY'
import re
import subprocess
import tarfile

tools = ("/usr/bin/busybox", "/usr/bin/curl", "/usr/bin/ping", "/usr/sbin/tc")
files = set(tools)
for tool in tools:
    result = subprocess.run(["ldd", tool], capture_output=True, text=True)
    files.update(re.findall(r"(?:^\s*|=>\s+)(/\S+) \(0x", result.stdout, re.MULTILINE))
with subprocess.Popen(["docker", "import", "-", "bilibili-netem:bx1qnb"], stdin=subprocess.PIPE) as image:
    with tarfile.open(fileobj=image.stdin, mode="w|", dereference=True) as archive:
        for path in sorted(files):
            archive.add(path, arcname=path.lstrip("/"))
    image.stdin.close()
    if image.wait():
        raise SystemExit("Unable to prepare local netem image")
PY
```

```bash
set -euo pipefail
umask 077
export TZ=Asia/Shanghai LC_ALL=C
root="$HOME/Downloads/bilibili-network/05-tcp-latency-bx1qnB"
out=$(mktemp -d "$root/docker-control-XXXXXX")
printf "%s\n" "$out"
network=bl-tcp-bx1qnb
server=bl-tcp-bx1qnb-server
client=bl-tcp-bx1qnb-client
image=bilibili-netem:bx1qnb
cleanup() {
  docker rm -f "$client" "$server" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker network create --internal "$network" >/dev/null
docker run -d --name "$server" --network "$network" --user "$(id -u):$(id -g)" --cap-drop ALL \
  --mount "type=bind,source=$root/payload.bin,target=/payload/payload.bin,readonly" \
  "$image" /usr/bin/busybox httpd -f -p 8050 -h /payload >/dev/null
docker run -d --name "$client" --network "$network" --cap-drop ALL --cap-add NET_ADMIN --cap-add NET_RAW \
  --mount "type=bind,source=$out,target=/output" \
  "$image" /usr/bin/busybox sleep 120 >/dev/null
server_ip=$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$server")
client_ip=$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$client")
expected=$(sha256sum "$root/payload.bin" | cut -d ' ' -f 1)
uid_gid="$(id -u):$(id -g)"
{
  printf 'network=%s server=%s client=%s sha256=%s\n' "$network" "$server_ip" "$client_ip" "$expected"
  docker exec "$client" /usr/bin/ping -n -c 1 -W 3 "$server_ip"
  for phase in baseline delay80; do
    if [[ "$phase" == delay80 ]]; then
      docker exec "$client" /usr/sbin/tc qdisc add dev eth0 root netem limit 10000 delay 80ms
    fi
    printf '\nphase=%s\n' "$phase"
    docker exec "$client" /usr/sbin/tc -s qdisc show dev eth0
    for round in 1 2 3 4 5; do
      printf 'round=%s at=%s\n' "$round" "$(date --iso-8601=ns)"
      docker exec "$client" /usr/bin/ping -n -c 1 -W 3 "$server_ip"
      file="$phase-$round.bin"
      docker exec --user "$uid_gid" "$client" /usr/bin/curl -q --noproxy '*' --http1.1 -fsS \
        --connect-timeout 5 --max-time 45 --output "/output/$file" \
        --write-out 'code=%{http_code} local=%{local_ip}:%{local_port} remote=%{remote_ip}:%{remote_port} tcp_s=%{time_connect} total_s=%{time_total} bytes=%{size_download} Bps=%{speed_download}\n' \
        "http://$server_ip:8050/payload.bin"
      printf '%s  %s\n' "$expected" "$out/$file" | sha256sum -c -
    done
    docker exec "$client" /usr/sbin/tc -s qdisc show dev eth0
  done
} >"$out/results.log" 2>&1
cleanup
trap - EXIT
if docker inspect "$client" >/dev/null 2>&1 ||
   docker inspect "$server" >/dev/null 2>&1 ||
   docker network inspect "$network" >/dev/null 2>&1; then
  exit 1
fi
cat "$out/results.log"
```

# 09 · HTTP 断点续传与 If-Range

2026-11-20（北京时间），从 Windows 游戏本通过 `ssh ubuntu` 协调 Ubuntu 虚拟机内的 HTTP 实验。三组都先收到同一文件的前 2 MiB 并中断。文件未变时，带强 ETag 的范围请求只取回剩余 6 MiB。普通重试和使用过期 ETag 的请求各取回完整的 8 MiB。三份成品均与对应的源文件逐字节一致，SHA-256 校验通过。

## 拓扑与控制变量

沿用[实验 08](08-tcp-loss-recovery.md)的 Docker 内部网桥。服务端 `172.18.0.2:8050` 和客户端 `172.18.0.3` 均在 Ubuntu 容器内，服务端未发布端口。Windows 的管理 SSH 经 `127.0.0.1:2222` 转发到 Ubuntu 的 `enp0s3`；实验未修改管理接口的队列。

服务端提供 `GET /payload.bin`，支持单段字节范围和使用强 ETag 的 `If-Range`。ETag 是带引号的 `"sha256-<当前文件的 SHA-256>"`，由所选文件的完整内容计算。校验值匹配时，服务端按请求范围响应。校验值失配时，服务端忽略 `Range`，返回完整的新表示。[RFC 9110 第 13.1.5 节 If-Range](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-range) · [RFC 9110 第 14.4 节 Content-Range](https://www.rfc-editor.org/rfc/rfc9110.html#name-content-range)

V1 用随机字节生成，长度为 **8,388,608 字节**（8 MiB）。V2 保持长度不变，只修改偏移 `0`、`2097152`、`8388607` 的三个字节，确保旧残片的内容已经失效。两版通过同一个 URL 提供。V2 替换发生在前两组恢复请求完成之后，置换时刻为北京时间 `18:08:20.714759809`。

每组的首次 GET 都带实验头 `X-Lab-Cut: 1`，服务返回 `200`、V1 ETag 和 `Content-Length: 8388608`，实际发送到 **2,097,152 字节**（2 MiB）后关闭连接。Python 客户端收到 `IncompleteRead`，保存 2 MiB 残片和 V1 ETag。三个残片彼此相同，并与 V1 前缀逐字节一致。这次受控中断用提前结束响应制造，实验 08 则在服务端主动重置已建立的连接。

## 请求、响应与校验结果

表内省略各请求共有的 `Host: 172.18.0.2:8050`、`Accept-Encoding: identity` 及用于关联日志的 `X-Lab-Case`。恢复请求均为 `GET /payload.bin HTTP/1.1`，各用一个新连接。“重新传输”只统计中断后响应的 HTTP 正文字节。

| 恢复组 | 请求 `Range` | 请求 `If-Range` | HTTP 状态 | 响应 `Content-Range` | 响应 ETag | 重新传输 | 复用残片 |
| --- | --- | --- | ---: | --- | --- | ---: | ---: |
| 从头重试 | 未发送 | 未发送 | 200 | 无 | V1 | 8,388,608 B | 0 B |
| 文件未变 | `bytes=2097152-` | V1 | 206 | `bytes 2097152-8388607/8388608` | V1 | 6,291,456 B | 2,097,152 B |
| 文件已变 | `bytes=2097152-` | V1 | 200 | 无 | V2 | 8,388,608 B | 0 B |

| 成品 | 最终字节数 | SHA-256 |
| --- | ---: | --- |
| `restart.bin` | 8,388,608 | `067546d91da1b07981c8797a9e38e84fee06b156d2f627e62438841c51eb1a0f`（V1） |
| `stable.bin` | 8,388,608 | `067546d91da1b07981c8797a9e38e84fee06b156d2f627e62438841c51eb1a0f`（V1） |
| `changed.bin` | 8,388,608 | `593ef11aafb0ed82115aa4ab584a1c0f31e4c9be823d9d1ef9f4d29cf42dace1`（V2） |

收到 `206` 后，客户端先核对返回 ETag、`Content-Range` 起点等于残片字节数、末尾为 `8388607`、总长度为 `8388608`，再核对 `Content-Length` 和读到的实际字节数，最后拼接。收到旧 ETag 对应的 `200` 时，完整响应单独写入 `changed.bin`，保存前还验证其前 2 MiB 与旧残片不同。此组只发了一次带条件的恢复请求，服务端直接在这次响应中发送 V2。

客户端 `client.jsonl` 和服务端 `server.jsonl` 用同一组名和客户端源端口关联。三组首次中断的源端口依次为 `54590`、`54594`、`54602`；恢复请求的端口和日志时刻如下。两端的请求条件、响应头和正文字节数已交叉核对。

| 组名 | 恢复源端口 | 客户端收到响应头（北京时间） | 日志中的保存证据 |
| --- | ---: | --- | --- |
| `restart` | 54610 | `18:08:17.970557` | `transferred_bytes=8388608`，V1 哈希通过。 |
| `stable` | 54626 | `18:08:20.219139` | `transferred_bytes=6291456`、`reused_bytes=2097152`，V1 哈希通过。 |
| `changed` | 54636 | `18:08:22.996740` | `transferred_bytes=8388608`、`reused_bytes=0`，V2 哈希通过。 |

## 三种恢复机制的边界

| 机制 | 谁发起 | 可以复用的数据 |
| --- | --- | --- |
| TCP 在原连接内重传 | 发送端 TCP 根据 ACK、SACK 等反馈或超时补发。[实验 08](08-tcp-loss-recovery.md)抓到了补段和 ACK 越过空洞。 | 仍存续的连接保留已收数据，应用继续读取同一字节流。 |
| 中断后从头重试 | 客户端或其调用脚本发起新连接。实验 08 的 curl 和[第二版 SCP](07-download-timing.md)的批次重跑都重新请求整个文件。 | 本次均复用 0 字节。SCP 的 `.part` 由 Windows 入口清理，TCP 本身不处理应用输出文件。 |
| HTTP 条件续传 | 客户端用残片长度生成 `Range`，用原响应的 ETag 生成 `If-Range`；服务端决定本次返回范围还是完整数据。 | V1 未变时复用 2 MiB，恢复请求少传 25% 的正文字节；V1 已更换为 V2 时复用 0 字节。 |

## 复现

将下方完整的 Bash 脚本保存为 Windows 的 `run-http-range.sh`，在 PowerShell 运行。脚本复用 Ubuntu 本地 Docker 权限，用本机 Python 和动态库构建临时镜像。

```powershell
Get-Content -LiteralPath .\run-http-range.sh -Raw |
    ssh -oBatchMode=yes ubuntu "tr -d '\r' | bash -s"
ssh -oBatchMode=yes ubuntu 'printf "%s\n" "$SSH_CONNECTION"'
```

首行 `RECORDS=` 会打印 Ubuntu 日志目录。可在 Ubuntu 核对三份成品与原始请求日志。

```bash
records="$HOME/Downloads/bilibili-network/09-http-range-mNrbew"
cat "$records/server.jsonl" "$records/client.jsonl"
sha256sum "$records/input/"v[12].bin "$records/client/"*.bin
```


<details>
<summary>完整实验脚本</summary>

```bash
#!/usr/bin/env bash
set -euo pipefail
umask 077
export LC_ALL=C TZ=Asia/Shanghai

base="$HOME/Downloads/bilibili-network"
mkdir -p -- "$base"
lab=$(mktemp -d "$base/09-http-range-XXXXXX")
printf 'RECORDS=%s\n' "$lab"
name="bl-http09-$(basename "$lab" | cut -d- -f4)"
image="bl-http09:$name"
server="$name-server"
uid_gid="$(id -u):$(id -g)"
mkdir "$lab/input" "$lab/client"

host_checks() { ip -br -4 addr; ip -4 route show; tc qdisc show; }
host_checks >"$lab/host-before.log"
cleanup() {
  if docker container inspect "$server" >/dev/null 2>&1; then docker rm -f "$server" >/dev/null; fi
  if docker network inspect "$name" >/dev/null 2>&1; then docker network rm "$name" >/dev/null; fi
  if docker image inspect "$image" >/dev/null 2>&1; then docker image rm "$image" >/dev/null; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Package the Ubuntu VM's Python and local libraries, without pulling an image.
python3 - "$image" <<'PY'
import pathlib
import re
import subprocess
import sys
import sysconfig
import tarfile

exe = pathlib.Path(sys.executable).resolve()
stdlib = pathlib.Path(sysconfig.get_path("stdlib"))
libs = set()
for binary in (exe, *sorted((stdlib / "lib-dynload").glob("*.so"))):
    output = subprocess.check_output(["ldd", binary], text=True)
    libs.update(re.findall(r"(?:^\s*|=>\s+)(/\S+) \(0x", output, re.MULTILINE))

def filter_stdlib(entry):
    skipped = {"__pycache__", "site-packages", "dist-packages"}
    return None if skipped.intersection(pathlib.PurePosixPath(entry.name).parts) else entry

with subprocess.Popen(["docker", "import", "-", sys.argv[1]], stdin=subprocess.PIPE) as proc:
    with tarfile.open(fileobj=proc.stdin, mode="w|", dereference=True) as archive:
        archive.add(exe, arcname="usr/bin/lab-python")
        archive.add(stdlib, arcname=str(stdlib).lstrip("/"), filter=filter_stdlib)
        for lib in sorted(libs):
            archive.add(lib, arcname=lib.lstrip("/"))
    proc.stdin.close()
    if proc.wait():
        raise SystemExit("Local image import failed")
PY

cat >"$lab/range.py" <<'PY'
import contextlib
import datetime
import hashlib
import http.client
import http.server
import json
import os
import pathlib
import re
import sys

SIZE = 8 * 1024 * 1024
CUT = 2 * 1024 * 1024
INPUT = pathlib.Path("/input")
OUTPUT = pathlib.Path("/output")
RESOURCE = "/payload.bin"
PORT = 8050
CASES = ("restart", "stable", "changed")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def tag(data):
    return f'"sha256-{digest(data)}"'

def log(event, **values):
    print(json.dumps({"time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "event": event, **values}, sort_keys=True), flush=True)

def byte_range(value, size):
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", value)
    if not match or not any(match.groups()):
        return None
    first, last = match.groups()
    if not first:
        count = int(last)
        return (max(0, size - count), size - 1)
    return (int(first), min(int(last), size - 1) if last else size - 1)

class Service(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != RESOURCE:
            self.send_error(404)
            return
        active = (INPUT / "active.bin").read_bytes()
        current = tag(active)
        size = len(active)
        requested = self.headers.get("Range")
        validator = self.headers.get("If-Range")
        span = byte_range(requested, size) if requested and validator in (None, current) else None

        status, body, content_range = 200, active, None
        if span is not None:
            first, last = span
            if first >= size or first > last:
                status, body, content_range = 416, b"", f"bytes */{size}"
            else:
                status, body = 206, active[first:last + 1]
                content_range = f"bytes {first}-{last}/{size}"

        headers = {"Content-Type": "application/octet-stream", "Content-Length": str(len(body)),
                   "Accept-Ranges": "bytes", "ETag": current, "Connection": "close"}
        if content_range is not None:
            headers["Content-Range"] = content_range
        cut = status == 200 and requested is None and self.headers.get("X-Lab-Cut") == "1"
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        sent = body[:CUT] if cut else body
        self.wfile.write(sent)
        self.wfile.flush()
        self.close_connection = True
        log("served", case=self.headers.get("X-Lab-Case"), request=self.requestline,
            peer=self.client_address, request_headers=dict(self.headers), status=status,
            response_headers=headers, sent_body_bytes=len(sent), forced_cut=cut)

@contextlib.contextmanager
def request(host, case, headers):
    sent = {"X-Lab-Case": case, **headers}
    with contextlib.closing(http.client.HTTPConnection(host, PORT, timeout=10)) as conn:
        conn.connect()
        local = conn.sock.getsockname()
        conn.request("GET", RESOURCE, headers=sent)
        response = conn.getresponse()
        log("headers", case=case, request=f"GET {RESOURCE} HTTP/1.1", local=local,
            request_headers=sent, status=response.status, response_headers=dict(response.getheaders()))
        yield response

def save_partial(host, case, expected):
    with request(host, f"initial-{case}", {"X-Lab-Cut": "1"}) as response:
        old_tag = response.getheader("ETag")
        assert response.status == 200 and response.getheader("Content-Range") is None
        assert int(response.getheader("Content-Length")) == SIZE
        assert old_tag == f'"sha256-{expected}"'
        try:
            response.read()
        except http.client.IncompleteRead as error:
            assert len(error.partial) == CUT and error.expected == SIZE - CUT
            (OUTPUT / f"{case}.part").write_bytes(error.partial)
            (OUTPUT / f"{case}.etag").write_text(old_tag, encoding="ascii")
            log("interrupted", case=case, partial_bytes=len(error.partial),
                partial_sha256=digest(error.partial), expected_missing=error.expected, error=type(error).__name__)
        else:
            raise RuntimeError("Expected an interrupted response")

def finish(host, case, expected):
    partial = (OUTPUT / f"{case}.part").read_bytes()
    assert len(partial) == CUT
    old_tag = (OUTPUT / f"{case}.etag").read_text(encoding="ascii")
    headers = {} if case == "restart" else {"Range": f"bytes={len(partial)}-", "If-Range": old_tag}
    with request(host, case, headers) as response:
        current = response.getheader("ETag")
        content_range = response.getheader("Content-Range")
        assert current == f'"sha256-{expected}"'
        if case == "stable":
            assert response.status == 206 and current == old_tag
            match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", content_range or "")
            assert match and tuple(map(int, match.groups())) == (len(partial), SIZE - 1, SIZE)
            expected_body = SIZE - len(partial)
        else:
            assert response.status == 200 and content_range is None
            assert (current != old_tag) if case == "changed" else (current == old_tag)
            expected_body = SIZE
        assert int(response.getheader("Content-Length")) == expected_body
        body = response.read()
        assert len(body) == expected_body

    if case == "changed":
        assert body[:len(partial)] != partial
    complete = partial + body if case == "stable" else body
    assert len(complete) == SIZE and digest(complete) == expected
    dest = OUTPUT / f"{case}.bin"
    dest.write_bytes(complete)
    log("saved", case=case, transferred_bytes=len(body), reused_bytes=len(partial) if case == "stable" else 0,
        final_bytes=dest.stat().st_size, final_sha256=digest(dest.read_bytes()), final_path=str(dest))

if sys.argv[1] == "fixture":
    folder = pathlib.Path(sys.argv[2])
    data = os.urandom(SIZE)
    changed = bytearray(data)
    for offset in (0, CUT, SIZE - 1):
        changed[offset] ^= 0xff
    (folder / "v1.bin").write_bytes(data)
    (folder / "v2.bin").write_bytes(changed)
elif sys.argv[1] == "serve":
    with http.server.HTTPServer(("0.0.0.0", PORT), Service) as httpd:
        log("ready", port=PORT)
        httpd.serve_forever()
elif sys.argv[1] == "prepare":
    for case in CASES:
        save_partial(sys.argv[2], case, sys.argv[3])
else:
    finish(sys.argv[2], sys.argv[1], sys.argv[3])
PY

python3 "$lab/range.py" fixture "$lab/input"
cp -- "$lab/input/v1.bin" "$lab/input/active.bin"
old=$(sha256sum "$lab/input/v1.bin" | cut -d ' ' -f1)
new=$(sha256sum "$lab/input/v2.bin" | cut -d ' ' -f1)
test "$old" != "$new"
printf 'v1=%s\nv2=%s\n' "$old" "$new" | tee "$lab/source-hashes.log"

docker network create --internal "$name" >"$lab/network-id.log"
docker run -d --name "$server" --network "$name" --cap-drop ALL --read-only --user "$uid_gid" \
  --mount "type=bind,source=$lab/input,target=/input,readonly" \
  --mount "type=bind,source=$lab/range.py,target=/range.py,readonly" \
  "$image" /usr/bin/lab-python -B /range.py serve >/dev/null
for _ in {1..100}; do
  if docker logs "$server" 2>&1 | grep -q '"event": "ready"'; then break; fi
  sleep .05
done
docker logs "$server" 2>&1 | grep '"event": "ready"'
host=$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$server")
docker network inspect "$name" --format 'internal={{.Internal}}' >"$lab/topology.log"
printf 'server=%s:8050 published_ports=%s\n' "$host" "$(docker port "$server")" | tee -a "$lab/topology.log"

client() {
  docker run --rm --network "$name" --cap-drop ALL --read-only --user "$uid_gid" \
    --mount "type=bind,source=$lab/client,target=/output" \
    --mount "type=bind,source=$lab/range.py,target=/range.py,readonly" \
    "$image" /usr/bin/lab-python -B /range.py "$1" "$host" "$2"
}
client prepare "$old" | tee "$lab/client.jsonl"
cmp "$lab/client/restart.part" "$lab/client/stable.part"
cmp "$lab/client/restart.part" "$lab/client/changed.part"
client restart "$old" | tee -a "$lab/client.jsonl"
client stable "$old" | tee -a "$lab/client.jsonl"
cp -- "$lab/input/v2.bin" "$lab/input/next.bin"
mv -T -- "$lab/input/next.bin" "$lab/input/active.bin"
date --iso-8601=ns >"$lab/replaced-at.log"
client changed "$new" | tee -a "$lab/client.jsonl"
docker logs "$server" >"$lab/server.jsonl" 2>&1
printf '%s  %s\n' "$old" "$lab/client/restart.bin" "$old" "$lab/client/stable.bin" \
  "$new" "$lab/client/changed.bin" | sha256sum -c - | tee "$lab/verification.log"
sha256sum "$lab/client/"*.part >"$lab/partials.sha256"

cleanup
! docker container inspect "$server" >/dev/null 2>&1 || exit 1
! docker network inspect "$name" >/dev/null 2>&1 || exit 1
! docker image inspect "$image" >/dev/null 2>&1 || exit 1
host_checks >"$lab/host-after.log"
cmp "$lab/host-before.log" "$lab/host-after.log"
printf 'cleanup=OK host_interfaces_routes_queues=unchanged\n' | tee "$lab/cleanup.log"
trap - EXIT
```

</details>

## 原始记录与清理

Ubuntu 仓库外的 `~/Downloads/bilibili-network/09-http-range-mNrbew/` 保存 V1、V2、三份中断残片、三份成品、`server.jsonl`、`client.jsonl`、`verification.log` 及清理记录。Windows 的 `Downloads\bilibili-network\09-http-range-20261120-100610Z\` 保存两端日志副本、运行脚本和独立复核记录。

已删除临时 HTTP 服务容器、内部网桥和临时镜像；客户端容器执行完即删除。Ubuntu 宿主接口、IPv4 路由和队列与预检一致。清理后 Windows 重新执行 `ssh ubuntu` 成功，Ubuntu 端记录的 `SSH_CONNECTION` 为 `10.0.2.2 61400 10.0.2.15 22`。

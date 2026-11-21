# 10 · 游戏本到轻薄本的 SSH 传输

2026-11-21 13:40（北京时间），从 Windows 游戏本交替向 Ubuntu 虚拟机与 Linux 轻薄本上传同一个 36,881,744 字节的 MP4。两端各五轮，十次 SHA-256 均与 Windows 源文件一致。

## 路径

| 接收端 | SSH 连接 | 路径证据 | ICMP RTT |
| --- | --- | --- | --- |
| Ubuntu | `192.168.56.1 → 192.168.56.20:22` | Ubuntu 的 `SSH_CONNECTION` 与 Windows 选用的 Host-Only 目标一致 | 三次均显示 <1 ms |
| 轻薄本 | Windows Tailscale 地址 → 轻薄本 Tailscale 地址的 TCP 22 | `ssh -G lightbook` 选用 Tailscale 地址。每轮上传结束后，目标状态均为 `active; direct`，底层端点为校园网 IPv6 地址和 UDP 端口 | 测速后向 Tailscale IP 探测，三次均显示 1 ms |

普通 `ping lightbook` 无法解析 OpenSSH 别名，因此轻薄本组改用实际 Tailscale IP。测速后的三次 `tailscale ping` 分别为 1、2、1 ms，均经同一 IPv6 端点直连。预检记录显示两端位于同一校园网 IPv6 前缀。物理房间位置尚待现场确认。

## 结果

| 轮次 | Ubuntu 耗时 (s) | Ubuntu 吞吐 (MiB/s) | 轻薄本耗时 (s) | 轻薄本吞吐 (MiB/s) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1.147 | 30.657 | 1.646 | 21.367 |
| 2 | 1.161 | 30.294 | 1.647 | 21.353 |
| 3 | 1.406 | 25.015 | 1.635 | 21.516 |
| 4 | 0.844 | 41.681 | 1.640 | 21.450 |
| 5 | 1.264 | 27.824 | 1.683 | 20.904 |
| **中位数** | **1.161** | **30.294** | **1.646** | **21.367** |
| **范围** | 0.844–1.406 | 25.015–41.681 | 1.635–1.683 | 20.904–21.516 |

本轮上传到轻薄本的中位耗时比上传到 Ubuntu 多 0.485 秒。两组接收设备、链路、文件系统与后台负载同时变化，结果描述的是这次 SCP 的端到端耗时。

## 复现与校验

从 Windows PowerShell 执行。先用 SSH 在两端各创建一个独立的临时目录，再将绝对路径填入 `$ubuntuDir` 和 `$lightbookDir`。每轮先向 Ubuntu 上传，再向轻薄本上传。SCP 使用独立连接、默认 SFTP 模式、固定加密算法并关闭压缩和连接复用。秒表覆盖 SCP 进程启动到退出，校验在计时结束后执行。

```powershell
$source = Join-Path $env:USERPROFILE 'Downloads\bilibili-network\BV1Fb4111732_p1.mp4'
$expected = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$common = @('-oBatchMode=yes','-oStrictHostKeyChecking=yes','-oConnectTimeout=10',
    '-oControlMaster=no','-oCompression=no','-c','chacha20-poly1305@openssh.com')
$ubuntu = @('-F','NUL','-oHostKeyAlias=[127.0.0.1]:2222') + $common
$ubuntuDir = ssh.exe @ubuntu wyh@192.168.56.20 'mktemp -d /tmp/bilibili-ubuntu-scp.XXXXXXXX'
$lightbookDir = ssh.exe @common lightbook 'mktemp -d /tmp/bilibili-lightbook-scp.XXXXXXXX'
ssh.exe @ubuntu wyh@192.168.56.20 'printenv SSH_CONNECTION'
ssh.exe @common lightbook 'printenv SSH_CONNECTION'

# 每轮使用不同文件名，分别记录下列两个命令的 TotalSeconds。
Measure-Command { scp.exe @ubuntu -q -- $source "wyh@192.168.56.20:$ubuntuDir/upload-1.mp4" }
Measure-Command { scp.exe @common -q -- $source "lightbook:$lightbookDir/upload-1.mp4" }
tailscale.exe status
ssh.exe @ubuntu wyh@192.168.56.20 "sha256sum -- '$ubuntuDir/upload-1.mp4'"
ssh.exe @common lightbook "sha256sum -- '$lightbookDir/upload-1.mp4'"
$expected
```

每次确认 SCP 成功后，将接收端哈希与源文件比较。吞吐量等于文件字节数除以 1,048,576 再除以实测秒数。最后删除本轮副本和对应的临时目录。本次已分别在两端复核实验接收目录清理完成。

Windows 原始 CSV、SSH 路径探测和 Tailscale 状态保存在 `%TEMP%\bilibili-lightbook-ssh-20261121-134047\`。测量脚本来自轻薄本上的实验准备目录，Windows 执行副本增加了每轮路径取证和临时目录校验。

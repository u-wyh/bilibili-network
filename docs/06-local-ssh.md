# 06 · 游戏本与 Ubuntu 的双向 SCP 对照

2026-11-20（北京时间），在同一台 Windows 游戏本上比较 VirtualBox NAT 转发和 Host-Only 直连的上传、下载表现。下载方向对应 [PowerShell 下载工具](../download-bilibili.ps1) 从 Ubuntu 取回视频的步骤。本轮使用游戏本和 Ubuntu 虚拟机，路径证据可与[实验 04](04-ssh-transfer-paths.md)对照。

## 路径

| 路径 | Windows 连接目标 | Ubuntu 端 `SSH_CONNECTION` 样本 |
| --- | --- | --- |
| VirtualBox NAT 转发 | `127.0.0.1:2222` | `10.0.2.2 54327 10.0.2.15 22` |
| Host-Only 直连 | `192.168.56.20:22` | `192.168.56.1 54332 192.168.56.20 22` |

## 方法

使用同一个 36,881,744 字节的 `BV1Fb4111732_p1.mp4`。上传从 Windows 读源文件，下载从 Ubuntu 上预置且校验过的副本读取。每轮依次执行 NAT 上传、NAT 下载、Host-Only 上传、Host-Only 下载，共五轮。每次用独立 SCP 进程，固定 SFTP、`chacha20-poly1305@openssh.com`、禁用压缩和连接复用，沿用 Ubuntu 已验证的主机密钥。用 PowerShell `Stopwatch` 记录 SCP 调用至退出的总耗时，含建连、认证、文件读写和协议收尾。每次在计时结束后比对 SHA-256，二十次全部通过。吞吐量按文件 MiB 除以总秒数计算。

## 结果

| 路径 | 方向 | 五轮总耗时 (s) | 总耗时中位数 (s) | 吞吐中位数 (MiB/s) |
| --- | --- | --- | ---: | ---: |
| NAT | Windows → Ubuntu | 2.101, 1.975, 2.073, 1.816, 1.815 | 1.975 | 17.81 |
| Host-Only | Windows → Ubuntu | 1.662, 1.791, 1.649, 1.685, 1.619 | 1.662 | 21.16 |
| NAT | Ubuntu → Windows | 2.156, 2.076, 1.836, 2.071, 1.674 | 2.071 | 16.98 |
| Host-Only | Ubuntu → Windows | 3.041, 2.399, 2.334, 2.188, 2.300 | 2.334 | 15.07 |

此前 11 月 18 日的 Host-Only 上传基线为 1.561 秒、22.53 MiB/s。此次 Host-Only 上传中位数较低，NAT 下载中位数较低。两种方向会互换读写端，每轮的执行顺序固定，后台负载未隔离。结果描述这台机器在该文件及该运行条件下的 SCP 端到端表现。

## 复现

在 Windows PowerShell 按下列参数分别运行两条路径。先在 Ubuntu 创建独立临时目录，上传源文件并核对哈希，再把 `$remoteDir` 设为该目录的绝对路径。每次换一个输出文件名，按上面的顺序分别计时五轮。

```powershell
$source = Join-Path $env:USERPROFILE 'Downloads\bilibili-network\BV1Fb4111732_p1.mp4'
$expected = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$common = @('-F','NUL','-oBatchMode=yes','-oStrictHostKeyChecking=yes',
    '-oHostKeyAlias=[127.0.0.1]:2222','-oConnectTimeout=5',
    '-oControlMaster=no','-oCompression=no','-c','chacha20-poly1305@openssh.com')

# NAT 用 127.0.0.1 和 2222。Host-Only 用 192.168.56.20 和 22。
$endpoint = 'wyh@127.0.0.1'
$port = 2222
ssh.exe @common -p $port $endpoint 'printenv SSH_CONNECTION'
$remotePrefix = $endpoint + ':' + $remoteDir
$upload = Measure-Command {
    scp.exe @common -q -P $port $source "$remotePrefix/upload-1.mp4"
    if ($LASTEXITCODE -ne 0) { throw '上传失败' }
}
$download = Measure-Command {
    scp.exe @common -q -P $port "$remotePrefix/source.mp4" ./download-1.mp4
    if ($LASTEXITCODE -ne 0) { throw '下载失败' }
}
$upload.TotalSeconds
$download.TotalSeconds
ssh.exe @common -p $port $endpoint "sha256sum -- '$remoteDir/upload-1.mp4'"
(Get-FileHash -LiteralPath ./download-1.mp4 -Algorithm SHA256).Hash
```

原始 CSV 和套接字记录保存在 Windows 下载目录的 `bilibili-network/06-local-ssh-20261120-150057/`。Windows 与 Ubuntu 的实验文件副本均已清理，原始样本仍在下载目录。

# 07 · 第二版下载计时与双路径取回

2026-11-20 在 Windows 游戏本和 Ubuntu 虚拟机上验收下载工具。正式下载沿用 `ssh ubuntu` 和默认 NAT 转发。测量两条 SCP 路径时，固定同一 Ubuntu 源文件并显式指定目标地址和端口。

## 实际下载与批量验收

Windows PowerShell 5.1 从一个新目录开始运行清单。清单包含一个无效 BV、有效的 `BV1Fb4111732 1`、同一个 BV 的重复项，以及一个超出整数范围的分 P。首个无效项后仍完成了 P1 下载，重复项直接跳过。批次汇总为 `Saved: 1`、`Existing: 1`、`Failed: 2`，退出码为 `1`。随后以单条模式对同一输出目录重跑，提示保留已有文件，SHA-256 和修改时间保持一致。

中断测试复用已下载的 Ubuntu 源文件。测试驱动在限速的真实 SCP 写入 32,768 字节后终止该进程，并把失败状态交给批量入口。失败项没有生成 MP4，残留的 `.part` 被清理。清单下一行重试同一个条目，成功取回并通过 SHA-256 校验，另一份预先放置的测试文件哈希保持一致。故障注入过程记录在 `interrupt-test.log`。

| 阶段 | 耗时 | 计时口径 |
| --- | ---: | --- |
| Ubuntu 下载与合并 | 10.976 s | Ubuntu 上的 Bash `time` 包住整个 Bash 下载入口，含视频与音频下载、合并及成品保存，SSH 建连在计时窗口之外。 |
| SCP 取回 | 2.623 s | Windows 的 `Stopwatch` 从调用 SCP 计到返回，包含 SSH/SFTP 会话建立、文件写入和协议收尾，最终移动和 SHA-256 校验在计时窗口之外。 |

两端 MP4 均为 **36,881,744 字节**，SHA-256 为 `5d1f9fdd32d7aeec7b195f169381f8ae43a9028770044bd19777696961346c6e`。Ubuntu `ffprobe` 确认有 H.264 640 × 360 视频、AAC 音频，时长为 634.566313 秒。Windows 验收文件与原始日志保存在仓库外的 `Downloads\bilibili-network\v2-acceptance-20261120\`，MP4 位于其 `Windows MP4\` 子目录。Ubuntu 源文件在 `~/Downloads/bilibili-network/windows-8c0d926a2bc94c58b698b812292e8916/BV1Fb4111732_p1.mp4`。

在 Windows 仓库根目录复现混合清单。批量命令会下载有效项并在结束后返回非零状态，随后单条命令应提示保留已收到的 MP4。

```powershell
$run = Join-Path $HOME ('Downloads\bilibili-network\v2-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
$list = Join-Path $run 'videos.txt'
$out = Join-Path $run 'Windows MP4'
@('invalid-first','BV1Fb4111732 1','BV1Fb4111732','BV1Fb4111732 2147483648') |
    Set-Content -LiteralPath $list -Encoding UTF8
powershell.exe -NoProfile -File .\download-bilibili.ps1 -ListPath $list -OutputDirectory $out
.\download-bilibili.ps1 BV1Fb4111732 -OutputDirectory $out
Get-FileHash -LiteralPath (Join-Path $out 'BV1Fb4111732_p1.mp4') -Algorithm SHA256
```

## Ubuntu → Windows 路径对照

每条路径从同一个 Ubuntu 成品取回五次，每轮交替安排先跑的路径，轮间有一秒间隔。每次启动独立 SCP 进程，默认使用 SFTP，与[实验 06](06-local-ssh.md)一样固定 `chacha20-poly1305@openssh.com`、禁用压缩和连接复用。Windows `Stopwatch` 的计时口径与上表 SCP 阶段相同。每轮计时后检查字节数和 SHA-256，再删除这一轮的副本，十次均通过。吞吐为文件字节数 ÷ 1,048,576 ÷ 总秒数。测速不包含实际下载或合并。

| 路径 | Windows 目标 | Ubuntu `SSH_CONNECTION` 样本 |
| --- | --- | --- |
| VirtualBox NAT 转发 | `127.0.0.1:2222` | `10.0.2.2 58589 10.0.2.15 22` |
| Host-Only 直连 | `192.168.56.20:22` | `192.168.56.1 58590 192.168.56.20 22` |

| 路径 | 五轮总耗时 (s) | 总耗时中位数与范围 (s) | 吞吐中位数与范围 (MiB/s) |
| --- | --- | --- | --- |
| NAT 转发 | 2.001, 1.927, 1.790, 2.248, 2.387 | 2.001（1.790–2.387） | 17.58（14.73–19.65） |
| Host-Only 直连 | 2.420, 2.047, 2.383, 2.483, 2.308 | 2.383（2.047–2.483） | 14.76（14.16–17.18） |

实验 06 同方向的中位数为 NAT **2.071 s / 16.98 MiB/s**、Host-Only **2.334 s / 15.07 MiB/s**。两次实验的 NAT 下载中位耗时均较短，本次两组耗时范围有重叠。实验 06 交叉执行上传和下载，本次仅取回文件，交替两条路径。Windows 每次试验前的整机 CPU 样点在 5%–22%，后台负载与文件缓存未隔离。单文件各五次反映此次端到端表现，无法把差异单独归因于 NAT 或 Host-Only。

## 复现路径测速

先按 [Windows 下载步骤](../README.md#windows-快速开始) 得到同一轮的 Windows 和 Ubuntu MP4。把 `$remoteFile` 设为 Ubuntu 脚本打印的成品绝对路径，把 `$localFile` 设为已经取回的本地文件。测速会使用已验证的 Ubuntu 主机密钥。以下例子沿用此次实验的 SSH 用户和端口。

```powershell
$remoteFile = '/home/wyh/Downloads/bilibili-network/windows-8c0d926a2bc94c58b698b812292e8916/BV1Fb4111732_p1.mp4'
$localFile = Join-Path $HOME 'Downloads\bilibili-network\v2-acceptance-20261120\Windows MP4\BV1Fb4111732_p1.mp4'
$expected = (Get-FileHash -LiteralPath $localFile -Algorithm SHA256).Hash
$bytes = (Get-Item -LiteralPath $localFile).Length
$common = @('-F','NUL','-oBatchMode=yes','-oStrictHostKeyChecking=yes',
    '-oHostKeyAlias=[127.0.0.1]:2222','-oConnectTimeout=5',
    '-oControlMaster=no','-oCompression=no','-c','chacha20-poly1305@openssh.com')
$routes = @{
    NAT = @{ Endpoint = 'wyh@127.0.0.1'; Port = 2222 }
    HostOnly = @{ Endpoint = 'wyh@192.168.56.20'; Port = 22 }
}
$rows = foreach ($round in 1..5) {
    $order = if ($round % 2) { 'NAT','HostOnly' } else { 'HostOnly','NAT' }
    foreach ($path in $order) {
        $route = $routes[$path]
        $scratch = New-TemporaryFile
        try {
            $timer = [Diagnostics.Stopwatch]::StartNew()
            scp.exe @common -q -P $route.Port "$($route.Endpoint):$remoteFile" $scratch.FullName
            $timer.Stop()
            if ($LASTEXITCODE -ne 0) { throw "scp failed for $path round $round" }
            if ((Get-FileHash -LiteralPath $scratch.FullName -Algorithm SHA256).Hash -ne $expected) {
                throw "SHA-256 mismatch for $path round $round"
            }
            $seconds = $timer.Elapsed.TotalSeconds
            [pscustomobject]@{ Path=$path; Round=$round; Seconds=$seconds; MiBps=$bytes / 1MB / $seconds }
        } finally {
            Remove-Item -LiteralPath $scratch.FullName
        }
        Start-Sleep -Seconds 1
    }
}
$rows | Format-Table
$rows | Group-Object Path | ForEach-Object {
    $sorted = @($_.Group | Sort-Object Seconds)
    [pscustomobject]@{
        Path = $_.Name
        MedianSeconds = $sorted[2].Seconds
        MinSeconds = $sorted[0].Seconds
        MaxSeconds = $sorted[-1].Seconds
        MedianMiBps = $sorted[2].MiBps
        MinMiBps = $sorted[-1].MiBps
        MaxMiBps = $sorted[0].MiBps
    }
}
```

原始记录为 Windows 验收目录内的 `batch.log`、`acceptance.json`、`ffprobe.json` 和 `scp-benchmark/rounds.csv`。计时副本已清理，保留用于验收的两端原始 MP4。

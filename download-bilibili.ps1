#requires -Version 5.1
[CmdletBinding(DefaultParameterSetName = 'Single')]
param(
    [Parameter(Mandatory, Position = 0, ParameterSetName = 'Single')]
    [ValidatePattern('(?-i:\ABV[A-Za-z0-9]{10}\z)')]
    [string]$Bv,

    [Parameter(Mandatory, ParameterSetName = 'Batch')]
    [ValidateNotNullOrEmpty()]
    [string]$ListPath,

    [ValidateRange(1, [int]::MaxValue)]
    [int]$Part = 1,

    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

if (-not $PSBoundParameters.ContainsKey('OutputDirectory')) {
    $downloads = Get-ItemPropertyValue -ErrorAction SilentlyContinue `
        -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders' `
        -Name '{374DE290-123F-4565-9164-39C4925E467B}'
    if (-not $downloads) {
        $downloads = Join-Path $HOME 'Downloads'
    }
    $OutputDirectory = Join-Path ([Environment]::ExpandEnvironmentVariables($downloads)) 'bilibili-network'
}

$outputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)

function Invoke-BilibiliDownload {
    param([string]$VideoId, [int]$VideoPart, [string]$DestinationDirectory)

    $fileName = "${VideoId}_p${VideoPart}.mp4"
    $target = Join-Path $DestinationDirectory $fileName
    if (Test-Path -LiteralPath $target) {
        Write-Host "Already exists. Keeping: $target"
        return 'Existing'
    }

    [IO.Directory]::CreateDirectory($DestinationDirectory) | Out-Null
    Get-Command ssh.exe, scp.exe -CommandType Application | Out-Null

    $runId = [guid]::NewGuid().ToString('N')
    $remoteDir = "Downloads/bilibili-network/windows-$runId"
    # Only validated BV/part values and the generated directory enter the remote command.
    $remoteCommand = 'bash -c ''TIMEFORMAT=Ubuntu\ download\ and\ merge:\ %3R\ s; {{ time ~/bilibili-network/download-bilibili.sh --part {0} --output ~/{1} {2}; }} 2>&1''' -f $VideoPart, $remoteDir, $VideoId
    & ssh.exe ubuntu $remoteCommand | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Ubuntu download failed for $VideoId P$VideoPart (ssh exit code $LASTEXITCODE). See the ssh and downloader output above."
    }

    $remoteFile = "ubuntu:$remoteDir/$fileName"
    $partial = Join-Path $DestinationDirectory ".$runId.part"
    try {
        $clock = [Diagnostics.Stopwatch]::StartNew()
        & scp.exe $remoteFile $partial | Out-Host
        $clock.Stop()
        $scpExitCode = $LASTEXITCODE
        Write-Host ('SCP retrieval: {0:F3} s' -f $clock.Elapsed.TotalSeconds)
        if ($scpExitCode -ne 0) {
            throw "MP4 transfer failed (scp exit code $scpExitCode). Ubuntu file: $remoteFile"
        }
        $received = Get-Item -LiteralPath $partial -ErrorAction SilentlyContinue
        if (-not $received -or $received.Length -le 0) {
            throw "MP4 transfer produced no data. Ubuntu file: $remoteFile"
        }
        try {
            [IO.File]::Move($partial, $target)
        } catch [IO.IOException] {
            if (Test-Path -LiteralPath $target) {
                Write-Host "Already exists. Keeping: $target"
                return 'Existing'
            }
            throw
        }
    } finally {
        if (Test-Path -LiteralPath $partial) {
            Remove-Item -LiteralPath $partial
        }
    }

    Write-Host "Saved: $target"
    return 'Saved'
}

if ($PSCmdlet.ParameterSetName -eq 'Single') {
    $null = Invoke-BilibiliDownload $Bv $Part $outputPath
    return
}

$lineNumber = 0
$results = foreach ($line in (Get-Content -LiteralPath $ListPath -Encoding UTF8)) {
    $lineNumber++
    $entry = $line.Trim()
    if (-not $entry -or $entry.StartsWith('#')) {
        continue
    }

    $status = 'Failed'
    $detail = ''
    try {
        $match = [regex]::Match($entry, '\A(BV[A-Za-z0-9]{10})(?:\s+([0-9]+))?\z')
        if (-not $match.Success) {
            throw 'Expected a BV ID followed by an optional positive part number.'
        }
        $videoId = $match.Groups[1].Value
        $videoPart = $Part
        if ($match.Groups[2].Success -and
            (-not [int]::TryParse($match.Groups[2].Value, [ref]$videoPart) -or $videoPart -lt 1)) {
            throw 'Part number is out of range.'
        }
        $entry = "$videoId P$videoPart"
        Write-Host "Processing line ${lineNumber}: $entry"
        $status = Invoke-BilibiliDownload $videoId $videoPart $outputPath
    } catch {
        $detail = $_.Exception.Message
    }
    [pscustomobject]@{ Line = $lineNumber; Entry = $entry; Status = $status; Detail = $detail }
}

$failedCount = 0
foreach ($status in 'Saved', 'Existing', 'Failed') {
    $items = @($results | Where-Object Status -eq $status)
    Write-Host "${status}: $($items.Count)"
    foreach ($item in $items) {
        $detail = if ($item.Detail) { " - $($item.Detail)" } else { '' }
        Write-Host "  Line $($item.Line): $($item.Entry)$detail"
    }
    if ($status -eq 'Failed') {
        $failedCount = $items.Count
    }
}
if ($failedCount -gt 0) {
    throw "Batch finished with $failedCount failed item(s). See the summary above."
}

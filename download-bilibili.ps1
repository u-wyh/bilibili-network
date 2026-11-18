#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidatePattern('(?-i:\ABV[A-Za-z0-9]{10}\z)')]
    [string]$Bv,

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
$fileName = "${Bv}_p${Part}.mp4"
$target = Join-Path $outputPath $fileName
if (Test-Path -LiteralPath $target) {
    Write-Host "Already exists. Keeping: $target"
    return
}

[IO.Directory]::CreateDirectory($outputPath) | Out-Null
Get-Command ssh.exe, scp.exe -CommandType Application | Out-Null

$runId = [guid]::NewGuid().ToString('N')
$remoteDir = "Downloads/bilibili-network/windows-$runId"
$remoteCommand = "~/bilibili-network/download-bilibili.sh --part $Part --output ~/$remoteDir $Bv"
& ssh.exe ubuntu $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Ubuntu download failed for $Bv P$Part (ssh exit code $LASTEXITCODE). See the ssh and downloader output above."
}

$remoteFile = "ubuntu:$remoteDir/$fileName"
$partial = Join-Path $outputPath ".$runId.part"
try {
    & scp.exe $remoteFile $partial
    if ($LASTEXITCODE -ne 0) {
        throw "MP4 transfer failed (scp exit code $LASTEXITCODE). Ubuntu file: $remoteFile"
    }
    if ((Get-Item -LiteralPath $partial).Length -le 0) {
        throw "MP4 transfer produced an empty file. Ubuntu file: $remoteFile"
    }
    try {
        [IO.File]::Move($partial, $target)
    } catch [IO.IOException] {
        if (Test-Path -LiteralPath $target) {
            Write-Host "Already exists. Keeping: $target"
            return
        }
        throw
    }
} finally {
    if (Test-Path -LiteralPath $partial) {
        Remove-Item -LiteralPath $partial
    }
}

Write-Host "Saved: $target"

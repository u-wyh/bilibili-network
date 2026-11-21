[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PythonRuntimeZip,
    [Parameter(Mandatory)][string]$PipWheel,
    [Parameter(Mandatory)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$output = [IO.Directory]::CreateDirectory($OutputDirectory).FullName
$payload = Join-Path $output ('payload-' + [guid]::NewGuid().ToString('N'))
& (Join-Path $PSScriptRoot 'build.ps1') -PythonRuntimeZip $PythonRuntimeZip -PipWheel $PipWheel -OutputDirectory $payload
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$archive = Join-Path $payload 'bilibili-cache-windows-x64.zip'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$setup = Join-Path $output 'Bilibili-Cache-Setup-v0.1.2-x64.exe'
$icon = Join-Path $PSScriptRoot '../../app/icon.ico'
$options = @('/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/codepage:65001',
    '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll', '/reference:Microsoft.CSharp.dll',
    '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
    "/resource:$archive,BilibiliCache.zip", "/win32icon:$icon", "/out:$setup", (Join-Path $PSScriptRoot 'Installer.cs'))
& $compiler @options
if ($LASTEXITCODE -ne 0) { throw 'Could not build the graphical installer.' }
Get-Item -LiteralPath $setup

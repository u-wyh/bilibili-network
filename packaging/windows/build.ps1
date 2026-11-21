[CmdletBinding(DefaultParameterSetName = 'Offline')]
param(
    [Parameter(Mandatory)][string]$PythonRuntimeZip,
    [Parameter(Mandatory, ParameterSetName = 'Offline')][string]$SitePackages,
    [Parameter(Mandatory, ParameterSetName = 'Bootstrap')][string]$PipWheel,
    [Parameter(Mandatory)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$output = [IO.Directory]::CreateDirectory($OutputDirectory).FullName
$zip = Join-Path $output 'bilibili-cache-windows-x64.zip'
if (Test-Path -LiteralPath $zip) { throw "Already exists: $zip" }

$stage = Join-Path $output ('windows-build-' + [guid]::NewGuid().ToString('N'))
$bundle = Join-Path $stage 'Bilibili-Download'
$runtime = Join-Path $bundle 'runtime'
$dependencies = Join-Path $runtime 'Lib/site-packages'
[IO.Directory]::CreateDirectory($runtime) | Out-Null
[IO.Directory]::CreateDirectory((Join-Path $bundle 'app')) | Out-Null
Expand-Archive -LiteralPath $PythonRuntimeZip -DestinationPath $runtime

$searchPath = Get-ChildItem -LiteralPath $runtime -Filter 'python*._pth' -File
if (@($searchPath).Count -ne 1) { throw 'Expected a Windows embeddable CPython ZIP.' }
$pythonPaths = @(($searchPath.BaseName + '.zip'), '.', 'Lib\site-packages', '..\app')

if ($PSCmdlet.ParameterSetName -eq 'Offline') {
    [IO.Directory]::CreateDirectory($dependencies) | Out-Null
    foreach ($module in 'PySide6', 'shiboken6', 'yt_dlp', 'imageio_ffmpeg') {
        Copy-Item -LiteralPath (Join-Path $SitePackages $module) -Destination $dependencies -Recurse
    }
    Get-ChildItem -LiteralPath $SitePackages -Directory |
        Where-Object Name -Match '^(pyside6(?:_addons|_essentials|_webengine|_pdf)?|shiboken6|yt_dlp|imageio_ffmpeg)-.*\.dist-info$' |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dependencies -Recurse }
} else {
    $bootstrap = Join-Path $bundle 'bootstrap'
    [IO.Directory]::CreateDirectory($bootstrap) | Out-Null
    Copy-Item -LiteralPath $PipWheel -Destination (Join-Path $bootstrap 'pip.whl')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'setup_runtime.py') -Destination (Join-Path $bundle 'app')
    $pythonPaths += '..\bootstrap\pip.whl'
}
($pythonPaths + 'import site') | Set-Content -Encoding ASCII -LiteralPath $searchPath.FullName

foreach ($file in 'main.py','platform_support.py','account_session.py','bilibili.py','cache_library.py','cache_worker.py','style.qss','requirements.txt') {
    Copy-Item -LiteralPath (Join-Path $repo "app/$file") -Destination (Join-Path $bundle 'app')
}

$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$launcher = Join-Path $bundle 'Bilibili-Download.exe'
& $compiler /nologo /target:winexe /reference:System.Windows.Forms.dll "/out:$launcher" (Join-Path $PSScriptRoot 'Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Could not build the launcher.' }

$python = Join-Path $runtime 'python.exe'
if ($PSCmdlet.ParameterSetName -eq 'Offline') {
    & $python -B -c 'import main; from PySide6.QtWebEngineWidgets import QWebEngineView; assert main.WINDOWS'
} else {
    & $python -B -m pip --version
}
if ($LASTEXITCODE -ne 0) { throw 'The bundled Python could not import the application.' }

Copy-Item -LiteralPath (Join-Path $repo 'packaging/portable-readme.txt') -Destination (Join-Path $bundle 'README.txt')
& tar.exe -a -cf $zip -C $stage 'Bilibili-Download'
if ($LASTEXITCODE -ne 0) { throw 'Could not create the portable ZIP.' }
Write-Output "BUNDLE=$bundle"
Get-Item -LiteralPath $zip

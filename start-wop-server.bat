<# : WoP Server Kit for Windows. Double-click this file. (The lines below run as PowerShell.)
@echo off
title WoP Server Kit
set "WOPKIT_BAT=%~f0"
if "%WOP_KIT_ROOT%"=="" set "WOP_KIT_ROOT=%LOCALAPPDATA%\WoPServer"
if exist "%WOP_KIT_ROOT%\wopkit.cmd" (
    call "%WOP_KIT_ROOT%\wopkit.cmd" start
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath $env:WOPKIT_BAT -Raw | Invoke-Expression"
if errorlevel 1 pause
exit /b
#>

# ---------------------------------------------------------------------------------------------
# First run: get uv (which provides Python) and the kit, then hand over to kit\setup\wopkit.py.
# ---------------------------------------------------------------------------------------------
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo     = 'OWNER/wop-server-kit'      # the GitHub repo with this kit
$Branch   = 'main'
$UvUrl    = 'https://github.com/astral-sh/uv/releases/download/0.9.2/uv-x86_64-pc-windows-msvc.zip'
$UvSha256 = 'ba61d01b7470b282e09e7c82a053472723c2a737fb3d137bd0f111e420cc1d9f'

$Root  = if ($env:WOP_KIT_ROOT) { $env:WOP_KIT_ROOT } else { Join-Path $env:LOCALAPPDATA 'WoPServer' }
$Tools = Join-Path $Root 'tools'
$Temp  = Join-Path $env:TEMP 'wop-server-kit-setup'

# Also works pasted into PowerShell:  irm https://raw.githubusercontent.com/<repo>/main/start-wop-server.bat | iex
$installed = Join-Path $Root 'wopkit.cmd'
if (Test-Path $installed) { & cmd.exe /c "`"$installed`" start"; exit $LASTEXITCODE }

Write-Host "WoP Server Kit: getting started (this window will ask you a few things)."
try {
    New-Item -ItemType Directory -Force $Tools, $Temp | Out-Null

    if (-not (Test-Path (Join-Path $Tools 'uv.exe'))) {
        Write-Host '>> Downloading the helper that runs the kit (uv, about 20 MB)...'
        $zip = Join-Path $Temp 'uv.zip'
        Invoke-WebRequest -UseBasicParsing -Uri $UvUrl -OutFile $zip
        if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $UvSha256) { throw 'The uv download is damaged. Please try again.' }
        Expand-Archive -Force $zip -DestinationPath (Join-Path $Temp 'uv')
        Copy-Item (Get-ChildItem -Recurse (Join-Path $Temp 'uv') -Filter 'uv.exe' | Select-Object -First 1).FullName $Tools
    }

    Write-Host '>> Downloading the WoP Server Kit...'
    $kitZip = Join-Path $Temp 'kit.zip'
    if ($env:WOP_KIT_URL) { Copy-Item ($env:WOP_KIT_URL -replace '^file:///?', '') $kitZip }
    else { Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $kitZip }
    $unpacked = Join-Path $Temp 'kit'
    if (Test-Path $unpacked) { Remove-Item -Recurse -Force $unpacked }
    Expand-Archive -Force $kitZip -DestinationPath $unpacked
    $kitDir = Get-ChildItem -Directory $unpacked | ForEach-Object { Join-Path $_.FullName 'kit' } | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $kitDir) { throw 'The kit download has no kit folder.' }
    $target = Join-Path $Root 'kit'
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Copy-Item -Recurse $kitDir $target

    # uv keeps Python and its downloads inside the kit folder
    $env:UV_CACHE_DIR = Join-Path $Root 'cache\uv'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $Root 'python'
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    & (Join-Path $Tools 'uv.exe') run --quiet --script (Join-Path $target 'setup\wopkit.py') start --no-update
    exit $LASTEXITCODE
}
catch {
    Write-Host ''
    Write-Host "Something went wrong: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Check your internet connection and double-click start-wop-server.bat again.'
    exit 1
}

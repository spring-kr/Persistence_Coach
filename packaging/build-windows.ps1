# Persistence Coach - Windows Pake packaging (static HTML, no server)
# Run from any PowerShell working directory: powershell -ExecutionPolicy Bypass -File .\packaging\build-windows.ps1
[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [string]$AppName = "Persistence-Coach"
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$source = Join-Path $repo "index.html"
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Required index.html is missing: $source"
}
if (-not (Get-Command pake -ErrorAction SilentlyContinue)) {
    throw "Pake CLI not found. Install it first: npm install -g pake-cli"
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $repo "dist-windows"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path

# Keep Rust artifacts on a short path to avoid the prior Windows LNK1104 case.
if (-not $env:CARGO_TARGET_DIR) {
    $env:CARGO_TARGET_DIR = "C:\pc-pake-target"
}
$stage = Join-Path $env:TEMP ("pc-pake-stage-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    Copy-Item -LiteralPath $source -Destination (Join-Path $stage "index.html")
    Write-Host "SOURCE=$source"
    Write-Host "CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR"
    Write-Host "OUTPUT_DIR=$OutputDir"
    Push-Location $OutputDir
    try {
        & pake $stage --name $AppName --width 1280 --height 850 --json
        $buildExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($buildExit -ne 0) {
        throw "PAKE_BUILD_FAILED exit=$buildExit"
    }
    $msi = @(Get-ChildItem -LiteralPath $OutputDir -Filter "*.msi" -File |
        Where-Object { $_.BaseName -like "$AppName*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1)
    if ($msi.Count -eq 0) {
        throw "Build exited successfully but no MSI was found in $OutputDir"
    }
    Write-Host "MSI_BUILD_PASS"
    Write-Host "MSI_PATH=$($msi[0].FullName)"
    Write-Host "MSI_SIZE=$($msi[0].Length)"
    Write-Host "MSI_SHA256=$((Get-FileHash -LiteralPath $msi[0].FullName -Algorithm SHA256).Hash)"
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}

# Build TuwaiqOS (PowerShell)
#
# Output: target\debug\boot-bios-tuwaiqos.img

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:RUSTUP_TOOLCHAIN = "nightly-2026-06-01"
$env:CARGO_TARGET_DIR = Join-Path $ProjectRoot "target"

Write-Host "=== TuwaiqOS build ===" -ForegroundColor Cyan
Write-Host "Toolchain: $env:RUSTUP_TOOLCHAIN"

Write-Host ""
Write-Host "[1/2] Building bare-metal kernel..." -ForegroundColor Yellow
cargo build --package kernel --target x86_64-unknown-none
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$KernelElf = Join-Path $ProjectRoot "target\x86_64-unknown-none\debug\kernel"
if (-not (Test-Path $KernelElf)) {
    $KernelElf = Join-Path $ProjectRoot "target\x86_64-unknown-none\debug\kernel.exe"
}
if (-not (Test-Path $KernelElf)) {
    Write-Host "Kernel ELF not found after step 1." -ForegroundColor Red
    exit 1
}
Write-Host "Kernel ELF: $KernelElf" -ForegroundColor Green

Write-Host ""
Write-Host "[2/2] Building BIOS disk image..." -ForegroundColor Yellow
cargo build --package tuwaiqos
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Image = Join-Path $ProjectRoot "target\debug\boot-bios-tuwaiqos.img"
if (-not (Test-Path $Image)) {
    Write-Host "Disk image not found at expected path." -ForegroundColor Red
    Get-ChildItem -Recurse (Join-Path $ProjectRoot "target") -Filter "boot-bios-tuwaiqos.img" -ErrorAction SilentlyContinue
    exit 1
}

Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
Write-Host "Disk image: $Image"
Write-Host "Size: $((Get-Item $Image).Length) bytes"

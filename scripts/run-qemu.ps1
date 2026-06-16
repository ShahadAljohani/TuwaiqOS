# Run TuwaiqOS in QEMU (PowerShell)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Candidates = @(
    (Join-Path $ProjectRoot "target\debug\boot-bios-tuwaiqos.img"),
    (Join-Path $ProjectRoot "target\release\boot-bios-tuwaiqos.img")
)

$Image = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Image) {
    Write-Host "Disk image not found. Run scripts\build.ps1 first." -ForegroundColor Red
    exit 1
}

$Qemu = Get-Command qemu-system-x86_64 -ErrorAction SilentlyContinue
if (-not $Qemu) {
    Write-Host "qemu-system-x86_64 not found in PATH." -ForegroundColor Red
    Write-Host "Install QEMU and add it to PATH, then retry."
    exit 1
}

Write-Host "Booting TuwaiqOS from: $Image" -ForegroundColor Cyan
Write-Host "Press Ctrl+Alt+G (QEMU) to release mouse. Close the window to exit." -ForegroundColor DarkGray

& qemu-system-x86_64 `
    -drive "format=raw,file=$Image" `
    -m 128M `
    -serial stdio

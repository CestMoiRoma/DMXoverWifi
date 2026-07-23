<#
Copies the firmware source (boot.py, code.py, src/, www/) from this repo
onto the board's CIRCUITPY drive. Does NOT touch lib/ (vendored
libraries) or data/ (runtime config) on the target.

The board's filesystem must be PC-writable to do this - either the
board is in config mode (double-tap reset, or serial "Set-System
unlock-write" after ejecting the drive), or nothing has booted normal
mode since it was last put in config mode.

Usage:
    powershell -ExecutionPolicy Bypass -File tools\deploy.ps1 -Target E:\
#>
param(
    [string]$Target = "E:\"
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Items = @("boot.py", "code.py", "src", "www")

if (-not (Test-Path $Target)) {
    Write-Host "Target $Target not found." -ForegroundColor Red
    exit 1
}

$testFile = Join-Path $Target ".deploy_write_test"
try {
    "test" | Out-File -FilePath $testFile -Encoding ascii -ErrorAction Stop
    Remove-Item $testFile -ErrorAction SilentlyContinue
} catch {
    Write-Host "$Target is read-only right now." -ForegroundColor Red
    Write-Host "Put the board in config mode first (double-tap reset) and retry." -ForegroundColor Red
    exit 1
}

foreach ($item in $Items) {
    $srcPath = Join-Path $RepoRoot $item
    $dstPath = Join-Path $Target $item
    if (-not (Test-Path $srcPath)) {
        Write-Host "Skipping $item (not found in repo)" -ForegroundColor Yellow
        continue
    }
    Write-Host "Syncing $item ..."
    if (Test-Path $srcPath -PathType Container) {
        # Remove the destination dir first: Copy-Item -Recurse nests the
        # source folder inside an existing destination instead of merging.
        if (Test-Path $dstPath) {
            Remove-Item -Path $dstPath -Recurse -Force
        }
        Copy-Item -Path $srcPath -Destination $dstPath -Recurse -Force
    } else {
        Copy-Item -Path $srcPath -Destination $dstPath -Force
    }
}

Write-Host "Deploy complete. Reboot the board to run the new code." -ForegroundColor Green

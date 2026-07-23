<#
Minimal interactive serial terminal for the DMX-over-WiFi board's USB CDC
console. Uses .NET SerialPort directly with DTR/RTS forced on (GUI tools
like VS Code Serial Monitor / PuTTY have been unreliable with this
device's native USB CDC port - missing DTR/RTS, flow control assumptions).

Windows only. For macOS/Linux (or any OS with Python), use
serial_console.py instead.

Usage:
    powershell -ExecutionPolicy Bypass -File serial_console.ps1 -Port COM9
#>
param(
    [string]$Port = "COM9",
    [int]$Baud = 115200
)

$serial = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$serial.DtrEnable = $true
$serial.RtsEnable = $true
$serial.ReadTimeout = 500
$serial.WriteTimeout = 2000

try {
    $serial.Open()
} catch {
    Write-Host "Could not open $Port : $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Start-Sleep -Milliseconds 300
try { $serial.ReadExisting() | Out-Null } catch {}

Write-Host "Connected to $Port at $Baud baud. Type a command and press Enter." -ForegroundColor Green
Write-Host "Type 'exit' to quit this terminal (does not reset the board)." -ForegroundColor Green
Write-Host ""

while ($true) {
    $line = Read-Host ">"
    if ($line -eq "exit") { break }
    try {
        $serial.Write($line + "`r`n")
    } catch {
        Write-Host "Write failed: $($_.Exception.Message)" -ForegroundColor Red
        continue
    }
    Start-Sleep -Milliseconds 500
    try {
        $resp = $serial.ReadExisting()
        if ($resp) { Write-Host $resp }
    } catch {
        Write-Host "Read failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}

$serial.Close()
Write-Host "Disconnected."

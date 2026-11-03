param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'serial_monitor.json'),
    [ValidateRange(0,3600)][int]$DurationSeconds = 0
)
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$port = [System.IO.Ports.SerialPort]::new(
    [string]$settings.port, [int]$settings.baud,
    [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$port.Handshake = [System.IO.Ports.Handshake]::None
$port.DtrEnable = $false
$port.RtsEnable = $false
$port.ReadTimeout = 200
$received = 0
try {
    $port.Open()
    Write-Host ('Listening: {0}, {1} baud, 8N1, no flow control.' -f $settings.port,$settings.baud)
    Write-Host 'Read only: sends no commands; DTR/RTS are disabled. Ctrl+C to close.'
    Write-Host 'An empty window is possible before the bench firmware has been flashed.'
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($DurationSeconds -eq 0 -or $timer.Elapsed.TotalSeconds -lt $DurationSeconds) {
        $text = $port.ReadExisting()
        if ($text.Length -gt 0) { Write-Host -NoNewline $text; $received += $text.Length }
        Start-Sleep -Milliseconds 100
    }
    Write-Host ("`nReceived characters: {0}" -f $received)
} catch {
    Write-Error ('Serial monitor failed: ' + $_.Exception.Message) -ErrorAction Continue
    exit 1
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}

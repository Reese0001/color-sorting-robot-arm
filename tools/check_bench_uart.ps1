param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'serial_monitor.json'),
    [ValidateRange(3,60)][int]$WaitSeconds = 10
)
# Application test only. Wait for the bench STATUS before sending PING/STATUS.
# No BSL commands, motion commands, DTR/RTS reset, or firmware programming.
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$port = [System.IO.Ports.SerialPort]::new(
    [string]$settings.port, 115200,
    [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$port.Handshake = [System.IO.Ports.Handshake]::None
$port.DtrEnable = $false
$port.RtsEnable = $false
$port.WriteTimeout = 1000
$transcript = [System.Text.StringBuilder]::new()
$safeStatus = '(?m)^STATUS ms=\d+ online=\d+ seq=\d+ target=[A-Z]+ ok=\d+ bad=\d+ drop=\d+ motion=0 armed=0 bus=0\r?$'
$passed = $false
$sent = $false
$failure = $null
try {
    $port.Open()
    Write-Host ('Waiting for bench firmware on {0}, 115200 8N1...' -f $settings.port)
    Write-Host 'After successful flashing, press RST only. Do not hold BSL.'
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $WaitSeconds) {
        $chunk = $port.ReadExisting()
        if ($chunk) { [void]$transcript.Append($chunk); Write-Host -NoNewline $chunk }
        if ($transcript.ToString() -match $safeStatus) { break }
        Start-Sleep -Milliseconds 50
    }
    if ($transcript.ToString() -notmatch $safeStatus) {
        throw 'No bench STATUS with motion=0 armed=0 bus=0. Sent nothing; check firmware, RST and COM port.'
    }
    $reply = [System.Text.StringBuilder]::new()
    $port.Write("PING`r`nSTATUS`r`n")
    $sent = $true
    $timer.Restart()
    while ($timer.Elapsed.TotalSeconds -lt 3) {
        $chunk = $port.ReadExisting()
        if ($chunk) {
            [void]$transcript.Append($chunk)
            [void]$reply.Append($chunk)
            Write-Host -NoNewline $chunk
        }
        if ($reply.ToString() -match '(?m)^PONG MSPM0G3507\r?$' -and
            $reply.ToString() -match $safeStatus) { $passed = $true; break }
        Start-Sleep -Milliseconds 50
    }
    if (-not $passed) { throw 'No complete PONG and safe STATUS reply within 3 seconds.' }
    Write-Host "`nPASS: application UART transmit/receive verified; motion and bus remain disabled."
} catch {
    $failure = $_.Exception.Message
    Write-Host ("`nFAIL: " + $failure)
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
$result = [ordered]@{
    timestamp = [DateTimeOffset]::Now.ToString('o')
    port = [string]$settings.port
    baud = 115200
    passed = $passed
    commands_sent = $(if ($sent) { @('PING','STATUS') } else { @() })
    failure = $failure
    transcript = $transcript.ToString()
}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'last_bench_uart_check.json') -Encoding utf8
if (-not $passed) { exit 1 }

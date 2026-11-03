param([string]$Port='COM8')
# Board-side dry workflow check. Sends no ARM/PWM/MOVE/READ commands.
$ErrorActionPreference='Stop'
$serial=[IO.Ports.SerialPort]::new($Port,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable=$false
$serial.RtsEnable=$false
$serial.WriteTimeout=1500
$all=[Text.StringBuilder]::new()
$results=[Collections.Generic.List[object]]::new()
$benchConfirmed=$false
$passed=$false
$failure=$null
function Receive-Until([string]$Pattern,[int]$Seconds) {
    $received=[Text.StringBuilder]::new()
    $timer=[Diagnostics.Stopwatch]::StartNew()
    while($timer.Elapsed.TotalSeconds -lt $Seconds) {
        $chunk=$serial.ReadExisting()
        if($chunk){[void]$received.Append($chunk);[void]$all.Append($chunk)}
        if($received.ToString() -match $Pattern){return $received.ToString()}
        Start-Sleep -Milliseconds 30
    }
    throw ('Timed out waiting for '+$Pattern)
}
try {
    $serial.Open()
    $null=Receive-Until '(?m)^STATUS .* motion=0 armed=0 bus=0\r?$' 8
    $serial.Write("PING`r`n")
    $null=Receive-Until '(?m)^PONG MSPM0G3507\r?$' 3
    $benchConfirmed=$true
    foreach($case in @(@{color='RED';bin='LEFT'},@{color='GREEN';bin='CENTER'},@{color='BLUE';bin='RIGHT'})) {
        $serial.DiscardInBuffer()
        $serial.Write("RESET`r`nSIM AUTO`r`nSTART $($case.color)`r`n")
        $reply=Receive-Until ("(?m)^DRY DONE state=DONE color="+$case.color+" bin="+$case.bin+" step=RETURN ticket=\d+ fault=NONE\r?\n") 12
        $steps=@([regex]::Matches($reply,'DRY STEP ([1-7])/7 ') | ForEach-Object {$_.Groups[1].Value})
        if(($steps -join ',') -ne '1,2,3,4,5,6,7' -or $reply -match 'ERR|DRY FAULT'){
            throw ('Unexpected workflow for '+$case.color)
        }
        $results.Add(@{color=$case.color;bin=$case.bin;steps=7;passed=$true})
        Write-Host ('PASS: '+$case.color+' -> '+$case.bin+', 7 simulated steps, no servo output.')
    }
    $serial.Write("RESET`r`nFLOW`r`nSTATUS`r`n")
    $final=Receive-Until '(?m)^STATUS .* motion=0 armed=0 bus=0\r?\n' 3
    if($final -notmatch '(?m)^FLOW dry=1 state=IDLE .* fault=NONE\r?$'){
        throw 'Final idle state was not confirmed'
    }
    $passed=$true
} catch {
    $failure=$_.Exception.Message
    Write-Host ('FAIL: '+$failure)
} finally {
    if($serial.IsOpen) {
        if($benchConfirmed -and -not $passed){try{$serial.Write("STOP`r`nRESET`r`n")}catch{}}
        $serial.Close()
    }
    $serial.Dispose()
}
@{timestamp=[DateTimeOffset]::Now.ToString('o');port=$Port;passed=$passed;cases=$results.ToArray();failure=$failure;transcript=$all.ToString()} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'last_bench_flow_check.json') -Encoding utf8
if(-not $passed){exit 1}

param([string]$Port='COM8', [int]$Baud=9600)
# JSON line transport for bsl_direct.py, using the same .NET serial API as bsl_probe.ps1.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$serial=[IO.Ports.SerialPort]::new($Port,$Baud,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.Handshake=[IO.Ports.Handshake]::None
$serial.DtrEnable=$false
$serial.RtsEnable=$false
$serial.ReadTimeout=200
$serial.WriteTimeout=3000
try {
    while ($null -ne ($line=[Console]::ReadLine())) {
        $stop=$false
        try {
            $request=$line | ConvertFrom-Json
            $value=$null
            switch ($request.op) {
                'open' { $serial.Open() }
                'reset' { $serial.DiscardInBuffer() }
                'write' {
                    $bytes=[Convert]::FromBase64String([string]$request.data)
                    $serial.Write($bytes,0,$bytes.Length)
                    $value=$bytes.Length
                }
                'read' {
                    if($request.count -lt 1 -or $request.count -gt 2048){throw 'Invalid read size'}
                    $bytes=[byte[]]::new([int]$request.count)
                    $count=0
                    try { $count=$serial.Read($bytes,0,$bytes.Length) } catch [TimeoutException] {}
                    $value=[Convert]::ToBase64String($bytes,0,$count)
                }
                'close' { $stop=$true }
                default { throw 'Unknown bridge operation' }
            }
            [Console]::WriteLine((@{ok=$true;value=$value} | ConvertTo-Json -Compress))
        } catch {
            [Console]::WriteLine((@{ok=$false;error=$_.Exception.Message} | ConvertTo-Json -Compress))
        }
        if($stop){break}
    }
} finally {
    if($serial.IsOpen){$serial.Close()}
    $serial.Dispose()
}

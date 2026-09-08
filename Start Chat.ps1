$ErrorActionPreference = 'Stop'
$chatUrl = 'http://127.0.0.1:48200'
$chatPython = Join-Path $env:LOCALAPPDATA 'Programs\AI Playground\resources\OpenVINO\.venv\Scripts\pythonw.exe'
try {
    $chatStatus = Invoke-RestMethod "$chatUrl/api/status" -TimeoutSec 2
    if ($chatStatus.models -isnot [array]) { throw 'Port is occupied by another application.' }
} catch {
    if (-not (Test-Path -LiteralPath $chatPython)) { throw 'AI Playground OpenVINO Python runtime was not found.' }
    $chatServer = Join-Path $PSScriptRoot 'server.py'
    $chatProcess = Start-Process -FilePath $chatPython -ArgumentList ('"' + $chatServer + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
    $chatReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { $null = Invoke-RestMethod "$chatUrl/api/status" -TimeoutSec 1; $chatReady = $true; break } catch { }
    }
    if (-not $chatReady) { throw 'Chat server did not start. Port 48200 may be in use.' }
}
Start-Process $chatUrl

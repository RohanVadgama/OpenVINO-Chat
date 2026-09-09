param([switch]$Restart)
$ErrorActionPreference = 'Stop'
$chatUrl = 'http://127.0.0.1:48200'
$chatPython = Join-Path $env:LOCALAPPDATA 'Programs\AI Playground\resources\OpenVINO\.venv\Scripts\pythonw.exe'
$chatServer = Join-Path $PSScriptRoot 'server.py'
try {
    $chatStatus = $null
    try { $chatStatus = Invoke-RestMethod "$chatUrl/api/status" -TimeoutSec 2 } catch { }
    if ($chatStatus) {
        if ($chatStatus.models -isnot [array]) { throw 'Port 48200 is occupied by another application.' }
        if ($Restart -or $chatStatus.capabilities -notcontains 'read-link') {
            # Only stop the Python process serving this exact project on the app port.
            $chatOwners = @(Get-NetTCPConnection -LocalPort 48200 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique)
            foreach ($chatOwner in $chatOwners) {
                $chatExisting = Get-CimInstance Win32_Process -Filter "ProcessId = $chatOwner"
                if ($chatExisting.Name -notmatch '^pythonw?\.exe$' -or -not $chatExisting.CommandLine -or $chatExisting.CommandLine.IndexOf($chatServer, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
                    throw 'Another server owns port 48200. Close it before launching this project.'
                }
            }
            try { $null = Invoke-RestMethod "$chatUrl/api/unload" -Method Post -Headers @{'X-Local-Token'=$chatStatus.token} -ContentType 'application/json' -Body '{}' -TimeoutSec 20 } catch { throw 'Stop the current generation or model loading, then reopen the shortcut to update the server.' }
            foreach ($chatOwner in $chatOwners) { Stop-Process -Id $chatOwner -ErrorAction Stop }
            Start-Sleep -Milliseconds 700
            $chatStatus = $null
        }
    }
    if (-not $chatStatus) {
        if (-not (Test-Path -LiteralPath $chatPython)) { throw 'AI Playground OpenVINO Python runtime was not found.' }
        $chatProcess = Start-Process -FilePath $chatPython -ArgumentList ('"' + $chatServer + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
        $chatReady = $false
        for ($attempt = 0; $attempt -lt 40; $attempt++) {
            Start-Sleep -Milliseconds 300
            try {
                $chatStatus = Invoke-RestMethod "$chatUrl/api/status" -TimeoutSec 1
                if ($chatStatus.capabilities -contains 'read-link') { $chatReady = $true; break }
            } catch { }
            if ($chatProcess.HasExited) { break }
        }
        if (-not $chatReady) { throw 'The updated chat server did not start. Another process may still own port 48200.' }
    }
    Start-Process $chatUrl
} catch {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($_.Exception.Message, 'OpenVINO Chat could not start') | Out-Null
    exit 1
}

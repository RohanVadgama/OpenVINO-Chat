$ErrorActionPreference = 'Stop'
$chatShell = New-Object -ComObject WScript.Shell
$chatLauncher = Join-Path $PSScriptRoot 'Start Chat.ps1'
$chatTargets = @((Join-Path $PSScriptRoot 'OpenVINO Chat.lnk'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\OpenVINO Chat.lnk'))
foreach ($chatTarget in $chatTargets) {
    $chatLink = $chatShell.CreateShortcut($chatTarget)
    $chatLink.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $chatLink.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $chatLauncher + '"'
    $chatLink.WorkingDirectory = $PSScriptRoot
    $chatLink.WindowStyle = 7
    $chatLink.IconLocation = (Join-Path $PSScriptRoot 'static\icon.ico') + ',0'
    $chatLink.Save()
}

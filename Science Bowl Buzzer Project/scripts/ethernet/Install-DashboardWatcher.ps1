param(
    [Parameter(Mandatory=$true)][string]$AdapterName
)
# Run as the normal laptop user AFTER the dedicated wired IP is configured.
# This script does not modify network settings or require an administrator.
$ErrorActionPreference = 'Stop'
$adapter = Get-NetAdapter -Name $AdapterName
if (-not $adapter.HardwareInterface -or $adapter.InterfaceType -ne 6) {
    throw 'Select a physical Ethernet adapter, not Wi-Fi or a VPN.'
}
$ip = Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -eq '192.168.77.1' -and $_.PrefixLength -eq 24 }
if (-not $ip) { Write-Output 'Using automatic Ethernet addressing if the Pi DHCP setup is installed.' }
$destination = Join-Path $env:LOCALAPPDATA 'ScienceBowl'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$watcher = Join-Path $destination 'Watch-ScienceBowl.ps1'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Watch-ScienceBowl.ps1') -Destination $watcher -Force
$powerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$pwshCommand = Get-Command pwsh.exe -ErrorAction SilentlyContinue
if ($pwshCommand) { $powerShell = $pwshCommand.Source }
# Apply only to the watcher process; do not change user/machine policy.
$arguments = '-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -WindowStyle Hidden -File "{0}" -AdapterGuid "{1}"' -f $watcher, $adapter.InterfaceGuid
$startup = [Environment]::GetFolderPath('Startup')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $startup 'Science Bowl Dashboard.lnk'))
$shortcut.TargetPath = $powerShell
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $destination
$shortcut.Save()
Start-Process -FilePath $powerShell -ArgumentList $arguments -WindowStyle Hidden
Write-Output 'Startup shortcut installed and launcher requested. Sign out and back in to verify sign-in launch.'

# Run once as administrator for the dedicated Realtek USB Ethernet adapter.
$ErrorActionPreference = 'Stop'
$adapter = Get-NetAdapter -Name 'Ethernet'
if ($adapter.InterfaceDescription -ne 'Realtek USB GbE Family Controller') {
    throw 'Expected Realtek USB GbE Family Controller named Ethernet. Inspect adapters first.'
}
$existing = @(Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4)
if ($existing | Where-Object { $_.IPAddress -eq '192.168.77.1' -and $_.PrefixLength -eq 24 }) {
    Write-Output 'Dedicated Ethernet address already configured.'
    exit 0
}
if ($existing | Where-Object { $_.IPAddress -notlike '169.254.*' }) {
    throw 'Adapter already has another IPv4 address; inspect before replacing settings.'
}
New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress '192.168.77.1' -PrefixLength 24 | Out-Null
Write-Output 'Laptop Ethernet configured: 192.168.77.1/24, no gateway.'

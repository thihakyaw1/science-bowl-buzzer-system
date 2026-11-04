param(
    [Parameter(Mandatory=$true)][string]$AdapterGuid
)
# Runs in the logged-in user's session. Open once per cable connection,
# only after the expected Science Bowl API responds.
$ErrorActionPreference = 'Stop'
$mutex = New-Object System.Threading.Mutex($false, 'Local\ScienceBowlDashboardWatcher')
if (-not $mutex.WaitOne(0)) { exit }
$opened = $false
$disconnectedSamples = 0
try {
    while ($true) {
        try {
            $adapter = Get-NetAdapter | Where-Object { "$($_.InterfaceGuid)" -eq $AdapterGuid }
            if (-not $adapter -or $adapter.Status -ne 'Up') {
                $disconnectedSamples++
                if ($disconnectedSamples -ge 2) { $opened = $false }
            } else {
                $disconnectedSamples = 0
                if (-not $opened) {
                    $request = [System.Net.HttpWebRequest]::Create('http://192.168.77.2:8080/api/state')
                    $request.Proxy = $null
                    $request.Timeout = 2000
                    $request.ReadWriteTimeout = 2000
                    $response = $null
                    $reader = $null
                    try {
                        $response = $request.GetResponse()
                        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
                        $state = $reader.ReadToEnd() | ConvertFrom-Json
                        if ($null -ne $state.round -and $null -ne $state.hardware -and $null -ne $state.scores) {
                            Start-Process 'http://192.168.77.2:8080/'
                            $opened = $true
                        }
                    } finally {
                        if ($reader) { $reader.Dispose() }
                        if ($response) { $response.Dispose() }
                    }
                }
            }
        } catch {
            # Pi booting or unavailable: retry without opening repeated tabs.
        }
        Start-Sleep -Seconds 5
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}

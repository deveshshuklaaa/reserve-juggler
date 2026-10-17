# Reserve Juggler: System Health Diagnostic
Write-Host "=== RESERVE JUGGLER HEALTH CHECK ===" -ForegroundColor Cyan
Write-Host "Probing local microservices..." -ForegroundColor Gray

$results = @()

function Test-Endpoint($name, $url) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $res = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        $sw.Stop()
        return [PSCustomObject]@{
            Service  = $name
            State    = "Healthy"
            Status   = "ONLINE (HTTP $($res.StatusCode))"
            Latency  = "$($sw.ElapsedMilliseconds) ms"
            Endpoint = $url
        }
    } catch {
        $sw.Stop()
        return [PSCustomObject]@{
            Service  = $name
            State    = "Down"
            Status   = "OFFLINE / UNREACHABLE"
            Latency  = "-"
            Endpoint = $url
        }
    }
}

function Test-Port($name, $port) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect("127.0.0.1", $port, $null, $null)
    $success = $iar.AsyncWaitHandle.WaitOne(1000, $false)
    $sw.Stop()
    if ($success -and $tcp.Connected) {
        $tcp.EndConnect($iar)
        $tcp.Close()
        return [PSCustomObject]@{
            Service  = $name
            State    = "Healthy"
            Status   = "ONLINE (Listening)"
            Latency  = "$($sw.ElapsedMilliseconds) ms"
            Endpoint = "127.0.0.1:$port"
        }
    } else {
        $tcp.Close()
        return [PSCustomObject]@{
            Service  = $name
            State    = "Down"
            Status   = "OFFLINE (Port Closed)"
            Latency  = "-"
            Endpoint = "127.0.0.1:$port"
        }
    }
}

$results += Test-Endpoint "Frontend Client"   "http://localhost:3000"
$results += Test-Endpoint "Backend Core API" "http://localhost:8000/health"
$results += Test-Port     "PostgreSQL DB"    5432

$results | Format-Table -AutoSize -Property Service, State, Status, Latency, Endpoint

$downCount = ($results | Where-Object { $_.State -eq "Down" }).Count
if ($downCount -eq 0) {
    Write-Host "`nAll Reserve Juggler services are online and healthy!" -ForegroundColor Green
} else {
    Write-Host "`n$downCount service(s) offline. Start them using .\scripts\run.ps1" -ForegroundColor Yellow
}

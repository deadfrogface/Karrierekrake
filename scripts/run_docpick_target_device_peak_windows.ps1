#Requires -Version 5.1
<#
.SYNOPSIS
  Process-group Peak RSS measurement for Docpick+Qwen on the REAL target laptop.

.DESCRIPTION
  Target: Intel Core i3 (11th gen), exactly 8 GB RAM, Windows.
  Agent-VM / Cursor cloud numbers are NOT ship evidence.

  Measures Working Set of process group matching Karrierekrake / llama / docling
  patterns. Writes JSON under tests/docpick_qwen35/peak_rss_gate/.

  Hard gate: process-group Peak <= 3.3 GB (3300 MB). Soft <=12 GB is obsolete.
#>

param(
  [string]$OutDir = "tests/docpick_qwen35/peak_rss_gate",
  [int]$SampleSeconds = 120,
  [double]$GateGb = 3.3
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Get-OsRam {
  $os = Get-CimInstance Win32_OperatingSystem
  [pscustomobject]@{
    total_gb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 3)
    free_gb  = [math]::Round($os.FreePhysicalMemory / 1MB, 3)
  }
}

function Get-GroupProcesses {
  Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match 'Karrierekrake|python|llama|docling' -or
    ($_.CommandLine -and ($_.CommandLine -match 'llama_cpp|llama-server|docling|cv_docpick|Karrierekrake'))
  }
}

$ram0 = Get-OsRam
$peaks = @{}
$deadline = (Get-Date).AddSeconds($SampleSeconds)
Write-Host "Sampling process-group Working Set for $SampleSeconds s (gate=$GateGb GB)..."
Write-Host "IMPORTANT: start CV import in the app during this window."

while ((Get-Date) -lt $deadline) {
  foreach ($p in Get-GroupProcesses) {
    try {
      $proc = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
      if (-not $proc) { continue }
      $wsMb = [math]::Round($proc.WorkingSet64 / 1MB, 1)
      $key = "$($p.ProcessId):$($p.Name)"
      if (-not $peaks.ContainsKey($key) -or $wsMb -gt $peaks[$key]) {
        $peaks[$key] = $wsMb
      }
    } catch {}
  }
  Start-Sleep -Milliseconds 500
}

$ram1 = Get-OsRam
$groupPeakMb = ($peaks.Values | Measure-Object -Sum).Sum
if (-not $groupPeakMb) { $groupPeakMb = 0 }
$groupPeakGb = [math]::Round($groupPeakMb / 1024.0, 3)
$passed = ($groupPeakGb -le $GateGb) -and ($ram0.total_gb -ge 7.5) -and ($ram0.total_gb -le 8.5)

$result = [ordered]@{
  schema_version = 1
  test_type = "TARGET_DEVICE_PROCESS_GROUP_PEAK"
  ship_evidence = $true
  target_hardware = "Intel Core i3 (11th gen), exactly 8 GB RAM, Windows"
  agent_vm_note = "Do NOT use Agent-VM numbers as ship evidence."
  gate_peak_rss_gb = $GateGb
  obsolete_soft_gate_gb = 12
  measured = [ordered]@{
    os_total_ram_gb = $ram0.total_gb
    free_ram_gb_before = $ram0.free_gb
    free_ram_gb_after = $ram1.free_gb
    process_group_peak_rss_mb = [math]::Round($groupPeakMb, 1)
    process_group_peak_rss_gb = $groupPeakGb
    per_process_peak_mb = $peaks
    sample_seconds = $SampleSeconds
  }
  crashes_oom_ui_freeze = "FILL_MANUALLY: none|crash|oom|ui_freeze"
  import_parse_duration_s = "FILL_MANUALLY"
  gate_passed = $passed
  verdict = $(if ($passed) { "GO_CANDIDATE_PENDING_E2E" } else { "NO-GO" })
  kill_or_ship = "#62 only ships if full app flow on real i3/8GB Win laptop stays within RAM, stable, acceptable quality/wait. Unmeasured gates stay open."
}

$outFile = Join-Path $OutDir "TARGET_DEVICE_PEAK_RSS_RESULT.json"
($result | ConvertTo-Json -Depth 6) | Set-Content -Path $outFile -Encoding UTF8
Write-Host "Wrote $outFile"
Write-Host "process_group_peak_gb=$groupPeakGb gate=$GateGb verdict=$($result.verdict) ship_evidence_host_ok=$($ram0.total_gb -ge 7.5 -and $ram0.total_gb -le 8.5)"
if (-not ($ram0.total_gb -ge 7.5 -and $ram0.total_gb -le 8.5)) {
  Write-Warning "OS RAM $($ram0.total_gb) GB is not ~8 GB — this run is NOT valid ship evidence."
  exit 3
}
if (-not $passed) { exit 2 }
exit 0

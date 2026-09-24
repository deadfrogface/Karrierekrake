#Requires -Version 5.1
<#
.SYNOPSIS
  DEPRECATED for ship — name-based Working Set sampling only.

.DESCRIPTION
  Prefer scripts/run_docpick_job_object_peak_windows.ps1 for ship evidence.
  Hard gate remains 3_300_000_000 bytes. Agent-VM ≠ ship evidence. No Phi fallback.
#>

param(
  [string]$OutDir = "tests/docpick_qwen35/peak_rss_gate",
  [int]$SampleSeconds = 120,
  [long]$GateBytes = 3300000000
)

Write-Warning "This sampler is NOT ship evidence. Use run_docpick_job_object_peak_windows.ps1"
Write-Host "Redirecting mentally: gate=$GateBytes bytes; sampleSeconds=$SampleSeconds; out=$OutDir"
Write-Host "Exiting with code 5 — use Job Object runner."
exit 5

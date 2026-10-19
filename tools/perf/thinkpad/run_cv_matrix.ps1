# Karrierekrake CV-import speed matrix (ThinkPad, Windows PowerShell 5+/7).
# PRIMARY measurement: CV import, in-process llama-cpp-python 0.3.35. No llama-server.
# Each variant = one process = 10 CVs x (1 warm-up + 3 runs). Baseline is re-measured
# in THIS session (old 0.3.36 numbers do not count). Results: $Out\<label>\session.json + extracts\.
#
#   powershell -ExecutionPolicy Bypass -File run_cv_matrix.ps1 -K $env:USERPROFILE\kk-speedtest [-Only A,C] [-Runs 3] [-Cvs ""] [-With8B]
#   powershell -ExecutionPolicy Bypass -File run_cv_matrix.ps1 -K $env:USERPROFILE\kk-speedtest -Preset short [-With8B]
#     short = A baseline, B threads 6/6, D prompt cache (RAM), E Q4_0, F product Q2_K_XL, G thinking off + max_tokens 1024;
#             with -With8B also J 8B Q4_K_M baseline + L 8B Q4_K_M prompt-lookup (all 10 CVs, same seed, byte-identity check).
#   powershell -ExecutionPolicy Bypass -File run_cv_matrix.ps1 -K $env:USERPROFILE\kk-speedtest -PeakRaw     (step P only)
param(
  [string]$K = "$env:USERPROFILE\kk-speedtest",
  [string[]]$Only = @(),
  [int]$Runs = 3,
  [string]$Cvs = "",
  [switch]$With8B,
  [ValidateSet("full", "short")][string]$Preset = "full",
  [switch]$PeakRaw          # separate step P: repo run_i3_peak_job_benchmark.py, raw peak only (NOT i3 evidence)
)
# "Continue": in Windows PowerShell 5.1, "Stop" + 2>&1 turns any stderr line of python (log warnings) into a terminating error.
$ErrorActionPreference = "Continue"
$PY    = "$K\venv-cv035\Scripts\python.exe"
$H     = "$K\cvbench\thinkpad_cv_bench.py"
# Embedded repo snapshot: written by build_cv_bundle.sh next to this script (= cvbench\kk-repo-<short>.zip).
$COMMIT = if (Test-Path "$PSScriptRoot\REPO_COMMIT.txt") { (Get-Content -Raw "$PSScriptRoot\REPO_COMMIT.txt").Trim() } `
          else { "47e8f83b08a1925579891abbc861b68a284a66a8" }   # legacy bundles without REPO_COMMIT.txt
$REPO  = "$K\repo-$($COMMIT.Substring(0, 8))"
$M     = "$K\models"
$OUT   = "$K\results-cv"
$SEED8 = "4294967295"   # = llama_cpp.LLAMA_DEFAULT_SEED (what the product uses); passed explicitly to BOTH J and L
$Q4KM  = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
$Q40   = "298fcb5fe7a77ccc79745ae24751560c5ac56874caff4bb39b1f2055bd72b8bb"
$Q2XL  = "b7d9ec51fb4d726d31e6bfd47062fb74574a974b93951da6a435b5e35185cb5a"

# ---- pre-flight: abort if any other python / llama process is running (e.g. a parallel letter run) ----
function Assert-NoOtherPythonLlama {
  $mine = @($PID)
  $others = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -match '^(python|pythonw|py|llama-server|llama-cli|llama-bench|Karrierekrake)') -and ($mine -notcontains $_.ProcessId)
  }
  if ($others) {
    Write-Host "ABORT: other python/llama processes are running (parallel letter run?):" -ForegroundColor Red
    $others | Select-Object ProcessId, Name, CommandLine | Format-Table -AutoSize -Wrap | Out-String | Write-Host
    exit 3
  }
}
Assert-NoOtherPythonLlama

# ---- power state (Kritiker): scheme GUID+name and AC recorded at session start, before/after every variant and per CV
#      (inside the harness). Any change or AC not connected -> power_state_consistent=false, remaining variants aborted,
#      SESSION_INVALID.txt written, exit 5. READ-ONLY: this script only reads the power state and never switches the power plan.
$PREF = "$OUT\power_ref.json"
$PLOG = "$OUT\power_log.jsonl"
function Stop-PowerInvalid([string]$why) {
  $msg = "SESSION DOES NOT COUNT: power plan / AC state changed or AC not connected ($why). " +
         "Remaining variants aborted. Restore the session-start state (see power_ref.json) and start a NEW session."
  Write-Host "ABORT: $msg" -ForegroundColor Red
  Set-Content -Encoding utf8 -Path "$OUT\SESSION_INVALID.txt" -Value ("$(Get-Date -Format o)  $msg")
  $script:PowerInvalid = $true
}
function Test-Power([string]$where) {
  & $PY $H power-check --ref $PREF --log $PLOG --where $where | Out-Host
  if ($LASTEXITCODE -ne 0) { Stop-PowerInvalid $where; return $false }
  return $true
}
$PowerInvalid = $false

$common = @("--repo", $REPO, "--repo-commit", $COMMIT, "--out", $OUT, "--runs", "$Runs", "--warmup", "1", "--sysinfo-end",
            "--power-ref", $PREF)
if ($Cvs) { $common += @("--cvs", $Cvs) }

# id, label, args
$variants = @(
  @("A", "4b-q4km-baseline",     @("--model", "$M\Qwen3.5-4B-Q4_K_M.gguf", "--expect-model-sha256", $Q4KM)),
  @("B", "4b-q4km-t6x6",         @("--model", "$M\Qwen3.5-4B-Q4_K_M.gguf", "--expect-model-sha256", $Q4KM, "--threads", "6", "--threads-batch", "6")),
  # C: on the box this crashes (Qwen3.5 = hybrid/recurrent: llama_decode -1 after the first rejected draft).
  #    Kept as a 1-run check on DE_01 only, so the ThinkPad confirms the same failure without burning an hour.
  @("C", "4b-q4km-spec-lookup",  @("--model", "$M\Qwen3.5-4B-Q4_K_M.gguf", "--expect-model-sha256", $Q4KM, "--spec", "prompt-lookup", "--cvs", "DE_01", "--warmup", "0", "--runs", "1")),
  @("D", "4b-q4km-prefixcache",  @("--model", "$M\Qwen3.5-4B-Q4_K_M.gguf", "--expect-model-sha256", $Q4KM, "--prefix-cache", "ram")),
  @("E", "4b-q40-baseline",      @("--model", "$M\Qwen3.5-4B-Q4_0.gguf",   "--expect-model-sha256", $Q40)),
  @("F", "4b-q2kxl-gsq-baseline",@("--model", "$M\Qwen3.5-4B-Q2_K_XL.gguf","--expect-model-sha256", $Q2XL)),
  @("G", "4b-q4km-max1024",      @("--model", "$M\Qwen3.5-4B-Q4_K_M.gguf", "--expect-model-sha256", $Q4KM, "--max-tokens", "1024")),
  @("H", "4b-q4km-thinking-on",  @("--model", "$M\Qwen3.5-4B-Q4_K_M.gguf", "--expect-model-sha256", $Q4KM, "--thinking", "on"))
)
if ($With8B) {
  $variants += ,@("I", "8b-q3km-gsq-baseline", @("--model", "$M\qwen3-8b-Q3_K_M.gguf",  "--expect-model-sha256", "81894ed9b0e0245af542019a941e0aac21f3ec8b5a2386b82486db19c0170e77"))
  $variants += ,@("J", "8b-q4km-baseline",     @("--model", "$M\Qwen3-8B-Q4_K_M.gguf",  "--expect-model-sha256", "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785", "--seed", $SEED8))
  # L: prompt-lookup speculation works mechanically on the non-hybrid Qwen3 family (box: 0.6B identical output).
  #    Kritiker rule: all 10 CVs, temperature 0 (product), SAME seed as J, and --spec-baseline J -> per CV and run the
  #    extracts AND raw LLM outputs must be byte-identical to J; any deviation is written to session.json/diff as
  #    "KV-rollback defect, not a speed gain, goes to Personaler" and summarize marks speed_gain_counted=False.
  $variants += ,@("L", "8b-q4km-spec-lookup",  @("--model", "$M\Qwen3-8B-Q4_K_M.gguf",  "--expect-model-sha256", "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785", "--seed", $SEED8, "--spec", "prompt-lookup", "--spec-baseline", "$OUT\8b-q4km-baseline"))
  $variants += ,@("K", "8b-q40-baseline",      @("--model", "$M\Qwen_Qwen3-8B-Q4_0.gguf","--expect-model-sha256", "c9bd6e5597ad3a70ef5b9a0acb995f739e545c5f16cbdf52b1c78835172b893c"))
}

# ---- step P (separate, optional): raw peak via the repo's scripts/run_i3_peak_job_benchmark.py ----
# Label: "ThinkPad, speed/peak raw data, not i3 evidence". Product n_ctx + product thread plan, 0.3.35.
# Never --attest-physical-i3, never --enforce-limit, KARRIEREKRAKE_PHYSICAL_I3_8GB removed, no PEAK_ATTESTATION writes.
if ($PeakRaw) {
  Assert-NoOtherPythonLlama
  New-Item -ItemType Directory -Force -Path "$K\results-peak-raw-not-i3-evidence" | Out-Null
  & $PY $H power-snapshot --out "$K\results-peak-raw-not-i3-evidence\power_ref.json" | Out-Host
  if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: AC not connected / power scheme unreadable" -ForegroundColor Red; exit 5 }
  & $PY "$K\cvbench\thinkpad_peak_raw.py" --repo $REPO --repo-commit $COMMIT --model "$M\Qwen3.5-4B-Q4_K_M.gguf" `
      --expect-model-sha256 $Q4KM --out "$K\results-peak-raw-not-i3-evidence" 2>&1 |
    Tee-Object -FilePath "$K\results-peak-raw-not-i3-evidence.console.log"
  & $PY $H power-check --ref "$K\results-peak-raw-not-i3-evidence\power_ref.json" --where "after step P" `
      --log "$K\results-peak-raw-not-i3-evidence\power_log.jsonl" | Out-Host
  if ($LASTEXITCODE -ne 0) {
    Set-Content -Encoding utf8 -Path "$K\results-peak-raw-not-i3-evidence\SESSION_INVALID.txt" -Value "power state changed during step P"
    Write-Host "Step P does not count: power state changed" -ForegroundColor Red; exit 5
  }
  exit 0     # step P runs alone; the speed matrix is a separate invocation
}

if ($Preset -eq "short" -and $Only.Count -eq 0) {
  $Only = @("A", "B", "D", "E", "F", "G")
  if ($With8B) { $Only += @("J", "L") }
  Write-Host "Preset short: $($Only -join ',')  (10 CVs x (1 warm-up + $Runs runs) each; no baseline-end rerun)"
}
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
Remove-Item -ErrorAction SilentlyContinue "$OUT\SESSION_INVALID.txt", $PLOG
& $PY $H power-snapshot --out $PREF | Out-Host       # session-start reference (expected: AC, scheme e.g. 381b4222-... 'Ausbalanciert')
if ($LASTEXITCODE -ne 0) {
  Write-Host "ABORT: AC not connected or power scheme unreadable at session start - plug in AC; the script does not change the power plan." -ForegroundColor Red
  exit 5
}
& $PY $H sysinfo | Out-File -Encoding utf8 "$OUT\sysinfo_start.json"
if ($Only.Count -eq 0) { $Only2 = @("A2") } else { $Only2 = $Only }
$variants += ,@("A2", "4b-q4km-baseline-end", @("--model", "$M\Qwen3.5-4B-Q4_K_M.gguf", "--expect-model-sha256", $Q4KM))   # drift / thermal check
foreach ($v in $variants) {
  if ($v[0] -eq "A2") { if (-not ($Only2 -contains "A2")) { continue } } elseif ($Only.Count -gt 0 -and -not ($Only -contains $v[0])) { continue }
  Assert-NoOtherPythonLlama
  if (-not (Test-Power "before $($v[1])")) { break }
  Write-Host "=== $($v[0]) $($v[1])"
  & $PY $H run @common --label $v[1] @($v[2]) 2>&1 | Tee-Object -FilePath "$OUT\$($v[1]).console.log"
  if ($LASTEXITCODE -eq 5) { Stop-PowerInvalid "during $($v[1]) (harness exit 5)"; break }
  if (-not (Test-Power "after $($v[1])")) { break }
}
$dirs = Get-ChildItem -Directory $OUT | Where-Object { Test-Path "$($_.FullName)\session.json" } | ForEach-Object { $_.FullName }
& $PY $H summarize @dirs --csv "$OUT\summary.csv" | Out-File -Encoding utf8 "$OUT\summary.txt"
foreach ($d in $dirs) {
  $leaf = Split-Path $d -Leaf
  if ($leaf -ne "4b-q4km-baseline") {
    # Personaler reference = 4B Q4_K_M baseline of this session (same llama-cpp-python 0.3.35, same commit)
    & $PY $H diff "$OUT\4b-q4km-baseline" $d --json-out "$d\diff_vs_4b-q4km-baseline.json" | Out-File -Encoding utf8 "$d\diff_vs_4b-q4km-baseline.txt"
  }
  if ($leaf -eq "8b-q4km-spec-lookup" -and (Test-Path "$OUT\8b-q4km-baseline")) {
    & $PY $H diff "$OUT\8b-q4km-baseline" $d --json-out "$d\diff_vs_8b-q4km-baseline.json" | Out-File -Encoding utf8 "$d\diff_vs_8b-q4km-baseline.txt"
    # re-run the byte-identity verdict (also written by the run itself via --spec-baseline)
    & $PY $H spec-check "$OUT\8b-q4km-baseline" $d | Out-File -Encoding utf8 "$d\spec_identity_vs_8b-q4km-baseline.txt"
  }
}
if ($PowerInvalid) {
  Write-Host "SESSION DOES NOT COUNT (power_state_consistent=false) - see $OUT\SESSION_INVALID.txt, summary.txt, power_log.jsonl" -ForegroundColor Red
  exit 5
}
Write-Host "Power state consistent across the session (see $PLOG)."


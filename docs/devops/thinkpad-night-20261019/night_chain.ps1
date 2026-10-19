# Karrierekrake Nachtlauf 2026-10-19 – Kette: A (4B Baseline), F, Screenshot-Schritt, 8B J (speed only)
$ErrorActionPreference = "Continue"
$K   = "C:\Users\Lenovo\kk-speedtest"
$N   = "$K\night-20261019"
$PY  = "$K\venv-cv035\Scripts\python.exe"
$H   = "$N\cvbench\thinkpad_cv_bench.py"
$REPO= "$N\repo-7d5243d0"
$C   = "7d5243d02a2e7c066bd035e6e8dbd32fa057b868"
$M   = "$K\models"
$OUT = "$N\results-cv"
$LOG = "$N\NIGHT_RUN_LOG.txt"
$PREF= "$OUT\power_ref.json"; $PLOG = "$OUT\power_log.jsonl"
function L($m){ Add-Content -Encoding utf8 $LOG "$(Get-Date -Format o) $m" }
function NoOthers { $o = Get-CimInstance Win32_Process | ? { $_.Name -match '^(python|pythonw|py|llama-server|llama-cli|llama-bench|Karrierekrake)' }
  if ($o) { L ("ABORT: andere python/llama-Prozesse: " + (($o | % { "$($_.ProcessId) $($_.Name)" }) -join ', ')); return $false }; return $true }
function PC($w){ & $PY $H power-check --ref $PREF --log $PLOG --where $w *>&1 | Out-Null; return ($LASTEXITCODE -eq 0) }
function RunV($label, $extra){
  if (-not (NoOthers)) { return $false }
  if (-not (PC "before $label")) { L "POWER INVALID before $label"; return $false }
  L "START $label"
  & $PY $H run --repo $REPO --repo-commit $C --out $OUT --runs 3 --warmup 1 --sysinfo-end --power-ref $PREF --label $label @extra *>&1 | Out-File -Encoding utf8 "$OUT\$label.console.log"
  $rc = $LASTEXITCODE; L "END $label exit=$rc"
  if ($rc -eq 5) { return $false }
  if (-not (PC "after $label")) { L "POWER INVALID after $label"; return $false }
  return $true
}
New-Item -ItemType Directory -Force $OUT | Out-Null
L "Kette gestartet, PID $PID"
& $PY $H power-snapshot --out $PREF *>&1 | Out-File -Encoding utf8 "$OUT\power_snapshot.log"
if ($LASTEXITCODE -ne 0) { L "ABORT: kein Netzteil / Energieschema unlesbar (exit $LASTEXITCODE)"; exit 5 }
& $PY $H sysinfo *>&1 | Out-File -Encoding utf8 "$OUT\sysinfo_start.json"
$ok = RunV "4b-q4km-baseline" @("--model","$M\Qwen3.5-4B-Q4_K_M.gguf","--expect-model-sha256","00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4")
if ($ok) { $ok = RunV "4b-q2kxl-gsq-baseline" @("--model","$M\Qwen3.5-4B-Q2_K_XL.gguf","--expect-model-sha256","b7d9ec51fb4d726d31e6bfd47062fb74574a974b93951da6a435b5e35185cb5a") }

# ---- Screenshot-Schritt (L) ----
$SS = "$N\screenshot-76b02b68\capture_real_font_screenshots.py"; $SSOUT = "$N\screenshots-76b02b68"
New-Item -ItemType Directory -Force $SSOUT | Out-Null
$hash = (Get-FileHash $SS -Algorithm SHA256).Hash.ToLower()
$want = "ea18f9e89bacdcf734ed674c1d0cbc8507031a35a081d13bfd1edf01222740bb"
$locked = [bool](Get-Process LogonUI -EA SilentlyContinue)
$res = [ordered]@{ step="screenshot_L"; script_commit="76b02b68"; script_sha256=$hash; expected_sha256=$want; hash_ok=($hash -eq $want); logonui_running=$locked; time=(Get-Date -Format o) }
$SRC = "$K\src"; $VPY = "$K\.venv\Scripts\python.exe"
$prereq = (Test-Path "$SRC\tests\test_model_setup_lock_reason_visible.py") -and (Test-Path "$K\.venv\Lib\site-packages\_pytest") -and (Test-Path "$K\.venv\Lib\site-packages\PySide6")
$res.prereq_ok = $prereq
if (-not $res.hash_ok) { $res.status="SKIP"; $res.reason="hash mismatch - zaehlt nicht"; }
elseif ($locked) { $res.status="SKIP"; $res.reason="Bildschirm gesperrt (LogonUI.exe laeuft), L bleibt OFFEN" }
elseif (-not $prereq) { $res.status="SKIP"; $res.reason="Voraussetzungen fehlen (tests/test_model_setup_lock_reason_visible.py @76b02b68 und/oder pytest/PySide6 im venv), L bleibt OFFEN" }
else {
  Push-Location $SRC
  & $VPY $SS --out $SSOUT *>&1 | Out-File -Encoding utf8 "$SSOUT\console.log"
  $res.exit_code = $LASTEXITCODE; Pop-Location
  $res.status = if ($res.exit_code -eq 0) { "OK" } else { "FAIL" }
}
$res | ConvertTo-Json | Out-File -Encoding utf8 "$SSOUT\screenshot_result.json"
L "Screenshot-Schritt: $($res.status) $($res.reason) sha256=$hash"

# ---- 8B J (speed only) ----
$J = "$M\Qwen3-8B-Q4_K_M.gguf"
if (-not (Test-Path $J)) { L "8B: lade 8b-Q4_K_M (fetch_models.py, prueft Groesse+SHA)"; & $PY "$N\cvbench\fetch_models.py" --dest $M --ids 8b-Q4_K_M *>&1 | Out-File -Encoding utf8 "$OUT\fetch_8b.log"; L "fetch exit=$LASTEXITCODE" }
if ($ok -and (Test-Path $J)) { $null = RunV "8b-q4km-baseline" @("--model",$J,"--expect-model-sha256","d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785","--seed","4294967295") }
elseif (-not $ok) { L "8B uebersprungen (vorheriger Abbruch)" }

$dirs = Get-ChildItem -Directory $OUT | ? { Test-Path "$($_.FullName)\session.json" } | % { $_.FullName }
& $PY $H summarize @dirs --csv "$OUT\summary.csv" *>&1 | Out-File -Encoding utf8 "$OUT\summary.txt"
foreach ($d in $dirs) { if ((Split-Path $d -Leaf) -like "4b-*" -and (Split-Path $d -Leaf) -ne "4b-q4km-baseline") {
  & $PY $H diff "$OUT\4b-q4km-baseline" $d --json-out "$d\diff_vs_4b-q4km-baseline.json" *>&1 | Out-File -Encoding utf8 "$d\diff_vs_4b-q4km-baseline.txt" } }
L "Kette fertig"

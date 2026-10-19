# Folge-Skript nach night_chain.ps1 (PID 5400): K = 8b-q3km-gsq-product (speed only), dann L (Screenshots 76b02b68)
$ErrorActionPreference = "Continue"
$K="C:\Users\Lenovo\kk-speedtest"; $N="$K\night-20261019"
$PY="$K\venv-cv035\Scripts\python.exe"; $H="$N\cvbench\thinkpad_cv_bench.py"; $HSHA="76b02dafa759c5521adee9ff9fa9ab7aedb0ae9476bc66586a1c7a462f9f0e4c"
$REPO="$N\repo-7d5243d0"; $C="7d5243d02a2e7c066bd035e6e8dbd32fa057b868"; $M="$K\models"; $OUT="$N\results-cv"; $LOG="$N\NIGHT_RUN_LOG.txt"
$PREF="$OUT\power_ref.json"; $PLOG="$OUT\power_log.jsonl"
function L($m){ Add-Content -Encoding utf8 $LOG "$(Get-Date -Format o) [followup2] $m" }
function NoOthers { $o = Get-CimInstance Win32_Process | ? { $_.Name -match '^(python|pythonw|py|llama-server|llama-cli|llama-bench|Karrierekrake|curl)' }
  if ($o) { L ("ABORT: andere Prozesse: " + (($o | % { "$($_.ProcessId) $($_.Name)" }) -join ', ')); return $false }; return $true }
function PC($w){ & $PY $H power-check --ref $PREF --log $PLOG --where $w *>&1 | Out-Null; return ($LASTEXITCODE -eq 0) }
L "Folge-Skript gestartet PID $PID, warte auf PID 5400"
while (Get-Process -Id 5400 -EA SilentlyContinue) { Start-Sleep 60 }
L "PID 5400 beendet"
# --- Modell 8B GSQ Q3_K_M ---
$F="$M\qwen3-8b-Q3_K_M.gguf"; $PART="$F.part"; $SHA="81894ed9b0e0245af542019a941e0aac21f3ec8b5a2386b82486db19c0170e77"; $SIZE=4124161376
$URL="https://huggingface.co/ISTA-DASLab/Qwen3-8B-GGUF-GSQ/resolve/5605b36840bc26d62b34a6adb518109f55c412d2/qwen3-8b-Q3_K_M.gguf"
$cp = Get-Content "$N\fetch_8b_gsq_curl.pid" -EA SilentlyContinue
if ($cp) { while (Get-Process -Id $cp -Name curl -EA SilentlyContinue) { Start-Sleep 30 } }
if (-not (Test-Path $F)) {
  for ($i=0; $i -lt 3 -and (-not (Test-Path $PART) -or (Get-Item $PART).Length -ne $SIZE); $i++) { & curl.exe -L --fail --retry 5 -C - -o $PART $URL 2>> "$N\fetch_8b_gsq_curl.log" }
  if ((Test-Path $PART) -and (Get-Item $PART).Length -eq $SIZE) {
    $h=(Get-FileHash $PART -Algorithm SHA256).Hash.ToLower()
    if ($h -eq $SHA) { Move-Item $PART $F; L "8B GSQ Q3_K_M geladen, sha256 OK $h" } else { L "8B GSQ sha256 FALSCH ($h), nicht verwendet" }
  } else { L "8B GSQ Download unvollstaendig" }
}
$hh=(Get-FileHash $H -Algorithm SHA256).Hash.ToLower()
if ($hh -ne $HSHA) { L "ABORT: Harness-Hash $hh != $HSHA" }
elseif (Test-Path $F) {
  if ((NoOthers) -and (PC "before 8b-q3km-gsq-product")) {
    L "START 8b-q3km-gsq-product"
    & $PY $H run --repo $REPO --repo-commit $C --out $OUT --runs 3 --warmup 1 --sysinfo-end --power-ref $PREF --label "8b-q3km-gsq-product" --model $F --expect-model-sha256 $SHA --seed 4294967295 *>&1 | Out-File -Encoding utf8 "$OUT\8b-q3km-gsq-product.console.log"
    L "END 8b-q3km-gsq-product exit=$LASTEXITCODE"
    if (-not (PC "after 8b-q3km-gsq-product")) { L "POWER INVALID after 8b-q3km-gsq-product" }
    $dirs = Get-ChildItem -Directory $OUT | ? { Test-Path "$($_.FullName)\session.json" } | % { $_.FullName }
    & $PY $H summarize @dirs --csv "$OUT\summary.csv" *>&1 | Out-File -Encoding utf8 "$OUT\summary.txt"
  } else { L "8b-q3km-gsq-product nicht gestartet (andere Prozesse / Power invalid)" }
}
# --- A-Speed-Ersatz: DE_01 (warmup1+run1-3 ueberlappten mit Prep/Download 20:28-20:40) ---
if ($hh -eq $HSHA -and (NoOthers) -and (PC "before 4b-q4km-baseline-speedrerun")) {
  L "START 4b-q4km-baseline-speedrerun (--cvs DE_01)"
  & $PY $H run --repo $REPO --repo-commit $C --out $OUT --runs 3 --warmup 1 --sysinfo-end --power-ref $PREF --label "4b-q4km-baseline-speedrerun" --cvs DE_01 --model "$M\Qwen3.5-4B-Q4_K_M.gguf" --expect-model-sha256 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4 *>&1 | Out-File -Encoding utf8 "$OUT\4b-q4km-baseline-speedrerun.console.log"
  L "END 4b-q4km-baseline-speedrerun exit=$LASTEXITCODE"
  if (-not (PC "after 4b-q4km-baseline-speedrerun")) { L "POWER INVALID after 4b-q4km-baseline-speedrerun" }
} else { L "4b-q4km-baseline-speedrerun nicht gestartet" }
# --- Flags (Sidecar, keine Harness-Dateien veraendert) ---
$A="$OUT\4b-q4km-baseline"; $cut=[datetime]'2026-10-19T20:41:00'; $fl=@()
foreach ($cv in (Get-ChildItem -Directory "$A\extracts")) {
  $runs = Get-ChildItem "$($cv.FullName)\*.parsed.json" | Sort-Object LastWriteTime
  $prev=[datetime]'2026-10-19T20:26:31'
  foreach ($r in $runs) { if ($prev -lt $cut) { $fl += [ordered]@{ cv=$cv.Name; run=($r.Name -replace '\.parsed\.json$',''); est_start=$prev.ToString('o'); end=$r.LastWriteTime.ToString('o'); speed_excluded=$true; quality_valid=$true; reason="parallel prep/download 20:28-20:40" } }; $prev=$r.LastWriteTime }
}
[ordered]@{ variant="4b-q4km-baseline"; window="2026-10-19T20:28/20:40+02:00"; rule="alle Runs mit Start vor 20:41"; speed_replacement="4b-q4km-baseline-speedrerun"; runs=$fl } | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 "$OUT\speed_exclusions.json"
$dirs = Get-ChildItem -Directory $OUT | ? { Test-Path "$($_.FullName)\session.json" } | % { $_.FullName }
& $PY $H summarize @dirs --csv "$OUT\summary.csv" *>&1 | Out-File -Encoding utf8 "$OUT\summary.txt"
Add-Content -Encoding utf8 "$OUT\summary.txt" ("`nSPEED-HINWEIS: 4b-q4km-baseline Runs speed_excluded=true (parallel prep/download 20:28-20:40): " + (($fl | % { "$($_.cv)/$($_.run)" }) -join ', ') + " -> Speed-Ersatz: 4b-q4km-baseline-speedrerun; Qualitaet zaehlt. Details speed_exclusions.json")
L ("Speed-Flags gesetzt: " + (($fl | % { "$($_.cv)/$($_.run)" }) -join ', '))
# --- L: Screenshots @76b02b68 (kein Benchmark laeuft mehr) ---
$SRC="$K\src-76b02b68"; $VPY="$K\venv-L\Scripts\python.exe"; $SS="$SRC\scripts\capture_real_font_screenshots.py"; $SSOUT="$N\screenshots-76b02b68-L2"
New-Item -ItemType Directory -Force $SSOUT | Out-Null
$want="ea18f9e89bacdcf734ed674c1d0cbc8507031a35a081d13bfd1edf01222740bb"
$hash = if (Test-Path $SS) { (Get-FileHash $SS -Algorithm SHA256).Hash.ToLower() } else { "missing" }
$locked=[bool](Get-Process LogonUI -EA SilentlyContinue)
$res=[ordered]@{ step="screenshot_L"; commit="76b02b688f2ae2c131f5fc28a8f0e8d5efab4a10"; script_sha256=$hash; expected_sha256=$want; hash_ok=($hash -eq $want); logonui_running=$locked; scaling_expected="150%"; expect_dpr=1.5; time=(Get-Date -Format o) }
$prereq=(Test-Path "$SRC\tests\test_model_setup_lock_reason_visible.py") -and (Test-Path "$K\venv-L\Lib\site-packages\_pytest") -and (Test-Path "$K\venv-L\Lib\site-packages\PySide6")
$res.prereq_ok=$prereq
if (-not $res.hash_ok) { $res.status="SKIP"; $res.reason="hash mismatch - zaehlt nicht" }
elseif ($locked) { $res.status="SKIP"; $res.reason="Bildschirm gesperrt (LogonUI.exe laeuft), L bleibt OFFEN" }
elseif (-not $prereq) { $res.status="SKIP"; $res.reason="Voraussetzungen fehlen (src-76b02b68/tests oder venv-L), L bleibt OFFEN" }
else {
  Push-Location $SRC
  & $VPY -c "import tests.test_model_setup_lock_reason_visible" *>&1 | Out-File -Encoding utf8 "$SSOUT\importcheck.log"
  if ($LASTEXITCODE -ne 0) {
    L "L: Importcheck fehlgeschlagen, installiere requirements-runtime (ohne llama-cpp-python) in venv-L"
    (Get-Content "$SRC\requirements-runtime.txt") | ? { $_ -notmatch 'llama-cpp-python|extra-index-url' } | Set-Content "$SSOUT\req-L.txt"
    & $VPY -m pip install --disable-pip-version-check -r "$SSOUT\req-L.txt" -c "$SRC\constraints-runtime.txt" *>&1 | Out-File -Encoding utf8 "$SSOUT\pip.log"
  }
  & $VPY $SS --out $SSOUT --expect-dpr 1.5 *>&1 | Out-File -Encoding utf8 "$SSOUT\console.log"
  $res.exit_code=$LASTEXITCODE; Pop-Location
  $res.status = if ($res.exit_code -eq 0) { "OK" } elseif ($res.exit_code -eq 3) { "FAIL_DPR (nicht 150 %)" } else { "FAIL" }
}
$res | ConvertTo-Json | Out-File -Encoding utf8 "$SSOUT\screenshot_result.json"
L "Screenshot-Schritt L: $($res.status) $($res.reason) commit 76b02b68 sha256=$hash"
L "Folge-Skript fertig"


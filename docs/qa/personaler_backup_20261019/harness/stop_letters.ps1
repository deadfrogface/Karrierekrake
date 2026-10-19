# Stop letter run after the current letter: kill driver first (child case process keeps running), wait for child to finish.
$ErrorActionPreference='Continue'
$L='%USERPROFILE%\kk_letters_2026-10-18'
$procs=Get-CimInstance Win32_Process -Filter "Name='python.exe'"
$drv=$procs | ? { $_.CommandLine -match 'kk_letters_run.py' }
$case=$procs | ? { $_.CommandLine -match 'kk_letters_case.py' }
"driver: $($drv.ProcessId)  case: $($case.ProcessId) $(($case.CommandLine -split ' ')[-2])"
foreach($d in $drv){ Stop-Process -Id $d.ProcessId -Force; "killed driver $($d.ProcessId)" }
foreach($c in $case){ "waiting for case pid $($c.ProcessId)"; Wait-Process -Id $c.ProcessId -Timeout 1500 -ErrorAction SilentlyContinue; "case done (alive=$([bool](Get-Process -Id $c.ProcessId -ErrorAction SilentlyContinue)))" }
"STOPPED_AFTER_CURRENT $(Get-Date -Format o)" | Add-Content "$L\RUN.log"
Get-Content "$L\RUN.log" | Select -Last 25
Get-ChildItem "$L\q4_k_m" -Filter cl-*.json | Select -Expand Name
Get-ChildItem "$L\q4_k_m\logs" -Filter *.raw | Select -Expand Name
Add-Type -AssemblyName System.Windows.Forms; $s=[System.Windows.Forms.SystemInformation]::PowerStatus; "Power: $($s.PowerLineStatus) $([int]($s.BatteryLifePercent*100))%"

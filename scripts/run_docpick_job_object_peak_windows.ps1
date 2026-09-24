#Requires -Version 5.1
<#
.SYNOPSIS
  Windows Job Object Peak-memory benchmark for Docpick+Qwen (SHIP evidence only).

.DESCRIPTION
  Creates a Windows Job Object, starts Karrierekrake + Docling + Qwen/llama.cpp
  (and ALL import children) INSIDE that Job Object so no child can escape, then
  reads PeakJobMemoryUsed.

  Hard gate: PeakJobMemoryUsed <= 3,300,000,000 bytes.
  Host: real Intel Core i3 (11th gen) / exactly 8 GB RAM Windows laptop ONLY.
  Agent-VM / Cursor cloud numbers are NOT ship evidence.
  Soft <=12 GB is obsolete. NO automatic Phi fallback.

.PARAMETER LlamaServerCmd
  Full command line to start llama.cpp / llama_cpp.server (required unless -AttachOnly).

.PARAMETER AppCmd
  Full command line to start Karrierekrake desktop (optional; can import via CLI).

.PARAMETER ImportCmd
  Command that runs one representative CV import inside the job (Docling+Qwen path).

.PARAMETER SampleSeconds
  How long to keep the job alive after starting children (default 180).

.PARAMETER OutDir
  Output directory for JSON result.
#>

param(
  [string]$LlamaServerCmd = "",
  [string]$AppCmd = "",
  [string]$ImportCmd = "",
  [switch]$AttachOnly,
  [int]$SampleSeconds = 180,
  [string]$OutDir = "tests/docpick_qwen35/peak_rss_gate",
  [long]$GateBytes = 3300000000
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- Job Object P/Invoke ---
$JobObjectCSharp = @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

public static class JobObjectPeak {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool SetInformationJobObject(
    IntPtr hJob, int JobObjectInfoClass, IntPtr lpJobObjectInfo, uint cbJobObjectInfoLength);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool QueryInformationJobObject(
    IntPtr hJob, int JobObjectInfoClass, IntPtr lpJobObjectInfo, uint cbJobObjectInfoLength, IntPtr lpReturnLength);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool CloseHandle(IntPtr hObject);

  // JobObjectExtendedLimitInformation = 9
  public const int JobObjectExtendedLimitInformation = 9;

  [StructLayout(LayoutKind.Sequential)]
  public struct IO_COUNTERS {
    public ulong ReadOperationCount;
    public ulong WriteOperationCount;
    public ulong OtherOperationCount;
    public ulong ReadTransferCount;
    public ulong WriteTransferCount;
    public ulong OtherTransferCount;
  }

  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
    public long PerProcessUserTimeLimit;
    public long PerJobUserTimeLimit;
    public uint LimitFlags;
    public UIntPtr MinimumWorkingSetSize;
    public UIntPtr MaximumWorkingSetSize;
    public uint ActiveProcessLimit;
    public UIntPtr Affinity;
    public uint PriorityClass;
    public uint SchedulingClass;
  }

  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
    public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
    public IO_COUNTERS IoInfo;
    public UIntPtr ProcessMemoryLimit;
    public UIntPtr JobMemoryLimit;
    public UIntPtr PeakProcessMemoryUsed;
    public UIntPtr PeakJobMemoryUsed;
  }

  // Prevent breakaway; kill children when job handle closes.
  public const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
  public const uint JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800; // must NOT set
  public const uint JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000; // must NOT set

  public static IntPtr CreateContainmentJob() {
    IntPtr hJob = CreateJobObject(IntPtr.Zero, null);
    if (hJob == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());

    var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    // Explicitly do NOT set BREAKAWAY flags — children must not escape.

    int len = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
    IntPtr ptr = Marshal.AllocHGlobal(len);
    try {
      Marshal.StructureToPtr(info, ptr, false);
      if (!SetInformationJobObject(hJob, JobObjectExtendedLimitInformation, ptr, (uint)len))
        throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
    } finally {
      Marshal.FreeHGlobal(ptr);
    }
    return hJob;
  }

  public static void Assign(IntPtr hJob, Process p) {
    if (!AssignProcessToJobObject(hJob, p.Handle))
      throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
  }

  public static ulong QueryPeakJobMemoryUsed(IntPtr hJob) {
    int len = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
    IntPtr ptr = Marshal.AllocHGlobal(len);
    try {
      if (!QueryInformationJobObject(hJob, JobObjectExtendedLimitInformation, ptr, (uint)len, IntPtr.Zero))
        throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
      var info = (JOBOBJECT_EXTENDED_LIMIT_INFORMATION)Marshal.PtrToStructure(
        ptr, typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
      return info.PeakJobMemoryUsed.ToUInt64();
    } finally {
      Marshal.FreeHGlobal(ptr);
    }
  }
}
"@

Add-Type -TypeDefinition $JobObjectCSharp -ErrorAction Stop

function Get-OsRamBytes {
  $os = Get-CimInstance Win32_OperatingSystem
  [pscustomobject]@{
    total_bytes = [long]($os.TotalVisibleMemorySize * 1024)
    free_bytes  = [long]($os.FreePhysicalMemory * 1024)
  }
}

function Start-InJob {
  param([IntPtr]$Job, [string]$CommandLine)
  if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $null }
  Write-Host "Starting in Job Object: $CommandLine"
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "cmd.exe"
  $psi.Arguments = "/c $CommandLine"
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $p = [System.Diagnostics.Process]::Start($psi)
  [JobObjectPeak]::Assign($Job, $p)
  return $p
}

$ram0 = Get-OsRamBytes
$hostOk = ($ram0.total_bytes -ge 7.5GB) -and ($ram0.total_bytes -le 8.5GB)
if (-not $hostOk) {
  Write-Warning ("OS RAM {0} bytes is not ~8 GB — NOT valid ship evidence." -f $ram0.total_bytes)
}

$hJob = [JobObjectPeak]::CreateContainmentJob()
$children = @()
$peakObserved = [ulong]0
$errorNote = $null

try {
  if ($AttachOnly) {
    Write-Host "AttachOnly: assign already-running Karrierekrake/llama/docling PIDs (best-effort)."
    Write-Host "PREFERRED: start all children via this runner so none can escape the Job Object."
    Get-CimInstance Win32_Process | Where-Object {
      $_.CommandLine -and ($_.CommandLine -match 'llama_cpp|llama-server|docling|Karrierekrake|cv_docpick')
    } | ForEach-Object {
      try {
        $proc = [System.Diagnostics.Process]::GetProcessById($_.ProcessId)
        [JobObjectPeak]::Assign($hJob, $proc)
        Write-Host "Assigned PID $($_.ProcessId)"
      } catch {
        Write-Warning "Could not assign PID $($_.ProcessId): $_ (may already be in another job)"
      }
    }
  } else {
    if (-not $LlamaServerCmd) {
      throw "LlamaServerCmd required unless -AttachOnly. Example: .venv\Scripts\python.exe -m llama_cpp.server --model MODEL.gguf --n_ctx 2048"
    }
    $children += ,(Start-InJob -Job $hJob -CommandLine $LlamaServerCmd)
    Start-Sleep -Seconds 5
    if ($AppCmd) { $children += ,(Start-InJob -Job $hJob -CommandLine $AppCmd) }
    if ($ImportCmd) { $children += ,(Start-InJob -Job $hJob -CommandLine $ImportCmd) }
  }

  Write-Host "Sampling PeakJobMemoryUsed for $SampleSeconds s (gate=$GateBytes bytes)..."
  Write-Host "Run a representative CV import now if AppCmd/ImportCmd did not already."
  $deadline = (Get-Date).AddSeconds($SampleSeconds)
  while ((Get-Date) -lt $deadline) {
    $peak = [JobObjectPeak]::QueryPeakJobMemoryUsed($hJob)
    if ($peak -gt $peakObserved) { $peakObserved = $peak }
    Start-Sleep -Milliseconds 250
  }
  $peak = [JobObjectPeak]::QueryPeakJobMemoryUsed($hJob)
  if ($peak -gt $peakObserved) { $peakObserved = $peak }
} catch {
  $errorNote = "$_"
  Write-Error $errorNote
} finally {
  # Closing the job kills children (KILL_ON_JOB_CLOSE).
  [JobObjectPeak]::CloseHandle($hJob) | Out-Null
}

$ram1 = Get-OsRamBytes
$passed = ($peakObserved -le [ulong]$GateBytes) -and $hostOk -and (-not $errorNote)

$result = [ordered]@{
  schema_version = 1
  test_type = "WINDOWS_JOB_OBJECT_PROCESS_GROUP_PEAK"
  ship_evidence = [bool]$hostOk
  measurement_method = "Job Object PeakJobMemoryUsed (App+Docling+Qwen+ALL import children; no breakaway)"
  target_hardware = "Intel Core i3 (11th gen), exactly 8 GB RAM, Windows"
  agent_vm_note = "Agent-VM numbers are NOT ship evidence."
  gate_peak_rss_bytes = $GateBytes
  obsolete_soft_gate_note = "Soft <=12 GB / <=12000 MB is NOT success."
  no_phi_fallback = $true
  measured = [ordered]@{
    os_total_ram_bytes = $ram0.total_bytes
    free_ram_bytes_before = $ram0.free_bytes
    free_ram_bytes_after = $ram1.free_bytes
    peak_job_memory_used_bytes = [long]$peakObserved
    sample_seconds = $SampleSeconds
  }
  crashes_oom_ui_freeze = "FILL_MANUALLY: none|crash|oom|ui_freeze"
  import_parse_duration_s = "FILL_MANUALLY"
  error = $errorNote
  gate_passed = $passed
  verdict = $(if ($passed) { "GO_CANDIDATE_PENDING_E2E" } else { "NO-GO" })
  kill_path = [ordered]@{
    step_if_over_after_optimization = 1
    step_1 = "Try a smaller local model under the SAME quality/RAM/runtime gates. NO automatic Phi fallback."
    step_2_exact_wording = "wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; der manuelle Profilimport bleibt möglich."
  }
}

$outFile = Join-Path $OutDir "JOB_OBJECT_PEAK_RSS_RESULT.json"
($result | ConvertTo-Json -Depth 6) | Set-Content -Path $outFile -Encoding UTF8
Write-Host "Wrote $outFile"
Write-Host ("peak_job_memory_used_bytes={0} gate={1} verdict={2}" -f $peakObserved, $GateBytes, $result.verdict)

if (-not $hostOk) { exit 3 }
if ($errorNote) { exit 4 }
if (-not $passed) { exit 2 }
exit 0

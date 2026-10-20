param([Parameter(Mandatory)][int]$ProcessId, [switch]$Maximize)
# Brings a process's main window to the front (and maximizes it) for GUI checks.
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W32 {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern void keybd_event(byte k, byte s, uint f, UIntPtr e);
}
"@
$p = Get-Process -Id $ProcessId
$h = $p.MainWindowHandle
[W32]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero); [W32]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)  # Alt tap: allows SetForegroundWindow
[W32]::ShowWindow($h, $(if ($Maximize) { 3 } else { 9 })) | Out-Null
[W32]::SetForegroundWindow($h)

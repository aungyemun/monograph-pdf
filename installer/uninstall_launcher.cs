// uninstall.exe - the standard uninstaller entry point of an installed Monograph PDF.
//
// Inno Setup always names its uninstaller unins000.exe (with unins000.dat beside it). This
// small launcher gives installed builds the conventional uninstall.exe name: it starts the
// Inno Setup uninstaller from its own folder with the same command-line options, for example
//
//     uninstall.exe                               interactive; asks whether to remove settings too
//     uninstall.exe /SILENT                       progress only, keeps settings
//     uninstall.exe /VERYSILENT /REMOVEUSERDATA   nothing shown, removes settings too
//
// waits until it has finished and returns its exit code. Windows (Settings > Apps) runs this
// file. Built by scripts\build_release.ps1 with the C# compiler included in Windows (.NET
// Framework 4, C# 5); it needs no extra runtime.
//
// A running program cannot be deleted, so while it waits the launcher parks its own file in
// %TEMP% (a rename on the same drive, which Windows allows for running programs); the
// uninstaller can then remove the whole installation folder. If the uninstall is cancelled or
// refused, uninstall.exe is rewritten from the copy the launcher read into memory at start (the
// parked file itself is never moved back, since other programs could have changed it). Afterwards the parked copy is deleted. In a per-machine
// installation (Program Files) parking needs administrator rights, so the launcher first asks
// Windows to run it as administrator - the same single prompt the uninstaller would show.

using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("Monograph PDF Uninstaller")]
[assembly: AssemblyProduct("Monograph PDF")]
[assembly: AssemblyDescription("Removes Monograph PDF from this computer")]
[assembly: AssemblyCompany("Aung Ye Mun")]
[assembly: AssemblyCopyright("\u00A9 2026\u2013Present Aung Ye Mun")]
[assembly: AssemblyVersion(MonographPdfUninstall.BuildInfo.Version)]
[assembly: AssemblyFileVersion(MonographPdfUninstall.BuildInfo.Version)]
[assembly: AssemblyInformationalVersion(MonographPdfUninstall.BuildInfo.Version)]

namespace MonographPdfUninstall
{
    internal static class Program
    {
        private const string Title = "Monograph PDF Uninstall";
        private const string ElevatedFlag = "/MONOGRAPHPDF-ELEVATED"; // internal: second, elevated instance
        private const int ErrorAccessDenied = 5;
        private const int ErrorCancelled = 1223; // the user declined the Windows administrator prompt

        [STAThread]
        private static int Main(string[] rawArgs)
        {
            bool elevatedInstance = rawArgs.Any(a => a.Equals(ElevatedFlag, StringComparison.OrdinalIgnoreCase));
            string[] args = rawArgs.Where(a => !a.Equals(ElevatedFlag, StringComparison.OrdinalIgnoreCase)).ToArray();
            bool quiet = args.Any(a => a.Equals("/SILENT", StringComparison.OrdinalIgnoreCase)
                                    || a.Equals("/VERYSILENT", StringComparison.OrdinalIgnoreCase)
                                    || a.Equals("/SUPPRESSMSGBOXES", StringComparison.OrdinalIgnoreCase));
            string self = Assembly.GetExecutingAssembly().Location;
            string folder = Path.GetDirectoryName(self);
            string uninstaller = FindInnoUninstaller(folder);
            if (uninstaller == null)
            {
                Report(quiet, "The Monograph PDF uninstaller files (unins000.exe and unins000.dat) are missing from\n"
                            + folder + "\n\nRun Monograph PDF Setup again to repair the installation, then uninstall.");
                return 2;
            }

            // Our own bytes, kept in memory: if the uninstall is cancelled, uninstall.exe is restored
            // from this copy, never from the parked file in %TEMP% (which other programs can change).
            byte[] original = null;
            try { original = File.ReadAllBytes(self); }
            catch (Exception) { }

            int parkError = 0;
            string parked = null;
            if (original != null)
                parked = Park(self, out parkError);
            if (parked == null && parkError == ErrorAccessDenied && !elevatedInstance && !IsElevated())
            {
                // Per-machine installation: continue as administrator (one Windows prompt)
                int code;
                if (TryRun(self, args.Concat(new[] { ElevatedFlag }).ToArray(), "runas", quiet, out code))
                    return code;
            }

            int exitCode;
            TryRun(uninstaller, args, null, quiet, out exitCode);
            if (parked != null)
                Unpark(parked, self, uninstaller, original);
            return exitCode;
        }

        // Starts a program, waits for it and returns its exit code. False when it could not start.
        private static bool TryRun(string file, string[] args, string verb, bool quiet, out int exitCode)
        {
            var start = new ProcessStartInfo(file, JoinArguments(args))
            {
                UseShellExecute = true, // lets Windows show the administrator prompt when needed
                WorkingDirectory = Path.GetTempPath(),
            };
            if (verb != null)
                start.Verb = verb;
            try
            {
                using (Process process = Process.Start(start))
                {
                    process.WaitForExit();
                    exitCode = process.ExitCode;
                    return true;
                }
            }
            catch (Win32Exception ex)
            {
                exitCode = ex.NativeErrorCode == ErrorCancelled ? ErrorCancelled : 3;
                if (ex.NativeErrorCode == ErrorCancelled)
                    return true; // the user said no: nothing was changed
                if (verb == null)
                    Report(quiet, "Monograph PDF could not be uninstalled:\n" + ex.Message);
                return false;
            }
        }

        private static bool IsElevated()
        {
            try
            {
                return new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator);
            }
            catch (Exception)
            {
                return false;
            }
        }

        private static string FindInnoUninstaller(string folder)
        {
            string standard = Path.Combine(folder, "unins000.exe");
            if (File.Exists(standard) && File.Exists(Path.ChangeExtension(standard, ".dat")))
                return standard;
            return Directory.GetFiles(folder, "unins???.exe")
                            .Where(f => File.Exists(Path.ChangeExtension(f, ".dat")))
                            .OrderBy(f => f, StringComparer.OrdinalIgnoreCase)
                            .FirstOrDefault();
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool MoveFileEx(string existing, string target, int flags);

        // Moves this running program out of the installation folder; null when not possible
        // (no rights, or %TEMP% on another drive - then Inno Setup reports the leftover file).
        private static string Park(string self, out int error)
        {
            error = 0;
            string parked = Path.Combine(Path.GetTempPath(), "MonographPDF-uninstall-" + Guid.NewGuid().ToString("N") + ".exe");
            if (MoveFileEx(self, parked, 0)) // 0: rename on the same drive only, never copy
                return parked;
            error = Marshal.GetLastWin32Error();
            return null;
        }

        private static void Unpark(string parked, string self, string uninstaller, byte[] original)
        {
            // unins000.exe deletes itself shortly after it exits when the uninstall completed
            for (int i = 0; i < 40 && File.Exists(uninstaller); i++)
                Thread.Sleep(250);
            if (File.Exists(uninstaller) && !File.Exists(self))
            {
                // Cancelled or refused: Monograph PDF is still installed, so put uninstall.exe back
                try { File.WriteAllBytes(self, original); }
                catch (Exception) { }
            }
            if (File.Exists(parked))
            {
                // Delete the parked copy once this process (and a waiting first instance) has ended.
                // Full paths and the system folder as working folder: the parked copy lives in
                // %TEMP%, and Windows would otherwise look for cmd.exe / ping.exe there first.
                string system = Environment.SystemDirectory;
                var cleanup = new ProcessStartInfo(Path.Combine(system, "cmd.exe"),
                    "/d /c \"\"" + Path.Combine(system, "PING.EXE") + "\" 127.0.0.1 -n 4 > nul & del /f /q \"" + parked + "\"\"")
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden,
                    WorkingDirectory = system,
                };
                try { Process.Start(cleanup); }
                catch (Exception) { }
            }
        }

        private static void Report(bool quiet, string message)
        {
            Console.Error.WriteLine(message);
            if (!quiet)
                MessageBox.Show(message, Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }

        // Rebuilds a command line that the Inno Setup uninstaller parses exactly as typed.
        private static string JoinArguments(string[] args)
        {
            var sb = new StringBuilder();
            foreach (string arg in args)
            {
                if (sb.Length > 0)
                    sb.Append(' ');
                if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
                {
                    sb.Append(arg);
                    continue;
                }
                sb.Append('"');
                int slashes = 0;
                foreach (char c in arg)
                {
                    if (c == '\\') { slashes++; continue; }
                    if (c == '"') { sb.Append('\\', slashes * 2 + 1); sb.Append('"'); slashes = 0; continue; }
                    sb.Append('\\', slashes); slashes = 0; sb.Append(c);
                }
                sb.Append('\\', slashes * 2);
                sb.Append('"');
            }
            return sb.ToString();
        }
    }
}

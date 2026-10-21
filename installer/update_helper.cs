// MonographPDFUpdater.exe — finishes an update after Monograph PDF has closed.
//
// Monograph PDF downloads and verifies the new Setup.exe against the signed update manifest, copies
// this helper into the update's staging folder, writes handoff.json there and exits. The helper:
//
//   1. accepts one argument pair, --handoff <staging>\handoff.json, and checks every path in it
//      (staging folder under %LOCALAPPDATA%\Monograph PDF\Updates\Staging, the installation folder
//      registered in Windows for Monograph PDF's AppId in the given install mode);
//   2. waits until the application (and every other Monograph PDF window from that folder) has exited;
//   3. opens Setup.exe so it can no longer be changed (read sharing only), checks its size and
//      SHA-256 again and keeps it locked while Setup runs;
//   4. runs Setup silently in upgrade mode: /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
//      /CURRENTUSER|/ALLUSERS /DIR=<existing folder> /LOG=<staging>\setup.log — Setup keeps the
//      previous shortcuts and file-type choices; an all-users installation shows Windows' normal
//      administrator prompt (the helper itself never asks for or gains administrator rights);
//   5. verifies the installed version (uninstall entry, program file version, program files present,
//      the program's own self-check);
//   6. removes the downloaded installer and the other staging files, writes a short result file and
//      starts the updated program once (not when Windows must restart first).
//
// It never deletes anything outside its staging folder, never follows links, and never runs a file
// it has not verified. Built by scripts\build_release.ps1 with the .NET Framework 4 compiler.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: System.Reflection.AssemblyTitle("Monograph PDF Updater")]
[assembly: System.Reflection.AssemblyProduct("Monograph PDF")]
[assembly: System.Reflection.AssemblyDescription("Finishes a verified Monograph PDF update")]
[assembly: System.Reflection.AssemblyCompany("Aung Ye Mun")]
[assembly: System.Reflection.AssemblyCopyright("\u00A9 2026\u2013Present Aung Ye Mun")]
[assembly: System.Reflection.AssemblyVersion(MonographPdfUpdater.BuildInfo.Version)]
[assembly: System.Reflection.AssemblyFileVersion(MonographPdfUpdater.BuildInfo.Version)]
[assembly: System.Reflection.AssemblyInformationalVersion(MonographPdfUpdater.BuildInfo.Version)]

internal static class UpdateHelper
{
    const string AppId = "{64FC0D97-5E17-405F-9461-D6C075E1B467}";
    const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + AppId + "_is1";
    const string AppExe = "MonographPDF.exe";
    const string MutexName = @"Local\MonographPDF.Updater";
    static readonly Regex VersionRe = new Regex(@"^\d{1,5}\.\d{1,5}\.\d{1,5}(-[0-9A-Za-z.-]{1,64})?$");
    static readonly Regex IdRe = new Regex(@"^[0-9A-Za-z.-]{1,40}-[0-9a-f]{12}$");
    static readonly Regex HashRe = new Regex(@"^[0-9a-f]{64}$");

    static Form window;
    static Label stage;
    static Button cancelButton;
    static volatile bool cancelRequested;
    static volatile bool finished;
    // --quiet (automated tests only): no message boxes; the outcome is still written to the result file
    static bool quiet;
    static int exitCode = 1;

    [STAThread]
    static int Main(string[] args)
    {
        // Build check (scripts\build_release.ps1): starts, needs nothing, changes nothing
        if (args.Length == 1 && args[0] == "--self-check") return 0;
        bool created;
        using (var mutex = new Mutex(true, MutexName, out created))
        {
            if (!created)
            {
                if (args.Length == 3 && args[2] == "--quiet") return 3;
                MessageBox.Show("Another Monograph PDF update is already running.", "Monograph PDF Update",
                                MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 3;
            }
            quiet = args.Length == 3 && args[2] == "--quiet";
            if ((args.Length != 2 && !quiet) || args[0] != "--handoff")
            {
                MessageBox.Show("This program is started by Monograph PDF to finish an update.",
                                "Monograph PDF Update", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 2;
            }
            Application.EnableVisualStyles();
            BuildWindow();
            var worker = new Thread(() => Run(args[1])) { IsBackground = true };
            window.Shown += (s, e) => worker.Start();
            Application.Run(window);
            return exitCode;
        }
    }

    static void BuildWindow()
    {
        window = new Form
        {
            Text = "Monograph PDF Update",
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false,
            MinimizeBox = true,
            StartPosition = FormStartPosition.CenterScreen,
            ClientSize = new Size(440, 130),
            ShowInTaskbar = true,
        };
        try { window.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        stage = new Label { Left = 18, Top = 18, Width = 404, Height = 44, Text = "Preparing…" };
        var bar = new ProgressBar { Left = 18, Top = 66, Width = 404, Height = 14, Style = ProgressBarStyle.Marquee };
        cancelButton = new Button { Text = "Cancel", Left = 342, Top = 92, Width = 80 };
        cancelButton.Click += (s, e) => { cancelRequested = true; cancelButton.Enabled = false; };
        window.Controls.Add(stage);
        window.Controls.Add(bar);
        window.Controls.Add(cancelButton);
        // The window closes only when the work is done; closing it earlier asks to cancel (honoured
        // only before Setup starts)
        window.FormClosing += (s, e) =>
        {
            if (finished) return;
            e.Cancel = true;
            if (cancelButton.Enabled) { cancelRequested = true; cancelButton.Enabled = false; }
        };
    }

    static void Stage(string text, bool cancellable)
    {
        window.BeginInvoke((Action)(() => { stage.Text = text; cancelButton.Enabled = cancellable; }));
    }

    static void Finish(string message, MessageBoxIcon icon)
    {
        window.Invoke((Action)(() =>
        {
            if (message != null && !quiet)
                MessageBox.Show(window, message, "Monograph PDF Update", MessageBoxButtons.OK, icon);
            finished = true;
            window.Close();
        }));
    }

    // ------------------------------------------------------------------ hand-off

    sealed class Handoff
    {
        public string UpdateId, InstallDir, AppExePath, Mode, PreviousVersion, ExpectedVersion;
        public string Installer, Sha256, StagingDir, ResultPath, SetupLog;
        public long Size;
        public int AppPid;
        public bool Relaunch;
    }

    static string Full(string p) { return Path.GetFullPath(p).TrimEnd('\\'); }
    static bool Same(string a, string b) { return string.Equals(Full(a), Full(b), StringComparison.OrdinalIgnoreCase); }

    static bool IsLink(string path)
    {
        try { return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0; } catch { return false; }
    }

    static string Str(Dictionary<string, object> d, string k)
    {
        object v;
        if (!d.TryGetValue(k, out v) || !(v is string)) throw new InvalidDataException("handoff: " + k);
        var s = (string)v;
        if (s.IndexOf('"') >= 0 || s.IndexOf('\0') >= 0) throw new InvalidDataException("handoff: " + k);
        return s;
    }

    static string UpdatesRoot()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Monograph PDF", "Updates");
    }

    static Handoff Load(string handoffPath)
    {
        string root = Full(UpdatesRoot());
        string stagingRoot = Path.Combine(root, "Staging");
        handoffPath = Full(handoffPath);
        var d = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(handoffPath, Encoding.UTF8));
        object schema;
        if (!d.TryGetValue("schema", out schema) || Convert.ToInt32(schema) != 1) throw new InvalidDataException("handoff schema");
        var h = new Handoff
        {
            UpdateId = Str(d, "update_id"), InstallDir = Full(Str(d, "install_dir")), AppExePath = Full(Str(d, "app_exe")),
            Mode = Str(d, "install_mode"), PreviousVersion = Str(d, "previous_version"),
            ExpectedVersion = Str(d, "expected_version"), Installer = Full(Str(d, "installer")),
            Sha256 = Str(d, "installer_sha256"), StagingDir = Full(Str(d, "staging_dir")),
            ResultPath = Full(Str(d, "result")), SetupLog = Full(Str(d, "setup_log")),
            Size = Convert.ToInt64(d["installer_size"]), AppPid = Convert.ToInt32(d["app_pid"]),
            Relaunch = d.ContainsKey("relaunch") && d["relaunch"] is bool && (bool)d["relaunch"],
        };
        if (!IdRe.IsMatch(h.UpdateId) || !VersionRe.IsMatch(h.ExpectedVersion) || !HashRe.IsMatch(h.Sha256))
            throw new InvalidDataException("handoff values");
        if (h.Mode != "user" && h.Mode != "machine") throw new InvalidDataException("install mode");
        // Everything the helper writes or runs lives in its own staging folder
        if (!Same(Path.GetDirectoryName(h.StagingDir), stagingRoot) || Path.GetFileName(h.StagingDir) != h.UpdateId)
            throw new InvalidDataException("staging folder");
        if (IsLink(root) || IsLink(stagingRoot) || IsLink(h.StagingDir)) throw new InvalidDataException("staging folder is a link");
        if (!Same(Path.GetDirectoryName(handoffPath), h.StagingDir)) throw new InvalidDataException("handoff location");
        if (!Same(Path.GetDirectoryName(h.Installer), h.StagingDir) ||
            Path.GetFileName(h.Installer) != "MonographPDF_" + h.ExpectedVersion + "_Setup.exe")
            throw new InvalidDataException("installer location");
        if (!Same(Path.GetDirectoryName(h.SetupLog), h.StagingDir)) throw new InvalidDataException("log location");
        if (!Same(Path.GetDirectoryName(h.ResultPath), root) || Path.GetFileName(h.ResultPath) != "result-" + h.UpdateId + ".json")
            throw new InvalidDataException("result location");
        // The target is the installation Windows has registered for this mode — never another folder
        if (!Same(h.AppExePath, Path.Combine(h.InstallDir, AppExe)) || !File.Exists(Path.Combine(h.InstallDir, "unins000.exe")))
            throw new InvalidDataException("installation folder");
        if (!RegisteredLocations(h.Mode).Exists(loc => Same(loc, h.InstallDir)))
            throw new InvalidDataException("the installation folder is not registered for this install mode");
        return h;
    }

    static List<string> RegisteredLocations(string mode)
    {
        var found = new List<string>();
        var views = mode == "user"
            ? new[] { RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Default) }
            : new[] { RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64),
                      RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry32) };
        foreach (var hive in views)
        {
            using (hive)
            using (var key = hive.OpenSubKey(UninstallKey))
            {
                if (key == null) continue;
                var loc = key.GetValue("InstallLocation") as string;
                if (!string.IsNullOrEmpty(loc)) found.Add(loc);
            }
        }
        return found;
    }

    static string RegisteredVersion(string mode, string installDir)
    {
        var views = mode == "user"
            ? new[] { RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Default) }
            : new[] { RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64),
                      RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry32) };
        foreach (var hive in views)
        {
            using (hive)
            using (var key = hive.OpenSubKey(UninstallKey))
            {
                if (key == null) continue;
                var loc = key.GetValue("InstallLocation") as string;
                if (!string.IsNullOrEmpty(loc) && Same(loc, installDir)) return key.GetValue("DisplayVersion") as string ?? "";
            }
        }
        return "";
    }

    // ------------------------------------------------------------------ steps

    static List<Process> RunningCopies(string installDir)
    {
        var list = new List<Process>();
        foreach (var p in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(AppExe)))
        {
            string path = null;
            try { path = p.MainModule.FileName; } catch { }
            // a copy whose path cannot be read (another user) counts as running, to be safe
            if (path == null || Same(Path.GetDirectoryName(path), installDir)) list.Add(p); else p.Dispose();
        }
        return list;
    }

    static bool WaitForAppExit(Handoff h)
    {
        Stage("Waiting for Monograph PDF to close…", true);
        try { using (var p = Process.GetProcessById(h.AppPid)) p.WaitForExit(60000); } catch (ArgumentException) { }
        var deadline = DateTime.UtcNow.AddMinutes(10);
        while (DateTime.UtcNow < deadline)
        {
            var running = RunningCopies(h.InstallDir);
            int n = running.Count;
            foreach (var p in running) p.Dispose();
            if (n == 0) return true;
            if (cancelRequested) return false;
            Stage("Close every Monograph PDF window to continue the update (" + n + " still open)…", true);
            Thread.Sleep(1000);
        }
        return false;
    }

    static string Quote(string arg)
    {
        // Paths cannot contain quotes; Setup parses quoted tokens without backslash escapes
        return arg.IndexOf(' ') >= 0 || arg.IndexOf('\t') >= 0 ? "\"" + arg + "\"" : arg;
    }

    static string Hex(byte[] b)
    {
        var sb = new StringBuilder(b.Length * 2);
        foreach (var x in b) sb.Append(x.ToString("x2"));
        return sb.ToString();
    }

    static string FileVersion(string exe)
    {
        try
        {
            var v = FileVersionInfo.GetVersionInfo(exe);
            return (v.ProductVersion ?? "").Trim();
        }
        catch { return ""; }
    }

    static bool RebootRequested(string log)
    {
        try
        {
            foreach (var line in File.ReadAllLines(log))
                if (line.Contains("Need to restart Windows? Yes")) return true;
        }
        catch { }
        return false;
    }

    static bool SelfCheck(string exe, string updateId)
    {
        string tmp = Path.Combine(Path.GetTempPath(), "MonographPDF-update-check-" + updateId);
        try
        {
            Directory.CreateDirectory(tmp);
            var psi = new ProcessStartInfo(exe, "--smoke-test --runtime-dir " + Quote(Path.Combine(tmp, "runtime")) +
                                                " --report " + Quote(Path.Combine(tmp, "report.json")))
            { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(exe) };
            using (var p = Process.Start(psi))
            {
                if (!p.WaitForExit(180000)) { try { p.Kill(); } catch { } return false; }
                return p.ExitCode == 0;
            }
        }
        catch { return false; }
        finally
        {
            try { if (!IsLink(tmp)) Directory.Delete(tmp, true); } catch { }
        }
    }

    static void WriteMarker(Handoff h, string state)
    {
        try
        {
            var m = new Dictionary<string, object> {
                { "owner", "monograph-pdf-updater" }, { "id", h.UpdateId }, { "version", h.ExpectedVersion },
                { "state", state }, { "updated", (long)(DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds },
                { "helper_pid", Process.GetCurrentProcess().Id } };
            File.WriteAllText(Path.Combine(h.StagingDir, ".monograph-update"), new JavaScriptSerializer().Serialize(m), new UTF8Encoding(false));
        }
        catch { }
    }

    static void WriteResult(Handoff h, string status, string code, string installed, bool reboot, bool relaunched)
    {
        var r = new Dictionary<string, object> {
            { "schema", 1 }, { "update_id", h.UpdateId }, { "status", status }, { "code", code },
            { "previous_version", h.PreviousVersion }, { "expected_version", h.ExpectedVersion },
            { "installed_version", installed }, { "install_mode", h.Mode }, { "reboot_required", reboot },
            { "relaunched", relaunched }, { "time", DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'") } };
        try { File.WriteAllText(h.ResultPath, new JavaScriptSerializer().Serialize(r), new UTF8Encoding(false)); } catch { }
    }

    static void RemoveStagingFiles(Handoff h, bool keepInstaller, bool keepLog)
    {
        // Only the files this update created, only inside its own staging folder; the helper's own
        // copy and the marker stay until Monograph PDF's next start removes them (it is running now)
        var names = new List<string> { "handoff.json", Path.GetFileName(h.Installer) + ".part" };
        if (!keepInstaller) names.Add(Path.GetFileName(h.Installer));
        if (!keepLog) names.Add("setup.log");
        foreach (var n in names)
        {
            var f = Path.Combine(h.StagingDir, n);
            try { if (File.Exists(f) && !IsLink(f)) File.Delete(f); } catch { }
        }
    }

    static void Relaunch(Handoff h)
    {
        var psi = new ProcessStartInfo(h.AppExePath, "--update-finished " + h.UpdateId)
        { UseShellExecute = true, WorkingDirectory = h.InstallDir };
        Process.Start(psi).Dispose();
    }

    static void Run(string handoffPath)
    {
        try { RunSteps(handoffPath); }
        catch (Exception e)
        {
            exitCode = 6;
            Finish("The update stopped unexpectedly (" + e.GetType().Name + ").", MessageBoxIcon.Error);
        }
    }

    static void RunSteps(string handoffPath)
    {
        Handoff h;
        try { h = Load(handoffPath); }
        catch (Exception e)
        {
            Finish("The update could not be started: the update information was not valid (" + e.Message +
                   "). Nothing was changed.", MessageBoxIcon.Error);
            exitCode = 2;
            return;
        }
        WriteMarker(h, "handed_off");
        if (!WaitForAppExit(h))
        {
            WriteMarker(h, "cancelled");
            RemoveStagingFiles(h, false, false);
            WriteResult(h, "cancelled", cancelRequested ? "cancelled" : "app_still_running", h.PreviousVersion, false, false);
            Finish(cancelRequested ? "The update was cancelled. Nothing was changed."
                                   : "Monograph PDF did not close, so the update was not installed. Nothing was changed.",
                   MessageBoxIcon.Information);
            exitCode = 4;
            return;
        }

        Stage("Verifying the downloaded installer…", false);
        FileStream locked = null;
        int setupExit = -1;
        string failure = null;
        try
        {
            if (IsLink(h.Installer)) throw new InvalidDataException("installer is a link");
            // Read sharing only: nobody can change, rename or delete Setup.exe while it is checked and runs
            locked = new FileStream(h.Installer, FileMode.Open, FileAccess.Read, FileShare.Read);
            string digest;
            using (var sha = SHA256.Create()) digest = Hex(sha.ComputeHash(locked));
            if (locked.Length != h.Size || digest != h.Sha256)
                throw new InvalidDataException("the installer does not match the verified download");

            Stage("Installing Monograph PDF " + h.ExpectedVersion + "…" +
                  (h.Mode == "machine" ? "\nWindows may ask for administrator approval." : ""), false);
            var args = new List<string> { "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                                          h.Mode == "user" ? "/CURRENTUSER" : "/ALLUSERS",
                                          "/DIR=" + h.InstallDir, "/LOG=" + h.SetupLog };
            var psi = new ProcessStartInfo(h.Installer, string.Join(" ", args.ConvertAll(Quote)))
            { UseShellExecute = true, WorkingDirectory = h.StagingDir };
            using (var setup = Process.Start(psi))
            {
                setup.WaitForExit();
                setupExit = setup.ExitCode;
            }
        }
        catch (Exception e)
        {
            var w = e as System.ComponentModel.Win32Exception;
            failure = w != null && w.NativeErrorCode == 1223 ? "elevation_cancelled"
                    : e is InvalidDataException ? "verify" : "setup_start";
        }
        finally
        {
            if (locked != null) locked.Dispose();
        }

        Stage("Checking the installation…", false);
        string installed = RegisteredVersion(h.Mode, h.InstallDir);
        string exeVersion = File.Exists(h.AppExePath) ? FileVersion(h.AppExePath) : "";
        bool filesPresent = File.Exists(h.AppExePath) && Directory.Exists(Path.Combine(h.InstallDir, "_internal"));
        bool reboot = RebootRequested(h.SetupLog);
        if (failure == null && setupExit != 0) failure = "setup_exit_" + setupExit;
        if (failure == null && (installed != h.ExpectedVersion || exeVersion != h.ExpectedVersion || !filesPresent))
            failure = "version_mismatch";
        if (failure == null && !reboot && !SelfCheck(h.AppExePath, h.UpdateId)) failure = "self_check";

        if (failure == null)
        {
            WriteMarker(h, "installed");
            RemoveStagingFiles(h, false, false);
            bool relaunched = false;
            if (h.Relaunch && !reboot)
            {
                Stage("Restarting Monograph PDF…", false);
                try { Relaunch(h); relaunched = true; } catch { }
            }
            WriteResult(h, reboot ? "installed_restart_required" : "installed", reboot ? "reboot_required" : "ok",
                        installed, reboot, relaunched);
            exitCode = 0;
            if (reboot)
                Finish("Monograph PDF " + h.ExpectedVersion + " was installed. Restart Windows to finish the update.",
                       MessageBoxIcon.Information);
            else if (!relaunched)
                Finish("Monograph PDF " + h.ExpectedVersion + " was installed, but it could not be started automatically. " +
                       "Start it from the Start menu.", MessageBoxIcon.Information);
            else
                Finish(null, MessageBoxIcon.None);
            return;
        }

        // Failed: keep the verified installer (bounded retention; Monograph PDF removes it later) and
        // Setup's log for a retry, remove the rest. The previous version may still be intact.
        WriteMarker(h, "failed");
        bool previousIntact = filesPresent && exeVersion == h.PreviousVersion && installed == h.PreviousVersion;
        RemoveStagingFiles(h, true, true);
        bool relaunchedOld = false;
        if (previousIntact && h.Relaunch)
        {
            try { Relaunch(h); relaunchedOld = true; } catch { }
        }
        WriteResult(h, "failed", failure, installed, reboot, relaunchedOld);
        exitCode = 5;
        string why = failure == "elevation_cancelled" ? "administrator approval was not given"
                   : failure == "verify" ? "the installer did not match the verified download"
                   : failure == "self_check" ? "the updated program did not pass its self-check"
                   : failure == "version_mismatch" ? "the expected version was not found after Setup finished"
                   : "Setup reported an error (" + failure + ")";
        Finish("Monograph PDF " + h.ExpectedVersion + " was not installed: " + why + ".\n\n" +
               (previousIntact ? "Monograph PDF " + h.PreviousVersion + " is still installed."
                               : "If Monograph PDF does not start, run Setup again from the official release page.") +
               "\nSetup's log is kept at:\n" + h.SetupLog, MessageBoxIcon.Warning);
    }
}

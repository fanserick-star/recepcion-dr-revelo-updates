using System.Diagnostics;

namespace DrRevelo.LauncherUpdater;

internal static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            string? installer = Get(args, "--installer");
            string? launcher = Get(args, "--launcher");
            string? root = Get(args, "--root");
            string? log = Get(args, "--log");
            int parent = int.TryParse(Get(args, "--parent"), out var p) ? p : 0;

            if (string.IsNullOrWhiteSpace(installer) || !File.Exists(installer) ||
                string.IsNullOrWhiteSpace(launcher) || string.IsNullOrWhiteSpace(root))
                return 2;

            WriteLog(log, $"Helper iniciado. parent={parent}; installer={installer}");

            if (parent > 0)
            {
                try
                {
                    using var proc = Process.GetProcessById(parent);
                    proc.WaitForExit(60000);
                }
                catch { Thread.Sleep(1200); }
            }
            else Thread.Sleep(1200);

            var psi = new ProcessStartInfo(installer,
                "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES /SP-")
            {
                UseShellExecute = true,
                WorkingDirectory = Path.GetDirectoryName(installer) ?? root,
                WindowStyle = ProcessWindowStyle.Hidden
            };
            using var setup = Process.Start(psi);
            if (setup is null)
            {
                WriteLog(log, "No se pudo iniciar el instalador.");
                return 3;
            }

            WriteLog(log, $"Instalador iniciado PID={setup.Id}.");
            setup.WaitForExit();
            WriteLog(log, $"Instalador terminó ExitCode={setup.ExitCode}.");
            if (setup.ExitCode != 0) return setup.ExitCode;

            Thread.Sleep(900);

            if (!File.Exists(launcher))
            {
                WriteLog(log, "El instalador terminó pero RecepcionLauncher.exe no existe.");
                return 4;
            }

            var reopened = Process.Start(new ProcessStartInfo(launcher)
            {
                UseShellExecute = true,
                WorkingDirectory = root,
                WindowStyle = ProcessWindowStyle.Normal
            });
            WriteLog(log, reopened is null
                ? "No se pudo reabrir el launcher."
                : $"Launcher reabierto PID={reopened.Id}.");
            return reopened is null ? 5 : 0;
        }
        catch (Exception ex)
        {
            try { WriteLog(Get(args, "--log"), "ERROR helper: " + ex); } catch { }
            return 1;
        }
    }

    static void WriteLog(string? path, string message)
    {
        if (string.IsNullOrWhiteSpace(path)) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path) ?? ".");
            File.AppendAllText(path,
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}\r\n");
        }
        catch { }
    }

    static string? Get(string[] args, string key)
    {
        for (int i = 0; i + 1 < args.Length; i++)
            if (args[i].Equals(key, StringComparison.OrdinalIgnoreCase))
                return args[i + 1];
        return null;
    }
}

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
            int parent = int.TryParse(Get(args, "--parent"), out var p) ? p : 0;

            if (string.IsNullOrWhiteSpace(installer) || !File.Exists(installer) ||
                string.IsNullOrWhiteSpace(launcher) || string.IsNullOrWhiteSpace(root))
                return 2;

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
            if (setup is null) return 3;
            setup.WaitForExit();
            if (setup.ExitCode != 0) return setup.ExitCode;

            Thread.Sleep(600);
            Process.Start(new ProcessStartInfo(launcher)
            {
                UseShellExecute = true,
                WorkingDirectory = root,
                WindowStyle = ProcessWindowStyle.Normal
            });
            return 0;
        }
        catch { return 1; }
    }

    static string? Get(string[] args, string key)
    {
        for (int i = 0; i + 1 < args.Length; i++)
            if (args[i].Equals(key, StringComparison.OrdinalIgnoreCase))
                return args[i + 1];
        return null;
    }
}

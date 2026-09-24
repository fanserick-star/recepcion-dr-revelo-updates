using System.Diagnostics;
using Microsoft.Win32;

namespace DrRevelo.HistoriaUninstaller;

internal static class Program
{
    const string CanonicalRoot = @"C:\Historia Clinica Dr Revelo";
    const int Port = 8787;

    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        if (args.Any(a => a.Equals("--cleanup", StringComparison.OrdinalIgnoreCase)))
        {
            RunCleanup();
            return;
        }
        Application.Run(new ConfirmForm());
    }

    static void RunCleanup()
    {
        if (!CanonicalRoot.Equals(@"C:\Historia Clinica Dr Revelo", StringComparison.OrdinalIgnoreCase))
        {
            MessageBox.Show("La ruta protegida no coincide. Se canceló la desinstalación.",
                "Desinstalación cancelada", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        try
        {
            StopHistoriaProcesses();
            DeleteShortcuts();
            DeleteKnownAppData();
            DeleteKnownTemp();
            DeleteRegistryKeys();

            for (int i = 0; i < 6 && Directory.Exists(CanonicalRoot); i++)
            {
                TryDeleteDirectory(CanonicalRoot);
                if (Directory.Exists(CanonicalRoot)) Thread.Sleep(700);
            }

            MessageBox.Show(
                Directory.Exists(CanonicalRoot)
                    ? "La desinstalación terminó, pero Windows mantiene algún archivo bloqueado. Reinicia la PC y vuelve a ejecutar el desinstalador."
                    : "Historia Clínica Dr. Armando Revelo fue eliminada completamente de esta PC.",
                "Desinstalación de Historia Clínica",
                MessageBoxButtons.OK,
                Directory.Exists(CanonicalRoot) ? MessageBoxIcon.Warning : MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            MessageBox.Show("No se pudo completar la limpieza:\n\n" + ex.Message,
                "Desinstalación de Historia Clínica", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { ScheduleSelfDelete(); }
    }

    static void StopHistoriaProcesses()
    {
        foreach (var name in new[] { "HistoriaClinicaLauncher", "HistoriaClinica_Dr_Revelo" })
        {
            try
            {
                foreach (var p in Process.GetProcessesByName(name))
                {
                    try
                    {
                        if (p.Id != Environment.ProcessId)
                        {
                            p.Kill(true);
                            p.WaitForExit(3000);
                        }
                    }
                    catch { }
                    finally { p.Dispose(); }
                }
            }
            catch { }
        }

        try
        {
            if (!HistoriaResponds()) return;
            var psi = new ProcessStartInfo("netstat", "-ano -p tcp")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true
            };
            using var p = Process.Start(psi);
            if (p is null) return;
            var text = p.StandardOutput.ReadToEnd();
            p.WaitForExit(3000);

            foreach (var line in text.Split('\n'))
            {
                if (!line.Contains($":{Port}") ||
                    !line.Contains("LISTENING", StringComparison.OrdinalIgnoreCase))
                    continue;
                var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length < 5 || !int.TryParse(parts[^1], out int pid)) continue;
                try
                {
                    using var target = Process.GetProcessById(pid);
                    target.Kill(true);
                    target.WaitForExit(3000);
                }
                catch { }
                break;
            }
        }
        catch { }
    }

    static bool HistoriaResponds()
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromMilliseconds(700) };
            var s = client.GetStringAsync($"http://127.0.0.1:{Port}/api/version")
                .GetAwaiter().GetResult();
            return s.Contains("historia-clinica-dr-revelo", StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    }

    static void DeleteShortcuts()
    {
        var dirs = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory),
            Environment.GetFolderPath(Environment.SpecialFolder.Programs),
            Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms)
        };
        var names = new[]
        {
            "Historia Clínica - Dr. Armando Revelo.lnk",
            "Historia Clinica - Dr. Armando Revelo.lnk",
            "Historia Clínica Dr. Armando Revelo.lnk"
        };
        foreach (var dir in dirs.Where(Directory.Exists))
            foreach (var name in names)
                TryDeleteFile(Path.Combine(dir, name));
    }

    static void DeleteKnownAppData()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var roaming = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        var paths = new[]
        {
            Path.Combine(local, "DrArmandoRevelo", "HistoriaClinica"),
            Path.Combine(roaming, "DrArmandoRevelo", "HistoriaClinica"),
            Path.Combine(local, "Historia Clinica Dr Revelo"),
            Path.Combine(roaming, "Historia Clinica Dr Revelo"),
            Path.Combine(local, "Historia Clínica Dr Revelo"),
            Path.Combine(roaming, "Historia Clínica Dr Revelo")
        };
        foreach (var p in paths) TryDeleteDirectory(p);
    }

    static void DeleteKnownTemp()
    {
        var temp = Path.GetTempPath();
        foreach (var pattern in new[]
        {
            "DrReveloHistoriaLauncher*",
            "historia_update_*",
            "historia_repair_*",
            "hc_launcher_*",
            "DrRevelo_Historia_*"
        })
        {
            try
            {
                foreach (var f in Directory.GetFiles(temp, pattern)) TryDeleteFile(f);
                foreach (var d in Directory.GetDirectories(temp, pattern))
                    if (!Path.GetFullPath(d).Equals(
                        Path.GetDirectoryName(Environment.ProcessPath) ?? "",
                        StringComparison.OrdinalIgnoreCase))
                        TryDeleteDirectory(d);
            }
            catch { }
        }
    }

    static void DeleteRegistryKeys()
    {
        foreach (var sub in new[]
        {
            @"Software\DrArmandoRevelo\HistoriaClinica",
            @"Software\Dr. Armando Revelo\HistoriaClinica"
        })
        {
            try { Registry.CurrentUser.DeleteSubKeyTree(sub, false); } catch { }
            try { Registry.LocalMachine.DeleteSubKeyTree(sub, false); } catch { }
        }
    }

    static void TryDeleteFile(string path)
    {
        try
        {
            if (!File.Exists(path)) return;
            File.SetAttributes(path, FileAttributes.Normal);
            File.Delete(path);
        }
        catch { }
    }

    static void TryDeleteDirectory(string path)
    {
        try
        {
            if (!Directory.Exists(path)) return;
            foreach (var file in Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories))
                try { File.SetAttributes(file, FileAttributes.Normal); } catch { }
            Directory.Delete(path, true);
        }
        catch { }
    }

    static void ScheduleSelfDelete()
    {
        try
        {
            var self = Environment.ProcessPath;
            if (string.IsNullOrWhiteSpace(self)) return;
            var dir = Path.GetDirectoryName(self) ?? "";
            var cmd = $"/c ping 127.0.0.1 -n 3 >nul & cd /d \"{Path.GetTempPath().TrimEnd('\\')}\" & rd /s /q \"{dir}\"";
            Process.Start(new ProcessStartInfo("cmd.exe", cmd)
            {
                UseShellExecute = false,
                CreateNoWindow = true
            });
        }
        catch { }
    }

    internal static void LaunchCleanupCopy(Form owner)
    {
        try
        {
            var self = Environment.ProcessPath ??
                throw new InvalidOperationException("No se pudo localizar el desinstalador.");
            var dir = Path.Combine(Path.GetTempPath(),
                "DrRevelo_Historia_Uninstall_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            var copy = Path.Combine(dir, "Desinstalar_Historia_Clinica_Dr_Revelo.exe");
            File.Copy(self, copy, true);
            Process.Start(new ProcessStartInfo(copy, "--cleanup")
            {
                UseShellExecute = true,
                Verb = "runas",
                WorkingDirectory = dir
            });
            owner.Close();
        }
        catch (Exception ex)
        {
            MessageBox.Show(owner, ex.Message, "No se pudo iniciar la limpieza",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}

internal sealed class ConfirmForm : Form
{
    readonly TextBox confirm = new();
    readonly Button remove = new();

    public ConfirmForm()
    {
        Text = "Desinstalar Historia Clínica - Dr. Armando Revelo";
        ClientSize = new Size(650, 470);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        BackColor = Color.FromArgb(244, 239, 229);
        ForeColor = Color.FromArgb(23, 59, 102);
        Font = new Font("Segoe UI", 10);

        var title = new Label
        {
            Text = "Desinstalación total",
            Location = new Point(30, 26),
            AutoSize = true,
            Font = new Font("Segoe UI", 22, FontStyle.Bold),
            ForeColor = Color.FromArgb(173, 59, 67)
        };
        var intro = new Label
        {
            Text = "Este modo elimina completamente Historia Clínica de esta PC.",
            Location = new Point(32, 77),
            Size = new Size(580, 28),
            Font = new Font("Segoe UI", 11, FontStyle.Bold)
        };
        var info = new Label
        {
            Text =
                "Se eliminarán:\n" +
                "• C:\\Historia Clinica Dr Revelo completa\n" +
                "• historias y base local guardadas dentro de esa carpeta\n" +
                "• .env y configuración privada\n" +
                "• respaldos y perfiles WebView2 propios de Historia\n" +
                "• accesos directos de Historia Clínica\n\n" +
                "Recepción NO se elimina.",
            Location = new Point(33, 119),
            Size = new Size(580, 190),
            ForeColor = Color.FromArgb(82, 87, 92)
        };
        var warning = new Label
        {
            Text = "Esta acción no se puede deshacer.",
            Location = new Point(33, 311),
            AutoSize = true,
            ForeColor = Color.FromArgb(160, 106, 25),
            Font = new Font("Segoe UI", 10, FontStyle.Bold)
        };
        var prompt = new Label
        {
            Text = "Para continuar escribe  ELIMINAR",
            Location = new Point(33, 346),
            AutoSize = true
        };

        confirm.Location = new Point(34, 376);
        confirm.Size = new Size(270, 32);
        confirm.Font = new Font("Segoe UI", 11);
        confirm.CharacterCasing = CharacterCasing.Upper;

        var cancel = new Button
        {
            Text = "Cancelar",
            Location = new Point(331, 374),
            Size = new Size(120, 38),
            FlatStyle = FlatStyle.Flat,
            BackColor = Color.FromArgb(218, 210, 198),
            ForeColor = Color.FromArgb(63, 68, 76)
        };
        cancel.FlatAppearance.BorderSize = 0;
        cancel.Click += (_, _) => Close();

        remove.Text = "Eliminar completamente";
        remove.Location = new Point(463, 374);
        remove.Size = new Size(155, 38);
        remove.FlatStyle = FlatStyle.Flat;
        remove.FlatAppearance.BorderSize = 0;
        remove.BackColor = Color.FromArgb(173, 59, 67);
        remove.ForeColor = Color.White;
        remove.Enabled = false;

        confirm.TextChanged += (_, _) =>
            remove.Enabled = confirm.Text.Trim().Equals("ELIMINAR", StringComparison.Ordinal);

        remove.Click += (_, _) =>
        {
            var second = MessageBox.Show(this,
                "Última confirmación:\n\n¿Eliminar Historia Clínica y TODOS sus datos locales de esta PC?",
                "Confirmar borrado total",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Warning,
                MessageBoxDefaultButton.Button2);
            if (second == DialogResult.Yes)
                Program.LaunchCleanupCopy(this);
        };

        Controls.AddRange(new Control[] { title, intro, info, warning, prompt, confirm, cancel, remove });
    }
}

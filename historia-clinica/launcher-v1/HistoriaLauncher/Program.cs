using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace DrRevelo.HistoriaLauncher;

internal static class Program
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SetCurrentProcessExplicitAppUserModelID(string AppID);

    const string MutexName = @"Local\DrRevelo.HistoriaClinica.SingleInstance.V1";
    const string FocusEventName = @"Local\DrRevelo.HistoriaClinica.FocusExisting.V1";

    [STAThread]
    static void Main()
    {
        try { SetCurrentProcessExplicitAppUserModelID("DrArmandoRevelo.HistoriaClinica"); } catch { }
        ApplicationConfiguration.Initialize();

        if (Environment.GetCommandLineArgs().Any(a =>
            a.Equals("--repair-shortcut", StringComparison.OrdinalIgnoreCase)))
        {
            ShortcutRepair.Repair();
            return;
        }

        using var mutex = new Mutex(true, MutexName, out bool first);
        if (!first)
        {
            try
            {
                using var evt = EventWaitHandle.OpenExisting(FocusEventName);
                evt.Set();
            }
            catch { }
            return;
        }

        using var focusEvent = new EventWaitHandle(false, EventResetMode.AutoReset, FocusEventName);
        using var form = new LauncherForm();

        var waiter = new Thread(() =>
        {
            while (!form.IsDisposed)
            {
                try
                {
                    focusEvent.WaitOne();
                    if (form.IsDisposed) break;
                    form.BeginInvoke(new Action(form.FocusExistingHistoria));
                }
                catch { break; }
            }
        })
        {
            IsBackground = true,
            Name = "HistoriaFocusListener"
        };
        waiter.Start();

        Application.Run(form);
    }
}

internal static class ShortcutRepair
{
    public static void Repair()
    {
        try
        {
            var exe = Environment.ProcessPath ??
                throw new InvalidOperationException("No se encontró el launcher.");
            var root = Path.GetDirectoryName(exe) ?? @"C:\Historia Clinica Dr Revelo";
            var paths = new[]
            {
                Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                    "Historia Clínica - Dr. Armando Revelo.lnk"),
                Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.Programs),
                    "Historia Clínica - Dr. Armando Revelo.lnk")
            };

            foreach (var path in paths)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                var shellType = Type.GetTypeFromProgID("WScript.Shell") ??
                    throw new InvalidOperationException(
                        "Windows Script Host no está disponible.");
                dynamic shell = Activator.CreateInstance(shellType)!;
                dynamic link = shell.CreateShortcut(path);
                link.TargetPath = exe;
                link.WorkingDirectory = root;
                link.IconLocation = exe + ",0";
                link.Description = "Historia Clínica - Dr. Armando Revelo";
                link.Save();
                try { Marshal.FinalReleaseComObject(link); } catch { }
                try { Marshal.FinalReleaseComObject(shell); } catch { }
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "No se pudo reparar el acceso directo de Historia Clínica.\n\n" +
                ex.Message,
                "Historia Clínica - Dr. Armando Revelo",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }
}

internal sealed class LauncherForm : Form
{
    const string LauncherVersion = "1.0.4";
    const string ChannelUrl = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/historia-clinica/launcher-v1/app-channel.json";
    const string LauncherChannelUrl = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/historia-clinica/launcher-v1/launcher-channel.json";
    const int Port = 8787;

    readonly HttpClient http = new(new HttpClientHandler { AutomaticDecompression = DecompressionMethods.All });
    readonly string root;

    readonly Label lblPercent = new();
    readonly Label lblStage = new();
    readonly Label lblDetail = new();
    readonly Label lblVersion = new();
    readonly Panel progressTrack = new();
    readonly Panel progressFill = new();
    readonly Panel updatePanel = new();
    readonly Label updateTitle = new();
    readonly Label updateNotes = new();
    readonly Button btnUpdate = new();
    readonly Button btnLater = new();

    TaskCompletionSource<bool>? updateChoice;
    bool closingAllowed;
    HistoriaForm? historiaForm;

    public LauncherForm()
    {
        root = ResolveRoot();
        http.Timeout = TimeSpan.FromSeconds(8);
        http.DefaultRequestHeaders.UserAgent.ParseAdd("DrRevelo-HistoriaLauncher/1.0");
        BuildUi();
        Shown += async (_, _) => await StartAsync();
        FormClosing += (_, e) =>
        {
            if (!closingAllowed)
            {
                e.Cancel = true;
                WindowState = FormWindowState.Minimized;
            }
        };
    }

    static string ResolveRoot()
    {
        var baseDir = AppContext.BaseDirectory.TrimEnd('\\');
        if (File.Exists(Path.Combine(baseDir, "app.py"))) return baseDir;
        const string canonical = @"C:\Historia Clinica Dr Revelo";
        if (File.Exists(Path.Combine(canonical, "app.py"))) return canonical;
        return baseDir;
    }

    void BuildUi()
    {
        Text = "Historia Clínica - Dr. Armando Revelo";
        ClientSize = new Size(720, 450);
        MinimumSize = MaximumSize = Size;
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        BackColor = Color.FromArgb(244, 239, 229);
        ForeColor = Color.FromArgb(23, 59, 102);
        Font = new Font("Segoe UI", 10);

        var accent = Color.FromArgb(43, 106, 167);
        var muted = Color.FromArgb(101, 93, 82);
        var panel = Color.FromArgb(255, 253, 250);

        var brand = new Label {
            Text = "HISTORIA CLÍNICA", AutoSize = true, Location = new Point(34, 29),
            ForeColor = Color.FromArgb(43, 106, 167), Font = new Font("Segoe UI", 9, FontStyle.Bold)
        };
        var doctor = new Label {
            Text = "Dr. Armando Revelo", AutoSize = true, Location = new Point(31, 52),
            Font = new Font("Segoe UI", 22, FontStyle.Bold), ForeColor = Color.FromArgb(23, 59, 102)
        };
        var protectedBadge = new Label {
            Text = "  SISTEMA PROTEGIDO  ", AutoSize = true, Location = new Point(545, 37),
            ForeColor = Color.FromArgb(46, 118, 93), BackColor = Color.FromArgb(234, 243, 237),
            Padding = new Padding(6, 5, 6, 5), Font = new Font("Segoe UI", 8, FontStyle.Bold)
        };

        lblPercent.Text = "0 %";
        lblPercent.TextAlign = ContentAlignment.MiddleRight;
        lblPercent.Location = new Point(545, 112);
        lblPercent.Size = new Size(130, 54);
        lblPercent.Font = new Font("Segoe UI", 28, FontStyle.Bold);

        lblStage.Text = "Preparando Historia Clínica";
        lblStage.AutoSize = true;
        lblStage.Location = new Point(34, 122);
        lblStage.Font = new Font("Segoe UI", 15, FontStyle.Bold);

        lblDetail.Text = "Iniciando sistema seguro…";
        lblDetail.AutoSize = false;
        lblDetail.Location = new Point(35, 159);
        lblDetail.Size = new Size(530, 44);
        lblDetail.ForeColor = muted;
        lblDetail.Font = new Font("Segoe UI", 10);

        progressTrack.Location = new Point(36, 213);
        progressTrack.Size = new Size(639, 9);
        progressTrack.BackColor = Color.FromArgb(222, 214, 201);
        progressTrack.Controls.Add(progressFill);
        progressFill.Location = new Point(0, 0);
        progressFill.Size = new Size(0, 9);
        progressFill.BackColor = accent;

        var steps = new Label {
            Text = "COMPROBAR              PREPARAR              INICIAR              LISTO",
            Location = new Point(36, 240), Size = new Size(639, 25),
            ForeColor = Color.FromArgb(132, 123, 112), Font = new Font("Segoe UI", 8, FontStyle.Bold)
        };

        var sep = new Panel { Location = new Point(36, 284), Size = new Size(639, 1), BackColor = Color.FromArgb(207, 200, 189) };

        lblVersion.Location = new Point(36, 305);
        lblVersion.Size = new Size(520, 25);
        lblVersion.ForeColor = muted;
        lblVersion.Font = new Font("Segoe UI", 9);

        var footer = new Label {
            Text = "Las actualizaciones oficiales son obligatorias y nunca reemplazan pacientes, .env ni bases.",
            Location = new Point(36, 365), Size = new Size(640, 38),
            ForeColor = Color.FromArgb(132, 123, 112), Font = new Font("Segoe UI", 8)
        };

        updatePanel.Location = new Point(25, 102);
        updatePanel.Size = new Size(670, 286);
        updatePanel.BackColor = panel;
        updatePanel.Visible = false;
        updatePanel.BringToFront();

        updateTitle.Location = new Point(24, 22);
        updateTitle.Size = new Size(620, 34);
        updateTitle.Font = new Font("Segoe UI", 16, FontStyle.Bold);
        updateTitle.ForeColor = Color.FromArgb(23, 59, 102);

        updateNotes.Location = new Point(26, 68);
        updateNotes.Size = new Size(616, 125);
        updateNotes.Font = new Font("Segoe UI", 10);
        updateNotes.ForeColor = Color.FromArgb(101, 93, 82);

        btnLater.Text = "Salir";
        btnLater.Size = new Size(130, 42);
        btnLater.Location = new Point(350, 216);
        StyleButton(btnLater, Color.FromArgb(218, 210, 198));
        btnLater.ForeColor = Color.FromArgb(63, 68, 76);

        btnUpdate.Text = "Actualizar ahora";
        btnUpdate.Size = new Size(160, 42);
        btnUpdate.Location = new Point(494, 216);
        StyleButton(btnUpdate, accent);

        btnUpdate.Click += (_, _) =>
        {
            updatePanel.Visible = false;
            updateChoice?.TrySetResult(true);
        };
        btnLater.Click += (_, _) =>
        {
            updatePanel.Visible = false;
            updateChoice?.TrySetResult(false);
        };

        updatePanel.Controls.AddRange(new Control[] { updateTitle, updateNotes, btnLater, btnUpdate });
        Controls.AddRange(new Control[] {
            brand, doctor, protectedBadge, lblPercent, lblStage, lblDetail,
            progressTrack, steps, sep, lblVersion, footer, updatePanel
        });

        AcceptButton = btnUpdate;
    }

    static void StyleButton(Button b, Color color)
    {
        b.FlatStyle = FlatStyle.Flat;
        b.FlatAppearance.BorderSize = 0;
        b.BackColor = color;
        b.ForeColor = Color.White;
        b.Font = new Font("Segoe UI", 9, FontStyle.Bold);
        b.Cursor = Cursors.Hand;
    }

    void SetProgress(int percent, string stage, string detail)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => SetProgress(percent, stage, detail));
            return;
        }
        percent = Math.Clamp(percent, 0, 100);
        lblPercent.Text = $"{percent} %";
        lblStage.Text = stage;
        lblDetail.Text = detail;
        progressFill.Width = (int)Math.Round(progressTrack.Width * (percent / 100.0));
        Refresh();
    }

    async Task StartAsync()
    {
        try
        {
            var installed = await ReadInstalledVersionAsync();
            lblVersion.Text = $"Historia Clínica {installed}  ·  Launcher {LauncherVersion}";
            SetProgress(4, "Preparando Historia Clínica", "Comprobando componentes esenciales…");

            var pyw = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
            var app = Path.Combine(root, "app.py");
            if (!File.Exists(pyw) || !File.Exists(app))
                throw new InvalidOperationException("No encuentro los componentes principales de Historia Clínica en " + root);

            await Task.Delay(180);
            SetProgress(8, "Comprobando launcher", "Buscando una versión nueva del sistema de inicio…");

            LauncherChannel? launcherChannel = null;
            try { launcherChannel = await GetLauncherChannelAsync(); }
            catch { /* Sin internet nunca bloquea el trabajo */ }

            if (launcherChannel is not null && IsNewer(launcherChannel.LatestVersion, LauncherVersion))
            {
                bool updateLauncher = await AskLauncherUpdateAsync(launcherChannel);
                if (!updateLauncher)
                {
                    SetProgress(8, "Actualización obligatoria", "Historia Clínica no se abrirá hasta actualizar el launcher.");
                    closingAllowed = true;
                    Close();
                    return;
                }

                await DownloadAndInstallLauncherAsync(launcherChannel);
                return;
            }

            SetProgress(10, "Comprobando actualizaciones", "Consultando el canal estable de Historia Clínica…");

            AppChannel? channel = null;
            string? appChannelError = null;
            try { channel = await GetChannelAsync(); }
            catch (Exception ex) { appChannelError = ex.Message; }

            string? backup = null;
            string? expectedAfterUpdate = null;

            if (channel is not null)
            {
                SetProgress(14, "Actualizaciones comprobadas",
                    $"Local {installed} · Disponible {channel.AppVersion}");
            }
            else
            {
                SetProgress(14, "No se pudo comprobar Historia Clínica",
                    string.IsNullOrWhiteSpace(appChannelError) ? "Se abrirá la versión instalada." : appChannelError);
            }

            if (channel is not null && IsNewer(channel.AppVersion, installed))
            {
                bool doUpdate = await AskUpdateAsync(channel);
                if (!doUpdate)
                {
                    SetProgress(22, "Actualización obligatoria",
                        $"Historia Clínica {channel.AppVersion} debe instalarse antes de continuar.");
                    closingAllowed = true;
                    Close();
                    return;
                }

                expectedAfterUpdate = channel.AppVersion;
                backup = await ApplyUpdateAsync(channel);
                installed = channel.AppVersion;
                lblVersion.Text = $"Historia Clínica {installed}  ·  Launcher {LauncherVersion}";
            }
            else
            {
                SetProgress(22, "Sistema al día", channel is null
                    ? "Sin conexión al canal; se abrirá la versión instalada."
                    : "No hay actualizaciones pendientes.");
            }

            bool ready = await StartBackendAsync(expectedAfterUpdate);
            if (!ready && backup is not null)
            {
                SetProgress(52, "Recuperando versión estable",
                    "La actualización no inició correctamente. Cerrando candidata y restaurando…");
                await StopBackendIfOursAsync();
                await WaitForPortFreeAsync(TimeSpan.FromSeconds(8));
                await RollbackAsync(backup);
                ready = await StartBackendAsync(null);
            }

            if (!ready)
                throw new InvalidOperationException("El servidor local de Historia Clínica no respondió.");

            SetProgress(92, "Servidor listo", "Abriendo la ventana de Historia Clínica…");
            var nativeWindow = await OpenHistoriaAsync();
            if (nativeWindow is null)
                throw new InvalidOperationException("No se pudo abrir la ventana de Historia Clínica.");

            CleanupLegacyLauncher();
            SetProgress(100, "Todo listo", "Historia Clínica está lista para trabajar.");
            await Task.Delay(850);

            if (nativeWindow.Value)
            {
                // La ventana WebView2 vive en este mismo EXE; ocultamos el launcher
                // y mantenemos el message loop hasta que Historia Clínica se cierre.
                Hide();
            }
            else
            {
                // Fallback externo (Edge/navegador): el launcher ya puede terminar.
                closingAllowed = true;
                Close();
            }
        }
        catch (Exception ex)
        {
            SetProgress(Math.Max(1, ParsePercent()), "No se pudo iniciar Historia Clínica", ex.Message);
            MessageBox.Show(
                ex.Message + "\n\nEl launcher no eliminó sus datos. Puede cerrar esta ventana y revisar el sistema.",
                "Historia Clínica - Dr. Armando Revelo", MessageBoxButtons.OK, MessageBoxIcon.Error);
            closingAllowed = true;
        }
    }

    public void FocusExistingHistoria()
    {
        try
        {
            if (historiaForm is not null && !historiaForm.IsDisposed)
            {
                if (historiaForm.WindowState == FormWindowState.Minimized)
                    historiaForm.WindowState = FormWindowState.Maximized;
                if (!historiaForm.Visible) historiaForm.Show();
                historiaForm.TopMost = true;
                historiaForm.Activate();
                historiaForm.BringToFront();
                historiaForm.TopMost = false;
                return;
            }

            if (WindowState == FormWindowState.Minimized)
                WindowState = FormWindowState.Normal;
            if (!Visible) Show();
            TopMost = true;
            Activate();
            BringToFront();
            TopMost = false;
        }
        catch { }
    }

    int ParsePercent()
    {
        var t = lblPercent.Text.Replace("%", "").Trim();
        return int.TryParse(t, out var n) ? n : 1;
    }

    async Task<string> ReadInstalledVersionAsync()
    {
        // 1) Backend vivo: /api/version.
        var live = await GetBackendVersionAsync();
        if (!string.IsNullOrWhiteSpace(live)) return live;

        // 2) ÚNICA fuente local persistente para versiones nuevas.
        try
        {
            var p = Path.Combine(root, "historia-version.json");
            if (File.Exists(p))
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(p, Encoding.UTF8));
                if (doc.RootElement.TryGetProperty("version", out var v))
                {
                    var value = v.GetString();
                    if (!string.IsNullOrWhiteSpace(value)) return value;
                }
            }
        }
        catch { }

        // 3) Compatibilidad temporal con instalaciones antiguas.
        try
        {
            var p = Path.Combine(root, "update_manifest.json");
            if (File.Exists(p))
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(p, Encoding.UTF8));
                if (doc.RootElement.TryGetProperty("version", out var v))
                    return v.GetString() ?? "desconocida";
            }
        }
        catch { }
        return "desconocida";
    }

    async Task<AppChannel?> GetChannelAsync()
    {
        Exception? last = null;
        for (int attempt = 1; attempt <= 3; attempt++)
        {
            try
            {
                var url = ChannelUrl + "?t=" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "&a=" + attempt;
                using var req = new HttpRequestMessage(HttpMethod.Get, url);
                req.Headers.CacheControl = new CacheControlHeaderValue { NoCache = true, NoStore = true };
                using var resp = await http.SendAsync(req);
                resp.EnsureSuccessStatusCode();
                var json = await resp.Content.ReadAsStringAsync();
                var parsed = JsonSerializer.Deserialize<AppChannel>(json, JsonOpts);
                if (parsed is null || string.IsNullOrWhiteSpace(parsed.AppVersion))
                    throw new InvalidOperationException("El canal de Historia Clínica no devolvió appVersion.");
                return parsed;
            }
            catch (Exception ex)
            {
                last = ex;
                if (attempt < 3) await Task.Delay(350 * attempt);
            }
        }
        throw new InvalidOperationException("No se pudo leer el canal de Historia Clínica tras 3 intentos.", last);
    }

    async Task<LauncherChannel?> GetLauncherChannelAsync()
    {
        var url = LauncherChannelUrl + "?t=" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        using var resp = await http.GetAsync(url);
        resp.EnsureSuccessStatusCode();
        var json = await resp.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<LauncherChannel>(json, JsonOpts);
    }

    async Task<bool> AskLauncherUpdateAsync(LauncherChannel channel)
    {
        updateChoice = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        updateTitle.Text = $"Nuevo Launcher {channel.LatestVersion}";
        updateNotes.Text =
            (string.IsNullOrWhiteSpace(channel.Notes)
                ? $"Hay una nueva versión del Launcher. Actual: {LauncherVersion} · Nueva: {channel.LatestVersion}."
                : channel.Notes) +
            "\n\nEsta actualización es obligatoria. Para usar Historia Clínica debes elegir “Actualizar ahora”. Si eliges “Salir”, el programa no se abrirá.";
        updatePanel.Visible = true;
        updatePanel.BringToFront();
        btnUpdate.Focus();
        return await updateChoice.Task;
    }

    async Task DownloadAndInstallLauncherAsync(LauncherChannel channel)
    {
        if (string.IsNullOrWhiteSpace(channel.InstallerUrl) ||
            string.IsNullOrWhiteSpace(channel.InstallerSha256) ||
            string.IsNullOrWhiteSpace(channel.UpdaterUrl) ||
            string.IsNullOrWhiteSpace(channel.UpdaterSha256))
            throw new InvalidOperationException(
                "El canal del launcher no contiene el instalador/helper completo.");

        var dir = Path.Combine(Path.GetTempPath(), "DrReveloHistoriaLauncher",
            "self_update_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);

        var installer = Path.Combine(dir, $"Launcher_{channel.LatestVersion.Replace('.', '_')}.exe");
        var helper = Path.Combine(dir, "HistoriaLauncherUpdater.exe");
        var log = Path.Combine(root, "data", "historia_launcher_self_update.log");
        Directory.CreateDirectory(Path.GetDirectoryName(log)!);

        try
        {
            await File.WriteAllTextAsync(log,
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] Inicio self-update {LauncherVersion} -> {channel.LatestVersion}\r\n",
                Encoding.UTF8);

            SetProgress(12, "Descargando nuevo launcher",
                $"Launcher {LauncherVersion} → {channel.LatestVersion}");

            await DownloadSelfUpdateFileAsync(
                channel.InstallerUrl, installer, channel.InstallerSha256,
                12, 52, "instalador", log);

            SetProgress(54, "Descargando actualizador seguro",
                "Preparando el componente que reemplaza el launcher…");

            await DownloadSelfUpdateFileAsync(
                channel.UpdaterUrl, helper, channel.UpdaterSha256,
                54, 64, "helper", log);

            SetProgress(66, "Verificando actualización",
                "Instalador y helper verificados por SHA-256.");

            var currentExe = Path.Combine(root, "HistoriaClinicaLauncher.exe");
            var helperArgs =
                $"--parent {Environment.ProcessId} " +
                $"--installer {QuoteArg(installer)} " +
                $"--launcher {QuoteArg(currentExe)} " +
                $"--root {QuoteArg(root)} " +
                $"--log {QuoteArg(log)}";

            await File.AppendAllTextAsync(log,
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] Lanzando helper temporal elevado.\r\n",
                Encoding.UTF8);

            var psi = new ProcessStartInfo(helper, helperArgs)
            {
                UseShellExecute = true,
                Verb = "runas",
                WorkingDirectory = dir,
                WindowStyle = ProcessWindowStyle.Hidden
            };

            Process? hp;
            try
            {
                hp = Process.Start(psi);
            }
            catch (System.ComponentModel.Win32Exception ex)
            {
                await File.AppendAllTextAsync(log,
                    $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] UAC/helper no iniciado: {ex.NativeErrorCode} {ex.Message}\r\n",
                    Encoding.UTF8);
                throw new InvalidOperationException(
                    ex.NativeErrorCode == 1223
                        ? "La actualización fue cancelada en la ventana de permisos de Windows."
                        : "Windows no pudo iniciar el actualizador del launcher.", ex);
            }

            if (hp is null)
                throw new InvalidOperationException("Windows no devolvió el proceso del actualizador.");

            SetProgress(70, "Aplicando actualización",
                "Windows terminará de reemplazar el launcher y lo abrirá nuevamente.");

            closingAllowed = true;
            Close();
        }
        catch (Exception ex)
        {
            try
            {
                await File.AppendAllTextAsync(log,
                    $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] ERROR: {ex}\r\n",
                    Encoding.UTF8);
            }
            catch { }
            throw;
        }
    }

    async Task DownloadSelfUpdateFileAsync(
        string url, string destination, string expectedSha,
        int startPct, int endPct, string label, string log)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get,
            url + (url.Contains('?') ? "&" : "?") +
            "t=" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
        req.Headers.CacheControl = new CacheControlHeaderValue { NoCache = true, NoStore = true };

        using var resp = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead);
        resp.EnsureSuccessStatusCode();
        var length = resp.Content.Headers.ContentLength;

        await using var input = await resp.Content.ReadAsStreamAsync();
        var buffer = new byte[128 * 1024];
        long read = 0;

        await using (var output = File.Create(destination))
        {
            while (true)
            {
                int n = await input.ReadAsync(buffer);
                if (n <= 0) break;
                await output.WriteAsync(buffer.AsMemory(0, n));
                read += n;

                int pct = startPct;
                if (length is > 0)
                    pct = startPct + (int)((endPct - startPct) *
                        Math.Min(1.0, read / (double)length.Value));

                SetProgress(pct, "Descargando actualización del launcher",
                    length is > 0
                        ? $"{label}: {read / 1024 / 1024} MB de {length.Value / 1024 / 1024} MB"
                        : $"{label}: {read / 1024 / 1024} MB");
            }
            await output.FlushAsync();
        }

        var got = await Sha256Async(destination);
        if (!got.Equals(expectedSha, StringComparison.OrdinalIgnoreCase))
        {
            TryDeleteFile(destination);
            throw new InvalidOperationException(
                $"La verificación SHA-256 del {label} no coincidió.");
        }

        try
        {
            await File.AppendAllTextAsync(log,
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {label} OK SHA256={got}\r\n",
                Encoding.UTF8);
        }
        catch { }
    }

    async Task<bool> AskUpdateAsync(AppChannel channel)
    {
        updateChoice = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        updateTitle.Text = $"Actualización {channel.AppVersion} disponible";
        updateNotes.Text =
            (string.IsNullOrWhiteSpace(channel.Notes) ? "Hay una nueva versión estable de Historia Clínica." : channel.Notes) +
            "\n\nEsta actualización es obligatoria. Para usar Historia Clínica debes elegir “Actualizar ahora”. Si eliges “Salir”, el programa no se abrirá.";
        updatePanel.Visible = true;
        updatePanel.BringToFront();
        btnUpdate.Focus();
        return await updateChoice.Task;
    }

    async Task<string> ApplyUpdateAsync(AppChannel channel)
    {
        if (channel.Files is null || channel.Files.Count == 0)
            throw new InvalidOperationException("El canal de actualización no contiene archivos.");

        var staging = Path.Combine(Path.GetTempPath(), "DrReveloHistoriaLauncher",
            "staging_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);

        try
        {
            for (int i = 0; i < channel.Files.Count; i++)
            {
                var f = channel.Files[i];
                EnsureSafeUpdatePath(f.Path);
                var rel = f.Path.Replace('/', Path.DirectorySeparatorChar);
                var dst = Path.Combine(staging, rel);
                Directory.CreateDirectory(Path.GetDirectoryName(dst)!);

                int basePct = 24 + (int)(22.0 * i / channel.Files.Count);
                int nextPct = 24 + (int)(22.0 * (i + 1) / channel.Files.Count);
                await DownloadVerifiedAsync(f, dst, basePct, nextPct, i + 1, channel.Files.Count);
            }

            SetProgress(48, "Verificando actualización", "Probando la nueva versión antes de tocar la instalada…");
            await PrecheckCandidateAsync(staging, channel.AppVersion);

            SetProgress(54, "Preparando actualización", "Cerrando la versión anterior y creando respaldo…");
            await StopBackendIfOursAsync();
            if (!await WaitForPortFreeAsync(TimeSpan.FromSeconds(10)))
                throw new InvalidOperationException("El servidor anterior no liberó el puerto 8787. No se modificó la instalación.");

            var backup = Path.Combine(root, "update_backups",
                "launcher_v1_" + DateTime.Now.ToString("yyyyMMdd_HHmmss"));
            Directory.CreateDirectory(backup);
            var entries = new List<BackupEntry>();

            foreach (var f in channel.Files)
            {
                var rel = f.Path.Replace('/', Path.DirectorySeparatorChar);
                var current = Path.Combine(root, rel);
                var existed = File.Exists(current);
                entries.Add(new BackupEntry { Path = f.Path, Existed = existed });
                if (existed)
                {
                    var b = Path.Combine(backup, rel);
                    Directory.CreateDirectory(Path.GetDirectoryName(b)!);
                    File.Copy(current, b, true);
                }
            }
            File.WriteAllText(Path.Combine(backup, "backup_manifest.json"),
                JsonSerializer.Serialize(entries, JsonOpts), Encoding.UTF8);

            SetProgress(58, "Instalando actualización", "Aplicando archivos verificados…");
            try
            {
                int done = 0;
                foreach (var f in channel.Files)
                {
                    var rel = f.Path.Replace('/', Path.DirectorySeparatorChar);
                    var src = Path.Combine(staging, rel);
                    var dest = Path.Combine(root, rel);
                    Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
                    var temp = dest + ".launcher_v1_new";
                    File.Copy(src, temp, true);
                    File.Move(temp, dest, true);
                    done++;
                    SetProgress(58 + (int)(10.0 * done / channel.Files.Count),
                        "Instalando actualización", $"Aplicando {done} de {channel.Files.Count} archivos…");
                }
            }
            catch
            {
                await RollbackAsync(backup);
                throw;
            }

            SetProgress(69, "Actualización instalada", $"Historia Clínica {channel.AppVersion} quedó preparada.");
            return backup;
        }
        finally
        {
            TryDeleteDirectory(staging);
        }
    }

    async Task DownloadVerifiedAsync(ChannelFile f, string dst, int startPct, int endPct, int index, int total)
    {
        var urls = (f.Parts is { Count: > 0 })
            ? f.Parts.Where(x => !string.IsNullOrWhiteSpace(x)).ToList()
            : (string.IsNullOrWhiteSpace(f.Url) ? [] : new List<string> { f.Url });
        if (urls.Count == 0)
            throw new InvalidOperationException($"No hay URL para {f.Path}.");

        var buffer = new byte[64 * 1024];
        await using (var output = File.Create(dst))
        {
            for (int part = 0; part < urls.Count; part++)
            {
                var url = urls[part];
                using var req = new HttpRequestMessage(HttpMethod.Get,
                    url + (url.Contains('?') ? "&" : "?") +
                    "t=" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
                req.Headers.CacheControl = new CacheControlHeaderValue { NoCache = true, NoStore = true };
                using var resp = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead);
                resp.EnsureSuccessStatusCode();
                await using var input = await resp.Content.ReadAsStreamAsync();

                long read = 0;
                var length = resp.Content.Headers.ContentLength;
                while (true)
                {
                    int n = await input.ReadAsync(buffer);
                    if (n <= 0) break;
                    await output.WriteAsync(buffer.AsMemory(0, n));
                    read += n;
                    double partFraction = length is > 0
                        ? Math.Min(1.0, read / (double)length.Value)
                        : 0.5;
                    double overall = (part + partFraction) / urls.Count;
                    int pct = startPct + (int)((endPct - startPct) * overall);
                    SetProgress(pct, "Descargando actualización",
                        urls.Count > 1
                            ? $"Archivo {index} de {total} · {Path.GetFileName(f.Path)} · parte {part + 1}/{urls.Count}"
                            : $"Archivo {index} de {total} · {Path.GetFileName(f.Path)}");
                }
            }
            await output.FlushAsync();
        }

        var got = await Sha256Async(dst);
        if (!got.Equals(f.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(
                $"La verificación de {f.Path} no coincidió. No se instaló nada.");
    }

    async Task PrecheckCandidateAsync(string staging, string expected)
    {
        var versionPath = Path.Combine(staging, "historia-version.json");
        if (File.Exists(versionPath))
        {
            using var versionDoc = JsonDocument.Parse(
                await File.ReadAllTextAsync(versionPath, Encoding.UTF8));
            var canonical = versionDoc.RootElement.TryGetProperty("version", out var vv)
                ? vv.GetString()?.Trim()
                : null;
            if (string.IsNullOrWhiteSpace(canonical) ||
                !canonical.Equals(expected, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException(
                    $"historia-version.json anuncia {canonical ?? "[vacío]"}; se esperaba {expected}.");
        }

        var manifestPath = Path.Combine(staging, "update_manifest.json");
        if (File.Exists(manifestPath))
        {
            using var manifestDoc = JsonDocument.Parse(
                await File.ReadAllTextAsync(manifestPath, Encoding.UTF8));
            foreach (var alias in new[] { "version", "app_version", "runtime_version" })
            {
                if (!manifestDoc.RootElement.TryGetProperty(alias, out var av)) continue;
                var value = av.GetString()?.Trim();
                if (string.IsNullOrWhiteSpace(value) ||
                    !value.Equals(expected, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException(
                        $"{alias}={value ?? "[vacío]"} no coincide con la versión canónica {expected}.");
            }
        }

        var python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        if (!File.Exists(python))
            throw new InvalidOperationException(
                "No encuentro el Python de Historia Clínica para verificar la actualización.");

        var trial = Path.Combine(Path.GetTempPath(), "DrReveloHistoriaLauncher",
            "precheck_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(trial);

        Process? server = null;
        try
        {
            // Construimos explícitamente una instalación aislada mínima.
            // No dependemos de un glob *.py: app.py debe existir físicamente
            // antes de intentar importarlo.
            foreach (var name in new[]
            {
                "app.py",
                "cloud_sync.py",
                "cloud_presence_patch.py",
                "lan_bridge.py",
                "requirements.txt"
            })
            {
                var source = Path.Combine(root, name);
                if (File.Exists(source))
                    File.Copy(source, Path.Combine(trial, name), true);
            }

            var rootStatic = Path.Combine(root, "static");
            if (Directory.Exists(rootStatic))
                CopyDirectory(rootStatic, Path.Combine(trial, "static"));

            var data = Path.Combine(trial, "data");
            Directory.CreateDirectory(data);
            var sourceDb = Path.Combine(root, "data", "historia_clinica.db");
            var trialDb = Path.Combine(data, "historia_clinica.db");
            if (File.Exists(sourceDb))
                await BackupSqliteAsync(python, sourceDb, trialDb);

            // La candidata siempre se superpone al runtime estable.
            foreach (var file in Directory.GetFiles(staging, "*", SearchOption.AllDirectories))
            {
                var rel = Path.GetRelativePath(staging, file);
                var dest = Path.Combine(trial, rel);
                Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
                File.Copy(file, dest, true);
            }

            var trialApp = Path.Combine(trial, "app.py");
            if (!File.Exists(trialApp))
                throw new InvalidOperationException(
                    "La copia aislada no contiene app.py. " +
                    "La actualización se canceló antes de tocar Historia Clínica.");

            foreach (var required in new[]
            {
                "cloud_sync.py",
                "cloud_presence_patch.py",
                "lan_bridge.py"
            })
            {
                if (!File.Exists(Path.Combine(trial, required)))
                    throw new InvalidOperationException(
                        $"La copia aislada no contiene {required}. " +
                        "La actualización se canceló antes de tocar Historia Clínica.");
            }

            await VerifyTrialImportAsync(python, trial, expected);

            int testPort = ReserveFreePort();
            var log = Path.Combine(trial, "trial_startup.log");
            var serverScript = Path.Combine(trial, "_launcher_precheck_server.py");
            var logLiteral = JsonSerializer.Serialize(log);
            var trialLiteralForServer = JsonSerializer.Serialize(trial);
            var serverCode =
                "import os, sys, traceback, uvicorn, importlib.util\n" +
                $"trial = {trialLiteralForServer}\n" +
                $"log_path = {logLiteral}\n" +
                "os.chdir(trial)\n" +
                "sys.path.insert(0, trial)\n" +
                "log = open(log_path, 'a', encoding='utf-8', buffering=1)\n" +
                "sys.stdout = log\n" +
                "sys.stderr = log\n" +
                "try:\n" +
                "    app_path = os.path.join(trial, 'app.py')\n" +
                "    spec = importlib.util.spec_from_file_location('app', app_path)\n" +
                "    if spec is None or spec.loader is None:\n" +
                "        raise RuntimeError('No se pudo crear spec para app.py')\n" +
                "    historia_app = importlib.util.module_from_spec(spec)\n" +
                "    sys.modules['app'] = historia_app\n" +
                "    spec.loader.exec_module(historia_app)\n" +
                "    print('IMPORT_OK', getattr(historia_app, 'APP_VERSION', ''), flush=True)\n" +
                $"    uvicorn.run(historia_app.app, host='127.0.0.1', port={testPort}, access_log=False, log_level='warning')\n" +
                "except Exception:\n" +
                "    traceback.print_exc()\n" +
                "    raise\n";
            await File.WriteAllTextAsync(serverScript, serverCode, new UTF8Encoding(false));

            var psi = new ProcessStartInfo(python, QuoteArg(serverScript))
            {
                WorkingDirectory = trial,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            psi.Environment["HC_PREFLIGHT"] = "1";
            psi.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
            psi.Environment["HISTORIA_DATABASE_URL"] = "";
            psi.Environment["DATABASE_URL"] = "";

            server = Process.Start(psi) ??
                throw new InvalidOperationException(
                    "No se pudo iniciar la copia aislada de Historia Clínica.");

            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(30);
            while (DateTime.UtcNow < deadline)
            {
                if (server.HasExited)
                {
                    var tail = File.Exists(log)
                        ? LastLines(await File.ReadAllTextAsync(log, Encoding.UTF8), 12)
                        : "";
                    throw new InvalidOperationException(
                        "La copia de prueba terminó antes de iniciar." +
                        (string.IsNullOrWhiteSpace(tail) ? "" : "\n" + tail));
                }

                var probe = await ProbeVersionAsync(testPort);
                if (probe is not null &&
                    probe.Value.product.Equals(
                        "historia-clinica-dr-revelo",
                        StringComparison.OrdinalIgnoreCase) &&
                    probe.Value.version.Equals(expected, StringComparison.OrdinalIgnoreCase))
                    return;

                await Task.Delay(250);
            }

            var finalTail = File.Exists(log)
                ? LastLines(await File.ReadAllTextAsync(log, Encoding.UTF8), 8)
                : "";
            throw new InvalidOperationException(
                "La nueva versión no respondió correctamente en la prueba aislada." +
                (string.IsNullOrWhiteSpace(finalTail) ? "" : "\n" + finalTail));
        }
        finally
        {
            try
            {
                if (server is not null && !server.HasExited)
                {
                    server.Kill(true);
                    await server.WaitForExitAsync();
                }
            }
            catch { }
            TryDeleteDirectory(trial);
        }
    }

    async Task VerifyTrialImportAsync(string python, string trial, string expected)
    {
        var script = Path.Combine(trial, "_launcher_precheck_import.py");
        var trialLiteral = JsonSerializer.Serialize(trial);
        var code =
            "import os, sys, traceback, importlib.util\n" +
            $"trial = {trialLiteral}\n" +
            "os.chdir(trial)\n" +
            "sys.path.insert(0, trial)\n" +
            "app_path = os.path.join(trial, 'app.py')\n" +
            "print('TRIAL_APP=' + str(os.path.isfile(app_path)), flush=True)\n" +
            "try:\n" +
            "    spec = importlib.util.spec_from_file_location('app', app_path)\n" +
            "    if spec is None or spec.loader is None:\n" +
            "        raise RuntimeError('No se pudo crear spec para app.py')\n" +
            "    app = importlib.util.module_from_spec(spec)\n" +
            "    sys.modules['app'] = app\n" +
            "    spec.loader.exec_module(app)\n" +
            "    print(getattr(app, 'APP_VERSION', ''), flush=True)\n" +
            "except Exception:\n" +
            "    traceback.print_exc()\n" +
            "    raise\n";
        await File.WriteAllTextAsync(script, code, new UTF8Encoding(false));

        var psi = new ProcessStartInfo(python, QuoteArg(script))
        {
            WorkingDirectory = trial,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        psi.Environment["HC_PREFLIGHT"] = "1";
        psi.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        psi.Environment["HISTORIA_DATABASE_URL"] = "";
        psi.Environment["DATABASE_URL"] = "";

        using var p = Process.Start(psi) ??
            throw new InvalidOperationException(
                "No se pudo ejecutar la importación de prueba de Historia Clínica.");

        var outTask = p.StandardOutput.ReadToEndAsync();
        var errTask = p.StandardError.ReadToEndAsync();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await p.WaitForExitAsync(cts.Token);

        var stdout = (await outTask).Trim();
        var stderr = (await errTask).Trim();
        if (p.ExitCode != 0 ||
            !stdout.Contains(expected, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "La copia aislada no pudo importar app.py." +
                (string.IsNullOrWhiteSpace(stderr)
                    ? ""
                    : "\n" + LastLines(stderr, 12)));
        }
    }

    async Task BackupSqliteAsync(string python, string source, string destination)
    {
        string code =
            "import sqlite3;" +
            $"s=sqlite3.connect(r'{EscapePy(source)}');" +
            $"d=sqlite3.connect(r'{EscapePy(destination)}');" +
            "s.backup(d);d.close();s.close()";
        var psi = new ProcessStartInfo(python, "-c " + QuoteArg(code))
        {
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        using var p = Process.Start(psi) ??
            throw new InvalidOperationException(
                "No se pudo preparar la copia aislada de la base.");
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        await p.WaitForExitAsync(cts.Token);
        if (p.ExitCode != 0)
            throw new InvalidOperationException(
                "No se pudo crear la copia aislada de la base de Historia Clínica.");
    }

    static int ReserveFreePort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var dir in Directory.GetDirectories(source, "*", SearchOption.AllDirectories))
            Directory.CreateDirectory(
                Path.Combine(destination, Path.GetRelativePath(source, dir)));
        foreach (var file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
        {
            var dest = Path.Combine(destination, Path.GetRelativePath(source, file));
            Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
            File.Copy(file, dest, true);
        }
    }

    async Task<bool> StartBackendAsync(string? expected)
    {
        var current = await GetBackendVersionAsync();
        if (!string.IsNullOrWhiteSpace(current))
        {
            if (expected is null ||
                current.Equals(expected, StringComparison.OrdinalIgnoreCase))
                return true;

            SetProgress(70, "Cerrando versión anterior",
                $"Servidor activo {current}; se necesita {expected}…");
            await StopBackendIfOursAsync();
            if (!await WaitForPortFreeAsync(TimeSpan.FromSeconds(10)))
                return false;
        }
        else if (await IsPortOpenAsync())
        {
            SetProgress(70, "Puerto ocupado",
                "El puerto 8787 está siendo usado por otro proceso. No se cerrará un proceso desconocido.");
            return false;
        }

        var python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        if (!File.Exists(python)) return false;

        var log = Path.Combine(root, "data", "backend_startup.log");
        Directory.CreateDirectory(Path.GetDirectoryName(log)!);
        try { File.WriteAllText(log, "", Encoding.UTF8); } catch { }

        var scriptDir = Path.Combine(Path.GetTempPath(), "DrReveloHistoriaLauncher");
        Directory.CreateDirectory(scriptDir);
        var backendScript = Path.Combine(scriptDir,
            "backend_" + Guid.NewGuid().ToString("N") + ".py");
        var rootLiteral = JsonSerializer.Serialize(root);
        var logLiteral = JsonSerializer.Serialize(log);
        var backendCode =
            "import os, sys, traceback, uvicorn, importlib.util\n" +
            $"root = {rootLiteral}\n" +
            $"log_path = {logLiteral}\n" +
            "os.chdir(root)\n" +
            "sys.path.insert(0, root)\n" +
            "log = open(log_path, 'a', encoding='utf-8', buffering=1)\n" +
            "sys.stdout = log\n" +
            "sys.stderr = log\n" +
            "try:\n" +
            "    app_path = os.path.join(root, 'app.py')\n" +
            "    spec = importlib.util.spec_from_file_location('app', app_path)\n" +
            "    if spec is None or spec.loader is None:\n" +
            "        raise RuntimeError('No se pudo crear spec para app.py')\n" +
            "    historia_app = importlib.util.module_from_spec(spec)\n" +
            "    sys.modules['app'] = historia_app\n" +
            "    spec.loader.exec_module(historia_app)\n" +
            "    print('IMPORT_OK', getattr(historia_app, 'APP_VERSION', ''), flush=True)\n" +
            $"    uvicorn.run(historia_app.app, host='127.0.0.1', port={Port}, access_log=False, log_level='warning')\n" +
            "except Exception:\n" +
            "    traceback.print_exc()\n" +
            "    raise\n";
        await File.WriteAllTextAsync(backendScript, backendCode, new UTF8Encoding(false));

        var psi = new ProcessStartInfo(python, QuoteArg(backendScript))
        {
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        Process? launched;
        try { launched = Process.Start(psi); }
        catch { return false; }
        if (launched is null) return false;

        const int tries = 120;
        for (int i = 0; i < tries; i++)
        {
            SetProgress(70 + (int)(18.0 * i / tries), "Iniciando Historia Clínica",
                expected is null
                    ? "Esperando al servidor local…"
                    : $"Esperando Historia Clínica {expected}…");

            var probe = await ProbeVersionAsync(Port);
            if (probe is not null &&
                probe.Value.product.Equals(
                    "historia-clinica-dr-revelo",
                    StringComparison.OrdinalIgnoreCase))
            {
                if (expected is null ||
                    probe.Value.version.Equals(expected, StringComparison.OrdinalIgnoreCase))
                    return true;

                SetProgress(74, "Versión incorrecta detectada",
                    $"Respondió {probe.Value.version}; se esperaba {expected}. Reiniciando…");
                await StopBackendIfOursAsync();
                await WaitForPortFreeAsync(TimeSpan.FromSeconds(8));
                return false;
            }

            try
            {
                if (launched.HasExited)
                {
                    var tail = File.Exists(log)
                        ? LastLines(await File.ReadAllTextAsync(log, Encoding.UTF8), 8)
                        : "";
                    if (!string.IsNullOrWhiteSpace(tail))
                        SetProgress(78, "Historia Clínica no pudo iniciar", tail);
                    return false;
                }
            }
            catch { }

            await Task.Delay(250);
        }
        return false;
    }

    async Task<(string product, string version)?> ProbeVersionAsync(int port)
    {
        try
        {
            using var local = new HttpClient
            {
                Timeout = TimeSpan.FromMilliseconds(900)
            };
            using var resp = await local.GetAsync(
                $"http://127.0.0.1:{port}/api/version");
            resp.EnsureSuccessStatusCode();
            var text = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(text);
            var product = doc.RootElement.TryGetProperty("product", out var p)
                ? p.GetString() ?? ""
                : "";
            var version = doc.RootElement.TryGetProperty("version", out var v)
                ? v.GetString() ?? ""
                : "";
            if (string.IsNullOrWhiteSpace(version)) return null;
            return (product, version);
        }
        catch { return null; }
    }

    async Task<string?> GetBackendVersionAsync()
    {
        var probe = await ProbeVersionAsync(Port);
        if (probe is null ||
            !probe.Value.product.Equals(
                "historia-clinica-dr-revelo",
                StringComparison.OrdinalIgnoreCase))
            return null;
        return probe.Value.version;
    }

    async Task<bool> IsBackendReadyAsync(string? expected = null)
    {
        var ver = await GetBackendVersionAsync();
        if (string.IsNullOrWhiteSpace(ver)) return false;
        return expected is null || ver.Equals(expected, StringComparison.OrdinalIgnoreCase);
    }

    async Task<bool> IsPortOpenAsync()
    {
        try
        {
            using var client = new TcpClient();
            using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(500));
            await client.ConnectAsync("127.0.0.1", Port, cts.Token);
            return client.Connected;
        }
        catch { return false; }
    }

    async Task<bool> WaitForPortFreeAsync(TimeSpan timeout)
    {
        var until = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < until)
        {
            if (!await IsPortOpenAsync()) return true;
            await Task.Delay(250);
        }
        return !await IsPortOpenAsync();
    }

    async Task<int?> FindPortPidAsync()
    {
        try
        {
            var psi = new ProcessStartInfo("netstat", "-ano -p tcp") {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true
            };
            using var p = Process.Start(psi);
            if (p is null) return null;
            var output = await p.StandardOutput.ReadToEndAsync();
            await p.WaitForExitAsync();

            foreach (var line in output.Split('\n'))
            {
                if (!line.Contains($":{Port}") ||
                    !line.Contains("LISTENING", StringComparison.OrdinalIgnoreCase))
                    continue;
                var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length >= 5 && int.TryParse(parts[^1], out var pid))
                    return pid;
            }
        }
        catch { }
        return null;
    }

    async Task StopBackendIfOursAsync()
    {
        var pid = await FindPortPidAsync();
        if (pid is null) return;

        try
        {
            using var target = Process.GetProcessById(pid.Value);
            bool allowed = false;

            try
            {
                var name = target.ProcessName.ToLowerInvariant();
                if (name.StartsWith("python"))
                {
                    var exe = target.MainModule?.FileName ?? "";
                    if (!string.IsNullOrWhiteSpace(exe) &&
                        exe.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        allowed = true;
                }
            }
            catch { }

            // Si el API responde como Historia Clínica, también es seguro cerrar ese PID del puerto dedicado.
            if (!allowed && !string.IsNullOrWhiteSpace(await GetBackendVersionAsync()))
                allowed = true;

            if (!allowed) return;

            target.Kill(true);
            await target.WaitForExitAsync();
        }
        catch { }
    }

    async Task<bool?> OpenHistoriaAsync()
    {
        try
        {
            var shell = new HistoriaForm(root, $"http://127.0.0.1:{Port}");
            bool ok = await shell.InitializeAsync();
            if (ok)
            {
                historiaForm = shell;
                shell.FormClosed += (_, _) =>
                {
                    historiaForm = null;
                    closingAllowed = true;
                    if (!IsDisposed) Close();
                };
                shell.Show();
                shell.Activate();
                shell.BringToFront();
                return true; // ventana propia: mantener vivo este proceso
            }
            shell.Dispose();
        }
        catch { }

        // Respaldo: si WebView2 no está disponible, Historia Clínica sigue abriendo con Edge.
        try
        {
            var edge = FindEdge();
            if (edge is not null)
            {
                var profile = Path.Combine(root, "data", "edge_profile");
                Directory.CreateDirectory(profile);
                Process.Start(new ProcessStartInfo {
                    FileName = edge,
                    Arguments = $"--app=http://127.0.0.1:{Port} --start-maximized --no-first-run --disable-background-mode --user-data-dir={QuoteArg(profile)}",
                    WorkingDirectory = root,
                    UseShellExecute = false
                });
                return false; // abrió correctamente, pero en fallback externo
            }
            Process.Start(new ProcessStartInfo($"http://127.0.0.1:{Port}") { UseShellExecute = true });
            return false;
        }
        catch { return null; }
    }

    static string? FindEdge()
    {
        var candidates = new[] {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Microsoft", "Edge", "Application", "msedge.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Microsoft", "Edge", "Application", "msedge.exe")
        };
        return candidates.FirstOrDefault(File.Exists);
    }

    async Task RollbackAsync(string backup)
    {
        var mf = Path.Combine(backup, "backup_manifest.json");
        if (!File.Exists(mf)) return;
        var entries = JsonSerializer.Deserialize<List<BackupEntry>>(await File.ReadAllTextAsync(mf), JsonOpts) ?? [];
        foreach (var e in entries)
        {
            EnsureSafeUpdatePath(e.Path);
            var rel = e.Path.Replace('/', Path.DirectorySeparatorChar);
            var dest = Path.Combine(root, rel);
            var src = Path.Combine(backup, rel);
            try
            {
                if (e.Existed && File.Exists(src))
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
                    File.Copy(src, dest, true);
                }
                else if (!e.Existed && File.Exists(dest))
                {
                    File.Delete(dest);
                }
            }
            catch { }
        }
    }

    void CleanupLegacyLauncher()
    {
        try
        {
            foreach (var name in new[]
            {
                "ABRIR_HISTORIA_CLINICA.py",
                "ABRIR_HISTORIA_CLINICA.pyw",
                "INICIAR.bat"
            })
                TryDeleteFile(Path.Combine(root, name));

            var pycache = Path.Combine(root, "__pycache__");
            if (Directory.Exists(pycache))
                foreach (var file in Directory.GetFiles(
                    pycache, "ABRIR_HISTORIA_CLINICA*.pyc"))
                    TryDeleteFile(file);

            foreach (var name in new[] { "launcher.log", "launcher_state.json" })
                TryDeleteFile(Path.Combine(root, "data", name));

            var temp = Path.GetTempPath();
            foreach (var pattern in new[]
            {
                "historia_update_*",
                "historia_repair_*",
                "hc_launcher_*"
            })
            {
                foreach (var file in Directory.GetFiles(temp, pattern))
                    TryDeleteFile(file);
                foreach (var dir in Directory.GetDirectories(temp, pattern))
                    TryDeleteDirectory(dir);
            }

            TryDeleteDirectory(Path.Combine(temp, "DrReveloHistoriaLauncher"));
        }
        catch { }
    }

    static void EnsureSafeUpdatePath(string path)
    {
        var p = path.Replace('\\', '/').Trim();
        if (string.IsNullOrWhiteSpace(p) || p.StartsWith('/') || p.Contains("../") || Path.IsPathRooted(p))
            throw new InvalidOperationException("Ruta de actualización no permitida: " + path);

        var low = p.ToLowerInvariant();
        string[] protectedPrefixes = { "data/", "backups/", "update_backups/" };
        string[] protectedExact = {
            ".env",
            "historiaclinicalauncher.exe",
            "historialauncherupdater.exe",
            "desinstalar_historia_clinica_dr_revelo.exe"
        };
        if (protectedPrefixes.Any(low.StartsWith) || protectedExact.Contains(low) ||
            low.EndsWith(".db") || low.EndsWith(".sqlite") || low.EndsWith(".sqlite3") ||
            low.EndsWith(".mdb") || low.EndsWith(".accdb") ||
            low.EndsWith(".xlsx") || low.EndsWith(".xls"))
            throw new InvalidOperationException(
                "El canal intentó tocar un archivo protegido: " + path);
    }

    static async Task<string> Sha256Async(string path)
    {
        await using var fs = File.OpenRead(path);
        var hash = await SHA256.HashDataAsync(fs);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    static bool IsNewer(string candidate, string installed)
    {
        static Version V(string s)
        {
            var nums = new string(s.Where(c => char.IsDigit(c) || c == '.').ToArray()).Trim('.');
            var parts = nums.Split('.', StringSplitOptions.RemoveEmptyEntries).Take(4).ToArray();
            while (parts.Length < 2) parts = parts.Append("0").ToArray();
            return Version.TryParse(string.Join('.', parts), out var v) ? v : new Version(0, 0);
        }
        return V(candidate) > V(installed);
    }

    static string QuoteArg(string s) => "\"" + s.Replace("\"", "\\\"") + "\"";
    static string EscapePy(string s) => s.Replace("'", "\\'");
    static string LastLines(string text, int n) => string.Join("\n",
        text.Split('\n').TakeLast(n).Select(x => x.TrimEnd()));

    static void TryDeleteFile(string p) { try { if (File.Exists(p)) File.Delete(p); } catch { } }
    static void TryDeleteDirectory(string p) { try { if (Directory.Exists(p)) Directory.Delete(p, true); } catch { } }

    static readonly JsonSerializerOptions JsonOpts = new() {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true
    };
}


internal sealed class HistoriaForm : Form
{
    readonly string root;
    readonly string url;
    readonly WebView2 web = new();

    public HistoriaForm(string rootPath, string targetUrl, bool childWindow = false)
    {
        root = rootPath;
        url = targetUrl;

        Text = "Historia Clínica - Dr. Armando Revelo";
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = childWindow ? FormWindowState.Normal : FormWindowState.Maximized;
        Size = childWindow ? new Size(1220, 860) : Size;
        MinimumSize = new Size(960, 640);
        BackColor = Color.FromArgb(244, 239, 229);
        ShowInTaskbar = true;
        ShowIcon = true;

        try
        {
            var icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            if (icon is not null) Icon = icon;
        }
        catch { }

        web.Dock = DockStyle.Fill;
        web.DefaultBackgroundColor = Color.White;
        Controls.Add(web);
    }

    public async Task<bool> InitializeAsync()
    {
        try
        {
            var profile = Path.Combine(root, "data", "webview2_profile");
            Directory.CreateDirectory(profile);

            var env = await CoreWebView2Environment.CreateAsync(
                browserExecutableFolder: null,
                userDataFolder: profile);

            await web.EnsureCoreWebView2Async(env);

            web.CoreWebView2.Settings.AreDevToolsEnabled = false;
            web.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
            web.CoreWebView2.Settings.IsStatusBarEnabled = false;
            web.CoreWebView2.Settings.IsZoomControlEnabled = true;
            web.CoreWebView2.NewWindowRequested += async (_, e) =>
            {
                try
                {
                    if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var target) &&
                        target.Host.Equals("127.0.0.1", StringComparison.OrdinalIgnoreCase) &&
                        target.Port == 8787)
                    {
                        e.Handled = true;
                        var child = new HistoriaForm(root, e.Uri, true);
                        if (await child.InitializeAsync())
                            child.Show(this);
                        else
                            child.Dispose();
                        return;
                    }

                    Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true });
                    e.Handled = true;
                }
                catch { }
            };

            web.Source = new Uri(url);
            return true;
        }
        catch
        {
            return false;
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            try { web.Dispose(); } catch { }
        }
        base.Dispose(disposing);
    }
}

internal sealed class LauncherChannel
{
    public string LatestVersion { get; set; } = "";
    public string Notes { get; set; } = "";
    public string InstallerUrl { get; set; } = "";
    public string InstallerSha256 { get; set; } = "";
    public string UpdaterUrl { get; set; } = "";
    public string UpdaterSha256 { get; set; } = "";
}

internal sealed class AppChannel
{
    public string AppVersion { get; set; } = "";
    public string Notes { get; set; } = "";
    public List<ChannelFile> Files { get; set; } = [];
}

internal sealed class ChannelFile
{
    public string Path { get; set; } = "";
    public string Url { get; set; } = "";
    public List<string> Parts { get; set; } = [];
    public string Sha256 { get; set; } = "";
}

internal sealed class BackupEntry
{
    public string Path { get; set; } = "";
    public bool Existed { get; set; }
}

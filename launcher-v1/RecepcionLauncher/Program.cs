using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace DrRevelo.RecepcionLauncher;

internal static class Program
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SetCurrentProcessExplicitAppUserModelID(string AppID);

    const string MutexName = @"Local\DrRevelo.Recepcion.SingleInstance.V1";
    const string FocusEventName = @"Local\DrRevelo.Recepcion.FocusExisting.V1";

    [STAThread]
    static void Main()
    {
        try { SetCurrentProcessExplicitAppUserModelID("DrArmandoRevelo.Recepcion"); } catch { }
        ApplicationConfiguration.Initialize();

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
                    form.BeginInvoke(new Action(form.FocusExistingReception));
                }
                catch { break; }
            }
        })
        {
            IsBackground = true,
            Name = "RecepcionFocusListener"
        };
        waiter.Start();

        Application.Run(form);
    }
}

internal sealed class LauncherForm : Form
{
    const string LauncherVersion = "1.0.6";
    const string ChannelUrl = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/launcher-v1/app-channel.json";
    const string LauncherChannelUrl = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/launcher-v1/launcher-channel.json";
    const int Port = 8000;

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
    ReceptionForm? receptionForm;

    public LauncherForm()
    {
        root = ResolveRoot();
        http.Timeout = TimeSpan.FromSeconds(8);
        http.DefaultRequestHeaders.UserAgent.ParseAdd("DrRevelo-RecepcionLauncher/1.0");
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
        const string canonical = @"C:\Recepcion Dr Revelo";
        if (File.Exists(Path.Combine(canonical, "app.py"))) return canonical;
        return baseDir;
    }

    void BuildUi()
    {
        Text = "Recepción - Dr. Armando Revelo";
        ClientSize = new Size(720, 450);
        MinimumSize = MaximumSize = Size;
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        BackColor = Color.FromArgb(13, 22, 39);
        ForeColor = Color.White;
        Font = new Font("Segoe UI", 10);

        var accent = Color.FromArgb(79, 141, 247);
        var muted = Color.FromArgb(154, 174, 202);
        var panel = Color.FromArgb(22, 36, 60);

        var brand = new Label {
            Text = "RECEPCIÓN", AutoSize = true, Location = new Point(34, 29),
            ForeColor = Color.FromArgb(117, 169, 255), Font = new Font("Segoe UI", 9, FontStyle.Bold)
        };
        var doctor = new Label {
            Text = "Dr. Armando Revelo", AutoSize = true, Location = new Point(31, 52),
            Font = new Font("Segoe UI", 22, FontStyle.Bold), ForeColor = Color.White
        };
        var protectedBadge = new Label {
            Text = "  SISTEMA PROTEGIDO  ", AutoSize = true, Location = new Point(545, 37),
            ForeColor = Color.FromArgb(128, 220, 166), BackColor = Color.FromArgb(27, 54, 55),
            Padding = new Padding(6, 5, 6, 5), Font = new Font("Segoe UI", 8, FontStyle.Bold)
        };

        lblPercent.Text = "0 %";
        lblPercent.TextAlign = ContentAlignment.MiddleRight;
        lblPercent.Location = new Point(545, 112);
        lblPercent.Size = new Size(130, 54);
        lblPercent.Font = new Font("Segoe UI", 28, FontStyle.Bold);

        lblStage.Text = "Preparando Recepción";
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
        progressTrack.BackColor = Color.FromArgb(37, 55, 82);
        progressTrack.Controls.Add(progressFill);
        progressFill.Location = new Point(0, 0);
        progressFill.Size = new Size(0, 9);
        progressFill.BackColor = accent;

        var steps = new Label {
            Text = "COMPROBAR              PREPARAR              INICIAR              LISTO",
            Location = new Point(36, 240), Size = new Size(639, 25),
            ForeColor = Color.FromArgb(108, 132, 166), Font = new Font("Segoe UI", 8, FontStyle.Bold)
        };

        var sep = new Panel { Location = new Point(36, 284), Size = new Size(639, 1), BackColor = Color.FromArgb(38, 56, 82) };

        lblVersion.Location = new Point(36, 305);
        lblVersion.Size = new Size(520, 25);
        lblVersion.ForeColor = muted;
        lblVersion.Font = new Font("Segoe UI", 9);

        var footer = new Label {
            Text = "El launcher nunca modifica pacientes, .env o bases sin una actualización confirmada.",
            Location = new Point(36, 365), Size = new Size(640, 38),
            ForeColor = Color.FromArgb(105, 127, 158), Font = new Font("Segoe UI", 8)
        };

        updatePanel.Location = new Point(25, 102);
        updatePanel.Size = new Size(670, 286);
        updatePanel.BackColor = panel;
        updatePanel.Visible = false;
        updatePanel.BringToFront();

        updateTitle.Location = new Point(24, 22);
        updateTitle.Size = new Size(620, 34);
        updateTitle.Font = new Font("Segoe UI", 16, FontStyle.Bold);
        updateTitle.ForeColor = Color.White;

        updateNotes.Location = new Point(26, 68);
        updateNotes.Size = new Size(616, 125);
        updateNotes.Font = new Font("Segoe UI", 10);
        updateNotes.ForeColor = Color.FromArgb(193, 207, 226);

        btnLater.Text = "Más tarde";
        btnLater.Size = new Size(130, 42);
        btnLater.Location = new Point(350, 216);
        StyleButton(btnLater, Color.FromArgb(49, 65, 89));

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
            lblVersion.Text = $"Recepción {installed}  ·  Launcher {LauncherVersion}";
            SetProgress(4, "Preparando Recepción", "Comprobando componentes esenciales…");

            var pyw = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
            var app = Path.Combine(root, "app.py");
            if (!File.Exists(pyw) || !File.Exists(app))
                throw new InvalidOperationException("No encuentro los componentes principales de Recepción en " + root);

            await Task.Delay(180);
            SetProgress(8, "Comprobando launcher", "Buscando una versión nueva del sistema de inicio…");

            LauncherChannel? launcherChannel = null;
            try { launcherChannel = await GetLauncherChannelAsync(); }
            catch { /* Sin internet nunca bloquea el trabajo */ }

            if (launcherChannel is not null && IsNewer(launcherChannel.LatestVersion, LauncherVersion))
            {
                bool updateLauncher = await AskLauncherUpdateAsync(launcherChannel);
                if (updateLauncher)
                {
                    await DownloadAndInstallLauncherAsync(launcherChannel);
                    return;
                }
            }

            SetProgress(10, "Comprobando actualizaciones", "Consultando el canal estable de Recepción…");

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
                SetProgress(14, "No se pudo comprobar Recepción",
                    string.IsNullOrWhiteSpace(appChannelError) ? "Se abrirá la versión instalada." : appChannelError);
            }

            if (channel is not null && IsNewer(channel.AppVersion, installed))
            {
                bool doUpdate = await AskUpdateAsync(channel);
                if (doUpdate)
                {
                    expectedAfterUpdate = channel.AppVersion;
                    backup = await ApplyUpdateAsync(channel);
                    installed = channel.AppVersion;
                    lblVersion.Text = $"Recepción {installed}  ·  Launcher {LauncherVersion}";
                }
                else
                {
                    SetProgress(22, "Actualización aplazada", "Abriendo la versión instalada sin cambios…");
                }
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
                    "La actualización no inició correctamente. Restaurando automáticamente…");
                await RollbackAsync(backup);
                ready = await StartBackendAsync(null);
            }

            if (!ready)
                throw new InvalidOperationException("El servidor local de Recepción no respondió.");

            SetProgress(92, "Servidor listo", "Abriendo la ventana de Recepción…");
            var nativeWindow = await OpenReceptionAsync();
            if (nativeWindow is null)
                throw new InvalidOperationException("No se pudo abrir la ventana de Recepción.");

            CleanupLegacyLauncher();
            SetProgress(100, "Todo listo", "Recepción está lista para trabajar.");
            await Task.Delay(850);

            if (nativeWindow.Value)
            {
                // La ventana WebView2 vive en este mismo EXE; ocultamos el launcher
                // y mantenemos el message loop hasta que Recepción se cierre.
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
            SetProgress(Math.Max(1, ParsePercent()), "No se pudo iniciar Recepción", ex.Message);
            MessageBox.Show(
                ex.Message + "\n\nEl launcher no eliminó sus datos. Puede cerrar esta ventana y revisar el sistema.",
                "Recepción - Dr. Armando Revelo", MessageBoxButtons.OK, MessageBoxIcon.Error);
            closingAllowed = true;
        }
    }

    public void FocusExistingReception()
    {
        try
        {
            if (receptionForm is not null && !receptionForm.IsDisposed)
            {
                if (receptionForm.WindowState == FormWindowState.Minimized)
                    receptionForm.WindowState = FormWindowState.Maximized;
                if (!receptionForm.Visible) receptionForm.Show();
                receptionForm.TopMost = true;
                receptionForm.Activate();
                receptionForm.BringToFront();
                receptionForm.TopMost = false;
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
        // /api/version es la fuente autoritativa cuando el backend ya está vivo.
        try
        {
            using var local = new HttpClient { Timeout = TimeSpan.FromMilliseconds(1200) };
            using var resp = await local.GetAsync($"http://127.0.0.1:{Port}/api/version");
            resp.EnsureSuccessStatusCode();
            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("version", out var v))
            {
                var value = v.GetString();
                if (!string.IsNullOrWhiteSpace(value)) return value;
            }
        }
        catch { }

        // Fallback: manifest local.
        try
        {
            var p = Path.Combine(root, "update_manifest.json");
            if (!File.Exists(p)) return "desconocida";
            using var doc = JsonDocument.Parse(File.ReadAllText(p, Encoding.UTF8));
            if (doc.RootElement.TryGetProperty("app_version", out var a))
            {
                var value = a.GetString();
                if (!string.IsNullOrWhiteSpace(value)) return value;
            }
            if (doc.RootElement.TryGetProperty("version", out var v))
                return v.GetString() ?? "desconocida";
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
                    throw new InvalidOperationException("El canal de Recepción no devolvió appVersion.");
                return parsed;
            }
            catch (Exception ex)
            {
                last = ex;
                if (attempt < 3) await Task.Delay(350 * attempt);
            }
        }
        throw new InvalidOperationException("No se pudo leer el canal de Recepción tras 3 intentos.", last);
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
            "\n\nLa descarga solo comenzará si eliges “Actualizar ahora”.";
        updatePanel.Visible = true;
        updatePanel.BringToFront();
        btnUpdate.Focus();
        return await updateChoice.Task;
    }

    async Task DownloadAndInstallLauncherAsync(LauncherChannel channel)
    {
        if (string.IsNullOrWhiteSpace(channel.InstallerUrl) ||
            string.IsNullOrWhiteSpace(channel.InstallerSha256))
            throw new InvalidOperationException("El canal del launcher no contiene un instalador válido.");

        var dir = Path.Combine(Path.GetTempPath(), "DrReveloLauncher", "self_update");
        Directory.CreateDirectory(dir);
        var installer = Path.Combine(dir, $"Launcher_{channel.LatestVersion.Replace('.', '_')}.exe");

        SetProgress(12, "Descargando nuevo launcher",
            $"Launcher {LauncherVersion} → {channel.LatestVersion}");

        using (var req = new HttpRequestMessage(HttpMethod.Get,
            channel.InstallerUrl + (channel.InstallerUrl.Contains('?') ? "&" : "?") +
            "t=" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()))
        using (var resp = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead))
        {
            resp.EnsureSuccessStatusCode();
            var length = resp.Content.Headers.ContentLength;
            await using var input = await resp.Content.ReadAsStreamAsync();
            await using var output = File.Create(installer);
            var buffer = new byte[128 * 1024];
            long read = 0;
            while (true)
            {
                int n = await input.ReadAsync(buffer);
                if (n <= 0) break;
                await output.WriteAsync(buffer.AsMemory(0, n));
                read += n;

                int pct = 12;
                if (length is > 0)
                    pct = 12 + (int)(48 * Math.Min(1.0, read / (double)length.Value));

                SetProgress(pct, "Descargando nuevo launcher",
                    length is > 0
                        ? $"{read / 1024 / 1024} MB de {length.Value / 1024 / 1024} MB"
                        : $"{read / 1024 / 1024} MB descargados");
            }
            await output.FlushAsync();
        }

        SetProgress(63, "Verificando launcher", "Comprobando integridad SHA-256…");
        var got = await Sha256Async(installer);
        if (!got.Equals(channel.InstallerSha256, StringComparison.OrdinalIgnoreCase))
        {
            TryDeleteFile(installer);
            throw new InvalidOperationException(
                "El instalador del launcher no superó la verificación de seguridad. No se ejecutó.");
        }

        SetProgress(70, "Preparando actualización", "Cerrando esta versión de forma segura…");

        var helper = Path.Combine(dir, "actualizar_launcher.cmd");
        var currentExe = Path.Combine(root, "RecepcionLauncher.exe");
        var script =
            "@echo off\r\n" +
            "ping 127.0.0.1 -n 3 >nul\r\n" +
            $"start /wait \"\" \"{installer}\" /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /SP-\r\n" +
            $"start \"\" explorer.exe \"{currentExe}\"\r\n" +
            "del /f /q \"%~f0\" >nul 2>&1\r\n";
        await File.WriteAllTextAsync(helper, script, Encoding.ASCII);

        var psi = new ProcessStartInfo(helper)
        {
            UseShellExecute = true,
            Verb = "runas",
            WorkingDirectory = dir
        };
        Process.Start(psi);

        closingAllowed = true;
        Close();
    }

    async Task<bool> AskUpdateAsync(AppChannel channel)
    {
        updateChoice = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        updateTitle.Text = $"Actualización {channel.AppVersion} disponible";
        updateNotes.Text =
            (string.IsNullOrWhiteSpace(channel.Notes) ? "Hay una nueva versión estable de Recepción." : channel.Notes) +
            "\n\nLa descarga solo comenzará si eliges “Actualizar ahora”.";
        updatePanel.Visible = true;
        updatePanel.BringToFront();
        btnUpdate.Focus();
        return await updateChoice.Task;
    }

    async Task<string> ApplyUpdateAsync(AppChannel channel)
    {
        if (channel.Files is null || channel.Files.Count == 0)
            throw new InvalidOperationException("El canal de actualización no contiene archivos.");

        var staging = Path.Combine(Path.GetTempPath(), "DrReveloLauncher",
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

            SetProgress(54, "Preparando actualización", "Creando respaldo de la versión que funciona…");
            await StopBackendIfOursAsync();

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

            SetProgress(69, "Actualización instalada", $"Recepción {channel.AppVersion} quedó preparada.");
            return backup;
        }
        finally
        {
            TryDeleteDirectory(staging);
        }
    }

    async Task DownloadVerifiedAsync(ChannelFile f, string dst, int startPct, int endPct, int index, int total)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, f.Url + (f.Url.Contains('?') ? "&" : "?") +
            "t=" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
        using var resp = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead);
        resp.EnsureSuccessStatusCode();
        var length = resp.Content.Headers.ContentLength;
        await using var input = await resp.Content.ReadAsStreamAsync();
        var buffer = new byte[64 * 1024];
        long read = 0;

        // IMPORTANTE: cerrar el archivo descargado ANTES de calcular SHA-256.
        // File.Create usa bloqueo exclusivo; verificar el hash mientras el stream
        // seguía abierto provocaba ERROR_SHARING_VIOLATION en Windows.
        await using (var output = File.Create(dst))
        {
            while (true)
            {
                int n = await input.ReadAsync(buffer);
                if (n <= 0) break;
                await output.WriteAsync(buffer.AsMemory(0, n));
                read += n;
                int pct = startPct;
                if (length is > 0)
                    pct = startPct + (int)((endPct - startPct) * Math.Min(1.0, read / (double)length.Value));
                SetProgress(pct, "Descargando actualización",
                    $"Archivo {index} de {total} · {Path.GetFileName(f.Path)}");
            }
            await output.FlushAsync();
        }

        var got = await Sha256Async(dst);
        if (!got.Equals(f.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException($"La verificación de {f.Path} no coincidió. No se instaló nada.");
    }

    async Task PrecheckCandidateAsync(string staging, string expected)
    {
        var python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        if (!File.Exists(python))
            throw new InvalidOperationException("No encuentro el Python portátil para verificar la actualización.");

        var testData = Path.Combine(staging, "_precheck_data");
        Directory.CreateDirectory(testData);
        string code =
            "import sys;" +
            $"sys.path.insert(0,r'{EscapePy(staging)}');" +
            $"sys.path.insert(1,r'{EscapePy(root)}');" +
            "import app;" +
            "print(getattr(app,'APP_VERSION',''))";

        var psi = new ProcessStartInfo(python, "-c " + QuoteArg(code)) {
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        psi.Environment["RP_DATA_DIR"] = testData;
        psi.Environment["RP_FORCE_OFFLINE"] = "1";
        psi.Environment["RP_DESKTOP_LAUNCH"] = "1";
        psi.Environment["WHATSAPP_ENABLED"] = "0";
        psi.Environment["DATABASE_URL"] = "";
        psi.Environment["NEON_DATABASE_URL"] = "";
        psi.Environment["PYTHONPATH"] = staging + ";" + root;

        using var p = Process.Start(psi) ?? throw new InvalidOperationException("No se pudo ejecutar la prueba previa.");
        var outTask = p.StandardOutput.ReadToEndAsync();
        var errTask = p.StandardError.ReadToEndAsync();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(35));
        await p.WaitForExitAsync(cts.Token);
        var stdout = (await outTask).Trim();
        var stderr = (await errTask).Trim();
        if (p.ExitCode != 0 || !stdout.Contains(expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("La versión nueva no superó la prueba previa." +
                (string.IsNullOrWhiteSpace(stderr) ? "" : "\n" + LastLines(stderr, 5)));
    }

    async Task<bool> StartBackendAsync(string? expected)
    {
        if (await IsBackendReadyAsync(expected)) return true;

        var pyw = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
        var app = Path.Combine(root, "app.py");
        var psi = new ProcessStartInfo(pyw, QuoteArg(app)) {
            WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true
        };
        Process.Start(psi);

        const int tries = 80;
        for (int i = 0; i < tries; i++)
        {
            SetProgress(70 + (int)(18.0 * i / tries), "Iniciando Recepción",
                "Esperando al servidor local…");
            if (await IsBackendReadyAsync(expected)) return true;
            await Task.Delay(250);
        }
        return false;
    }

    async Task<bool> IsBackendReadyAsync(string? expected = null)
    {
        try
        {
            using var local = new HttpClient { Timeout = TimeSpan.FromMilliseconds(850) };
            var s = await local.GetStringAsync($"http://127.0.0.1:{Port}/api/version");
            using var doc = JsonDocument.Parse(s);
            var ver = doc.RootElement.TryGetProperty("version", out var v) ? v.GetString() : null;
            if (string.IsNullOrWhiteSpace(ver)) return false;
            return expected is null || ver.Equals(expected, StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    }

    async Task StopBackendIfOursAsync()
    {
        if (!await IsBackendReadyAsync()) return;
        try
        {
            var psi = new ProcessStartInfo("netstat", "-ano -p tcp") {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true
            };
            using var p = Process.Start(psi);
            if (p is null) return;
            var text = await p.StandardOutput.ReadToEndAsync();
            await p.WaitForExitAsync();
            foreach (var line in text.Split('\n'))
            {
                if (!line.Contains($":{Port}") || !line.Contains("LISTENING", StringComparison.OrdinalIgnoreCase))
                    continue;
                var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length < 5 || !int.TryParse(parts[^1], out var pid)) continue;
                try
                {
                    using var target = Process.GetProcessById(pid);
                    target.Kill(true);
                    await target.WaitForExitAsync();
                }
                catch { }
                break;
            }
        }
        catch { }
    }

    async Task<bool?> OpenReceptionAsync()
    {
        try
        {
            var shell = new ReceptionForm(root, $"http://127.0.0.1:{Port}");
            bool ok = await shell.InitializeAsync();
            if (ok)
            {
                receptionForm = shell;
                shell.FormClosed += (_, _) =>
                {
                    receptionForm = null;
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

        // Respaldo: si WebView2 no está disponible, Recepción sigue abriendo con Edge.
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
            var legacy = Path.Combine(root, "ABRIR_RECEPCION.py");
            if (File.Exists(legacy)) File.Delete(legacy);

            var pycache = Path.Combine(root, "__pycache__");
            if (Directory.Exists(pycache))
                foreach (var f in Directory.GetFiles(pycache, "ABRIR_RECEPCION*.pyc"))
                    TryDeleteFile(f);

            var oldLog = Path.Combine(root, "data", "launcher_errors.log");
            TryDeleteFile(oldLog);
            var oldState = Path.Combine(root, "data", "auto_update_state.json");
            TryDeleteFile(oldState);

            var temp = Path.GetTempPath();
            foreach (var pattern in new[] { "dr_revelo_splash_*", "rp_launcher_*" })
            {
                foreach (var f in Directory.GetFiles(temp, pattern)) TryDeleteFile(f);
                foreach (var d in Directory.GetDirectories(temp, pattern)) TryDeleteDirectory(d);
            }
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
        string[] protectedExact = { ".env", "base de datos 2026.xlsx", "historico_pacientes_2020_2025.csv", "recepcionlauncher.exe" };
        if (protectedPrefixes.Any(low.StartsWith) || protectedExact.Contains(low) ||
            low.EndsWith(".db") || low.EndsWith(".sqlite") || low.EndsWith(".sqlite3") ||
            low.EndsWith(".xlsx"))
            throw new InvalidOperationException("El canal intentó tocar un archivo protegido: " + path);
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


internal sealed class ReceptionForm : Form
{
    readonly string root;
    readonly string url;
    readonly WebView2 web = new();

    public ReceptionForm(string rootPath, string targetUrl)
    {
        root = rootPath;
        url = targetUrl;

        Text = "Recepción de Pacientes";
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;
        MinimumSize = new Size(960, 640);
        BackColor = Color.FromArgb(13, 22, 39);
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
            web.CoreWebView2.NewWindowRequested += (_, e) =>
            {
                try
                {
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
    public string Sha256 { get; set; } = "";
}

internal sealed class BackupEntry
{
    public string Path { get; set; } = "";
    public bool Existed { get; set; }
}

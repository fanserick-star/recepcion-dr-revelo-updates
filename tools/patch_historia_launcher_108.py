from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
program_path = ROOT / "historia-clinica/launcher-v1/HistoriaLauncher/Program.cs"
iss_path = ROOT / "historia-clinica/launcher-v1/installer/LauncherV1.iss"
workflow_path = ROOT / ".github/workflows/build-historia-launcher-v1.yml"


def rep(text: str, old: str, new: str, *, count: int = 1, label: str = "replacement") -> str:
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count}, found {found}")
    return text.replace(old, new, count)

program = program_path.read_text(encoding="utf-8")
program = rep(
    program,
    '    const string LauncherVersion = "1.0.7";\n',
    '    const string LauncherVersion = "1.0.8";\n',
    label="launcher version",
)

program = rep(
    program,
    '''internal sealed class HistoriaForm : Form\n{\n    readonly string root;\n    readonly string url;\n    readonly WebView2 web = new();\n\n    public HistoriaForm(string rootPath, string targetUrl, bool childWindow = false)\n    {\n        root = rootPath;\n        url = targetUrl;\n''',
    '''internal sealed class HistoriaForm : Form\n{\n    readonly string root;\n    readonly string url;\n    readonly bool silentPrint;\n    readonly string printerName;\n    readonly WebView2 web = new();\n    CoreWebView2Environment? environment;\n\n    public HistoriaForm(string rootPath, string targetUrl, bool childWindow = false, bool silentPrint = false, string printerName = "")\n    {\n        root = rootPath;\n        url = targetUrl;\n        this.silentPrint = silentPrint;\n        this.printerName = printerName ?? "";\n''',
    label="HistoriaForm fields and ctor",
)

program = rep(
    program,
    '''        WindowState = childWindow ? FormWindowState.Normal : FormWindowState.Maximized;\n        Size = childWindow ? new Size(1220, 860) : Size;\n        MinimumSize = new Size(960, 640);\n        BackColor = Color.FromArgb(244, 239, 229);\n        ShowInTaskbar = true;\n        ShowIcon = true;\n''',
    '''        WindowState = childWindow ? FormWindowState.Normal : FormWindowState.Maximized;\n        Size = childWindow ? new Size(1220, 860) : Size;\n        MinimumSize = silentPrint ? new Size(1, 1) : new Size(960, 640);\n        BackColor = Color.FromArgb(244, 239, 229);\n        ShowInTaskbar = !silentPrint;\n        ShowIcon = !silentPrint;\n        if (silentPrint)\n        {\n            StartPosition = FormStartPosition.Manual;\n            Location = new Point(-32000, -32000);\n            Size = new Size(24, 24);\n            Opacity = 0;\n            FormBorderStyle = FormBorderStyle.None;\n        }\n''',
    label="silent form ui",
)

program = rep(
    program,
    '''            var env = await CoreWebView2Environment.CreateAsync(\n                browserExecutableFolder: null,\n                userDataFolder: profile);\n\n            await web.EnsureCoreWebView2Async(env);\n\n            web.CoreWebView2.Settings.AreDevToolsEnabled = false;\n''',
    '''            var env = await CoreWebView2Environment.CreateAsync(\n                browserExecutableFolder: null,\n                userDataFolder: profile);\n            environment = env;\n\n            await web.EnsureCoreWebView2Async(env);\n\n            web.CoreWebView2.Settings.AreDevToolsEnabled = false;\n''',
    label="store webview environment",
)

insert = r'''            web.CoreWebView2.WebMessageReceived += async (_, e) =>
            {
                try
                {
                    using var message = JsonDocument.Parse(e.WebMessageAsJson);
                    var rootEl = message.RootElement;
                    if (!rootEl.TryGetProperty("type", out var typeEl) ||
                        !string.Equals(typeEl.GetString(), "historia-print-url", StringComparison.Ordinal))
                        return;

                    var rawUrl = rootEl.TryGetProperty("url", out var urlEl)
                        ? urlEl.GetString() ?? ""
                        : "";
                    var requestedPrinter = rootEl.TryGetProperty("printer", out var printerEl)
                        ? printerEl.GetString() ?? ""
                        : "";

                    Uri target;
                    if (Uri.TryCreate(rawUrl, UriKind.Absolute, out var absolute))
                        target = absolute;
                    else
                        target = new Uri(new Uri("http://127.0.0.1:8787/"), rawUrl.TrimStart('/'));

                    if (!target.Host.Equals("127.0.0.1", StringComparison.OrdinalIgnoreCase) ||
                        target.Port != 8787)
                        throw new InvalidOperationException("La impresión solo admite documentos locales de Historia Clínica.");

                    var printForm = new HistoriaForm(
                        root,
                        target.ToString(),
                        childWindow: true,
                        silentPrint: true,
                        printerName: requestedPrinter);
                    if (!await printForm.InitializeAsync())
                    {
                        printForm.Dispose();
                        throw new InvalidOperationException("No se pudo preparar la impresión nativa.");
                    }
                    printForm.FormClosed += (_, _) => printForm.Dispose();
                    printForm.Show(this);
                }
                catch (Exception ex)
                {
                    MessageBox.Show(
                        "No se pudo imprimir el documento.\n\n" + ex.Message,
                        "Historia Clínica - Impresión",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                }
            };

            if (silentPrint)
            {
                bool printStarted = false;
                web.CoreWebView2.NavigationCompleted += async (_, e) =>
                {
                    if (printStarted) return;
                    printStarted = true;
                    try
                    {
                        if (!e.IsSuccess)
                            throw new InvalidOperationException("No se pudo cargar el documento para imprimir.");

                        await Task.Delay(180);
                        var settings = environment!.CreatePrintSettings();
                        settings.PrinterName = printerName;
                        settings.ShouldPrintBackgrounds = true;
                        settings.ShouldPrintHeaderAndFooter = false;
                        var status = await web.CoreWebView2.PrintAsync(settings);
                        if (status == CoreWebView2PrintStatus.PrinterUnavailable)
                            throw new InvalidOperationException(
                                string.IsNullOrWhiteSpace(printerName)
                                    ? "La impresora predeterminada de Windows no está disponible."
                                    : $"La impresora '{printerName}' no está disponible en esta PC.");
                        if (status != CoreWebView2PrintStatus.Succeeded)
                            throw new InvalidOperationException("Windows no pudo completar la impresión.");
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show(
                            "No se pudo imprimir el documento.\n\n" + ex.Message,
                            "Historia Clínica - Impresión",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error);
                    }
                    finally
                    {
                        try { BeginInvoke(new Action(Close)); } catch { }
                    }
                };
            }
'''
program = rep(
    program,
    '''            web.CoreWebView2.Settings.IsZoomControlEnabled = true;\n            web.CoreWebView2.NewWindowRequested += async (_, e) =>\n''',
    '''            web.CoreWebView2.Settings.IsZoomControlEnabled = true;\n''' + insert + '''            web.CoreWebView2.NewWindowRequested += async (_, e) =>\n''',
    label="native print webmessage handler",
)

program = rep(
    program,
    '''                try\n                {\n                    if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var target) &&\n''',
    '''                try\n                {\n                    if (string.Equals(e.Uri, "about:blank", StringComparison.OrdinalIgnoreCase))\n                    {\n                        e.Handled = true;\n                        return;\n                    }\n\n                    if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var target) &&\n''',
    label="about blank protection",
)

program_path.write_text(program, encoding="utf-8")

iss = iss_path.read_text(encoding="utf-8")
iss = iss.replace('1.0.7', '1.0.8').replace('V1_0_7', 'V1_0_8')
if '1.0.7' in iss or 'V1_0_7' in iss:
    raise RuntimeError('LauncherV1.iss still contains 1.0.7')
iss_path.write_text(iss, encoding="utf-8")

workflow = workflow_path.read_text(encoding="utf-8")
workflow = workflow.replace('1.0.7', '1.0.8').replace('V1_0_7', 'V1_0_8')
workflow = workflow.replace(
    'gh release create $tag --title "Launcher Historia Clínica v1.0.8" --notes "Launcher nativo v1.0.8: corrige de forma definitiva los scripts de preprueba aislada de app.py y conserva WebView2, instancia única, actualización obligatoria, SHA-256 y rollback."',
    'gh release create $tag --title "Launcher Historia Clínica v1.0.8" --notes "Launcher nativo v1.0.8: impresión directa con WebView2 PrintAsync, protección de about:blank, WebView2, instancia única, actualización obligatoria, SHA-256, preprueba y rollback."'
)
channel_step = r'''
      - name: Publish launcher channel 1.0.8
        shell: pwsh
        run: |
          $installer = "historia-clinica/launcher-v1/package/INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe"
          $updater = "historia-clinica/launcher-v1/package/HistoriaLauncherUpdater.exe"
          $installerHash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
          $updaterHash = (Get-FileHash $updater -Algorithm SHA256).Hash.ToLowerInvariant()
          $channel = [ordered]@{
            schema = 2
            product = "historia-launcher-dr-revelo"
            latestVersion = "1.0.8"
            mandatory = $true
            notes = "Launcher Historia 1.0.8: impresión directa nativa de recetas y certificados con WebView2, sin vista previa del navegador; corrige el vínculo about:blank."
            installerUrl = "https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/historia-launcher-v1.0.8/INSTALAR_LAUNCHER_HISTORIA_CLINICA_DR_REVELO_V1_0_8.exe"
            installerSha256 = $installerHash
            updaterUrl = "https://github.com/fanserick-star/recepcion-dr-revelo-updates/releases/download/historia-launcher-v1.0.8/HistoriaLauncherUpdater.exe"
            updaterSha256 = $updaterHash
          }
          $json = $channel | ConvertTo-Json -Depth 4
          Set-Content "historia-clinica/launcher-v1/launcher-channel.json" $json -Encoding utf8
          git config user.name "fanserick-star"
          git config user.email "fanserick@hotmail.com"
          git add historia-clinica/launcher-v1/launcher-channel.json
          git diff --cached --quiet
          if ($LASTEXITCODE -ne 0) {
            git commit -m "Publicar canal Launcher Historia 1.0.8"
            git push origin HEAD:main
          }
'''
marker = '      - name: Upload complete package\n'
if marker not in workflow:
    raise RuntimeError('Upload complete package marker not found')
workflow = workflow.replace(marker, channel_step + '\n' + marker, 1)
workflow_path.write_text(workflow, encoding="utf-8")

print('Launcher 1.0.8 native-print patch applied')

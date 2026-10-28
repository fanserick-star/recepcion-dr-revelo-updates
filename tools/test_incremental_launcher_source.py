"""Contract tests for the two Windows verified-delta launchers.

No patients, cloud calls or installed applications are touched.
The Windows PR build separately compiles both launchers with .NET 8.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("Recepción", ROOT / "launcher-v1/RecepcionLauncher/Program.cs", "1.0.13"),
    ("Historia", ROOT / "historia-clinica/launcher-v1/HistoriaLauncher/Program.cs", "1.0.9"),
]

for product, path, expected in SOURCES:
    text = path.read_text(encoding="utf-8")
    assert f'const string LauncherVersion = "{expected}"' in text, product
    begin = text.index("async Task<string> ApplyUpdateAsync(AppChannel channel)")
    end = text.index("async Task DownloadVerifiedAsync(ChannelFile", begin)
    update = text[begin:end]
    assert 'var downloadedPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);' in update
    assert 'StageOrDownloadVerifiedAsync(f, dst, basePct, nextPct, i + 1, channel.Files.Count)' in update
    assert 'await PrecheckCandidateAsync(staging, channel.AppVersion)' in update
    assert 'await StopBackendIfOursAsync()' in update
    assert 'foreach (var f in channel.Files)' in update, "All signed files must be staged"
    assert 'var filesToApply = channel.Files.Where(f => downloadedPaths.Contains(f.Path)).ToList();' in update
    assert update.count('foreach (var f in filesToApply)') == 2, (product, "backup and install only changed")
    assert 'foreach (var f in channel.Files)\n            {\n                var rel = f.Path.Replace' not in update, product
    assert 'await RollbackAsync(backup)' in update
    assert 'Math.Max(1, filesToApply.Count)' in update
    assert 'try\n        {' in update

    stage = update[update.index('async Task<bool> StageOrDownloadVerifiedAsync'): ]
    assert 'File.Exists(installed)' in stage
    assert stage.count('await Sha256Async(') >= 2, "Hash original and copied staging"
    assert '(await Sha256Async(installed)).Equals(f.Sha256, StringComparison.OrdinalIgnoreCase)' in stage
    assert '(await Sha256Async(dst)).Equals(f.Sha256, StringComparison.OrdinalIgnoreCase)' in stage
    assert 'File.Copy(installed, dst, true)' in stage
    assert 'catch (IOException)' in stage
    assert 'catch (UnauthorizedAccessException)' in stage
    assert 'await DownloadVerifiedAsync(f, dst, startPct, endPct, index, total)' in stage
    assert 'return true;' in stage and 'return false;' in stage

    download = text[text.index('async Task DownloadVerifiedAsync(ChannelFile'): ]
    assert 'await Sha256Async(dst)' in download
    assert 'f.Sha256' in download
    assert "EnsureSafeUpdatePath(f.Path)" in update
    assert 'update_backups' in update
    assert "Directory.CreateDirectory(staging)" in update
    assert 'File.Move(temp, dest, true)' in update
    assert 'PrecheckCandidateAsync' in update

    folder = path.parent.parent
    installer = (folder / "installer/LauncherV1.iss").read_text(encoding="utf-8")
    assert f'#define MyAppVersion "{expected}"' in installer
    suffix="_".join(expected.split("."))
    assert "V"+suffix in installer
    print(f"{product}: verificación SHA-256, stage completo, delta y rollback OK")

reception_workflow = (ROOT / ".github/workflows/build-reception-launcher-v1.yml").read_text(encoding="utf-8")
historia_workflow = (ROOT / ".github/workflows/build-historia-launcher-v1.yml").read_text(encoding="utf-8")
for text, name, version in [(reception_workflow, "Recepción", "1.0.13"), (historia_workflow, "Historia", "1.0.9")]:
    assert "if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'" in text
    assert "if: github.event_name == 'pull_request'" in text
    assert "dotnet build" in text
    assert "tools/test_incremental_launcher_source.py" in text
    assert f'latestVersion = "{version}"' in text
    assert "Get-FileHash $installer -Algorithm SHA256" in text
    assert "Get-FileHash $updater -Algorithm SHA256" in text
    assert "git rebase origin/main" in text
    assert "gh release upload" in text
    print(f"{name}: control de publicación segura y hash del autoactualizador OK")
print("INCREMENTAL_LAUNCHERS_CONTRACT_OK")

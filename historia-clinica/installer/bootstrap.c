#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <shellapi.h>
#include <stdint.h>
#include <stdio.h>
#include <wchar.h>

static const char MARKER[16] = {'H','C','R','E','V','E','L','O','P','A','Y','L','O','A','D','1'};

typedef struct Footer {
    char marker[16];
    uint64_t payload_size;
} Footer;

static void msg(const wchar_t *text, UINT flags) {
    MessageBoxW(NULL, text, L"Historia Clinica - Dr. Armando Revelo", flags | MB_OK);
}

static int file_exists(const wchar_t *p) {
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static int dir_exists(const wchar_t *p) {
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}

static int run_wait(const wchar_t *exe, wchar_t *cmdline, const wchar_t *cwd, DWORD show, DWORD *exit_code) {
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si)); ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si); si.dwFlags = STARTF_USESHOWWINDOW; si.wShowWindow = (WORD)show;
    if (!CreateProcessW(exe, cmdline, NULL, NULL, FALSE, CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW, NULL, cwd, &si, &pi)) return 0;
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1; GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    if (exit_code) *exit_code = code;
    return 1;
}

static int extract_payload(const wchar_t *self, const wchar_t *zipPath) {
    FILE *f = _wfopen(self, L"rb"); if (!f) return 0;
    _fseeki64(f, 0, SEEK_END); __int64 total = _ftelli64(f);
    if (total < (int)sizeof(Footer)) { fclose(f); return 0; }
    _fseeki64(f, total - sizeof(Footer), SEEK_SET);
    Footer foot; if (fread(&foot, 1, sizeof(foot), f) != sizeof(foot)) { fclose(f); return 0; }
    if (memcmp(foot.marker, MARKER, 16) != 0 || foot.payload_size == 0 || foot.payload_size > (uint64_t)total) { fclose(f); return 0; }
    __int64 start = total - sizeof(Footer) - (__int64)foot.payload_size;
    if (start < 0) { fclose(f); return 0; }
    _fseeki64(f, start, SEEK_SET);
    FILE *o = _wfopen(zipPath, L"wb"); if (!o) { fclose(f); return 0; }
    char buf[1 << 16]; uint64_t left = foot.payload_size;
    while (left) {
        size_t want = left > sizeof(buf) ? sizeof(buf) : (size_t)left;
        size_t n = fread(buf, 1, want, f); if (!n) { fclose(o); fclose(f); return 0; }
        if (fwrite(buf, 1, n, o) != n) { fclose(o); fclose(f); return 0; }
        left -= n;
    }
    fclose(o); fclose(f); return 1;
}

static int ps_wait(const wchar_t *script, DWORD *code) {
    wchar_t *cmd = (wchar_t*)calloc(1, (wcslen(script) + 128) * sizeof(wchar_t));
    if (!cmd) return 0;
    swprintf(cmd, wcslen(script) + 120, L"powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"%ls\"", script);
    int ok = run_wait(NULL, cmd, NULL, SW_HIDE, code);
    free(cmd); return ok;
}

int WINAPI wWinMain(HINSTANCE h, HINSTANCE p, PWSTR cmdLine, int show) {
    (void)h; (void)p; (void)cmdLine; (void)show;
    wchar_t self[MAX_PATH * 4]; if (!GetModuleFileNameW(NULL, self, ARRAYSIZE(self))) { msg(L"No se pudo localizar el instalador.", MB_ICONERROR); return 2; }

    wchar_t temp[MAX_PATH * 4]; GetTempPathW(ARRAYSIZE(temp), temp);
    wchar_t zipPath[MAX_PATH * 4], stage[MAX_PATH * 4];
    swprintf(zipPath, ARRAYSIZE(zipPath), L"%lsHC_Revelo_%lu.zip", temp, GetCurrentProcessId());
    swprintf(stage, ARRAYSIZE(stage), L"%lsHC_Revelo_%lu", temp, GetCurrentProcessId());
    CreateDirectoryW(stage, NULL);

    if (!extract_payload(self, zipPath)) { msg(L"El instalador esta incompleto o danado. Vuelve a descargarlo.", MB_ICONERROR); return 3; }

    wchar_t localApp[MAX_PATH * 4];
    if (FAILED(SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, SHGFP_TYPE_CURRENT, localApp))) { msg(L"No se pudo localizar AppData.", MB_ICONERROR); return 4; }
    wchar_t dest[MAX_PATH * 4]; swprintf(dest, ARRAYSIZE(dest), L"%ls\\HistoriaClinicaDrRevelo", localApp);

    wchar_t ps[16384];
    swprintf(ps, ARRAYSIZE(ps),
        L"$ErrorActionPreference='Stop'; "
        L"$zip='%ls'; $stage='%ls'; $dest='%ls'; "
        L"if(Test-Path $stage){Remove-Item -LiteralPath $stage -Recurse -Force}; New-Item -ItemType Directory -Path $stage -Force|Out-Null; "
        L"Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force; "
        L"New-Item -ItemType Directory -Path $dest -Force|Out-Null; "
        L"Get-ChildItem -LiteralPath $stage -Force | ForEach-Object { "
        L"  $target=Join-Path $dest $_.Name; "
        L"  if(($_.Name -eq 'data' -or $_.Name -eq '.env') -and (Test-Path -LiteralPath $target)){ } "
        L"  else { Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force } "
        L"};",
        zipPath, stage, dest);
    DWORD code=1;
    if (!ps_wait(ps, &code) || code != 0) { msg(L"No se pudieron copiar los archivos de Historia Clinica.", MB_ICONERROR); return 5; }

    // Garantiza Python 3.12 en modo usuario. Solo se descarga si no existe.
    wchar_t py[MAX_PATH * 4]; swprintf(py, ARRAYSIZE(py), L"%ls\\Programs\\Python\\Python312\\python.exe", localApp);
    if (!file_exists(py)) {
        wchar_t pyInstaller[MAX_PATH * 4]; swprintf(pyInstaller, ARRAYSIZE(pyInstaller), L"%ls\\python-3.12.10-amd64.exe", stage);
        swprintf(ps, ARRAYSIZE(ps),
            L"$ErrorActionPreference='Stop'; $out='%ls'; "
            L"Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $out; "
            L"$p=Start-Process -FilePath $out -ArgumentList '/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 Include_pip=1 Include_test=0 SimpleInstall=1' -Wait -PassThru; exit $p.ExitCode;",
            pyInstaller);
        if (!ps_wait(ps, &code) || code != 0 || !file_exists(py)) {
            msg(L"No se pudo instalar Python automaticamente. Comprueba que la PC tenga Internet y vuelve a ejecutar el instalador.", MB_ICONERROR); return 6;
        }
    }

    wchar_t launcher[MAX_PATH * 4]; swprintf(launcher, ARRAYSIZE(launcher), L"%ls\\ABRIR_HISTORIA_CLINICA.py", dest);
    wchar_t prepCmd[8192]; swprintf(prepCmd, ARRAYSIZE(prepCmd), L"\"%ls\" \"%ls\" --prepare", py, launcher);
    if (!run_wait(NULL, prepCmd, dest, SW_HIDE, &code) || code != 0) {
        msg(L"Los archivos se instalaron, pero no se pudieron preparar las dependencias. Comprueba Internet y vuelve a ejecutar el instalador.", MB_ICONERROR); return 7;
    }

    // Crea acceso directo en el escritorio apuntando al Python sin consola del venv.
    wchar_t desktop[MAX_PATH * 4];
    SHGetFolderPathW(NULL, CSIDL_DESKTOPDIRECTORY, NULL, SHGFP_TYPE_CURRENT, desktop);
    wchar_t venvPyw[MAX_PATH * 4], icon[MAX_PATH * 4], lnk[MAX_PATH * 4];
    swprintf(venvPyw, ARRAYSIZE(venvPyw), L"%ls\\.venv\\Scripts\\pythonw.exe", dest);
    swprintf(icon, ARRAYSIZE(icon), L"%ls\\static\\doctor_icon.ico", dest);
    swprintf(lnk, ARRAYSIZE(lnk), L"%ls\\Historia Clinica - Dr. Armando Revelo.lnk", desktop);
    swprintf(ps, ARRAYSIZE(ps),
        L"$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%ls'); $s.TargetPath='%ls'; $s.Arguments='\"%ls\"'; $s.WorkingDirectory='%ls'; $s.IconLocation='%ls,0'; $s.Description='Historia Clinica - Dr. Armando Revelo'; $s.Save();",
        lnk, venvPyw, launcher, dest, icon);
    ps_wait(ps, &code);

    // Limpieza temporal.
    DeleteFileW(zipPath);
    swprintf(ps, ARRAYSIZE(ps), L"if(Test-Path -LiteralPath '%ls'){Remove-Item -LiteralPath '%ls' -Recurse -Force -ErrorAction SilentlyContinue}", stage, stage);
    ps_wait(ps, &code);

    msg(L"Historia Clinica quedo instalada. Se creo el acceso directo en el Escritorio.\n\nLa primera sincronizacion con la nube puede continuar en segundo plano.", MB_ICONINFORMATION);

    if (file_exists(venvPyw)) {
        wchar_t runCmd[8192]; swprintf(runCmd, ARRAYSIZE(runCmd), L"\"%ls\" \"%ls\"", venvPyw, launcher);
        STARTUPINFOW si; PROCESS_INFORMATION pi; ZeroMemory(&si,sizeof(si)); ZeroMemory(&pi,sizeof(pi)); si.cb=sizeof(si); si.dwFlags=STARTF_USESHOWWINDOW; si.wShowWindow=SW_HIDE;
        if(CreateProcessW(NULL, runCmd, NULL,NULL,FALSE,CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW,NULL,dest,&si,&pi)){ CloseHandle(pi.hThread); CloseHandle(pi.hProcess); }
    }
    return 0;
}
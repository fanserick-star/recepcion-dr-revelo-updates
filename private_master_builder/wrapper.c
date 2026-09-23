#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <stdint.h>
#include <stdio.h>

#define RES_SETUP 101
#define MAGIC "DRREVELOENV1"
#define MAGIC_LEN 12
#define FOOTER_LEN (8 + MAGIC_LEN)

static void failmsg(const wchar_t *msg) {
    MessageBoxW(NULL, msg, L"Instalador Maestro - Dr. Revelo", MB_ICONERROR | MB_OK);
}

static int write_file(const wchar_t *path, const void *data, DWORD size) {
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    DWORD written = 0;
    BOOL ok = WriteFile(h, data, size, &written, NULL);
    CloseHandle(h);
    return ok && written == size;
}

static int extract_setup(const wchar_t *path) {
    HRSRC r = FindResourceW(NULL, MAKEINTRESOURCEW(RES_SETUP), RT_RCDATA);
    if (!r) return 0;
    HGLOBAL hg = LoadResource(NULL, r);
    if (!hg) return 0;
    DWORD sz = SizeofResource(NULL, r);
    void *p = LockResource(hg);
    if (!p || !sz) return 0;
    return write_file(path, p, sz);
}

static int read_private_env(unsigned char **out, DWORD *outlen) {
    wchar_t self[MAX_PATH * 4];
    DWORD n = GetModuleFileNameW(NULL, self, ARRAYSIZE(self));
    if (!n || n >= ARRAYSIZE(self)) return 0;

    HANDLE h = CreateFileW(self, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;

    LARGE_INTEGER size;
    if (!GetFileSizeEx(h, &size) || size.QuadPart < FOOTER_LEN) {
        CloseHandle(h); return 0;
    }

    LARGE_INTEGER pos;
    pos.QuadPart = size.QuadPart - FOOTER_LEN;
    if (!SetFilePointerEx(h, pos, NULL, FILE_BEGIN)) {
        CloseHandle(h); return 0;
    }

    unsigned char footer[FOOTER_LEN];
    DWORD got = 0;
    if (!ReadFile(h, footer, FOOTER_LEN, &got, NULL) || got != FOOTER_LEN) {
        CloseHandle(h); return 0;
    }

    if (memcmp(footer + 8, MAGIC, MAGIC_LEN) != 0) {
        CloseHandle(h); return 0;
    }

    uint64_t len = 0;
    memcpy(&len, footer, 8);
    if (!len || len > 1024 * 1024 || (uint64_t)size.QuadPart < len + FOOTER_LEN) {
        CloseHandle(h); return 0;
    }

    pos.QuadPart = size.QuadPart - FOOTER_LEN - (LONGLONG)len;
    if (!SetFilePointerEx(h, pos, NULL, FILE_BEGIN)) {
        CloseHandle(h); return 0;
    }

    unsigned char *buf = (unsigned char*)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (SIZE_T)len);
    if (!buf) { CloseHandle(h); return 0; }

    got = 0;
    BOOL ok = ReadFile(h, buf, (DWORD)len, &got, NULL);
    CloseHandle(h);
    if (!ok || got != (DWORD)len) {
        SecureZeroMemory(buf, (SIZE_T)len);
        HeapFree(GetProcessHeap(), 0, buf);
        return 0;
    }

    *out = buf;
    *outlen = (DWORD)len;
    return 1;
}

static void append_arg(wchar_t *dst, size_t cap, const wchar_t *arg) {
    if (wcslen(dst) + wcslen(arg) + 4 >= cap) return;
    wcscat_s(dst, cap, L" \"");
    for (const wchar_t *p = arg; *p; ++p) {
        if (*p == L'"') wcscat_s(dst, cap, L"\\\"");
        else {
            wchar_t one[2] = {*p, 0};
            wcscat_s(dst, cap, one);
        }
    }
    wcscat_s(dst, cap, L"\"");
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmd, int show) {
    (void)hInst; (void)hPrev; (void)cmd; (void)show;

    unsigned char *envData = NULL;
    DWORD envLen = 0;
    if (!read_private_env(&envData, &envLen)) {
        failmsg(L"Este archivo no contiene la configuración privada del consultorio.");
        return 2;
    }

    wchar_t temp[MAX_PATH], dir[MAX_PATH], setup[MAX_PATH], envPath[MAX_PATH];
    if (!GetTempPathW(ARRAYSIZE(temp), temp)) {
        SecureZeroMemory(envData, envLen); HeapFree(GetProcessHeap(), 0, envData);
        failmsg(L"No se pudo preparar la carpeta temporal.");
        return 3;
    }

    swprintf_s(dir, ARRAYSIZE(dir), L"%sDrReveloMaster_%lu", temp, GetCurrentProcessId());
    CreateDirectoryW(dir, NULL);
    swprintf_s(setup, ARRAYSIZE(setup), L"%s\\setup.exe", dir);
    swprintf_s(envPath, ARRAYSIZE(envPath), L"%s\\private.env", dir);

    if (!extract_setup(setup) || !write_file(envPath, envData, envLen)) {
        SecureZeroMemory(envData, envLen); HeapFree(GetProcessHeap(), 0, envData);
        DeleteFileW(envPath); DeleteFileW(setup); RemoveDirectoryW(dir);
        failmsg(L"No se pudo preparar el instalador interno.");
        return 4;
    }

    SecureZeroMemory(envData, envLen);
    HeapFree(GetProcessHeap(), 0, envData);

    int argc = 0;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    wchar_t params[32768] = L"";
    if (argv) {
        for (int i = 1; i < argc; ++i) append_arg(params, ARRAYSIZE(params), argv[i]);
        LocalFree(argv);
    }

    wchar_t privateArg[MAX_PATH * 2];
    swprintf_s(privateArg, ARRAYSIZE(privateArg), L"/PRIVATEENV=%s", envPath);
    append_arg(params, ARRAYSIZE(params), privateArg);

    SHELLEXECUTEINFOW se;
    ZeroMemory(&se, sizeof(se));
    se.cbSize = sizeof(se);
    se.fMask = SEE_MASK_NOCLOSEPROCESS;
    se.lpVerb = L"runas";
    se.lpFile = setup;
    se.lpParameters = params;
    se.lpDirectory = dir;
    se.nShow = SW_SHOWNORMAL;

    if (!ShellExecuteExW(&se)) {
        DWORD err = GetLastError();
        DeleteFileW(envPath); DeleteFileW(setup); RemoveDirectoryW(dir);
        if (err != ERROR_CANCELLED) failmsg(L"No se pudo iniciar el instalador con permisos de administrador.");
        return (err == ERROR_CANCELLED) ? 5 : 6;
    }

    WaitForSingleObject(se.hProcess, INFINITE);
    DWORD exitCode = 1;
    GetExitCodeProcess(se.hProcess, &exitCode);
    CloseHandle(se.hProcess);

    DeleteFileW(envPath);
    DeleteFileW(setup);
    RemoveDirectoryW(dir);
    return (int)exitCode;
}

#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <commctrl.h>
#include <bcrypt.h>
#include <wincrypt.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "bootstrap_ps.h"

#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "crypt32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "comctl32.lib")

#define APP_TITLE L"Consultorio Dr. Armando Revelo"
#define ENV_NAME_A "DR_REVELO_PRIVATE_CONFIG_B64"
#define MAX_CFG_SIZE (64u * 1024u)

/* Patched after CI compilation. The final key is never committed to GitHub. */
volatile unsigned char g_master_key[64] = {
  0x19,0x6f,0x31,0xad,0x9f,0x13,0x31,0x62,0x09,0xce,0x97,0x72,0xd6,0xa8,0x7a,0xde,
  0xee,0x4b,0x61,0xb4,0x25,0x18,0x0b,0x79,0x6d,0x21,0x43,0x6b,0x32,0x51,0x38,0x57,
  0xe3,0xee,0xda,0xba,0x6f,0xb9,0x1b,0x43,0x3c,0x0c,0xe6,0x35,0xd5,0x23,0x25,0xd5,
  0x91,0x43,0x98,0xdf,0x0e,0x42,0x96,0x5f,0xb9,0x3a,0x54,0x20,0x56,0x10,0xbd,0x9b
};

#pragma pack(push,1)
typedef struct {
    unsigned char magic[16];
    uint32_t version;
    uint32_t payload_len;
    unsigned char nonce[16];
    unsigned char mac[32];
} ConfigFooter;
#pragma pack(pop)

static const unsigned char FOOTER_MAGIC[16] = {
    'D','R','R','V','2','C','F','G','F','O','O','T','E','R','!','!'
};

static void show_error(const wchar_t *msg) {
    MessageBoxW(NULL, msg, APP_TITLE, MB_OK | MB_ICONERROR | MB_TOPMOST);
}

static int is_elevated(void) {
    HANDLE token = NULL;
    TOKEN_ELEVATION elev;
    DWORD size = 0;
    int result = 0;
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) {
        if (GetTokenInformation(token, TokenElevation, &elev, sizeof(elev), &size)) {
            result = elev.TokenIsElevated ? 1 : 0;
        }
        CloseHandle(token);
    }
    return result;
}

static int relaunch_elevated(void) {
    wchar_t self[MAX_PATH * 4];
    if (!GetModuleFileNameW(NULL, self, (DWORD)(sizeof(self)/sizeof(self[0])))) return 0;
    HINSTANCE r = ShellExecuteW(NULL, L"runas", self, L"--elevated", NULL, SW_SHOWNORMAL);
    return ((INT_PTR)r > 32);
}

static NTSTATUS hash_sha256(const unsigned char *data, DWORD data_len, unsigned char out[32]) {
    BCRYPT_ALG_HANDLE alg = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    PUCHAR obj = NULL;
    DWORD obj_len = 0, cb = 0;
    NTSTATUS st = BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, NULL, 0);
    if (st < 0) goto done;
    st = BCryptGetProperty(alg, BCRYPT_OBJECT_LENGTH, (PUCHAR)&obj_len, sizeof(obj_len), &cb, 0);
    if (st < 0) goto done;
    obj = (PUCHAR)HeapAlloc(GetProcessHeap(), 0, obj_len);
    if (!obj) { st = (NTSTATUS)0xC0000017L; goto done; }
    st = BCryptCreateHash(alg, &hash, obj, obj_len, NULL, 0, 0);
    if (st < 0) goto done;
    st = BCryptHashData(hash, (PUCHAR)data, data_len, 0);
    if (st < 0) goto done;
    st = BCryptFinishHash(hash, out, 32, 0);
done:
    if (hash) BCryptDestroyHash(hash);
    if (obj) HeapFree(GetProcessHeap(), 0, obj);
    if (alg) BCryptCloseAlgorithmProvider(alg, 0);
    return st;
}

static NTSTATUS hmac_sha256(const unsigned char *key, DWORD key_len,
                            const unsigned char *data, DWORD data_len,
                            unsigned char out[32]) {
    BCRYPT_ALG_HANDLE alg = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    PUCHAR obj = NULL;
    DWORD obj_len = 0, cb = 0;
    NTSTATUS st = BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, NULL, BCRYPT_ALG_HANDLE_HMAC_FLAG);
    if (st < 0) goto done;
    st = BCryptGetProperty(alg, BCRYPT_OBJECT_LENGTH, (PUCHAR)&obj_len, sizeof(obj_len), &cb, 0);
    if (st < 0) goto done;
    obj = (PUCHAR)HeapAlloc(GetProcessHeap(), 0, obj_len);
    if (!obj) { st = (NTSTATUS)0xC0000017L; goto done; }
    st = BCryptCreateHash(alg, &hash, obj, obj_len, (PUCHAR)key, key_len, 0);
    if (st < 0) goto done;
    st = BCryptHashData(hash, (PUCHAR)data, data_len, 0);
    if (st < 0) goto done;
    st = BCryptFinishHash(hash, out, 32, 0);
done:
    if (hash) BCryptDestroyHash(hash);
    if (obj) HeapFree(GetProcessHeap(), 0, obj);
    if (alg) BCryptCloseAlgorithmProvider(alg, 0);
    return st;
}

static int secure_equal(const unsigned char *a, const unsigned char *b, size_t n) {
    unsigned char d = 0;
    size_t i;
    for (i = 0; i < n; ++i) d |= (unsigned char)(a[i] ^ b[i]);
    return d == 0;
}

static int decrypt_payload(const unsigned char *cipher, uint32_t len,
                           const ConfigFooter *ft, unsigned char **plain_out) {
    unsigned char mac_calc[32];
    unsigned char *mac_input = NULL;
    unsigned char *plain = NULL;
    unsigned char block_in[32 + 16 + 4];
    unsigned char digest[32];
    uint32_t counter = 0, pos = 0;
    size_t mac_len = 8u + 16u + (size_t)len;
    unsigned char enc_key[32], mac_key[32];
    size_t i;

    for (i = 0; i < 32; ++i) enc_key[i] = g_master_key[i];
    for (i = 0; i < 32; ++i) mac_key[i] = g_master_key[32 + i];

    mac_input = (unsigned char*)HeapAlloc(GetProcessHeap(), 0, mac_len);
    plain = (unsigned char*)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (size_t)len + 1u);
    if (!mac_input || !plain) goto fail;

    mac_input[0] = (unsigned char)(ft->version & 0xff);
    mac_input[1] = (unsigned char)((ft->version >> 8) & 0xff);
    mac_input[2] = (unsigned char)((ft->version >> 16) & 0xff);
    mac_input[3] = (unsigned char)((ft->version >> 24) & 0xff);
    mac_input[4] = (unsigned char)(ft->payload_len & 0xff);
    mac_input[5] = (unsigned char)((ft->payload_len >> 8) & 0xff);
    mac_input[6] = (unsigned char)((ft->payload_len >> 16) & 0xff);
    mac_input[7] = (unsigned char)((ft->payload_len >> 24) & 0xff);
    memcpy(mac_input + 8, ft->nonce, 16);
    memcpy(mac_input + 24, cipher, len);

    if (hmac_sha256(mac_key, 32, mac_input, (DWORD)mac_len, mac_calc) < 0) goto fail;
    if (!secure_equal(mac_calc, ft->mac, 32)) goto fail;

    while (pos < len) {
        memcpy(block_in, enc_key, 32);
        memcpy(block_in + 32, ft->nonce, 16);
        block_in[48] = (unsigned char)(counter & 0xff);
        block_in[49] = (unsigned char)((counter >> 8) & 0xff);
        block_in[50] = (unsigned char)((counter >> 16) & 0xff);
        block_in[51] = (unsigned char)((counter >> 24) & 0xff);
        if (hash_sha256(block_in, sizeof(block_in), digest) < 0) goto fail;
        for (i = 0; i < 32 && pos < len; ++i, ++pos) plain[pos] = (unsigned char)(cipher[pos] ^ digest[i]);
        counter++;
    }

    if (len < 20 || memcmp(plain, "DR_REVELO_CONFIG_V2\n", 20) != 0) goto fail;
    *plain_out = plain;
    SecureZeroMemory(enc_key, sizeof(enc_key));
    SecureZeroMemory(mac_key, sizeof(mac_key));
    SecureZeroMemory(block_in, sizeof(block_in));
    SecureZeroMemory(digest, sizeof(digest));
    SecureZeroMemory(mac_calc, sizeof(mac_calc));
    HeapFree(GetProcessHeap(), 0, mac_input);
    return 1;

fail:
    SecureZeroMemory(enc_key, sizeof(enc_key));
    SecureZeroMemory(mac_key, sizeof(mac_key));
    SecureZeroMemory(block_in, sizeof(block_in));
    SecureZeroMemory(digest, sizeof(digest));
    SecureZeroMemory(mac_calc, sizeof(mac_calc));
    if (mac_input) { SecureZeroMemory(mac_input, mac_len); HeapFree(GetProcessHeap(), 0, mac_input); }
    if (plain) { SecureZeroMemory(plain, (size_t)len + 1u); HeapFree(GetProcessHeap(), 0, plain); }
    return 0;
}

static int read_private_payload(unsigned char **plain_out, uint32_t *plain_len) {
    wchar_t self[MAX_PATH * 4];
    HANDLE f = INVALID_HANDLE_VALUE;
    LARGE_INTEGER size, pos;
    ConfigFooter ft;
    DWORD got = 0;
    unsigned char *cipher = NULL;
    int ok = 0;

    if (!GetModuleFileNameW(NULL, self, (DWORD)(sizeof(self)/sizeof(self[0])))) return 0;
    f = CreateFileW(self, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) goto done;
    if (!GetFileSizeEx(f, &size)) goto done;
    if (size.QuadPart < (LONGLONG)sizeof(ft)) goto done;
    pos.QuadPart = size.QuadPart - (LONGLONG)sizeof(ft);
    if (!SetFilePointerEx(f, pos, NULL, FILE_BEGIN)) goto done;
    if (!ReadFile(f, &ft, sizeof(ft), &got, NULL) || got != sizeof(ft)) goto done;
    if (memcmp(ft.magic, FOOTER_MAGIC, 16) != 0 || ft.version != 2 || ft.payload_len == 0 || ft.payload_len > MAX_CFG_SIZE) goto done;
    if (size.QuadPart < (LONGLONG)sizeof(ft) + (LONGLONG)ft.payload_len) goto done;
    pos.QuadPart = size.QuadPart - (LONGLONG)sizeof(ft) - (LONGLONG)ft.payload_len;
    if (!SetFilePointerEx(f, pos, NULL, FILE_BEGIN)) goto done;
    cipher = (unsigned char*)HeapAlloc(GetProcessHeap(), 0, ft.payload_len);
    if (!cipher) goto done;
    if (!ReadFile(f, cipher, ft.payload_len, &got, NULL) || got != ft.payload_len) goto done;
    if (!decrypt_payload(cipher, ft.payload_len, &ft, plain_out)) goto done;
    *plain_len = ft.payload_len;
    ok = 1;
done:
    if (cipher) { SecureZeroMemory(cipher, ft.payload_len); HeapFree(GetProcessHeap(), 0, cipher); }
    if (f != INVALID_HANDLE_VALUE) CloseHandle(f);
    SecureZeroMemory(&ft, sizeof(ft));
    return ok;
}

static char *base64_encode(const unsigned char *data, DWORD len) {
    DWORD needed = 0;
    char *out = NULL;
    if (!CryptBinaryToStringA(data, len, CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, NULL, &needed)) return NULL;
    out = (char*)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, needed + 1u);
    if (!out) return NULL;
    if (!CryptBinaryToStringA(data, len, CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, out, &needed)) {
        HeapFree(GetProcessHeap(), 0, out); return NULL;
    }
    return out;
}

static int write_bootstrap_script(wchar_t *path, size_t path_chars) {
    wchar_t tmp[MAX_PATH * 4];
    wchar_t dir[MAX_PATH * 4];
    HANDLE f;
    DWORD written = 0;
    DWORD pid = GetCurrentProcessId();
    if (!GetTempPathW((DWORD)(sizeof(tmp)/sizeof(tmp[0])), tmp)) return 0;
    _snwprintf(dir, sizeof(dir)/sizeof(dir[0]), L"%lsDrReveloSetup", tmp);
    CreateDirectoryW(dir, NULL);
    _snwprintf(path, path_chars, L"%ls\\bootstrap-%lu.ps1", dir, (unsigned long)pid);
    f = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_TEMPORARY, NULL);
    if (f == INVALID_HANDLE_VALUE) return 0;
    if (!WriteFile(f, bootstrap_ps1, (DWORD)bootstrap_ps1_len, &written, NULL) || written != (DWORD)bootstrap_ps1_len) {
        CloseHandle(f); DeleteFileW(path); return 0;
    }
    FlushFileBuffers(f);
    CloseHandle(f);
    return 1;
}

static int choose_mode(void) {
    int r = MessageBoxW(NULL,
        L"¿Qué deseas preparar en esta PC?\n\n"
        L"Sí  = Recepción + Historia Clínica\n"
        L"No = instalar solo uno\n"
        L"Cancelar = salir",
        APP_TITLE, MB_YESNOCANCEL | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND);
    if (r == IDYES) return 3;
    if (r != IDNO) return 0;
    r = MessageBoxW(NULL,
        L"Elige el programa individual:\n\n"
        L"Sí = Recepción\n"
        L"No = Historia Clínica\n"
        L"Cancelar = salir",
        APP_TITLE, MB_YESNOCANCEL | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND);
    if (r == IDYES) return 1;
    if (r == IDNO) return 2;
    return 0;
}

static LRESULT CALLBACK status_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_CLOSE) return 0;
    return DefWindowProcW(hwnd, msg, wp, lp);
}

static HWND create_status_window(HWND *progress_out) {
    WNDCLASSW wc;
    HWND hwnd, label, progress;
    HINSTANCE inst = GetModuleHandleW(NULL);
    INITCOMMONCONTROLSEX ic = { sizeof(ic), ICC_PROGRESS_CLASS };
    InitCommonControlsEx(&ic);
    ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc = status_proc;
    wc.hInstance = inst;
    wc.hCursor = LoadCursor(NULL, IDC_WAIT);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"DrReveloInstallStatus";
    RegisterClassW(&wc);
    hwnd = CreateWindowExW(WS_EX_TOPMOST | WS_EX_DLGMODALFRAME, wc.lpszClassName, APP_TITLE,
                           WS_CAPTION | WS_VISIBLE, CW_USEDEFAULT, CW_USEDEFAULT, 520, 170,
                           NULL, NULL, inst, NULL);
    if (!hwnd) return NULL;
    label = CreateWindowW(L"STATIC",
        L"Preparando el consultorio…\nDescargando y verificando componentes. No cierres esta ventana.",
        WS_CHILD | WS_VISIBLE | SS_CENTER, 25, 25, 455, 52, hwnd, NULL, inst, NULL);
    SendMessageW(label, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
    progress = CreateWindowExW(0, PROGRESS_CLASSW, NULL, WS_CHILD | WS_VISIBLE | PBS_MARQUEE,
                               45, 92, 415, 20, hwnd, NULL, inst, NULL);
    SendMessageW(progress, PBM_SETMARQUEE, TRUE, 35);
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    *progress_out = progress;
    return hwnd;
}

static int run_bootstrap(int mode, const char *cfg_b64, DWORD *exit_code) {
    wchar_t script[MAX_PATH * 4];
    wchar_t ps[MAX_PATH * 4];
    wchar_t cmd[8192];
    wchar_t win[MAX_PATH * 4];
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    BOOL ok;
    HWND progress = NULL, status = NULL;
    MSG msg;

    if (!SetEnvironmentVariableA(ENV_NAME_A, cfg_b64)) return 0;
    if (!write_bootstrap_script(script, sizeof(script)/sizeof(script[0]))) {
        SetEnvironmentVariableA(ENV_NAME_A, NULL); return 0;
    }
    if (!GetWindowsDirectoryW(win, (UINT)(sizeof(win)/sizeof(win[0])))) {
        DeleteFileW(script); SetEnvironmentVariableA(ENV_NAME_A, NULL); return 0;
    }
    _snwprintf(ps, sizeof(ps)/sizeof(ps[0]), L"%ls\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", win);
    if (mode == 1)
        _snwprintf(cmd, sizeof(cmd)/sizeof(cmd[0]), L"\"%ls\" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%ls\" -Reception", ps, script);
    else if (mode == 2)
        _snwprintf(cmd, sizeof(cmd)/sizeof(cmd[0]), L"\"%ls\" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%ls\" -Historia", ps, script);
    else
        _snwprintf(cmd, sizeof(cmd)/sizeof(cmd[0]), L"\"%ls\" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%ls\" -Reception -Historia", ps, script);

    ZeroMemory(&si, sizeof(si)); ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si); si.dwFlags = STARTF_USESHOWWINDOW; si.wShowWindow = SW_HIDE;
    ok = CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
                        NULL, NULL, &si, &pi);
    SetEnvironmentVariableA(ENV_NAME_A, NULL);
    if (!ok) { DeleteFileW(script); return 0; }

    status = create_status_window(&progress);
    for (;;) {
        DWORD w = MsgWaitForMultipleObjects(1, &pi.hProcess, FALSE, 150, QS_ALLINPUT);
        while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg); DispatchMessageW(&msg);
        }
        if (w == WAIT_OBJECT_0) break;
    }
    if (!GetExitCodeProcess(pi.hProcess, exit_code)) *exit_code = 1;
    if (status) DestroyWindow(status);
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    DeleteFileW(script);
    return 1;
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmdLine, int show) {
    unsigned char *plain = NULL;
    uint32_t plain_len = 0;
    char *b64 = NULL;
    int mode;
    DWORD exit_code = 1;
    (void)hInst; (void)hPrev; (void)cmdLine; (void)show;

    if (!is_elevated()) {
        if (!relaunch_elevated()) show_error(L"Windows no concedió permisos de administrador. La instalación no se modificó.");
        return 0;
    }

    if (!read_private_payload(&plain, &plain_len)) {
        show_error(L"Este instalador está incompleto o su configuración privada fue alterada. Vuelve a descargar el archivo original.");
        return 2;
    }
    b64 = base64_encode(plain, plain_len);
    SecureZeroMemory(plain, (size_t)plain_len + 1u);
    HeapFree(GetProcessHeap(), 0, plain);
    plain = NULL;
    if (!b64) {
        show_error(L"No se pudo preparar la configuración privada en memoria.");
        return 3;
    }

    mode = choose_mode();
    if (!mode) {
        SecureZeroMemory(b64, strlen(b64)); HeapFree(GetProcessHeap(), 0, b64);
        return 0;
    }

    if (!run_bootstrap(mode, b64, &exit_code)) {
        SecureZeroMemory(b64, strlen(b64)); HeapFree(GetProcessHeap(), 0, b64);
        show_error(L"No se pudo iniciar el instalador interno. No se eliminaron tus datos ni tu configuración previa.");
        return 4;
    }
    SecureZeroMemory(b64, strlen(b64)); HeapFree(GetProcessHeap(), 0, b64);

    if (exit_code == 0) {
        MessageBoxW(NULL,
            L"Listo. La instalación quedó preparada y las conexiones privadas fueron verificadas.\n\n"
            L"Puedes abrir Recepción o Historia Clínica desde sus accesos directos.",
            APP_TITLE, MB_OK | MB_ICONINFORMATION | MB_TOPMOST | MB_SETFOREGROUND);
        return 0;
    }

    MessageBoxW(NULL,
        L"La instalación no pudo completarse.\n\n"
        L"No se borraron las bases locales ni la configuración previa.\n"
        L"Revisa el registro en C:\\ProgramData\\DrReveloRuntime\\logs.",
        APP_TITLE, MB_OK | MB_ICONERROR | MB_TOPMOST | MB_SETFOREGROUND);
    return (int)exit_code;
}

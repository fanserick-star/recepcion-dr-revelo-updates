// Single-purpose clinic installer: one EXE, both apps, NO embedded credentials.
// Requires one-time administrator-approved enrollment from isolated Cloudflare Worker.
// Windows x64, UAC, PowerShell 5.1. The clinic's production programs are not changed
// by this source file, which lives on a validation branch.
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <commctrl.h>
#include <stdio.h>
#include <wchar.h>
#include "bootstrap_ps.h"
#include "auto_enroll_ps.h"

#define TITLE L"Consultorio Dr. Armando Revelo"
#define CONFIG_COUNT 2

static void error_box(const wchar_t *message) {
    MessageBoxW(NULL,message,TITLE,MB_ICONERROR|MB_OK|MB_TOPMOST|MB_SETFOREGROUND);
}
static int is_elevated(void) {
    HANDLE token=NULL;
    TOKEN_ELEVATION e;
    DWORD used=0;
    int yes=0;
    if(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token)){
        if(GetTokenInformation(token,TokenElevation,&e,sizeof(e),&used))
            yes=(e.TokenIsElevated!=0);
        CloseHandle(token);
    }
    return yes;
}
static int launch_as_admin(void) {
    wchar_t file[MAX_PATH*4];
    if(!GetModuleFileNameW(NULL,file,(DWORD)(sizeof(file)/sizeof(file[0]))))return 0;
    HINSTANCE h=ShellExecuteW(NULL,L"runas",file,NULL,NULL,SW_SHOWNORMAL);
    return ((INT_PTR)h>32);
}

static int write_embedded(const wchar_t *basename,
    const unsigned char *data,DWORD length,wchar_t *path,size_t capacity) {
    wchar_t temp[MAX_PATH*4],directory[MAX_PATH*4];
    DWORD written=0;
    if(!GetTempPathW((DWORD)(sizeof(temp)/sizeof(temp[0])),temp))return 0;
    _snwprintf(directory,sizeof(directory)/sizeof(directory[0]),L"%lsDrReveloSetup",temp);
    if(!CreateDirectoryW(directory,NULL)&&GetLastError()!=ERROR_ALREADY_EXISTS)return 0;
    _snwprintf(path,capacity,L"%ls\\%ls-%lu.ps1",directory,basename,
              (unsigned long)GetCurrentProcessId());
    HANDLE f=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,
                         FILE_ATTRIBUTE_HIDDEN|FILE_ATTRIBUTE_TEMPORARY,NULL);
    if(f==INVALID_HANDLE_VALUE)return 0;
    int ok=WriteFile(f,data,length,&written,NULL)&&written==length;
    if(ok)ok=FlushFileBuffers(f)!=0;
    CloseHandle(f);
    if(!ok)DeleteFileW(path);
    return ok;
}

static LRESULT CALLBACK progress_proc(HWND h,UINT m,WPARAM wp,LPARAM lp) {
    if(m==WM_CLOSE)return 0;  // Prevent apparent success by dismissing window.
    return DefWindowProcW(h,m,wp,lp);
}
static HWND show_progress(void) {
    INITCOMMONCONTROLSEX ic={sizeof(ic),ICC_PROGRESS_CLASS};
    InitCommonControlsEx(&ic);
    HINSTANCE inst=GetModuleHandleW(NULL);
    WNDCLASSW wc;
    ZeroMemory(&wc,sizeof(wc));
    wc.lpfnWndProc=progress_proc;
    wc.hInstance=inst;
    wc.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);
    wc.hCursor=LoadCursor(NULL,IDC_WAIT);
    wc.lpszClassName=L"ReveloOneClickProgress";
    RegisterClassW(&wc);
    HWND h=CreateWindowExW(WS_EX_TOPMOST|WS_EX_DLGMODALFRAME,wc.lpszClassName,TITLE,
       WS_CAPTION|WS_VISIBLE,CW_USEDEFAULT,CW_USEDEFAULT,550,185,
       NULL,NULL,inst,NULL);
    if(!h)return NULL;
    HWND label=CreateWindowW(L"STATIC",
       L"Instalador Maestro: Recepción + Historia Clínica\n"
       L"Autoriza la computadora cuando aparezca el aviso.\n"
       L"Después se descargarán y comprobarán los componentes.",
       WS_CHILD|WS_VISIBLE|SS_CENTER,20,20,500,80,h,NULL,inst,NULL);
    SendMessageW(label,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
    HWND bar=CreateWindowExW(0,PROGRESS_CLASSW,NULL,
       WS_CHILD|WS_VISIBLE|PBS_MARQUEE,42,114,458,20,h,NULL,inst,NULL);
    SendMessageW(bar,PBM_SETMARQUEE,TRUE,40);
    ShowWindow(h,SW_SHOW);
    UpdateWindow(h);
    return h;
}

static int install_both(void) {
    wchar_t bootstrap[MAX_PATH*4]={0},activation[MAX_PATH*4]={0};
    wchar_t windows[MAX_PATH*4],powershell[MAX_PATH*4],cmd[8192];
    PROCESS_INFORMATION pi;
    STARTUPINFOW si;
    DWORD exit_code=1;
    MSG msg;
    HANDLE mutex=CreateMutexW(NULL,TRUE,L"Local\\DrReveloOneClickMasterInstaller");
    if(!mutex)return 8;
    if(GetLastError()==ERROR_ALREADY_EXISTS) {
        error_box(L"Ya hay una instalación del consultorio en curso.");
        CloseHandle(mutex);
        return 9;
    }
    int ok=write_embedded(L"bootstrap",bootstrap_ps1,(DWORD)bootstrap_ps1_len,
                          bootstrap,sizeof(bootstrap)/sizeof(bootstrap[0]));
    if(ok)ok=write_embedded(L"activation",auto_enroll_ps1,(DWORD)auto_enroll_ps1_len,
                           activation,sizeof(activation)/sizeof(activation[0]));
    if(!ok){
        error_box(L"No se pudieron preparar los componentes internos del instalador.");
        if(bootstrap[0])DeleteFileW(bootstrap);
        if(activation[0])DeleteFileW(activation);
        ReleaseMutex(mutex);CloseHandle(mutex);
        return 10;
    }
    if(!GetWindowsDirectoryW(windows,(UINT)(sizeof(windows)/sizeof(windows[0])))){
        DeleteFileW(bootstrap);DeleteFileW(activation);
        ReleaseMutex(mutex);CloseHandle(mutex);return 11;
    }
    _snwprintf(powershell,sizeof(powershell)/sizeof(powershell[0]),
        L"%ls\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",windows);
    _snwprintf(cmd,sizeof(cmd)/sizeof(cmd[0]),
        L"\"%ls\" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%ls\" "
        L"-BootstrapScript \"%ls\"",powershell,activation,bootstrap);
    ZeroMemory(&si,sizeof(si));
    ZeroMemory(&pi,sizeof(pi));
    si.cb=sizeof(si);
    si.dwFlags=STARTF_USESHOWWINDOW;
    si.wShowWindow=SW_HIDE;
    BOOL started=CreateProcessW(NULL,cmd,NULL,NULL,FALSE,
      CREATE_NO_WINDOW|CREATE_UNICODE_ENVIRONMENT,NULL,NULL,&si,&pi);
    if(!started){
        DeleteFileW(bootstrap);DeleteFileW(activation);
        ReleaseMutex(mutex);CloseHandle(mutex);
        error_box(L"No se pudo iniciar el instalador de Windows.");
        return 12;
    }
    HWND progress=show_progress();
    for(;;){
        DWORD w=MsgWaitForMultipleObjects(1,&pi.hProcess,FALSE,150,QS_ALLINPUT);
        while(PeekMessageW(&msg,NULL,0,0,PM_REMOVE)){
            TranslateMessage(&msg);DispatchMessageW(&msg);
        }
        if(w==WAIT_OBJECT_0)break;
        if(w==WAIT_FAILED)break;
    }
    if(!GetExitCodeProcess(pi.hProcess,&exit_code))exit_code=1;
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
    if(progress)DestroyWindow(progress);
    DeleteFileW(bootstrap);DeleteFileW(activation);
    ReleaseMutex(mutex);CloseHandle(mutex);
    if(exit_code==0){
        MessageBoxW(NULL,L"Recepción e Historia Clínica instaladas.\n\n"
          L"Se validaron las conexiones y la recuperación clínica inicial.\n"
          L"Verifica los periféricos antes de comenzar la atención.",
          TITLE,MB_OK|MB_ICONINFORMATION|MB_TOPMOST|MB_SETFOREGROUND);
        return 0;
    }
    error_box(L"La instalación no se pudo completar o esta PC no fue autorizada.\n\n"
      L"No se han borrado bases clínicas ni configuraciones existentes.\n"
      L"Consulta los registros en C:\\ProgramData\\DrReveloRuntime\\logs.");
    return (int)exit_code;
}

int WINAPI wWinMain(HINSTANCE app,HINSTANCE previous,PWSTR command,int show) {
    (void)app;(void)previous;(void)command;(void)show;
    if(!is_elevated()){
        if(!launch_as_admin())
            error_box(L"Se necesitan permisos de administrador para instalar ambos programas.");
        return 0;
    }
    return install_both();
}

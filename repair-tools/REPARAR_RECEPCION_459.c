#define UNICODE
#define _UNICODE
#include <windows.h>
#include <urlmon.h>
#include <shellapi.h>
#pragma comment(lib,"urlmon.lib")
#pragma comment(lib,"shell32.lib")

int WINAPI wWinMain(HINSTANCE h,HINSTANCE p,PWSTR cmd,int show){
    wchar_t tmp[MAX_PATH], py[MAX_PATH], script[MAX_PATH];
    GetTempPathW(MAX_PATH,tmp);
    wsprintfW(script,L"%sRecepcion_Reparar_459.py",tmp);
    HRESULT hr=URLDownloadToFileW(NULL,
      L"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/repair-tools/REPARAR_RECEPCION_459.py",
      script,0,NULL);
    if(FAILED(hr)){MessageBoxW(NULL,L"No pude descargar la reparación. Revisa Internet y vuelve a intentarlo.",L"Reparar Recepción",MB_ICONERROR);return 2;}
    lstrcpyW(py,L"C:\\Recepcion Dr Revelo\\.venv\\Scripts\\python.exe");
    if(GetFileAttributesW(py)==INVALID_FILE_ATTRIBUTES){MessageBoxW(NULL,L"No encontré el Python de Recepción en C:\\Recepcion Dr Revelo.",L"Reparar Recepción",MB_ICONERROR);return 3;}
    wchar_t args[MAX_PATH*2]; wsprintfW(args,L"\"%s\"",script);
    SHELLEXECUTEINFOW se={0};se.cbSize=sizeof(se);se.fMask=SEE_MASK_NOCLOSEPROCESS;se.lpVerb=L"open";se.lpFile=py;se.lpParameters=args;se.lpDirectory=L"C:\\Recepcion Dr Revelo";se.nShow=SW_HIDE;
    if(!ShellExecuteExW(&se)){MessageBoxW(NULL,L"No pude iniciar la reparación.",L"Reparar Recepción",MB_ICONERROR);return 4;}
    WaitForSingleObject(se.hProcess,INFINITE);DWORD ec=1;GetExitCodeProcess(se.hProcess,&ec);CloseHandle(se.hProcess);return (int)ec;
}
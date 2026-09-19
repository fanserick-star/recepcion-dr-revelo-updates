#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <propkey.h>
#include <propvarutil.h>
#include <shellapi.h>
#include <strsafe.h>
#pragma comment(lib,"ole32.lib")
#pragma comment(lib,"shell32.lib")

static const wchar_t *APP_ID = L"DrArmandoRevelo.HistoriaClinica";
static const wchar_t *LINK_NAME = L"Historia Clínica - Dr. Armando Revelo.lnk";

static BOOL FileExists(const wchar_t* p){
    DWORD a=GetFileAttributesW(p);
    return a!=INVALID_FILE_ATTRIBUTES && !(a&FILE_ATTRIBUTE_DIRECTORY);
}

static void GetRoot(wchar_t* out, size_t cch){
    GetModuleFileNameW(NULL,out,(DWORD)cch);
    wchar_t* slash=wcsrchr(out,L'\\');
    if(slash)*slash=0;
}

static HRESULT MakeShortcut(const wchar_t* linkPath,const wchar_t* exePath,const wchar_t* root){
    IShellLinkW* sl=NULL;
    IPropertyStore* ps=NULL;
    IPersistFile* pf=NULL;
    PROPVARIANT pv;
    HRESULT hr=CoCreateInstance(&CLSID_ShellLink,NULL,CLSCTX_INPROC_SERVER,&IID_IShellLinkW,(void**)&sl);
    if(FAILED(hr))return hr;

    sl->lpVtbl->SetPath(sl,exePath);
    sl->lpVtbl->SetWorkingDirectory(sl,root);
    sl->lpVtbl->SetDescription(sl,L"Historia Clínica - Dr. Armando Revelo");
    sl->lpVtbl->SetShowCmd(sl,SW_SHOWNORMAL);
    sl->lpVtbl->SetIconLocation(sl,exePath,0);

    hr=sl->lpVtbl->QueryInterface(sl,&IID_IPropertyStore,(void**)&ps);
    if(SUCCEEDED(hr)){
        PropVariantInit(&pv);
        size_t appLen = wcslen(APP_ID) + 1;
        pv.vt = VT_LPWSTR;
        pv.pwszVal = (LPWSTR)CoTaskMemAlloc(appLen * sizeof(wchar_t));
        if(pv.pwszVal){
            StringCchCopyW(pv.pwszVal, appLen, APP_ID);
            ps->lpVtbl->SetValue(ps,&PKEY_AppUserModel_ID,&pv);
            ps->lpVtbl->Commit(ps);
        }
        PropVariantClear(&pv);
        ps->lpVtbl->Release(ps);
    }

    hr=sl->lpVtbl->QueryInterface(sl,&IID_IPersistFile,(void**)&pf);
    if(SUCCEEDED(hr)){
        hr=pf->lpVtbl->Save(pf,linkPath,TRUE);
        pf->lpVtbl->Release(pf);
    }
    sl->lpVtbl->Release(sl);
    return hr;
}

static BOOL RepairShortcuts(const wchar_t* exePath,const wchar_t* root){
    wchar_t dir[MAX_PATH]={0}, link[MAX_PATH]={0};
    BOOL ok=TRUE;
    HRESULT hr=CoInitializeEx(NULL,COINIT_APARTMENTTHREADED);
    BOOL co=SUCCEEDED(hr);

    if(SUCCEEDED(SHGetFolderPathW(NULL,CSIDL_DESKTOPDIRECTORY,NULL,SHGFP_TYPE_CURRENT,dir))){
        StringCchPrintfW(link,MAX_PATH,L"%s\\%s",dir,LINK_NAME);
        if(FAILED(MakeShortcut(link,exePath,root)))ok=FALSE;
    }
    ZeroMemory(dir,sizeof(dir));
    if(SUCCEEDED(SHGetFolderPathW(NULL,CSIDL_PROGRAMS,NULL,SHGFP_TYPE_CURRENT,dir))){
        StringCchPrintfW(link,MAX_PATH,L"%s\\%s",dir,LINK_NAME);
        MakeShortcut(link,exePath,root);
    }

    if(co)CoUninitialize();
    SHChangeNotify(SHCNE_ASSOCCHANGED,SHCNF_IDLIST,NULL,NULL);
    return ok;
}

static int LaunchPython(const wchar_t* root){
    wchar_t pyw[MAX_PATH], script[MAX_PATH], cmd[MAX_PATH*3];
    StringCchPrintfW(pyw,MAX_PATH,L"%s\\.venv\\Scripts\\pythonw.exe",root);
    StringCchPrintfW(script,MAX_PATH,L"%s\\ABRIR_HISTORIA_CLINICA.py",root);
    if(!FileExists(pyw) || !FileExists(script)){
        MessageBoxW(NULL,L"No encontré los componentes de Historia Clínica.\n\nEjecute INICIAR.bat desde la carpeta del programa para reparar la instalación.",L"Historia Clínica - Dr. Armando Revelo",MB_OK|MB_ICONERROR);
        return 2;
    }

    StringCchPrintfW(cmd,MAX_PATH*3,L"\"%s\" \"%s\"",pyw,script);
    STARTUPINFOW si={0};
    PROCESS_INFORMATION pi={0};
    si.cb=sizeof(si);
    if(!CreateProcessW(NULL,cmd,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,root,&si,&pi)){
        MessageBoxW(NULL,L"No pude iniciar Historia Clínica.",L"Historia Clínica - Dr. Armando Revelo",MB_OK|MB_ICONERROR);
        return 3;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

int WINAPI wWinMain(HINSTANCE h,HINSTANCE p,PWSTR cmd,int show){
    SetCurrentProcessExplicitAppUserModelID(APP_ID);
    wchar_t root[MAX_PATH], exe[MAX_PATH];
    GetRoot(root,MAX_PATH);
    GetModuleFileNameW(NULL,exe,MAX_PATH);

    BOOL repairOnly=(cmd && wcsstr(cmd,L"--repair-shortcut")!=NULL);
    RepairShortcuts(exe,root);
    if(repairOnly)return 0;
    return LaunchPython(root);
}

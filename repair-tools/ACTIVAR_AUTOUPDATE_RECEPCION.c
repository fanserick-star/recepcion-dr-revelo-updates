#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <objbase.h>
#include <shobjidl.h>
#include <shellapi.h>
#include <strsafe.h>
#pragma comment(lib,"ole32.lib")
#pragma comment(lib,"shell32.lib")

static HRESULT MakeShortcut(const wchar_t* linkPath,const wchar_t* target,const wchar_t* args,const wchar_t* work,const wchar_t* icon){
    IShellLinkW* sl=NULL; IPersistFile* pf=NULL;
    HRESULT hr=CoCreateInstance(&CLSID_ShellLink,NULL,CLSCTX_INPROC_SERVER,&IID_IShellLinkW,(void**)&sl);
    if(FAILED(hr)) return hr;
    sl->lpVtbl->SetPath(sl,target);
    sl->lpVtbl->SetArguments(sl,args);
    sl->lpVtbl->SetWorkingDirectory(sl,work);
    sl->lpVtbl->SetDescription(sl,L"Recepción Dr. Armando Revelo");
    sl->lpVtbl->SetShowCmd(sl,SW_SHOWNORMAL);
    if(icon && *icon) sl->lpVtbl->SetIconLocation(sl,icon,0);
    hr=sl->lpVtbl->QueryInterface(sl,&IID_IPersistFile,(void**)&pf);
    if(SUCCEEDED(hr)){
        hr=pf->lpVtbl->Save(pf,linkPath,TRUE);
        pf->lpVtbl->Release(pf);
    }
    sl->lpVtbl->Release(sl);
    return hr;
}

static BOOL Exists(const wchar_t* p){
    DWORD a=GetFileAttributesW(p);
    return a!=INVALID_FILE_ATTRIBUTES && !(a&FILE_ATTRIBUTE_DIRECTORY);
}

int WINAPI wWinMain(HINSTANCE h,HINSTANCE p,PWSTR cmd,int show){
    const wchar_t* root=L"C:\\Recepcion Dr Revelo";
    wchar_t pyw[MAX_PATH], launcher[MAX_PATH], icon[MAX_PATH], args[MAX_PATH*2];
    StringCchPrintfW(pyw,MAX_PATH,L"%s\\.venv\\Scripts\\pythonw.exe",root);
    StringCchPrintfW(launcher,MAX_PATH,L"%s\\ABRIR_RECEPCION.py",root);
    StringCchPrintfW(icon,MAX_PATH,L"%s\\recepcion.ico",root);
    if(!Exists(icon)) StringCchPrintfW(icon,MAX_PATH,L"%s\\static\\doctor_icon.ico",root);

    if(!Exists(pyw) || !Exists(launcher)){
        MessageBoxW(NULL,
            L"No encontré la instalación oficial en C:\\Recepcion Dr Revelo.\n\nNo se modificó nada.",
            L"Activar actualizaciones automáticas",MB_ICONERROR|MB_OK);
        return 2;
    }

    HRESULT hr=CoInitializeEx(NULL,COINIT_APARTMENTTHREADED);
    BOOL co=SUCCEEDED(hr);
    wchar_t desktop[MAX_PATH]={0}, programs[MAX_PATH]={0}, link[MAX_PATH]={0};
    BOOL ok=TRUE;

    if(SUCCEEDED(SHGetFolderPathW(NULL,CSIDL_DESKTOPDIRECTORY,NULL,SHGFP_TYPE_CURRENT,desktop))){
        StringCchPrintfW(link,MAX_PATH,L"%s\\Recepción Dr. Armando Revelo.lnk",desktop);
        if(FAILED(MakeShortcut(link,pyw,L"\"C:\\Recepcion Dr Revelo\\ABRIR_RECEPCION.py\"",root,icon))) ok=FALSE;
    }
    if(SUCCEEDED(SHGetFolderPathW(NULL,CSIDL_PROGRAMS,NULL,SHGFP_TYPE_CURRENT,programs))){
        StringCchPrintfW(link,MAX_PATH,L"%s\\Recepción Dr. Armando Revelo.lnk",programs);
        MakeShortcut(link,pyw,L"\"C:\\Recepcion Dr Revelo\\ABRIR_RECEPCION.py\"",root,icon);
    }
    if(co) CoUninitialize();

    SHChangeNotify(SHCNE_ASSOCCHANGED,SHCNF_IDLIST,NULL,NULL);

    StringCchPrintfW(args,MAX_PATH*2,L"\"%s\"",launcher);
    SHELLEXECUTEINFOW se={0};
    se.cbSize=sizeof(se);
    se.fMask=SEE_MASK_NOCLOSEPROCESS;
    se.lpVerb=L"open";
    se.lpFile=pyw;
    se.lpParameters=args;
    se.lpDirectory=root;
    se.nShow=SW_HIDE;
    if(!ShellExecuteExW(&se)){
        MessageBoxW(NULL,
            L"El acceso directo quedó corregido, pero no pude abrir Recepción automáticamente.\n\nÁbrela desde el nuevo acceso directo.",
            L"Activar actualizaciones automáticas",MB_ICONWARNING|MB_OK);
        return 3;
    }
    if(se.hProcess) CloseHandle(se.hProcess);

    MessageBoxW(NULL,
        ok ?
        L"Listo. El acceso directo ahora entra por el launcher oficial.\n\nRecepción se está abriendo y debe aplicar la actualización automática publicada." :
        L"Recepción se está abriendo por el launcher oficial. Si el icono del escritorio no cambió, reinicia el Explorador de Windows.",
        L"Actualizaciones automáticas activadas",MB_ICONINFORMATION|MB_OK);
    return 0;
}

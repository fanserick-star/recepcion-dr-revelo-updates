#define UNICODE
#define _UNICODE
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <wchar.h>

static const char MARKER[16]={'H','C','R','E','V','E','L','O','L','I','N','K','U','R','L','1'};
typedef struct Footer { char marker[16]; uint64_t payload_size; } Footer;

static void msg(const wchar_t *t, UINT f){ MessageBoxW(NULL,t,L"Vincular Recepcion con Historia Clinica",f|MB_OK); }

static int read_payload(wchar_t **out){
    wchar_t self[4096]; if(!GetModuleFileNameW(NULL,self,4096)) return 0;
    FILE *f=_wfopen(self,L"rb"); if(!f) return 0;
    _fseeki64(f,0,SEEK_END); __int64 total=_ftelli64(f);
    if(total<(int)sizeof(Footer)){fclose(f);return 0;}
    _fseeki64(f,total-sizeof(Footer),SEEK_SET); Footer ft;
    if(fread(&ft,1,sizeof(ft),f)!=sizeof(ft) || memcmp(ft.marker,MARKER,16)!=0 || ft.payload_size<20 || ft.payload_size>4096){fclose(f);return 0;}
    __int64 start=total-sizeof(Footer)-(__int64)ft.payload_size; if(start<0){fclose(f);return 0;}
    _fseeki64(f,start,SEEK_SET);
    char *buf=(char*)calloc((size_t)ft.payload_size+1,1); if(!buf){fclose(f);return 0;}
    if(fread(buf,1,(size_t)ft.payload_size,f)!=(size_t)ft.payload_size){free(buf);fclose(f);return 0;}
    fclose(f);
    int n=MultiByteToWideChar(CP_UTF8,0,buf,(int)ft.payload_size,NULL,0); if(n<=0){free(buf);return 0;}
    wchar_t *w=(wchar_t*)calloc((size_t)n+1,sizeof(wchar_t)); if(!w){free(buf);return 0;}
    MultiByteToWideChar(CP_UTF8,0,buf,(int)ft.payload_size,w,n); free(buf); *out=w; return 1;
}

static int run_ps(const wchar_t *script){
    size_t cap=wcslen(script)+128; wchar_t *cmd=(wchar_t*)calloc(cap,sizeof(wchar_t)); if(!cmd)return 0;
    swprintf(cmd,cap,L"powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"%ls\"",script);
    STARTUPINFOW si; PROCESS_INFORMATION pi; ZeroMemory(&si,sizeof(si));ZeroMemory(&pi,sizeof(pi));si.cb=sizeof(si);si.dwFlags=STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;
    BOOL ok=CreateProcessW(NULL,cmd,NULL,NULL,FALSE,CREATE_NO_WINDOW|CREATE_UNICODE_ENVIRONMENT,NULL,L"C:\\Recepcion Dr Revelo",&si,&pi);
    free(cmd); if(!ok)return 0; WaitForSingleObject(pi.hProcess,INFINITE); DWORD ec=1;GetExitCodeProcess(pi.hProcess,&ec);CloseHandle(pi.hThread);CloseHandle(pi.hProcess);return ec==0;
}

int WINAPI wWinMain(HINSTANCE h,HINSTANCE p,PWSTR c,int s){
    (void)h;(void)p;(void)c;(void)s;
    const wchar_t *root=L"C:\\Recepcion Dr Revelo";
    const wchar_t *launcher=L"C:\\Recepcion Dr Revelo\\ABRIR_RECEPCION.py";
    DWORD a=GetFileAttributesW(launcher);
    if(a==INVALID_FILE_ATTRIBUTES){ msg(L"No encontre Recepcion en C:\\Recepcion Dr Revelo. Instala o migra primero Recepcion a esa carpeta.",MB_ICONERROR); return 2; }
    wchar_t *url=NULL; if(!read_payload(&url)){ msg(L"El archivo de vinculacion esta incompleto. Vuelve a descargarlo.",MB_ICONERROR); return 3; }
    size_t need=wcslen(url)+12000; wchar_t *ps=(wchar_t*)calloc(need,sizeof(wchar_t)); if(!ps){free(url);return 4;}
    swprintf(ps,need,
      L"$ErrorActionPreference='Stop'; $p='C:\\Recepcion Dr Revelo\\.env'; $bak='C:\\Recepcion Dr Revelo\\.env.antes_historia'; $k='HISTORIA_DATABASE_URL'; $v='%ls'; "
      L"if(Test-Path -LiteralPath $p){Copy-Item -LiteralPath $p -Destination $bak -Force; $lines=Get-Content -LiteralPath $p -Encoding UTF8}else{$lines=@()}; "
      L"$found=$false; $out=@(); foreach($line in $lines){if($line -match '^\\s*HISTORIA_DATABASE_URL\\s*='){if(-not $found){$out+=($k+'='+$v);$found=$true}}else{$out+=$line}}; if(-not $found){$out+=($k+'='+$v)}; "
      L"Set-Content -LiteralPath $p -Value $out -Encoding UTF8;",
      url);
    free(url);
    int ok=run_ps(ps); free(ps);
    if(!ok){ msg(L"No pude guardar la configuracion privada de Historia Clinica. Intenta ejecutar este archivo como administrador.",MB_ICONERROR); return 5; }
    msg(L"Recepcion quedo vinculada con Historia Clinica.\n\nCierra Recepcion si esta abierta y vuelve a abrirla. El actualizador instalara v4.5.8 y desde entonces cada nueva atencion se enviara a Pacientes en espera del doctor.",MB_ICONINFORMATION);
    return 0;
}
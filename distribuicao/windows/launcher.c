#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
int WINAPI wWinMain(HINSTANCE h,HINSTANCE prev,LPWSTR args,int show){
 wchar_t dir[32768],script[32768],python[32768],key[512],params[32768];
 GetModuleFileNameW(NULL,dir,32768);wchar_t *end=wcsrchr(dir,L'\\');if(!end)return 1;*end=0;
 swprintf(script,32768,L"%ls\\desktop_boot.py",dir);
 if(GetFileAttributesW(script)==INVALID_FILE_ATTRIBUTES){MessageBoxW(NULL,L"Extraia todo o ZIP. Mantenha o executável junto dos outros arquivos.",L"Ripagem Maker",MB_ICONERROR);return 1;}
 const wchar_t *versions[]={L"3.12",L"3.13",L"3.11",L"3.10"};
 HKEY roots[]={HKEY_CURRENT_USER,HKEY_LOCAL_MACHINE};BOOL found=FALSE;
 for(int v=0;v<4&&!found;v++)for(int r=0;r<2&&!found;r++){
  swprintf(key,512,L"Software\\Python\\PythonCore\\%ls\\InstallPath",versions[v]);HKEY handle;
  if(RegOpenKeyExW(roots[r],key,0,KEY_READ|KEY_WOW64_64KEY,&handle)==ERROR_SUCCESS){
   DWORD bytes=sizeof(python);if(RegQueryValueExW(handle,L"WindowedExecutablePath",NULL,NULL,(LPBYTE)python,&bytes)==ERROR_SUCCESS&&GetFileAttributesW(python)!=INVALID_FILE_ATTRIBUTES)found=TRUE;
   if(!found){bytes=sizeof(python);if(RegQueryValueExW(handle,NULL,NULL,NULL,(LPBYTE)python,&bytes)==ERROR_SUCCESS){wcscat(python,L"pythonw.exe");if(GetFileAttributesW(python)!=INVALID_FILE_ATTRIBUTES)found=TRUE;}}
   RegCloseKey(handle);
  }
 }
 if(!found){MessageBoxW(NULL,L"Instale Python 3.12 de 64 bits pelo site python.org, com Tcl/Tk e pip. Depois abra novamente. Não é preciso remover outras versões.",L"Ripagem Maker",MB_ICONINFORMATION);return 1;}
 swprintf(params,32768,L"\"%ls\"",script);
 if((INT_PTR)ShellExecuteW(NULL,L"open",python,params,dir,SW_SHOWNORMAL)<=32){MessageBoxW(NULL,L"Não foi possível iniciar o Python instalado.",L"Ripagem Maker",MB_ICONERROR);return 1;}
 return 0;
}

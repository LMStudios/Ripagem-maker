#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdint.h>
#include <string.h>
static void quoteps(wchar_t *out,const wchar_t *in){while(*in){*out++=*in;if(*in=='\'')*out++='\'';in++;}*out=0;}
int WINAPI wWinMain(HINSTANCE h,HINSTANCE prev,LPWSTR args,int show){
 wchar_t self[32768],temp[32768],folder[32768],zip[32768],qfolder[32768],qzip[32768],params[32768],ps[32768];
 GetModuleFileNameW(NULL,self,32768);GetTempPathW(32768,temp);GetTempFileNameW(temp,L"RMI",0,folder);DeleteFileW(folder);CreateDirectoryW(folder,NULL);
 swprintf(zip,32768,L"%ls\\conteudo.zip",folder);
 HANDLE input=CreateFileW(self,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);if(input==INVALID_HANDLE_VALUE)goto fail;
 LARGE_INTEGER size,pos;GetFileSizeEx(input,&size);if(size.QuadPart<16){CloseHandle(input);goto fail;}
 pos.QuadPart=size.QuadPart-16;SetFilePointerEx(input,pos,NULL,FILE_BEGIN);unsigned char footer[16];DWORD got;
 if(!ReadFile(input,footer,16,&got,NULL)||got!=16||memcmp(footer+8,"RMSETUP1",8)){CloseHandle(input);goto fail;}
 uint64_t length;memcpy(&length,footer,8);if(length>size.QuadPart-16||length>100000000){CloseHandle(input);goto fail;}
 pos.QuadPart=size.QuadPart-16-length;SetFilePointerEx(input,pos,NULL,FILE_BEGIN);
 HANDLE output=CreateFileW(zip,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);if(output==INVALID_HANDLE_VALUE){CloseHandle(input);goto fail;}
 char buffer[65536];DWORD wrote;BOOL ok=TRUE;
 while(length){DWORD chunk=length>sizeof(buffer)?sizeof(buffer):(DWORD)length;if(!ReadFile(input,buffer,chunk,&got,NULL)||got!=chunk||!WriteFile(output,buffer,chunk,&wrote,NULL)||wrote!=chunk){ok=FALSE;break;}length-=chunk;}
 CloseHandle(input);CloseHandle(output);if(!ok)goto fail;
 quoteps(qfolder,folder);quoteps(qzip,zip);
 swprintf(params,32768,L"-NoProfile -STA -WindowStyle Hidden -Command \"$ErrorActionPreference='Stop';try { Expand-Archive -LiteralPath '%ls' -DestinationPath '%ls' -Force; & ([ScriptBlock]::Create([IO.File]::ReadAllText('%ls\\instalar.ps1'))) -Source '%ls\\Ripagem Maker' } catch { Add-Type -AssemblyName System.Windows.Forms; [Windows.Forms.MessageBox]::Show($_.Exception.Message,'Ripagem Maker') }\"",qzip,qfolder,qfolder,qfolder);
 GetSystemDirectoryW(ps,32768);wcscat(ps,L"\\WindowsPowerShell\\v1.0\\powershell.exe");
 if((INT_PTR)ShellExecuteW(NULL,L"open",ps,params,folder,SW_HIDE)<=32)goto fail;
 return 0;
 fail:MessageBoxW(NULL,L"Não foi possível preparar o instalador. Baixe o arquivo novamente e confira se há espaço na pasta temporária.",L"Ripagem Maker",MB_ICONERROR);return 1;
}

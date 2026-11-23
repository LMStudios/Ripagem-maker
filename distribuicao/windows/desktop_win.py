import os,sys,time,json,subprocess,urllib.request,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
LOG=ROOT/'ripagem-windows.log'
def main():
 import webview
 # Downloads são desativados por padrão no pywebview.
 webview.settings['ALLOW_DOWNLOADS']=True
 env=os.environ.copy();env.update(DRSTUDIO_EMBED='1',PYTHONIOENCODING='utf-8',PYTHONUTF8='1',PYTHONUNBUFFERED='1')
 child=None
 def online():
  try:
   with urllib.request.urlopen('http://127.0.0.1:8765/api/recursos',timeout=1) as response:return json.load(response).get('forma_produto')
  except Exception:return False
 with LOG.open('a',encoding='utf-8') as log:
  try:
   if not online():
    python=Path(sys.executable).with_name('python.exe')
    child=subprocess.Popen([str(python),str(ROOT/'app.py')],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(120):
     if child.poll() is not None:raise RuntimeError('O servidor fechou. Veja ripagem-windows.log.')
     if online():break
     time.sleep(.5)
    else:raise RuntimeError('O servidor não respondeu em 60 segundos.')
   from plataforma.native_files import FileBridge
   bridge=FileBridge(webview)
   window=webview.create_window('Ripagem Maker','http://127.0.0.1:8765/',width=1400,height=900,min_size=(960,620),js_api=bridge)
   bridge._window=window
   if os.name=='nt':
    def set_window_icon():
     try:
      import ctypes
      from ctypes import wintypes
      user32=ctypes.windll.user32
      user32.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR];user32.FindWindowW.restype=wintypes.HWND
      user32.LoadImageW.argtypes=[wintypes.HINSTANCE,wintypes.LPCWSTR,wintypes.UINT,ctypes.c_int,ctypes.c_int,wintypes.UINT];user32.LoadImageW.restype=wintypes.HICON
      user32.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM];user32.SendMessageW.restype=wintypes.LPARAM
      hwnd=user32.FindWindowW(None,'Ripagem Maker')
      icon=user32.LoadImageW(None,str(ROOT/'plataforma/static/assets/app.ico'),1,0,0,0x10|0x40)
      if hwnd and icon:
       user32.SendMessageW(hwnd,0x80,0,icon);user32.SendMessageW(hwnd,0x80,1,icon)
     except Exception:pass  # O recurso embutido do launcher continua disponível.
    window.events.shown+=set_window_icon
   webview.start(gui='edgechromium')
  finally:
   if child and child.poll() is None:
    subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
if __name__=='__main__':
 try:main()
 except Exception as error:
  with LOG.open('a',encoding='utf-8') as f:traceback.print_exc(file=f)
  import ctypes
  ctypes.windll.user32.MessageBoxW(None,'Não foi possível abrir: '+str(error)+'\n\nDetalhes: '+str(LOG),'Ripagem Maker',16)

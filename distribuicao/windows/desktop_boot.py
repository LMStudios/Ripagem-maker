"""Janela de preparação, com dados mantidos fora do executável."""
import os,sys,json,shutil,subprocess,threading,queue,importlib.util,urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
SOURCE=Path(__file__).resolve().parent
STATE=SOURCE/'.app-root.json'
app=tk.Tk();app.title('Ripagem Maker');app.geometry('560x250');app.resizable(False,False)
try:app.iconbitmap(str(SOURCE/'plataforma/static/assets/app.ico'))
except tk.TclError:pass
status=tk.StringVar(value='Abra aqui ou escolha a pasta de uma versão já instalada.')
ttk.Label(app,text='Ripagem Maker',font=('Segoe UI',20,'bold')).pack(pady=15)
ttk.Label(app,textvariable=status,wraplength=520).pack(padx=20,pady=10)
bar=ttk.Progressbar(app,mode='indeterminate');bar.pack(fill='x',padx=24,pady=10)
messages=queue.Queue();busy=False

def install(root):
 try:
  try:
   with urllib.request.urlopen('http://127.0.0.1:8765/api/recursos',timeout=1) as response:running=json.load(response).get('forma_produto')
  except Exception:running=False
  if running:raise RuntimeError('Feche a versão anterior e o Terminal que mantém o app aberto, antes de continuar.')
  # Atualiza somente os arquivos distribuídos; nunca .env, saídas ou configurações.
  names=json.loads((SOURCE/'manifest.json').read_text())
  def version(folder):
   p=folder/'VERSION';return tuple(map(int,p.read_text().strip().split('.'))) if p.exists() else (0,0,0)
  if root.resolve()!=SOURCE.resolve() and version(root)<=version(SOURCE):
   for name in names:
    dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(SOURCE/name,dest)
  STATE.write_text(json.dumps({'root':str(root)}))
  spec=importlib.util.spec_from_file_location('starter',root/'iniciar.py');starter=importlib.util.module_from_spec(spec);spec.loader.exec_module(starter)
  starter.ensure_runtime()
  python=starter.PY;marker=starter.ENV/'desktop-instalado-v1'
  with (root/'preparacao-windows.log').open('a',encoding='utf-8') as log:
   if not starter.dependencies_ready(marker,desktop=True):
    messages.put(('status','Preparando dependências. Na primeira abertura pode levar alguns minutos…'))
    subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt'),'pywebview>=5,<7'],stdout=log,stderr=log,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    marker.write_text(starter.dependency_fingerprint(desktop=True))
  if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):raise RuntimeError('Instale FFmpeg no Terminal: winget install --id Gyan.FFmpeg -e. Depois feche e abra o aplicativo novamente.')
  subprocess.Popen([str(python.with_name('pythonw.exe')),str(root/'desktop_win.py')],cwd=root,creationflags=subprocess.CREATE_NO_WINDOW)
  messages.put(('done',None))
 except Exception as e:messages.put(('error',str(e)+'\nConsulte preparacao-windows.log na pasta escolhida.'))

def begin(previous=False):
 global busy
 if busy:return
 root=SOURCE
 if previous:
  selected=filedialog.askdirectory(title='Escolha a pasta da versão anterior que contém app.py')
  if not selected:return
  root=Path(selected)
  if not (root/'app.py').is_file():messagebox.showerror('Pasta inválida','Escolha a pasta que contém app.py.');return
 else:
  try:
   saved=Path(json.loads(STATE.read_text())['root'])
   if (saved/'app.py').is_file():root=saved
  except (OSError,KeyError,ValueError):pass
 busy=True;open_button.config(state='disabled');old_button.config(state='disabled');bar.start();status.set('Preparando o ambiente deste computador…')
 threading.Thread(target=install,args=(root,),daemon=True).start()

def poll():
 global busy
 try:
  kind,value=messages.get_nowait()
  if kind=='done':app.destroy();return
  if kind=='status':status.set(value)
  if kind=='error':
   busy=False;bar.stop();status.set('Não foi possível preparar o aplicativo.');open_button.config(state='normal');old_button.config(state='normal');messagebox.showerror('Ripagem Maker',value)
 except queue.Empty:pass
 app.after(150,poll)
open_button=ttk.Button(app,text='Abrir Ripagem Maker',command=begin);open_button.pack(side='left',padx=30,pady=15)
old_button=ttk.Button(app,text='Usar pasta já instalada',command=lambda:begin(True));old_button.pack(side='right',padx=30,pady=15)
app.protocol('WM_DELETE_WINDOW',lambda:messagebox.showinfo('Preparação em andamento','Aguarde a preparação terminar antes de fechar.') if busy else app.destroy())
poll();app.mainloop()

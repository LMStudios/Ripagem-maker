"""Ponte restrita para diálogos de arquivos da janela Windows."""
import os,shutil,sys,tempfile,uuid
from itertools import count
from pathlib import Path
from urllib.parse import urlsplit,unquote
from . import armazenamento as S
class FileBridge:
 def __init__(self,webview):
  self._webview=webview;self._window=None
  self._folder=getattr(getattr(webview,'FileDialog',None),'FOLDER',getattr(webview,'FOLDER_DIALOG',None))
  self._save=getattr(getattr(webview,'FileDialog',None),'SAVE',getattr(webview,'SAVE_DIALOG',None))
 def _local(self):
  if not self._window:raise ValueError('Janela ainda não está pronta.')
  url=urlsplit(self._window.get_current_url() or '')
  if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost') or url.port!=8765:raise ValueError('A ação está disponível somente na janela local do Ripagem Maker.')
 def choose_folder(self):
  try:
   self._local();selected=self._window.create_file_dialog(self._folder);self._local()
   return {'ok':True,'cancelado':not bool(selected),'pasta':str(selected[0]) if selected else ''}
  except Exception as e:return {'ok':False,'erro':str(e)}
 def save_file(self,address):
  try:
   self._local();url=urlsplit(str(address))
   if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost') or url.port!=8765 or not url.path.startswith('/files/'):raise ValueError('Arquivo fora do trabalho local.')
   relative=unquote(url.path[len('/files/'):]);source=S.resolve('fatiador',relative)
   if not source.is_file() or not any(source.is_relative_to(root) for root in S.roots('fatiador')):raise ValueError('O arquivo não existe no local esperado: '+str(source))
   selected=self._window.create_file_dialog(self._save,save_filename=source.name)
   self._local()
   if not selected:return {'ok':True,'cancelado':True,'origem':str(source)}
   target=Path(selected[0]).resolve()
   if target!=source:
    temporary=target.with_name('.'+target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:shutil.copyfile(source,temporary);os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
   if not target.is_file() or target.stat().st_size!=source.stat().st_size:raise OSError('A cópia não foi confirmada no destino.')
   return {'ok':True,'arquivo':str(target),'origem':str(source),'bytes':target.stat().st_size}
  except Exception as e:return {'ok':False,'erro':str(e)}


def copy_to_downloads(source):
    """No iniciador Mac clássico, mantém o destino de download e confirma a cópia no disco."""
    if sys.platform != 'darwin':
        raise ValueError('Use a janela Salvar como deste aplicativo.')
    directory = Path.home() / 'Downloads'
    fd, name = tempfile.mkstemp(prefix='.ripagem-', dir=directory)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as target, source.open('rb') as origin:
            shutil.copyfileobj(origin, target)
        size = source.stat().st_size
        if not size or temp.stat().st_size != size:
            raise OSError('A cópia ficou incompleta.')
        for number in count(1):
            filename = source.name if number == 1 else f'{source.stem} ({number}){source.suffix}'
            output = directory / filename
            try:
                os.link(temp, output)
                return str(output)
            except FileExistsError:
                continue
    finally:
        temp.unlink(missing_ok=True)

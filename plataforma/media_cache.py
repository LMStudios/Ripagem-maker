"""Bounded in-memory metadata cache, invalidated by the actual file identity."""
import copy
import json
import subprocess
import threading
from collections import OrderedDict
from pathlib import Path

_CACHE=OrderedDict()
_LOCK=threading.RLock()
_PENDING={}
_LIMIT=1024

def metadata(path,executable):
    file=Path(path).resolve();stat=file.stat()
    key=(str(file),str(executable),stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key);return copy.deepcopy(_CACHE[key])
        lock=_PENDING.setdefault(key,threading.Lock())
    # Only requests for the same file wait for each other: no duplicate probes, but different files are read in parallel.
    with lock:
        try:
            with _LOCK:
                if key in _CACHE:return copy.deepcopy(_CACHE[key])
            try:
                result=subprocess.run([executable,'-v','error','-show_format','-show_streams','-of','json',str(file)],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            except subprocess.TimeoutExpired as error:raise ValueError('A leitura da mídia demorou demais. Confira o arquivo e tente novamente.') from error
            if result.returncode:raise ValueError('Não foi possível ler a mídia: '+file.name)
            data=json.loads(result.stdout)
            if not isinstance(data,dict):raise ValueError('Metadados de mídia inválidos.')
            with _LOCK:
                # Replace stale entries for this path; do not retain old revisions in RAM.
                for previous in list(_CACHE):
                    if previous[:2]==key[:2]:del _CACHE[previous]
                _CACHE[key]=data
                while len(_CACHE)>_LIMIT:_CACHE.popitem(last=False)
            return copy.deepcopy(data)
        finally:
            with _LOCK:_PENDING.pop(key,None)

def prefetch(paths,executable,workers=8):
    """Read many files at once before a loop that needs them one by one; unreadable files are left for that loop to report."""
    from concurrent.futures import ThreadPoolExecutor
    def one(path):
        try:metadata(path,executable)
        except (OSError,ValueError):pass
    unique=list(dict.fromkeys(str(p) for p in paths))
    if len(unique)<2:return
    with ThreadPoolExecutor(min(workers,len(unique))) as pool:list(pool.map(one,unique))

"""Exclusão recuperável: Lixeira do sistema quando existe; senão, uma pasta de recuperação ao lado do material."""
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path


def _mac(path):
    tool = Path('/usr/bin/trash')
    if tool.is_file():
        return subprocess.run([str(tool), str(path)], capture_output=True, timeout=120).returncode == 0
    script = 'tell application "Finder" to delete (POSIX file ' + json.dumps(str(path)) + ')'
    return subprocess.run(['osascript', '-e', script], capture_output=True, timeout=120).returncode == 0


def _windows(path):
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT), ('pFrom', wintypes.LPCWSTR), ('pTo', wintypes.LPCWSTR),
                    ('fFlags', ctypes.c_uint16), ('fAnyOperationsAborted', wintypes.BOOL), ('hNameMappings', ctypes.c_void_p),
                    ('lpszProgressTitle', wintypes.LPCWSTR)]
    # FO_DELETE com FOF_ALLOWUNDO manda para a Lixeira; sem janelas de confirmação.
    op = SHFILEOPSTRUCTW(None, 3, str(path) + '\0', None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted


def recovery_folder(path):
    """Pasta oculta de recuperação no mesmo disco, quando a Lixeira do sistema não aceita o item."""
    return Path(path).resolve().parent / '.Recuperar Ripagem Maker'


def to_trash(path):
    """Move para a Lixeira e confirma que o item saiu do lugar. Nunca apaga definitivamente."""
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return {'caminho': str(path), 'destino': 'ja_ausente'}
    ok = False
    try:
        if sys.platform == 'darwin':
            ok = _mac(path)
        elif os.name == 'nt':
            ok = _windows(path)
        else:
            ok = False
    except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
        ok = False
    if ok and not path.exists():
        return {'caminho': str(path), 'destino': 'lixeira'}
    folder = recovery_folder(path) / time.strftime('%Y-%m-%d_%H%M%S')
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / path.name
    if target.exists():
        target = folder / f'{path.stem}_{uuid.uuid4().hex[:6]}{path.suffix}'
    shutil.move(str(path), str(target))
    return {'caminho': str(path), 'destino': 'recuperacao', 'recuperar_em': str(target)}

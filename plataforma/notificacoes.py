"""Avisos locais de conclusão, independentes da página aberta."""
import base64
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from . import armazenamento as S

MIN_SECONDS = 5
SYNC_TASKS = {
    '/frases': 'Busca e recorte de falas',
    '/precos/aplicar': 'Troca de preços e kits',
    '/alinhar': 'Alinhamento dos trechos',
    '/fatiador/premiere': 'Exportação para o Premiere',
    '/fatiador/corrigir-srt': 'Correção da legenda SRT',
    '/fatiador/trocas/ofertas-adaptar': 'Adaptação de ofertas',
    '/fatiador/trocas/exportar': 'Exportação do XML',
    '/fatiador/trocas/visual-detectar': 'Identificação de menções para os takes',
    '/fatiador/trocas/visual-exportar': 'Exportação dos takes',
    '/fatiador/trocas/entrega': 'Entrega para o Premiere',
    '/api/atualizar': 'Atualização do aplicativo',
}
# Estes tipos recebem nomes de mídias no título do job.
PRIVATE_TITLES = {'analise': 'Análise de vídeo', 'render': 'Renderização de montagem'}
MESSAGES = {
    'concluido': 'Tarefa concluída',
    'erro': 'Tarefa interrompida por um erro',
    'pendente': 'Tarefa precisa de atenção',
}
OUTBOX = queue.Queue(maxsize=32)
START_LOCK = threading.Lock()
worker = None

MAC_SCRIPT = '''
on run argv
    display notification (item 1 of argv) with title "Ripagem Maker"
end run
'''
WINDOWS_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
$message = ConvertFrom-Json -InputObject ([Console]::In.ReadToEnd())
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$tray = [System.Windows.Forms.NotifyIcon]::new()
try {
    $tray.Icon = [System.Drawing.SystemIcons]::Information
    $tray.Text = 'Ripagem Maker'
    $tray.Visible = $true
    $tray.ShowBalloonTip(10000, 'Ripagem Maker', [string]$message, [System.Windows.Forms.ToolTipIcon]::Info)
    $deadline = [DateTime]::UtcNow.AddSeconds(12)
    while ([DateTime]::UtcNow -lt $deadline) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 150
    }
} finally {
    $tray.Dispose()
}
'''


def command(message):
    if sys.platform == 'darwin':
        return ['/usr/bin/osascript', '-e', MAC_SCRIPT, '--', message], {}
    if sys.platform == 'win32':
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        code = base64.b64encode(WINDOWS_SCRIPT.encode('utf-16-le')).decode('ascii')
        return [str(powershell), '-NoProfile', '-NonInteractive', '-STA', '-EncodedCommand', code], {
            'input': json.dumps(message).encode('utf-8'),
            'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        }
    return None, {}


def settings(enabled=None):
    if enabled is not None:
        if type(enabled) is not bool:
            raise ValueError('Escolha ligar ou desligar as notificações.')
        with S.LOCK:
            config = S.read()
            config['notificacoes_tarefas'] = enabled
            S.write_config(config)
    return {'ativo': S.read().get('notificacoes_tarefas') is True,
            'disponivel': sys.platform in ('darwin', 'win32'),
            'sistema': 'macos' if sys.platform == 'darwin' else 'windows' if sys.platform == 'win32' else ''}


def dispatch(message):
    args, options = command(message)
    if args:
        subprocess.run(args, **options, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=20, check=True)


def _deliver():
    while True:
        message = OUTBOX.get()
        try:
            if settings()['ativo']:
                dispatch(message)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            # A notificação é auxiliar e jamais muda o resultado ou a fila da tarefa.
            print(f'Notificações: envio ao sistema indisponível ({type(error).__name__}).', file=sys.stderr)
        finally:
            OUTBOX.task_done()


def enqueue(message):
    global worker
    state = settings()
    if not state['ativo'] or not state['disponivel']:
        return False
    try:
        OUTBOX.put_nowait(message)
    except queue.Full:
        return False
    with START_LOCK:
        if worker is None:
            worker = threading.Thread(target=_deliver, name='notificacoes', daemon=True)
            worker.start()
    return True


def send_test():
    if not enqueue('Este é um aviso de teste das notificações de tarefas.'):
        raise ValueError('Ative as notificações em um Mac ou Windows para enviar o teste.')
    return {'solicitada': True}


def finished(title, status, seconds, result=None, minimum=MIN_SECONDS):
    if seconds < minimum or status not in ('concluido', 'erro'):
        return
    data = result if isinstance(result, dict) else {}
    rows = data.get('resultados')
    if status == 'concluido' and (
        data.get('pendencia') or data.get('pendencias') or data.get('para_revisar')
        or (isinstance(rows, list) and any(isinstance(r, dict) and
             (r.get('erro') or r.get('status') in ('regenerar_longo', 'regenerar_curto')) for r in rows))
    ):
        status = 'pendente'
    try:
        enqueue(f'{MESSAGES[status]}: {title}.')
    except (OSError, ValueError, TypeError):
        pass


def queued_job(job):
    finished(PRIVATE_TITLES.get(job.kind, job.title), job.status,
             max(0, job.finished - job.created), job.result,
             minimum=0 if job.kind == 'ripagem_automatica' else MIN_SECONDS)

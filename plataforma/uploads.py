"""Recebe mídia por blocos; só publica um envio completo e com espaço disponível."""
import shutil
from pathlib import Path
import uuid

def check(length, directory):
    """Confere o envio antes de o navegador transmitir um vídeo grande.

    A conferência também é repetida por receive: o espaço pode mudar entre
    a consulta e o envio. A consulta nunca cria uma tarefa de transcrição.
    """
    if isinstance(length, bool) or isinstance(length, float) and not length.is_integer():
        raise ValueError('Tamanho do arquivo inválido. Selecione o arquivo novamente.')
    try: length = int(length)
    except (ValueError, TypeError): raise ValueError('Tamanho do arquivo inválido. Selecione o arquivo novamente.')
    if not 0 < length <= 20 * 1024**3:
        raise ValueError('Escolha um arquivo de até 20 GB, com tamanho maior que zero.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(directory).free
    required = length + 256 * 1024**2
    if free < required:
        gb = lambda value: f'{value / 1_000_000_000:.2f}'.replace('.', ',')
        raise ValueError(f'Espaço insuficiente para receber o arquivo de {gb(length)} GB. '
                         f'Há {gb(free)} GB livres; são necessários pelo menos {gb(required)} GB. '
                         'Libere espaço no disco do aplicativo ou escolha um arquivo menor antes de tentar novamente. '
                         'Nenhuma transcrição foi iniciada.')
    return {'ok': True, 'bytes': length, 'livres': free, 'necessarios': required}


def receive(stream, length, destination):
    destination = Path(destination)
    info = check(length, destination.parent)
    length = info['bytes']
    if destination.exists(): raise ValueError('O arquivo de destino já existe. Tente novamente.')
    temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.partial')
    try:
        with temporary.open('xb') as output:
            remaining = length
            while remaining:
                chunk = stream.read(min(1024**2, remaining))
                if not chunk: raise ValueError('O envio foi interrompido. Selecione o arquivo e tente novamente; nenhum processamento foi iniciado.')
                output.write(chunk)
                remaining -= len(chunk)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination

"""Projetos (trabalhos da troca de potes): identificação, favoritos, referências e mudança de pasta segura."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import armazenamento as S

LOCK = threading.RLock()
META = 'projeto.json'
JOURNAL = S.PROJECT / 'plataforma/workspace/movimentos.json'
MEDIA = {'.mp4', '.mov', '.m4v', '.mkv', '.webm', '.mp3', '.wav', '.m4a', '.aac', '.png', '.jpg', '.jpeg'}


def key(path):
    """Forma única para comparar caminhos: NFC e, no Windows, sem diferença de maiúsculas."""
    return os.path.normcase(unicodedata.normalize('NFC', str(path)))


def _slug(text, n):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_')[:n]


def folder_name(project, product='', when=None):
    """Nome identificável: projeto, produto e data (AAAA-MM-DD_HHMMSS para não colidir)."""
    when = when or datetime.now()
    parts = [_slug(project, 50) or 'Projeto']
    product = _slug(product, 30)
    if product and product.casefold() not in parts[0].casefold():
        parts.append(product)
    parts.append(when.strftime('%Y-%m-%d_%H%M%S'))
    return '_'.join(parts)


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def read_meta(out):
    try:
        data = json.loads((Path(out) / META).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_meta(out, **changes):
    with LOCK:
        data = read_meta(out) | changes
        _write_json(Path(out) / META, data)
        return data


def create_meta(out, project, product='', new_product=''):
    return write_meta(out, nome=str(project or Path(out).name), produto=product, produto_novo=new_product,
                      criado=datetime.now().isoformat(timespec='seconds'), favorito=False)


def is_project(path):
    path = Path(path)
    return path.is_dir() and (path / 'transcricao_bruta.json').is_file()


def all_projects():
    seen, rows = set(), []
    for root in S.roots('fatiador'):
        if not root.is_dir():
            continue
        for d in root.iterdir():
            if d.name.startswith('.') or not is_project(d):
                continue
            ident = key(d.resolve())
            if ident in seen:
                continue
            seen.add(ident)
            rows.append(d)
    return rows


def active_folders(exclude=None):
    """Pastas usadas por tarefas na fila ou em andamento (não podem ser movidas nem limpas)."""
    from . import ml_core as M
    result = set()
    for job in list(M.JOBS.values()):
        if job is exclude or job.status not in ('na_fila', 'executando'):
            continue
        out = job.params.get('out') if isinstance(job.params, dict) else None
        if out:
            result.add(key(Path(out).resolve()))
    return result


def moving(out):
    """True enquanto uma tarefa de mudança de pasta usa este projeto: edições esperam para não ficarem na cópia antiga."""
    from . import ml_core as M
    target = key(Path(out).resolve())
    return any(j.kind == 'mover_projeto' and j.status in ('na_fila', 'executando') and key(Path(j.params.get('out', '')).resolve()) == target
               for j in list(M.JOBS.values()) if j.params.get('out'))


def size_of(path):
    total = 0
    for parent, dirs, names in os.walk(path, followlinks=False):
        for name in names:
            p = Path(parent) / name
            try:
                if not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                pass
    return total


def summary(out, with_size=False, *, active=None):
    from . import trocas as T
    out = Path(out)
    folder_stat = out.stat()
    resolved = out.resolve()
    meta = read_meta(out)
    stage, product = 'Transcrição', meta.get('produto_novo') or meta.get('produto') or ''
    try:
        # A listagem só precisa do estado salvo. A revisão do plano fica para a abertura.
        plan = json.loads(T.plan_path(out).read_text(encoding='utf-8'))
    except (OSError, ValueError, KeyError):
        plan = None
    if isinstance(plan, dict):
        product = plan.get('produto_novo') or plan.get('produto') or product
        delivery = plan.get('entrega')
        items = plan.get('itens')
        if isinstance(delivery, dict) and delivery.get('xml'):
            stage = 'Entregue'
        elif isinstance(items, list) and all(isinstance(row, dict) for row in items):
            chosen = [row for row in items if row.get('aprovado')]
            approved = chosen and all(isinstance(row.get('audio'), dict) and row['audio'].get('aprovado') for row in chosen)
            stage = 'Takes / entrega' if approved else 'Falas'
    times = []
    for name in ('trocas/plano.json', 'transcricao_bruta.json', META):
        try:
            times.append((out / name).stat().st_mtime)
        except OSError:
            continue
    modified = max(times, default=folder_stat.st_mtime)
    row = {'pasta': out.name, 'caminho': str(resolved), 'nome': meta.get('nome') or out.name, 'produto': product,
           'criado': meta.get('criado') or datetime.fromtimestamp(folder_stat.st_ctime).isoformat(timespec='seconds'),
           'atualizado': modified, 'etapa': stage, 'favorito': bool(meta.get('favorito')),
           'em_uso': key(resolved) in (active_folders() if active is None else active)}
    if with_size:
        row['bytes'] = size_of(out)
    return row


def listing(with_size=False):
    active = active_folders()
    rows = []
    for folder in all_projects():
        try:
            rows.append(summary(folder, with_size, active=active))
        except OSError:
            # O projeto pode ter sido movido durante a listagem.
            continue
    return sorted(rows, key=lambda r: -r['atualizado'])


def find(name):
    folder = S.job_folder(name)
    if not S.is_job(folder) or not is_project(folder):
        raise ValueError('Projeto não encontrado.')
    return folder


def set_favorite(name, value):
    out = find(name)
    write_meta(out, favorito=bool(value))
    return summary(out)


# ------------------------------------------------------------------ referências
def _variants(path):
    """Formas com que o mesmo caminho pode estar gravado: resolvido ou não (no Mac /var = /private/var) e em NFC/NFD."""
    forms = [str(Path(path).absolute()), str(Path(path).resolve())]
    forms += [f[len('/private'):] for f in forms if f.startswith('/private/')]
    return list(dict.fromkeys(v for f in forms for v in (f, unicodedata.normalize('NFC', f), unicodedata.normalize('NFD', f))))


def xml_paths(xml_file):
    """Caminhos absolutos das mídias citadas num XML do Premiere."""
    try:
        text = Path(xml_file).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return set()
    return pathurls(text, os.name == 'nt')


def pathurls(text, windows=False):
    """file:///Users/… (Mac) e file:///C:/… ou file://localhost/C:/… (Windows) viram caminhos comparáveis."""
    result = set()
    for url in re.findall(r'<pathurl>([^<]+)</pathurl>', text):
        u = urlparse(url.strip())
        path = unquote(u.path)
        if windows and re.match(r'^/[A-Za-z]:', path):
            path = path[1:]
        if u.netloc and u.netloc not in ('', 'localhost'):
            path = '//' + u.netloc + path
        if windows:
            path = path.replace('/', '\\')
        result.add(key(path))
    return result


def references(out):
    """Arquivos que o projeto usa: os citados no plano e os citados nos XMLs exportados."""
    out = Path(out)
    used = set()
    for json_file in [out / 'trocas/plano.json', out / 'trocas/visuais/plano.json', out / 'trocas/legendas/estado.json']:
        try:
            text = json_file.read_text(encoding='utf-8')
        except OSError:
            continue
        for value in re.findall(r'"((?:[^"\\]|\\.)*)"', text):
            if '/' not in value and '\\' not in value:
                continue
            value = value.replace('\\\\', '\\')
            candidate = Path(value) if os.path.isabs(value) else out / value
            used.add(key(candidate.resolve()))
    for xml in out.rglob('*.xml'):
        used |= xml_paths(xml)
    for name in ('_fonte.mp4', 'transcricao_bruta.json', 'trocas/plano.json'):
        used.add(key((out / name).resolve()))
    return used


def all_references():
    """Referências de todos os projetos e dos XMLs das Montagens (para a limpeza não remover nada em uso)."""
    used = set()
    for project in all_projects():
        used |= references(project)
    for root in S.roots('montagens'):
        if root.is_dir():
            for xml in root.glob('*.xml'):
                used |= xml_paths(xml)
    return used


# ------------------------------------------------------------------ mudança de pasta
def _journal():
    try:
        return json.loads(JOURNAL.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def _save_journal(rows):
    _write_json(JOURNAL, rows)


def _digest(path, job=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while block := f.read(8 * 1024 ** 2):
            if job is not None and job.cancel:
                from . import ml_core as M
                raise M.Cancelled()
            h.update(block)
    return h.hexdigest()


def check_destination(name, destination, job=None):
    out = find(name)
    dest = Path(str(destination or '')).expanduser()
    if not dest.is_absolute():
        raise ValueError('Escolha a pasta de destino ou informe o caminho completo.')
    dest = dest.resolve()
    if dest == out.parent.resolve():
        raise ValueError('O projeto já está nesta pasta.')
    if dest.is_relative_to(out.resolve()):
        raise ValueError('Escolha uma pasta fora do próprio projeto.')
    if (dest / out.name).exists():
        raise ValueError('Já existe uma pasta com o nome deste projeto no destino.')
    if key(out.resolve()) in active_folders(job):
        raise ValueError('Há uma tarefa usando este projeto. A mudança poderá ser feita assim que ela terminar ou for cancelada.')
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryFile(dir=dest):
            pass
    except OSError:
        raise ValueError('Sem permissão para gravar na pasta de destino.') from None
    need = size_of(out)
    zip_file = out.with_suffix('.zip')
    if zip_file.is_file():
        need += zip_file.stat().st_size
    free = shutil.disk_usage(dest).free
    same_volume = dest.stat().st_dev == out.stat().st_dev
    xmls = stale_xmls(out)
    if free < need * 1.05 + 200 * 1024 ** 2:
        raise ValueError(f'Espaço insuficiente no destino: precisa de {need / 1024 ** 3:.2f} GB e há {free / 1024 ** 3:.2f} GB livres.')
    return {'origem': str(out.resolve()), 'destino': str(dest / out.name), 'bytes': need, 'livre_bytes': free, 'mesmo_disco': same_volume,
            'xmls_a_refazer': xmls}


def _under(value, olds):
    for old in olds:
        if value == old or value.startswith(old + '/') or value.startswith(old + '\\'):
            return old
    return None


def _rewrite_paths(folder, old, new):
    """Atualiza caminhos absolutos gravados nos JSON do projeto (plano, takes, legendas). Mídias externas ficam como estão."""
    changed = []
    olds = sorted(_variants(old), key=len, reverse=True)
    new = str(new)
    def walk(value):
        if isinstance(value, str):
            hit = _under(unicodedata.normalize('NFC', value), [unicodedata.normalize('NFC', o) for o in olds])
            return new + unicodedata.normalize('NFC', value)[len(hit):] if hit else value
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value
    for json_file in Path(folder).rglob('*.json'):
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        updated = walk(data)
        if updated != data:
            _write_json(json_file, updated)
            changed.append(str(json_file.relative_to(folder)))
    return changed


def stale_xmls(out):
    """XMLs exportados que apontam para mídias dentro do projeto (precisam ser gerados de novo depois da mudança)."""
    olds = [key(v) for v in _variants(out)]
    return [str(x.relative_to(out)) for x in Path(out).rglob('*.xml') if any(_under(p, olds) for p in xml_paths(x))]


def move_job(job, name, destination, out=None):
    """Copia, confere byte a byte (SHA-256), atualiza referências e só então manda a origem para a Lixeira."""
    from . import lixeira
    check = check_destination(name, destination, job)
    out, final = Path(check['origem']), Path(check['destino'])
    partial = final.with_name('.' + final.name + '.copiando')
    entry = {'id': uuid.uuid4().hex[:10], 'origem': str(out), 'destino': str(final), 'parcial': str(partial), 'etapa': 'copiando', 'inicio': time.time()}
    with LOCK:
        rows = _journal()
        rows.append(entry)
        _save_journal(rows)
    def stage(value, **extra):
        with LOCK:
            rows = _journal()
            for r in rows:
                if r['id'] == entry['id']:
                    r.update(etapa=value, **extra)
            _save_journal(rows)
    files = [p for p in out.rglob('*') if p.is_file() and not p.is_symlink()]
    zip_file = out.with_suffix('.zip')
    total = sum(p.stat().st_size for p in files) or 1
    copied = 0
    job.step = 'Copiando o projeto'
    try:
        for p in files:
            if job.cancel:
                from . import ml_core as M
                raise M.Cancelled()
            target = partial / p.relative_to(out)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            copied += p.stat().st_size
            job.pct = 0.8 * copied / total
            job.progress = {'tipo': 'mover', 'fase': 'Copiando arquivos', 'processadas': copied, 'total': total, 'indeterminado': False}
        job.step = 'Conferindo a cópia'
        checked = 0
        for p in files:
            target = partial / p.relative_to(out)
            if target.stat().st_size != p.stat().st_size or _digest(target, job) != _digest(p, job):
                raise RuntimeError('A cópia de ' + p.name + ' não confere com o original. Nada foi removido.')
            checked += p.stat().st_size
            job.pct = 0.8 + 0.15 * checked / total
            job.progress = {'tipo': 'mover', 'fase': 'Conferindo a cópia', 'processadas': checked, 'total': total, 'indeterminado': False}
        job.step = 'Atualizando referências internas'
        rewritten = _rewrite_paths(partial, out, final)
        os.replace(partial, final)
        if zip_file.is_file():
            shutil.copy2(zip_file, final.with_suffix('.zip'))
        stage('copiado', reescritos=rewritten)
        S.add_project_root(final.parent)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        stage('cancelado')
        raise
    job.step = 'Enviando a pasta antiga para a Lixeira'
    trashed = [lixeira.to_trash(out)]
    if zip_file.is_file():
        trashed.append(lixeira.to_trash(zip_file))
    stage('concluido', lixeira=trashed)
    job.pct = 1
    job.step = 'Projeto movido'
    return {'origem': str(out), 'destino': str(final), 'arquivos': len(files), 'bytes': total, 'referencias_atualizadas': rewritten,
            'xmls_a_refazer': check['xmls_a_refazer'], 'lixeira': trashed,
            'observacao': 'A pasta antiga foi para a Lixeira (recuperável). ' + ('Gere o XML novamente: os XMLs já exportados ainda apontam para o local antigo.' if check['xmls_a_refazer'] else 'Nenhum XML exportado apontava para o local antigo.')}


def recover_moves():
    """Ao abrir o app: desfaz cópias interrompidas e conclui as que já estavam conferidas. A origem só sai depois de conferida."""
    from . import lixeira
    report = []
    with LOCK:
        rows = _journal()
        for r in rows:
            if r.get('etapa') == 'copiando':
                partial = Path(r['parcial'])
                if partial.exists():
                    shutil.rmtree(partial, ignore_errors=True)
                r['etapa'] = 'interrompido'
                report.append({'projeto': Path(r['origem']).name, 'acao': 'Cópia interrompida descartada; o projeto continua no local original.'})
            elif r.get('etapa') == 'copiado':
                final, origin = Path(r['destino']), Path(r['origem'])
                if final.is_dir() and is_project(final):
                    S.add_project_root(final.parent)
                    if origin.exists():
                        r['lixeira'] = [lixeira.to_trash(origin)]
                    r['etapa'] = 'concluido'
                    report.append({'projeto': final.name, 'acao': 'Mudança concluída após reabrir o app; a pasta antiga foi para a Lixeira.'})
                else:
                    r['etapa'] = 'interrompido'
                    report.append({'projeto': origin.name, 'acao': 'A cópia não foi encontrada; o projeto continua no local original.'})
        _save_journal(rows[-50:])
    return report

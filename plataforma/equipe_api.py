"""Rotas locais de autenticação da equipe e atribuição dos projetos."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import equipe_auth as auth
from .api import STATIC, _send


PAGES = {'/', '/painel', '/fatiador'}
PUBLIC_GET = {'/api/recursos', '/api/desktop/status'}
NEW_PROJECT = {'/upload/check', '/upload', '/api/ml/upload'}


def authorize(handler, method, path):
    """Resolve a sessão no servidor antes de acessar projetos, mídias ou ferramentas."""
    handler.editor_profile = None
    if method == 'GET' and (path in PUBLIC_GET or path.startswith('/static/')):
        return True
    try:
        handler.editor_profile = auth.require_active(online=method == 'POST' and path in NEW_PROJECT)
        return True
    except auth.AuthError as error:
        if method == 'GET' and path in PAGES:
            target = '/fatiador' if path == '/fatiador' else '/'
            _send(handler, 303, b'', extra={'Location': '/entrar?voltar=' + target})
        else:
            _send(handler, error.status_code, {'erro': str(error), 'estado': error.estado})
        return False


def _body(handler):
    size = int(handler.headers.get('Content-Length', '0'))
    if not 0 <= size <= 8_192:
        raise ValueError('Solicitação inválida.')
    if not size:
        return {}
    if handler.headers.get_content_type() != 'application/json':
        raise ValueError('Envie os dados no formato JSON.')
    data = json.loads(handler.rfile.read(size))
    if not isinstance(data, dict):
        raise ValueError('Solicitação inválida.')
    return data


def handle(handler, method, path):
    if method == 'GET' and path == '/entrar':
        _send(handler, 200, (STATIC / 'entrar.html').read_bytes(), 'text/html; charset=utf-8')
        return True
    if not path.startswith('/api/equipe/'):
        return False
    try:
        if method == 'GET' and path == '/api/equipe/relatorios':
            query = parse_qs(urlsplit(handler.path).query)
            result = auth.get_reports(offset=int(query.get('offset', ['0'])[0]))
        elif method == 'GET' and path == '/api/equipe/relatorio-xml':
            from . import armazenamento, relatorio_ripagem
            profile = auth.require_active(online=False)
            if not profile:
                raise auth.AuthError('Entre com a conta da equipe.', 401)
            folder = parse_qs(urlsplit(handler.path).query).get('folder', [''])[0]
            out = armazenamento.job_folder(folder)
            if not armazenamento.is_job(out):
                raise ValueError('Projeto indisponível.')
            result = relatorio_ripagem.read(out, profile)
        elif method == 'GET' and path == '/api/equipe/sessao':
            result = auth.status()
        elif method == 'POST':
            if handler.headers.get('Origin') == 'null':
                _send(handler, 403, {'erro': 'Abra o login na janela do Ripagem Maker.'})
                return True
            data = _body(handler)
            if path == '/api/equipe/entrar':
                result = auth.login(data.get('email'), data.get('senha'))
                from . import relatorio_ripagem
                relatorio_ripagem.schedule_sync(result['perfil']['id'])
            elif path == '/api/equipe/sair':
                result = auth.logout()
            elif path == '/api/equipe/recuperar':
                result = auth.request_recovery(data.get('email'))
            elif path == '/api/equipe/redefinir':
                result = auth.reset_password(data.get('email'), data.get('codigo'), data.get('nova_senha'),
                                             convite=data.get('convite') is True)
            elif path == '/api/equipe/atividade':
                auth.activity()
                profile = auth.cached_profile()
                if profile:
                    from . import relatorio_ripagem
                    relatorio_ripagem.schedule_sync(profile['id'])
                result = {'ok': True}
            elif path == '/api/equipe/fechar':
                auth.close_session()
                result = {'ok': True}
            elif path == '/api/equipe/relatorio-feedback':
                from . import armazenamento, relatorio_ripagem
                profile = auth.require_active(online=False)
                if not profile:
                    raise auth.AuthError('Entre com a conta da equipe.', 401)
                out = armazenamento.job_folder(data.get('folder', ''))
                if not armazenamento.is_job(out):
                    raise ValueError('Projeto indisponível.')
                result = relatorio_ripagem.feedback(out, profile, data)
            elif path == '/api/equipe/admin':
                result = auth.admin(data.get('acao'), data)
            else:
                _send(handler, 404, {'erro': 'Ação de conta desconhecida.'})
                return True
        else:
            _send(handler, 404, {'erro': 'Ação de conta desconhecida.'})
            return True
        _send(handler, 200, result if result is not None else {'ok': True})
    except auth.AuthError as error:
        _send(handler, error.status_code, {'erro': str(error), 'estado': error.estado})
    except PermissionError as error:
        _send(handler, 403, {'erro': str(error)})
    except (ValueError, UnicodeError, TypeError):
        _send(handler, 400, {'erro': 'Confira os dados e tente novamente.'})
    return True


def project_created(out, profile, applied):
    if not profile:
        return
    from . import projetos
    metadata = projetos.write_meta(out, projeto_id=str(uuid.uuid4()), criado_por=profile['id'])
    auth.record_event('projeto_criado', perfil=profile, projeto_id=metadata['projeto_id'], codigo_aplicado=applied)


def xml_saved(out, profile, result, applied):
    if not profile or not result.get('medicao_encerrada'):
        return
    from . import projetos
    with projetos.LOCK:
        metadata = projetos.read_meta(out)
        project_id = metadata.get('projeto_id') or str(uuid.uuid4())
        event = {'usuario': profile['id'], 'codigo_aplicado': applied,
                 'quando': datetime.now(timezone.utc).isoformat(),
                 'xml': Path(result['xml_salvo']).name}
        projetos.write_meta(out, projeto_id=project_id, ultimo_xml_salvo_por=event)
    auth.record_event('xml_salvo', perfil=profile, projeto_id=project_id, codigo_aplicado=applied)
    from . import relatorio_ripagem
    if 'app_min' in result:
        try:
            relatorio_ripagem.saved(out, profile, result, applied)
        except OSError:
            result['aviso_relatorio'] = 'XML salvo. Não foi possível gravar o relatório local.'

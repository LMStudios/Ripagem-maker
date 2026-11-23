"""Conta do Ripagem Maker. Só a sessão e o perfil consultam o Supabase."""
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
from threading import RLock
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import requests

from . import armazenamento, segredos

CONFIG = armazenamento.PROJECT / 'plataforma/workspace/equipe_auth.json'
EVENTOS = CONFIG.parent / 'eventos'
VALIDADE_PERFIL_S = 30
INTERVALO_ATIVIDADE_S = 60
TIMEOUT = (3, 5)
REPORT_FIELDS = ('projeto_id', 'tempo_ripagem_ms', 'espera_ms', 'retrabalho_ms', 'fora_app_ms',
                 'xml_revisao', 'pendencias_visuais', 'tentativas', 'falhas', 'medicao_completa', 'versao_app',
                 'sistema', 'etapas_ms', 'feedback_etapa', 'visuais', 'revisao')
REPORT_TIMES = ('tempo_ripagem_ms', 'espera_ms', 'retrabalho_ms', 'fora_app_ms')
REPORT_STEPS = frozenset(('transcricao', 'voz', 'busca_visual', 'takes', 'exportacao'))
MAX_TIME_MS = 30 * 24 * 60 * 60 * 1000
REPORT_COUNT_MAX = 100000
REPORT_REVISION_MAX = 9007199254740991
VISUAL_COUNTS = frozenset(('sugeridas', 'aprovadas', 'descartadas', 'manuais', 'marcadas'))


class AuthError(ValueError):
    def __init__(self, mensagem, status_code=400, estado='aguardando_login', *, codigo_remoto=''):
        super().__init__(mensagem)
        self.status_code = status_code
        self.estado = estado
        self.codigo_remoto = codigo_remoto


def _unavailable():
    return AuthError('Serviço de login indisponível. Tente novamente em instantes.', 503, 'indisponivel')


@dataclass(frozen=True)
class _Config:
    url: str
    public_key: str = field(repr=False)

    @property
    def credential_name(self):
        return 'supabase_refresh_' + sha256(self.url.encode()).hexdigest()[:20]


@dataclass
class _Tokens:
    access: str = field(repr=False)
    refresh: str = field(repr=False)
    expires_at: float


def _publishable(value):
    if not isinstance(value, str) or len(value) > 4096:
        return False
    if re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]{12,}', value):
        return True
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', value):
        return False
    # A chave legada "anon" é pública. Recusa JWTs de outras funções.
    try:
        payload = value.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))).get('role') == 'anon'
    except (ValueError, AttributeError):
        return False


def _configuration():
    url = os.environ.get('RIPAGEM_SUPABASE_URL')
    key = os.environ.get('RIPAGEM_SUPABASE_CHAVE_PUBLICA')
    if url is None and key is None:
        if not CONFIG.exists():
            return None
        try:
            data = json.loads(CONFIG.read_text(encoding='utf-8'))
            url, key = data.get('url'), data.get('chave_publica')
        except (OSError, ValueError, AttributeError):
            url, key = None, None
    url = url.strip().rstrip('/') if isinstance(url, str) else ''
    key = key.strip() if isinstance(key, str) else ''
    try:
        origin = urlsplit(url)
        hostname = origin.hostname or ''
        # O endereço local é reservado ao Supabase de desenvolvimento.
        host_supported = (
            origin.scheme == 'https' and origin.port in (None, 443)
            and re.fullmatch(r'[a-z0-9-]+\.supabase\.co', hostname)
        ) or (origin.scheme == 'http' and hostname in ('localhost', '127.0.0.1') and origin.port)
        valid_url = host_supported and not (
            origin.username or origin.password or origin.path or origin.query or origin.fragment
            or re.search(r'[\s\\]', url)
        )
    except ValueError:
        valid_url = False
    if not valid_url or not _publishable(key):
        raise AuthError('Confira a URL do projeto e a chave pública do Supabase na configuração do login.',
                        503, 'configuracao_invalida')
    return _Config(url, key)


def _credential(action, *args):
    try:
        return getattr(segredos, action)(*args)
    except RuntimeError as error:
        raise AuthError(str(error), 503, 'cofre_indisponivel') from None


def _remote(config, method, route, *, token=None, body=None, query=None, prefer=None):
    headers = {'apikey': config.public_key}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if prefer:
        headers['Prefer'] = prefer
    try:
        response = requests.request(method, config.url + route, headers=headers, json=body,
                                    params=query, allow_redirects=False, timeout=TIMEOUT)
    except requests.RequestException:
        raise _unavailable() from None
    if response.status_code >= 500 or 300 <= response.status_code < 400:
        raise _unavailable()
    data = {}
    if response.content:
        try:
            data = response.json()
        except ValueError:
            raise _unavailable() from None
    if not 200 <= response.status_code < 300:
        code = data.get('error_code') or data.get('code') if isinstance(data, dict) else ''
        if response.status_code == 429:
            message = 'Muitas tentativas. Aguarde alguns instantes antes de repetir.'
        elif response.status_code in (401, 403):
            message = 'Acesso não autorizado. Confira os dados ou entre novamente.'
        else:
            message = 'Não foi possível concluir. Confira os dados e tente novamente.'
        raise AuthError(message, response.status_code, codigo_remoto=code)
    return data


def _tokens(data):
    try:
        access = data['access_token']
        refresh = data['refresh_token']
        expires = int(data['expires_in'])
        if not all(isinstance(value, str) and 0 < len(value) <= 65536 for value in (access, refresh)):
            raise ValueError
        if not 0 < expires <= 86400:
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _unavailable() from None
    return _Tokens(access, refresh, time.monotonic() + expires)


def _email(value):
    if isinstance(value, str):
        value = value.strip()
        if len(value) <= 254 and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
            return value
    raise AuthError('Informe um e-mail válido.')


def _password(value, *, new=False):
    try:
        size = len(value.encode('utf-8')) if isinstance(value, str) else 0
    except UnicodeEncodeError:
        size = 0
    if not 1 <= size <= 72:
        raise AuthError('Informe uma senha de até 72 bytes.')
    if new and len(value) < 8:
        raise AuthError('Use pelo menos oito caracteres na nova senha.')
    return value


def _identifier(value):
    return str(UUID(value))


def _report_ids(row):
    if not isinstance(row, dict):
        raise AuthError('Relatório inválido.')
    try:
        return _identifier(row['projeto_id']), _identifier(row['usuario'])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AuthError('O relatório precisa de um projeto e um editor identificados.') from None


def _report_payload(row, project_id):
    # O dono é atribuído no Postgres a partir do JWT. São enviados só os campos de acompanhamento.
    payload = dict(projeto_id=project_id)
    for key in REPORT_TIMES:
        value = row.get(key)
        if value is not None and (type(value) is not int or not 0 <= value <= MAX_TIME_MS):
            raise AuthError('Os tempos do relatório devem estar entre zero e 30 dias.')
        payload[key] = value
    for key in ('pendencias_visuais', 'tentativas', 'falhas'):
        value = row.get(key, 0)
        if type(value) is not int or not 0 <= value <= REPORT_COUNT_MAX:
            raise AuthError('Contagem inválida no relatório.')
        payload[key] = value
    for key in ('xml_revisao', 'medicao_completa'):
        value = row.get(key, False)
        if type(value) is not bool:
            raise AuthError('Estado inválido no relatório.')
        payload[key] = value
    steps = row.get('etapas_ms', {})
    if not isinstance(steps, dict) or steps.keys() - REPORT_STEPS or any(
            type(value) is not int or not 0 <= value <= MAX_TIME_MS for value in steps.values()):
        raise AuthError('As etapas do relatório devem conter durações válidas.')
    payload['etapas_ms'] = steps
    version = row.get('versao_app')
    if version is not None and (not isinstance(version, str) or not re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,4}){2}', version)):
        raise AuthError('Versão inválida no relatório.')
    payload['versao_app'] = version
    system = row.get('sistema', {'Darwin': 'macOS', 'Windows': 'Windows', 'Linux': 'Linux'}.get(platform.system(), 'Outro'))
    if system is not None and system not in ('macOS', 'Windows', 'Linux', 'Outro'):
        raise AuthError('Sistema inválido no relatório.')
    payload['sistema'] = system
    feedback_step = row.get('feedback_etapa')
    if feedback_step is not None and (not isinstance(feedback_step, str)
                                     or feedback_step not in REPORT_STEPS | {'legenda', 'outro'}):
        raise AuthError('Etapa de feedback inválida.')
    payload['feedback_etapa'] = feedback_step
    visual_counts = row.get('visuais', {})
    if not isinstance(visual_counts, dict) or visual_counts.keys() - VISUAL_COUNTS or any(
            type(value) is not int or not 0 <= value <= REPORT_COUNT_MAX for value in visual_counts.values()):
        raise AuthError('Contagens visuais inválidas no relatório.')
    payload['visuais'] = visual_counts
    version_number = row.get('revisao', 1)
    if type(version_number) is not int or not 1 <= version_number <= REPORT_REVISION_MAX:
        raise AuthError('Revisão inválida no relatório.')
    payload['revisao'] = version_number
    return payload


def _access_rejected():
    return AuthError('Este acesso está desativado ou o perfil ainda precisa ser configurado. Consulte o administrador.',
                     403, 'sem_acesso')


def _verified_profile(config, tokens):
    user = _remote(config, 'GET', '/auth/v1/user', token=tokens.access)
    try:
        user_id = _identifier(user['id'])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _unavailable() from None
    profiles = _remote(config, 'GET', '/rest/v1/perfis', token=tokens.access,
                       query={'select': 'id,nome,codigo,funcao,ativo', 'id': f'eq.{user_id}', 'limit': 2})
    if not isinstance(profiles, list):
        raise _unavailable()
    if len(profiles) != 1 or not isinstance(profiles[0], dict):
        raise _access_rejected()
    profile = profiles[0]
    name = profile.get('nome')
    code = profile.get('codigo')
    if (profile.get('id') != user_id or profile.get('ativo') is not True
            or profile.get('funcao') not in ('editor', 'administrador')
            or not isinstance(name, str) or not 1 <= len(name.strip()) <= 120
            or not isinstance(code, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{0,23}', code)):
        raise _access_rejected()
    return {'id': user_id, 'nome': name.strip(), 'codigo': code, 'funcao': profile['funcao'], 'ativo': True}


def _terminate_remote(config, tokens):
    try:
        _remote(config, 'POST', '/auth/v1/logout', token=tokens.access, query={'scope': 'local'})
    except AuthError:
        # O logout local sempre remove a credencial deste computador.
        pass


def _event(user_id, session, kind, **details):
    path = EVENTOS / (user_id + '.jsonl')
    try:
        path.parent.mkdir(exist_ok=True, parents=True)
        version = (armazenamento.PROJECT / 'VERSION').read_text(encoding='utf-8').strip()
        event = {'id': str(uuid4()), 'sessao': session, 'usuario': user_id, 'tipo': kind,
                 'quando': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                 'versao_app': version, 'sistema': platform.system(), **details}
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
    except OSError:
        print('Aviso: não foi possível registrar um evento da sessão no computador.', flush=True)


class _Equipe:
    def __init__(self):
        self.lock = RLock()
        self.config = None
        self.tokens = None
        self.profile = None
        self.checked_at = 0.
        self.offline_at = None
        self.presence = None
        self.last_activity = 0.
        self.has_checked_keyring = False

    def _use_config(self):
        try:
            config = _configuration()
        except AuthError:
            self.__clear()
            self.config = None
            self.has_checked_keyring = False
            raise
        if self.config != config:
            if self.presence and self.profile:
                _event(self.profile['id'], self.presence, 'configuracao_alterada')
            self.__clear()
            self.config = config
            self.has_checked_keyring = False
        return config

    def __clear(self):
        self.tokens = None
        self.profile = None
        self.checked_at = 0.
        self.offline_at = None
        self.presence = None

    def _presence(self, kind):
        self.presence = str(uuid4())
        self.last_activity = time.monotonic()
        _event(self.profile['id'], self.presence, kind)

    def _record_profile(self, profile, kind):
        self.profile = profile
        self.checked_at = time.monotonic()
        self.offline_at = None
        if not self.presence:
            self._presence(kind)

    def _refresh(self, refresh):
        data = _remote(self.config, 'POST', '/auth/v1/token',
                       query={'grant_type': 'refresh_token'}, body={'refresh_token': refresh})
        fresh = _tokens(data)
        _credential('set', self.config.credential_name, fresh.refresh)
        self.tokens = fresh
        return fresh

    def _end(self, kind, *, retain_session=False):
        try:
            if not retain_session:
                _credential('delete', self.config.credential_name)
            if self.presence and self.profile:
                _event(self.profile['id'], self.presence, kind)
        finally:
            if retain_session:
                self.presence = None
            else:
                self.__clear()
                self.has_checked_keyring = True

    def _profile(self, *, force):
        now = time.monotonic()
        if self.offline_at is not None and now - self.offline_at < 5:
            raise _unavailable()
        if self.tokens is None and self.has_checked_keyring:
            raise AuthError('Entre com sua conta para continuar.', 401)
        if (not force and self.profile and self.offline_at is None
                and now - self.checked_at < VALIDADE_PERFIL_S
                and self.tokens.expires_at > now + 30):
            return self.profile
        try:
            if self.tokens is None:
                refresh = _credential('get', self.config.credential_name)
                if not refresh:
                    self.has_checked_keyring = True
                    raise AuthError('Entre com sua conta para continuar.', 401)
                self._refresh(refresh)
            elif self.tokens.expires_at <= now + 30:
                self._refresh(self.tokens.refresh)
            try:
                profile = _verified_profile(self.config, self.tokens)
            except AuthError as error:
                if error.status_code != 401:
                    raise
                fresh = self._refresh(self.tokens.refresh)
                profile = _verified_profile(self.config, fresh)
            self._record_profile(profile, 'sessao_restaurada')
            return profile
        except AuthError as error:
            if error.estado == 'indisponivel':
                self.offline_at = time.monotonic()
            if not self.has_checked_keyring or self.tokens is not None:
                if error.estado == 'sem_acesso' or error.status_code in (401, 403) or error.codigo_remoto in (
                    'refresh_token_not_found', 'refresh_token_already_used', 'session_not_found', 'session_expired', 'user_banned',
                ):
                    self._end('acesso_encerrado')
            raise

    def status(self):
        with self.lock:
            try:
                if self._use_config() is None:
                    return _status(False, 'desativado')
                profile = self._profile(force=False)
                return _status(True, 'autenticado', profile)
            except AuthError as error:
                cached = self.profile if error.estado == 'indisponivel' else None
                return _status(True, error.estado, cached, str(error))

    def require_active(self, *, online=True):
        with self.lock:
            if self._use_config() is None:
                return None
            try:
                return dict(self._profile(force=online))
            except AuthError as error:
                if not online and self.profile and error.estado == 'indisponivel':
                    return dict(self.profile)
                raise

    def configured(self):
        try:
            return _configuration() is not None
        except AuthError:
            return True

    def cached_profile(self):
        with self.lock:
            if self.config is None or self.profile is None:
                return None
            return dict(self.profile)

    def _enabled(self):
        if self._use_config() is None:
            raise AuthError('Configure a integração de login antes de entrar.', 409, 'desativado')
        return self.config

    def login(self, email, senha):
        with self.lock:
            config = self._enabled()
            payload = {'email': _email(email), 'password': _password(senha)}
            try:
                response = _remote(config, 'POST', '/auth/v1/token', query={'grant_type': 'password'}, body=payload)
            except AuthError as error:
                if error.codigo_remoto == 'user_banned':
                    raise _access_rejected() from None
                if error.codigo_remoto in ('invalid_credentials', 'email_not_confirmed'):
                    raise AuthError('Confira o e-mail, a senha e se o convite foi aceito.', 401) from None
                raise
            tokens = _tokens(response)
            try:
                profile = _verified_profile(config, tokens)
                _credential('set', config.credential_name, tokens.refresh)
            except AuthError:
                _terminate_remote(config, tokens)
                raise
            previous = self.tokens
            if self.presence and self.profile:
                _event(self.profile['id'], self.presence, 'troca_de_conta')
            self.__clear()
            self.tokens = tokens
            self.has_checked_keyring = True
            self._record_profile(profile, 'login_confirmado')
            if previous:
                _terminate_remote(config, previous)
            return _status(True, 'autenticado', profile)

    def logout(self):
        with self.lock:
            config = self._use_config()
            if not config:
                return _status(False, 'desativado')
            tokens = self.tokens
            try:
                self._end('logout')
            finally:
                if tokens:
                    _terminate_remote(config, tokens)
            return _status(True, 'aguardando_login')

    def activity(self):
        with self.lock:
            if self.profile and self.presence:
                now = time.monotonic()
                if now - self.last_activity >= INTERVALO_ATIVIDADE_S:
                    _event(self.profile['id'], self.presence, 'atividade')
                    self.last_activity = now

    def close_session(self):
        with self.lock:
            if self.profile and self.presence:
                self._end('fechamento_normal', retain_session=True)

    def record_event(self, tipo, *, perfil=None, projeto_id=None, codigo_aplicado=None):
        if tipo not in ('projeto_criado', 'xml_salvo'):
            raise ValueError('Evento de projeto inválido.')
        with self.lock:
            profile = perfil if perfil is not None else self.profile
            if not profile:
                return
            details = {'codigo_editor': profile['codigo']}
            if projeto_id is not None:
                details['projeto_id'] = _identifier(projeto_id)
            if codigo_aplicado:
                details['codigo_aplicado'] = str(codigo_aplicado)[:80]
            session = self.presence if self.profile and self.profile['id'] == profile['id'] else None
            _event(_identifier(profile['id']), session, tipo, **details)

    def request_recovery(self, email):
        with self.lock:
            try:
                _remote(self._enabled(), 'POST', '/auth/v1/recover', body={'email': _email(email)})
            except AuthError as error:
                if error.codigo_remoto not in ('user_not_found', 'email_not_confirmed'):
                    raise
            return {'ok': True}

    def reset_password(self, email, codigo, nova_senha, *, convite=False):
        if not isinstance(codigo, str) or not re.fullmatch(r'[0-9]{6,10}', codigo.strip()):
            raise AuthError('Informe o código numérico enviado por e-mail.')
        if not isinstance(convite, bool):
            raise AuthError('Informe um tipo de confirmação válido.')
        with self.lock:
            config = self._enabled()
            password = _password(nova_senha, new=True)
            payload = {'email': _email(email), 'token': codigo.strip(), 'type': 'invite' if convite else 'recovery'}
            try:
                tokens = _tokens(_remote(config, 'POST', '/auth/v1/verify', body=payload))
            except AuthError as error:
                if error.codigo_remoto in ('otp_expired', 'otp_disabled', 'validation_failed'):
                    raise AuthError('Código inválido ou expirado. Confira o último e-mail recebido.') from None
                raise
            try:
                _verified_profile(config, tokens)
                _remote(config, 'PUT', '/auth/v1/user', token=tokens.access, body={'password': password})
            finally:
                _terminate_remote(config, tokens)
            return {'ok': True}

    def sync_report(self, row):
        project_id, author = _report_ids(row)
        payload = _report_payload(row, project_id)
        with self.lock:
            profile = self.require_active()
            if not profile or author != profile['id']:
                raise AuthError('Entre com a conta que fez esta ripagem para enviar o relatório.', 403, 'conta_diferente')
            _remote(self.config, 'POST', '/rest/v1/relatorios_ripagem', token=self.tokens.access,
                    query={'on_conflict': 'projeto_id'}, body=payload,
                    prefer='resolution=merge-duplicates,return=representation,missing=default')
            return {'ok': True}

    def get_reports(self, *, limit=100, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset < 2000000000:
            raise AuthError('Informe uma página válida de relatórios.')
        with self.lock:
            if not self.require_active():
                raise AuthError('Entre com sua conta para ver os relatórios.', 401)
            fields = REPORT_FIELDS + ('usuario', 'criado_em', 'atualizado_em')
            rows = _remote(self.config, 'GET', '/rest/v1/relatorios_ripagem', token=self.tokens.access,
                           query={'select': ','.join(fields), 'order': 'atualizado_em.desc,projeto_id.asc',
                                  'limit': limit, 'offset': offset})
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise _unavailable()
            return {'relatorios': [{key: row[key] for key in fields if key in row} for row in rows],
                    'proximo_offset': offset + limit if len(rows) == limit else None}

    def admin(self, action, data=None):
        if action not in ('listar', 'convidar', 'editar', 'desativar', 'reativar'):
            raise AuthError('Ação de equipe desconhecida.')
        if data is not None and not isinstance(data, dict):
            raise AuthError('Dados da equipe inválidos.')
        with self.lock:
            profile = self.require_active()
            if not profile or profile['funcao'] != 'administrador':
                raise AuthError('A tela Equipe é exclusiva de administradores.', 403)
            # A função revalida a conta e define os campos que cada operação aceita.
            payload = {k: v for k, v in (data or {}).items() if k in ('id', 'email', 'nome', 'codigo')}
            try:
                return _remote(self.config, 'POST', '/functions/v1/equipe-admin',
                               token=self.tokens.access, body=dict(payload, acao=action))
            except AuthError as error:
                messages = {
                    409: 'Já existe uma conta ou código com esses dados, ou a alteração conflita com o acesso atual.',
                    422: 'Confira os dados informados para esta ação.',
                }
                if error.status_code in messages:
                    raise AuthError(messages[error.status_code], error.status_code) from None
                raise


def _status(configured, state, profile=None, message=''):
    return {'configurado': configured, 'autenticado': state == 'autenticado',
            'perfil': dict(profile) if profile else None, 'estado': state, 'mensagem': message}


_instance = _Equipe()

status = _instance.status
login = _instance.login
logout = _instance.logout
require_active = _instance.require_active
configured = _instance.configured
cached_profile = _instance.cached_profile
activity = _instance.activity
close_session = _instance.close_session
request_recovery = _instance.request_recovery
reset_password = _instance.reset_password
admin = _instance.admin
record_event = _instance.record_event
sync_report = _instance.sync_report
get_reports = _instance.get_reports

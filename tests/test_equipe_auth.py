import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from plataforma import equipe_auth as auth


ALICE = 'a7498600-c8d3-4d6e-95b1-b4593b75e496'
BRUNO = 'e2e11cf6-f3d2-41a8-b893-f173c10c4b20'
URL = 'https://ripagem-test.supabase.co'
KEY = 'sb_publishable_fixture_abcdEF12345'
USER = {'id': ALICE}
PROFILE = {'id': ALICE, 'nome': 'Alice Lima', 'codigo': 'EV08', 'funcao': 'editor', 'ativo': True}


def response(status, data=None):
    result = requests.Response()
    result.status_code = status
    result.encoding = 'utf-8'
    result._content = b'' if data is None else json.dumps(data).encode()
    return result


def tokens(access='access1', refresh='refresh1'):
    return {'access_token': access, 'refresh_token': refresh, 'expires_in': 3600}


class TeamAuthTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        self.secrets = {}
        self.auth = auth._Equipe()
        self.now = 1000
        self.config = root / 'login.json'
        self.events = root / 'eventos'
        self.config.write_text(json.dumps({'url': URL, 'chave_publica': KEY}))
        for item in (
            patch.object(auth, 'CONFIG', self.config),
            patch.object(auth, 'EVENTOS', self.events),
            patch.dict(auth.os.environ, {}, clear=True),
            patch.object(auth.segredos, 'get', side_effect=self.secrets.get),
            patch.object(auth.segredos, 'set', side_effect=lambda name, value: self.secrets.update({name: value})),
            patch.object(auth.segredos, 'delete', side_effect=lambda name: self.secrets.pop(name, None)),
            patch.object(auth.time, 'monotonic', side_effect=lambda: self.now),
        ):
            item.start()
            self.addCleanup(item.stop)
        stub = patch.object(auth.requests, 'request')
        self.http = stub.start()
        self.addCleanup(stub.stop)

    def signin(self):
        self.http.side_effect = [response(200, tokens()), response(200, USER), response(200, [PROFILE])]
        return self.auth.login('alice@example.test', 'senha local')

    def history(self, user=ALICE):
        return [json.loads(line) for line in (self.events / (user + '.jsonl')).read_text().splitlines()]

    def test_keeps_legacy_mode_when_supabase_configuration_absent(self):
        self.config.unlink()
        self.assertEqual(self.auth.status()['estado'], 'desativado')
        self.assertIsNone(self.auth.require_active())
        self.http.assert_not_called()

    def test_rejects_invalid_config_instead_of_bypassing_login(self):
        for url, key in (
            ('https://outro-dominio.example', KEY),
            (URL, 'sb_secret_fixture_aBcdEF12345'),
            ('http://127.0.0.1:9999/path', KEY),
        ):
            self.config.write_text(json.dumps({'url': url, 'chave_publica': key}))
            self.assertTrue(self.auth.configured())
            self.assertEqual(self.auth.status()['estado'], 'configuracao_invalida')
            with self.assertRaises(auth.AuthError):
                self.auth.require_active()
        self.http.assert_not_called()

    def test_legacy_key_must_be_anon_and_env_pair_has_precedence(self):
        def jwt(role):
            payload = base64.urlsafe_b64encode(json.dumps({'role': role}).encode()).decode().rstrip('=')
            return f'header.{payload}.sig'

        self.assertTrue(auth._publishable(jwt('anon')))
        self.assertFalse(auth._publishable(jwt('service_role')))
        with patch.dict(auth.os.environ, {'RIPAGEM_SUPABASE_URL': 'http://127.0.0.1:54321',
                                        'RIPAGEM_SUPABASE_CHAVE_PUBLICA': KEY}):
            self.assertEqual(auth._configuration().url, 'http://127.0.0.1:54321')

    def test_verified_login_uses_cofre_and_only_returns_public_profile(self):
        state = self.signin()
        self.assertTrue(state['autenticado'])
        self.assertEqual(state['perfil'], PROFILE)
        self.assertEqual(list(self.secrets.values()), ['refresh1'])
        self.assertNotIn('access1', json.dumps(state))
        self.assertNotIn('refresh1', json.dumps(state))
        self.assertEqual(self.http.call_args_list[1].args[:2], ('GET', URL + '/auth/v1/user'))
        profile_request = self.http.call_args_list[2]
        self.assertEqual(profile_request.kwargs['params']['id'], f'eq.{ALICE}')
        self.assertEqual(profile_request.kwargs['headers']['Authorization'], 'Bearer access1')
        self.assertFalse(profile_request.kwargs['allow_redirects'])
        self.auth.status()
        self.assertEqual(self.http.call_count, 3)
        self.assertEqual(self.history()[0]['tipo'], 'login_confirmado')
        self.assertNotIn('senha local', json.dumps(self.history()))

    def test_startup_rotates_refresh_and_logs_restore_not_another_login(self):
        self.signin()
        self.auth.close_session()
        restored = auth._Equipe()
        self.http.side_effect = [
            response(200, tokens('a2', 'r2')), response(200, USER), response(200, [PROFILE]),
        ]
        self.assertTrue(restored.status()['autenticado'])
        self.assertEqual(list(self.secrets.values()), ['r2'])
        events = self.history()
        self.assertEqual([e['tipo'] for e in events], ['login_confirmado', 'fechamento_normal', 'sessao_restaurada'])
        self.assertNotEqual(events[0]['sessao'], events[-1]['sessao'])

    def test_reconnect_rejects_inactive_profile_and_clears_credential(self):
        self.signin()
        self.http.side_effect = [response(200, USER), response(200, [dict(PROFILE, ativo=False)])]
        with self.assertRaises(auth.AuthError) as raised:
            self.auth.require_active()
        self.assertEqual(raised.exception.estado, 'sem_acesso')
        self.assertIsNone(self.auth.cached_profile())
        self.assertFalse(self.secrets)

    def test_provider_outage_can_keep_an_open_project_but_blocks_new_projects(self):
        self.signin()
        self.http.side_effect = requests.ConnectionError('secret from request')
        with self.assertRaises(auth.AuthError) as raised:
            self.auth.require_active(online=True)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn('secret from request', str(raised.exception))
        self.assertEqual(self.auth.require_active(online=False), PROFILE)
        self.assertFalse(self.auth.status()['autenticado'])
        self.assertEqual(list(self.secrets.values()), ['refresh1'])
        cold = auth._Equipe()
        with self.assertRaises(auth.AuthError):
            cold.require_active(online=False)

    def test_session_restore_rejects_revoked_token(self):
        self.signin()
        self.http.side_effect = [response(400, {'error_code': 'refresh_token_not_found'})]
        self.assertFalse(auth._Equipe().status()['autenticado'])
        self.assertFalse(self.secrets)

    def test_logout_clears_cofre_even_when_provider_offline(self):
        self.signin()
        self.http.side_effect = requests.ConnectionError()
        self.assertEqual(self.auth.logout()['estado'], 'aguardando_login')
        self.assertFalse(self.secrets)
        self.assertIsNone(self.auth.cached_profile())
        self.assertEqual(self.history()[-1]['tipo'], 'logout')

    def test_switch_keeps_local_events_separate_and_logs_explicit_profile_snapshot(self):
        self.signin()
        self.now += 70
        self.auth.activity()
        self.auth.activity()
        bruno_profile = dict(PROFILE, id=BRUNO, nome='Bruno', codigo='EV09')
        self.http.side_effect = [
            response(200, tokens('a2', 'r2')), response(200, {'id': BRUNO}),
            response(200, [bruno_profile]), response(204),
        ]
        self.assertEqual(self.auth.login('bruno@example.test', 'outra')['perfil'], bruno_profile)
        self.auth.record_event('xml_salvo', perfil=PROFILE, projeto_id=BRUNO, codigo_aplicado='EV08')
        self.assertEqual([e['tipo'] for e in self.history()], ['login_confirmado', 'atividade', 'troca_de_conta', 'xml_salvo'])
        self.assertEqual(self.history()[-1]['codigo_aplicado'], 'EV08')
        self.assertEqual(self.history(BRUNO)[0]['usuario'], BRUNO)

    def test_recovery_uses_email_otp_and_keeps_tokens_temporary(self):
        self.http.side_effect = [response(200), response(200, tokens()), response(200, USER),
                                 response(200, [PROFILE]), response(200, USER), response(204)]
        self.assertEqual(self.auth.request_recovery('alice@example.test'), {'ok': True})
        self.assertEqual(self.auth.reset_password('alice@example.test', ' 123456 ', 'nova-senha'), {'ok': True})
        self.assertEqual(self.http.call_args_list[1].kwargs['json']['type'], 'recovery')
        self.assertEqual(self.http.call_args_list[4].kwargs['json'], {'password': 'nova-senha'})
        self.assertFalse(self.secrets)

    def test_invite_validation_uses_invite_type(self):
        self.http.side_effect = [response(403, {'error_code': 'otp_expired'})]
        with self.assertRaisesRegex(auth.AuthError, 'Código inválido ou expirado'):
            self.auth.reset_password('alice@example.test', '123456', 'nova-senha', convite=True)
        self.assertEqual(self.http.call_args.kwargs['json']['type'], 'invite')

    def test_non_admin_cannot_call_edge_function(self):
        self.signin()
        self.http.side_effect = [response(200, USER), response(200, [PROFILE])]
        with self.assertRaisesRegex(auth.AuthError, 'exclusiva'):
            self.auth.admin('listar')
        self.assertEqual(self.http.call_count, 5)

    def test_reports_reject_a_snapshot_from_another_account(self):
        self.signin()
        self.http.side_effect = [response(200, USER), response(200, [PROFILE])]
        with self.assertRaisesRegex(auth.AuthError, 'conta que fez'):
            self.auth.sync_report({'usuario': BRUNO, 'projeto_id': ALICE})
        self.assertEqual(self.http.call_count, 5)

    def test_report_only_sends_known_metrics_and_preserves_revision(self):
        self.signin()
        self.http.side_effect = [response(200, USER), response(200, [PROFILE]), response(201, [])]
        self.assertEqual(self.auth.sync_report({
            'usuario': ALICE, 'projeto_id': BRUNO, 'tempo_ripagem_ms': 4600,
            'revisao': 4, 'visuais': {'aprovadas': 1}, 'feedback_etapa': 'legenda',
            'versao_app': '3.11.1', 'etapas_ms': {'transcricao': 1500},
            'xml': '/Users/local/projeto.xml', 'feedback': 'nome ou transcrição',
        }), {'ok': True})
        call = self.http.call_args
        self.assertTrue(call.args[1].endswith('/rest/v1/relatorios_ripagem'))
        payload = call.kwargs['json']
        self.assertEqual(payload['revisao'], 4)
        self.assertEqual(payload['visuais'], {'aprovadas': 1})
        self.assertFalse({'usuario', 'xml', 'feedback'} & payload.keys())
        self.assertIn('merge-duplicates', call.kwargs['headers']['Prefer'])

    def test_reports_read_uses_active_session_and_filters_returned_fields(self):
        self.signin()
        remote_row = {'projeto_id': BRUNO, 'usuario': ALICE, 'versao_app': '3.11.1', 'html': 'não é métrica'}
        self.http.side_effect = [response(200, USER), response(200, [PROFILE]), response(200, [remote_row])]
        result = self.auth.get_reports(limit=1, offset=2)
        self.assertEqual(result['proximo_offset'], 3)
        self.assertEqual(result['relatorios'], [{k: v for k, v in remote_row.items() if k != 'html'}])
        self.assertEqual(self.http.call_args.kwargs['params']['order'], 'atualizado_em.desc,projeto_id.asc')

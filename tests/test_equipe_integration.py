import io
import json
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import app
from plataforma import equipe_api as api, identidade_entrega as names, projetos


class Request:
    def __init__(self, path, *, body=None, origin=None):
        self.path = path
        self.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        self.headers = Message()
        self.headers['Host'] = '127.0.0.1:8765'
        if origin:
            self.headers['Origin'] = origin
        raw = json.dumps(body).encode() if body is not None else b''
        if raw:
            self.headers['Content-Length'] = str(len(raw))
            self.headers['Content-Type'] = 'application/json'
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.response_headers = {}

    local_request = app.H.local_request
    send = app.H.send

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers[name] = value

    def end_headers(self):
        pass


class LoginIntegrationTests(TestCase):
    def test_configured_gate_protects_pages_media_and_upload(self):
        error = api.auth.AuthError('Entre no aplicativo.', 401, 'aguardando_login')
        with patch.object(api.auth, 'require_active', side_effect=error) as check:
            page = Request('/fatiador?folder=outro')
            app.H.do_GET(page)
            self.assertEqual(page.status, 303)
            self.assertEqual(page.response_headers['Location'], '/entrar?voltar=/fatiador')
            media = Request('/files/teste/voz.wav')
            app.H.do_GET(media)
            self.assertEqual(media.status, 401)
            upload = Request('/upload', body={'fake': True})
            app.H.do_POST(upload)
            self.assertEqual(upload.status, 401)
            self.assertEqual(upload.rfile.tell(), 0)
            check.assert_called_with(online=True)
            ready = Request('/api/recursos')
            app.H.do_GET(ready)
            self.assertEqual(ready.status, 200)

    def test_local_origin_is_checked_before_credentials(self):
        post = Request('/api/equipe/entrar', origin='https://example.com',
                       body={'email': 'teste@example.com', 'senha': 'senha de teste'})
        with patch.object(api.auth, 'login') as login:
            app.H.do_POST(post)
            self.assertEqual(post.status, 403)
            login.assert_not_called()

    def test_credentials_do_not_enter_the_http_response(self):
        profile = {'id': str(uuid4()), 'codigo': 'EV08'}
        response = {'configurado': True, 'autenticado': True, 'perfil': profile}
        post = Request('/api/equipe/entrar', body={'email': 'teste@example.com', 'senha': 'senha de teste'})
        with patch.object(api.auth, 'login', return_value=response) as login:
            app.H.do_POST(post)
        login.assert_called_once_with('teste@example.com', 'senha de teste')
        self.assertEqual(json.loads(post.wfile.getvalue()), response)
        self.assertEqual(post.response_headers['Cache-Control'], 'no-store')

    def test_new_projects_use_active_code_while_reopening_preserves_saved_code(self):
        first, second = {'codigo': 'EV08'}, {'codigo': 'EV12'}
        with TemporaryDirectory() as directory:
            out = Path(directory)
            config = names.for_new_project({'numero_vsl': 2}, first)
            names.save(out, config)
            self.assertEqual(names.read(out)['editor_origem'], 'perfil')
            self.assertEqual(names.for_new_project({}, second)['editor'], 'EV12')
            self.assertEqual(names.read(out)['editor'], 'EV08')
            self.assertEqual(names.for_new_project({'editor': 'ev05'}, second)['editor_origem'], 'manual')
            names.save(out, {'editor': 'FX7'})
            self.assertEqual(names.read(out)['editor_origem'], 'manual')

    def test_editor_saving_xml_can_differ_from_project_code(self):
        profile = {'id': str(uuid4()), 'codigo': 'EV12'}
        with TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(api.auth, 'record_event') as record:
                api.xml_saved(out, profile, {'medicao_encerrada': True, 'xml_salvo': 'trocas/Funil.xml'}, 'EV08')
                meta = projetos.read_meta(out)
                self.assertEqual(meta['ultimo_xml_salvo_por']['usuario'], profile['id'])
                self.assertEqual(meta['ultimo_xml_salvo_por']['codigo_aplicado'], 'EV08')
                record.assert_called_once_with('xml_salvo', perfil=profile, projeto_id=meta['projeto_id'], codigo_aplicado='EV08')

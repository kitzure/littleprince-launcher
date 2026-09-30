#!/usr/bin/env python3
"""Regression tests: pack installs must never fall back to Google Drive."""
import ast
import http.server
import importlib.machinery
import importlib.util
import io
import json
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(sys.argv.pop(1)) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'lpo')]
import server
import fetch_cloud
import pack_download as policy
loader = importlib.machinery.SourceFileLoader('windows_launcher_test', str(ROOT / 'Start_Server_GUI.pyw'))
spec = importlib.util.spec_from_loader(loader.name, loader)
gui = importlib.util.module_from_spec(spec)
loader.exec_module(gui)

payload = io.BytesIO()
with zipfile.ZipFile(payload, 'w') as archive:
    archive.writestr('cloud/LP1/download-test.txt', 'local regression fixture')
ZIP_BYTES = payload.getvalue()
SEEN = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        SEEN.append((self.path, self.headers.get('User-Agent')))
        if self.path == '/redirect-drive':
            self.send_response(302)
            self.send_header('Location', 'https://drive.google.com/file/d/disabled-test/view')
            self.end_headers()
        elif self.path == '/redirect-ok':
            self.send_response(302)
            self.send_header('Location', '/pack.zip')
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Length', str(len(ZIP_BYTES)))
            self.end_headers()
            self.wfile.write(ZIP_BYTES)

    def log_message(self, *args):
        pass


class NoDriveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:%d' % cls.httpd.server_port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def test_builtin_sources(self):
        self.assertEqual(set(gui.PACK_SOURCES), {'LP1', 'LP2', 'LP3', 'lpo', 'browser'})
        self.assertEqual(set(server.PACK_SOURCES), {'LP1', 'LP2', 'LP3'})
        for table in (gui.PACK_SOURCES, server.PACK_SOURCES):
            for urls in table.values():
                self.assertEqual(len(urls), 1)
                for url in urls:
                    self.assertEqual(policy.validate_pack_url(url), url)
                    self.assertIn(urllib.parse.urlsplit(url).hostname, ('files.catbox.moe', 'pixeldrain.com'))

    def test_drive_hosts_and_non_http_rejected(self):
        for url in ('https://drive.google.com/file/d/test/view',
                    'https://DRIVE.GOOGLE.COM./uc?id=test',
                    'https://docs.google.com/uc?id=test',
                    'https://drive.usercontent.google.com/download?id=test',
                    'https://test.googleusercontent.com/file', 'file:///tmp/test.zip'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                policy.validate_pack_url(url)

    def test_self_host_accepted(self):
        self.assertEqual(policy.validate_pack_url(self.base + '/pack.zip'), self.base + '/pack.zip')
        self.assertEqual(policy.validate_pack_url('https://downloads.example.org/pack.zip'), 'https://downloads.example.org/pack.zip')

    def test_old_saved_drive_choice_migrates(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'settings.json'
            file.write_text(json.dumps({'method': 'gdrive', 'custom': {'LP1': 'https://drive.google.com/uc?id=test'}}))
            with patch.object(server, 'DOWNLOAD_SETTINGS_FILE', file):
                self.assertEqual(server.download_settings(), {'method': 'auto', 'custom': {}})
                self.assertEqual(server.pack_sources('LP1'), gui.PACK_SOURCES['LP1'])

    def test_custom_and_auto_sources(self):
        url = self.base + '/pack.zip'
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'settings.json'
            with patch.object(server, 'DOWNLOAD_SETTINGS_FILE', file):
                file.write_text(json.dumps({'method': 'custom', 'custom': {'lp1': url}}))
                self.assertEqual(server.pack_sources('LP1'), [url])
                file.write_text(json.dumps({'method': 'auto', 'custom': {'LP1': url}}))
                self.assertEqual(server.pack_sources('LP1'), [url] + gui.PACK_SOURCES['LP1'])

    def test_ui_has_no_drive_option_and_migrates_selection(self):
        captured = {}
        def capture(*args, **kwargs):
            captured['options'] = [option for group, options in args[2] for option in options]
            captured.update(kwargs)
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'settings.json'
            file.write_text(json.dumps({'method': 'gdrive'}))
            backend = types.SimpleNamespace(_settings_file=str(file), ui=object(), _save_settings=lambda *a: None)
            with patch.object(gui.launcher_ui, 'open_settings_window', capture):
                gui.WindowsBackend.open_settings(backend)
        self.assertEqual([value for text, value in captured['options']], ['auto', 'pixeldrain', 'custom'])
        self.assertNotIn('Google Drive', str(captured['options']))
        self.assertEqual(list(captured['values']['radio'].values()), ['auto'])

    def test_save_rejects_drive_and_accepts_self_host(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'settings.json'
            backend = types.SimpleNamespace(_settings_file=str(file), ui=types.SimpleNamespace(note=lambda *a: None))
            bad = types.SimpleNamespace(get=lambda: 'https://drive.google.com/uc?id=test')
            result = gui.WindowsBackend._save_settings(backend, {'source': 'custom'}, {'LP1': bad})
            self.assertFalse(result[0])
            self.assertFalse(file.exists())
            good = types.SimpleNamespace(get=lambda: self.base + '/pack.zip')
            self.assertTrue(gui.WindowsBackend._save_settings(backend, {'source': 'custom'}, {'LP1': good})[0])
            self.assertEqual(json.loads(file.read_text())['custom']['LP1'], self.base + '/pack.zip')

    def test_drive_rejected_before_network(self):
        with patch('urllib.request.OpenerDirector.open') as network:
            with self.assertRaises(ValueError):
                policy.open_pack('https://drive.google.com/uc?id=test')
            network.assert_not_called()

    def test_redirect_to_drive_is_rejected(self):
        with self.assertRaises(ValueError):
            policy.open_pack(self.base + '/redirect-drive')

    def test_allowed_redirect_returns_zip(self):
        with policy.open_pack(self.base + '/redirect-ok') as response:
            self.assertEqual(response.read(), ZIP_BYTES)
        self.assertTrue(SEEN[-1][1].startswith('Mozilla/5.0'))

    def test_launcher_fetches_and_extracts_real_local_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(gui.fetch_pack([self.base + '/pack.zip'], temp, log=lambda *a: None), 1)
            self.assertEqual((Path(temp) / 'cloud/LP1/download-test.txt').read_text(), 'local regression fixture')

    def test_server_worker_fetches_and_extracts_real_local_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / 'settings.json'
            file.write_text(json.dumps({'method': 'custom', 'custom': {'LP1': self.base + '/pack.zip'}}))
            state = {'state': 'downloading'}
            with patch.object(server, 'DOWNLOAD_SETTINGS_FILE', file), patch.object(server, 'cloud_dir', return_value=root / 'cloud'), patch.object(server, 'CLOUD_DOWNLOADS', {'LP1': state}), patch.object(fetch_cloud, 'check', return_value=([], [])), patch.object(fetch_cloud, 'client_bad', return_value=[]), patch.object(server, 'disk_state_invalidate'):
                server.cloud_download_worker('LP1')
            self.assertEqual(state['state'], 'ready')
            self.assertEqual((root / 'cloud/LP1/download-test.txt').read_text(), 'local regression fixture')

    def test_failed_mirror_does_not_try_drive(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=urllib.error.URLError('mirror offline')) as network:
            with tempfile.TemporaryDirectory() as temp, self.assertRaises(urllib.error.URLError):
                gui.fetch_pack(gui.PACK_SOURCES['LP1'], temp, log=lambda *a: None)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(network.call_args.args[0].full_url, gui.PACK_SOURCES['LP1'][0])


if __name__ == '__main__':
    unittest.main(verbosity=2)

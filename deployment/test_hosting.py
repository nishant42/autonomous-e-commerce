import base64
import http.client
import os
import threading
import unittest
from unittest.mock import patch
import serve


class HostedAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {
            'VIEWER_PASSWORD': 'test-viewer-password',
            'OPERATOR_PASSWORD': 'test-operator-password',
            'SHOP_PUBLIC_URL': 'https://shop.example.test/dk/store',
            'ENGINE_PUBLIC_URL': 'https://agents.example.test',
        })
        cls.env.start()
        cls.http = serve.server.ThreadingHTTPServer(('127.0.0.1', 0), serve.HostedHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.env.stop()

    def request(self, path, user=None, method='GET', extra=None):
        headers = dict(extra or {})
        if user:
            password = 'test-operator-password' if user == 'operator' else 'test-viewer-password'
            headers['Authorization'] = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        conn.request(method, path, body='{}' if method == 'POST' else None, headers=headers)
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def test_health_is_public_but_console_is_not(self):
        self.assertEqual(self.request('/healthz')[0], 200)
        self.assertEqual(self.request('/console')[0], 401)

    def test_viewer_can_read_config_and_guide(self):
        status, body = self.request('/api/public-config', 'recruiter')
        self.assertEqual(status, 200)
        self.assertIn(b'https://shop.example.test/dk/store', body)
        self.assertEqual(self.request('/ui/agents-guide.html', 'recruiter')[0], 200)

    def test_viewer_cannot_write(self):
        self.assertEqual(self.request('/api/reset', 'recruiter', 'POST')[0], 403)

    def test_traversal_and_source_import_blocked(self):
        self.assertEqual(self.request('/ui/../.env', 'recruiter')[0], 404)
        self.assertEqual(self.request('/api/code?module=deployment', 'recruiter')[0], 403)

    def test_operator_requires_json_and_same_origin(self):
        self.assertEqual(self.request('/unused', 'operator', 'POST')[0], 415)
        headers = {'Content-Type': 'application/json', 'Origin': 'https://evil.example'}
        self.assertEqual(self.request('/unused', 'operator', 'POST', headers)[0], 403)
        headers['Origin'] = 'https://agents.example.test'
        self.assertEqual(self.request('/unused', 'operator', 'POST', headers)[0], 404)

    def test_malformed_credentials_rejected(self):
        for token in ('', 'Bearer test', 'Basic !!!', 'Basic Og=='):
            self.assertIsNone(serve.role(token))


if __name__ == '__main__':
    unittest.main()

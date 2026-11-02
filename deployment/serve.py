"""Authenticated hosting entrypoint; local server.py remains unchanged."""
import base64
import hmac
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
import server


def role(header):
    try:
        scheme, encoded = header.split(' ', 1)
        if scheme.lower() != 'basic':
            return None
        user, password = base64.b64decode(encoded, validate=True).decode().split(':', 1)
    except (ValueError, UnicodeError):
        return None
    for name, variable in [('operator', 'OPERATOR_PASSWORD'), ('recruiter', 'VIEWER_PASSWORD')]:
        expected = os.environ.get(variable, '')
        if user == name and expected and hmac.compare_digest(password.encode(), expected.encode()):
            return name
    return None


class HostedHandler(server.Handler):
    def authorize(self):
        who = role(self.headers.get('Authorization', ''))
        if who:
            return who
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Halden demo", charset="UTF-8"')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        return None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/healthz':
            return self.send_json({'status': 'ok'})
        if not self.authorize():
            return
        if path == '/api/code':
            return self.send_json({'error': 'Source inspection is available in the GitHub repository'}, 403)
        if path == '/api/public-config':
            return self.send_json({'shop_url': os.environ.get('SHOP_PUBLIC_URL', '')})
        return super().do_GET()

    def do_POST(self):
        who = self.authorize()
        if not who:
            return
        if who != 'operator' and urlsplit(self.path).path != '/api/explain-quantity':
            return self.send_json({'error': 'Operator access required to change state'}, 403)
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            return self.send_json({'error': 'JSON required'}, 415)
        origin = self.headers.get('Origin')
        if origin and origin != os.environ['ENGINE_PUBLIC_URL']:
            return self.send_json({'error': 'Origin not allowed'}, 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            size = -1
        if not 0 <= size <= 1048576:
            return self.send_json({'error': 'Invalid request size'}, 413)
        return super().do_POST()

    def send_file(self, path):
        # Do not let /ui/../ paths read environment files or the database.
        resolved = Path(path).resolve()
        if Path(server.UI).resolve() not in resolved.parents:
            return self.send_json({'error': 'Not found'}, 404)
        return super().send_file(str(resolved))


def main():
    for key in ('OPERATOR_PASSWORD', 'VIEWER_PASSWORD'):
        if len(os.environ.get(key, '')) < 16:
            raise SystemExit(key + ' must contain at least 16 characters')
    if os.environ['OPERATOR_PASSWORD'] == os.environ['VIEWER_PASSWORD']:
        raise SystemExit('Use different operator and recruiter passwords')
    os.environ.setdefault('ENGINE_PUBLIC_URL', os.environ.get('RENDER_EXTERNAL_URL', ''))
    for key in ('SHOP_PUBLIC_URL', 'ENGINE_PUBLIC_URL'):
        value = os.environ.get(key, '')
        if key == 'SHOP_PUBLIC_URL' and not value:
            continue  # Shop is wired after its own first deployment.
        if urlsplit(value).scheme != 'https':
            raise SystemExit(key + ' must be an HTTPS URL')
    Path(server.db.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    server.ensure_db().close()
    address = ('0.0.0.0', int(os.environ.get('PORT', '8787')))
    server.ThreadingHTTPServer(address, HostedHandler).serve_forever()


if __name__ == '__main__':
    main()
